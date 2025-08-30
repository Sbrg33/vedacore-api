#!/usr/bin/env python3
"""
Application configuration
"""

import os

from pathlib import Path
from zoneinfo import ZoneInfo

# Timezone definitions
NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

# Cache configuration - configurable root
DATA_ROOT = Path(
    os.getenv("VEDACORE_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)
CACHE_DIR = DATA_ROOT / "cache" / "KP"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Session bounds in NY time (hour, minute, hour, minute)
SESSION_BOUNDS: dict[str, tuple[int, int, int, int]] = {
    "PRE_MARKET": (4, 0, 9, 30),
    "REGULAR": (9, 30, 16, 0),
    "AFTER_HOURS": (16, 0, 20, 0),
}

# System namespace for future extensibility
SYSTEM_NAMESPACE = "KP"  # Will allow "Chinese", "Chaldean" etc. later

# Finance settings
FINANCE_OFFSET_SECONDS = 307  # KP-specific offset (applied in facade)

# API settings
MAX_DAYS_PER_REQUEST = 7
MAX_INTERVALS_PER_DAY = 43200  # 1 day at 2-second intervals

# Performance settings
ENABLE_CACHE = True
CACHE_TTL_HOURS = 24
WARMUP_ON_STARTUP = True

# Feature flags (can be overridden by environment)
FEATURE_FLAGS = {
    "numba_jit": True,
    "boundary_snapping": False,
    "deterministic_mode": False,
    "metrics_enabled": True,
    "cache_enabled": True,
}
