#!/usr/bin/env python3
"""
Swiss Ephemeris backend interface
Thread-safe planet calculations with Krishnamurti ayanamsa
Single-mode enforcement: ayanamsa set once at module import
"""

import threading
import warnings

from datetime import datetime

import swisseph as swe

from .constants import PLANET_IDS, PLANET_NAMES
from .numerics import normalize_angle
from .time_utils import datetime_to_julian_day, ensure_utc

# ============================================================================
# SWISS EPHEMERIS CONFIGURATION
# ============================================================================

# Thread lock for Swiss Ephemeris calls (it's not thread-safe)
_swe_lock = threading.Lock()

# Track if ayanamsa has been set
_ayanamsa_initialized = False
_current_ayanamsa = None

# Set ephemeris path and Krishnamurti ayanamsa ONCE at module import
from pathlib import Path

# Find ephemeris path
ephemeris_path = None
possible_paths = [
    Path(__file__).parent.parent / "swisseph" / "ephe",
    Path("/home/sb108/projects/vedacore/swisseph/ephe"),
    Path("/home/sb108/projects/master_ephe/swisseph/ephe"),
]

for path in possible_paths:
    if path.exists():
        ephemeris_path = str(path)
        break

with _swe_lock:
    # Set ephemeris path if found
    if ephemeris_path:
        swe.set_ephe_path(ephemeris_path)

    # Set Krishnamurti ayanamsa
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI, 0, 0)
    _ayanamsa_initialized = True
    _current_ayanamsa = swe.SIDM_KRISHNAMURTI

# Standard flags for all calculations
FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_SIDEREAL

# Equatorial flags (without sidereal)
FLAGS_EQUATORIAL = swe.FLG_SWIEPH | swe.FLG_EQUATORIAL

# ============================================================================
# AYANAMSA ENFORCEMENT
# ============================================================================


class SwissModeError(Exception):
    """Raised when attempting to change ayanamsa after initialization"""

    pass


def get_current_ayanamsa() -> int:
    """Get the currently set ayanamsa ID"""
    return _current_ayanamsa


def validate_ayanamsa(ayanamsa_id: int) -> None:
    """Validate that requested ayanamsa matches current setting

    Args:
        ayanamsa_id: Requested ayanamsa ID

    Raises:
        SwissModeError: If ayanamsa doesn't match current setting
    """
    if _current_ayanamsa is not None and ayanamsa_id != _current_ayanamsa:
        raise SwissModeError(
            f"Cannot change ayanamsa from {_current_ayanamsa} to {ayanamsa_id}. "
            "Swiss Ephemeris enforces single-mode per process. "
            "Use separate processes for different ayanamsas."
        )


# ============================================================================
# PLANET CALCULATIONS
# ============================================================================


def get_planet_longitude(ts_utc: datetime, planet_id: int) -> tuple[float, float]:
    """Get sidereal longitude and speed for planet at timestamp

    Args:
        ts_utc: UTC timestamp
        planet_id: Planet ID (1-9 in KP system)

    Returns:
        (longitude, speed) tuple
        - longitude: Sidereal longitude in degrees [0, 360)
        - speed: Longitude speed in degrees/day
    """
    ts_utc = ensure_utc(ts_utc)
    jd = datetime_to_julian_day(ts_utc)

    if planet_id not in PLANET_IDS:
        raise ValueError(f"Invalid planet_id: {planet_id}")

    swe_id = PLANET_IDS[planet_id]

    with _swe_lock:
        if swe_id < 0:  # Ketu: compute Rahu + 180°
            # Unpack the return values properly
            (lon, lat, dist, sp_lon, sp_lat, sp_dist), retflag = swe.calc_ut(
                jd, -swe_id, FLAGS
            )
            longitude = normalize_angle(lon + 180.0)
            speed = sp_lon  # Ketu has same speed as Rahu
        else:
            # Unpack the return values properly
            (lon, lat, dist, sp_lon, sp_lat, sp_dist), retflag = swe.calc_ut(
                jd, swe_id, FLAGS
            )
            longitude = normalize_angle(lon)
            speed = sp_lon

    return longitude, speed


def get_planet_position_full(ts_utc: datetime, planet_id: int) -> dict:
    """Get full planetary position data

    Args:
        ts_utc: UTC timestamp
        planet_id: Planet ID (1-9 in KP system)

    Returns:
        Dictionary with position data:
        - longitude: Sidereal longitude in degrees
        - latitude: Ecliptic latitude in degrees
        - distance: Distance in AU
        - speed_lon: Longitude speed in degrees/day
        - speed_lat: Latitude speed in degrees/day
        - speed_dist: Distance speed in AU/day
    """
    ts_utc = ensure_utc(ts_utc)
    jd = datetime_to_julian_day(ts_utc)

    if planet_id not in PLANET_IDS:
        raise ValueError(f"Invalid planet_id: {planet_id}")

    swe_id = PLANET_IDS[planet_id]

    with _swe_lock:
        if swe_id < 0:  # Ketu
            (lon, lat, dist, sp_lon, sp_lat, sp_dist), retflag = swe.calc_ut(
                jd, -swe_id, FLAGS
            )
            lon = normalize_angle(lon + 180.0)
            lat = -lat  # Ketu has opposite latitude
        else:
            (lon, lat, dist, sp_lon, sp_lat, sp_dist), retflag = swe.calc_ut(
                jd, swe_id, FLAGS
            )
            lon = normalize_angle(lon)

    return {
        "longitude": lon,
        "latitude": lat,
        "distance": dist,
        "speed_lon": sp_lon,
        "speed_lat": sp_lat,
        "speed_dist": sp_dist,
        "retflag": retflag,
    }


def get_planet_state(speed: float, threshold: float = 0.05) -> int:
    """Determine planet state from speed

    Args:
        speed: Planet speed in degrees/day
        threshold: Speed threshold for stationary state

    Returns:
        State code: 0=direct, 1=retrograde, 2=stationary
    """
    if abs(speed) < threshold:
        return 2  # Stationary
    elif speed < 0:
        return 1  # Retrograde
    else:
        return 0  # Direct


# ============================================================================
# BATCH CALCULATIONS
# ============================================================================


def get_planets_batch(
    ts_utc: datetime, planet_ids: list[int] | None = None
) -> dict[int, dict]:
    """Get positions for multiple planets at once

    Args:
        ts_utc: UTC timestamp
        planet_ids: List of planet IDs (default: all 9 planets)

    Returns:
        Dictionary mapping planet_id to position data
    """
    if planet_ids is None:
        planet_ids = list(range(1, 10))  # All 9 planets

    ts_utc = ensure_utc(ts_utc)
    jd = datetime_to_julian_day(ts_utc)

    results = {}

    with _swe_lock:
        for planet_id in planet_ids:
            if planet_id not in PLANET_IDS:
                warnings.warn(f"Skipping invalid planet_id: {planet_id}")
                continue

            swe_id = PLANET_IDS[planet_id]

            if swe_id < 0:  # Ketu
                (lon, lat, dist, sp_lon, sp_lat, sp_dist), retflag = swe.calc_ut(
                    jd, -swe_id, FLAGS
                )
                lon = normalize_angle(lon + 180.0)
                lat = -lat
            else:
                (lon, lat, dist, sp_lon, sp_lat, sp_dist), retflag = swe.calc_ut(
                    jd, swe_id, FLAGS
                )
                lon = normalize_angle(lon)

            results[planet_id] = {
                "longitude": lon,
                "latitude": lat,
                "distance": dist,
                "speed_lon": sp_lon,
                "speed_lat": sp_lat,
                "speed_dist": sp_dist,
                "state": get_planet_state(sp_lon),
                "name": PLANET_NAMES.get(planet_id, f"Planet_{planet_id}"),
            }

    return results


# ============================================================================
# HOUSE CALCULATIONS (Not used in v1, included for completeness)
# ============================================================================


def get_houses(
    ts_utc: datetime, latitude: float, longitude: float, house_system: bytes = b"P"
) -> tuple[list[float], list[float]]:
    """Calculate house cusps (not used in v1 refactoring)

    Args:
        ts_utc: UTC timestamp
        latitude: Geographic latitude
        longitude: Geographic longitude
        house_system: House system code (P=Placidus)

    Returns:
        (cusps, ascmc) tuple
        - cusps: List of 12 house cusps
        - ascmc: List of angles (ASC, MC, etc.)
    """
    ts_utc = ensure_utc(ts_utc)
    jd = datetime_to_julian_day(ts_utc)

    with _swe_lock:
        cusps, ascmc = swe.houses(jd, latitude, longitude, house_system)

    # Apply sidereal correction to cusps
    ayanamsa = get_ayanamsa_value(ts_utc)
    cusps_sidereal = [(cusp - ayanamsa) % 360.0 for cusp in cusps]
    ascmc_sidereal = [(angle - ayanamsa) % 360.0 for angle in ascmc]

    return cusps_sidereal, ascmc_sidereal


# ============================================================================
# AYANAMSA VALUE
# ============================================================================


def get_ayanamsa_value(ts_utc: datetime) -> float:
    """Get ayanamsa value in degrees for given time

    Args:
        ts_utc: UTC timestamp

    Returns:
        Ayanamsa value in degrees
    """
    ts_utc = ensure_utc(ts_utc)
    jd = datetime_to_julian_day(ts_utc)

    with _swe_lock:
        ayanamsa = swe.get_ayanamsa(jd)

    return ayanamsa


# ============================================================================
# ECLIPSE AND SPECIAL CALCULATIONS
# ============================================================================


def get_eclipse_info(ts_utc: datetime, planet_id: int = 1) -> dict | None:
    """Get eclipse information if any (Sun/Moon only)

    Args:
        ts_utc: UTC timestamp
        planet_id: 1 for Sun, 2 for Moon

    Returns:
        Eclipse info dict or None if no eclipse
    """
    if planet_id not in [1, 2]:
        return None

    ts_utc = ensure_utc(ts_utc)
    jd = datetime_to_julian_day(ts_utc)

    with _swe_lock:
        if planet_id == 1:  # Solar eclipse
            retval = swe.sol_eclipse_when_glob(jd, swe.FLG_SWIEPH)
        else:  # Lunar eclipse
            retval = swe.lun_eclipse_when(jd, swe.FLG_SWIEPH)

    if retval and retval[0] > 0:
        return {
            "type": "solar" if planet_id == 1 else "lunar",
            "max_jd": retval[0],
            "data": retval,
        }

    return None


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def is_planet_retrograde(speed: float) -> bool:
    """Check if planet is retrograde based on speed

    Args:
        speed: Longitude speed in degrees/day

    Returns:
        True if retrograde (negative speed)
    """
    return speed < 0


def is_planet_stationary(speed: float, threshold: float = 0.05) -> bool:
    """Check if planet is stationary

    Args:
        speed: Longitude speed in degrees/day
        threshold: Speed threshold for stationary state

    Returns:
        True if speed is below threshold
    """
    return abs(speed) < threshold


def get_planet_average_speed(planet_id: int) -> float:
    """Get average daily speed for a planet

    Args:
        planet_id: Planet ID (1-9)

    Returns:
        Average speed in degrees/day
    """
    # Average speeds in degrees/day
    avg_speeds = {
        1: 0.9856,  # Sun
        2: 13.1764,  # Moon
        3: 0.0831,  # Jupiter
        4: 0.0529,  # Rahu (mean)
        5: 1.3833,  # Mercury
        6: 1.2000,  # Venus
        7: 0.0529,  # Ketu (mean)
        8: 0.0334,  # Saturn
        9: 0.5240,  # Mars
    }

    return avg_speeds.get(planet_id, 1.0)


# ============================================================================
# EPHEMERIS DATA PATH
# ============================================================================


def set_ephemeris_path(path: str | None = None) -> None:
    """Set custom ephemeris data path

    Args:
        path: Path to ephemeris data files (None for default)
    """
    with _swe_lock:
        if path:
            swe.set_ephe_path(path)
        else:
            # Use default (built-in) ephemeris
            swe.set_ephe_path(None)


def get_ephemeris_path() -> str:
    """Get current ephemeris data path"""
    # Swiss Ephemeris doesn't provide a getter, so we track it
    # For now, return a placeholder
    return "default"
