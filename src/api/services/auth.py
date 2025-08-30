"""
services/auth.py — Browser-compatible JWT verification for FastAPI streaming.

Features:
- Supports JWKS (RS256/ES256) via AUTH_JWKS_URL or HS256 via AUTH_JWT_SECRET
- Browser-compatible: Query parameter authentication (EventSource/WebSocket limitation)
- Validates exp/iat; optional aud/iss; enforces presence of tenant_id by default
- Fail-fast validation: prevents both JWKS and HS256 being configured
- Returns AuthContext object for use in routers/services

Environment variables:
- AUTH_JWKS_URL        : https://.../.well-known/jwks.json (preferred for managed IdPs)
- AUTH_JWT_SECRET     : HS256 shared secret (e.g., Supabase JWT secret) [fallback]
- AUTH_AUDIENCE       : expected audience (optional but recommended)
- AUTH_ISSUER         : expected issuer (optional but recommended)
- AUTH_LEEWAY_SEC     : clock skew allowance (default: 60)
- AUTH_REQUIRE_TENANT : '1' to require tenant_id claim (default: '1')
"""

from __future__ import annotations

import os

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from fastapi import Header, HTTPException, Query, status

# Import metrics for monitoring
try:
    from .metrics import streaming_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

try:
    import jwt  # PyJWT

    from jwt import PyJWKClient
except Exception as e:  # pragma: no cover
    raise RuntimeError("PyJWT is required: pip install PyJWT[crypto]") from e


@dataclass
class AuthContext:
    """Authentication context with tenant information."""

    raw: dict[str, Any]
    sub: str | None
    tenant_id: str | None
    role: str | None
    scopes: str | None

    def require_tenant(self) -> str:
        """Require tenant_id to be present, raise 403 if missing."""
        if not self.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="tenant_required"
            )
        return self.tenant_id


class AuthError(Exception):
    """Authentication/authorization error."""

    pass


class JWTVerifier:
    """JWT verification with browser-compatible query parameter support."""

    def __init__(
        self,
        *,
        jwks_url: str | None,
        hs_secret: str | None,
        audience: str | None,
        issuer: str | None,
        leeway: int,
        require_tenant: bool,
    ) -> None:
        # CRITICAL FIX: Fail fast if both auth modes configured (PM requirement)
        if jwks_url and hs_secret:
            raise AuthError("Configure AUTH_JWKS_URL OR AUTH_JWT_SECRET, not both")

        if not jwks_url and not hs_secret:
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "production":
                raise AuthError(
                    "PRODUCTION ERROR: Authentication is required. Set AUTH_JWKS_URL or AUTH_JWT_SECRET. "
                    "For managed identity providers, use AUTH_JWKS_URL. For shared secret auth, use AUTH_JWT_SECRET."
                )
            elif env in ("staging", "test"):
                raise AuthError(
                    f"{env.upper()} ERROR: Authentication configuration required. "
                    "Set AUTH_JWKS_URL or AUTH_JWT_SECRET environment variable."
                )
            else:  # development
                import logging

                logger = logging.getLogger(__name__)
                logger.error("=" * 60)
                logger.error("🚨 DEVELOPMENT MODE: NO AUTHENTICATION CONFIGURED")
                logger.error("=" * 60)
                logger.error("This is INSECURE and only allowed in development!")
                logger.error("Set AUTH_JWT_SECRET or AUTH_JWKS_URL before production.")
                logger.error("Example: export AUTH_JWT_SECRET='your-secret-here'")
                logger.error("=" * 60)
                hs_secret = "dev-insecure-fallback-secret-do-not-use-in-production"

        self.jwks_url = jwks_url
        self.hs_secret = hs_secret  # May be set to dev default above
        self.audience = audience
        self.issuer = issuer
        self.leeway = leeway
        self.require_tenant = require_tenant

        # SECURITY: Validate JWT secret strength for production
        self._validate_secret_strength()

    def _validate_secret_strength(self) -> None:
        """Validate JWT secret meets security requirements."""
        if not self.hs_secret:
            return  # JWKS mode, no secret to validate

        env = os.getenv("ENVIRONMENT", "development").lower()
        secret = self.hs_secret

        # Check for insecure development defaults
        insecure_patterns = [
            "dev",
            "test",
            "example",
            "secret",
            "default",
            "insecure",
            "fallback",
            "demo",
            "local",
        ]

        if env == "production":
            # Production security requirements
            if len(secret) < 32:
                raise AuthError(
                    "PRODUCTION SECURITY ERROR: JWT secret must be at least 32 characters. "
                    "Use a cryptographically secure random string."
                )

            if any(pattern in secret.lower() for pattern in insecure_patterns):
                raise AuthError(
                    "PRODUCTION SECURITY ERROR: JWT secret contains insecure patterns. "
                    "Use a secure random string without common words."
                )

            if secret.isalnum() or secret.isalpha() or secret.isdigit():
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    "SECURITY WARNING: JWT secret should contain mixed characters, "
                    "numbers, and symbols for maximum security."
                )

        elif env in ("staging", "test"):
            # Staging/test minimum requirements
            if len(secret) < 16:
                raise AuthError(
                    f"{env.upper()} SECURITY ERROR: JWT secret must be at least 16 characters."
                )

    def verify(self, token: str) -> AuthContext:
        """Verify JWT token and extract claims."""
        try:
            if self.jwks_url:
                key = _get_signing_key(self.jwks_url, token)
                claims = jwt.decode(
                    token,
                    key=key,
                    algorithms=["RS256", "ES256"],
                    audience=self.audience,
                    issuer=self.issuer,
                    options={"require": ["exp", "iat"]},
                    leeway=self.leeway,
                )
            else:
                claims = jwt.decode(
                    token,
                    key=self.hs_secret,
                    algorithms=["HS256"],
                    audience=self.audience,
                    issuer=self.issuer,
                    options={"require": ["exp", "iat"]},
                    leeway=self.leeway,
                )
        except Exception as e:
            # Audit failed token validation (PM5.txt requirement)
            try:
                from .token_auditing import audit_invalid_token
                audit_invalid_token(
                    token_payload={"sub": "unknown", "jti": "unknown"},
                    error=str(e)
                )
            except:
                pass  # Don't fail auth on audit failure
            
            raise AuthError(f"invalid_token: {e}") from e

        # Extract tenant_id from multiple possible claim locations
        tenant_id = (
            claims.get("tenant_id")
            or (claims.get("user_metadata") or {}).get("tenant_id")
            or (claims.get("app_metadata") or {}).get("tenant_id")
        )

        # ENHANCED: Fallback tenant mapping for cases where JWT doesn't contain tenant_id
        if self.require_tenant and not tenant_id:
            # Could add database lookup here: tenant_id = await get_tenant_by_sub(claims.get("sub"))
            raise AuthError("tenant_id_claim_missing")

        ctx = AuthContext(
            raw=claims,
            sub=claims.get("sub"),
            tenant_id=tenant_id,
            role=claims.get("role") or (claims.get("app_metadata") or {}).get("role"),
            scopes=claims.get("scope"),
        )
        
        # Audit successful token validation (PM5.txt requirement)
        try:
            from .token_auditing import audit_token_validated
            audit_token_validated(token_payload=claims)
        except:
            pass  # Don't fail auth on audit failure
        
        return ctx


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    """Cached JWKS client."""
    return PyJWKClient(jwks_url)


def _get_signing_key(jwks_url: str, token: str):
    """Get signing key from JWKS."""
    client = _jwks_client(jwks_url)
    signing_key = client.get_signing_key_from_jwt(token)
    return signing_key.key


def _from_env() -> JWTVerifier:
    """Create JWTVerifier from environment variables."""
    jwks_url = os.getenv("AUTH_JWKS_URL") or None
    hs_secret = os.getenv("AUTH_JWT_SECRET") or None
    audience = os.getenv("AUTH_AUDIENCE") or None
    issuer = os.getenv("AUTH_ISSUER") or None
    leeway = int(os.getenv("AUTH_LEEWAY_SEC", "60"))
    require_tenant = os.getenv("AUTH_REQUIRE_TENANT", "1") == "1"
    return JWTVerifier(
        jwks_url=jwks_url,
        hs_secret=hs_secret,
        audience=audience,
        issuer=issuer,
        leeway=leeway,
        require_tenant=require_tenant,
    )


_verifier = _from_env()


def _parse_bearer(header_val: str | None) -> str:
    """Parse Bearer token from Authorization header."""
    if not header_val:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_authorization_header",
        )
    parts = header_val.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_authorization_header",
        )
    return parts[1]


# -------------------- FastAPI Dependencies --------------------


async def require_jwt(authorization: str | None = Header(default=None)) -> AuthContext:
    """Require JWT authentication via Authorization header."""
    token = _parse_bearer(authorization)
    try:
        return _verifier.verify(token)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


async def require_jwt_query(token: str | None = Query(default=None)) -> AuthContext:
    """
    Require JWT authentication via query parameter (browser-compatible).

    CRITICAL: EventSource and WebSocket APIs cannot send Authorization headers
    in browsers, so we must use query parameters for authentication.

    Usage:
    - SSE: /stream/topic?token=jwt_token_here
    - WebSocket: /ws?token=jwt_token_here
    """
    if not token:
        if METRICS_AVAILABLE:
            streaming_metrics.record_auth_failure("missing_token", "query_param")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token_parameter"
        )

    try:
        auth_context = _verifier.verify(token)
        if METRICS_AVAILABLE:
            streaming_metrics.record_auth_success(
                auth_context.tenant_id or "unknown", "query_param"
            )
        return auth_context
    except AuthError as e:
        if METRICS_AVAILABLE:
            streaming_metrics.record_auth_failure("invalid_token", "query_param")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


async def optional_jwt(
    authorization: str | None = Header(default=None),
) -> AuthContext | None:
    """Optional JWT authentication via Authorization header."""
    if not authorization:
        return None
    token = _parse_bearer(authorization)
    try:
        return _verifier.verify(token)
    except AuthError:
        # For optional paths, return None on verify failures
        return None


async def optional_jwt_query(
    token: str | None = Query(default=None),
) -> AuthContext | None:
    """Optional JWT authentication via query parameter."""
    if not token:
        return None
    try:
        return _verifier.verify(token)
    except AuthError:
        return None


# -------------------- Utility Functions --------------------


def validate_jwt_token(token: str) -> AuthContext:
    """Validate JWT token directly (for use in WebSocket handling)."""
    try:
        return _verifier.verify(token)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def create_jwt_token(
    tenant_id: str,
    user_id: str = "test-user",
    role: str = "user",
    ttl_seconds: int = 3600,
) -> str:
    """Create a JWT token for testing purposes (development only)."""
    if not _verifier.hs_secret:
        raise AuthError("HS256 secret required for token creation")

    import time

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time() + ttl_seconds),
    }
    return jwt.encode(payload, _verifier.hs_secret, algorithm="HS256")
