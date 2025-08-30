#!/usr/bin/env python3
"""
Moon Factors Configuration - Phase 7
Frozen configuration for lunar calculations
"""

import logging
import os

from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MoonConfig:
    """Configuration for moon factor calculations."""

    # Speed thresholds
    mean_speed: float = 13.176  # Mean Moon speed in degrees/day
    fast_speed_threshold: float = 14.5  # Fast moon threshold
    slow_speed_threshold: float = 11.8  # Slow moon threshold

    # Latitude thresholds
    max_latitude: float = 5.145  # Maximum lunar latitude in degrees

    # Distance thresholds (in AU)
    mean_distance: float = 0.00257  # Mean Earth-Moon distance in AU
    perigee_distance: float = 0.00238  # Typical perigee distance
    apogee_distance: float = 0.00268  # Typical apogee distance

    # Event detection
    perigee_threshold: float = 0.00245  # Distance threshold for perigee
    apogee_threshold: float = 0.00265  # Distance threshold for apogee
    standstill_threshold: float = 0.01  # Declination change threshold

    # Search parameters
    event_search_step_hours: int = 6  # Step size for event search
    event_refinement_tolerance: float = 0.001  # Refinement tolerance
    max_search_days: int = 365  # Maximum search span

    # Cache settings
    cache_ttl_profile_days: int = 30  # TTL for daily profiles
    cache_ttl_events_days: int = 90  # TTL for event caches

    # Quality thresholds
    strong_moon_speed: float = 13.5  # Speed for strong moon
    weak_moon_speed: float = 12.5  # Speed for weak moon

    # Tolerances
    speed_tolerance: float = 0.001  # Tolerance for speed comparisons
    distance_tolerance: float = 0.00001  # Tolerance for distance
    time_tolerance_seconds: int = 60  # Time tolerance for events

    @classmethod
    def from_env(cls, prefix: str = "MOON_") -> "MoonConfig":
        """Create config from environment variables."""
        kwargs = {}

        # Map environment variables to config fields
        env_mapping = {
            f"{prefix}MEAN_SPEED": ("mean_speed", float),
            f"{prefix}FAST_THRESHOLD": ("fast_speed_threshold", float),
            f"{prefix}SLOW_THRESHOLD": ("slow_speed_threshold", float),
            f"{prefix}MAX_LATITUDE": ("max_latitude", float),
            f"{prefix}MEAN_DISTANCE": ("mean_distance", float),
            f"{prefix}PERIGEE_DISTANCE": ("perigee_distance", float),
            f"{prefix}APOGEE_DISTANCE": ("apogee_distance", float),
            f"{prefix}EVENT_SEARCH_HOURS": ("event_search_step_hours", int),
            f"{prefix}MAX_SEARCH_DAYS": ("max_search_days", int),
            f"{prefix}CACHE_PROFILE_DAYS": ("cache_ttl_profile_days", int),
            f"{prefix}CACHE_EVENTS_DAYS": ("cache_ttl_events_days", int),
        }

        for env_var, (field_name, field_type) in env_mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                try:
                    kwargs[field_name] = field_type(value)
                    logger.info(
                        f"Set {field_name} = {kwargs[field_name]} from {env_var}"
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid value for {env_var}: {value} - {e}")

        return cls(**kwargs)

    @classmethod
    def production(cls) -> "MoonConfig":
        """Production configuration."""
        return cls()  # Use defaults

    @classmethod
    def research(cls) -> "MoonConfig":
        """Research configuration with tighter tolerances."""
        return cls(
            speed_tolerance=0.0001,
            distance_tolerance=0.000001,
            time_tolerance_seconds=30,
            event_refinement_tolerance=0.0001,
        )

    @classmethod
    def testing(cls) -> "MoonConfig":
        """Testing configuration with relaxed limits."""
        return cls(
            max_search_days=30,
            cache_ttl_profile_days=1,
            cache_ttl_events_days=1,
            event_search_step_hours=12,
        )


# Global configuration instance
_moon_config: MoonConfig | None = None


def get_moon_config() -> MoonConfig:
    """Get the global moon configuration."""
    global _moon_config
    if _moon_config is None:
        _moon_config = MoonConfig()
    return _moon_config


def initialize_moon_config(config: MoonConfig | None = None) -> MoonConfig:
    """
    Initialize the global moon configuration.

    Args:
        config: Optional configuration to use. If None, creates from environment.

    Returns:
        The initialized configuration
    """
    global _moon_config

    if _moon_config is not None:
        logger.warning("Moon configuration already initialized")
        return _moon_config

    if config is None:
        # Try environment variables first
        if any(k.startswith("MOON_") for k in os.environ):
            config = MoonConfig.from_env()
            logger.info("Initialized moon config from environment")
        else:
            # Use default production config
            config = MoonConfig.production()
            logger.info("Initialized moon config with production defaults")

    _moon_config = config
    logger.info(f"Moon configuration initialized: {config}")
    return _moon_config


def reset_moon_config():
    """Reset the global configuration (for testing)."""
    global _moon_config
    _moon_config = None
    logger.debug("Moon configuration reset")
