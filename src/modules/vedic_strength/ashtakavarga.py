"""
Ashtakavarga scoring module for transit and strength evaluation.
Based on Parashari system of benefic points.
"""

from dataclasses import dataclass

from config.feature_flags import require_feature
from constants.ashtakavarga_points import (
    SAV_INTERPRETATION,
    TRANSIT_ACTIVATION,
    get_benefic_houses,
)


@dataclass
class AshtakavargaResult:
    """Container for Ashtakavarga calculations."""

    bav: dict[int, list[int]]  # Bhinnashtakavarga - individual planet charts
    sav: list[int]  # Sarvashtakavarga - combined totals
    planet_bindus: dict[int, dict[int, int]]  # Planet-wise bindus per house
    interpretations: dict[str, str]  # Interpretations
    transit_strength: dict[int, float]  # Transit strength per house

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "bav": self.format_bav(),
            "sav": self.sav,
            "planet_bindus": self.planet_bindus,
            "interpretations": self.interpretations,
            "transit_strength": self.transit_strength,
        }

    def format_bav(self) -> dict[str, list[int]]:
        """Format BAV for output."""
        formatted = {}
        planet_names = {
            1: "sun",
            2: "moon",
            3: "jupiter",
            4: "rahu",
            5: "mercury",
            6: "venus",
            7: "ketu",
            8: "saturn",
            9: "mars",
        }
        for planet_id, bindus in self.bav.items():
            formatted[planet_names.get(planet_id, f"planet_{planet_id}")] = bindus
        return formatted


@require_feature("ashtakavarga")
def compute_bav_sav(ctx: dict) -> dict[str, any]:
    """Compute Bhinnashtakavarga and Sarvashtakavarga.

    Args:
        ctx: Context with planet positions and houses

    Returns:
        Dictionary with BAV and SAV calculations
    """
    planets = ctx.get("planets", {})
    ascendant = ctx.get("ascendant", 0.0)

    if not planets:
        return {}

    # Calculate ascendant sign
    asc_sign = int(ascendant / 30) + 1

    # Initialize result
    result = AshtakavargaResult(
        bav={},
        sav=[0] * 12,  # 12 houses
        planet_bindus={},
        interpretations={},
        transit_strength={},
    )

    # Calculate BAV for each planet
    for planet_id in range(1, 10):
        if planet_id in [4, 7]:  # Skip Rahu/Ketu in basic calculation
            continue

        planet_data = planets.get(planet_id, {})
        if not planet_data:
            continue

        planet_sign = planet_data.get("sign", 1)

        # Calculate bindus for this planet's chart
        bindus = calculate_planet_bav(planet_id, planet_sign, planets, asc_sign)

        result.bav[planet_id] = bindus
        result.planet_bindus[planet_id] = {i + 1: bindus[i] for i in range(12)}

        # Add to SAV
        for i in range(12):
            result.sav[i] += bindus[i]

    # Calculate interpretations
    result.interpretations = generate_interpretations(result.sav, result.bav)

    # Calculate transit strength
    result.transit_strength = calculate_transit_strength(result.sav)

    return {"ashtakavarga": result.to_dict()}


def calculate_planet_bav(
    planet_id: int, planet_sign: int, all_planets: dict, asc_sign: int
) -> list[int]:
    """Calculate Bhinnashtakavarga for a single planet.

    Args:
        planet_id: Planet to calculate BAV for
        planet_sign: Sign position of the planet
        all_planets: All planet positions
        asc_sign: Ascendant sign

    Returns:
        List of 12 bindus (benefic points) for each house
    """
    bindus = [0] * 12  # Initialize 12 houses with 0 bindus

    # Get benefic points from each planet
    for from_planet_id in range(1, 10):
        if from_planet_id in [4, 7]:  # Skip Rahu/Ketu as contributors
            continue

        from_planet_data = all_planets.get(from_planet_id, {})
        if not from_planet_data:
            continue

        from_sign = from_planet_data.get("sign", 1)

        # Get benefic houses from this planet
        benefic_houses = get_benefic_houses(from_planet_id, planet_id)

        # Mark benefic points
        for house_offset in benefic_houses:
            # Calculate actual house position
            house_from_planet = ((from_sign - 1) + (house_offset - 1)) % 12
            bindus[house_from_planet] += 1

    # Add points from Ascendant
    asc_benefic_houses = get_benefic_houses(0, planet_id)  # 0 = Ascendant
    for house_offset in asc_benefic_houses:
        house_from_asc = ((asc_sign - 1) + (house_offset - 1)) % 12
        bindus[house_from_asc] += 1

    # Apply reductions if needed (Shodhya Pinda)
    bindus = apply_reductions(bindus, planet_id)

    return bindus


def apply_reductions(bindus: list[int], planet_id: int) -> list[int]:
    """Apply traditional reductions (Shodhya Pinda).

    Args:
        bindus: Original bindus
        planet_id: Planet ID

    Returns:
        Reduced bindus
    """
    # Trikashuddhi - Reduction of malefic houses
    # This is a simplified version
    reduced = bindus.copy()

    # Ensure minimum and maximum limits
    for i in range(12):
        if reduced[i] < 0:
            reduced[i] = 0
        elif reduced[i] > 8:
            reduced[i] = 8

    return reduced


def generate_interpretations(
    sav: list[int], bav: dict[int, list[int]]
) -> dict[str, str]:
    """Generate interpretations for Ashtakavarga results.

    Args:
        sav: Sarvashtakavarga totals
        bav: Bhinnashtakavarga for each planet

    Returns:
        Dictionary of interpretations
    """
    interpretations = {}

    # Overall SAV strength
    total_sav = sum(sav)
    if total_sav >= 337:
        interpretations["overall"] = "Very Strong Chart"
    elif total_sav >= 320:
        interpretations["overall"] = "Strong Chart"
    elif total_sav >= 300:
        interpretations["overall"] = "Average Chart"
    elif total_sav >= 280:
        interpretations["overall"] = "Below Average Chart"
    else:
        interpretations["overall"] = "Weak Chart"

    # House-wise interpretations
    house_names = [
        "Personality",
        "Wealth",
        "Communication",
        "Home",
        "Creativity",
        "Health",
        "Partnership",
        "Transformation",
        "Dharma",
        "Career",
        "Gains",
        "Spirituality",
    ]

    for i in range(12):
        house_strength = sav[i]
        house_name = house_names[i]

        if house_strength >= SAV_INTERPRETATION["excellent"]:
            interpretations[f"house_{i+1}"] = f"{house_name}: Excellent"
        elif house_strength >= SAV_INTERPRETATION["good"]:
            interpretations[f"house_{i+1}"] = f"{house_name}: Good"
        elif house_strength >= SAV_INTERPRETATION["average"]:
            interpretations[f"house_{i+1}"] = f"{house_name}: Average"
        elif house_strength >= SAV_INTERPRETATION["weak"]:
            interpretations[f"house_{i+1}"] = f"{house_name}: Weak"
        else:
            interpretations[f"house_{i+1}"] = f"{house_name}: Very Weak"

    # Find strongest and weakest houses
    max_house = sav.index(max(sav)) + 1
    min_house = sav.index(min(sav)) + 1

    interpretations["strongest_house"] = (
        f"House {max_house} ({house_names[max_house-1]})"
    )
    interpretations["weakest_house"] = f"House {min_house} ({house_names[min_house-1]})"

    return interpretations


def calculate_transit_strength(sav: list[int]) -> dict[int, float]:
    """Calculate transit activation strength for each house.

    Args:
        sav: Sarvashtakavarga totals

    Returns:
        Transit strength scores (0-100) per house
    """
    transit_strength = {}

    for i in range(12):
        points = sav[i]

        # Convert to 0-100 scale
        if points >= 35:
            strength = 100.0
        elif points >= 30:
            strength = 80.0 + (points - 30) * 4
        elif points >= 25:
            strength = 60.0 + (points - 25) * 4
        elif points >= 20:
            strength = 40.0 + (points - 20) * 4
        elif points >= 15:
            strength = 20.0 + (points - 15) * 4
        else:
            strength = max(0, points * 1.33)

        transit_strength[i + 1] = round(strength, 1)

    return transit_strength


@require_feature("ashtakavarga")
def get_transit_recommendation(
    planet_id: int, transit_house: int, ashtakavarga_data: dict
) -> dict[str, any]:
    """Get transit recommendations based on Ashtakavarga.

    Args:
        planet_id: Transiting planet
        transit_house: House being transited
        ashtakavarga_data: Ashtakavarga calculation results

    Returns:
        Transit recommendations
    """
    if not ashtakavarga_data or "ashtakavarga" not in ashtakavarga_data:
        return {}

    av_data = ashtakavarga_data["ashtakavarga"]

    # Get bindus for this planet in this house
    planet_bindus = av_data.get("planet_bindus", {}).get(planet_id, {})
    bindus = planet_bindus.get(transit_house, 0)

    # Get SAV for this house
    sav_points = av_data.get("sav", [])[transit_house - 1] if transit_house <= 12 else 0

    recommendation = {
        "planet_bindus": bindus,
        "sav_points": sav_points,
        "strength": "weak",
        "favorable": False,
        "advice": "",
    }

    # Determine strength
    if bindus >= TRANSIT_ACTIVATION["strong"]:
        recommendation["strength"] = "strong"
        recommendation["favorable"] = True
        recommendation["advice"] = "Excellent time for initiatives"
    elif bindus >= TRANSIT_ACTIVATION["moderate"]:
        recommendation["strength"] = "moderate"
        recommendation["favorable"] = True
        recommendation["advice"] = "Good time for steady progress"
    elif bindus >= TRANSIT_ACTIVATION["weak"]:
        recommendation["strength"] = "weak"
        recommendation["favorable"] = False
        recommendation["advice"] = "Proceed with caution"
    else:
        recommendation["strength"] = "negligible"
        recommendation["favorable"] = False
        recommendation["advice"] = "Avoid important decisions"

    # SAV modifier
    if sav_points >= 30:
        recommendation["advice"] += " (House strongly supported)"
    elif sav_points < 20:
        recommendation["advice"] += " (House needs strengthening)"

    return recommendation


@require_feature("ashtakavarga")
def find_favorable_transits(ashtakavarga_data: dict, min_bindus: int = 4) -> list[dict]:
    """Find favorable transit periods based on Ashtakavarga.

    Args:
        ashtakavarga_data: Ashtakavarga calculations
        min_bindus: Minimum bindus for favorable transit

    Returns:
        List of favorable transit opportunities
    """
    if not ashtakavarga_data or "ashtakavarga" not in ashtakavarga_data:
        return []

    av_data = ashtakavarga_data["ashtakavarga"]
    favorable_transits = []

    planet_names = {
        1: "Sun",
        2: "Moon",
        3: "Jupiter",
        5: "Mercury",
        6: "Venus",
        8: "Saturn",
        9: "Mars",
    }

    # Check each planet's BAV
    for planet_id, bindus_list in av_data.get("bav", {}).items():
        if isinstance(bindus_list, list):
            for house in range(12):
                bindus = bindus_list[house] if house < len(bindus_list) else 0
                if bindus >= min_bindus:
                    favorable_transits.append(
                        {
                            "planet": planet_names.get(
                                planet_id, f"Planet {planet_id}"
                            ),
                            "house": house + 1,
                            "bindus": bindus,
                            "strength": "strong" if bindus >= 5 else "moderate",
                        }
                    )

    # Sort by bindus (strongest first)
    favorable_transits.sort(key=lambda x: x["bindus"], reverse=True)

    return favorable_transits[:10]  # Return top 10 opportunities
