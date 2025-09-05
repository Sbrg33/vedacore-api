"""
Usage Metering Middleware

Implements PM requirement for usage tracking with Postgres backend.
Emits usage events for billing/quotas with tenant tracking.
"""

import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional, Dict, Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import jwt

from app.core.logging import get_api_logger
from app.core.environment import get_complete_config
from api.routers.v1.models import PATH_TEMPLATES
from api.services.rate_limiter import (
    DEFAULT_QPS_LIMIT,
    DEFAULT_BURST_LIMIT,
)

logger = get_api_logger("usage_metering")

# Default header values are aligned with centralized rate limiter defaults
# (imported above). We no longer keep a separate constant with stale
# placeholders to avoid drift.


class UsageMeteringMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware to track API usage for billing and quotas.
    
    Implements PM requirements:
    - Emit usage_event per request (after response)
    - Track tenant_id, api_key_id, path_template
    - Record status_code, duration_ms, bytes_in/out
    - Never block response on metering failure (best-effort)
    - Add rate-limit headers to all responses
    """
    
    def __init__(self, app: ASGIApp, enable_metering: bool = True):
        super().__init__(app)
        self.enable_metering = enable_metering
        self.config = get_complete_config()
        
        # Initialize database connection pool (would be async pool in real implementation)
        self._init_db_connection()
    
    def _init_db_connection(self):
        """Initialize database connection for usage tracking."""
        # In a real implementation, this would set up an async connection pool
        # For now, we'll simulate the structure
        logger.info("📊 Usage metering initialized (database connection ready)")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with usage metering."""
        
        if not self.enable_metering:
            return await call_next(request)
        
        # Start timing (monotonic to avoid clock regressions)
        start_time = time.perf_counter()
        request_start = datetime.now(timezone.utc)
        
        # Extract tenant info from token (if present)
        tenant_info = self._extract_tenant_info(request)
        
        # Get request size
        bytes_in = self._get_request_size(request)
        
        # Execute request
        try:
            response = await call_next(request)
            
            # Calculate metrics
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            bytes_out = self._get_response_size(response)
            
            # Add rate limit headers (PM requirement)
            response = await self._add_rate_limit_headers(response, tenant_info)
            
            # Emit usage event (async, non-blocking)
            await self._emit_usage_event(
                request=request,
                response=response,
                tenant_info=tenant_info,
                timestamp=request_start,
                duration_ms=duration_ms,
                bytes_in=bytes_in,
                bytes_out=bytes_out
            )
            
            return response
            
        except Exception as e:
            # Still emit usage event for failed requests
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            try:
                await self._emit_usage_event(
                    request=request,
                    response=None,
                    tenant_info=tenant_info,
                    timestamp=request_start,
                    duration_ms=duration_ms,
                    bytes_in=bytes_in,
                    bytes_out=0,
                    status_code=500
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit usage event for failed request: {emit_error}")
            
            raise
    
    def _extract_tenant_info(self, request: Request) -> Dict[str, str]:
        """Extract tenant and API key info from request."""
        tenant_info = {
            "tenant_id": "unknown",
            "api_key_id": "unknown",
        }
        
        try:
            # Check Authorization header
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove "Bearer "
            else:
                # Check query parameter (for SSE/WebSocket)
                token = request.query_params.get("token")
            
            if token:
                # Decode JWT to extract tenant info
                payload = jwt.decode(
                    token, 
                    self.config.database.auth_secret, 
                    algorithms=["HS256"],
                    options={"verify_exp": False}  # Don't verify expiry for metering
                )
                
                tenant_info["tenant_id"] = payload.get("tid", "unknown")
                tenant_info["api_key_id"] = payload.get("sub", "unknown")
                
        except Exception as e:
            # Don't log token decode failures (they're expected for public endpoints)
            pass
        
        return tenant_info
    
    def _get_request_size(self, request: Request) -> int:
        """Estimate request size in bytes."""
        try:
            # Headers size (approximate)
            headers_size = sum(len(k) + len(v) for k, v in request.headers.items())
            
            # URL size
            url_size = len(str(request.url))
            
            # Content length (if available)
            content_length = request.headers.get("content-length", "0")
            body_size = int(content_length) if content_length.isdigit() else 0
            
            return headers_size + url_size + body_size
            
        except Exception:
            return 0
    
    def _get_response_size(self, response: Response) -> int:
        """Estimate response size in bytes."""
        try:
            # Content length from headers
            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit():
                return int(content_length)
            
            # Estimate from body if available
            if hasattr(response, 'body') and response.body:
                return len(response.body)
            
            return 0
            
        except Exception:
            return 0
    
    async def _add_rate_limit_headers(
        self, 
        response: Response, 
        tenant_info: Dict[str, str]
    ) -> Response:
        """Add rate limit headers to response (PM requirement)."""
        # Reflect current per-tenant QPS limits via the in-process rate limiter
        remaining = None
        limit = None
        try:
            from api.services.rate_limiter import rate_limiter
            tenant_id = tenant_info.get("tenant_id") or "unknown"
            # Snapshot without creating new entries; synchronized under tenant lock
            limit_val, remaining_val = await rate_limiter.snapshot_limits(tenant_id)
            if limit_val is not None:
                limit = limit_val
            if remaining_val is not None:
                remaining = int(max(0, remaining_val))
        except Exception:
            # Fallback: leave as None; we'll populate with defaults below
            pass

        # Calculate reset time (next hour)
        now = datetime.now(timezone.utc)
        # Handle hour rollover safely by adding an hour then zeroing minutes/seconds
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        reset_time = int(next_hour.timestamp())
        
        # Add headers (fallbacks align with configured defaults)
        # - Limit falls back to DEFAULT_QPS_LIMIT
        # - Remaining falls back to DEFAULT_BURST_LIMIT (full bucket)
        response.headers["X-RateLimit-Limit"] = str(limit if limit is not None else DEFAULT_QPS_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(
            remaining if remaining is not None else DEFAULT_BURST_LIMIT
        )
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        # Optional: expose the window length in seconds (hourly window)
        response.headers["X-RateLimit-Window"] = "3600"
        
        return response
    
    def _get_path_template(self, request: Request) -> str:
        """Get path template for metering (PM requirement - use templates, not raw paths)."""
        path = request.url.path
        
        # Map actual paths to templates
        for template_key, template_path in PATH_TEMPLATES.items():
            # Simple matching - in production would use more sophisticated routing
            if template_path.replace("{type}", "").replace("{query}", "") in path:
                return template_path
        
        # Fallback to actual path for unmapped routes
        return path
    
    def _calculate_compute_units(
        self, 
        request: Request, 
        duration_ms: int, 
        status_code: int
    ) -> float:
        """Calculate compute units for request (PM requirement)."""
        path = request.url.path
        
        # Base compute unit
        base_units = 1.0
        
        # Adjust based on endpoint complexity
        if "/kp/chain" in path or "/kp/horary" in path:
            base_units = 1.5  # KP calculations are more complex
        elif "/jyotish/transits/window" in path:
            base_units = 2.0  # Transit analysis is expensive
        elif "/stream" in path or "/ws" in path:
            base_units = 0.1  # Streaming connections are lightweight
        elif status_code >= 400:
            base_units = 0.1  # Error responses are cheap
        
        # Adjust for duration (long requests cost more)
        # Check higher threshold first to ensure it is not shadowed by lower one.
        if duration_ms > 5000:  # > 5 seconds
            base_units *= 2.0
        elif duration_ms > 1000:  # > 1 second
            base_units *= 1.5
        
        return base_units
    
    async def _emit_usage_event(
        self,
        request: Request,
        response: Optional[Response],
        tenant_info: Dict[str, str],
        timestamp: datetime,
        duration_ms: int,
        bytes_in: int,
        bytes_out: int,
        status_code: Optional[int] = None
    ):
        """Emit usage event to database (PM requirement - async, non-blocking)."""
        
        try:
            # Build usage event
            event = {
                "ts": timestamp.isoformat(),
                "tenant_id": tenant_info["tenant_id"],
                "api_key_id": tenant_info["api_key_id"],
                "path_template": self._get_path_template(request),
                "method": request.method,
                "status_code": status_code or (response.status_code if response else 500),
                "duration_ms": duration_ms,
                "bytes_in": bytes_in,
                "bytes_out": bytes_out,
                "region": "local",  # Would be detected from deployment
                "cache": "miss",    # Would be determined from response
                "compute_units": self._calculate_compute_units(request, duration_ms, status_code or 500)
            }
            
            # In a real implementation, this would be an async database insert
            # For now, just log the event structure
            logger.info(
                "📊 Usage event",
                extra={
                    "event_type": "usage",
                    "tenant_id": event["tenant_id"],
                    "path_template": event["path_template"],
                    "duration_ms": event["duration_ms"],
                    "compute_units": event["compute_units"],
                    **event
                }
            )
            
            # Persist usage event (best-effort; non-blocking on failure)
            await self._insert_usage_event(event)
            
        except Exception as e:
            # PM requirement: never block response on metering failure
            logger.warning(f"Failed to emit usage event: {e}")
    
    async def _insert_usage_event(self, event: Dict[str, Any]):
        """Insert usage event into database using the project's async DB client.

        Best-effort: any failure is logged and swallowed per PM requirement.
        """
        try:
            from datetime import datetime
            from app.services.supabase_signals import get_supabase_signals_service

            svc = await get_supabase_signals_service()
            if not getattr(svc, "enabled", False) or not getattr(svc, "pool", None):
                # DB not configured; skip persist silently
                return

            # Convert values to types expected by asyncpg
            ts = event.get("ts")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = datetime.now(timezone.utc)

            values = (
                ts,
                event.get("tenant_id"),
                event.get("api_key_id"),
                event.get("path_template"),
                event.get("method"),
                int(event.get("status_code", 200)),
                int(event.get("duration_ms", 0)),
                int(event.get("bytes_in", 0)),
                int(event.get("bytes_out", 0)),
                event.get("region"),
                event.get("cache"),
                float(event.get("compute_units", 1.0)),
            )

            SQL = (
                "INSERT INTO usage_events ("
                "ts, tenant_id, api_key_id, path_template, method, "
                "status_code, duration_ms, bytes_in, bytes_out, "
                "region, cache, compute_units) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)"
            )

            async with svc.get_connection() as conn:
                await conn.execute(SQL, *values)

        except Exception as e:
            logger.warning(f"Usage event persist failed: {e}")


def create_usage_tables_sql() -> str:
    """Generate SQL to create usage tracking tables (PM requirement)."""
    return """
-- Usage events table (PM specification)
CREATE TABLE IF NOT EXISTS usage_events(
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    tenant_id TEXT NOT NULL,
    api_key_id TEXT NOT NULL,
    path_template TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INT NOT NULL,
    duration_ms INT NOT NULL,
    bytes_in INT NOT NULL,
    bytes_out INT NOT NULL,
    region TEXT,
    cache TEXT,
    compute_units NUMERIC(10,2) NOT NULL DEFAULT 1.0
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON usage_events(ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_tenant_ts ON usage_events(tenant_id, ts);
CREATE INDEX IF NOT EXISTS idx_usage_events_template ON usage_events(path_template);

-- Daily rollup view (PM specification)
CREATE MATERIALIZED VIEW IF NOT EXISTS usage_daily AS
SELECT 
    tenant_id, 
    DATE_TRUNC('day', ts) as day,
    COUNT(*) as requests,
    SUM(bytes_out) as egress_bytes,
    SUM(compute_units) as compute_units,
    AVG(duration_ms) as avg_duration_ms,
    COUNT(CASE WHEN status_code >= 400 THEN 1 END) as error_count
FROM usage_events 
GROUP BY tenant_id, DATE_TRUNC('day', ts)
ORDER BY day DESC;

-- Refresh function for daily rollups
CREATE OR REPLACE FUNCTION refresh_usage_daily()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW usage_daily;
END;
$$ LANGUAGE plpgsql;
"""
