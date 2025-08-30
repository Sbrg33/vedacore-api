"""
Direction Engine for Phase 10
Computes directional bias (up/down/neutral) from astrological factors
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from .direction_config import DirectionConfig, get_direction_config

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")
NY_TZ = ZoneInfo("America/New_York")
Direction = Literal["up", "down", "neutral"]


@dataclass(frozen=True)
class DirectionSignal:
    """
    Directional bias signal for a specific timestamp.

    Attributes:
        t: Timestamp (UTC)
        direction: Categorical direction (up/down/neutral)
        direction_score: Magnitude of directional bias (0.0 to 1.0)
        dir_factors: Breakdown of signed contributions
        rules_applied: List of directional rules that were triggered
    """

    t: datetime
    direction: Direction
    direction_score: float
    dir_factors: dict[str, float]
    rules_applied: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "t": self.t.isoformat(),
            "direction": self.direction,
            "direction_score": round(self.direction_score, 4),
            "dir_factors": {k: round(v, 4) for k, v in self.dir_factors.items()},
            "rules_applied": self.rules_applied,
        }


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clip value to range."""
    return max(lo, min(hi, x))


def _ema(prev: float, now: float, alpha: float) -> float:
    """Exponential moving average."""
    return alpha * now + (1 - alpha) * prev


def _sign(x: float) -> int:
    """Get sign of value."""
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _micro_slope(
    micro_now: float | None,
    micro_prev2: float | None,
    micro_prev5: float | None = None,
) -> tuple[float, str]:
    """
    Calculate micro-timing slope across recent minutes.

    Returns:
        Tuple of (slope value, trend label)
    """
    if micro_now is None or micro_prev2 is None:
        return 0.0, "flat"

    # Primary slope: 2-minute change
    slope_2m = (micro_now - micro_prev2) / 0.3  # Scale to [-1, 1]
    slope_2m = _clip(slope_2m, -1.0, 1.0)

    # Optional 5-minute slope for trend confirmation
    if micro_prev5 is not None:
        slope_5m = (micro_now - micro_prev5) / 0.5
        slope_5m = _clip(slope_5m, -1.0, 1.0)
        # Weight recent change more
        slope = 0.7 * slope_2m + 0.3 * slope_5m
    else:
        slope = slope_2m

    # Categorize trend
    if slope > 0.1:
        trend = "rising"
    elif slope < -0.1:
        trend = "falling"
    else:
        trend = "flat"

    return slope, trend


def _amd_directional_weight(phase: str | None, slope_sign: int) -> float:
    """
    Get AMD contribution with directional bias.

    AMD phase indicates volatility potential, slope gives direction.
    """
    base_weights = {
        "critical_change": 1.0,
        "pre_change": 0.7,
        "confirmation": 0.5,
        "volatility_build": 0.4,
        "consolidation": 0.3,
        "neutral": 0.2,
    }

    weight = base_weights.get(phase, 0.2) if phase else 0.2

    # Apply directional sign based on micro slope
    return weight * slope_sign


def _moon_reversion_bias(
    moon_profile: dict[str, Any] | None, recent_direction: int
) -> float:
    """
    Calculate moon-based mean reversion bias.

    Fast moon near perigee suggests reversal potential.
    """
    if not moon_profile:
        return 0.0

    velocity_index = float(moon_profile.get("velocity_index", 1.0))
    distance_index = float(moon_profile.get("distance_index", 0.5))

    # Fast moon (velocity > 1.15) near perigee (distance < 0.2)
    # suggests mean reversion
    velocity_deviation = abs(velocity_index - 1.0)
    proximity_factor = 1.0 - distance_index  # Closer = higher

    # Reversion strength
    reversion_mag = min(velocity_deviation / 0.2, 1.0) * proximity_factor

    # Apply opposite to recent direction
    return -recent_direction * reversion_mag * 0.5  # Scale down


def _node_cooldown_factor(
    node_event_minutes_ago: int | None, cooldown_period: int
) -> float:
    """
    Calculate dampening factor for recent node events.

    Returns multiplier [0, 1] where 0 = full dampening, 1 = no effect.
    """
    if node_event_minutes_ago is None:
        return 1.0

    if node_event_minutes_ago >= cooldown_period:
        return 1.0

    # Linear decay from 0.3 to 1.0 over cooldown period
    return 0.3 + 0.7 * (node_event_minutes_ago / cooldown_period)


def _apply_direction_rules(
    raw_score: float, tags: list[str], cfg: DirectionConfig
) -> tuple[float, list[str]]:
    """
    Apply rulebook to modify directional score.

    Returns:
        Tuple of (modified score, list of applied rules)
    """
    if not cfg.enable_rulebook or not cfg.rulebook:
        return raw_score, []

    applied_rules = []

    for rule in cfg.rulebook.get("rules", []):
        required_tags = rule.get("when", [])

        # Check if all required tags are present
        if all(tag in tags for tag in required_tags):
            # Apply directional boost (additive)
            if "direction_boost" in rule:
                boost = float(rule["direction_boost"])
                raw_score += boost
                applied_rules.append(rule.get("name", "unnamed"))

            # Apply multiplier (multiplicative)
            if "direction_multiplier" in rule:
                mult = float(rule["direction_multiplier"])
                raw_score *= mult
                applied_rules.append(rule.get("name", "unnamed"))

    return raw_score, applied_rules


def compute_direction_raw(
    *,
    t: datetime,
    cfg: DirectionConfig,
    confidence: float,
    micro_now: float | None,
    micro_prev2: float | None,
    micro_prev5: float | None = None,
    amd_phase: str | None = None,
    moon_profile: dict[str, Any] | None = None,
    node_event_minutes_ago: int | None = None,
    tags: list[str] = None,
    prev_raw: float | None = None,
) -> tuple[float, dict[str, float], list[str]]:
    """
    Compute raw directional score and factor breakdown.

    Returns:
        Tuple of (raw score, factor dict, applied rules)
        Positive score = up bias, negative = down bias
    """
    parts: dict[str, float] = {}
    tags = tags or []

    # 1. Micro slope (primary directional signal)
    slope, trend = _micro_slope(micro_now, micro_prev2, micro_prev5)
    parts["micro_slope"] = slope * cfg.w_micro_dir

    # Add trend tags
    if trend == "rising":
        tags.append("micro_rising")
    elif trend == "falling":
        tags.append("micro_falling")

    # 2. AMD phase contribution (magnitude with slope-based direction)
    amd_contrib = _amd_directional_weight(amd_phase, _sign(slope))
    parts["amd_phase"] = amd_contrib * cfg.w_amd_dir

    # 3. Moon reversion (optional)
    if cfg.enable_moon_reversion and moon_profile:
        moon_rev = _moon_reversion_bias(moon_profile, _sign(slope))
        parts["moon_reversion"] = moon_rev * cfg.w_moon_dir
    else:
        parts["moon_reversion"] = 0.0

    # 4. Node cooldown (dampening)
    node_damp = _node_cooldown_factor(node_event_minutes_ago, cfg.node_cooldown_min)
    if node_damp < 1.0:
        # Apply dampening to all components
        for key in parts:
            parts[key] *= node_damp
        parts["node_dampening"] = (1.0 - node_damp) * cfg.w_nodes_dir

    # Sum raw contributions
    raw = sum(parts.values())

    # 5. Apply confidence gate
    if confidence < cfg.min_conf_for_direction:
        raw *= 0.2  # Heavy dampening for low confidence
        parts["confidence_gate"] = -0.8 * abs(raw)

    # 6. Apply directional rules
    raw, rules_applied = _apply_direction_rules(raw, tags, cfg)

    # 7. EMA smoothing
    if prev_raw is not None:
        raw = _ema(prev_raw, raw, cfg.ema_alpha_dir)

    return raw, parts, rules_applied


def label_direction(raw: float, cfg: DirectionConfig) -> Direction:
    """
    Convert raw score to categorical direction.
    """
    if abs(raw) < cfg.neutral_band:
        return "neutral"
    return "up" if raw > 0 else "down"


def compute_direction(
    t: datetime,
    *,
    confidence: float,
    micro_now: float | None = None,
    micro_prev2: float | None = None,
    micro_prev5: float | None = None,
    amd_phase: str | None = None,
    moon_profile: dict[str, Any] | None = None,
    node_event_minutes_ago: int | None = None,
    tags: list[str] | None = None,
    prev_raw: float | None = None,
    last_flip_minutes_ago: int | None = None,
    cfg: DirectionConfig | None = None,
) -> tuple[DirectionSignal, float]:
    """
    Compute directional signal for a specific timestamp.

    Returns:
        Tuple of (DirectionSignal, raw_score for next iteration)
    """
    cfg = cfg or get_direction_config()

    # Check flip prevention
    if (
        last_flip_minutes_ago is not None
        and last_flip_minutes_ago < cfg.min_minutes_between_flips
    ):
        # Prevent rapid flips by maintaining previous direction
        if prev_raw is not None:
            raw = prev_raw * 0.95  # Slight decay
            parts = {"flip_prevention": raw}
            rules_applied = ["flip_prevention"]
        else:
            raw, parts, rules_applied = compute_direction_raw(
                t=t,
                cfg=cfg,
                confidence=confidence,
                micro_now=micro_now,
                micro_prev2=micro_prev2,
                micro_prev5=micro_prev5,
                amd_phase=amd_phase,
                moon_profile=moon_profile,
                node_event_minutes_ago=node_event_minutes_ago,
                tags=tags,
                prev_raw=prev_raw,
            )
    else:
        raw, parts, rules_applied = compute_direction_raw(
            t=t,
            cfg=cfg,
            confidence=confidence,
            micro_now=micro_now,
            micro_prev2=micro_prev2,
            micro_prev5=micro_prev5,
            amd_phase=amd_phase,
            moon_profile=moon_profile,
            node_event_minutes_ago=node_event_minutes_ago,
            tags=tags,
            prev_raw=prev_raw,
        )

    # Convert to bounded score using sigmoid-like function
    score = _clip(abs(raw) / (1.0 + abs(raw)))

    # Determine direction label
    direction = label_direction(raw, cfg)

    signal = DirectionSignal(
        t=t,
        direction=direction,
        direction_score=score,
        dir_factors=parts,
        rules_applied=rules_applied,
    )

    return signal, raw


def calculate_direction_stats(signals: list[DirectionSignal]) -> dict[str, Any]:
    """
    Calculate summary statistics for directional signals.
    """
    if not signals:
        return {
            "up_minutes": 0,
            "down_minutes": 0,
            "neutral_minutes": 0,
            "mean_direction_score": 0.0,
            "max_direction_score": 0.0,
            "flip_count": 0,
        }

    up_count = sum(1 for s in signals if s.direction == "up")
    down_count = sum(1 for s in signals if s.direction == "down")
    neutral_count = sum(1 for s in signals if s.direction == "neutral")

    scores = [s.direction_score for s in signals]

    # Count direction flips
    flip_count = 0
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
        "up_minutes": up_count,
        "down_minutes": down_count,
        "neutral_minutes": neutral_count,
        "mean_direction_score": sum(scores) / len(scores) if scores else 0.0,
        "max_direction_score": max(scores) if scores else 0.0,
        "flip_count": flip_count,
        "direction_ratio": up_count / down_count if down_count > 0 else float("inf"),
    }
