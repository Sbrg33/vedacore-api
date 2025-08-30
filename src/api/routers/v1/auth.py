"""
API v1 Auth Router

Authentication endpoints for streaming tokens and auth management.
Implements PM requirements for one-time streaming tokens.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer
import jwt

from .models import (
    BaseResponse,
    ErrorResponse,
    StreamTokenRequest, 
    StreamTokenResponse,
    PATH_TEMPLATES
)
from app.core.environment import get_complete_config

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
security = HTTPBearer()


def get_jwt_secret() -> str:
    """Get JWT secret for token signing."""
    config = get_complete_config()
    return config.database.auth_secret


def create_stream_token(
    topic: str,
    ttl_seconds: int,
    tenant_id: str,
    api_key_id: str
) -> tuple[str, datetime]:
    """
    Create one-time streaming token with PM requirements:
    - aud="stream", topic-scoped, jti for single-use
    - TTL ≤ 300 seconds
    """
    if ttl_seconds > 300:
        raise ValueError("TTL cannot exceed 300 seconds")
    
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)
    jti = str(uuid4())
    
    payload = {
        "iss": "vedacore",
        "aud": "stream", 
        "sub": api_key_id,
        "tid": tenant_id,
        "topic": topic,
        "iat": now.timestamp(),
        "exp": expires_at.timestamp(),
        "jti": jti
    }
    
    token = jwt.encode(payload, get_jwt_secret(), algorithm="HS256")
    return token, expires_at


async def verify_api_token(request: Request, credentials = Depends(security)) -> dict:
    """
    Verify API token and extract tenant/api_key info.
    Used for stream token issuance authorization.
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            get_jwt_secret(),
            algorithms=["HS256"]
        )
        
        # Extract tenant and API key info
        return {
            "tenant_id": payload.get("tid", "unknown"),
            "api_key_id": payload.get("sub", "unknown"),
            "payload": payload
        }
        
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse.create(
                code="AUTH_ERROR",
                message="Invalid authentication token",
                details={"error": str(e)}
            ).dict()
        )


@router.post("/stream-token", response_model=BaseResponse, summary="Issue Streaming Token")
async def issue_stream_token(
    request: StreamTokenRequest,
    auth_info: dict = Depends(verify_api_token)
) -> BaseResponse:
    """
    Issue one-time streaming token for SSE/WebSocket authentication.
    
    Creates JWT token with:
    - Topic-scoped access (only specified topic allowed)
    - Short TTL (≤ 300 seconds, default 180)
    - Single-use enforcement via jti
    - Proper audience claim for stream validation
    """
    try:
        # Validate topic authorization (simplified for now)
        valid_topics = [
            "kp.ruling_planets",
            "kp.moon.chain", 
            "jyotish.transit_events",
            "location.activation"
        ]
        
        if request.topic not in valid_topics:
            raise HTTPException(
                status_code=403,
                detail=ErrorResponse.create(
                    code="AUTH_ERROR",
                    message=f"Access denied for topic: {request.topic}",
                    details={"valid_topics": valid_topics}
                ).dict()
            )
        
        # Create streaming token
        token, expires_at = create_stream_token(
            topic=request.topic,
            ttl_seconds=request.ttl_seconds,
            tenant_id=auth_info["tenant_id"],
            api_key_id=auth_info["api_key_id"]
        )
        
        # Audit token issuance (PM5.txt requirement)
        try:
            from api.services.token_auditing import audit_token_issued
            token_payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
            await audit_token_issued(
                token_payload=token_payload,
                client_ip=request.client.host if hasattr(request, 'client') else None,
                endpoint="/api/v1/auth/stream-token"
            )
        except Exception as e:
            logger.warning(f"Failed to audit token issuance: {e}")
        
        # Store JTI for one-time use enforcement (implemented via token auditing)
        try:
            from api.services.token_auditing import get_token_audit_service
            audit_service = await get_token_audit_service()
            token_payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
            await audit_service.mark_jti_used(token_payload["jti"], request.ttl_seconds)
        except Exception as e:
            logger.warning(f"Failed to track JTI: {e}")
        
        response_data = StreamTokenResponse(
            token=token,
            expires_at=expires_at,
            topic=request.topic
        )
        
        return BaseResponse.create(
            data=response_data,
            path_template=PATH_TEMPLATES["auth_stream_token"],
            topic=request.topic,
            ttl_seconds=request.ttl_seconds,
            compute_units=0.01
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"Token creation failed: {str(e)}"
            ).dict()
        )


@router.get("/validate", response_model=BaseResponse, summary="Validate Token")
async def validate_token(auth_info: dict = Depends(verify_api_token)) -> BaseResponse:
    """
    Validate current authentication token.
    
    Returns token information and validity status.
    Useful for client token health checks.
    """
    payload = auth_info["payload"]
    
    # Calculate remaining TTL
    now = datetime.utcnow().timestamp()
    exp = payload.get("exp", now)
    ttl_remaining = max(0, int(exp - now))
    
    validation_data = {
        "valid": True,
        "tenant_id": auth_info["tenant_id"],
        "api_key_id": auth_info["api_key_id"],
        "ttl_remaining": ttl_remaining,
        "issued_at": datetime.fromtimestamp(payload.get("iat", now)),
        "expires_at": datetime.fromtimestamp(exp)
    }
    
    return BaseResponse.create(
        data=validation_data,
        compute_units=0.01
    )