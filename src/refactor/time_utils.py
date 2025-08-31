#!/usr/bin/env python3
"""
Time utilities for ephemeris calculations.

Provides UTC validation, Julian day conversions, and timezone helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

try:
    import swisseph as swe
except Exception:  # pragma: no cover - fallback for type checking
    swe = None  # type: ignore


def ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware and in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_utc_datetime(dt: datetime) -> datetime:
    """Alias for ensure_utc; kept for API compatibility."""
    return ensure_utc(dt)


def datetime_to_julian_day(dt: datetime) -> float:
    """Convert aware datetime to Julian Day (UT)."""
    dt = ensure_utc(dt)
    if swe is None:
        # Minimal astronomical JD conversion if swisseph is unavailable
        # Algorithm from Jean Meeus (approximate), but here we assume swe is present.
        # Fallback to Unix epoch approximation
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return 2440587.5 + (dt - epoch).total_seconds() / 86400.0
    y, m, d = dt.year, dt.month, dt.day
    h = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3_600_000_000.0
    return swe.julday(y, m, d, h)


def julian_day_to_datetime(jd: float) -> datetime:
    """Convert Julian Day to aware UTC datetime."""
    if swe is None:
        # Reverse of the Unix epoch approximation
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return epoch + timedelta(days=(jd - 2440587.5))
    y, m, d, h = swe.revjul(jd, swe.GREG_CAL)
    hours = int(h)
    minutes = int((h - hours) * 60)
    seconds = int(round((((h - hours) * 60) - minutes) * 60))
    return datetime(y, m, d, hours, minutes, seconds, tzinfo=timezone.utc)


def to_ny(dt: datetime) -> datetime:
    """Convert a datetime to America/New_York timezone."""
    return ensure_utc(dt).astimezone(ZoneInfo("America/New_York"))
