#!/usr/bin/env python3
"""
Enhanced Moon Factors - Phase 7 Implementation
Adds velocity index, latitude index, distance index, and anomaly detection
"""

import logging

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import swisseph as swe

from .moon_config import MoonConfig, get_moon_config
from .moon_factors import MoonFactors, MoonFactorsCalculator
from .time_utils import validate_utc_datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MoonProfile:
    """Enhanced moon profile with Phase 7 indices."""

    date: datetime
    basic_factors: MoonFactors

    # Phase 7 Indices
    velocity_index: float  # Current speed / mean speed
    latitude_index: float  # Current latitude / max latitude
    distance_index: float  # (distance - perigee) / (apogee - perigee)

    # Derived strength
    strength: str  # "strong", "average", "weak"
    strength_score: float  # Combined strength 0-100

    # Anomaly flags
    is_perigee: bool = False
    is_apogee: bool = False
    is_standstill: bool = False
    is_fast_moon: bool = False
    is_slow_moon: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "date": self.date.isoformat(),
            "tithi": self.basic_factors.tithi,
            "tithi_num": self.basic_factors.tithi_num,
            "paksha": "Shukla" if self.basic_factors.is_waxing else "Krishna",
            "velocity_index": round(self.velocity_index, 4),
            "latitude_index": round(self.latitude_index, 4),
            "distance_index": round(self.distance_index, 4),
            "strength": self.strength,
            "strength_score": round(self.strength_score, 2),
            "nakshatra": self.basic_factors.nakshatra,
            "phase": self.basic_factors.phase_name,
            "illumination": round(self.basic_factors.illumination, 1),
            "anomalies": {
                "is_perigee": self.is_perigee,
                "is_apogee": self.is_apogee,
                "is_standstill": self.is_standstill,
                "is_fast_moon": self.is_fast_moon,
                "is_slow_moon": self.is_slow_moon,
            },
        }


@dataclass(frozen=True)
class MoonEvent:
    """Represents a lunar anomaly event."""

    event_type: str  # "perigee", "apogee", "standstill"
    timestamp: datetime
    value: float  # Distance for perigee/apogee, declination for standstill
    metadata: dict = field(default_factory=dict)


class EnhancedMoonCalculator:
    """Enhanced calculator with Phase 7 features."""

    def __init__(self, config: MoonConfig | None = None):
        """Initialize with configuration."""
        self.config = config or get_moon_config()
        self.basic_calc = MoonFactorsCalculator()
        swe.set_ephe_path("./swisseph/ephe")

    def calculate_profile(self, ts_utc: datetime) -> MoonProfile:
        """
        Calculate complete moon profile with Phase 7 indices.

        Args:
            ts_utc: UTC timestamp

        Returns:
            MoonProfile with all indices
        """
        ts_utc = validate_utc_datetime(ts_utc)

        # Get basic factors
        basic = self.basic_calc.calculate(ts_utc)

        # Calculate velocity index
        velocity_index = basic.speed / self.config.mean_speed

        # Calculate latitude index
        latitude_index = basic.latitude / self.config.max_latitude

        # Calculate distance index (0 = perigee, 1 = apogee)
        distance_range = self.config.apogee_distance - self.config.perigee_distance
        distance_index = (
            basic.distance - self.config.perigee_distance
        ) / distance_range
        distance_index = max(0.0, min(1.0, distance_index))  # Clamp to 0-1

        # Determine strength
        strength_score = self._calculate_strength(
            velocity_index, latitude_index, distance_index, basic
        )

        if strength_score >= 75:
            strength = "strong"
        elif strength_score >= 40:
            strength = "average"
        else:
            strength = "weak"

        # Check anomalies
        is_fast = basic.speed > self.config.fast_speed_threshold
        is_slow = basic.speed < self.config.slow_speed_threshold
        is_perigee = basic.distance < self.config.perigee_threshold
        is_apogee = basic.distance > self.config.apogee_threshold

        # Check for standstill (very slow declination change)
        is_standstill = abs(basic.declination_speed) < self.config.standstill_threshold

        return MoonProfile(
            date=ts_utc,
            basic_factors=basic,
            velocity_index=velocity_index,
            latitude_index=latitude_index,
            distance_index=distance_index,
            strength=strength,
            strength_score=strength_score,
            is_perigee=is_perigee,
            is_apogee=is_apogee,
            is_standstill=is_standstill,
            is_fast_moon=is_fast,
            is_slow_moon=is_slow,
        )

    def find_events(
        self,
        start_utc: datetime,
        end_utc: datetime,
        event_types: list[str] | None = None,
    ) -> list[MoonEvent]:
        """
        Find lunar anomaly events in date range.

        Args:
            start_utc: Start of search range
            end_utc: End of search range
            event_types: Optional list of event types to find

        Returns:
            List of MoonEvent objects
        """
        start_utc = validate_utc_datetime(start_utc)
        end_utc = validate_utc_datetime(end_utc)

        # Validate range
        max_days = self.config.max_search_days
        if (end_utc - start_utc).days > max_days:
            raise ValueError(f"Search range cannot exceed {max_days} days")

        if event_types is None:
            event_types = ["perigee", "apogee", "standstill"]

        events = []

        # Search with configured step size
        step = timedelta(hours=self.config.event_search_step_hours)
        current = start_utc

        # Track previous values for detecting extrema
        prev_distance = None
        prev_declination = None
        prev_decl_speed = None

        while current <= end_utc:
            profile = self.calculate_profile(current)
            basic = profile.basic_factors

            # Check for perigee (local minimum of distance)
            if "perigee" in event_types and prev_distance is not None:
                if (
                    prev_distance > basic.distance
                    and basic.distance < self.config.perigee_threshold
                ):
                    # Potential perigee, refine with bisection
                    exact_time = self._refine_extremum(
                        current - step,
                        current + step,
                        lambda t: self.calculate_profile(t).basic_factors.distance,
                        is_minimum=True,
                    )
                    refined = self.calculate_profile(exact_time)
                    events.append(
                        MoonEvent(
                            event_type="perigee",
                            timestamp=exact_time,
                            value=refined.basic_factors.distance,
                            metadata={
                                "speed": refined.basic_factors.speed,
                                "latitude": refined.basic_factors.latitude,
                            },
                        )
                    )

            # Check for apogee (local maximum of distance)
            if "apogee" in event_types and prev_distance is not None:
                if (
                    prev_distance < basic.distance
                    and basic.distance > self.config.apogee_threshold
                ):
                    # Potential apogee, refine with bisection
                    exact_time = self._refine_extremum(
                        current - step,
                        current + step,
                        lambda t: self.calculate_profile(t).basic_factors.distance,
                        is_minimum=False,
                    )
                    refined = self.calculate_profile(exact_time)
                    events.append(
                        MoonEvent(
                            event_type="apogee",
                            timestamp=exact_time,
                            value=refined.basic_factors.distance,
                            metadata={
                                "speed": refined.basic_factors.speed,
                                "latitude": refined.basic_factors.latitude,
                            },
                        )
                    )

            # Check for standstill (declination speed near zero)
            if "standstill" in event_types and prev_decl_speed is not None:
                if (
                    abs(prev_decl_speed) > self.config.standstill_threshold
                    and abs(basic.declination_speed) < self.config.standstill_threshold
                ):
                    # Potential standstill
                    events.append(
                        MoonEvent(
                            event_type="standstill",
                            timestamp=current,
                            value=basic.declination,
                            metadata={
                                "declination_speed": basic.declination_speed,
                                "latitude": basic.latitude,
                            },
                        )
                    )

            # Update previous values
            prev_distance = basic.distance
            prev_declination = basic.declination
            prev_decl_speed = basic.declination_speed

            current += step

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)
        return events

    def _calculate_strength(
        self,
        velocity_idx: float,
        latitude_idx: float,
        distance_idx: float,
        basic: MoonFactors,
    ) -> float:
        """
        Calculate combined strength score.

        Args:
            velocity_idx: Velocity index
            latitude_idx: Latitude index
            distance_idx: Distance index
            basic: Basic moon factors

        Returns:
            Strength score 0-100
        """
        score = 50.0  # Base score

        # Velocity contribution (faster is stronger)
        if velocity_idx > 1.0:
            score += min(20, (velocity_idx - 1.0) * 40)
        else:
            score -= min(20, (1.0 - velocity_idx) * 40)

        # Distance contribution (closer is stronger)
        score += (1.0 - distance_idx) * 20

        # Latitude contribution (less is stronger)
        score -= abs(latitude_idx) * 10

        # Basic factors contribution
        if basic.is_exalted:
            score += 10
        elif basic.is_debilitated:
            score -= 10
        elif basic.is_own_sign:
            score += 5

        # Gandanta penalty
        if basic.is_gandanta:
            score -= 15

        # Void of course penalty
        if basic.is_void_of_course:
            score -= 10

        return max(0.0, min(100.0, score))

    def _refine_extremum(
        self,
        start: datetime,
        end: datetime,
        func,
        is_minimum: bool = True,
        tolerance: float | None = None,
    ) -> datetime:
        """
        Refine extremum time using bisection.

        Args:
            start: Start of search interval
            end: End of search interval
            func: Function to evaluate
            is_minimum: True for minimum, False for maximum
            tolerance: Convergence tolerance

        Returns:
            Refined timestamp of extremum
        """
        if tolerance is None:
            tolerance = self.config.event_refinement_tolerance

        # Binary search for extremum
        while (end - start).total_seconds() > self.config.time_tolerance_seconds:
            mid1 = start + (end - start) / 3
            mid2 = end - (end - start) / 3

            val1 = func(mid1)
            val2 = func(mid2)

            if is_minimum:
                if val1 < val2:
                    end = mid2
                else:
                    start = mid1
            else:
                if val1 > val2:
                    end = mid2
                else:
                    start = mid1

        return start + (end - start) / 2


# Convenience functions


def get_moon_profile(ts_utc: datetime, config: MoonConfig | None = None) -> MoonProfile:
    """Get moon profile for a timestamp."""
    calculator = EnhancedMoonCalculator(config)
    return calculator.calculate_profile(ts_utc)


def find_moon_events(
    start_utc: datetime,
    end_utc: datetime,
    event_types: list[str] | None = None,
    config: MoonConfig | None = None,
) -> list[MoonEvent]:
    """Find moon events in a date range."""
    calculator = EnhancedMoonCalculator(config)
    return calculator.find_events(start_utc, end_utc, event_types)
