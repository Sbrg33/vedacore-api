"""
Market Micro-Timing Engine
Phase 8: Core volatility window generation from astro factors
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from .eclipse import EclipseEvent
from .eclipse import events_between as eclipse_events_between

# Dasha requires birth data - will be added later if needed
# from .dasha import get_dasha_engine
from .micro_config import MicroConfig, get_micro_config

# Import existing phase modules for data
from .moon_factors_enhanced import find_moon_events, get_moon_profile
from .nodes import NodeEvent, get_node_calculator

logger = logging.getLogger(__name__)

UTC = UTC
Strength = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class MicroWindow:
    """
    Represents a volatility window with timing and strength.

    Attributes:
        start: Window start time (UTC)
        end: Window end time (UTC)
        score: Raw volatility score (0.0 to 1.0)
        strength: Categorical strength (low/medium/high)
        factors: List of contributing factors
    """

    start: datetime
    end: datetime
    score: float
    strength: Strength
    factors: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for API responses."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "score": round(self.score, 4),
            "strength": self.strength,
            "factors": self.factors,
        }


def _strength(score: float, cfg: MicroConfig) -> Strength:
    """Categorize volatility score into strength levels."""
    if score >= cfg.high_threshold:
        return "high"
    if score >= cfg.med_threshold:
        return "medium"
    return "low"


def _merge_windows(windows: list[MicroWindow], cfg: MicroConfig) -> list[MicroWindow]:
    """
    Merge overlapping windows, combining scores and factors.

    Strategy:
    - Sort windows by start time
    - Merge overlapping windows
    - Use maximum score for merged windows
    - Union factor tags
    """
    if not windows:
        return []

    # Sort by start time
    windows = sorted(windows, key=lambda w: w.start)
    merged: list[MicroWindow] = []
    current = windows[0]

    for window in windows[1:]:
        if window.start <= current.end:
            # Overlapping - merge
            end = max(current.end, window.end)
            score = max(current.score, window.score)
            factors = sorted(list(set(current.factors + window.factors)))
            current = MicroWindow(
                current.start, end, score, _strength(score, cfg), factors
            )
        else:
            # No overlap - save current and start new
            merged.append(current)
            current = window

    # Don't forget the last window
    merged.append(current)
    return merged


def _create_window(
    center: datetime, minutes: int, score: float, strength: Strength, factors: list[str]
) -> MicroWindow:
    """Create a window centered on a timestamp."""
    half = timedelta(minutes=minutes // 2)
    return MicroWindow(
        start=center - half,
        end=center + half,
        score=score,
        strength=strength,
        factors=factors,
    )


def _score_moon_profile(profile: dict[str, Any], cfg: MicroConfig) -> float:
    """
    Score volatility contribution from Moon profile.

    Factors:
    - Velocity deviation from mean (faster or slower = higher volatility)
    - Distance from Earth (closer = higher volatility)
    - Latitude extremes (higher absolute latitude = higher volatility)
    """
    # Velocity index: 1.0 = mean speed, deviation indicates volatility
    vi = profile.get("velocity_index", 1.0)
    vel_deviation = abs(vi - 1.0)
    vel_score = min(vel_deviation / 0.2, 1.0)  # 20% deviation = max score

    # Distance index: 0 = perigee (close), 1 = apogee (far)
    # Closer moon = stronger gravitational effects
    di = profile.get("distance_index", 0.5)
    dist_score = 1.0 - di  # Invert so closer = higher score

    # Latitude index: -1 to +1, extremes = higher volatility
    li = abs(profile.get("latitude_index", 0.0))
    lat_score = min(li / 0.6, 1.0)  # 60% of max = full score

    # Combine with equal weights (can be tuned)
    combined = (vel_score + dist_score + lat_score) / 3.0
    return max(0.0, min(1.0, combined))


def _score_moon_anomaly(anomaly_type: str) -> float:
    """Score moon anomaly events by type."""
    scores = {
        "perigee": 0.9,  # Closest approach - high impact
        "apogee": 0.7,  # Farthest point - moderate impact
        "standstill": 0.8,  # Declination extreme - significant
        "fast_moon": 0.6,  # Speed anomaly - moderate
        "slow_moon": 0.6,  # Speed anomaly - moderate
    }
    return scores.get(anomaly_type, 0.5)


def _score_node_event(event: NodeEvent) -> float:
    """Score node events by type."""
    if event.event_type == "direction_change":
        return 1.0  # Maximum impact - trend reversal
    elif event.event_type in ("stationary_start", "stationary_end"):
        return 0.7  # High impact - pause in motion
    elif event.event_type == "wobble_peak":
        return 0.4  # Moderate impact
    else:
        return 0.3  # Low impact


def _score_eclipse(eclipse: EclipseEvent) -> float:
    """Score eclipse events by type and magnitude."""
    base_scores = {
        "total_solar": 1.0,
        "annular_solar": 0.9,
        "hybrid_solar": 0.95,
        "partial_solar": 0.7,
        "total_lunar": 0.8,
        "partial_lunar": 0.6,
        "penumbral_lunar": 0.4,
    }

    # Get base score from classification
    eclipse_type = eclipse.classification.lower().replace(" ", "_")
    base = base_scores.get(eclipse_type, 0.5)

    # Adjust by magnitude if available
    if eclipse.magnitude is not None:
        base *= 0.5 + 0.5 * min(eclipse.magnitude, 1.0)

    return base


def _score_dasha_change(level: int) -> float:
    """Score dasha period changes by level."""
    # Level 1 = Mahadasha (major), 5 = Prana (minor)
    scores = {
        1: 0.9,  # Mahadasha change - rare, major
        2: 0.7,  # Antardasha - significant
        3: 0.5,  # Pratyantara - moderate
        4: 0.3,  # Sookshma - minor
        5: 0.2,  # Prana - very minor
    }
    return scores.get(level, 0.4)


def _get_moon_windows(day_utc: date, cfg: MicroConfig) -> list[MicroWindow]:
    """Generate volatility windows from Moon factors."""
    windows = []

    # Get moon profile for the day
    start_dt = datetime.combine(day_utc, datetime.min.time(), tzinfo=UTC)

    try:
        # Get profile at start of day
        profile = get_moon_profile(start_dt)

        # Score the profile
        base_score = _score_moon_profile(profile, cfg)
        weighted_score = base_score * cfg.w_moon_velocity

        if weighted_score > 0.01:  # Threshold to avoid noise
            # Create window at moon's peak influence time (typically around noon)
            peak_time = start_dt + timedelta(hours=12)
            window = _create_window(
                peak_time,
                cfg.win_moon_anomaly_min,
                weighted_score,
                _strength(weighted_score, cfg),
                ["moon_profile"],
            )
            windows.append(window)

        # Search for specific anomaly events
        end_dt = start_dt + timedelta(days=1)
        events = find_moon_events(start_dt, end_dt)

        for event in events:
            if event.event_type in [
                "perigee",
                "apogee",
                "max_declination",
                "min_declination",
            ]:
                anomaly_score = _score_moon_anomaly(event.event_type)
                weighted = anomaly_score * cfg.w_moon_velocity

                window = _create_window(
                    event.timestamp,
                    cfg.win_moon_anomaly_min,
                    weighted,
                    _strength(weighted, cfg),
                    ["moon_anomaly", event.event_type],
                )
                windows.append(window)

    except Exception as e:
        logger.warning(f"Error getting moon windows: {e}")

    return windows


def _get_node_windows(day_utc: date, cfg: MicroConfig) -> list[MicroWindow]:
    """Generate volatility windows from Node events."""
    windows = []

    try:
        # Get node calculator and search for events in the day
        start_dt = datetime.combine(day_utc, datetime.min.time(), tzinfo=UTC)
        end_dt = start_dt + timedelta(days=1)

        calculator = get_node_calculator()
        events = calculator.detect_events(start_dt, end_dt)

        for event in events:
            score = _score_node_event(event)
            weighted = score * cfg.w_node_events

            if weighted > 0.01:
                window = _create_window(
                    event.timestamp,
                    cfg.win_node_event_min,
                    weighted,
                    _strength(weighted, cfg),
                    ["node_event", event.event_type],
                )
                windows.append(window)

    except Exception as e:
        logger.warning(f"Error getting node windows: {e}")

    return windows


def _get_eclipse_windows(day_utc: date, cfg: MicroConfig) -> list[MicroWindow]:
    """Generate volatility windows from Eclipse events."""
    windows = []

    try:
        # Search wider range since eclipse effects extend days
        start_dt = datetime.combine(day_utc, datetime.min.time(), tzinfo=UTC)
        pad = timedelta(hours=cfg.win_eclipse_hours)

        # Search from days before to days after
        search_start = start_dt - pad
        search_end = start_dt + timedelta(days=1) + pad

        eclipses = eclipse_events_between(search_start, search_end)

        for eclipse in eclipses:
            # Check if eclipse window overlaps with our day
            eclipse_start = eclipse.peak_utc - pad
            eclipse_end = eclipse.peak_utc + pad

            day_start = start_dt
            day_end = start_dt + timedelta(days=1)

            # Check for overlap
            if eclipse_end >= day_start and eclipse_start <= day_end:
                score = _score_eclipse(eclipse)
                weighted = score * cfg.w_eclipse

                # Create window centered on eclipse peak
                # but clipped to day boundaries if needed
                win_start = max(eclipse_start, day_start)
                win_end = min(eclipse_end, day_end)

                window = MicroWindow(
                    win_start,
                    win_end,
                    weighted,
                    _strength(weighted, cfg),
                    ["eclipse", eclipse.classification.lower().replace(" ", "_")],
                )
                windows.append(window)

    except Exception as e:
        logger.warning(f"Error getting eclipse windows: {e}")

    return windows


def _get_dasha_windows(
    day_utc: date,
    cfg: MicroConfig,
    birth_time: datetime | None = None,
    moon_longitude: float | None = None,
) -> list[MicroWindow]:
    """
    Generate volatility windows from Dasha period changes.

    Note: Requires birth_time and moon_longitude for personalized calculations.
    For market-wide signals, we could use a reference chart (e.g., NYSE founding).
    """
    windows = []

    # Dasha calculation requires birth data and is disabled for now
    # Will be implemented when birth chart is available
    # (e.g., NYSE founding chart for market-wide signals)

    return windows


def build_day_timeline(
    day_local: date,
    *,
    cfg: MicroConfig | None = None,
    birth_time: datetime | None = None,
    moon_longitude: float | None = None,
) -> list[MicroWindow]:
    """
    Build micro-volatility windows for a given date.

    Args:
        day_local: Date to analyze (interpreted as UTC date)
        cfg: Configuration (uses default if None)
        birth_time: Birth time for Dasha calculations (optional)
        moon_longitude: Birth moon longitude for Dasha (optional)

    Returns:
        List of merged volatility windows sorted by start time
    """
    if cfg is None:
        cfg = get_micro_config()

    all_windows = []

    # Collect windows from each enabled source
    if cfg.enable_moon:
        all_windows.extend(_get_moon_windows(day_local, cfg))

    if cfg.enable_nodes:
        all_windows.extend(_get_node_windows(day_local, cfg))

    if cfg.enable_eclipse:
        all_windows.extend(_get_eclipse_windows(day_local, cfg))

    if cfg.enable_dasha and birth_time and moon_longitude is not None:
        all_windows.extend(
            _get_dasha_windows(day_local, cfg, birth_time, moon_longitude)
        )

    # Merge overlapping windows
    merged = _merge_windows(all_windows, cfg)

    # Filter out low-score windows if desired
    # (keeping all for now for transparency)

    return merged


def find_next_high_volatility(
    threshold: Strength = "high", max_days: int = 31, cfg: MicroConfig | None = None
) -> MicroWindow | None:
    """
    Find the next high-volatility window from today.

    Args:
        threshold: Minimum strength level to search for
        max_days: Maximum days to search ahead
        cfg: Configuration (uses default if None)

    Returns:
        Next matching window or None if not found
    """
    if cfg is None:
        cfg = get_micro_config()

    today = datetime.now(UTC).date()
    strength_order = {"low": 0, "medium": 1, "high": 2}
    min_strength = strength_order[threshold]

    for day_offset in range(max_days):
        check_date = today + timedelta(days=day_offset)
        windows = build_day_timeline(check_date, cfg=cfg)

        for window in windows:
            if strength_order[window.strength] >= min_strength:
                # Check if window is still in future
                if window.start > datetime.now(UTC):
                    return window

    return None


def calculate_volatility_score(
    timestamp: datetime, cfg: MicroConfig | None = None
) -> dict[str, Any]:
    """
    Calculate instantaneous volatility score at a specific time.

    Args:
        timestamp: Time to evaluate
        cfg: Configuration (uses default if None)

    Returns:
        Dictionary with score, strength, and contributing factors
    """
    if cfg is None:
        cfg = get_micro_config()

    # Get windows for the day
    day = timestamp.date()
    windows = build_day_timeline(day, cfg=cfg)

    # Find windows that contain this timestamp
    active_windows = [w for w in windows if w.start <= timestamp <= w.end]

    if not active_windows:
        return {
            "timestamp": timestamp.isoformat(),
            "score": 0.0,
            "strength": "low",
            "factors": [],
            "active_windows": 0,
        }

    # Aggregate scores (using max)
    max_score = max(w.score for w in active_windows)
    all_factors = []
    for w in active_windows:
        all_factors.extend(w.factors)
    unique_factors = sorted(list(set(all_factors)))

    return {
        "timestamp": timestamp.isoformat(),
        "score": round(max_score, 4),
        "strength": _strength(max_score, cfg),
        "factors": unique_factors,
        "active_windows": len(active_windows),
    }
