#!/usr/bin/env python3
"""
Eclipse Configuration - Frozen at startup for determinism
Phase 6: Eclipse Prediction Module

This module defines immutable configuration for eclipse calculations,
following the same pattern as house_config.py and nodes_config.py.
"""

import os

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EclipseConfig:
    """
    Immutable configuration for eclipse calculations.
    Frozen at startup to ensure deterministic behavior.
    """

    # Search parameters
    search_step_days: float = 1.0  # Coarse step for long-range searches
    refinement_step_hours: float = 0.1  # Fine step for precise timing

    # Path calculation
    path_sampling_km: int = 50  # Resolution along central path
    path_points_max: int = 500  # Maximum points in path polyline
    local_grid_km: int | None = None  # Optional grid for visibility heatmaps

    # API limits
    max_span_years: int = 5  # Maximum range for event searches
    max_events_per_query: int = 100  # Limit results per API call

    # Features
    enable_diagnostics: bool = False  # Node proximity, elongation overlays
    enable_saros: bool = True  # Include Saros series if available
    enable_gamma: bool = True  # Include gamma parameter
    enable_delta_t: bool = False  # Include ΔT corrections

    # Cache settings
    cache_ttl_events_days: int = 365  # Long-lived cache for sparse events
    cache_ttl_visibility_hours: int = 24  # Shorter cache for visibility queries
    cache_ttl_path_days: int = 30  # Path data cache duration

    # Tolerances
    magnitude_tolerance: float = 0.005  # For fixture validation
    time_tolerance_seconds: int = 60  # For fixture validation

    # Swiss Ephemeris settings
    use_true_node: bool = True  # Use True Node (consistent with KP)
    ephemeris_path: str = "./swisseph/ephe"

    # Safety limits
    min_year: int = 1900  # Earliest supported year
    max_year: int = 2100  # Latest supported year

    # Additional metadata
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.search_step_days <= 0:
            raise ValueError("search_step_days must be positive")
        if self.max_span_years <= 0:
            raise ValueError("max_span_years must be positive")
        if self.path_sampling_km <= 0:
            raise ValueError("path_sampling_km must be positive")
        if self.magnitude_tolerance <= 0:
            raise ValueError("magnitude_tolerance must be positive")
        if self.min_year >= self.max_year:
            raise ValueError("min_year must be less than max_year")


# Global configuration instance (set once at startup)
_CONFIG: EclipseConfig | None = None
_CONFIG_LOCKED = False


def set_eclipse_config(config: EclipseConfig) -> None:
    """
    Set the global eclipse configuration.
    Can only be called once at startup.

    Args:
        config: EclipseConfig instance to use globally

    Raises:
        RuntimeError: If configuration is already locked
    """
    global _CONFIG, _CONFIG_LOCKED

    if _CONFIG_LOCKED:
        raise RuntimeError(
            "Eclipse configuration is locked. "
            "Configuration can only be set once at startup."
        )

    _CONFIG = config
    _CONFIG_LOCKED = True


def get_eclipse_config() -> EclipseConfig:
    """
    Get the global eclipse configuration.

    Returns:
        The global EclipseConfig instance

    Raises:
        RuntimeError: If configuration not yet set
    """
    if _CONFIG is None:
        # Auto-initialize with defaults if not set
        set_eclipse_config(EclipseConfig())

    # After initialization, _CONFIG is guaranteed to be not None
    assert _CONFIG is not None
    return _CONFIG


def reset_config_for_testing() -> None:
    """
    Reset configuration state for testing only.
    This should NEVER be called in production code.
    """
    global _CONFIG, _CONFIG_LOCKED

    if os.getenv("PYTEST_CURRENT_TEST") is None:
        raise RuntimeError("reset_config_for_testing() can only be called during tests")

    _CONFIG = None
    _CONFIG_LOCKED = False


# Environment-based configuration overrides
def create_config_from_env() -> EclipseConfig:
    """
    Create configuration from environment variables.
    Useful for deployment configuration.

    Environment variables:
        ECLIPSE_SEARCH_STEP_DAYS: Search step in days
        ECLIPSE_PATH_SAMPLING_KM: Path sampling resolution
        ECLIPSE_MAX_SPAN_YEARS: Maximum search span
        ECLIPSE_ENABLE_DIAGNOSTICS: Enable diagnostic features
        ECLIPSE_CACHE_TTL_DAYS: Cache TTL for events
        ECLIPSE_EPHEMERIS_PATH: Path to Swiss Ephemeris files
    """
    return EclipseConfig(
        search_step_days=float(os.getenv("ECLIPSE_SEARCH_STEP_DAYS", "1.0")),
        path_sampling_km=int(os.getenv("ECLIPSE_PATH_SAMPLING_KM", "50")),
        max_span_years=int(os.getenv("ECLIPSE_MAX_SPAN_YEARS", "5")),
        enable_diagnostics=os.getenv("ECLIPSE_ENABLE_DIAGNOSTICS", "").lower()
        == "true",
        cache_ttl_events_days=int(os.getenv("ECLIPSE_CACHE_TTL_DAYS", "365")),
        ephemeris_path=os.getenv("ECLIPSE_EPHEMERIS_PATH", "./swisseph/ephe"),
    )


# Default configuration for reference
DEFAULT_CONFIG = EclipseConfig()


# Configuration presets for different use cases
PRESETS = {
    "production": EclipseConfig(
        search_step_days=1.0,
        path_sampling_km=50,
        max_span_years=5,
        enable_diagnostics=False,
        cache_ttl_events_days=365,
    ),
    "research": EclipseConfig(
        search_step_days=0.5,
        path_sampling_km=25,
        max_span_years=10,
        enable_diagnostics=True,
        enable_delta_t=True,
        cache_ttl_events_days=30,
    ),
    "testing": EclipseConfig(
        search_step_days=2.0,
        path_sampling_km=100,
        max_span_years=1,
        enable_diagnostics=False,
        cache_ttl_events_days=1,
    ),
}


def use_preset(preset_name: str) -> None:
    """
    Use a predefined configuration preset.

    Args:
        preset_name: Name of preset ("production", "research", "testing")

    Raises:
        ValueError: If preset name not recognized
        RuntimeError: If configuration already locked
    """
    if preset_name not in PRESETS:
        raise ValueError(
            f"Unknown preset: {preset_name}. "
            f"Available presets: {list(PRESETS.keys())}"
        )

    set_eclipse_config(PRESETS[preset_name])
