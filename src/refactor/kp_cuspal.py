#!/usr/bin/env python3
"""
KP Cuspal Sub-Lord (CSL) Module
Core KP functionality for house cusp sub-lords and their significations
"""

from dataclasses import dataclass

from .constants import PLANET_NAMES
from .houses import Houses
from .kp_chain import get_kp_lords_for_planet


@dataclass
class CuspalAnalysis:
    """Complete cuspal sub-lord analysis for a chart"""

    cusp_sublords: dict[int, int]  # house_num -> sublord planet ID
    cusp_starlords: dict[int, int]  # house_num -> starlord planet ID
    cusp_signlords: dict[int, int]  # house_num -> signlord planet ID
    cusp_positions: dict[int, float]  # house_num -> degree position
    fruitful_houses: list[int]  # Houses with favorable CSL

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "cuspal_sublords": {
                house: {
                    "sublord": sublord,
                    "sublord_name": PLANET_NAMES.get(sublord, str(sublord)),
                    "starlord": self.cusp_starlords[house],
                    "starlord_name": PLANET_NAMES.get(
                        self.cusp_starlords[house], str(self.cusp_starlords[house])
                    ),
                    "signlord": self.cusp_signlords[house],
                    "signlord_name": PLANET_NAMES.get(
                        self.cusp_signlords[house], str(self.cusp_signlords[house])
                    ),
                    "position": round(self.cusp_positions[house], 2),
                }
                for house, sublord in self.cusp_sublords.items()
            },
            "fruitful_houses": self.fruitful_houses,
        }


def get_cusp_sublords(houses: Houses) -> dict[int, tuple[int, int, int]]:
    """
    Calculate sub-lords for all house cusps.

    Args:
        houses: Houses object with cusp positions

    Returns:
        Dictionary mapping house number to (signlord, starlord, sublord) tuple
    """
    cusp_lords = {}

    for house_num in range(1, 13):
        cusp_degree = houses.cusps[house_num - 1]  # 0-indexed list

        # Get KP lords for this cusp position
        nl, sl, ssl = get_kp_lords_for_planet(cusp_degree)

        # In KP terminology:
        # nl = nakshatra lord (star lord)
        # sl = sub lord
        # ssl = sub-sub lord (not typically used for cusps)

        # Also get sign lord
        sign_num = int(cusp_degree / 30) + 1  # 1-12
        sign_lord = _get_sign_lord(sign_num)

        cusp_lords[house_num] = (sign_lord, nl, sl)

    return cusp_lords


def get_csl_significations(
    cusp_num: int, sublord: int, planet_positions: dict[int, dict]
) -> dict:
    """
    Determine what a cuspal sub-lord signifies for a house.

    In KP, the sub-lord of a cusp indicates:
    1. Whether house matters will fructify (if connected to houses 2,11)
    2. Nature of results (benefic/malefic based on houses signified)
    3. Timing factors (through dasha/transit activation)

    Args:
        cusp_num: House number (1-12)
        sublord: Planet ID of the sub-lord
        planet_positions: Dictionary of planet data including house positions

    Returns:
        Dictionary with signification analysis
    """
    significations = {
        "house": cusp_num,
        "sublord": sublord,
        "sublord_name": PLANET_NAMES.get(sublord, str(sublord)),
        "promises": [],
        "denials": [],
        "mixed": [],
        "strength": 0.0,
    }

    # Get sub-lord's house position if available
    if sublord in planet_positions:
        sl_data = planet_positions[sublord]
        sl_house = sl_data.get("house", 0)

        # Determine promises based on house matters
        promises, denials = _analyze_house_promises(cusp_num, sublord, sl_house)
        significations["promises"] = promises
        significations["denials"] = denials

        # Calculate strength based on sub-lord's condition
        significations["strength"] = _calculate_csl_strength(sublord, sl_data)

    return significations


def is_cusp_fruitful(
    cusp_num: int, sublord: int, sublord_significations: list[int]
) -> bool:
    """
    Check if a house cusp promises positive results.

    In KP, a cusp is fruitful if its sub-lord signifies:
    - Houses 2, 11 (gains, fulfillment)
    - Primary houses for that matter (e.g., 7 for marriage cusp 7)
    - NOT houses 6, 8, 12 strongly (unless for specific matters)

    Args:
        cusp_num: House number being analyzed
        sublord: Sub-lord planet ID
        sublord_significations: Houses signified by the sub-lord

    Returns:
        True if cusp promises positive results
    """
    if not sublord_significations:
        return False

    # Universal positive houses
    positive_houses = {2, 11}

    # Universal negative houses (with exceptions)
    negative_houses = {6, 8, 12}

    # House-specific positive significations
    house_specific_positive = {
        1: {1, 9, 10},  # Self, fortune, career
        2: {2, 6, 10, 11},  # Wealth, service, profession, gains
        3: {3, 9, 11},  # Communication, higher learning, fulfillment
        4: {4, 9, 11},  # Property, fortune, gains
        5: {5, 9, 11},  # Speculation, fortune, gains
        6: {6, 10, 11},  # Service, career, income (6th is positive here)
        7: {2, 7, 11},  # Partnership, wealth, fulfillment
        8: {2, 8, 11},  # Inheritance, transformation (8th can be positive)
        9: {5, 9, 11},  # Fortune, higher knowledge
        10: {2, 6, 10, 11},  # Career, service, wealth, gains
        11: {2, 6, 10, 11},  # Income from all sources
        12: {3, 9, 12},  # Foreign, spirituality (12th for specific matters)
    }

    # Get specific positive houses for this cusp
    specific_positive = house_specific_positive.get(cusp_num, positive_houses)

    # Count positive and negative significations
    positive_count = len(specific_positive.intersection(set(sublord_significations)))
    negative_count = len(negative_houses.intersection(set(sublord_significations)))

    # Special handling for houses 6, 8, 12 as primary houses
    if cusp_num in {6, 8, 12}:
        # These houses need their own number strongly signified
        if cusp_num in sublord_significations:
            positive_count += 2  # Give extra weight

    # Fruitful if positive outweighs negative
    return positive_count > negative_count


def get_cuspal_analysis(
    houses: Houses, planet_positions: dict[int, dict]
) -> CuspalAnalysis:
    """
    Complete cuspal sub-lord analysis for all houses.

    Args:
        houses: Houses object with cusp positions
        planet_positions: Dictionary of planet data

    Returns:
        CuspalAnalysis object with complete CSL data
    """
    # Get sub-lords for all cusps
    cusp_lords = get_cusp_sublords(houses)

    # Separate into different lord types
    cusp_sublords = {}
    cusp_starlords = {}
    cusp_signlords = {}
    cusp_positions = {}
    fruitful_houses = []

    for house_num in range(1, 13):
        sign_lord, star_lord, sub_lord = cusp_lords[house_num]
        cusp_sublords[house_num] = sub_lord
        cusp_starlords[house_num] = star_lord
        cusp_signlords[house_num] = sign_lord
        cusp_positions[house_num] = houses.cusps[house_num - 1]

        # Check if house is fruitful (simplified check for now)
        # In full implementation, would need significator data
        if sub_lord in {1, 2, 3, 5, 6, 9}:  # Benefic planets as sublords
            fruitful_houses.append(house_num)

    return CuspalAnalysis(
        cusp_sublords=cusp_sublords,
        cusp_starlords=cusp_starlords,
        cusp_signlords=cusp_signlords,
        cusp_positions=cusp_positions,
        fruitful_houses=fruitful_houses,
    )


def _get_sign_lord(sign_num: int) -> int:
    """Get the lord of a zodiac sign"""
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
    return sign_lords.get(sign_num, 0)


def _analyze_house_promises(
    cusp_num: int, sublord: int, sublord_house: int
) -> tuple[list[str], list[str]]:
    """
    Analyze what a CSL promises or denies for a house.

    Returns:
        Tuple of (promises list, denials list)
    """
    promises = []
    denials = []

    # House-specific promise analysis
    house_promises = {
        1: {
            "positive": ["Health", "Success", "Recognition"],
            "negative": ["Obstacles", "Ill-health"],
        },
        2: {
            "positive": ["Wealth", "Family harmony", "Speech"],
            "negative": ["Financial loss", "Family discord"],
        },
        3: {
            "positive": ["Communication", "Courage", "Siblings support"],
            "negative": ["Miscommunication", "Conflicts with siblings"],
        },
        4: {
            "positive": ["Property", "Comfort", "Mother's wellbeing"],
            "negative": ["Property disputes", "Domestic unrest"],
        },
        5: {
            "positive": ["Creativity", "Children", "Speculation gains"],
            "negative": ["Creative blocks", "Speculation losses"],
        },
        6: {
            "positive": ["Service", "Health recovery", "Competition success"],
            "negative": ["Diseases", "Debts", "Enemies"],
        },
        7: {
            "positive": ["Partnership", "Marriage", "Business success"],
            "negative": ["Separation", "Business loss"],
        },
        8: {
            "positive": ["Transformation", "Inheritance", "Occult knowledge"],
            "negative": ["Obstacles", "Chronic issues", "Sudden events"],
        },
        9: {
            "positive": ["Fortune", "Higher learning", "Father's support"],
            "negative": ["Misfortune", "Academic obstacles"],
        },
        10: {
            "positive": ["Career growth", "Status", "Authority"],
            "negative": ["Career obstacles", "Disgrace"],
        },
        11: {
            "positive": ["Gains", "Fulfillment", "Elder siblings support"],
            "negative": ["Unfulfilled desires", "Financial stagnation"],
        },
        12: {
            "positive": ["Foreign success", "Spirituality", "Liberation"],
            "negative": ["Losses", "Hospitalization", "Imprisonment"],
        },
    }

    # Get promises for this house
    if cusp_num in house_promises:
        house_data = house_promises[cusp_num]

        # Simple logic: benefics promise positive, malefics indicate challenges
        benefics = {1, 2, 3, 5, 6}  # Sun, Moon, Jupiter, Mercury, Venus
        malefics = {4, 7, 8, 9}  # Rahu, Ketu, Saturn, Mars

        if sublord in benefics:
            promises = house_data["positive"]
        elif sublord in malefics:
            # Malefics can give mixed results
            promises = house_data["positive"][:1]  # Limited positive
            denials = house_data["negative"][:1]  # Some negative
        else:
            promises = house_data["positive"][:2]  # Moderate positive

    return promises, denials


def _calculate_csl_strength(sublord: int, planet_data: dict) -> float:
    """
    Calculate strength of cuspal sub-lord.

    Factors:
    - Planet's inherent nature
    - Speed (fast = strong)
    - Retrogression (reduces strength)
    - Sign placement dignity

    Returns:
        Strength score 0.0 to 100.0
    """
    strength = 50.0  # Base strength

    # Natural benefics get bonus
    if sublord in {1, 2, 3, 5, 6}:  # Sun, Moon, Jupiter, Mercury, Venus
        strength += 10

    # Speed factor
    speed = planet_data.get("speed", 0)
    if speed > 0:  # Direct motion
        strength += 10
    elif speed < 0:  # Retrograde
        strength -= 15

    # Sign dignity (simplified)
    # In full implementation, would check exaltation, own sign, etc.
    longitude = planet_data.get("longitude", 0)
    sign = int(longitude / 30) + 1

    # Example: Jupiter strong in Sagittarius (9) and Pisces (12)
    if sublord == 3 and sign in {9, 12}:
        strength += 20

    # Ensure within bounds
    return max(0.0, min(100.0, strength))
