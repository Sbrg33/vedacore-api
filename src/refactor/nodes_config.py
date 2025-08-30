#!/usr/bin/env python3
"""
Node Configuration Module - Thresholds and Feature Flags for Rahu/Ketu Detection.
Configuration is frozen at startup to ensure determinism.
"""

import logging

from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeConfig:
    """Immutable configuration for node calculations"""

    # Speed thresholds (degrees per day)
    speed_threshold: float = 0.005  # Below this = stationary
    speed_hysteresis: float = 0.0005  # Exit threshold = speed_threshold + hysteresis

    # Scanning parameters
    scan_step_seconds: int = 60  # Coarse scan stride
    bisection_max_iters: int = 24  # Max iterations for refinement
    bisection_tolerance_seconds: float = 0.5  # Target precision

    # Feature flags
    enable_wobble_detection: bool = False  # Wobble/perturbation peaks
    enable_diagnostics: bool = False  # Solar elongation, proximity bands
    enable_hysteresis: bool = True  # Use hysteresis for stationary exit

    # Wobble detection parameters (if enabled)
    wobble_window_hours: int = 24  # Look ±N hours around events
    wobble_min_amplitude: float = 0.01  # Minimum amplitude to report

    # Diagnostic parameters (if enabled)
    proximity_bands: tuple = (5.0, 10.0, 15.0)  # Degrees for proximity analysis

    # Cache settings
    cache_ttl_seconds: int = 86400  # 1 day for event cache
    live_ttl_seconds: int = 5  # 5 seconds for "now" endpoint

    # Metric labels
    metric_system: str = "KP_NODES"
    metric_features: dict[str, str] = field(
        default_factory=lambda: {
            "stationary": "enabled",
            "direction": "enabled",
            "wobble": "disabled",
            "diagnostics": "disabled",
        }
    )

    def __post_init__(self):
        """Update metric features based on flags"""
        # This won't work with frozen=True, so we handle it differently
        pass

    def get_exit_threshold(self) -> float:
        """Get stationary exit threshold with hysteresis"""
        if self.enable_hysteresis:
            return self.speed_threshold + self.speed_hysteresis
        return self.speed_threshold

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "speed_threshold": self.speed_threshold,
            "speed_hysteresis": self.speed_hysteresis,
            "exit_threshold": self.get_exit_threshold(),
            "scan_step_seconds": self.scan_step_seconds,
            "bisection_max_iters": self.bisection_max_iters,
            "bisection_tolerance_seconds": self.bisection_tolerance_seconds,
            "enable_wobble_detection": self.enable_wobble_detection,
            "enable_diagnostics": self.enable_diagnostics,
            "enable_hysteresis": self.enable_hysteresis,
            "wobble_window_hours": self.wobble_window_hours,
            "wobble_min_amplitude": self.wobble_min_amplitude,
            "proximity_bands": list(self.proximity_bands),
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "live_ttl_seconds": self.live_ttl_seconds,
            "metric_system": self.metric_system,
        }


# Global configuration instance (frozen at startup)
_config: NodeConfig | None = None
_initialized: bool = False


def initialize_node_config(
    speed_threshold: float = 0.005,
    enable_wobble: bool = False,
    enable_diagnostics: bool = False,
    **kwargs,
) -> NodeConfig:
    """
    Initialize node configuration. Can only be called once.

    Args:
        speed_threshold: Stationary speed threshold in degrees/day
        enable_wobble: Enable wobble/perturbation detection
        enable_diagnostics: Enable solar elongation and proximity diagnostics
        **kwargs: Additional config parameters

    Returns:
        Frozen NodeConfig instance

    Raises:
        RuntimeError: If already initialized
    """
    global _config, _initialized

    if _initialized:
        raise RuntimeError("Node configuration already initialized")

    # Build config with provided parameters
    config_params = {
        "speed_threshold": speed_threshold,
        "enable_wobble_detection": enable_wobble,
        "enable_diagnostics": enable_diagnostics,
    }

    # Add any additional kwargs
    for key, value in kwargs.items():
        if hasattr(NodeConfig, key):
            config_params[key] = value

    _config = NodeConfig(**config_params)
    _initialized = True

    # Update metric features based on flags
    features = {
        "stationary": "enabled",
        "direction": "enabled",
        "wobble": "enabled" if _config.enable_wobble_detection else "disabled",
        "diagnostics": "enabled" if _config.enable_diagnostics else "disabled",
    }

    logger.info(f"Node configuration initialized: {_config.to_dict()}")
    logger.info(f"Features: {features}")

    return _config


def get_node_config() -> NodeConfig:
    """
    Get the current node configuration.

    Returns:
        Current NodeConfig instance

    Raises:
        RuntimeError: If not initialized
    """
    global _config

    if _config is None:
        # Auto-initialize with defaults if not done
        logger.warning("Node config not initialized, using defaults")
        return initialize_node_config()

    return _config


def is_initialized() -> bool:
    """Check if node configuration has been initialized"""
    return _initialized


def reset_config():
    """Reset configuration (for testing only)"""
    global _config, _initialized
    if _initialized:
        logger.warning("Resetting node configuration (testing only)")
    _config = None
    _initialized = False
