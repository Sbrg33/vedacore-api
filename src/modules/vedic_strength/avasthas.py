"""
Avasthas (Planetary States) calculation module.
Based on Brihat Parasara Hora Shastra and traditional texts.
"""

from dataclasses import dataclass

from config.feature_flags import require_feature
from constants.relationships import (
    DEBILITATION_SIGNS,
    EXALTATION_SIGNS,
    NATURAL_ENEMIES,
    NATURAL_FRIENDS,
    SIGN_LORDS,
)


@dataclass
class AvasthaStates:
    """Container for various avastha states."""

    baladi: str = ""  # Age-based state
    jagradadi: str = ""  # Awareness state
    deeptadi: str = ""  # Luminosity state
    lajjitadi: list[str] = None  # Situational states
    score: float = 0.0  # Overall avastha score (0-100)

    def __post_init__(self):
        if self.lajjitadi is None:
            self.lajjitadi = []

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "baladi": self.baladi,
            "jagradadi": self.jagradadi,
            "deeptadi": self.deeptadi,
            "lajjitadi": self.lajjitadi,
            "score": round(self.score, 2),
        }


# Baladi Avasthas (Age-based states) - 5 states
BALADI_RANGES = {
    # Each sign divided into 5 parts of 6° each
    "bala": (0, 6),  # Infant (0-6°)
    "kumara": (6, 12),  # Youth (6-12°)
    "yuva": (12, 18),  # Adult (12-18°)
    "vriddha": (18, 24),  # Old (18-24°)
    "mrita": (24, 30),  # Dead (24-30°)
}

# Odd vs Even sign modifications for Baladi
BALADI_ODD_SIGN = ["bala", "kumara", "yuva", "vriddha", "mrita"]
BALADI_EVEN_SIGN = ["mrita", "vriddha", "yuva", "kumara", "bala"]

# Baladi strength scores
BALADI_SCORES = {
    "bala": 25.0,  # Infant - weak
    "kumara": 50.0,  # Youth - moderate
    "yuva": 100.0,  # Adult - full strength
    "vriddha": 50.0,  # Old - declining
    "mrita": 12.5,  # Dead - very weak
}


# Jagradadi Avasthas (Awareness states) - 3 states
def calculate_jagradadi(planet_id: int, sign: int, is_retrograde: bool) -> str:
    """Calculate awareness state based on sign placement."""
    # Own sign or exaltation = Jagrat (Awake)
    if sign == EXALTATION_SIGNS.get(planet_id):
        return "jagrat"

    # Check if in own sign
    own_signs = get_own_signs(planet_id)
    if sign in own_signs:
        return "jagrat"

    # Friend's sign = Swapna (Dreaming)
    sign_lord = SIGN_LORDS.get(sign)
    if sign_lord and sign_lord in NATURAL_FRIENDS.get(planet_id, set()):
        return "swapna"

    # Enemy or debilitation = Sushupti (Deep Sleep)
    if sign == DEBILITATION_SIGNS.get(planet_id):
        return "sushupti"

    if sign_lord and sign_lord in NATURAL_ENEMIES.get(planet_id, set()):
        return "sushupti"

    # Neutral sign = Swapna
    return "swapna"


# Jagradadi strength scores
JAGRADADI_SCORES = {
    "jagrat": 100.0,  # Awake - full awareness
    "swapna": 50.0,  # Dreaming - half awareness
    "sushupti": 25.0,  # Deep sleep - minimal awareness
}

# Deeptadi Avasthas (Luminosity states) - 9 states
DEEPTADI_STATES = {
    "deepta": 100.0,  # Brilliant (exalted)
    "swastha": 80.0,  # Comfortable (own sign)
    "mudita": 70.0,  # Happy (friend's sign)
    "shanta": 60.0,  # Peaceful (benefic aspect)
    "sakta": 50.0,  # Attached (with benefic)
    "peedita": 40.0,  # Troubled (with malefic)
    "deena": 30.0,  # Miserable (enemy sign)
    "vikala": 20.0,  # Mutilated (combust)
    "khala": 10.0,  # Mischievous (debilitated)
}


# Lajjitadi Avasthas (Situational states) - 6 special conditions
def calculate_lajjitadi(planet_data: dict, all_planets: dict) -> list[str]:
    """Calculate special situational states."""
    states = []
    planet_id = planet_data.get("id")
    house = planet_data.get("house")

    # Lajjita (Ashamed) - In 5th house with malefic
    if house == 5:
        malefics_in_5th = check_malefics_in_house(5, all_planets)
        if malefics_in_5th:
            states.append("lajjita")

    # Garvita (Proud) - In exaltation or moolatrikona
    if planet_data.get("sign") == EXALTATION_SIGNS.get(planet_id):
        states.append("garvita")

    # Kshudhita (Hungry) - In enemy sign without benefic aspect
    sign_lord = SIGN_LORDS.get(planet_data.get("sign"))
    if sign_lord in NATURAL_ENEMIES.get(planet_id, set()):
        if not has_benefic_aspect(planet_data, all_planets):
            states.append("kshudhita")

    # Trushita (Thirsty) - In watery sign aspected by malefic
    if planet_data.get("sign") in [4, 8, 12]:  # Cancer, Scorpio, Pisces
        if has_malefic_aspect(planet_data, all_planets):
            states.append("trushita")

    # Mudita (Delighted) - With friend in good house
    if house in [1, 4, 5, 7, 9, 10, 11]:
        if has_friend_conjunction(planet_data, all_planets):
            states.append("mudita_special")

    # Kshobhita (Agitated) - With Sun (combust) or malefic
    if is_combust(planet_data, all_planets):
        states.append("kshobhita")

    return states


@require_feature("avasthas")
def compute_avasthas(ctx: dict) -> dict[str, any]:
    """Compute all avastha states for planets.

    Args:
        ctx: Context with planet positions, houses, aspects

    Returns:
        Dictionary with avastha states for each planet
    """
    result = {}

    for planet_id in range(1, 10):
        if planet_id not in ctx.get("planets", {}):
            continue

        planet_data = ctx["planets"][planet_id]
        planet_data["id"] = planet_id  # Add ID for reference

        states = AvasthaStates()

        # 1. Baladi Avastha (Age state)
        states.baladi = calculate_baladi(
            planet_data.get("longitude", 0), planet_data.get("sign", 1)
        )

        # 2. Jagradadi Avastha (Awareness state)
        states.jagradadi = calculate_jagradadi(
            planet_id, planet_data.get("sign", 1), planet_data.get("retrograde", False)
        )

        # 3. Deeptadi Avastha (Luminosity state)
        states.deeptadi = calculate_deeptadi(
            planet_id,
            planet_data.get("sign", 1),
            planet_data.get("combust", False),
            ctx.get("aspects", {}),
        )

        # 4. Lajjitadi Avasthas (Situational states)
        states.lajjitadi = calculate_lajjitadi(planet_data, ctx.get("planets", {}))

        # Calculate overall score
        states.score = calculate_avastha_score(states)

        result[f"planet_{planet_id}"] = states.to_dict()

    return {"avasthas": result}


def calculate_baladi(longitude: float, sign: int) -> str:
    """Calculate age-based state from position in sign."""
    # Get position within sign (0-30°)
    sign_position = longitude % 30.0

    # Determine if odd or even sign
    if sign % 2 == 1:  # Odd sign
        sequence = BALADI_ODD_SIGN
    else:  # Even sign
        sequence = BALADI_EVEN_SIGN

    # Find which 6° segment (0-5)
    segment = int(sign_position / 6)
    if segment >= 5:
        segment = 4

    return sequence[segment]


def calculate_deeptadi(
    planet_id: int, sign: int, is_combust: bool, aspects: dict
) -> str:
    """Calculate luminosity state."""
    # Check for exaltation
    if sign == EXALTATION_SIGNS.get(planet_id):
        return "deepta"

    # Check for debilitation
    if sign == DEBILITATION_SIGNS.get(planet_id):
        return "khala"

    # Check for combustion
    if is_combust:
        return "vikala"

    # Check for own sign
    own_signs = get_own_signs(planet_id)
    if sign in own_signs:
        return "swastha"

    # Check for friend's sign
    sign_lord = SIGN_LORDS.get(sign)
    if sign_lord in NATURAL_FRIENDS.get(planet_id, set()):
        return "mudita"

    # Check for enemy sign
    if sign_lord in NATURAL_ENEMIES.get(planet_id, set()):
        return "deena"

    # Check aspects for remaining states
    planet_aspects = aspects.get(planet_id, {})
    benefic_aspects = sum(1 for p in [2, 3, 5, 6] if p in planet_aspects)
    malefic_aspects = sum(1 for p in [1, 4, 7, 8, 9] if p in planet_aspects)

    if benefic_aspects > malefic_aspects:
        return "shanta"
    elif malefic_aspects > benefic_aspects:
        return "peedita"
    else:
        return "sakta"


def calculate_avastha_score(states: AvasthaStates) -> float:
    """Calculate overall avastha score from all states."""
    scores = []

    # Baladi score (25% weight)
    baladi_score = BALADI_SCORES.get(states.baladi, 50.0)
    scores.append(baladi_score * 0.25)

    # Jagradadi score (35% weight)
    jagradadi_score = JAGRADADI_SCORES.get(states.jagradadi, 50.0)
    scores.append(jagradadi_score * 0.35)

    # Deeptadi score (30% weight)
    deeptadi_score = DEEPTADI_STATES.get(states.deeptadi, 50.0)
    scores.append(deeptadi_score * 0.30)

    # Lajjitadi modifiers (10% weight)
    lajjitadi_modifier = 50.0  # Base
    if "garvita" in states.lajjitadi:
        lajjitadi_modifier += 25
    if "mudita_special" in states.lajjitadi:
        lajjitadi_modifier += 15
    if "lajjita" in states.lajjitadi:
        lajjitadi_modifier -= 20
    if "kshudhita" in states.lajjitadi:
        lajjitadi_modifier -= 15
    if "kshobhita" in states.lajjitadi:
        lajjitadi_modifier -= 25

    lajjitadi_modifier = max(0, min(100, lajjitadi_modifier))
    scores.append(lajjitadi_modifier * 0.10)

    return sum(scores)


@require_feature("avasthas")
def avastha_tags(ctx: dict) -> list[str]:
    """Get list of significant avastha tags for all planets.

    Args:
        ctx: Context with planet data

    Returns:
        List of avastha tags
    """
    tags = []
    avasthas = compute_avasthas(ctx)

    if "avasthas" not in avasthas:
        return tags

    for planet_key, planet_avasthas in avasthas["avasthas"].items():
        planet_num = planet_key.replace("planet_", "")

        # Add significant states
        if planet_avasthas["baladi"] in ["yuva", "mrita"]:
            tags.append(f"P{planet_num}_{planet_avasthas['baladi']}")

        if planet_avasthas["jagradadi"] == "jagrat":
            tags.append(f"P{planet_num}_awake")
        elif planet_avasthas["jagradadi"] == "sushupti":
            tags.append(f"P{planet_num}_asleep")

        if planet_avasthas["deeptadi"] in ["deepta", "khala", "vikala"]:
            tags.append(f"P{planet_num}_{planet_avasthas['deeptadi']}")

        # Add special lajjitadi states
        for lajjita_state in planet_avasthas.get("lajjitadi", []):
            if lajjita_state in ["garvita", "lajjita", "kshobhita"]:
                tags.append(f"P{planet_num}_{lajjita_state}")

    return tags


@require_feature("avasthas")
def avastha_score(ctx: dict) -> float:
    """Get overall avastha score for chart.

    Args:
        ctx: Context with planet data

    Returns:
        Average avastha score (0-100)
    """
    avasthas = compute_avasthas(ctx)

    if "avasthas" not in avasthas:
        return 50.0

    scores = []
    for planet_avasthas in avasthas["avasthas"].values():
        scores.append(planet_avasthas.get("score", 50.0))

    return sum(scores) / len(scores) if scores else 50.0


# Helper functions


def get_own_signs(planet_id: int) -> list[int]:
    """Get signs ruled by a planet."""
    own_signs = []
    for sign, lord in SIGN_LORDS.items():
        if lord == planet_id:
            own_signs.append(sign)
    return own_signs


def check_malefics_in_house(house: int, all_planets: dict) -> list[int]:
    """Check which malefics are in a given house."""
    malefics = [1, 4, 7, 8, 9]  # Sun, Rahu, Ketu, Saturn, Mars
    malefics_in_house = []

    for planet_id, planet_data in all_planets.items():
        if planet_id in malefics and planet_data.get("house") == house:
            malefics_in_house.append(planet_id)

    return malefics_in_house


def has_benefic_aspect(planet_data: dict, all_planets: dict) -> bool:
    """Check if planet has benefic aspects."""
    # Simplified - would need aspect data in context
    return False


def has_malefic_aspect(planet_data: dict, all_planets: dict) -> bool:
    """Check if planet has malefic aspects."""
    # Simplified - would need aspect data in context
    return False


def has_friend_conjunction(planet_data: dict, all_planets: dict) -> bool:
    """Check if planet is conjunct with friend."""
    planet_id = planet_data.get("id")
    friends = NATURAL_FRIENDS.get(planet_id, set())

    for other_id, other_data in all_planets.items():
        if other_id != planet_id and other_id in friends:
            if other_data.get("house") == planet_data.get("house"):
                return True

    return False


def is_combust(planet_data: dict, all_planets: dict) -> bool:
    """Check if planet is combust."""
    # Check distance from Sun
    if planet_data.get("id") == 1:  # Sun itself
        return False

    sun_data = all_planets.get(1, {})
    if not sun_data:
        return False

    # Calculate angular distance
    planet_long = planet_data.get("longitude", 0)
    sun_long = sun_data.get("longitude", 0)

    distance = abs(planet_long - sun_long)
    if distance > 180:
        distance = 360 - distance

    # Use combustion orbs from constants
    from constants.combustion_orbs import get_combustion_state

    state = get_combustion_state(
        planet_data.get("id"), distance, planet_data.get("retrograde", False)
    )

    return state in ["combust", "deep_combust"]
