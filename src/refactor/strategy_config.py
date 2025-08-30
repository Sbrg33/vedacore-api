"""
Trading Strategy Configuration
Phase 9: Frozen configuration for signal confidence scoring and rule combinators
"""

from __future__ import annotations

import json
import os

from dataclasses import dataclass
from typing import Any


def _f(name: str, default: float) -> float:
    """Parse float from environment variable with fallback."""
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    """Parse int from environment variable with fallback."""
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default


def _b(name: str, default: bool) -> bool:
    """Parse boolean from environment variable with fallback."""
    val = os.getenv(name)
    return default if val is None else val.lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class StrategyConfig:
    """
    Frozen configuration for Trading Strategy Integration.

    Attributes:
        Weights (sum ≈ 1.0):
            w_micro: Weight for micro-timing volatility windows (default 0.45)
            w_amd: Weight for AMD phase transitions (default 0.35)
            w_moon: Weight for moon factors (default 0.10)
            w_nodes: Weight for node events (default 0.10)

        Thresholds:
            high_threshold: Confidence threshold for high signals (default 0.70)
            med_threshold: Confidence threshold for medium signals (default 0.40)
            ema_alpha: EMA smoothing factor (default 0.30)

        Market Hours (NY time):
            open_hh/open_mm: Market open time (default 09:30)
            close_hh/close_mm: Market close time (default 16:00)

        Limits:
            max_days_range: Maximum days for range queries (default 31)
            cache_day_ttl_s: Cache TTL in seconds (default 24 hours)

        Features:
            enable_rulebook: Enable rule-based confidence boosting (default True)
            enable_smoothing: Enable EMA smoothing (default True)
            enable_market_hours: Only generate signals during market hours (default True)
    """

    # Weights (sum ≈ 1.0)
    w_micro: float = _f("STRAT_W_MICRO", 0.45)
    w_amd: float = _f("STRAT_W_AMD", 0.35)
    w_moon: float = _f("STRAT_W_MOON", 0.10)
    w_nodes: float = _f("STRAT_W_NODES", 0.10)

    # Thresholds and smoothing
    high_threshold: float = _f("STRAT_HIGH_THR", 0.70)
    med_threshold: float = _f("STRAT_MED_THR", 0.40)
    ema_alpha: float = _f("STRAT_EMA_ALPHA", 0.30)  # Smoothing (0..1)

    # Market hours (NY time)
    open_hh: int = _i("STRAT_OPEN_HH", 9)
    open_mm: int = _i("STRAT_OPEN_MM", 30)
    close_hh: int = _i("STRAT_CLOSE_HH", 16)
    close_mm: int = _i("STRAT_CLOSE_MM", 0)

    # Search and caching
    max_days_range: int = _i("STRAT_MAX_DAYS_RANGE", 31)
    cache_day_ttl_s: int = _i("STRAT_CACHE_DAY_TTL_S", 24 * 3600)

    # Feature flags
    enable_rulebook: bool = _b("STRAT_ENABLE_RULEBOOK", True)
    enable_smoothing: bool = _b("STRAT_ENABLE_SMOOTHING", True)
    enable_market_hours: bool = _b("STRAT_ENABLE_MARKET_HOURS", True)

    # Rulebook (loaded separately)
    rulebook: dict[str, Any] = None  # type: ignore

    def __post_init__(self):
        """Validate configuration on initialization."""
        # Validate thresholds
        if not (0 <= self.med_threshold <= self.high_threshold <= 1):
            raise ValueError(
                f"Invalid thresholds: 0 <= med({self.med_threshold}) "
                f"<= high({self.high_threshold}) <= 1"
            )

        # Validate weights sum to approximately 1.0
        weight_sum = self.w_micro + self.w_amd + self.w_moon + self.w_nodes
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(f"Weights should sum to ~1.0, got {weight_sum:.3f}")

        # Validate EMA alpha
        if not (0 < self.ema_alpha <= 1):
            raise ValueError(f"EMA alpha must be in (0, 1], got {self.ema_alpha}")

        # Validate market hours
        if not (0 <= self.open_hh <= 23 and 0 <= self.open_mm <= 59):
            raise ValueError(
                f"Invalid open time: {self.open_hh:02d}:{self.open_mm:02d}"
            )
        if not (0 <= self.close_hh <= 23 and 0 <= self.close_mm <= 59):
            raise ValueError(
                f"Invalid close time: {self.close_hh:02d}:{self.close_mm:02d}"
            )


def default_rulebook() -> dict[str, Any]:
    """
    Simple, auditable default ruleset.

    Each rule has:
        - name: Rule identifier
        - when: List of required tags (all must match)
        - multiplier: Confidence multiplier (>=1 boosts, <1 dampens)

    Returns:
        Default rulebook dictionary
    """
    return {
        "ruleset_id": "default@v1",
        "description": "Default rule set for confidence boosting",
        "rules": [
            {
                "name": "amd_peak_boost",
                "description": "Boost during AMD critical change phase",
                "when": ["AMD=critical_change"],
                "multiplier": 1.15,
            },
            {
                "name": "micro_high_boost",
                "description": "Boost when micro-timing shows high volatility",
                "when": ["micro_high"],
                "multiplier": 1.10,
            },
            {
                "name": "node_flip_boost",
                "description": "Boost during node direction changes",
                "when": ["node_event", "direction_change"],
                "multiplier": 1.12,
            },
            {
                "name": "eclipse_window_boost",
                "description": "Boost during eclipse windows",
                "when": ["eclipse"],
                "multiplier": 1.08,
            },
            {
                "name": "moon_perigee_boost",
                "description": "Boost when moon is at perigee",
                "when": ["moon_perigee"],
                "multiplier": 1.06,
            },
            {
                "name": "combined_critical",
                "description": "Major boost when multiple critical factors align",
                "when": ["AMD=critical_change", "micro_high", "node_event"],
                "multiplier": 1.25,
            },
        ],
    }


def load_strategy_config() -> StrategyConfig:
    """
    Load strategy configuration with rulebook.

    Checks for STRAT_RULEBOOK_JSON environment variable for custom rules,
    otherwise uses default rulebook.

    Returns:
        Configured StrategyConfig instance
    """
    # Create base config
    base_config = StrategyConfig()

    # Load rulebook
    rulebook_json = os.getenv("STRAT_RULEBOOK_JSON")
    if rulebook_json:
        try:
            rulebook = json.loads(rulebook_json)
        except json.JSONDecodeError:
            rulebook = default_rulebook()
    else:
        rulebook = default_rulebook()

    # Create new config with rulebook
    # Since dataclass is frozen, we need to create a new instance
    config_dict = {
        "w_micro": base_config.w_micro,
        "w_amd": base_config.w_amd,
        "w_moon": base_config.w_moon,
        "w_nodes": base_config.w_nodes,
        "high_threshold": base_config.high_threshold,
        "med_threshold": base_config.med_threshold,
        "ema_alpha": base_config.ema_alpha,
        "open_hh": base_config.open_hh,
        "open_mm": base_config.open_mm,
        "close_hh": base_config.close_hh,
        "close_mm": base_config.close_mm,
        "max_days_range": base_config.max_days_range,
        "cache_day_ttl_s": base_config.cache_day_ttl_s,
        "enable_rulebook": base_config.enable_rulebook,
        "enable_smoothing": base_config.enable_smoothing,
        "enable_market_hours": base_config.enable_market_hours,
        "rulebook": rulebook,
    }

    return StrategyConfig(**config_dict)


# Module-level singleton instance
_config: StrategyConfig | None = None


def get_strategy_config() -> StrategyConfig:
    """Get the singleton strategy configuration instance."""
    global _config
    if _config is None:
        _config = load_strategy_config()
    return _config


def initialize_strategy_config(config: StrategyConfig | None = None) -> StrategyConfig:
    """
    Initialize or replace the strategy configuration.

    Args:
        config: Optional StrategyConfig instance. If None, loads default.

    Returns:
        The initialized configuration

    Raises:
        RuntimeError: If configuration already initialized (frozen pattern)
    """
    global _config
    if _config is not None:
        raise RuntimeError("Strategy configuration already initialized")
    _config = config or load_strategy_config()
    return _config
