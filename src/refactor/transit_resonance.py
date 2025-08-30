#!/usr/bin/env python3
"""
Transit Resonance Kernel - Aspect Strength Calculations
Implements aspect kernels with Gaussian orb decay for transit events
"""

import logging
import math

from dataclasses import dataclass
from enum import Enum

from numba import njit

logger = logging.getLogger(__name__)


class AspectType(Enum):
    """KP/Vedic aspect types with base strengths"""

    CONJUNCTION = ("Conjunction", 0, 1.00)
    OPPOSITION = ("Opposition", 180, 0.95)
    TRINE = ("Trine", 120, 0.85)
    SQUARE = ("Square", 90, 0.80)
    SEXTILE = ("Sextile", 60, 0.65)
    SEMI_SEXTILE = ("Semi-sextile", 30, 0.40)
    SEMI_SQUARE = ("Semi-square", 45, 0.50)
    SESQUIQUADRATE = ("Sesquiquadrate", 135, 0.55)
    QUINCUNX = ("Quincunx", 150, 0.40)

    @property
    def name(self) -> str:
        return self.value[0].upper().replace("-", "_")

    @property
    def angle(self) -> float:
        return self.value[1]

    @property
    def base_strength(self) -> float:
        return self.value[2]


@dataclass
class ResonanceResult:
    """Result of resonance calculation"""

    aspect_type: AspectType
    exact_angle: float
    orb: float
    kernel_value: float
    is_applying: bool
    is_tight: bool  # Within 1° orb

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "aspect": self.aspect_type.name,
            "angle": round(self.exact_angle, 2),
            "orb": round(self.orb, 2),
            "kernel": round(self.kernel_value, 4),
            "applying": self.is_applying,
            "tight": self.is_tight,
        }


class ResonanceKernel:
    """
    Calculate aspect resonance with Gaussian orb decay.
    Performance optimized with Numba JIT compilation.
    """

    # Base aspect strengths (KP/Vedic tradition)
    BASE_STRENGTHS = {
        "CONJUNCTION": 1.00,
        "OPPOSITION": 0.95,
        "TRINE": 0.85,
        "SQUARE": 0.80,
        "SEXTILE": 0.65,
        "SEMI_SEXTILE": 0.40,
        "SEMI_SQUARE": 0.50,
        "SESQUIQUADRATE": 0.55,
        "QUINCUNX": 0.40,
    }

    # Maximum allowed orbs for each aspect (tightened per PM guidance)
    ORB_ALLOWANCES = {
        "CONJUNCTION": 8.0,
        "OPPOSITION": 6.0,
        "TRINE": 5.0,  # Per PM spec
        "SQUARE": 4.0,  # Per PM spec
        "SEXTILE": 3.0,  # Per PM spec
        "SEMI_SEXTILE": 2.0,
        "SEMI_SQUARE": 2.0,
        "SESQUIQUADRATE": 2.0,
        "QUINCUNX": 0.0,  # Disabled by default per PM
    }

    # Applying aspect bonus multiplier
    APPLYING_BONUS = 1.08

    def __init__(
        self,
        custom_strengths: dict[str, float] | None = None,
        custom_orbs: dict[str, float] | None = None,
    ):
        """
        Initialize resonance kernel calculator.

        Args:
            custom_strengths: Override base strengths
            custom_orbs: Override orb allowances
        """
        self.base_strengths = custom_strengths or self.BASE_STRENGTHS.copy()
        self.orb_allowances = custom_orbs or self.ORB_ALLOWANCES.copy()

        # Precompute for performance
        self._aspect_angles = {
            0: AspectType.CONJUNCTION,
            30: AspectType.SEMI_SEXTILE,
            45: AspectType.SEMI_SQUARE,
            60: AspectType.SEXTILE,
            90: AspectType.SQUARE,
            120: AspectType.TRINE,
            135: AspectType.SESQUIQUADRATE,
            150: AspectType.QUINCUNX,
            180: AspectType.OPPOSITION,
        }

        logger.info("ResonanceKernel initialized")

    def calculate_kernel(
        self,
        planet1_lon: float,
        planet2_lon: float,
        planet1_speed: float = 0.0,
        planet2_speed: float = 0.0,
        aspect_type: AspectType | None = None,
    ) -> ResonanceResult:
        """
        Calculate resonance kernel for planetary aspect.

        Args:
            planet1_lon: First planet longitude (0-360)
            planet2_lon: Second planet longitude (0-360)
            planet1_speed: First planet daily motion
            planet2_speed: Second planet daily motion
            aspect_type: Specific aspect to check (None = find closest)

        Returns:
            ResonanceResult with kernel value and details
        """
        # Calculate angular separation
        angle_diff = self._calculate_angle_difference(planet1_lon, planet2_lon)

        # Find aspect type if not specified
        if aspect_type is None:
            aspect_type, orb = self._find_closest_aspect(angle_diff)
        else:
            orb = abs(angle_diff - aspect_type.angle)

        # Check if within allowed orb
        max_orb = self.orb_allowances.get(aspect_type.name, 2.0)
        if orb > max_orb:
            # No aspect within orb
            return ResonanceResult(
                aspect_type=aspect_type,
                exact_angle=angle_diff,
                orb=orb,
                kernel_value=0.0,
                is_applying=False,
                is_tight=False,
            )

        # Calculate kernel value with Gaussian decay
        kernel = self._gaussian_kernel(aspect_type.name, orb, max_orb)

        # Check if applying or separating
        is_applying = self._is_aspect_applying(
            planet1_lon, planet2_lon, planet1_speed, planet2_speed, aspect_type.angle
        )

        # Apply bonus for applying aspects
        if is_applying:
            kernel = min(1.0, kernel * self.APPLYING_BONUS)

        # Check if tight aspect (within 1°)
        is_tight = orb <= 1.0

        return ResonanceResult(
            aspect_type=aspect_type,
            exact_angle=angle_diff,
            orb=orb,
            kernel_value=kernel,
            is_applying=is_applying,
            is_tight=is_tight,
        )

    def calculate_multi_resonance(
        self, moon_lon: float, moon_speed: float, planet_positions: dict[int, dict]
    ) -> dict[int, ResonanceResult]:
        """
        Calculate resonance between Moon and multiple planets.

        Args:
            moon_lon: Moon's longitude
            moon_speed: Moon's daily motion
            planet_positions: Dict of planet_id -> {longitude, speed}

        Returns:
            Dict of planet_id -> ResonanceResult
        """
        results = {}

        for planet_id, pdata in planet_positions.items():
            if planet_id == 2:  # Skip Moon itself
                continue

            result = self.calculate_kernel(
                moon_lon,
                pdata.get("longitude", pdata.get("position", 0)),
                moon_speed,
                pdata.get("speed", 0),
            )

            if result.kernel_value > 0:  # Only include if aspect exists
                results[planet_id] = result

        return results

    @staticmethod
    @njit(cache=True)
    def _gaussian_kernel_jit(base_strength: float, orb: float, max_orb: float) -> float:
        """
        JIT-compiled Gaussian kernel calculation.

        Args:
            base_strength: Base strength of aspect
            orb: Actual orb in degrees
            max_orb: Maximum allowed orb

        Returns:
            Kernel value with Gaussian decay
        """
        if max_orb <= 0:
            return 0.0

        # Gaussian decay: exp(-(orb/max_orb)^2)
        decay = math.exp(-((orb / max_orb) ** 2))
        return base_strength * decay

    def _gaussian_kernel(self, aspect_name: str, orb: float, max_orb: float) -> float:
        """
        Calculate Gaussian kernel with orb decay.

        Args:
            aspect_name: Name of aspect type
            orb: Actual orb in degrees
            max_orb: Maximum allowed orb

        Returns:
            Kernel value [0, 1]
        """
        base_strength = self.base_strengths.get(aspect_name, 0.5)
        return self._gaussian_kernel_jit(base_strength, orb, max_orb)

    def _calculate_angle_difference(self, lon1: float, lon2: float) -> float:
        """
        Calculate shortest angular distance between two longitudes.

        Args:
            lon1: First longitude (0-360)
            lon2: Second longitude (0-360)

        Returns:
            Angular distance (0-180)
        """
        diff = abs(lon1 - lon2)
        if diff > 180:
            diff = 360 - diff
        return diff

    def _find_closest_aspect(self, angle: float) -> tuple[AspectType, float]:
        """
        Find the closest aspect type for given angle.

        Args:
            angle: Angular separation (0-180)

        Returns:
            Tuple of (AspectType, orb)
        """
        closest_aspect = AspectType.CONJUNCTION
        min_orb = angle  # Default to conjunction orb

        for aspect_angle, aspect_type in self._aspect_angles.items():
            orb = abs(angle - aspect_angle)
            if orb < min_orb:
                min_orb = orb
                closest_aspect = aspect_type

        return closest_aspect, min_orb

    def _is_aspect_applying(
        self,
        lon1: float,
        lon2: float,
        speed1: float,
        speed2: float,
        target_angle: float,
    ) -> bool:
        """
        Determine if aspect is applying (forming) or separating.

        Args:
            lon1: First planet longitude
            lon2: Second planet longitude
            speed1: First planet daily motion
            speed2: Second planet daily motion
            target_angle: Target aspect angle

        Returns:
            True if applying, False if separating
        """
        current_distance = self._calculate_angle_difference(lon1, lon2)

        # Project positions forward by small amount (0.1 day)
        future_lon1 = (lon1 + speed1 * 0.1) % 360
        future_lon2 = (lon2 + speed2 * 0.1) % 360
        future_distance = self._calculate_angle_difference(future_lon1, future_lon2)

        # Check if moving toward exact aspect
        current_diff = abs(current_distance - target_angle)
        future_diff = abs(future_distance - target_angle)

        return future_diff < current_diff

    def get_active_aspects(
        self, resonances: dict[int, ResonanceResult], min_kernel: float = 0.5
    ) -> list[tuple[int, ResonanceResult]]:
        """
        Get aspects above minimum kernel threshold.

        Args:
            resonances: Dict of all resonance calculations
            min_kernel: Minimum kernel value to include

        Returns:
            List of (planet_id, result) sorted by kernel strength
        """
        active = [
            (pid, res)
            for pid, res in resonances.items()
            if res.kernel_value >= min_kernel
        ]

        # Sort by kernel strength (descending)
        active.sort(key=lambda x: x[1].kernel_value, reverse=True)

        return active

    def detect_aspect_patterns(self, aspects: list[ResonanceResult]) -> list[str]:
        """
        Detect special aspect patterns (T-square, Grand Trine, etc).

        Args:
            aspects: List of active aspects

        Returns:
            List of detected pattern names
        """
        patterns = []

        # Count aspect types
        squares = sum(1 for a in aspects if a.aspect_type == AspectType.SQUARE)
        trines = sum(1 for a in aspects if a.aspect_type == AspectType.TRINE)
        oppositions = sum(1 for a in aspects if a.aspect_type == AspectType.OPPOSITION)

        # T-Square: 2 squares + 1 opposition
        if squares >= 2 and oppositions >= 1:
            patterns.append("T-Square")

        # Grand Trine: 3+ trines
        if trines >= 3:
            patterns.append("Grand Trine")

        # Grand Cross: 2+ oppositions + 4 squares
        if oppositions >= 2 and squares >= 4:
            patterns.append("Grand Cross")

        # Multiple conjunctions (stellium indicator)
        conjunctions = sum(
            1 for a in aspects if a.aspect_type == AspectType.CONJUNCTION
        )
        if conjunctions >= 3:
            patterns.append("Stellium")

        return patterns


# Module-level instance for efficiency
_kernel_instance: ResonanceKernel | None = None


def get_resonance_kernel() -> ResonanceKernel:
    """Get or create singleton kernel instance"""
    global _kernel_instance
    if _kernel_instance is None:
        _kernel_instance = ResonanceKernel()
    return _kernel_instance
