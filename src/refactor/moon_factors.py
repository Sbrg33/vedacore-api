#!/usr/bin/env python3
"""
Moon Factors Calculator - Advanced Lunar Calculations for KP Astrology

This module provides comprehensive moon-specific calculations for financial timing,
including Panchanga elements (tithi, yoga, karana), lunar phases, and advanced
metrics. All calculations are geocentric and globally valid for any UTC timestamp.

Features:
- High-precision Panchanga calculations
- Lunar phase and illumination metrics
- Speed and acceleration analysis
- Declination and latitude tracking
- Thread-safe with Numba JIT optimization
- Integration with KP system constants

Author: VedaCore Team
Version: 1.0.0
"""

import math

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from numba import njit

import swisseph as swe

from .constants import NAKSHATRA_NAMES
from .swe_backend import get_planet_position_full
from .time_utils import validate_utc_datetime

# Planet IDs
MOON_ID = 2
SUN_ID = 1
KP_AYANAMSA_ID = 5  # Krishnamurti ayanamsa

# Sign names
SIGNS_SHORT = [
    "Ari",
    "Tau",
    "Gem",
    "Can",
    "Leo",
    "Vir",
    "Lib",
    "Sco",
    "Sag",
    "Cap",
    "Aqu",
    "Pis",
]

# Panchanga element names
TITHI_NAMES = [
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashti",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
    "Purnima",
    # Krishna paksha (waning)
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashti",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
    "Amavasya",
]

YOGA_NAMES = [
    "Vishkumbha",
    "Priti",
    "Ayushman",
    "Saubhagya",
    "Shobhana",
    "Atiganda",
    "Sukarma",
    "Dhriti",
    "Shoola",
    "Ganda",
    "Vriddhi",
    "Dhruva",
    "Vyaghata",
    "Harshana",
    "Vajra",
    "Siddhi",
    "Vyatipata",
    "Variyan",
    "Parigha",
    "Shiva",
    "Siddha",
    "Sadhya",
    "Shubha",
    "Shukla",
    "Brahma",
    "Aindra",
    "Vaidhriti",
]

# Karana names - 11 unique karanas (7 repeating + 4 fixed)
KARANA_NAMES_REPEATING = [
    "Bava",
    "Balava",
    "Kaulava",
    "Taitula",
    "Gara",
    "Vanija",
    "Vishti",
]

KARANA_NAMES_FIXED = {
    0: "Kimstughna",  # 1st half of Krishna Chaturdashi
    57: "Shakuni",  # 2nd half of Krishna Chaturdashi
    58: "Chatushpada",  # 1st half of Amavasya
    59: "Naga",  # 2nd half of Amavasya
}

# Special lunar points
GANDANTA_ZONES = [
    (29.0, 1.0),  # Pisces-Aries junction
    (119.0, 121.0),  # Cancer-Leo junction
    (239.0, 241.0),  # Scorpio-Sagittarius junction
]

# Moon exaltation/debilitation
MOON_EXALTATION = 33.0  # 3° Taurus
MOON_DEBILITATION = 213.0  # 3° Scorpio
MOON_OWN_SIGN = (90.0, 120.0)  # Cancer


@dataclass(frozen=True)
class MoonFactors:
    """Complete moon calculation results"""

    # Basic position
    longitude: float
    latitude: float
    distance: float
    speed: float
    acceleration: float

    # Declination
    declination: float
    declination_speed: float

    # Sign and nakshatra
    sign: str
    sign_num: int
    nakshatra: str
    nakshatra_num: int
    pada: int

    # Panchanga elements
    tithi: str
    tithi_num: int
    tithi_percent: float
    yoga: str
    yoga_num: int
    yoga_percent: float
    karana: str
    karana_num: int

    # Lunar phase
    phase_angle: float
    illumination: float
    phase_name: str
    is_waxing: bool

    # Dignities
    is_exalted: bool
    is_debilitated: bool
    is_own_sign: bool
    dignity_score: float

    # Special conditions
    is_gandanta: bool
    is_sandhi: bool
    is_void_of_course: bool
    is_combust: bool

    # Timing quality
    quality_score: float
    quality_factors: dict[str, float] = field(default_factory=dict)


@njit(cache=True)
def calculate_tithi(moon_lon: float, sun_lon: float) -> tuple[int, float]:
    """
    Calculate lunar tithi (lunar day).

    Args:
        moon_lon: Moon's longitude in degrees
        sun_lon: Sun's longitude in degrees

    Returns:
        Tuple of (tithi_number, tithi_percent_complete)
    """
    # Calculate angular separation
    diff = moon_lon - sun_lon
    if diff < 0:
        diff += 360.0

    # Each tithi is 12 degrees
    tithi_num = int(diff / 12.0)
    tithi_percent = (diff % 12.0) / 12.0 * 100.0

    return tithi_num, tithi_percent


@njit(cache=True)
def calculate_yoga(moon_lon: float, sun_lon: float) -> tuple[int, float]:
    """
    Calculate yoga (sum of sun and moon longitudes).

    Args:
        moon_lon: Moon's longitude in degrees
        sun_lon: Sun's longitude in degrees

    Returns:
        Tuple of (yoga_number, yoga_percent_complete)
    """
    # Sum of longitudes
    yoga_sum = (moon_lon + sun_lon) % 360.0

    # Each yoga is 13°20' (13.333... degrees)
    yoga_deg = 360.0 / 27.0
    yoga_num = int(yoga_sum / yoga_deg)
    yoga_percent = (yoga_sum % yoga_deg) / yoga_deg * 100.0

    return yoga_num, yoga_percent


@njit(cache=True)
def calculate_karana(tithi_num: int, tithi_percent: float) -> int:
    """
    Calculate karana (half of tithi).

    Args:
        tithi_num: Current tithi number (0-29)
        tithi_percent: Percentage of tithi complete

    Returns:
        Karana number (0-59)
    """
    # Each tithi has 2 karanas
    karana_base = tithi_num * 2

    # Check if in second half of tithi
    if tithi_percent >= 50.0:
        karana_base += 1

    return karana_base


def get_karana_name(karana_num: int) -> str:
    """Get karana name from number."""
    # Fixed karanas for special positions
    if karana_num in KARANA_NAMES_FIXED:
        return KARANA_NAMES_FIXED[karana_num]

    # Repeating karanas (cycle through 7)
    if karana_num <= 56:
        return KARANA_NAMES_REPEATING[(karana_num - 1) % 7]

    # Default to first repeating karana
    return KARANA_NAMES_REPEATING[0]


@njit(cache=True)
def calculate_phase_angle(moon_lon: float, sun_lon: float) -> float:
    """
    Calculate lunar phase angle (0-360).

    0° = New Moon
    90° = First Quarter
    180° = Full Moon
    270° = Last Quarter
    """
    angle = moon_lon - sun_lon
    if angle < 0:
        angle += 360.0
    return angle


@njit(cache=True)
def calculate_illumination(phase_angle: float) -> float:
    """
    Calculate moon illumination percentage.

    Args:
        phase_angle: Phase angle in degrees (0-360)

    Returns:
        Illumination percentage (0-100)
    """
    # Use cosine formula for illumination
    rad = math.radians(phase_angle)
    illumination = (1 - math.cos(rad)) * 50.0
    return max(0.0, min(100.0, illumination))


def get_phase_name(phase_angle: float) -> str:
    """Get descriptive phase name from angle."""
    if phase_angle < 11.25:
        return "New Moon"
    elif phase_angle < 33.75:
        return "Waxing Crescent"
    elif phase_angle < 56.25:
        return "Waxing Crescent"
    elif phase_angle < 78.75:
        return "Waxing Crescent"
    elif phase_angle < 101.25:
        return "First Quarter"
    elif phase_angle < 123.75:
        return "Waxing Gibbous"
    elif phase_angle < 146.25:
        return "Waxing Gibbous"
    elif phase_angle < 168.75:
        return "Waxing Gibbous"
    elif phase_angle < 191.25:
        return "Full Moon"
    elif phase_angle < 213.75:
        return "Waning Gibbous"
    elif phase_angle < 236.25:
        return "Waning Gibbous"
    elif phase_angle < 258.75:
        return "Waning Gibbous"
    elif phase_angle < 281.25:
        return "Last Quarter"
    elif phase_angle < 303.75:
        return "Waning Crescent"
    elif phase_angle < 326.25:
        return "Waning Crescent"
    elif phase_angle < 348.75:
        return "Waning Crescent"
    else:
        return "New Moon"


@njit(cache=True)
def check_gandanta(longitude: float) -> bool:
    """Check if moon is in gandanta zone (inauspicious junction)."""
    # Hardcode gandanta zones for Numba compatibility
    # Pisces-Aries junction (end of Pisces or start of Aries)
    if longitude >= 359.0 or longitude <= 1.0:
        return True
    # Cancer-Leo junction
    if 119.0 <= longitude <= 121.0:
        return True
    # Scorpio-Sagittarius junction
    if 239.0 <= longitude <= 241.0:
        return True
    return False


@njit(cache=True)
def check_sandhi(longitude: float) -> bool:
    """Check if moon is at sign boundary (sandhi)."""
    sign_pos = longitude % 30.0
    return sign_pos < 1.0 or sign_pos > 29.0


@njit(cache=True)
def calculate_dignity_score(longitude: float, speed: float) -> float:
    """
    Calculate moon's dignity score (0-100).

    Factors:
    - Exaltation/debilitation
    - Own sign placement
    - Speed (fast = strong)
    """
    score = 50.0  # Base score

    # Exaltation/debilitation
    if abs(longitude - MOON_EXALTATION) < 5.0:
        score += 30.0
    elif abs(longitude - MOON_DEBILITATION) < 5.0:
        score -= 30.0

    # Own sign (Cancer)
    if 90.0 <= longitude <= 120.0:
        score += 20.0

    # Speed factor (normal is ~13°/day)
    if speed > 14.0:
        score += 10.0
    elif speed < 12.0:
        score -= 10.0

    return max(0.0, min(100.0, score))


class MoonFactorsCalculator:
    """Calculator for comprehensive moon factors."""

    def __init__(self, ephe_path: str = "./swisseph/ephe"):
        """Initialize calculator with ephemeris path."""
        # Set ephemeris path
        swe.set_ephe_path(ephe_path)
        # Set KP ayanamsa
        swe.set_sid_mode(KP_AYANAMSA_ID, 0, 0)
        self._cache = {}

    def calculate(self, ts_utc: datetime) -> MoonFactors:
        """
        Calculate all moon factors for given timestamp.

        Args:
            ts_utc: UTC timestamp

        Returns:
            MoonFactors object with all calculations
        """
        ts_utc = validate_utc_datetime(ts_utc)

        # Check cache
        cache_key = ts_utc.isoformat()
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get moon and sun positions
        moon_data = get_planet_position_full(ts_utc, MOON_ID)
        sun_data = get_planet_position_full(ts_utc, SUN_ID)

        moon_lon = moon_data["longitude"]
        sun_lon = sun_data["longitude"]

        # Calculate acceleration (speed change)
        dt_delta = timedelta(hours=1)
        moon_future = get_planet_position_full(ts_utc + dt_delta, MOON_ID)
        acceleration = (moon_future["speed_lon"] - moon_data["speed_lon"]) / 24.0

        # Sign and nakshatra
        sign_num = int(moon_lon / 30.0)
        sign = SIGNS_SHORT[sign_num]

        nakshatra_num = int(moon_lon * 27.0 / 360.0)
        # NAKSHATRA_NAMES is 1-indexed dictionary
        nakshatra = NAKSHATRA_NAMES[nakshatra_num + 1]
        pada = int((moon_lon * 27.0 / 360.0 - nakshatra_num) * 4.0) + 1

        # Panchanga calculations
        tithi_num, tithi_percent = calculate_tithi(moon_lon, sun_lon)
        yoga_num, yoga_percent = calculate_yoga(moon_lon, sun_lon)
        karana_num = calculate_karana(tithi_num, tithi_percent)

        # Lunar phase
        phase_angle = calculate_phase_angle(moon_lon, sun_lon)
        illumination = calculate_illumination(phase_angle)
        phase_name = get_phase_name(phase_angle)
        is_waxing = phase_angle < 180.0

        # Dignities
        is_exalted = abs(moon_lon - MOON_EXALTATION) < 5.0
        is_debilitated = abs(moon_lon - MOON_DEBILITATION) < 5.0
        is_own_sign = 90.0 <= moon_lon <= 120.0
        dignity_score = calculate_dignity_score(moon_lon, moon_data["speed_lon"])

        # Special conditions
        is_gandanta = check_gandanta(moon_lon)
        is_sandhi = check_sandhi(moon_lon)
        is_void_of_course = False  # TODO: Implement VOC calculation
        is_combust = abs(moon_lon - sun_lon) < 12.0

        # Calculate quality score
        quality_factors = {
            "dignity": dignity_score / 100.0,
            "speed": min(1.0, moon_data["speed_lon"] / 13.0),
            "phase": illumination / 100.0,
            "gandanta": 0.0 if is_gandanta else 1.0,
            "sandhi": 0.0 if is_sandhi else 1.0,
        }
        quality_score = sum(quality_factors.values()) / len(quality_factors) * 100.0

        # Create result
        result = MoonFactors(
            longitude=moon_lon,
            latitude=moon_data["latitude"],
            distance=moon_data["distance"],
            speed=moon_data["speed_lon"],
            acceleration=acceleration,
            declination=moon_data.get("declination", 0.0),
            declination_speed=moon_data.get("speed_lat", 0.0),
            sign=sign,
            sign_num=sign_num,
            nakshatra=nakshatra,
            nakshatra_num=nakshatra_num + 1,  # 1-based
            pada=pada,
            tithi=TITHI_NAMES[tithi_num],
            tithi_num=tithi_num + 1,  # 1-based
            tithi_percent=tithi_percent,
            yoga=YOGA_NAMES[yoga_num],
            yoga_num=yoga_num + 1,  # 1-based
            yoga_percent=yoga_percent,
            karana=get_karana_name(karana_num),
            karana_num=karana_num,
            phase_angle=phase_angle,
            illumination=illumination,
            phase_name=phase_name,
            is_waxing=is_waxing,
            is_exalted=is_exalted,
            is_debilitated=is_debilitated,
            is_own_sign=is_own_sign,
            dignity_score=dignity_score,
            is_gandanta=is_gandanta,
            is_sandhi=is_sandhi,
            is_void_of_course=is_void_of_course,
            is_combust=is_combust,
            quality_score=quality_score,
            quality_factors=quality_factors,
        )

        # Cache result
        self._cache[cache_key] = result

        # Limit cache size
        if len(self._cache) > 10000:
            # Remove oldest entries
            keys = list(self._cache.keys())
            for key in keys[:5000]:
                del self._cache[key]

        return result

    def find_tithi_changes(
        self, start_utc: datetime, end_utc: datetime, step_minutes: int = 5
    ) -> list[dict]:
        """
        Find all tithi changes in a time range.

        Args:
            start_utc: Start time (UTC)
            end_utc: End time (UTC)
            step_minutes: Scan step size in minutes

        Returns:
            List of tithi change events
        """
        changes = []
        current = start_utc
        prev_tithi = None

        while current <= end_utc:
            factors = self.calculate(current)

            if prev_tithi is not None and factors.tithi_num != prev_tithi:
                # Refine the exact moment
                left = current - timedelta(minutes=step_minutes)
                right = current

                # Binary search for exact moment
                while (right - left).total_seconds() > 1:
                    mid = left + (right - left) / 2
                    mid_factors = self.calculate(mid)

                    if mid_factors.tithi_num == prev_tithi:
                        left = mid
                    else:
                        right = mid

                changes.append(
                    {
                        "timestamp": right.isoformat(),
                        "type": "tithi_change",
                        "from": TITHI_NAMES[prev_tithi - 1],
                        "to": factors.tithi,
                        "longitude": factors.longitude,
                    }
                )

            prev_tithi = factors.tithi_num
            current += timedelta(minutes=step_minutes)

        return changes

    def find_phase_events(self, start_utc: datetime, end_utc: datetime) -> list[dict]:
        """
        Find major lunar phase events (new, full, quarters).

        Args:
            start_utc: Start time (UTC)
            end_utc: End time (UTC)

        Returns:
            List of phase events
        """
        events = []
        current = start_utc

        # Target phase angles
        phase_targets = {
            0: "New Moon",
            90: "First Quarter",
            180: "Full Moon",
            270: "Last Quarter",
        }

        # Scan for each phase
        for target_angle, phase_name in phase_targets.items():
            current = start_utc

            while current <= end_utc:
                factors = self.calculate(current)

                # Check if close to target
                angle_diff = abs(factors.phase_angle - target_angle)
                if angle_diff > 180:
                    angle_diff = 360 - angle_diff

                if angle_diff < 1.0:
                    # Refine with bisection
                    left = current - timedelta(hours=1)
                    right = current + timedelta(hours=1)

                    while (right - left).total_seconds() > 60:
                        mid = left + (right - left) / 2
                        mid_factors = self.calculate(mid)

                        mid_diff = abs(mid_factors.phase_angle - target_angle)
                        if mid_diff > 180:
                            mid_diff = 360 - mid_diff

                        left_factors = self.calculate(left)
                        left_diff = abs(left_factors.phase_angle - target_angle)
                        if left_diff > 180:
                            left_diff = 360 - left_diff

                        if mid_diff < left_diff:
                            right = mid
                        else:
                            left = mid

                    events.append(
                        {
                            "timestamp": left.isoformat(),
                            "type": "lunar_phase",
                            "phase": phase_name,
                            "angle": target_angle,
                            "illumination": self.calculate(left).illumination,
                        }
                    )

                    # Skip ahead to avoid duplicate detection
                    current += timedelta(days=5)
                else:
                    current += timedelta(hours=6)

        # Sort by timestamp
        events.sort(key=lambda x: x["timestamp"])
        return events


# Public API
def get_moon_factors(ts_utc: datetime) -> MoonFactors:
    """
    Get moon factors for a given timestamp.

    This is the main entry point for external code.

    Args:
        ts_utc: UTC timestamp

    Returns:
        MoonFactors object with all calculations
    """
    calculator = MoonFactorsCalculator()
    return calculator.calculate(ts_utc)


def get_panchanga(ts_utc: datetime) -> dict[str, any]:
    """
    Get Panchanga (5 limbs) for a timestamp.

    Args:
        ts_utc: UTC timestamp

    Returns:
        Dictionary with tithi, nakshatra, yoga, karana, vara (weekday)
    """
    factors = get_moon_factors(ts_utc)

    # Get weekday (vara)
    vara_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    vara = vara_names[ts_utc.weekday()]

    return {
        "timestamp": ts_utc.isoformat(),
        "tithi": {
            "name": factors.tithi,
            "number": factors.tithi_num,
            "percent": factors.tithi_percent,
        },
        "nakshatra": {
            "name": factors.nakshatra,
            "number": factors.nakshatra_num,
            "pada": factors.pada,
        },
        "yoga": {
            "name": factors.yoga,
            "number": factors.yoga_num,
            "percent": factors.yoga_percent,
        },
        "karana": {"name": factors.karana, "number": factors.karana_num},
        "vara": vara,
    }
