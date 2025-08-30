#!/usr/bin/env python3
"""
KP Star Links Module
Handles nakshatra (star) relationships and depositor chains in KP system
"""

from collections import defaultdict
from dataclasses import dataclass

from .constants import PLANET_NAMES


@dataclass
class StarLinkData:
    """Complete star link analysis for a chart"""

    planets_in_stars: dict[int, list[int]]  # star_lord -> [planets]
    depositor_chains: dict[int, list[int]]  # planet -> [chain]
    star_to_house: dict[int, dict]  # star_lord -> house connections
    mutual_stars: list[tuple[int, int]]  # [(planet1, planet2)] in mutual stars
    star_strength: dict[int, float]  # star_lord -> strength score

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "planets_in_stars": {
                PLANET_NAMES.get(star_lord, str(star_lord)): [
                    PLANET_NAMES.get(p, str(p)) for p in planets
                ]
                for star_lord, planets in self.planets_in_stars.items()
            },
            "depositor_chains": {
                PLANET_NAMES.get(planet, str(planet)): [
                    PLANET_NAMES.get(p, str(p)) for p in chain
                ]
                for planet, chain in self.depositor_chains.items()
            },
            "star_to_house": self.star_to_house,
            "mutual_stars": [
                (PLANET_NAMES.get(p1, str(p1)), PLANET_NAMES.get(p2, str(p2)))
                for p1, p2 in self.mutual_stars
            ],
            "star_strength": {
                PLANET_NAMES.get(star_lord, str(star_lord)): round(strength, 2)
                for star_lord, strength in self.star_strength.items()
            },
        }


def get_planets_in_star(star_lord: int, planet_positions: dict[int, dict]) -> list[int]:
    """
    Get all planets positioned in the nakshatras of a given planet.

    Each planet rules 3 nakshatras in the 27-nakshatra system.

    Args:
        star_lord: Planet ID whose nakshatras to check
        planet_positions: Dictionary with planet data including nakshatra

    Returns:
        List of planet IDs in this star lord's nakshatras
    """
    # Get nakshatras ruled by this planet
    ruled_nakshatras = _get_ruled_nakshatras(star_lord)

    planets_in_star = []
    for planet_id, data in planet_positions.items():
        nakshatra = data.get("nakshatra", 0)
        if nakshatra in ruled_nakshatras:
            planets_in_star.append(planet_id)

    return planets_in_star


def get_depositor_chain(
    planet_id: int, planet_positions: dict[int, dict], max_depth: int = 5
) -> list[int]:
    """
    Get the depositor chain for a planet.

    Chain follows: Planet → Star Lord → Star Lord's Star Lord → ...
    Stops when cycle detected or max depth reached.

    Args:
        planet_id: Starting planet
        planet_positions: All planet data
        max_depth: Maximum chain length

    Returns:
        List of planets in depositor chain
    """
    if planet_id not in planet_positions:
        return []

    chain = [planet_id]
    seen = {planet_id}
    current = planet_id

    for _ in range(max_depth):
        # Get star lord of current planet
        current_data = planet_positions.get(current, {})
        star_lord = current_data.get("nl", 0)  # Nakshatra lord

        if not star_lord or star_lord not in planet_positions:
            break

        # Check for cycle
        if star_lord in seen:
            # Optionally append to show the cycle
            chain.append(star_lord)
            break

        chain.append(star_lord)
        seen.add(star_lord)
        current = star_lord

    return chain


def get_star_to_house_connections(
    planet_positions: dict[int, dict], house_cusps: list[float]
) -> dict[int, dict]:
    """
    Map star lords to their house connections.

    Shows which houses are influenced by planets in each star lord's nakshatras.

    Args:
        planet_positions: All planet data
        house_cusps: House cusp positions

    Returns:
        Dictionary mapping star_lord -> house connection data
    """
    star_connections = defaultdict(
        lambda: {
            "planets_in_star": [],
            "houses_occupied": set(),
            "houses_owned": set(),
            "strength": 0.0,
        }
    )

    # For each planet that rules nakshatras
    for star_lord in range(1, 10):  # Planets 1-9
        planets_in_star = get_planets_in_star(star_lord, planet_positions)

        if not planets_in_star:
            continue

        star_data = star_connections[star_lord]
        star_data["planets_in_star"] = planets_in_star

        # Collect houses occupied by planets in this star
        for planet in planets_in_star:
            if planet in planet_positions:
                house = planet_positions[planet].get("house", 0)
                if house > 0:
                    star_data["houses_occupied"].add(house)

                # Also get houses owned by these planets
                owned = _get_houses_owned_by_planet(planet, house_cusps)
                star_data["houses_owned"].update(owned)

        # Calculate strength based on number of planets and houses
        star_data["strength"] = (
            len(planets_in_star) * 10
            + len(star_data["houses_occupied"]) * 5
            + len(star_data["houses_owned"]) * 3
        )

        # Convert sets to lists for JSON serialization
        star_data["houses_occupied"] = list(star_data["houses_occupied"])
        star_data["houses_owned"] = list(star_data["houses_owned"])

    return dict(star_connections)


def find_mutual_star_connections(
    planet_positions: dict[int, dict],
) -> list[tuple[int, int]]:
    """
    Find planets in mutual nakshatra exchange.

    Example: If Mars is in Venus's nakshatra and Venus is in Mars's nakshatra.

    Args:
        planet_positions: All planet data

    Returns:
        List of planet pairs in mutual star exchange
    """
    mutual_pairs = []
    checked = set()

    for planet1 in planet_positions:
        for planet2 in planet_positions:
            if planet1 >= planet2:  # Avoid duplicates and self-comparison
                continue

            pair = tuple(sorted([planet1, planet2]))
            if pair in checked:
                continue
            checked.add(pair)

            # Check if planet1 is in planet2's star
            p1_data = planet_positions[planet1]
            p1_star_lord = p1_data.get("nl", 0)

            # Check if planet2 is in planet1's star
            p2_data = planet_positions[planet2]
            p2_star_lord = p2_data.get("nl", 0)

            # Mutual exchange exists if each is in other's star
            if p1_star_lord == planet2 and p2_star_lord == planet1:
                mutual_pairs.append(pair)

    return mutual_pairs


def analyze_star_strength(star_lord: int, planet_positions: dict[int, dict]) -> float:
    """
    Calculate the strength of a star lord based on occupants.

    Factors:
    - Number of planets in star
    - Nature of planets (benefic/malefic)
    - Speed and dignity of planets

    Args:
        star_lord: Star lord planet ID
        planet_positions: All planet data

    Returns:
        Strength score (0-100)
    """
    planets_in_star = get_planets_in_star(star_lord, planet_positions)

    if not planets_in_star:
        return 0.0

    strength = 0.0

    # Base strength from number of planets
    strength += len(planets_in_star) * 15

    # Analyze each planet in star
    for planet in planets_in_star:
        if planet not in planet_positions:
            continue

        planet_data = planet_positions[planet]

        # Benefic planets add strength
        if planet in {1, 2, 3, 5, 6}:  # Sun, Moon, Jupiter, Mercury, Venus
            strength += 10

        # Direct motion adds strength
        if planet_data.get("speed", 0) > 0:
            strength += 5

        # Strong house placement (angles, trines)
        house = planet_data.get("house", 0)
        if house in {1, 4, 7, 10}:  # Angles
            strength += 8
        elif house in {5, 9}:  # Trines
            strength += 6

    # Star lord's own condition
    if star_lord in planet_positions:
        star_lord_data = planet_positions[star_lord]

        # Star lord in good house
        house = star_lord_data.get("house", 0)
        if house in {1, 2, 4, 5, 9, 10, 11}:
            strength += 10

        # Star lord direct
        if star_lord_data.get("speed", 0) > 0:
            strength += 5

    return min(100.0, strength)


def get_complete_star_link_data(
    planet_positions: dict[int, dict], house_cusps: list[float]
) -> StarLinkData:
    """
    Generate complete star link analysis for a chart.

    Args:
        planet_positions: All planet data
        house_cusps: House cusp positions

    Returns:
        StarLinkData object with all star relationships
    """
    # Build planets in stars mapping
    planets_in_stars = {}
    for star_lord in range(1, 10):
        planets = get_planets_in_star(star_lord, planet_positions)
        if planets:
            planets_in_stars[star_lord] = planets

    # Build depositor chains
    depositor_chains = {}
    for planet_id in planet_positions:
        chain = get_depositor_chain(planet_id, planet_positions)
        if len(chain) > 1:  # Only include if there's an actual chain
            depositor_chains[planet_id] = chain

    # Get star to house connections
    star_to_house = get_star_to_house_connections(planet_positions, house_cusps)

    # Find mutual star connections
    mutual_stars = find_mutual_star_connections(planet_positions)

    # Calculate star strength
    star_strength = {}
    for star_lord in range(1, 10):
        strength = analyze_star_strength(star_lord, planet_positions)
        if strength > 0:
            star_strength[star_lord] = strength

    return StarLinkData(
        planets_in_stars=planets_in_stars,
        depositor_chains=depositor_chains,
        star_to_house=star_to_house,
        mutual_stars=mutual_stars,
        star_strength=star_strength,
    )


def is_star_chain_favorable(
    chain: list[int], planet_positions: dict[int, dict]
) -> bool:
    """
    Determine if a depositor chain is favorable.

    Favorable if:
    - Chain includes benefics
    - Planets in good houses
    - No severe afflictions

    Args:
        chain: Depositor chain
        planet_positions: All planet data

    Returns:
        True if chain is favorable
    """
    if not chain:
        return False

    benefic_count = 0
    malefic_count = 0
    good_houses = 0
    bad_houses = 0

    for planet in chain:
        if planet not in planet_positions:
            continue

        # Check nature
        if planet in {1, 2, 3, 5, 6}:  # Benefics
            benefic_count += 1
        elif planet in {4, 7, 8, 9}:  # Malefics
            malefic_count += 1

        # Check house
        house = planet_positions[planet].get("house", 0)
        if house in {1, 2, 4, 5, 9, 10, 11}:
            good_houses += 1
        elif house in {6, 8, 12}:
            bad_houses += 1

    # Favorable if benefics and good houses outweigh negatives
    return (benefic_count + good_houses) > (malefic_count + bad_houses)


# Helper functions


def _get_ruled_nakshatras(planet_id: int) -> set[int]:
    """Get the nakshatras ruled by a planet"""
    nakshatra_rulership = {
        1: {3, 12, 21},  # Sun: Krittika, U.Phalguni, U.Ashadha
        2: {4, 13, 22},  # Moon: Rohini, Hasta, Shravana
        3: {7, 16, 25},  # Jupiter: Punarvasu, Vishakha, P.Bhadrapada
        4: {6, 15, 24},  # Rahu: Ardra, Swati, Shatabhisha
        5: {9, 18, 27},  # Mercury: Ashlesha, Jyeshtha, Revati
        6: {2, 11, 20},  # Venus: Bharani, P.Phalguni, P.Ashadha
        7: {1, 10, 19},  # Ketu: Ashwini, Magha, Moola
        8: {8, 17, 26},  # Saturn: Pushya, Anuradha, U.Bhadrapada
        9: {5, 14, 23},  # Mars: Mrigashira, Chitra, Dhanishta
    }
    return nakshatra_rulership.get(planet_id, set())


def _get_houses_owned_by_planet(planet_id: int, house_cusps: list[float]) -> list[int]:
    """Get houses owned by a planet based on cusps"""
    # Planet to sign rulership
    planet_signs = {
        1: [5],  # Sun: Leo
        2: [4],  # Moon: Cancer
        3: [9, 12],  # Jupiter: Sagittarius, Pisces
        4: [],  # Rahu: No signs
        5: [3, 6],  # Mercury: Gemini, Virgo
        6: [2, 7],  # Venus: Taurus, Libra
        7: [],  # Ketu: No signs
        8: [10, 11],  # Saturn: Capricorn, Aquarius
        9: [1, 8],  # Mars: Aries, Scorpio
    }

    owned_houses = []
    signs = planet_signs.get(planet_id, [])

    for house_num in range(1, 13):
        cusp_deg = house_cusps[house_num - 1]
        cusp_sign = int(cusp_deg / 30) + 1
        if cusp_sign in signs:
            owned_houses.append(house_num)

    return owned_houses
