"""
Deprecation Headers Middleware

Implements PM Final requirement: add deprecation headers to legacy routes.
Provides RFC 8594 compliant deprecation notices with sunset dates.

Features:
- Warning headers per RFC 7234
- Sunset headers per RFC 8594  
- Link headers for migration guidance
- Configurable deprecation timeline
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from urllib.parse import urlparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_api_logger

logger = get_api_logger("deprecation_headers")


class DeprecationHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add deprecation headers to legacy API endpoints."""
    
    def __init__(self, app):
        super().__init__(app)
        
        # PM Final: Sunset date October 27, 2025
        self.sunset_date = os.getenv("LEGACY_SUNSET_DATE", "2025-10-27T00:00:00Z")
        self.migration_guide_url = os.getenv("MIGRATION_GUIDE_URL", "https://docs.vedacore.com/migration/v1")
        
        # Legacy endpoints to deprecate
        self.legacy_endpoints = [
            "/api/houses",
            "/api/kp/",
            "/api/dasha", 
            "/api/signals",
            "/legacy/",
            "/houses",
            "/dasha",
            "/nodes",
            "/eclipse",
            "/moon",
            "/micro",
            "/strategy",
            "/advisory",
            "/tara",
            "/fortuna",
            "/transit-events",
            "/ats",
            "/panchanga",
            "/kp-horary",
            "/kp-ruling-planets"
        ]
        
        # Calculate days until sunset for warnings
        try:
            sunset_dt = datetime.fromisoformat(self.sunset_date.replace('Z', '+00:00'))
            self.days_until_sunset = max(0, (sunset_dt - datetime.now(timezone.utc)).days)
        except:
            self.days_until_sunset = 60  # Default fallback
        
        logger.info(f"Deprecation headers middleware initialized")
        logger.info(f"Sunset date: {self.sunset_date} ({self.days_until_sunset} days)")
        logger.info(f"Monitoring {len(self.legacy_endpoints)} legacy endpoint patterns")
    
    async def dispatch(self, request: Request, call_next):
        """Add deprecation headers to legacy endpoint responses."""
        
        response = await call_next(request)
        
        # Check if this is a legacy endpoint
        if self._is_legacy_endpoint(request.url.path):
            self._add_deprecation_headers(response, request.url.path)
        
        return response
    
    def _is_legacy_endpoint(self, path: str) -> bool:
        """Check if the path is a legacy endpoint."""
        # Skip health and metrics endpoints
        if path in ["/health", "/metrics", "/", "/api/docs", "/api/redoc"]:
            return False
        
        # Check if path starts with any legacy pattern
        return any(
            path.startswith(pattern) or path == pattern.rstrip('/')
            for pattern in self.legacy_endpoints
        )
    
    def _add_deprecation_headers(self, response: Response, path: str) -> None:
        """Add deprecation headers to response."""
        
        # RFC 8594 Deprecation header
        response.headers["Deprecation"] = "true"
        
        # RFC 8594 Sunset header (when the API will be removed)
        response.headers["Sunset"] = self._format_sunset_date()
        
        # RFC 7234 Warning header with countdown
        response.headers["Warning"] = self._generate_warning_header()
        
        # Link header for migration guidance (RFC 8288)
        response.headers["Link"] = f'<{self.migration_guide_url}>; rel="sunset"; title="Migration Guide"'
        
        # Custom headers for client guidance
        response.headers["X-API-Deprecation"] = "legacy-endpoint"
        response.headers["X-Migration-Deadline"] = self.sunset_date
        response.headers["X-Replacement-API"] = self._get_v1_equivalent(path)
        
        # Cache control to prevent caching deprecated responses
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        
        # Log deprecation access for monitoring
        logger.warning(
            f"Legacy endpoint accessed: {path}",
            extra={
                "legacy_endpoint": path,
                "days_until_sunset": self.days_until_sunset,
                "client_should_migrate": True
            }
        )
    
    def _format_sunset_date(self) -> str:
        """Format sunset date for HTTP header (RFC 7231)."""
        try:
            sunset_dt = datetime.fromisoformat(self.sunset_date.replace('Z', '+00:00'))
            return sunset_dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
        except:
            return "Sun, 27 Oct 2025 00:00:00 GMT"
    
    def _generate_warning_header(self) -> str:
        """Generate RFC 7234 compliant warning header."""
        if self.days_until_sunset <= 7:
            urgency = "URGENT"
            warn_code = "299"  # Miscellaneous persistent warning
        elif self.days_until_sunset <= 14:
            urgency = "CRITICAL"
            warn_code = "299"
        elif self.days_until_sunset <= 30:
            urgency = "WARNING"
            warn_code = "299"
        else:
            urgency = "NOTICE"
            warn_code = "299"
        
        return f'{warn_code} "vedacore-api" "{urgency}: Legacy routes removed on 2025-10-27 ({self.days_until_sunset} days)"'
    
    def _get_v1_equivalent(self, legacy_path: str) -> str:
        """Get the v1 equivalent path for legacy endpoint."""
        
        # Direct mappings
        mappings = {
            "/api/houses": "/api/v1/jyotish/houses",
            "/api/kp/ruling-planets": "/api/v1/kp/ruling-planets", 
            "/api/dasha": "/api/v1/jyotish/dasha",
            "/api/signals": "/api/v1/kp/signals",
            "/legacy/kp/rp": "/api/v1/kp/ruling-planets",
            "/legacy/houses": "/api/v1/jyotish/houses"
        }
        
        # Check direct mappings first
        if legacy_path in mappings:
            return mappings[legacy_path]
        
        # Pattern-based mappings
        if legacy_path.startswith("/api/kp/"):
            return legacy_path.replace("/api/kp/", "/api/v1/kp/")
        elif legacy_path.startswith("/legacy/"):
            clean_path = legacy_path.replace("/legacy/", "")
            if clean_path.startswith("kp/"):
                return f"/api/v1/kp/{clean_path[3:]}"
            else:
                return f"/api/v1/jyotish/{clean_path}"
        elif legacy_path.startswith("/api/"):
            endpoint_name = legacy_path.replace("/api/", "")
            return f"/api/v1/jyotish/{endpoint_name}"
        else:
            # Fallback mapping for root-level endpoints
            endpoint_name = legacy_path.lstrip("/")
            return f"/api/v1/jyotish/{endpoint_name}"


def install_deprecation_headers_middleware(app, enabled: bool = None):
    """Install deprecation headers middleware."""
    
    # Check if deprecation should be enabled
    if enabled is None:
        # PM Final: Start deprecation warnings on Sep 13 (T+16d)
        enabled = os.getenv("LEGACY_DEPRECATION_ENABLED", "true").lower() == "true"
    
    # Only install if v1 routing is available
    from app.core.environment import get_complete_config
    config = get_complete_config()
    
    if not config.feature_v1_routing:
        logger.info("⏭️  Deprecation headers disabled (FEATURE_V1_ROUTING=false)")
        return False
    
    if not enabled:
        logger.info("⏭️  Deprecation headers disabled")
        return False
    
    # Install middleware
    app.add_middleware(DeprecationHeadersMiddleware)
    
    logger.info("⚠️  Deprecation headers middleware installed")
    logger.info("   Legacy endpoints will include sunset notices")
    
    return True