#!/usr/bin/env python3
"""
KP Significator Hierarchy Module
Implements the complete KP significator system for house and planet relationships
"""


from collections import defaultdict
from dataclasses import dataclass

from .constants import PLANET_NAMES


@dataclass
class SignificatorData:
    """Complete significator analysis for a chart"""

    house_significators: dict[
        int, list[tuple[int, str, float]]
    ]  # house -> [(planet, level, strength)]
    planet_significations: dict[int, list[int]]  # planet -> [houses]
    significator_matrix: dict[int, dict[int, float]]  # planet -> house -> strength
    primary_significators: dict[int, list[int]]  # house -> [strongest planets]

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "house_significators": {
                house: [
                    {
                        "planet": planet,
                        "planet_name": PLANET_NAMES.get(planet, str(planet)),
                        "level": level,
                        "strength": round(strength, 2),
                    }
                    for planet, level, strength in sigs
                ]
                for house, sigs in self.house_significators.items()
            },
            "planet_significations": {
                planet: houses for planet, houses in self.planet_significations.items()
            },
            "primary_significators": self.primary_significators,
        }


def get_house_significators(
    house_num: int,
    planet_positions: dict[int, dict],
    house_cusps: list[float],
    aspects: dict | None = None,
) -> list[tuple[int, str, float]]:
    """
    Get all significators for a house in KP hierarchy order.

    KP Significator Levels (strongest to weakest):
    1. Planets in the star of occupants (A grade)
    2. Occupants of the house (B grade)
    3. Planets in the star of owner (C grade)
    4. Owner of the house (D grade)
    5. Planets aspecting the house (E grade)

    Args:
        house_num: House number (1-12)
        planet_positions: Dict with planet data including house, nakshatra info
        house_cusps: List of 12 house cusp positions
        aspects: Optional aspect data

    Returns:
        List of (planet_id, level, strength) tuples sorted by strength
    """
    significators = []

    # Level 1: Find occupants of the house
    occupants = _get_house_occupants(house_num, planet_positions)

    # Level 2: Find planets in stars of occupants (strongest)
    for occupant in occupants:
        planets_in_star = _get_planets_in_star_of(occupant, planet_positions)
        for planet in planets_in_star:
            significators.append((planet, "star_of_occupant", 100.0))

    # Level 3: Add occupants themselves
    for occupant in occupants:
        significators.append((occupant, "occupant", 75.0))

    # Level 4: Find owner of the house
    owner = _get_house_owner(house_num)

    # Level 5: Find planets in star of owner
    if owner:
        planets_in_star = _get_planets_in_star_of(owner, planet_positions)
        for planet in planets_in_star:
            if (planet, "star_of_occupant", 100.0) not in significators:
                significators.append((planet, "star_of_owner", 50.0))

    # Level 6: Add owner itself
    if owner and (owner, "occupant", 75.0) not in significators:
        significators.append((owner, "owner", 25.0))

    # Level 7: Planets aspecting the house (if aspects provided)
    if aspects:
        aspecting_planets = _get_aspecting_planets(
            house_num, house_cusps, planet_positions, aspects
        )
        for planet in aspecting_planets:
            # Check if not already a significator
            existing = [p for p, _, _ in significators]
            if planet not in existing:
                significators.append((planet, "aspect", 10.0))

    # Sort by strength (descending)
    significators.sort(key=lambda x: x[2], reverse=True)

    return significators


def get_planet_significations(
    planet_id: int, planet_positions: dict[int, dict], house_cusps: list[float]
) -> list[int]:
    """
    Get all houses a planet signifies.

    A planet signifies houses through:
    1. Occupation (being placed in house)
    2. Ownership (ruling the sign on cusp)
    3. Star lord's position (nakshatra dispositor)
    4. Aspects to houses

    Args:
        planet_id: Planet ID to analyze
        planet_positions: All planet data
        house_cusps: House cusp positions

    Returns:
        List of house numbers this planet signifies
    """
    signified_houses = set()

    if planet_id not in planet_positions:
        return []

    planet_data = planet_positions[planet_id]

    # 1. House occupied by planet
    occupied_house = planet_data.get("house", 0)
    if occupied_house > 0:
        signified_houses.add(occupied_house)

    # 2. Houses owned by planet
    owned_houses = _get_houses_owned_by(planet_id, house_cusps)
    signified_houses.update(owned_houses)

    # 3. House of star lord (nakshatra dispositor)
    star_lord = planet_data.get("nl", 0)  # Nakshatra lord
    if star_lord > 0 and star_lord in planet_positions:
        star_lord_house = planet_positions[star_lord].get("house", 0)
        if star_lord_house > 0:
            signified_houses.add(star_lord_house)

    # 4. House of sub lord
    sub_lord = planet_data.get("sl", 0)
    if sub_lord > 0 and sub_lord in planet_positions:
        sub_lord_house = planet_positions[sub_lord].get("house", 0)
        if sub_lord_house > 0:
            signified_houses.add(sub_lord_house)

    return sorted(list(signified_houses))


def build_significator_matrix(
    planet_positions: dict[int, dict],
    house_cusps: list[float],
    aspects: dict | None = None,
) -> dict[int, dict[int, float]]:
    """
    Build complete planet-to-house significator matrix.

    Returns a matrix showing strength of connection between
    each planet and each house.

    Args:
        planet_positions: All planet data
        house_cusps: House cusp positions
        aspects: Optional aspect data

    Returns:
        Matrix: planet_id -> house_num -> strength (0-100)
    """
    matrix = defaultdict(lambda: defaultdict(float))

    # For each house, get its significators
    for house in range(1, 13):
        significators = get_house_significators(
            house, planet_positions, house_cusps, aspects
        )

        # Add to matrix
        for planet, level, strength in significators:
            # Take maximum strength if planet signifies house multiple ways
            matrix[planet][house] = max(matrix[planet][house], strength)

    # Convert to regular dict
    return {planet: dict(houses) for planet, houses in matrix.items()}


def get_primary_significators(
    house_num: int, significators: list[tuple[int, str, float]], max_planets: int = 3
) -> list[int]:
    """
    Get the primary (strongest) significators for a house.

    In KP, typically the top 3-4 significators are considered
    primary for timing purposes.

    Args:
        house_num: House number
        significators: Full list of significators
        max_planets: Maximum number to return

    Returns:
        List of planet IDs
    """
    # Filter for minimum strength threshold
    strong_sigs = [
        (planet, level, strength)
        for planet, level, strength in significators
        if strength >= 25.0  # At least "owner" level
    ]

    # Return top N planets
    return [planet for planet, _, _ in strong_sigs[:max_planets]]


def evaluate_significator_strength(
    planet_id: int,
    house_num: int,
    planet_positions: dict[int, dict],
    house_cusps: list[float],
) -> float:
    """
    Evaluate the strength of a planet as significator for a house.

    Detailed strength calculation considering:
    - Significator level (star of occupant = 100%)
    - Number of connections to house
    - Planet's own strength (speed, dignity)

    Args:
        planet_id: Planet to evaluate
        house_num: House in question
        planet_positions: All planet data
        house_cusps: House cusp positions

    Returns:
        Strength score (0-100)
    """
    strength = 0.0
    connections = 0

    # Get all significators for this house
    all_sigs = get_house_significators(house_num, planet_positions, house_cusps)

    # Find this planet's entries
    for p, level, s in all_sigs:
        if p == planet_id:
            strength = max(strength, s)
            connections += 1

    # Bonus for multiple connections
    if connections > 1:
        strength = min(100.0, strength * (1 + 0.1 * (connections - 1)))

    # Adjust for planet's condition
    if planet_id in planet_positions:
        planet_data = planet_positions[planet_id]

        # Retrograde reduces strength
        if planet_data.get("speed", 0) < 0:
            strength *= 0.8

        # Fast planets are stronger
        avg_speed = _get_average_speed(planet_id)
        actual_speed = abs(planet_data.get("speed", avg_speed))
        if actual_speed > avg_speed * 1.2:
            strength *= 1.1

    return min(100.0, strength)


def get_complete_significator_data(
    planet_positions: dict[int, dict],
    house_cusps: list[float],
    aspects: dict | None = None,
) -> SignificatorData:
    """
    Generate complete significator analysis for a chart.

    Args:
        planet_positions: All planet data
        house_cusps: House cusp positions
        aspects: Optional aspect data

    Returns:
        SignificatorData object with all relationships
    """
    house_significators = {}
    planet_significations = {}
    primary_significators = {}

    # Build house significators
    for house in range(1, 13):
        sigs = get_house_significators(house, planet_positions, house_cusps, aspects)
        house_significators[house] = sigs
        primary_significators[house] = get_primary_significators(house, sigs)

    # Build planet significations
    for planet_id in planet_positions.keys():
        planet_significations[planet_id] = get_planet_significations(
            planet_id, planet_positions, house_cusps
        )

    # Build matrix
    matrix = build_significator_matrix(planet_positions, house_cusps, aspects)

    return SignificatorData(
        house_significators=house_significators,
        planet_significations=planet_significations,
        significator_matrix=matrix,
        primary_significators=primary_significators,
    )


# Helper functions


def _get_house_occupants(
    house_num: int, planet_positions: dict[int, dict]
) -> list[int]:
    """Get planets occupying a house"""
    occupants = []
    for planet_id, data in planet_positions.items():
        if data.get("house") == house_num:
            occupants.append(planet_id)
    return occupants


def _get_planets_in_star_of(
    star_lord: int, planet_positions: dict[int, dict]
) -> list[int]:
    """Get planets in the nakshatra of a given planet"""
    planets = []

    # Get nakshatras ruled by this planet
    star_lord_nakshatras = _get_nakshatras_ruled_by(star_lord)

    for planet_id, data in planet_positions.items():
        planet_nak = data.get("nakshatra", 0)
        if planet_nak in star_lord_nakshatras:
            planets.append(planet_id)

    return planets


def _get_nakshatras_ruled_by(planet_id: int) -> set[int]:
    """Get nakshatra numbers ruled by a planet"""
    nakshatra_lords = {
        1: {3, 12, 21},  # Sun: Krittika, Uttara Phalguni, Uttara Ashadha
        2: {4, 13, 22},  # Moon: Rohini, Hasta, Shravana
        3: {7, 16, 25},  # Jupiter: Punarvasu, Vishakha, Purva Bhadrapada
        4: {6, 15, 24},  # Rahu: Ardra, Swati, Shatabhisha
        5: {9, 18, 27},  # Mercury: Ashlesha, Jyeshtha, Revati
        6: {2, 11, 20},  # Venus: Bharani, Purva Phalguni, Purva Ashadha
        7: {1, 10, 19},  # Ketu: Ashwini, Magha, Moola
        8: {8, 17, 26},  # Saturn: Pushya, Anuradha, Uttara Bhadrapada
        9: {5, 14, 23},  # Mars: Mrigashira, Chitra, Dhanishta
    }
    return nakshatra_lords.get(planet_id, set())


def _get_house_owner(house_num: int) -> int | None:
    """Get the owner of a house based on sign on cusp"""
    # This maps house number to sign, then sign to ruler
    # In actual implementation, would check the actual sign on cusp
    sign_lords = {
        1: 9,  # Aries - Mars
        2: 6,  # Taurus - Venus
        3: 5,  # Gemini - Mercury
        4: 2,  # Cancer - Moon
        5: 1,  # Leo - Sun
        6: 5,  # Virgo - Mercury
        7: 6,  # Libra - Venus
        8: 9,  # Scorpio - Mars
        9: 3,  # Sagittarius - Jupiter
        10: 8,  # Capricorn - Saturn
        11: 8,  # Aquarius - Saturn
        12: 3,  # Pisces - Jupiter
    }

    # For now, using natural zodiac
    # In full implementation, would calculate from actual cusp position
    sign = house_num  # Simplified: house 1 = Aries, etc.
    return sign_lords.get(sign)


def _get_houses_owned_by(planet_id: int, house_cusps: list[float]) -> list[int]:
    """Get houses owned by a planet"""
    planet_signs = {
        1: [5],  # Sun owns Leo
        2: [4],  # Moon owns Cancer
        3: [9, 12],  # Jupiter owns Sagittarius, Pisces
        4: [],  # Rahu owns no signs
        5: [3, 6],  # Mercury owns Gemini, Virgo
        6: [2, 7],  # Venus owns Taurus, Libra
        7: [],  # Ketu owns no signs
        8: [10, 11],  # Saturn owns Capricorn, Aquarius
        9: [1, 8],  # Mars owns Aries, Scorpio
    }

    owned_houses = []
    signs = planet_signs.get(planet_id, [])

    # Check each house cusp
    for house_num in range(1, 13):
        cusp_deg = house_cusps[house_num - 1]
        cusp_sign = int(cusp_deg / 30) + 1
        if cusp_sign in signs:
            owned_houses.append(house_num)

    return owned_houses


def _get_aspecting_planets(
    house_num: int,
    house_cusps: list[float],
    planet_positions: dict[int, dict],
    aspects: dict,
) -> list[int]:
    """Get planets aspecting a house"""
    # Simplified: check if any planet aspects the house cusp
    # In full implementation, would check aspects to cusp degree
    aspecting = []

    cusp_deg = house_cusps[house_num - 1]

    # Check each planet
    for planet_id, data in planet_positions.items():
        planet_deg = data.get("longitude", 0)

        # Check for aspect (simplified - just opposition and trine)
        diff = abs(planet_deg - cusp_deg)
        if diff > 180:
            diff = 360 - diff

        # Opposition (180° ± 10°)
        if 170 <= diff <= 190:
            aspecting.append(planet_id)
        # Trine (120° ± 9°)
        elif 111 <= diff <= 129:
            aspecting.append(planet_id)
        # Square (90° ± 8°)
        elif 82 <= diff <= 98:
            aspecting.append(planet_id)

    return aspecting


def _get_average_speed(planet_id: int) -> float:
    """Get average daily speed for a planet"""
    avg_speeds = {
        1: 0.9856,  # Sun
        2: 13.176,  # Moon
        3: 0.0831,  # Jupiter
        4: 0.053,  # Rahu (mean)
        5: 1.383,  # Mercury
        6: 1.2,  # Venus
        7: 0.053,  # Ketu (mean)
        8: 0.0334,  # Saturn
        9: 0.524,  # Mars
    }
    return avg_speeds.get(planet_id, 1.0)
