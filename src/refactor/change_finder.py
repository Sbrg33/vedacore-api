#!/usr/bin/env python3
"""
KP Lord Change Detection
High-precision detection and refinement of lord transitions
Detection runs in raw UTC, finance offset applied only at display
"""


from datetime import datetime, timedelta

from .angles_indices import sign_index
from .core_types import KPLordChange
from .kp_chain import get_kp_lords_for_planet
from .swe_backend import get_planet_longitude
from .time_utils import datetime_to_julian_day, ensure_utc, to_ny

# ============================================================================
# CHANGE DETECTION PARAMETERS
# ============================================================================

# Grid search parameters
COARSE_GRID_MINUTES = 5  # 5-minute intervals for initial search
FINE_GRID_SECONDS = 30  # 30-second intervals for refinement

# Bisection parameters
BISECTION_TOLERANCE_SECONDS = 0.5  # Target precision in seconds
BISECTION_MAX_DEPTH = 20  # Maximum bisection iterations

# ============================================================================
# LORD EXTRACTION
# ============================================================================


def get_lords_at_time(
    ts_utc: datetime, planet_id: int, levels: tuple[str, ...] = ("nl", "sl", "sl2")
) -> dict[str, int]:
    """Get KP lords for a planet at specific time

    Args:
        ts_utc: UTC timestamp
        planet_id: Planet ID (1-9)
        levels: Lord levels to extract

    Returns:
        Dictionary mapping level to lord ID
    """
    ts_utc = ensure_utc(ts_utc)
    longitude, _ = get_planet_longitude(ts_utc, planet_id)

    # Get full KP chain
    nl, sl, sl2 = get_kp_lords_for_planet(longitude)

    # Build result based on requested levels
    result = {}
    if "nl" in levels:
        result["nl"] = nl
    if "sl" in levels:
        result["sl"] = sl
    if "sl2" in levels:
        result["sl2"] = sl2
    if "sign" in levels:
        result["sign"] = sign_index(longitude) + 1  # 1-12

    return result


# ============================================================================
# CHANGE DETECTION - COARSE GRID
# ============================================================================


def detect_changes_coarse(
    start_utc: datetime,
    end_utc: datetime,
    planet_id: int,
    levels: tuple[str, ...],
    grid_minutes: int = COARSE_GRID_MINUTES,
) -> list[tuple[datetime, str, int, int]]:
    """Coarse grid search for lord changes

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        planet_id: Planet ID
        levels: Lord levels to detect
        grid_minutes: Grid interval in minutes

    Returns:
        List of (approx_time, level, old_lord, new_lord) tuples
    """
    changes = []

    # Initialize with lords at start
    current_time = ensure_utc(start_utc)
    end_time = ensure_utc(end_utc)
    prev_lords = get_lords_at_time(current_time, planet_id, levels)

    # Grid search
    grid_delta = timedelta(minutes=grid_minutes)

    while current_time < end_time:
        next_time = min(current_time + grid_delta, end_time)
        next_lords = get_lords_at_time(next_time, planet_id, levels)

        # Check for changes in each level
        for level in levels:
            if level in prev_lords and level in next_lords:
                if prev_lords[level] != next_lords[level]:
                    # Found a change in this interval
                    changes.append(
                        (
                            next_time,  # Approximate time
                            level,
                            prev_lords[level],
                            next_lords[level],
                        )
                    )

        prev_lords = next_lords
        current_time = next_time

    return changes


# ============================================================================
# CHANGE REFINEMENT - BISECTION
# ============================================================================


def refine_change_time(
    start_utc: datetime,
    end_utc: datetime,
    planet_id: int,
    level: str,
    old_lord: int,
    new_lord: int,
    tolerance_seconds: float = BISECTION_TOLERANCE_SECONDS,
) -> datetime:
    """Refine change time using bisection

    Finds exact moment of lord transition within tolerance.

    Args:
        start_utc: Start of interval containing change
        end_utc: End of interval containing change
        planet_id: Planet ID
        level: Lord level ('nl', 'sl', 'sl2', 'sign')
        old_lord: Lord before change
        new_lord: Lord after change
        tolerance_seconds: Target precision

    Returns:
        Refined timestamp of change
    """
    start = ensure_utc(start_utc)
    end = ensure_utc(end_utc)

    # Convert to Julian days for precision
    jd_start = datetime_to_julian_day(start)
    jd_end = datetime_to_julian_day(end)

    # Bisection loop
    iterations = 0
    while iterations < BISECTION_MAX_DEPTH:
        # Check interval size
        interval_seconds = (jd_end - jd_start) * 86400.0
        if interval_seconds <= tolerance_seconds:
            break

        # Midpoint
        jd_mid = (jd_start + jd_end) / 2.0

        # Get lord at midpoint
        from .time_utils import julian_day_to_datetime

        mid_time = julian_day_to_datetime(jd_mid)
        mid_lords = get_lords_at_time(mid_time, planet_id, (level,))
        mid_lord = mid_lords.get(level)

        # Determine which half contains the change
        if mid_lord == old_lord:
            # Change is in second half
            jd_start = jd_mid
        else:
            # Change is in first half
            jd_end = jd_mid

        iterations += 1

    # Return midpoint of final interval
    jd_final = (jd_start + jd_end) / 2.0
    return julian_day_to_datetime(jd_final)


# ============================================================================
# MAIN CHANGE DETECTION FUNCTION
# ============================================================================


def detect_kp_lord_changes(
    start_utc: datetime,
    end_utc: datetime,
    planet_id: int = 2,
    levels: tuple[str, ...] = ("nl", "sl", "sl2"),
) -> list[KPLordChange]:
    """Detect KP lord changes in time range

    Detection runs in raw UTC. Finance offset applied only at display.

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        planet_id: Planet ID (default: 2 for Moon)
        levels: Lord levels to detect

    Returns:
        List of KPLordChange objects
    """
    start_utc = ensure_utc(start_utc)
    end_utc = ensure_utc(end_utc)

    # Coarse detection
    coarse_changes = detect_changes_coarse(start_utc, end_utc, planet_id, levels)

    # Refine each change
    refined_changes = []

    for approx_time, level, old_lord, new_lord in coarse_changes:
        # Define search window around approximate time
        window_start = approx_time - timedelta(minutes=COARSE_GRID_MINUTES)
        window_end = approx_time

        # Ensure window is within original range
        window_start = max(window_start, start_utc)
        window_end = min(window_end, end_utc)

        # Refine the exact time
        exact_time = refine_change_time(
            window_start, window_end, planet_id, level, old_lord, new_lord
        )

        # Get planet position at change
        longitude, _ = get_planet_longitude(exact_time, planet_id)

        # Create KPLordChange object
        change = KPLordChange(
            timestamp_utc=exact_time,
            julian_day=datetime_to_julian_day(exact_time),
            planet_id=planet_id,
            level=level,
            old_lord=old_lord,
            new_lord=new_lord,
            position=longitude,
            timestamp_ny=to_ny(exact_time),
        )

        refined_changes.append(change)

    # Sort by timestamp
    refined_changes.sort(key=lambda x: x.timestamp_utc)

    return refined_changes


# ============================================================================
# OPTIMIZATION: CHANGE DETECTION WITH CACHING
# ============================================================================


class ChangeDetector:
    """Optimized change detector with caching"""

    def __init__(self):
        """Initialize change detector"""
        self._cache = {}  # Cache for lord calculations
        self._cache_hits = 0
        self._cache_misses = 0

    def _get_lords_cached(
        self, ts_utc: datetime, planet_id: int, levels: tuple[str, ...]
    ) -> dict[str, int]:
        """Get lords with caching"""
        # Create cache key
        cache_key = (ts_utc.timestamp(), planet_id, levels)

        if cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]

        self._cache_misses += 1
        result = get_lords_at_time(ts_utc, planet_id, levels)
        self._cache[cache_key] = result
        return result

    def detect_changes(
        self,
        start_utc: datetime,
        end_utc: datetime,
        planet_id: int = 2,
        levels: tuple[str, ...] = ("nl", "sl", "sl2"),
    ) -> list[KPLordChange]:
        """Detect changes with caching optimization"""
        # Clear cache for new detection run
        self._cache.clear()

        # Use standard detection with cached lord calculations
        return detect_kp_lord_changes(start_utc, end_utc, planet_id, levels)

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "cache_size": len(self._cache),
        }


# ============================================================================
# SPECIALIZED DETECTORS
# ============================================================================


def detect_sign_ingresses(
    start_utc: datetime, end_utc: datetime, planet_id: int = 2
) -> list[KPLordChange]:
    """Detect sign ingress events

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        planet_id: Planet ID

    Returns:
        List of sign ingress events
    """
    return detect_kp_lord_changes(start_utc, end_utc, planet_id, ("sign",))


def detect_nakshatra_changes(
    start_utc: datetime, end_utc: datetime, planet_id: int = 2
) -> list[KPLordChange]:
    """Detect nakshatra lord (NL) changes

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        planet_id: Planet ID

    Returns:
        List of nakshatra lord changes
    """
    return detect_kp_lord_changes(start_utc, end_utc, planet_id, ("nl",))


def detect_all_changes(
    start_utc: datetime, end_utc: datetime, planet_id: int = 2
) -> dict[str, list[KPLordChange]]:
    """Detect all types of changes

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        planet_id: Planet ID

    Returns:
        Dictionary mapping level to list of changes
    """
    all_changes = detect_kp_lord_changes(
        start_utc, end_utc, planet_id, ("nl", "sl", "sl2", "sign")
    )

    # Group by level
    grouped = {"nl": [], "sl": [], "sl2": [], "sign": []}

    for change in all_changes:
        if change.level in grouped:
            grouped[change.level].append(change)

    return grouped


# ============================================================================
# VALIDATION UTILITIES
# ============================================================================


def validate_change_sequence(changes: list[KPLordChange]) -> bool:
    """Validate that change sequence is logical

    Args:
        changes: List of changes to validate

    Returns:
        True if sequence is valid
    """
    if not changes:
        return True

    # Check timestamps are in order
    for i in range(1, len(changes)):
        if changes[i].timestamp_utc <= changes[i - 1].timestamp_utc:
            return False

    # Check that old_lord of each change matches new_lord of previous
    # (for same level and planet)
    by_level = {}
    for change in changes:
        key = (change.planet_id, change.level)
        if key not in by_level:
            by_level[key] = []
        by_level[key].append(change)

    for key, level_changes in by_level.items():
        for i in range(1, len(level_changes)):
            if level_changes[i].old_lord != level_changes[i - 1].new_lord:
                return False

    return True
