#!/usr/bin/env python3
"""
KP Context Module
Runtime context for KP calculations with per-request variations
"""

import json

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.utils.hash_keys import key_digest

from .kp_config import get_kp_config


@dataclass
class KPContext:
    """
    Runtime context for KP calculations.

    Unlike KPConfiguration which is frozen at startup, KPContext
    can vary per request/calculation while respecting the base config.
    """

    # Mode of analysis
    mode: Literal["natal", "horary", "mundane", "intraday"] = "natal"

    # Retrograde handling for this calculation
    use_retrograde_reversal: bool = False
    retrograde_custom_factor: float | None = None  # Override config factor

    # Custom orbs for this calculation
    custom_orbs: dict[str, float] | None = None

    # Performance hints
    time_sensitive: bool = False  # For HFT/real-time calculations
    skip_minor_aspects: bool = False  # Skip sextile, quincunx, etc.
    max_significator_levels: int = 5  # How deep to go in significator hierarchy

    # Special flags
    use_ruling_planets: bool = False  # Include RP in analysis
    strict_orbs: bool = False  # Use even tighter orbs
    include_cuspal_interlinks: bool = True  # Full CSL analysis

    # Horary-specific
    horary_number: int | None = None  # 1-249 for KP horary

    # Subject matter (affects orbs and rules)
    subject: str | None = None  # 'marriage', 'career', 'health', etc.

    # Caching hint
    cache_key_suffix: str | None = None  # Additional cache key component

    def get_orb(self, orb_type: str) -> float:
        """
        Get appropriate orb for this context.

        Priority:
        1. Custom orbs (if provided)
        2. Subject-specific adjustments
        3. Strict orbs (if enabled)
        4. Mode-based orbs from config

        Args:
            orb_type: Type of orb ('cusp', 'sandhi', 'aspect', etc.)

        Returns:
            Orb value in degrees
        """
        # Check custom orbs first
        if self.custom_orbs and orb_type in self.custom_orbs:
            orb = self.custom_orbs[orb_type]
        else:
            # Get from config based on mode
            config = get_kp_config()
            mode_orbs = config.get_orbs_for_mode(self.mode)
            orb = mode_orbs.get(orb_type, 5.0)

        # Apply subject-specific adjustments
        if self.subject:
            orb = self._adjust_orb_for_subject(orb, orb_type)

        # Apply strict orbs if enabled
        if self.strict_orbs:
            orb *= 0.7  # 30% tighter

        return orb

    def _adjust_orb_for_subject(self, base_orb: float, orb_type: str) -> float:
        """Adjust orb based on subject matter"""
        adjustments = {
            "marriage": {"cusp": 1.2, "aspect": 1.1},  # Wider for 7th house matters
            "career": {
                "cusp": 0.9,  # Tighter for 10th house
                "angle": 1.2,  # But wider for MC
            },
            "health": {
                "cusp": 0.8,  # Very tight for 6th/8th
                "sandhi": 0.6,  # Critical to avoid sandhi
            },
            "wealth": {"cusp": 1.0, "aspect": 0.9},  # Standard for 2nd/11th
            "speculation": {"cusp": 0.7, "aspect": 0.8},  # Very tight for 5th house
        }

        if self.subject in adjustments:
            factor = adjustments[self.subject].get(orb_type, 1.0)
            return base_orb * factor

        return base_orb

    def get_retrograde_factor(self) -> float:
        """Get retrograde strength factor for this context"""
        if self.retrograde_custom_factor is not None:
            return self.retrograde_custom_factor

        config = get_kp_config()
        return config.retrograde_strength_factor

    def should_reverse_sublord(self) -> bool:
        """Check if sublord should be reversed for retrograde planets"""
        if not self.use_retrograde_reversal:
            return False

        config = get_kp_config()
        return config.retrograde_reverses_sublord

    def get_significator_threshold(self) -> float:
        """Get minimum significator strength for this context"""
        config = get_kp_config()
        threshold = config.significator_min_strength

        # Adjust based on mode
        if self.mode == "horary":
            threshold *= 0.8  # Lower threshold for horary
        elif self.mode == "intraday":
            threshold *= 1.2  # Higher threshold for trading

        return threshold

    def to_cache_key(self) -> str:
        """
        Generate a cache key component for this context.

        Used to differentiate cached calculations with different contexts.
        """
        key_parts = [
            self.mode,
            str(self.use_retrograde_reversal),
            str(self.strict_orbs),
            str(self.time_sensitive),
            self.subject or "general",
        ]

        # Add custom orbs if present
        if self.custom_orbs:
            orb_str = json.dumps(self.custom_orbs, sort_keys=True)
            key_parts.append(orb_str)

        # Add horary number if present
        if self.horary_number:
            key_parts.append(f"h{self.horary_number}")

        # Add custom suffix
        if self.cache_key_suffix:
            key_parts.append(self.cache_key_suffix)

        # Create hash for consistent length
        key_str = "|".join(key_parts)
        return key_digest(key_str, short=8, fast=True)

    def is_high_performance(self) -> bool:
        """Check if this context requires high-performance mode"""
        return self.time_sensitive or self.mode == "intraday"

    def validate(self) -> bool:
        """
        Validate context parameters.

        Returns:
            True if valid

        Raises:
            ValueError: If invalid parameters
        """
        # Validate mode
        valid_modes = {"natal", "horary", "mundane", "intraday"}
        if self.mode not in valid_modes:
            raise ValueError(f"Invalid mode: {self.mode}")

        # Validate horary number
        if self.horary_number is not None:
            if not 1 <= self.horary_number <= 249:
                raise ValueError(
                    f"Horary number must be 1-249, got {self.horary_number}"
                )

        # Validate custom orbs
        if self.custom_orbs:
            for orb_type, value in self.custom_orbs.items():
                if value < 0 or value > 30:
                    raise ValueError(f"Orb {orb_type}={value} out of range (0-30)")

        # Validate retrograde factor
        if self.retrograde_custom_factor is not None:
            if not 0 < self.retrograde_custom_factor <= 2:
                raise ValueError(
                    f"Retrograde factor {self.retrograde_custom_factor} out of range"
                )

        return True


@dataclass
class KPRequest:
    """
    Complete request for KP analysis including context.

    This bundles all parameters needed for a KP calculation.
    """

    timestamp: datetime
    latitude: float
    longitude: float
    context: KPContext = field(default_factory=KPContext)

    # Optional birth data for comparisons
    birth_timestamp: datetime | None = None
    birth_latitude: float | None = None
    birth_longitude: float | None = None

    # Optional specific analysis requests
    analyze_houses: list[int] | None = None  # Specific houses to analyze
    analyze_planets: list[int] | None = None  # Specific planets to analyze
    analyze_matters: list[str] | None = None  # Life matters to analyze

    def validate(self) -> bool:
        """Validate request parameters"""
        # Validate coordinates
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Invalid latitude: {self.latitude}")

        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Invalid longitude: {self.longitude}")

        # Validate context
        self.context.validate()

        # Validate house numbers
        if self.analyze_houses:
            for house in self.analyze_houses:
                if not 1 <= house <= 12:
                    raise ValueError(f"Invalid house number: {house}")

        # Validate planet IDs
        if self.analyze_planets:
            for planet in self.analyze_planets:
                if not 1 <= planet <= 9:
                    raise ValueError(f"Invalid planet ID: {planet}")

        return True


def create_natal_context(
    use_retrograde: bool = False,
    strict_orbs: bool = False,
    subject: str | None = None,
) -> KPContext:
    """Create a context for natal chart analysis"""
    return KPContext(
        mode="natal",
        use_retrograde_reversal=use_retrograde,
        strict_orbs=strict_orbs,
        subject=subject,
        include_cuspal_interlinks=True,
    )


def create_horary_context(
    horary_number: int,
    use_retrograde: bool = True,  # Often used in horary
    strict_orbs: bool = True,  # Horary needs precision
) -> KPContext:
    """Create a context for horary (prashna) analysis"""
    return KPContext(
        mode="horary",
        horary_number=horary_number,
        use_retrograde_reversal=use_retrograde,
        strict_orbs=strict_orbs,
        skip_minor_aspects=True,  # Focus on major aspects
    )


def create_intraday_context(
    time_sensitive: bool = True, skip_minor: bool = True
) -> KPContext:
    """Create a context for intraday trading analysis"""
    return KPContext(
        mode="intraday",
        time_sensitive=time_sensitive,
        skip_minor_aspects=skip_minor,
        max_significator_levels=3,  # Faster analysis
        use_ruling_planets=True,  # Important for timing
    )


def create_mundane_context(
    subject: str = "world_events", wider_orbs: bool = True
) -> KPContext:
    """Create a context for mundane astrology"""
    custom_orbs = None
    if wider_orbs:
        custom_orbs = {"cusp": 8.0, "aspect": 12.0, "conjunction": 12.0}

    return KPContext(
        mode="mundane",
        subject=subject,
        custom_orbs=custom_orbs,
        include_cuspal_interlinks=False,  # Less important for mundane
    )
