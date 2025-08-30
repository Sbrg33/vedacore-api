"""
API Key Routing Middleware

Implements PM5.txt Day 3 requirement: auto-route **new** API keys to v1 only.
Blocks legacy endpoint access for new keys while maintaining compatibility for existing keys.

Key Features:
- New API keys created after cutoff date are v1-only
- Existing API keys maintain legacy access during migration window
- Automatic redirection with proper HTTP status codes
- Comprehensive metrics and logging for migration tracking
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import jwt

from app.core.environment import get_complete_config

logger = logging.getLogger(__name__)

# PM5.txt: Day 3 cutoff date for new API key routing
# Environment variable allows flexible cutoff date configuration
API_KEY_V1_CUTOFF_DATE = os.getenv(
    "API_KEY_V1_CUTOFF_DATE",
    "2025-08-31"  # Default cutoff: T+3 days from PM5.txt go-live
)

# Convert to datetime object for comparison
try:
    V1_CUTOFF = datetime.fromisoformat(API_KEY_V1_CUTOFF_DATE).replace(tzinfo=timezone.utc)
    logger.info(f"🔄 API key v1 routing cutoff: {V1_CUTOFF}")
except ValueError:
    logger.error(f"Invalid API_KEY_V1_CUTOFF_DATE format: {API_KEY_V1_CUTOFF_DATE}")
    V1_CUTOFF = datetime(2025, 8, 31, tzinfo=timezone.utc)


class APIKeyRoutingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce v1-only routing for new API keys.
    
    PM5.txt Implementation:
    - Day 3: auto-route **new** API keys to v1 only
    - Legacy blocked for new keys, allowed for existing keys
    - Graceful migration with proper HTTP status codes
    """

    def __init__(self, app, enable_routing: bool = True):
        super().__init__(app)
        self.enable_routing = enable_routing
        self.config = get_complete_config()
        
        # Legacy endpoints that should be blocked for new API keys
        self.legacy_prefixes = [
            "/legacy/",
            "/api/signals/",
            "/api/houses/",
            "/api/kp/",
            "/api/dasha/",
            "/api/nodes/",
            "/api/eclipse/",
            "/api/moon/",
            "/api/micro/",
            "/api/strategy/",
            "/api/advisory/",
            "/api/tara/",
            "/api/fortuna/",
            "/api/transit-events/",
            "/api/ats/",
            "/api/panchanga/",
            "/api/kp-horary/",
            "/api/kp-ruling-planets/"
        ]
        
        # V1 endpoint mappings for automatic redirection
        self.legacy_to_v1_mappings = {
            "/api/houses": "/api/v1/jyotish/houses",
            "/api/kp/ruling-planets": "/api/v1/kp/ruling-planets",
            "/api/dasha": "/api/v1/jyotish/dasha",
            "/api/signals": "/api/v1/kp/signals",
            "/legacy/kp/rp": "/api/v1/kp/ruling-planets",
            "/legacy/houses": "/api/v1/jyotish/houses"
        }
        
        logger.info(f"🔄 API Key routing middleware initialized (enabled: {enable_routing})")
        logger.info(f"   Protecting {len(self.legacy_prefixes)} legacy endpoint patterns")
        logger.info(f"   V1 cutoff date: {V1_CUTOFF}")

    async def dispatch(self, request: Request, call_next):
        """Process request and apply API key routing rules."""
        
        # Skip routing if disabled
        if not self.enable_routing:
            return await call_next(request)
            
        # Skip routing for non-API endpoints
        if not self._is_api_endpoint(request.url.path):
            return await call_next(request)
            
        # Extract API key information
        api_key_info = await self._extract_api_key_info(request)
        
        # Skip routing if no valid API key found
        if not api_key_info:
            return await call_next(request)
            
        # Apply routing rules based on API key creation date
        routing_response = await self._apply_routing_rules(request, api_key_info)
        if routing_response:
            return routing_response
            
        # Continue with normal request processing
        return await call_next(request)

    def _is_api_endpoint(self, path: str) -> bool:
        """Check if path is an API endpoint that needs routing."""
        return (
            path.startswith("/api/") or 
            path.startswith("/legacy/") or
            path in ["/stream/", "/ws"]
        )

    async def _extract_api_key_info(self, request: Request) -> Optional[dict]:
        """Extract API key information from request."""
        try:
            # Try Authorization header first
            auth_header = request.headers.get("Authorization")
            token = None
            
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            elif "token" in request.query_params:
                # Handle streaming authentication via query parameter
                token = request.query_params["token"]
            
            if not token:
                return None
                
            # Decode JWT to extract API key information
            payload = jwt.decode(
                token,
                self.config.database.auth_secret,
                algorithms=["HS256"],
                options={"verify_exp": False}  # We just need the metadata
            )
            
            # Extract API key creation timestamp
            api_key_id = payload.get("sub")
            issued_at = payload.get("iat")
            
            if not api_key_id or not issued_at:
                return None
                
            key_created_at = datetime.fromtimestamp(issued_at, tz=timezone.utc)
            
            return {
                "api_key_id": api_key_id,
                "tenant_id": payload.get("tid") or payload.get("tenant_id"),
                "created_at": key_created_at,
                "is_new_key": key_created_at >= V1_CUTOFF,
                "payload": payload
            }
            
        except Exception as e:
            logger.debug(f"Failed to extract API key info: {e}")
            return None

    async def _apply_routing_rules(self, request: Request, api_key_info: dict) -> Optional[Response]:
        """Apply routing rules based on API key status."""
        
        path = request.url.path
        is_new_key = api_key_info["is_new_key"]
        api_key_id = api_key_info["api_key_id"]
        
        # Log API key routing decision
        key_status = "new" if is_new_key else "existing"
        logger.debug(f"API key routing: {api_key_id} ({key_status}) -> {path}")
        
        # If this is a new key accessing legacy endpoint, block or redirect
        if is_new_key and self._is_legacy_endpoint(path):
            return await self._handle_new_key_legacy_access(request, api_key_info, path)
            
        # If this is an existing key, allow normal access
        return None

    def _is_legacy_endpoint(self, path: str) -> bool:
        """Check if path is a legacy endpoint."""
        return any(path.startswith(prefix) for prefix in self.legacy_prefixes)

    async def _handle_new_key_legacy_access(
        self, 
        request: Request, 
        api_key_info: dict, 
        path: str
    ) -> Response:
        """Handle new API key attempting to access legacy endpoint."""
        
        api_key_id = api_key_info["api_key_id"]
        tenant_id = api_key_info["tenant_id"]
        
        # Log blocked access attempt
        logger.warning(
            f"🚫 Legacy access blocked for new API key: {api_key_id} -> {path}",
            extra={
                "api_key_id": api_key_id,
                "tenant_id": tenant_id,
                "blocked_path": path,
                "reason": "new_key_legacy_blocked"
            }
        )
        
        # Try to find v1 equivalent for automatic redirection
        v1_path = self._get_v1_equivalent(path)
        
        if v1_path and os.getenv("API_KEY_ROUTING_AUTO_REDIRECT", "true").lower() == "true":
            # Return redirect response to v1 equivalent
            redirect_url = str(request.url).replace(path, v1_path)
            
            logger.info(
                f"🔄 Auto-redirecting new API key to v1: {path} -> {v1_path}",
                extra={
                    "api_key_id": api_key_id,
                    "tenant_id": tenant_id,
                    "original_path": path,
                    "redirected_path": v1_path
                }
            )
            
            return JSONResponse(
                status_code=301,  # Permanent redirect
                content={
                    "error": {
                        "code": "LEGACY_ENDPOINT_DEPRECATED",
                        "message": "Legacy endpoint access blocked for new API keys",
                        "details": {
                            "reason": "New API keys must use v1 endpoints",
                            "redirect_to": v1_path,
                            "migration_guide": "https://docs.vedacore.com/migration/v1",
                            "api_key_created": api_key_info["created_at"].isoformat(),
                            "cutoff_date": V1_CUTOFF.isoformat()
                        }
                    }
                },
                headers={
                    "Location": redirect_url,
                    "X-API-Migration": "v1-required",
                    "X-Deprecated-Endpoint": path,
                    "X-Recommended-Endpoint": v1_path
                }
            )
        else:
            # Return 403 Forbidden with migration guidance
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "LEGACY_ACCESS_FORBIDDEN",
                        "message": "Legacy endpoint access not allowed for new API keys",
                        "details": {
                            "reason": "API key created after v1 migration cutoff",
                            "api_key_created": api_key_info["created_at"].isoformat(),
                            "cutoff_date": V1_CUTOFF.isoformat(),
                            "available_endpoints": "https://docs.vedacore.com/api/v1",
                            "migration_guide": "https://docs.vedacore.com/migration/v1",
                            "support": "contact@vedacore.com"
                        }
                    }
                },
                headers={
                    "X-API-Migration": "v1-required",
                    "X-Deprecated-Endpoint": path,
                    "Retry-After": "never"
                }
            )

    def _get_v1_equivalent(self, legacy_path: str) -> Optional[str]:
        """Get v1 equivalent path for legacy endpoint."""
        
        # Direct mappings
        if legacy_path in self.legacy_to_v1_mappings:
            return self.legacy_to_v1_mappings[legacy_path]
            
        # Pattern-based mappings
        if legacy_path.startswith("/api/houses"):
            return legacy_path.replace("/api/houses", "/api/v1/jyotish/houses")
        elif legacy_path.startswith("/api/kp/"):
            return legacy_path.replace("/api/kp/", "/api/v1/kp/")
        elif legacy_path.startswith("/api/signals"):
            return legacy_path.replace("/api/signals", "/api/v1/kp/signals")
        elif legacy_path.startswith("/legacy/"):
            # Remove /legacy prefix and map to appropriate v1 path
            clean_path = legacy_path.replace("/legacy/", "/")
            if clean_path.startswith("kp/"):
                return f"/api/v1/kp/{clean_path[3:]}"
            elif clean_path.startswith("houses"):
                return f"/api/v1/jyotish/houses"
                
        return None


def install_api_key_routing_middleware(app, enable_routing: bool = None):
    """Install API key routing middleware with environment-based configuration."""
    
    # Check if routing should be enabled
    if enable_routing is None:
        enable_routing = os.getenv("API_KEY_ROUTING_ENABLED", "true").lower() == "true"
    
    # Only install if v1 routing is enabled
    config = get_complete_config()
    if not config.feature_v1_routing:
        logger.info("⏭️  API key routing disabled (FEATURE_V1_ROUTING=false)")
        return False
        
    # Check environment requirements
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "production" and not os.getenv("API_KEY_V1_CUTOFF_DATE"):
        logger.error("🚨 PRODUCTION ERROR: API_KEY_V1_CUTOFF_DATE must be set for production")
        raise RuntimeError("API_KEY_V1_CUTOFF_DATE required for production deployment")
    
    # Install middleware
    app.add_middleware(APIKeyRoutingMiddleware, enable_routing=enable_routing)
    
    logger.info("🔄 API key routing middleware installed")
    logger.info(f"   Routing enabled: {enable_routing}")
    logger.info(f"   V1 cutoff date: {V1_CUTOFF}")
    logger.info(f"   Auto-redirect: {os.getenv('API_KEY_ROUTING_AUTO_REDIRECT', 'true')}")
    
    return True