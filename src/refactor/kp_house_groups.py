#!/usr/bin/env python3
"""
KP House Groups Module
Defines house combinations for various life matters in KP astrology
"""

from dataclasses import dataclass
from enum import Enum

from .kp_significators import SignificatorData


class LifeMatter(Enum):
    """Common life matters and their house combinations"""

    WEALTH = "wealth"
    CAREER = "career"
    MARRIAGE = "marriage"
    CHILDREN = "children"
    HEALTH = "health"
    EDUCATION = "education"
    PROPERTY = "property"
    FOREIGN = "foreign"
    SPIRITUALITY = "spirituality"
    SPECULATION = "speculation"
    LITIGATION = "litigation"
    ACCIDENT = "accident"


@dataclass
class HouseGroupAnalysis:
    """Analysis of house combinations for various matters"""

    matter: str
    primary_houses: list[int]
    supporting_houses: list[int]
    negative_houses: list[int]
    significators: list[int]  # Planets signifying the combination
    strength: float  # Overall strength of combination
    timing_favorable: bool  # If current dasha/transit supports

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "matter": self.matter,
            "primary_houses": self.primary_houses,
            "supporting_houses": self.supporting_houses,
            "negative_houses": self.negative_houses,
            "significators": self.significators,
            "strength": round(self.strength, 2),
            "timing_favorable": self.timing_favorable,
        }


# KP House Groupings for Various Matters
HOUSE_GROUPS = {
    LifeMatter.WEALTH: {
        "primary": [2, 11],  # Wealth and gains
        "supporting": [6, 10],  # Service and profession
        "negative": [8, 12],  # Losses and expenses
        "description": "Financial prosperity and accumulation",
    },
    LifeMatter.CAREER: {
        "primary": [10],  # Career house
        "supporting": [2, 6, 11],  # Income, service, gains
        "negative": [5, 8, 12],  # Break in career, obstacles
        "description": "Professional success and recognition",
    },
    LifeMatter.MARRIAGE: {
        "primary": [7],  # Partnership
        "supporting": [2, 11],  # Family and fulfillment
        "negative": [1, 6, 10, 12],  # Separation factors
        "description": "Marital prospects and harmony",
    },
    LifeMatter.CHILDREN: {
        "primary": [5],  # Children house
        "supporting": [2, 11],  # Family expansion and fulfillment
        "negative": [1, 4, 10],  # Denial factors
        "description": "Childbirth and progeny matters",
    },
    LifeMatter.HEALTH: {
        "primary": [1],  # Physical body
        "supporting": [5, 9, 11],  # Cure and recovery
        "negative": [6, 8, 12],  # Disease and hospitalization
        "description": "Physical and mental wellbeing",
    },
    LifeMatter.EDUCATION: {
        "primary": [4, 9],  # Education and higher learning
        "supporting": [2, 11],  # Success and achievement
        "negative": [3, 8, 12],  # Breaks and obstacles
        "description": "Academic success and knowledge",
    },
    LifeMatter.PROPERTY: {
        "primary": [4],  # Immovable assets
        "supporting": [11, 12],  # Gains and investments
        "negative": [3, 6, 8],  # Disposal and litigation
        "description": "Real estate and property matters",
    },
    LifeMatter.FOREIGN: {
        "primary": [12],  # Foreign lands
        "supporting": [3, 9],  # Travel and fortune abroad
        "negative": [2, 4, 11],  # Staying in homeland
        "description": "Foreign travel and settlement",
    },
    LifeMatter.SPIRITUALITY: {
        "primary": [9, 12],  # Dharma and moksha
        "supporting": [5, 8],  # Purva punya and transformation
        "negative": [3, 6, 11],  # Material attachments
        "description": "Spiritual growth and liberation",
    },
    LifeMatter.SPECULATION: {
        "primary": [5],  # Speculation house
        "supporting": [2, 11],  # Gains from speculation
        "negative": [8, 12],  # Losses in speculation
        "description": "Gambling and speculative gains",
    },
    LifeMatter.LITIGATION: {
        "primary": [6],  # Disputes
        "supporting": [1, 3, 11],  # Victory in litigation
        "negative": [7, 8, 12],  # Defeat and losses
        "description": "Legal matters and disputes",
    },
    LifeMatter.ACCIDENT: {
        "primary": [8],  # Sudden events
        "supporting": [6, 12],  # Injury and hospitalization
        "negative": [1, 5, 9, 11],  # Protection factors
        "description": "Accidents and sudden mishaps",
    },
}


def get_house_groups() -> dict[str, list[int]]:
    """
    Get standard KP house groupings for quick reference.

    Returns:
        Dictionary of common groupings
    """
    return {
        "gains": [2, 6, 10, 11],  # Financial gains
        "losses": [5, 8, 12],  # Financial losses
        "movable": [1, 4, 7, 10],  # Cardinal houses
        "fixed": [2, 5, 8, 11],  # Fixed houses
        "dual": [3, 6, 9, 12],  # Dual/Mutable houses
        "kendra": [1, 4, 7, 10],  # Angles
        "trikona": [1, 5, 9],  # Trines
        "upachaya": [3, 6, 10, 11],  # Growth houses
        "dusthana": [6, 8, 12],  # Difficult houses
        "maraka": [2, 7],  # Death-inflicting houses
        "badhaka": {  # Obstruction houses (depends on lagna)
            "movable": 11,  # 11th for movable signs
            "fixed": 9,  # 9th for fixed signs
            "dual": 7,  # 7th for dual signs
        },
    }


def evaluate_house_combination(
    houses: list[int],
    significator_data: SignificatorData,
    required_strength: float = 25.0,
) -> tuple[float, list[int]]:
    """
    Evaluate the strength of a house combination.

    Args:
        houses: List of houses in the combination
        significator_data: Complete significator analysis
        required_strength: Minimum strength to consider a planet

    Returns:
        Tuple of (combination_strength, list_of_strong_significators)
    """
    if not houses or not significator_data:
        return 0.0, []

    # Collect all significators for the house combination
    combination_significators = {}

    for house in houses:
        house_sigs = significator_data.house_significators.get(house, [])
        for planet, level, strength in house_sigs:
            if planet not in combination_significators:
                combination_significators[planet] = []
            combination_significators[planet].append((house, level, strength))

    # Calculate combined strength
    total_strength = 0.0
    strong_significators = []

    for planet, connections in combination_significators.items():
        # Planet strength = average of its connections to required houses
        planet_strength = sum(s for _, _, s in connections) / len(connections)

        # Bonus if planet connects to multiple houses in combination
        if len(connections) >= 2:
            planet_strength *= 1.2

        # Bonus if planet connects to ALL houses in combination
        connected_houses = set(h for h, _, _ in connections)
        if connected_houses == set(houses):
            planet_strength *= 1.5

        if planet_strength >= required_strength:
            strong_significators.append(planet)
            total_strength += planet_strength

    # Normalize strength to 0-100 scale
    if strong_significators:
        total_strength = min(100.0, total_strength / len(houses))
    else:
        total_strength = 0.0

    return total_strength, strong_significators


def analyze_life_matter(
    matter: LifeMatter,
    significator_data: SignificatorData,
    dasha_lords: list[int] | None = None,
    transit_activators: list[int] | None = None,
) -> HouseGroupAnalysis:
    """
    Analyze a specific life matter based on house combinations.

    Args:
        matter: Life matter to analyze
        significator_data: Complete significator analysis
        dasha_lords: Current dasha/bhukti/antara lords
        transit_activators: Planets currently activating by transit

    Returns:
        HouseGroupAnalysis for the matter
    """
    # Get house groups for this matter
    matter_config = HOUSE_GROUPS.get(matter, {})
    primary = matter_config.get("primary", [])
    supporting = matter_config.get("supporting", [])
    negative = matter_config.get("negative", [])

    # Evaluate primary combination
    primary_strength, primary_sigs = evaluate_house_combination(
        primary, significator_data
    )

    # Evaluate supporting combination
    support_strength, support_sigs = evaluate_house_combination(
        supporting, significator_data, required_strength=20.0
    )

    # Evaluate negative combination
    negative_strength, negative_sigs = evaluate_house_combination(
        negative, significator_data, required_strength=20.0
    )

    # Combine significators (primary weighted more)
    all_significators = list(set(primary_sigs + support_sigs))

    # Calculate overall strength
    overall_strength = primary_strength * 0.6 + support_strength * 0.3

    # Reduce strength if negative houses are strong
    if negative_strength > 30:
        overall_strength *= 1 - negative_strength / 200

    # Check timing favorability
    timing_favorable = False
    if dasha_lords and all_significators:
        # Favorable if dasha lords are among significators
        if any(lord in all_significators for lord in dasha_lords):
            timing_favorable = True
            overall_strength *= 1.2  # Timing bonus

    if transit_activators and all_significators:
        # Extra favorable if transit also supports
        if any(planet in all_significators for planet in transit_activators):
            timing_favorable = True
            overall_strength *= 1.1

    return HouseGroupAnalysis(
        matter=matter.value,
        primary_houses=primary,
        supporting_houses=supporting,
        negative_houses=negative,
        significators=all_significators,
        strength=min(100.0, overall_strength),
        timing_favorable=timing_favorable,
    )


def get_result_timings(
    target_houses: list[int],
    significator_data: SignificatorData,
    dasha_periods: list[dict],
    min_strength: float = 30.0,
) -> list[dict]:
    """
    Identify favorable periods for house combination to give results.

    In KP, results come when:
    1. Dasha/Bhukti/Antara lords are significators
    2. Transit triggers the combination
    3. Sufficient strength exists

    Args:
        target_houses: House combination to analyze
        significator_data: Complete significator analysis
        dasha_periods: List of dasha period data
        min_strength: Minimum strength required

    Returns:
        List of favorable timing windows
    """
    # Get significators for target combination
    strength, significators = evaluate_house_combination(
        target_houses, significator_data
    )

    if strength < min_strength or not significators:
        return []

    favorable_periods = []

    for period in dasha_periods:
        dasha_lord = period.get("planet", 0)
        start_date = period.get("start")
        end_date = period.get("end")
        level = period.get("level", "MD")  # MD/AD/PD/SD/PAD

        # Check if dasha lord is a significator
        if dasha_lord in significators:
            # Calculate period strength
            period_strength = strength

            # Stronger if primary significator
            primary_sigs = significator_data.primary_significators
            for house in target_houses:
                if dasha_lord in primary_sigs.get(house, []):
                    period_strength *= 1.3
                    break

            favorable_periods.append(
                {
                    "start": start_date,
                    "end": end_date,
                    "level": level,
                    "planet": dasha_lord,
                    "strength": min(100.0, period_strength),
                    "houses": target_houses,
                    "description": f"{level} of planet {dasha_lord} activating houses {target_houses}",
                }
            )

    # Sort by strength
    favorable_periods.sort(key=lambda x: x["strength"], reverse=True)

    return favorable_periods


def find_contradicting_houses(primary_houses: list[int]) -> list[int]:
    """
    Find houses that contradict or negate the given houses.

    In KP, certain houses naturally oppose others:
    - 2,11 (gains) vs 8,12 (losses)
    - 1 (self) vs 7 (others)
    - 4 (home) vs 10 (outside)

    Args:
        primary_houses: Houses to check

    Returns:
        List of contradicting house numbers
    """
    contradictions = {
        1: [7, 8, 12],  # Self vs others, longevity issues
        2: [8, 12],  # Wealth vs losses
        3: [9, 12],  # Short travel vs long travel
        4: [8, 10],  # Home vs away, peace vs transformation
        5: [1, 10, 12],  # Children vs no children factors
        6: [1, 11, 12],  # Disease vs health, service vs gains
        7: [1, 6],  # Partnership vs self, separation
        8: [1, 2, 11],  # Death vs life, losses vs gains
        9: [3, 6, 8],  # Fortune vs misfortune
        10: [4, 5, 9],  # Career vs home, authority vs subordination
        11: [5, 8, 12],  # Gains vs losses, fulfillment vs denial
        12: [1, 2, 11],  # Loss vs gain, foreign vs home
    }

    negating_houses = set()
    for house in primary_houses:
        negating_houses.update(contradictions.get(house, []))

    # Remove any houses that are also in primary
    negating_houses -= set(primary_houses)

    return sorted(list(negating_houses))


def classify_house_combination(houses: list[int]) -> str:
    """
    Classify a house combination into a category.

    Categories:
    - Highly Favorable: 2,11 present without 8,12
    - Favorable: Positive houses dominate
    - Mixed: Both positive and negative
    - Challenging: Negative houses dominate
    - Highly Challenging: 6,8,12 together

    Args:
        houses: List of house numbers

    Returns:
        Classification string
    """
    if not houses:
        return "Neutral"

    house_set = set(houses)

    # Define house categories
    highly_positive = {2, 11}
    positive = {1, 4, 5, 9, 10}
    negative = {6, 8, 12}

    # Count categories
    has_highly_positive = bool(house_set & highly_positive)
    has_positive = bool(house_set & positive)
    has_negative = bool(house_set & negative)

    # Special combinations
    if house_set >= {2, 11} and not has_negative:
        return "Highly Favorable"

    if house_set >= {6, 8, 12}:
        return "Highly Challenging"

    if house_set >= {2, 6, 10, 11}:
        return "Career Success"

    if house_set >= {5, 9, 11}:
        return "Fortune and Creativity"

    # General classification
    positive_count = len(house_set & (highly_positive | positive))
    negative_count = len(house_set & negative)

    if positive_count > negative_count * 2:
        return "Favorable"
    elif negative_count > positive_count * 2:
        return "Challenging"
    else:
        return "Mixed Results"
