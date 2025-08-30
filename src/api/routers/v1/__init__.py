"""
VedaCore API v1 Router Package

This package contains all versioned v1 routers following PM guidance:
- All public routes under /api/v1/
- Uniform error schema and response models
- Vedic/KP-first approach with enforced defaults
- Path templates for usage metering
"""

from .jyotish import router as jyotish_router
from .kp import router as kp_router
from .ref import router as ref_router
from .atlas import router as atlas_router
from .auth import router as auth_router
from .stream import router as stream_router

__all__ = [
    "jyotish_router",
    "kp_router", 
    "ref_router",
    "atlas_router",
    "auth_router",
    "stream_router",
]