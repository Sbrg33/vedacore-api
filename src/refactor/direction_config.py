"""
Direction Configuration for Phase 10
Frozen configuration for directional bias modeling with env overrides
"""

from __future__ import annotations

import json
import os

from dataclasses import dataclass
from typing import Any


def _f(name: str, default: float) -> float:
    """Parse float from environment variable."""
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    """Parse int from environment variable."""
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _b(name: str, default: bool) -> bool:
    """Parse bool from environment variable."""
    v = os.getenv(name)
    return default if v is None else v.lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class DirectionConfig:
    """
    Frozen configuration for directional bias modeling.

    Weights control the influence of each factor on direction.
    Thresholds and bands determine when to label as up/down vs neutral.
    """

    # Feature weights for direction (signed contributions)
    w_amd_dir: float = _f("DIR_W_AMD", 0.35)
    w_micro_dir: float = _f("DIR_W_MICRO", 0.45)
    w_moon_dir: float = _f("DIR_W_MOON", 0.10)
    w_nodes_dir: float = _f("DIR_W_NODES", 0.10)
    w_dasha_dir: float = _f("DIR_W_DASHA", 0.00)  # Disabled by default

    # Gating and smoothing parameters
    min_conf_for_direction: float = _f("DIR_MIN_CONF", 0.25)  # Below this → neutral
    neutral_band: float = _f("DIR_NEUTRAL_BAND", 0.15)  # Small |score| → neutral
    ema_alpha_dir: float = _f("DIR_EMA_ALPHA", 0.30)  # EMA smoothing factor

    # Node event cooldown (minutes after flip)
    node_cooldown_min: int = _i("DIR_NODE_COOLDOWN_MIN", 5)

    # Feature toggles
    enable_moon_reversion: bool = _b("DIR_ENABLE_MOON_REVERSION", True)
    enable_dasha_bias: bool = _b("DIR_ENABLE_DASHA_BIAS", False)
    enable_rulebook: bool = _b("DIR_ENABLE_RULEBOOK", True)
    enable_market_hours_only: bool = _b("DIR_MARKET_HOURS_ONLY", True)

    # Flip prevention
    min_minutes_between_flips: int = _i("DIR_MIN_FLIP_MINUTES", 3)

    # Optional rulebook JSON (can override via env)
    rulebook_json: str | None = os.getenv("DIR_RULEBOOK_JSON")

    @property
    def rulebook(self) -> dict[str, Any] | None:
        """Parse rulebook JSON if provided."""
        if not self.rulebook_json:
            # Default rulebook with directional rules
            return {
                "ruleset_id": "direction_v1",
                "rules": [
                    {
                        "name": "strong_micro_up",
                        "when": ["micro_high", "micro_rising"],
                        "direction_boost": 0.20,
                    },
                    {
                        "name": "strong_micro_down",
                        "when": ["micro_high", "micro_falling"],
                        "direction_boost": -0.20,
                    },
                    {
                        "name": "amd_critical_up",
                        "when": ["AMD=critical_change", "micro_rising"],
                        "direction_boost": 0.25,
                    },
                    {
                        "name": "amd_critical_down",
                        "when": ["AMD=critical_change", "micro_falling"],
                        "direction_boost": -0.25,
                    },
                    {
                        "name": "moon_reversal_signal",
                        "when": ["moon_perigee", "moon_fast"],
                        "direction_boost": -0.15,  # Mean reversion
                    },
                    {
                        "name": "node_dampener",
                        "when": ["node_event"],
                        "direction_multiplier": 0.5,  # Reduce directional confidence
                    },
                ],
            }

        try:
            return json.loads(self.rulebook_json)
        except Exception:
            return None

    def validate(self) -> bool:
        """Validate configuration consistency."""
        # Check weights sum approximately to 1.0 (allow some variance)
        weight_sum = (
            self.w_amd_dir
            + self.w_micro_dir
            + self.w_moon_dir
            + self.w_nodes_dir
            + self.w_dasha_dir
        )
        if not (0.9 <= weight_sum <= 1.1):
            return False

        # Check reasonable ranges
        if not (0.0 <= self.min_conf_for_direction <= 1.0):
            return False
        if not (0.0 <= self.neutral_band <= 0.5):
            return False
        if not (0.0 <= self.ema_alpha_dir <= 1.0):
            return False

        return True


# Global singleton instance
_CONFIG: DirectionConfig | None = None


def get_direction_config() -> DirectionConfig:
    """Get or create the global direction configuration."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = DirectionConfig()
        if not _CONFIG.validate():
            raise ValueError("Invalid direction configuration")
    return _CONFIG


def initialize_direction_config() -> None:
    """Initialize and validate direction configuration at startup."""
    config = get_direction_config()
    if config.validate():
        print(
            f"Direction config initialized: weights={config.w_micro_dir:.2f}/{config.w_amd_dir:.2f}"
        )
    else:
        raise ValueError("Direction configuration validation failed")
