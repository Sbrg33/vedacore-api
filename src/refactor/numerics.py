#!/usr/bin/env python3
"""
Numerical helpers used across refactor modules.

Implements local versions to avoid cross-repo imports.
"""

from __future__ import annotations

from math import floor


def normalize_angle(deg: float) -> float:
    """Normalize an angle in degrees to [0, 360).

    Handles negative inputs robustly.
    """
    if deg is None:
        return 0.0
    x = float(deg) % 360.0
    return x + 360.0 if x < 0.0 else x


def clamp_value(v: float, lo: float, hi: float) -> float:
    """Clamp a value into [lo, hi]."""
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def degrees_to_dms(deg: float) -> str:
    """Format degrees into D°M'S" string with one decimal on seconds.

    Example: 123.4567 -> "123°27'24.1".
    """
    d = normalize_angle(deg)
    whole_deg = int(floor(d))
    minutes_full = (d - whole_deg) * 60.0
    whole_min = int(floor(minutes_full))
    seconds = (minutes_full - whole_min) * 60.0
    return f"{whole_deg}°{whole_min:02d}'{seconds:04.1f}"
