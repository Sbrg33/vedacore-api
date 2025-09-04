"""
Ephemeris Headers Middleware

Adds PM-required ephemeris build information to all responses.
Ensures numerical reproducibility and version tracking.
"""

import hashlib
import os
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_api_logger

logger = get_api_logger("ephemeris_headers")


class EphemerisHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add ephemeris build information to all API responses.
    
    PM Requirements:
    - X-Ephemeris-Build: Swiss Ephemeris build hash
    - X-Ayanamsha: Active ayanamsha system  
    - X-Node-Mode: Node calculation mode
    
    Ensures clients can verify numerical consistency.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.ephemeris_build = self._get_ephemeris_build_hash()
        self.headers = self._build_static_headers()
        
        logger.info(f"🔢 Ephemeris headers initialized: {self.headers}")
    
    def _get_ephemeris_build_hash(self) -> str:
        """Get Swiss Ephemeris build hash for reproducibility."""
        try:
            # Try to get actual Swiss Ephemeris version
            import swisseph as swe
            version = swe.version()
            
            # Create hash from version + system info for reproducibility
            system_info = f"{version}|{os.name}|{os.uname().machine if hasattr(os, 'uname') else 'unknown'}"
            build_hash = hashlib.md5(system_info.encode()).hexdigest()[:8]
            
            return f"swe-{build_hash}"
            
        except ImportError:
            # Fallback if Swiss Ephemeris not available
            logger.warning("Swiss Ephemeris not available, using fallback build hash")
            return "swe-fallback"
        except Exception as e:
            logger.warning(f"Failed to get ephemeris version: {e}")
            return "swe-unknown"
    
    def _build_static_headers(self) -> dict[str, str]:
        """Build static headers that are the same for all responses."""
        algo_version = os.getenv("ALGO_VERSION", "1.0.0")
        return {
            "X-Ephemeris-Build": self.ephemeris_build,
            "X-Ayanamsha": "kp",  # Default ayanamsha (may be overridden per request)
            "X-Node-Mode": "true_node",  # Default node mode  
            "X-Zodiac": "sidereal",  # Enforced zodiac system
            "X-House-System": "placidus",  # Default house system
            "X-Algorithm-Version": algo_version,
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add ephemeris headers to response."""
        
        # Process request
        response = await call_next(request)
        
        # Add static ephemeris headers
        for header, value in self.headers.items():
            response.headers[header] = value
        
        # Add dynamic headers based on request
        self._add_dynamic_headers(request, response)

        return response
    
    def _add_dynamic_headers(self, request: Request, response: Response):
        """Add headers that may vary based on request parameters."""
        
        # Override ayanamsha if specified in request
        if hasattr(request.state, 'ayanamsha'):
            response.headers["X-Ayanamsha"] = request.state.ayanamsha
        
        # Override node mode if specified  
        if hasattr(request.state, 'node_mode'):
            response.headers["X-Node-Mode"] = request.state.node_mode
            
        # Add computation metadata
        if hasattr(request.state, 'compute_time_ms'):
            response.headers["X-Compute-Time-Ms"] = str(request.state.compute_time_ms)
            
        if hasattr(request.state, 'cache_status'):
            response.headers["X-Cache-Status"] = request.state.cache_status
            try:
                # boolean-friendly indicator
                response.headers["computed_from_cache"] = (
                    "true" if str(request.state.cache_status).upper() == "HIT" else "false"
                )
            except Exception:
                response.headers["computed_from_cache"] = "false"


def get_ephemeris_info() -> dict[str, str]:
    """Get current ephemeris configuration info."""
    middleware = EphemerisHeadersMiddleware(None)  # Just for header generation
    return middleware.headers


def verify_ephemeris_consistency() -> bool:
    """Verify ephemeris build consistency across requests."""
    try:
        import swisseph as swe
        
        # Test key calculations for consistency
        test_jd = 2451545.0  # J2000.0 epoch
        
        # Get Sun position at J2000
        sun_pos = swe.calc_ut(test_jd, swe.SUN)[0][0]  # Longitude
        
        # Expected value (approximately 280.46 degrees at J2000)
        expected = 280.46
        tolerance = 0.1
        
        is_consistent = abs(sun_pos - expected) < tolerance
        
        if is_consistent:
            logger.info(f"✅ Ephemeris consistency verified: Sun@J2000 = {sun_pos:.6f}°")
        else:
            logger.error(f"❌ Ephemeris inconsistency: Sun@J2000 = {sun_pos:.6f}°, expected ~{expected}°")
        
        return is_consistent
        
    except Exception as e:
        logger.error(f"Failed to verify ephemeris consistency: {e}")
        return False


# Ayanamsha table information for reproducibility
AYANAMSHA_INFO = {
    "kp": {
        "name": "KP Ayanamsha",
        "epoch": "1900.0",
        "rate": "50.25 arcsec/year",
        "description": "Krishnamurti Paddhati ayanamsha"
    },
    "lahiri": {
        "name": "Lahiri Ayanamsha", 
        "epoch": "1900.0",
        "rate": "50.26 arcsec/year",
        "description": "Chitrapaksha ayanamsha (Government of India)"
    }
}


def get_ayanamsha_info(ayanamsha: str = "kp") -> dict[str, str]:
    """Get ayanamsha calculation parameters."""
    return AYANAMSHA_INFO.get(ayanamsha, AYANAMSHA_INFO["kp"])


if __name__ == "__main__":
    # Test ephemeris consistency
    print("🔢 Testing ephemeris consistency...")
    
    info = get_ephemeris_info()
    print(f"Build info: {info}")
    
    consistent = verify_ephemeris_consistency()
    print(f"Consistency check: {'✅ PASS' if consistent else '❌ FAIL'}")
    
    for name, details in AYANAMSHA_INFO.items():
        print(f"{name}: {details['description']}")
