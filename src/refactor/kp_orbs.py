#!/usr/bin/env python3
"""
KP Orbs and Bhava Sandhi Module
Handles cusp orbs, bhava sandhi (house junctions), and effective house positions
"""

from dataclasses import dataclass
from enum import Enum

from .constants import PLANET_NAMES


class HousePosition(Enum):
    """Planet's position relative to house cusp"""

    DEEP = "deep"  # Well within house (>10° from cusps)
    MIDDLE = "middle"  # Middle of house (5-10° from cusps)
    EARLY = "early"  # Early degrees (within 5° of previous cusp)
    LATE = "late"  # Late degrees (within 5° of next cusp)
    SANDHI = "sandhi"  # In bhava sandhi (junction between houses)


@dataclass
class PlanetHousePosition:
    """Detailed house position analysis for a planet"""

    planet_id: int
    planet_name: str
    longitude: float
    primary_house: int  # Main house occupied
    secondary_house: int | None  # If in sandhi, the other house
    position_type: HousePosition
    distance_from_cusp: float  # Degrees from nearest cusp
    orb_strength: float  # How strongly planet influences the house

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "planet": self.planet_name,
            "longitude": round(self.longitude, 2),
            "primary_house": self.primary_house,
            "secondary_house": self.secondary_house,
            "position": self.position_type.value,
            "cusp_distance": round(self.distance_from_cusp, 2),
            "orb_strength": round(self.orb_strength, 2),
        }


@dataclass
class CuspAspect:
    """Aspect from planet to house cusp"""

    planet_id: int
    planet_name: str
    cusp_house: int
    aspect_type: str  # conjunction, opposition, trine, etc.
    orb: float  # Degrees of separation
    strength: float  # Aspect strength based on orb

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "planet": self.planet_name,
            "cusp_house": self.cusp_house,
            "aspect": self.aspect_type,
            "orb": round(self.orb, 2),
            "strength": round(self.strength, 2),
        }


# KP Standard Orbs
KP_CUSP_ORB = 5.0  # Standard orb around cusps
KP_SANDHI_ORB = 2.5  # Tighter orb for bhava sandhi
KP_ASPECT_ORBS = {
    "conjunction": 8.0,
    "opposition": 8.0,
    "trine": 6.0,
    "square": 6.0,
    "sextile": 4.0,
    "quincunx": 2.0,
}


def get_effective_house_position(
    planet_longitude: float, house_cusps: list[float], orb: float = KP_CUSP_ORB
) -> tuple[int, HousePosition, int | None]:
    """
    Determine the effective house position of a planet considering orbs.

    In KP, planets near cusps have influence on both houses.
    Within 5° of cusp = bhava sandhi (weak for results)

    Args:
        planet_longitude: Planet's longitude in degrees
        house_cusps: List of 12 house cusp positions
        orb: Orb to use around cusps (default 5°)

    Returns:
        Tuple of (primary_house, position_type, secondary_house)
    """
    # Normalize longitude
    planet_long = planet_longitude % 360

    # Find which house the planet is in
    primary_house = 0
    for i in range(12):
        cusp1 = house_cusps[i]
        cusp2 = house_cusps[(i + 1) % 12]

        # Handle wrap around 360°
        if cusp1 > cusp2:  # Crosses 0°
            if planet_long >= cusp1 or planet_long < cusp2:
                primary_house = i + 1
                break
        else:
            if cusp1 <= planet_long < cusp2:
                primary_house = i + 1
                break

    if primary_house == 0:  # Fallback
        primary_house = 1

    # Check distance from cusps
    prev_house = primary_house - 1 if primary_house > 1 else 12
    next_house = primary_house + 1 if primary_house < 12 else 1

    prev_cusp = house_cusps[prev_house - 1]
    current_cusp = house_cusps[primary_house - 1]
    next_cusp = house_cusps[next_house - 1]

    # Calculate angular distances
    dist_from_prev = _angular_distance(planet_long, prev_cusp)
    dist_from_current = _angular_distance(planet_long, current_cusp)
    dist_from_next = _angular_distance(planet_long, next_cusp)

    # Determine position type
    position_type = HousePosition.MIDDLE
    secondary_house = None

    # Check if in bhava sandhi (within orb of cusps)
    if dist_from_current <= orb:
        # Just past the cusp, early degrees
        position_type = HousePosition.EARLY
        if dist_from_current <= KP_SANDHI_ORB:
            position_type = HousePosition.SANDHI
            secondary_house = prev_house
    elif dist_from_next <= orb:
        # Approaching next cusp, late degrees
        position_type = HousePosition.LATE
        if dist_from_next <= KP_SANDHI_ORB:
            position_type = HousePosition.SANDHI
            secondary_house = next_house
    elif dist_from_current > 15 and dist_from_next > 15:
        # Deep in the house
        position_type = HousePosition.DEEP

    return primary_house, position_type, secondary_house


def is_in_bhava_sandhi(
    planet_longitude: float, house_cusps: list[float], orb: float = KP_SANDHI_ORB
) -> bool:
    """
    Check if a planet is in bhava sandhi (house junction).

    Planets in bhava sandhi are weak for giving house results.

    Args:
        planet_longitude: Planet's longitude
        house_cusps: House cusp positions
        orb: Orb for sandhi (default 2.5°)

    Returns:
        True if planet is in bhava sandhi
    """
    _, position_type, _ = get_effective_house_position(
        planet_longitude, house_cusps, orb
    )
    return position_type == HousePosition.SANDHI


def get_cusp_aspects(
    planet_longitude: float,
    house_cusps: list[float],
    planet_id: int,
    aspect_orbs: dict[str, float] | None = None,
) -> list[CuspAspect]:
    """
    Find aspects from a planet to house cusps.

    In KP, aspects to cusps activate house matters.

    Args:
        planet_longitude: Planet's longitude
        house_cusps: House cusp positions
        planet_id: Planet ID for identification
        aspect_orbs: Custom orbs (uses KP defaults if None)

    Returns:
        List of CuspAspect objects
    """
    if aspect_orbs is None:
        aspect_orbs = KP_ASPECT_ORBS

    aspects = []
    planet_name = PLANET_NAMES.get(planet_id, str(planet_id))

    # Check each cusp
    for house_num in range(1, 13):
        cusp_deg = house_cusps[house_num - 1]

        # Calculate separation
        separation = _angular_distance(planet_longitude, cusp_deg)

        # Check each aspect type
        for aspect_type, max_orb in aspect_orbs.items():
            aspect_angle = _get_aspect_angle(aspect_type)

            # Check if within orb
            if abs(separation - aspect_angle) <= max_orb:
                orb = abs(separation - aspect_angle)
                strength = _calculate_aspect_strength(orb, max_orb)

                aspects.append(
                    CuspAspect(
                        planet_id=planet_id,
                        planet_name=planet_name,
                        cusp_house=house_num,
                        aspect_type=aspect_type,
                        orb=orb,
                        strength=strength,
                    )
                )

    return aspects


def calculate_house_strength_from_occupants(
    house_num: int, planet_positions: dict[int, dict], house_cusps: list[float]
) -> float:
    """
    Calculate house strength based on occupant positions.

    Planets deep in house = full strength
    Planets in sandhi = reduced strength

    Args:
        house_num: House number to analyze
        planet_positions: All planet data
        house_cusps: House cusp positions

    Returns:
        House strength score (0-100)
    """
    strength = 0.0
    occupant_count = 0

    for planet_id, data in planet_positions.items():
        planet_long = data.get("longitude", 0)

        # Get house position
        primary_house, position_type, secondary_house = get_effective_house_position(
            planet_long, house_cusps
        )

        # Check if in target house
        if primary_house == house_num:
            occupant_count += 1

            # Add strength based on position
            if position_type == HousePosition.DEEP:
                strength += 20  # Full strength
            elif position_type == HousePosition.MIDDLE:
                strength += 15  # Good strength
            elif position_type in [HousePosition.EARLY, HousePosition.LATE]:
                strength += 10  # Moderate strength
            elif position_type == HousePosition.SANDHI:
                strength += 5  # Weak strength

            # Natural benefics add more strength
            if planet_id in {1, 2, 3, 5, 6}:  # Sun, Moon, Jupiter, Mercury, Venus
                strength += 5

        # If in sandhi with this house as secondary
        elif secondary_house == house_num:
            occupant_count += 0.5
            strength += 3  # Minimal strength

    # Bonus for multiple occupants
    if occupant_count >= 2:
        strength *= 1.2
    elif occupant_count >= 3:
        strength *= 1.5

    return min(100.0, strength)


def get_planets_in_house_with_orbs(
    house_num: int,
    planet_positions: dict[int, dict],
    house_cusps: list[float],
    include_sandhi: bool = True,
) -> list[PlanetHousePosition]:
    """
    Get all planets in a house, including those in orb.

    Args:
        house_num: House to check
        planet_positions: All planet data
        house_cusps: House cusp positions
        include_sandhi: Whether to include planets in sandhi

    Returns:
        List of PlanetHousePosition objects
    """
    planets_in_house = []

    for planet_id, data in planet_positions.items():
        planet_long = data.get("longitude", 0)
        planet_name = PLANET_NAMES.get(planet_id, str(planet_id))

        # Get house position
        primary_house, position_type, secondary_house = get_effective_house_position(
            planet_long, house_cusps
        )

        # Check if in target house
        include = False
        if primary_house == house_num:
            include = True
        elif include_sandhi and secondary_house == house_num:
            include = True

        if include:
            # Calculate distance from cusp
            cusp_deg = house_cusps[house_num - 1]
            distance = _angular_distance(planet_long, cusp_deg)

            # Calculate orb strength
            if distance <= KP_SANDHI_ORB:
                orb_strength = 100.0  # Very strong if on cusp
            elif distance <= KP_CUSP_ORB:
                orb_strength = 80.0  # Strong if within standard orb
            elif position_type == HousePosition.DEEP:
                orb_strength = 60.0  # Moderate if deep
            else:
                orb_strength = 40.0  # Weak otherwise

            planets_in_house.append(
                PlanetHousePosition(
                    planet_id=planet_id,
                    planet_name=planet_name,
                    longitude=planet_long,
                    primary_house=primary_house,
                    secondary_house=secondary_house,
                    position_type=position_type,
                    distance_from_cusp=distance,
                    orb_strength=orb_strength,
                )
            )

    # Sort by orb strength
    planets_in_house.sort(key=lambda x: x.orb_strength, reverse=True)

    return planets_in_house


def find_planets_on_angles(
    planet_positions: dict[int, dict], house_cusps: list[float], orb: float = 5.0
) -> dict[str, list[int]]:
    """
    Find planets on angles (1st, 4th, 7th, 10th cusps).

    Planets on angles are very powerful in KP.

    Args:
        planet_positions: All planet data
        house_cusps: House cusp positions
        orb: Orb to use for angles

    Returns:
        Dictionary mapping angle name to list of planets
    """
    angles = {
        "ascendant": (1, house_cusps[0]),
        "ic": (4, house_cusps[3]),
        "descendant": (7, house_cusps[6]),
        "midheaven": (10, house_cusps[9]),
    }

    planets_on_angles = {name: [] for name in angles}

    for planet_id, data in planet_positions.items():
        planet_long = data.get("longitude", 0)

        for angle_name, (house_num, cusp_deg) in angles.items():
            distance = _angular_distance(planet_long, cusp_deg)

            if distance <= orb:
                planets_on_angles[angle_name].append(planet_id)

    return planets_on_angles


# Helper functions


def _angular_distance(long1: float, long2: float) -> float:
    """Calculate shortest angular distance between two longitudes"""
    diff = abs(long1 - long2)
    if diff > 180:
        diff = 360 - diff
    return diff


def _get_aspect_angle(aspect_type: str) -> float:
    """Get the angle for an aspect type"""
    angles = {
        "conjunction": 0,
        "opposition": 180,
        "trine": 120,
        "square": 90,
        "sextile": 60,
        "quincunx": 150,
        "semisextile": 30,
        "semisquare": 45,
        "sesquiquadrate": 135,
    }
    return angles.get(aspect_type, 0)


def _calculate_aspect_strength(orb: float, max_orb: float) -> float:
    """Calculate aspect strength based on orb"""
    if max_orb == 0:
        return 0.0

    # Linear decrease from 100% at 0° orb to 0% at max orb
    strength = (1 - orb / max_orb) * 100
    return max(0.0, min(100.0, strength))
