#!/usr/bin/env python3
"""
Time interval utilities for slicing intraday data
"""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Literal

IntervalType = Literal["2s", "5s", "15s", "30s", "1m", "5m", "15m", "30m", "1h"]

# Interval definitions in seconds
INTERVALS_SECONDS: dict[str, int] = {
    "2s": 2,
    "5s": 5,
    "15s": 15,
    "30s": 30,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


def iter_slices(
    start: datetime, end: datetime, interval_key: IntervalType
) -> Iterator[tuple[datetime, datetime]]:
    """Generate time slices for a given interval

    Args:
        start: Start time
        end: End time
        interval_key: Interval size

    Yields:
        (slice_start, slice_end) tuples
    """
    if interval_key not in INTERVALS_SECONDS:
        raise ValueError(f"Invalid interval: {interval_key}")

    step_seconds = INTERVALS_SECONDS[interval_key]
    current = start

    while current < end:
        next_time = current + timedelta(seconds=step_seconds)
        yield current, min(next_time, end)
        current = next_time


def count_slices(start: datetime, end: datetime, interval_key: IntervalType) -> int:
    """Count number of slices in a time range

    Args:
        start: Start time
        end: End time
        interval_key: Interval size

    Returns:
        Number of slices
    """
    if interval_key not in INTERVALS_SECONDS:
        raise ValueError(f"Invalid interval: {interval_key}")

    duration_seconds = (end - start).total_seconds()
    step_seconds = INTERVALS_SECONDS[interval_key]

    return int(duration_seconds / step_seconds) + (
        1 if duration_seconds % step_seconds > 0 else 0
    )


def align_to_interval(ts: datetime, interval_key: IntervalType) -> datetime:
    """Align timestamp to interval boundary

    Args:
        ts: Timestamp to align
        interval_key: Interval size

    Returns:
        Aligned timestamp (rounded down to interval)
    """
    if interval_key not in INTERVALS_SECONDS:
        raise ValueError(f"Invalid interval: {interval_key}")

    step_seconds = INTERVALS_SECONDS[interval_key]

    # Get seconds since midnight
    midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_since_midnight = (ts - midnight).total_seconds()

    # Align to interval
    aligned_seconds = (seconds_since_midnight // step_seconds) * step_seconds

    return midnight + timedelta(seconds=aligned_seconds)
