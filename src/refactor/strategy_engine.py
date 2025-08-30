"""
Trading Strategy Engine
Phase 9: Confidence synthesis, rule combinators, and audit trails
"""

from __future__ import annotations

import json
import logging

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from .direction_config import get_direction_config
from .direction_engine import compute_direction
from .strategy_config import StrategyConfig, get_strategy_config

logger = logging.getLogger(__name__)

UTC = UTC
NY_TZ = ZoneInfo("America/New_York")
Strength = Literal["low", "medium", "high"]
Direction = Literal["neutral", "up", "down"]


@dataclass(frozen=True)
class MinuteSignal:
    """
    Represents a minute-level trading signal with directional bias.

    Attributes:
        t: Timestamp (UTC)
        confidence: Signal confidence score (0.0 to 1.0)
        direction: Signal direction (neutral/up/down)
        direction_score: Magnitude of directional bias (0.0 to 1.0)
        strength: Categorical strength (low/medium/high)
        tags: List of active tags for this minute
        factors: Breakdown of confidence contributions
        direction_factors: Breakdown of directional contributions
        rules_applied: List of rules that were triggered
    """

    t: datetime
    confidence: float
    direction: Direction
    direction_score: float
    strength: Strength
    tags: list[str]
    factors: dict[str, float]
    direction_factors: dict[str, float]
    rules_applied: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for API/logging."""
        return {
            "t": self.t.isoformat(),
            "confidence": round(self.confidence, 4),
            "direction": self.direction,
            "direction_score": round(self.direction_score, 4),
            "strength": self.strength,
            "tags": self.tags,
            "factors": {k: round(v, 4) for k, v in self.factors.items()},
            "direction_factors": {
                k: round(v, 4) for k, v in self.direction_factors.items()
            },
            "rules_applied": self.rules_applied,
        }


def _within_market_hours(ts: datetime, cfg: StrategyConfig) -> bool:
    """Check if timestamp is within market hours."""
    if not cfg.enable_market_hours:
        return True

    # Convert to NY time
    local = ts.astimezone(NY_TZ)
    local_time = local.time()

    open_time = time(cfg.open_hh, cfg.open_mm)
    close_time = time(cfg.close_hh, cfg.close_mm)

    return open_time <= local_time <= close_time


def _categorize_strength(confidence: float, cfg: StrategyConfig) -> Strength:
    """Categorize confidence into strength levels."""
    if confidence >= cfg.high_threshold:
        return "high"
    if confidence >= cfg.med_threshold:
        return "medium"
    return "low"


def _map_amd_weight(phase: str) -> float:
    """
    Map AMD phase to weight.

    Critical phases get higher weights for volatility prediction.
    """
    weights = {
        "critical_change": 1.0,
        "pre_change": 0.7,
        "confirmation": 0.5,
        "volatility_build": 0.4,
        "consolidation": 0.3,
        "neutral": 0.2,
    }
    return weights.get(phase, 0.2)


def _apply_rulebook(
    confidence: float, tags: list[str], cfg: StrategyConfig
) -> tuple[float, list[str]]:
    """
    Apply rulebook to modify confidence based on tag combinations.

    Returns:
        Tuple of (modified confidence, list of applied rules)
    """
    if not cfg.enable_rulebook or not cfg.rulebook:
        return confidence, []

    applied_rules = []

    for rule in cfg.rulebook.get("rules", []):
        required_tags = rule.get("when", [])

        # Check if all required tags are present
        if all(tag in tags for tag in required_tags):
            multiplier = float(rule.get("multiplier", 1.0))
            confidence *= multiplier
            applied_rules.append(rule.get("name", "unnamed_rule"))

    # Clamp to [0, 1]
    confidence = min(max(confidence, 0.0), 1.0)

    return confidence, applied_rules


def _ema_smooth(previous: float, current: float, alpha: float) -> float:
    """
    Apply exponential moving average smoothing.

    Args:
        previous: Previous smoothed value
        current: Current raw value
        alpha: Smoothing factor (0 < alpha <= 1)

    Returns:
        Smoothed value
    """
    return alpha * current + (1.0 - alpha) * previous


def synthesize_minute(
    ts: datetime,
    *,
    cfg: StrategyConfig,
    dir_cfg=None,
    micro_feature: dict[str, Any] | None = None,
    micro_prev2: float | None = None,
    micro_prev5: float | None = None,
    amd_phase: str | None = None,
    moon_profile: dict[str, Any] | None = None,
    node_event_recent: bool | None = None,
    node_event_minutes_ago: int | None = None,
    previous_confidence: float = 0.0,
    previous_raw_direction: float | None = None,
    last_flip_minutes_ago: int | None = None,
) -> tuple[MinuteSignal, float]:
    """
    Synthesize a minute-level signal from multiple factors with directional bias.

    Args:
        ts: Timestamp for this minute
        cfg: Strategy configuration
        dir_cfg: Direction configuration (optional)
        micro_feature: Micro-timing window data if active
        micro_prev2: Micro score 2 minutes ago
        micro_prev5: Micro score 5 minutes ago
        amd_phase: Current AMD phase if available
        moon_profile: Moon profile data if available
        node_event_recent: Whether a node event occurred recently
        node_event_minutes_ago: Minutes since last node event
        previous_confidence: Previous minute's confidence for smoothing
        previous_raw_direction: Previous raw direction score for smoothing
        last_flip_minutes_ago: Minutes since last direction flip

    Returns:
        Tuple of (MinuteSignal with confidence and direction, raw_direction for next iteration)
    """
    confidence = 0.0
    tags: list[str] = []
    contributions: dict[str, float] = {}

    # 1. Micro-timing contribution
    micro_score_now = None
    if micro_feature:
        micro_score_now = float(micro_feature.get("score", 0.0))
        weighted = cfg.w_micro * micro_score_now
        confidence += weighted
        contributions["micro"] = weighted

        # Add strength tags
        strength = micro_feature.get("strength")
        if strength == "high":
            tags.append("micro_high")
        elif strength == "medium":
            tags.append("micro_medium")
        elif strength == "low":
            tags.append("micro_low")

        # Add factor tags
        factors = micro_feature.get("factors", [])
        for factor in factors:
            if factor not in tags:
                tags.append(factor)

    # 2. AMD phase contribution
    if amd_phase:
        weight = _map_amd_weight(amd_phase)
        weighted = cfg.w_amd * weight
        confidence += weighted
        contributions["amd"] = weighted
        tags.append(f"AMD={amd_phase}")

    # 3. Moon factors contribution
    if moon_profile:
        # Use velocity deviation as indicator
        velocity_index = float(moon_profile.get("velocity_index", 1.0))
        velocity_deviation = abs(velocity_index - 1.0)

        # Distance factor (closer = higher volatility)
        distance_index = float(moon_profile.get("distance_index", 0.5))
        distance_factor = 1.0 - distance_index

        # Combine moon factors
        moon_score = (velocity_deviation / 0.3 + distance_factor) / 2.0
        moon_score = min(moon_score, 1.0)
        weighted = cfg.w_moon * moon_score
        confidence += weighted
        contributions["moon"] = weighted

        # Add moon tags
        if velocity_index > 1.15:
            tags.append("moon_fast")
        elif velocity_index < 0.85:
            tags.append("moon_slow")

        if distance_index < 0.2:
            tags.append("moon_perigee")
        elif distance_index > 0.8:
            tags.append("moon_apogee")

    # 4. Node events contribution
    if node_event_recent:
        # Recent node event increases volatility likelihood
        weighted = cfg.w_nodes * 0.7
        confidence += weighted
        contributions["nodes"] = weighted
        tags.extend(["node_event", "direction_change"])

    # Clamp raw confidence to [0, 1]
    confidence = min(max(confidence, 0.0), 1.0)

    # Apply rulebook
    confidence, rules_applied = _apply_rulebook(confidence, tags, cfg)

    # Apply smoothing if enabled and within market hours
    if cfg.enable_smoothing and _within_market_hours(ts, cfg):
        confidence = _ema_smooth(previous_confidence, confidence, cfg.ema_alpha)

    # Determine strength category
    strength = _categorize_strength(confidence, cfg)

    # Compute direction (Phase 10)
    if dir_cfg:
        dir_signal, raw_direction = compute_direction(
            ts,
            confidence=confidence,
            micro_now=micro_score_now,
            micro_prev2=micro_prev2,
            micro_prev5=micro_prev5,
            amd_phase=amd_phase,
            moon_profile=moon_profile,
            node_event_minutes_ago=node_event_minutes_ago,
            tags=tags,
            prev_raw=previous_raw_direction,
            last_flip_minutes_ago=last_flip_minutes_ago,
            cfg=dir_cfg,
        )
        direction = dir_signal.direction
        direction_score = dir_signal.direction_score
        direction_factors = dir_signal.dir_factors
        rules_applied.extend(dir_signal.rules_applied)
    else:
        # Fallback to neutral if no direction config
        direction = "neutral"
        direction_score = 0.0
        direction_factors = {}
        raw_direction = 0.0

    signal = MinuteSignal(
        t=ts,
        confidence=confidence,
        direction=direction,
        direction_score=direction_score,
        strength=strength,
        tags=sorted(set(tags)),
        factors=contributions,
        direction_factors=direction_factors,
        rules_applied=rules_applied,
    )

    return signal, raw_direction


def build_day_propensity(
    day_local: date,
    ticker: str = "TSLA",
    *,
    cfg: StrategyConfig | None = None,
    enable_direction: bool = True,
) -> list[MinuteSignal]:
    """
    Build a minute-by-minute propensity timeline for a trading day.

    Args:
        day_local: Date to analyze
        ticker: Ticker symbol (for future use)
        cfg: Strategy configuration (uses default if None)

    Returns:
        List of MinuteSignal objects for the day
    """
    if cfg is None:
        cfg = get_strategy_config()

    # Import here to avoid circular dependency
    from interfaces.registry import get_system

    # Get system adapters
    micro_system = get_system("KP_MICRO")
    # AMD would come from KP system but needs per-minute exposure
    # For now, we'll simulate AMD phases
    moon_system = get_system("KP_MOON") if callable(get_system) else None
    nodes_system = get_system("KP_NODES") if callable(get_system) else None

    # Define day boundaries in UTC
    start_dt = datetime.combine(day_local, time.min, tzinfo=UTC)
    end_dt = datetime.combine(day_local, time.max, tzinfo=UTC)

    # 1. Get daily micro windows
    micro_windows = []
    if micro_system:
        try:
            micro_day_data = micro_system.day(day_local)
            micro_windows = micro_day_data.get("windows", [])
        except Exception as e:
            logger.warning(f"Error getting micro windows: {e}")

    # Index windows by minute for fast lookup
    window_index: dict[str, dict[str, Any]] = {}
    for window in micro_windows:
        try:
            win_start = datetime.fromisoformat(
                window["start"].replace("Z", "+00:00")
            ).astimezone(UTC)
            win_end = datetime.fromisoformat(
                window["end"].replace("Z", "+00:00")
            ).astimezone(UTC)

            # Mark all minutes in window
            current = win_start
            while current <= win_end and current < end_dt:
                minute_key = current.strftime("%H:%M")

                # Keep highest scoring window if overlap
                if minute_key not in window_index or window_index[minute_key].get(
                    "score", 0
                ) < window.get("score", 0):
                    window_index[minute_key] = window

                current += timedelta(minutes=1)
        except Exception as e:
            logger.warning(f"Error indexing window: {e}")

    # 2. Get moon profile for the day
    moon_profile = None
    if moon_system:
        try:
            moon_profile = moon_system.snapshot(start_dt)
        except Exception as e:
            logger.warning(f"Error getting moon profile: {e}")

    # 3. Check for recent node events (simplified)
    node_event_recent = False
    if nodes_system:
        try:
            # Check if any node events in last 24 hours
            check_start = start_dt - timedelta(days=1)
            # This would need actual node event checking
            # For now, simulate occasional node events
            node_event_recent = (day_local.day % 7) == 0  # Weekly for demo
        except Exception as e:
            logger.warning(f"Error checking node events: {e}")

    # Get direction config if enabled
    dir_cfg = get_direction_config() if enable_direction else None

    # 4. Build minute-by-minute timeline
    signals: list[MinuteSignal] = []
    previous_confidence = 0.0
    previous_raw_direction = None
    last_direction = None
    last_flip_minutes = None

    # Build micro score history index for lookback
    micro_score_history: dict[str, float] = {}
    for minute_key, window in window_index.items():
        if window:
            micro_score_history[minute_key] = float(window.get("score", 0.0))

    # Generate signals for every minute of the day
    current = start_dt
    minute_counter = 0
    node_event_minutes_ago = None

    while current <= end_dt:
        minute_key = current.strftime("%H:%M")

        # Get micro feature for this minute
        micro_feature = window_index.get(minute_key)
        micro_score_now = micro_score_history.get(minute_key)

        # Get historical micro scores for slope calculation
        prev2_key = (current - timedelta(minutes=2)).strftime("%H:%M")
        prev5_key = (current - timedelta(minutes=5)).strftime("%H:%M")
        micro_prev2 = micro_score_history.get(prev2_key)
        micro_prev5 = micro_score_history.get(prev5_key)

        # Simulate AMD phase (in production, would get from actual AMD system)
        # For demo, cycle through phases
        hour = current.hour
        if hour in [9, 15]:  # Market open and near close
            amd_phase = "critical_change"
        elif hour in [10, 14]:
            amd_phase = "pre_change"
        elif hour in [11, 13]:
            amd_phase = "confirmation"
        else:
            amd_phase = "neutral"

        # Track node event timing
        if node_event_recent and minute_counter == 0:
            node_event_minutes_ago = 0
        elif node_event_minutes_ago is not None:
            node_event_minutes_ago += 1
            if node_event_minutes_ago > 60:  # Reset after an hour
                node_event_minutes_ago = None

        # Synthesize signal for this minute
        signal, raw_direction = synthesize_minute(
            current,
            cfg=cfg,
            dir_cfg=dir_cfg,
            micro_feature=micro_feature,
            micro_prev2=micro_prev2,
            micro_prev5=micro_prev5,
            amd_phase=amd_phase,
            moon_profile=moon_profile,
            node_event_recent=node_event_recent,
            node_event_minutes_ago=node_event_minutes_ago,
            previous_confidence=previous_confidence,
            previous_raw_direction=previous_raw_direction,
            last_flip_minutes_ago=last_flip_minutes,
        )

        # Track direction flips
        if last_direction and signal.direction != last_direction:
            if signal.direction != "neutral" and last_direction != "neutral":
                last_flip_minutes = 0
        if last_flip_minutes is not None:
            last_flip_minutes += 1
            if last_flip_minutes > 30:  # Reset after 30 minutes
                last_flip_minutes = None

        signals.append(signal)
        previous_confidence = signal.confidence
        previous_raw_direction = raw_direction
        last_direction = signal.direction

        current += timedelta(minutes=1)
        minute_counter += 1

    return signals


def save_feature_log(
    day_local: date,
    ticker: str,
    signals: list[MinuteSignal],
    output_dir: Path | None = None,
) -> Path:
    """
    Save feature log to JSON (Parquet would require pandas).

    Args:
        day_local: Date of signals
        ticker: Ticker symbol
        signals: List of minute signals
        output_dir: Output directory (defaults to data/signals/{ticker}/)

    Returns:
        Path to saved file
    """
    if output_dir is None:
        output_dir = Path("data/signals") / ticker

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create filename
    filename = output_dir / f"{day_local.isoformat()}.json"

    # Prepare data
    data = {
        "date": day_local.isoformat(),
        "ticker": ticker,
        "signal_count": len(signals),
        "signals": [s.to_dict() for s in signals],
        "metadata": {"generated_at": datetime.now(UTC).isoformat(), "version": "1.0.0"},
    }

    # Write to file
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved feature log to {filename}")
    return filename


def calculate_summary_stats(signals: list[MinuteSignal]) -> dict[str, Any]:
    """
    Calculate summary statistics for a list of signals including directional stats.

    Args:
        signals: List of minute signals

    Returns:
        Dictionary of summary statistics
    """
    if not signals:
        return {
            "total_minutes": 0,
            "p95": 0.0,
            "p75": 0.0,
            "p50": 0.0,
            "mean": 0.0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "max_confidence": 0.0,
            "min_confidence": 0.0,
            "up_minutes": 0,
            "down_minutes": 0,
            "neutral_minutes": 0,
            "mean_direction_score": 0.0,
            "flip_count": 0,
        }

    confidences = [s.confidence for s in signals]
    confidences.sort()

    n = len(confidences)

    # Directional statistics
    up_count = sum(1 for s in signals if s.direction == "up")
    down_count = sum(1 for s in signals if s.direction == "down")
    neutral_count = sum(1 for s in signals if s.direction == "neutral")

    direction_scores = [s.direction_score for s in signals]
    mean_dir_score = (
        sum(direction_scores) / len(direction_scores) if direction_scores else 0.0
    )

    # Count direction flips
    flip_count = 0
    if len(signals) > 1:
        prev_dir = signals[0].direction
        for s in signals[1:]:
            if (
                s.direction != prev_dir
                and s.direction != "neutral"
                and prev_dir != "neutral"
            ):
                flip_count += 1
            prev_dir = s.direction

    return {
        "total_minutes": n,
        "p95": confidences[int(0.95 * n) - 1] if n > 0 else 0.0,
        "p75": confidences[int(0.75 * n) - 1] if n > 0 else 0.0,
        "p50": confidences[int(0.50 * n) - 1] if n > 0 else 0.0,
        "mean": sum(confidences) / n if n > 0 else 0.0,
        "high_count": sum(1 for s in signals if s.strength == "high"),
        "medium_count": sum(1 for s in signals if s.strength == "medium"),
        "low_count": sum(1 for s in signals if s.strength == "low"),
        "max_confidence": max(confidences) if confidences else 0.0,
        "min_confidence": min(confidences) if confidences else 0.0,
        "up_minutes": up_count,
        "down_minutes": down_count,
        "neutral_minutes": neutral_count,
        "mean_direction_score": mean_dir_score,
        "flip_count": flip_count,
    }
