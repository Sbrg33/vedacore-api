#!/usr/bin/env python3
"""
HFT-Optimized Facade for KP Calculations
Integrates high-performance caching to achieve 100k+ calculations/second
"""

import time

from datetime import UTC, datetime, timedelta


# Import the base calculation function avoiding circular import
def _get_original_positions():
    """Lazy import to avoid circular dependency"""
    from . import facade

    # Save original function before it gets modified
    if not hasattr(_get_original_positions, "_cached"):
        _get_original_positions._cached = (
            facade.get_positions.__wrapped__
            if hasattr(facade.get_positions, "__wrapped__")
            else facade.get_positions
        )
    return _get_original_positions._cached


from .constants import PLANET_NAMES
from .core_types import PlanetData
from .hft_cache import get_cache_monitor, get_hft_cache, warmup_cache
from .kp_chain import kp_chain_for_longitude


def get_positions_hft(
    timestamp_utc: datetime, planet_id: int = 2, apply_kp_offset: bool = True
) -> PlanetData:
    """
    HFT-optimized version of get_positions with 1-second caching.

    This function wraps the original get_positions with intelligent caching
    that's safe for HFT operations. Moon SL2 won't change within 1 second.

    Args:
        timestamp_utc: UTC timestamp
        planet_id: Planet ID (1-9)
        apply_kp_offset: Whether to apply 307-second offset

    Returns:
        PlanetData with position and KP lords
    """
    start_time = time.perf_counter()

    # Get cache instance
    cache = get_hft_cache()
    monitor = get_cache_monitor()

    # Try cache first
    cached_data = cache.get_position(timestamp_utc, planet_id, apply_kp_offset)

    if cached_data is not None:
        # Cache hit!
        duration = time.perf_counter() - start_time
        monitor.record_request(duration, was_cached=True)
        return cached_data

    # Cache miss - calculate using the base function
    # We need to call the non-HFT version directly
    from .facade import get_positions as _get_pos_base

    # Temporarily disable HFT to avoid recursion
    planet_data = _get_pos_base(
        timestamp_utc, planet_id, apply_kp_offset, use_hft_cache=False
    )

    # Store in cache
    cache.set_position(timestamp_utc, planet_id, apply_kp_offset, planet_data)

    duration = time.perf_counter() - start_time
    monitor.record_request(duration, was_cached=False)

    return planet_data


def get_moon_sl2_fast(
    timestamp_utc: datetime, apply_kp_offset: bool = True
) -> tuple[int, float]:
    """
    Ultra-fast Moon SL2 retrieval for HFT.

    Returns:
        Tuple of (sl2_lord_id, moon_position)
    """
    moon = get_positions_hft(
        timestamp_utc, planet_id=2, apply_kp_offset=apply_kp_offset
    )
    return moon.sl2, moon.position


def get_next_sl2_change(
    start_time: datetime, apply_kp_offset: bool = True, max_hours: int = 2
) -> tuple[datetime, int, int] | None:
    """
    Find the next Moon SL2 change from given time.

    Args:
        start_time: Start searching from this time
        apply_kp_offset: Whether to apply 307-second offset
        max_hours: Maximum hours to search ahead

    Returns:
        Tuple of (change_time, old_sl2, new_sl2) or None if not found
    """
    current = start_time
    end_time = start_time + timedelta(hours=max_hours)

    # Get initial SL2
    moon = get_positions_hft(current, planet_id=2, apply_kp_offset=apply_kp_offset)
    last_sl2 = moon.sl2

    # Check every 30 seconds (SL2 changes are typically 20-30 minutes apart)
    step = timedelta(seconds=30)

    while current <= end_time:
        current += step
        moon = get_positions_hft(current, planet_id=2, apply_kp_offset=apply_kp_offset)

        if moon.sl2 != last_sl2:
            # Found a change! Now refine to exact second
            exact_time = _refine_change_time(
                current - step, current, last_sl2, moon.sl2, apply_kp_offset
            )
            return exact_time, last_sl2, moon.sl2

        last_sl2 = moon.sl2

    return None


def _refine_change_time(
    before: datetime,
    after: datetime,
    old_lord: int,
    new_lord: int,
    apply_kp_offset: bool,
) -> datetime:
    """Binary search to find exact change time."""
    tolerance = timedelta(seconds=1)

    while after - before > tolerance:
        mid = before + (after - before) / 2
        moon = get_positions_hft(mid, planet_id=2, apply_kp_offset=apply_kp_offset)

        if moon.sl2 == old_lord:
            before = mid
        else:
            after = mid

    return after


def preload_trading_day(
    date: datetime.date, ny_open: str = "09:30", ny_close: str = "16:00"
) -> int:
    """
    Preload cache with Moon positions for entire trading day.

    Args:
        date: Trading date
        ny_open: Market open time in NY (HH:MM)
        ny_close: Market close time in NY (HH:MM)

    Returns:
        Number of positions cached
    """
    import pytz

    ny_tz = pytz.timezone("America/New_York")

    # Parse times
    open_h, open_m = map(int, ny_open.split(":"))
    close_h, close_m = map(int, ny_close.split(":"))

    # Create NY times
    start_ny = ny_tz.localize(datetime(date.year, date.month, date.day, open_h, open_m))
    end_ny = ny_tz.localize(datetime(date.year, date.month, date.day, close_h, close_m))

    # Convert to UTC
    start_utc = start_ny.astimezone(UTC)
    end_utc = end_ny.astimezone(UTC)

    # Preload with 60-second intervals (more than enough for SL2)
    return warmup_cache(start_utc, end_utc, planet_id=2, interval_seconds=60)


def get_all_sl2_changes_for_day(
    date: datetime.date, ny_open: str = "09:30", ny_close: str = "16:00"
) -> list[tuple[datetime, int, int]]:
    """
    Get all Moon SL2 changes for a trading day.

    Returns:
        List of (change_time, old_sl2, new_sl2) tuples
    """
    import pytz

    ny_tz = pytz.timezone("America/New_York")

    # Parse times
    open_h, open_m = map(int, ny_open.split(":"))
    close_h, close_m = map(int, ny_close.split(":"))

    # Create NY times
    start_ny = ny_tz.localize(datetime(date.year, date.month, date.day, open_h, open_m))
    end_ny = ny_tz.localize(datetime(date.year, date.month, date.day, close_h, close_m))

    # Convert to UTC
    start_utc = start_ny.astimezone(UTC)
    end_utc = end_ny.astimezone(UTC)

    changes = []
    current = start_utc

    # Get initial SL2
    moon = get_positions_hft(current, planet_id=2, apply_kp_offset=True)
    last_sl2 = moon.sl2

    # Scan in 30-second increments
    step = timedelta(seconds=30)

    while current <= end_utc:
        current += step
        moon = get_positions_hft(current, planet_id=2, apply_kp_offset=True)

        if moon.sl2 != last_sl2:
            # Refine to exact time
            exact_time = _refine_change_time(
                current - step, current, last_sl2, moon.sl2, apply_kp_offset=True
            )
            changes.append((exact_time, last_sl2, moon.sl2))
            last_sl2 = moon.sl2

    return changes


def print_cache_stats():
    """Print current cache statistics."""
    cache = get_hft_cache()
    monitor = get_cache_monitor()

    print("\nHFT CACHE STATISTICS")
    print("=" * 50)

    # Overall stats
    all_stats = cache.get_all_stats()

    for planet_id, stats in all_stats.items():
        if stats["hits"] + stats["misses"] > 0:
            print(f"\n{PLANET_NAMES.get(planet_id, f'Planet {planet_id}')}:")
            print(f"  Hits: {stats['hits']:,}")
            print(f"  Misses: {stats['misses']:,}")
            print(f"  Hit Rate: {stats['hit_rate']:.1%}")
            print(f"  Cache Size: {stats['size']}")
            print(f"  TTL: {stats['ttl']}s")

    # Performance metrics
    metrics = monitor.get_metrics()
    if metrics["total_requests"] > 0:
        print("\nPERFORMANCE METRICS:")
        print(f"  Total Requests: {metrics['total_requests']:,}")
        print(f"  Avg Request Time: {metrics['avg_request_time_ms']:.3f}ms")
        print(f"  Avg Cache Hit Time: {metrics['avg_cache_time_ms']:.3f}ms")
        print(f"  Avg Calculation Time: {metrics['avg_calculation_time_ms']:.3f}ms")
        print(f"  Cache Speedup: {metrics['cache_speedup']:.1f}x")

        # Calculate effective rate
        if metrics["avg_request_time_ms"] > 0:
            rate = 1000.0 / metrics["avg_request_time_ms"]
            print(f"  Effective Rate: {rate:,.0f} calculations/second")


def clear_cache():
    """Clear all cache entries."""
    cache = get_hft_cache()
    cache.clear_all()

    monitor = get_cache_monitor()
    monitor.reset()

    print("Cache cleared and statistics reset.")


def shutdown_cache():
    """Shutdown cache cleanup threads."""
    cache = get_hft_cache()
    cache.shutdown()
    print("Cache shutdown complete.")


# Convenience function for direct KP calculation (bypasses ephemeris)
def get_kp_lords_direct(longitude: float, levels: int = 3) -> list[int]:
    """
    Direct KP lord calculation from longitude.
    Ultra-fast, no ephemeris lookup needed.

    Args:
        longitude: Sidereal longitude in degrees
        levels: Number of lord levels (1-5)

    Returns:
        List of lord IDs
    """
    return kp_chain_for_longitude(longitude, levels=levels)
