"""
Stream Token Validation Middleware

Implements PM5.txt Section 3 requirement for token replay prevention.
Validates streaming tokens and enforces one-time use policy.

Features:
- JTI-based replay prevention
- Token validation with comprehensive auditing
- Performance-optimized Redis backend
- Security-focused error handling
"""

import logging
from typing import Optional
import jwt
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from api.services.token_auditing import get_token_audit_service, audit_token_replay_attempt
from app.core.environment import get_complete_config
from app.core.logging import get_api_logger

logger = get_api_logger("stream_token_validation")


class StreamTokenValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate streaming tokens and prevent replay attacks."""

    def __init__(self, app):
        super().__init__(app)
        self.config = get_complete_config()
        
        # Streaming endpoints that require token validation
        self.streaming_endpoints = [
            "/stream/",
            "/api/v1/stream",
            "/ws",
            "/api/v1/ws"
        ]
        
        logger.info("🔒 Stream token validation middleware initialized")
    
    async def dispatch(self, request: Request, call_next):
        """Validate streaming tokens and check for replay attempts."""
        
        # Skip non-streaming endpoints
        if not self._is_streaming_endpoint(request.url.path):
            return await call_next(request)
        
        # Extract and validate token
        token_validation = await self._validate_streaming_token(request)
        
        if token_validation["error"]:
            return self._create_error_response(token_validation["error"])
        
        # Add token payload to request state for downstream use
        if token_validation["payload"]:
            request.state.token_payload = token_validation["payload"]
            request.state.streaming_validated = True
        
        return await call_next(request)
    
    def _is_streaming_endpoint(self, path: str) -> bool:
        """Check if path is a streaming endpoint."""
        return any(path.startswith(endpoint) for endpoint in self.streaming_endpoints)
    
    async def _validate_streaming_token(self, request: Request) -> dict:
        """Validate streaming token and check for replay attempts."""
        try:
            # Extract token from query parameter (streaming requirement)
            token = request.query_params.get("token")
            if not token:
                return {"error": "missing_token", "payload": None}
            
            # Decode token to get payload
            try:
                payload = jwt.decode(
                    token,
                    self.config.database.auth_secret,
                    algorithms=["HS256"]
                )
            except jwt.InvalidTokenError as e:
                # Audit invalid token attempt
                try:
                    await self._audit_invalid_token(request, str(e))
                except:
                    pass
                return {"error": "invalid_token", "payload": None}
            
            # Check if token is streaming-specific
            if payload.get("aud") != "stream":
                return {"error": "invalid_audience", "payload": None}
            
            # Check for JTI replay attempt (PM5.txt requirement)
            jti = payload.get("jti")
            if jti:
                audit_service = await get_token_audit_service()
                if await audit_service.check_jti_used(jti):
                    # Audit replay attempt
                    await self._audit_replay_attempt(request, payload)
                    return {"error": "token_replay", "payload": payload}
                
                # Mark JTI as used
                ttl = payload.get("exp", 0) - payload.get("iat", 0)
                await audit_service.mark_jti_used(jti, max(300, ttl))
            
            # Audit successful validation
            await self._audit_successful_validation(request, payload)
            
            return {"error": None, "payload": payload}
            
        except Exception as e:
            logger.error(f"Stream token validation error: {e}")
            return {"error": "validation_failed", "payload": None}
    
    async def _audit_invalid_token(self, request: Request, error: str):
        """Audit invalid token attempt."""
        try:
            from api.services.token_auditing import audit_invalid_token
            await audit_invalid_token(
                token_payload={"sub": "unknown", "jti": "unknown"},
                error=error,
                client_ip=self._get_client_ip(request)
            )
        except Exception as e:
            logger.warning(f"Failed to audit invalid token: {e}")
    
    async def _audit_replay_attempt(self, request: Request, payload: dict):
        """Audit token replay attempt (security incident)."""
        try:
            await audit_token_replay_attempt(
                token_payload=payload,
                client_ip=self._get_client_ip(request),
                endpoint=request.url.path
            )
            
            logger.warning(
                f"🚨 Token replay attempt detected: JTI {payload.get('jti')} from {self._get_client_ip(request)}",
                extra={
                    "security_incident": "token_replay",
                    "jti": payload.get("jti"),
                    "tenant_id": payload.get("tid"),
                    "client_ip": self._get_client_ip(request),
                    "endpoint": request.url.path
                }
            )
        except Exception as e:
            logger.warning(f"Failed to audit replay attempt: {e}")
    
    async def _audit_successful_validation(self, request: Request, payload: dict):
        """Audit successful token validation."""
        try:
            from api.services.token_auditing import audit_token_validated
            await audit_token_validated(
                token_payload=payload,
                client_ip=self._get_client_ip(request),
                endpoint=request.url.path
            )
        except Exception as e:
            logger.warning(f"Failed to audit token validation: {e}")
    
    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP address."""
        # Check for forwarded headers (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return None
    
    def _create_error_response(self, error_type: str) -> Response:
        """Create appropriate error response for token validation failures."""
        
        error_responses = {
            "missing_token": {
                "status_code": 401,
                "detail": {
                    "error": "authentication_required",
                    "message": "Streaming token required in query parameter",
                    "hint": "Add ?token=your_stream_token to the URL"
                }
            },
            "invalid_token": {
                "status_code": 401,
                "detail": {
                    "error": "invalid_token",
                    "message": "Invalid or expired streaming token",
                    "hint": "Request new token from /api/v1/auth/stream-token"
                }
            },
            "invalid_audience": {
                "status_code": 403,
                "detail": {
                    "error": "invalid_token_type",
                    "message": "Token not valid for streaming",
                    "hint": "Use streaming-specific token from /api/v1/auth/stream-token"
                }
            },
            "token_replay": {
                "status_code": 409,
                "detail": {
                    "error": "token_already_used",
                    "message": "Streaming token can only be used once",
                    "hint": "Request new token for each streaming connection"
                }
            },
            "validation_failed": {
                "status_code": 500,
                "detail": {
                    "error": "token_validation_error",
                    "message": "Unable to validate streaming token"
                }
            }
        }
        
        error_config = error_responses.get(error_type, error_responses["validation_failed"])
        
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=error_config["status_code"],
            content=error_config["detail"],
            headers={
                "X-Token-Validation": "failed",
                "X-Error-Type": error_type,
                "Cache-Control": "no-store"  # Don't cache error responses
            }
        )


def install_stream_token_validation_middleware(app):
    """Install stream token validation middleware."""
    app.add_middleware(StreamTokenValidationMiddleware)
    logger.info("🔒 Stream token validation middleware installed")