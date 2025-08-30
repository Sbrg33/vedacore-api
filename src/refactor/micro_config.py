"""
Market Micro-Timing Configuration
Phase 8: Frozen configuration for volatility window generation
"""

from __future__ import annotations

import os

from dataclasses import dataclass


def _f(name: str, default: float) -> float:
    """Parse float from environment variable with fallback."""
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


def _b(name: str, default: bool) -> bool:
    """Parse boolean from environment variable with fallback."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class MicroConfig:
    """
    Frozen configuration for Market Micro-Timing Engine.

    Attributes:
        Scoring Weights (sum to ~1.0):
            w_moon_velocity: Weight for moon velocity deviation (default 0.30)
            w_node_events: Weight for node events (default 0.20)
            w_eclipse: Weight for eclipse proximity (default 0.30)
            w_dasha: Weight for dasha changeovers (default 0.20)

        Window Durations:
            win_moon_anomaly_min: Minutes around moon anomalies (default 15)
            win_node_event_min: Minutes around node events (default 20)
            win_eclipse_hours: Hours around eclipse peak (default 72)
            win_dasha_min: Minutes around dasha changes (default 15)

        Thresholds:
            high_threshold: Score threshold for high volatility (default 0.70)
            med_threshold: Score threshold for medium volatility (default 0.40)

        Performance/Safety:
            max_days_range: Maximum days for range queries (default 31)
            cache_day_ttl_s: Cache TTL in seconds (default 24 hours)

        Feature Flags:
            enable_eclipse: Enable eclipse factor (default True)
            enable_dasha: Enable dasha factor (default True)
            enable_nodes: Enable node factor (default True)
            enable_moon: Enable moon factor (default True)
    """

    # Scoring weights (sum ~1.0)
    w_moon_velocity: float = _f("MICRO_W_MOON_VELOCITY", 0.30)
    w_node_events: float = _f("MICRO_W_NODE_EVENTS", 0.20)
    w_eclipse: float = _f("MICRO_W_ECLIPSE", 0.30)
    w_dasha: float = _f("MICRO_W_DASHA", 0.20)

    # Window durations (minutes except eclipse)
    win_moon_anomaly_min: int = int(_f("MICRO_WIN_MOON_ANOMALY_MIN", 15))
    win_node_event_min: int = int(_f("MICRO_WIN_NODE_EVENT_MIN", 20))
    win_eclipse_hours: int = int(_f("MICRO_WIN_ECLIPSE_HOURS", 72))  # 3 days
    win_dasha_min: int = int(_f("MICRO_WIN_DASHA_MIN", 15))

    # Volatility thresholds
    high_threshold: float = _f("MICRO_HIGH_THRESHOLD", 0.70)
    med_threshold: float = _f("MICRO_MED_THRESHOLD", 0.40)

    # Performance and safety limits
    max_days_range: int = int(_f("MICRO_MAX_DAYS_RANGE", 31))
    cache_day_ttl_s: int = int(_f("MICRO_CACHE_DAY_TTL_S", 24 * 3600))

    # Feature flags
    enable_eclipse: bool = _b("MICRO_ENABLE_ECLIPSE", True)
    enable_dasha: bool = _b("MICRO_ENABLE_DASHA", True)
    enable_nodes: bool = _b("MICRO_ENABLE_NODES", True)
    enable_moon: bool = _b("MICRO_ENABLE_MOON", True)

    def __post_init__(self):
        """Validate configuration on initialization."""
        # Validate thresholds
        if not (0 <= self.med_threshold <= self.high_threshold <= 1):
            raise ValueError(
                f"Invalid thresholds: 0 <= med({self.med_threshold}) "
                f"<= high({self.high_threshold}) <= 1"
            )

        # Validate weights sum to approximately 1.0
        weight_sum = (
            self.w_moon_velocity + self.w_node_events + self.w_eclipse + self.w_dasha
        )
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(f"Weights should sum to ~1.0, got {weight_sum:.3f}")

        # Validate window durations
        if any(
            x <= 0
            for x in [
                self.win_moon_anomaly_min,
                self.win_node_event_min,
                self.win_eclipse_hours,
                self.win_dasha_min,
            ]
        ):
            raise ValueError("All window durations must be positive")

        # Validate max days range
        if not (1 <= self.max_days_range <= 365):
            raise ValueError(f"max_days_range must be 1-365, got {self.max_days_range}")


# Module-level singleton instance
_config: MicroConfig | None = None


def get_micro_config() -> MicroConfig:
    """Get the singleton micro configuration instance."""
    global _config
    if _config is None:
        _config = MicroConfig()
    return _config


def initialize_micro_config(config: MicroConfig | None = None) -> MicroConfig:
    """
    Initialize or replace the micro configuration.

    Args:
        config: Optional MicroConfig instance. If None, creates default.

    Returns:
        The initialized configuration

    Raises:
        RuntimeError: If configuration already initialized (frozen pattern)
    """
    global _config
    if _config is not None:
        raise RuntimeError("Micro configuration already initialized")
    _config = config or MicroConfig()
    return _config
