#!/usr/bin/env python3
"""
Trading session detection based on NY time
"""

from datetime import datetime, time
from typing import Literal

from app.services.unified_cache import get_unified_cache

from .config import NY_TZ, SESSION_BOUNDS

# Global cache service instance - PM requirement: environment-driven cache selection
cache_service = get_unified_cache("SESSION")

SessionType = Literal["PRE_MARKET", "REGULAR", "AFTER_HOURS", "OFF_HOURS"]


def in_session(ts_local: datetime) -> SessionType:
    """Determine which trading session a timestamp falls into

    Args:
        ts_local: Timezone-aware datetime (should be NY time)

    Returns:
        Session type string
    """
    assert ts_local.tzinfo is not None, "Timestamp must be timezone-aware"

    # Convert to NY time if needed
    if ts_local.tzinfo != NY_TZ:
        ts_local = ts_local.astimezone(NY_TZ)

    h, m = ts_local.hour, ts_local.minute
    current_time = time(h, m)

    def within(bounds: tuple) -> bool:
        h1, m1, h2, m2 = bounds
        start_time = time(h1, m1)
        end_time = time(h2, m2)
        return start_time <= current_time < end_time

    if within(SESSION_BOUNDS["PRE_MARKET"]):
        return "PRE_MARKET"
    if within(SESSION_BOUNDS["REGULAR"]):
        return "REGULAR"
    if within(SESSION_BOUNDS["AFTER_HOURS"]):
        return "AFTER_HOURS"

    return "OFF_HOURS"


def is_market_open(ts_local: datetime) -> bool:
    """Check if market is open (any session except OFF_HOURS)

    Args:
        ts_local: Timezone-aware datetime

    Returns:
        True if market is open
    """
    return in_session(ts_local) != "OFF_HOURS"


def get_session_bounds(
    session: SessionType, date: datetime
) -> tuple[datetime, datetime]:
    """Get start and end times for a session on a given date

    Args:
        session: Session type
        date: Date (NY timezone)

    Returns:
        (start, end) datetimes in NY timezone
    """
    if session == "OFF_HOURS":
        # OFF_HOURS spans from end of AFTER_HOURS to start of PRE_MARKET
        h1, m1, _, _ = SESSION_BOUNDS["PRE_MARKET"]
        _, _, h2, m2 = SESSION_BOUNDS["AFTER_HOURS"]
        start = date.replace(hour=h2, minute=m2, second=0, microsecond=0)
        # Next day's pre-market start
        from datetime import timedelta

        end = (date + timedelta(days=1)).replace(
            hour=h1, minute=m1, second=0, microsecond=0
        )
    else:
        h1, m1, h2, m2 = SESSION_BOUNDS[session]
        start = date.replace(hour=h1, minute=m1, second=0, microsecond=0)
        end = date.replace(hour=h2, minute=m2, second=0, microsecond=0)

    return start, end
