#!/usr/bin/env python3
"""
KP Configuration Module
Frozen configuration for KP system variations and customizations
"""

import os

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class KPConfiguration:
    """
    Immutable KP configuration for runtime variations.

    This configuration is set once at startup and remains constant
    throughout the application lifecycle for consistency.
    """

    # ============== Retrograde Handling ==============
    retrograde_reverses_sublord: bool = False
    retrograde_strength_factor: float = 0.8  # Reduce strength by 20% when retrograde
    retrograde_affects_significators: bool = True
    rahu_ketu_always_retrograde: bool = True
    treat_stationary_as_powerful: bool = True
    stationary_strength_bonus: float = 1.2

    # ============== Orb Configurations ==============
    # Natal chart orbs (birth chart analysis)
    natal_orbs: dict[str, float] = field(
        default_factory=lambda: {
            "cusp": 5.0,  # Standard KP orb for cusps
            "sandhi": 2.5,  # Bhava sandhi (house junction)
            "aspect": 8.0,  # Aspect orbs
            "conjunction": 8.0,  # Conjunction orb
            "opposition": 8.0,  # Opposition orb
            "trine": 6.0,  # Trine orb
            "square": 6.0,  # Square orb
            "sextile": 4.0,  # Sextile orb
            "angle": 5.0,  # Orb for angles (ASC, MC, etc.)
        }
    )

    # Horary chart orbs (prashna, tighter orbs)
    horary_orbs: dict[str, float] = field(
        default_factory=lambda: {
            "cusp": 3.0,  # Tighter for horary precision
            "sandhi": 1.5,  # Very tight sandhi
            "aspect": 5.0,  # Tighter aspects
            "conjunction": 5.0,
            "opposition": 5.0,
            "trine": 4.0,
            "square": 4.0,
            "sextile": 3.0,
            "angle": 3.0,
        }
    )

    # Mundane astrology orbs (world events, wider orbs)
    mundane_orbs: dict[str, float] = field(
        default_factory=lambda: {
            "cusp": 7.0,  # Wider for collective events
            "sandhi": 3.5,
            "aspect": 10.0,  # Wider aspects for mundane
            "conjunction": 10.0,
            "opposition": 10.0,
            "trine": 8.0,
            "square": 8.0,
            "sextile": 6.0,
            "angle": 7.0,
        }
    )

    # Intraday trading orbs (financial markets)
    intraday_orbs: dict[str, float] = field(
        default_factory=lambda: {
            "cusp": 2.0,  # Very tight for minute-level timing
            "sandhi": 1.0,  # Minimal sandhi
            "aspect": 3.0,  # Quick aspects
            "conjunction": 3.0,
            "opposition": 3.0,
            "trine": 2.5,
            "square": 2.5,
            "sextile": 2.0,
            "angle": 2.0,
        }
    )

    # ============== Significator Rules ==============
    significator_min_strength: float = 25.0  # Minimum strength to consider
    primary_significator_count: int = 3  # Top N significators to use
    include_aspect_significators: bool = True
    aspect_significator_weight: float = 0.5  # Weight for aspect-based significators

    # ============== House System Preferences ==============
    default_house_system: Literal["PLACIDUS", "BHAVA"] = "PLACIDUS"
    use_bhava_for_occupation: bool = False  # Use Bhava chart for house occupation

    # ============== Timing Rules ==============
    dasha_activation_orb_days: int = 7  # Days before/after dasha change
    transit_activation_orb_hours: int = 24  # Hours for transit activation
    use_progression: bool = False  # Secondary progressions

    # ============== Special KP Rules ==============
    use_kp_ayanamsa: bool = True  # Always use KP ayanamsa
    sublord_decides_matter: bool = True  # CSL determines house results
    ruling_planets_override: bool = False  # RP can override other factors

    # ============== Performance Settings ==============
    enable_caching: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    enable_lazy_evaluation: bool = True
    max_depositor_chain_depth: int = 5

    # ============== Mode Settings ==============
    default_mode: Literal["natal", "horary", "mundane", "intraday"] = "natal"
    strict_kp_rules: bool = True  # Follow strict KP principles

    def get_orbs_for_mode(self, mode: str) -> dict[str, float]:
        """Get orb configuration for a specific mode"""
        orb_maps = {
            "natal": self.natal_orbs,
            "horary": self.horary_orbs,
            "mundane": self.mundane_orbs,
            "intraday": self.intraday_orbs,
        }
        return orb_maps.get(mode, self.natal_orbs)


# Global configuration instance
_kp_config: KPConfiguration | None = None
_config_initialized: bool = False


def initialize_kp_config(**kwargs) -> KPConfiguration:
    """
    Initialize KP configuration once at startup.

    Can be called with custom parameters or will use defaults.
    Subsequent calls will return the same instance.

    Args:
        **kwargs: Configuration overrides

    Returns:
        KPConfiguration instance
    """
    global _kp_config, _config_initialized

    if not _config_initialized:
        # Check environment variables for overrides
        env_overrides = {}

        # Retrograde handling
        if os.environ.get("KP_RETROGRADE_REVERSES_SUBLORD"):
            env_overrides["retrograde_reverses_sublord"] = (
                os.environ["KP_RETROGRADE_REVERSES_SUBLORD"].lower() == "true"
            )

        if os.environ.get("KP_RETROGRADE_STRENGTH_FACTOR"):
            env_overrides["retrograde_strength_factor"] = float(
                os.environ["KP_RETROGRADE_STRENGTH_FACTOR"]
            )

        # Orb overrides
        if os.environ.get("KP_NATAL_CUSP_ORB"):
            natal_orbs = KPConfiguration().natal_orbs.copy()
            natal_orbs["cusp"] = float(os.environ["KP_NATAL_CUSP_ORB"])
            env_overrides["natal_orbs"] = natal_orbs

        # Mode
        if os.environ.get("KP_DEFAULT_MODE"):
            env_overrides["default_mode"] = os.environ["KP_DEFAULT_MODE"]

        # Performance
        if os.environ.get("KP_ENABLE_CACHING"):
            env_overrides["enable_caching"] = (
                os.environ["KP_ENABLE_CACHING"].lower() == "true"
            )

        # Merge environment overrides with provided kwargs
        config_params = {**env_overrides, **kwargs}

        # Create configuration
        _kp_config = KPConfiguration(**config_params)
        _config_initialized = True

        # Log configuration
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"KP Configuration initialized with mode: {_kp_config.default_mode}"
        )
        logger.info(f"Retrograde reversal: {_kp_config.retrograde_reverses_sublord}")
        logger.info(f"Caching enabled: {_kp_config.enable_caching}")

    return _kp_config


def get_kp_config() -> KPConfiguration:
    """
    Get the current KP configuration.

    Returns:
        KPConfiguration instance

    Raises:
        RuntimeError: If configuration not initialized
    """
    if _kp_config is None:
        # Auto-initialize with defaults if not done
        return initialize_kp_config()
    return _kp_config


def ensure_config_initialized():
    """Ensure KP configuration is initialized"""
    if not _config_initialized:
        initialize_kp_config()


def reset_kp_config():
    """Reset configuration (mainly for testing)"""
    global _kp_config, _config_initialized
    _kp_config = None
    _config_initialized = False
