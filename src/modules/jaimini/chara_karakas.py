"""
Chara Karakas (Variable Significators) calculation module.
Based on Jaimini Sutras for determining soul-level significators.
"""

from dataclasses import dataclass

from config.feature_flags import require_feature


@dataclass
class CharaKarakas:
    """Container for Chara Karaka assignments."""

    atma_karaka: int  # Soul significator (highest degree)
    amatya_karaka: int  # Minister/career
    bhratru_karaka: int  # Siblings
    matru_karaka: int  # Mother
    putra_karaka: int  # Children
    gnati_karaka: int  # Enemies/obstacles
    dara_karaka: int  # Spouse

    # Optional 8th karaka (some schools include Rahu)
    karaka_8: int | None = None

    def to_dict(self) -> dict[str, any]:
        """Convert to dictionary format."""
        result = {
            "AK": self.atma_karaka,
            "AmK": self.amatya_karaka,
            "BK": self.bhratru_karaka,
            "MK": self.matru_karaka,
            "PK": self.putra_karaka,
            "GK": self.gnati_karaka,
            "DK": self.dara_karaka,
        }
        if self.karaka_8 is not None:
            result["K8"] = self.karaka_8
        return result

    def get_karaka_name(self, karaka_type: str) -> str:
        """Get the name of a karaka type."""
        names = {
            "AK": "Atma Karaka (Soul)",
            "AmK": "Amatya Karaka (Mind/Career)",
            "BK": "Bhratru Karaka (Siblings)",
            "MK": "Matru Karaka (Mother)",
            "PK": "Putra Karaka (Children)",
            "GK": "Gnati Karaka (Obstacles)",
            "DK": "Dara Karaka (Spouse)",
            "K8": "8th Karaka (Hidden)",
        }
        return names.get(karaka_type, karaka_type)


# Karaka significations
KARAKA_SIGNIFICATIONS = {
    "AK": [
        "Soul purpose",
        "Deepest desires",
        "Life mission",
        "Spiritual path",
        "Core identity",
    ],
    "AmK": [
        "Career and profession",
        "Advisors and ministers",
        "Mental faculties",
        "Decision making",
        "Authority figures",
    ],
    "BK": ["Siblings", "Courage", "Short journeys", "Communication", "Initiative"],
    "MK": ["Mother", "Education", "Vehicles", "Property", "Emotional security"],
    "PK": ["Children", "Creativity", "Intelligence", "Speculation", "Romance"],
    "GK": ["Enemies and rivals", "Obstacles", "Diseases", "Debts", "Competition"],
    "DK": [
        "Spouse and partnerships",
        "Marriage",
        "Business partners",
        "Contracts",
        "Public relations",
    ],
}


@require_feature("jaimini")
def calculate_chara_karakas(ctx: dict) -> dict[str, any]:
    """Calculate Chara Karakas based on planetary degrees.

    Args:
        ctx: Context with planet positions

    Returns:
        Dictionary with Chara Karaka assignments
    """
    planets = ctx.get("planets", {})
    include_rahu = ctx.get("include_rahu_as_8th", False)

    if not planets:
        return {}

    # Get degrees for each planet (excluding Ketu)
    planet_degrees = []

    for planet_id in range(1, 10):
        if planet_id == 7:  # Skip Ketu (always opposite to Rahu)
            continue

        planet_data = planets.get(planet_id)
        if planet_data:
            longitude = planet_data.get("longitude", 0)
            # Get degree within sign (0-30)
            degree_in_sign = longitude % 30

            # For Rahu, use reverse degrees (some schools)
            if planet_id == 4 and not include_rahu:
                degree_in_sign = 30 - degree_in_sign

            planet_degrees.append((planet_id, degree_in_sign))

    # Sort by degrees (highest to lowest)
    planet_degrees.sort(key=lambda x: x[1], reverse=True)

    # Handle ties (planets at same degree)
    planet_degrees = handle_tie_breaks(planet_degrees)

    # Assign Karakas
    if len(planet_degrees) >= 7:
        karakas = CharaKarakas(
            atma_karaka=planet_degrees[0][0],
            amatya_karaka=planet_degrees[1][0],
            bhratru_karaka=planet_degrees[2][0],
            matru_karaka=planet_degrees[3][0],
            putra_karaka=planet_degrees[4][0],
            gnati_karaka=planet_degrees[5][0],
            dara_karaka=planet_degrees[6][0],
        )

        # Optional 8th karaka
        if len(planet_degrees) >= 8:
            karakas.karaka_8 = planet_degrees[7][0]
    else:
        # Not enough planets (shouldn't happen)
        return {}

    # Calculate karaka strengths
    strengths = calculate_karaka_strengths(karakas, planets)

    # Get significations
    significations = get_karaka_significations(karakas)

    return {
        "chara_karakas": karakas.to_dict(),
        "strengths": strengths,
        "significations": significations,
        "interpretation": interpret_karakas(karakas, planets),
    }


def handle_tie_breaks(
    planet_degrees: list[tuple[int, float]],
) -> list[tuple[int, float]]:
    """Handle tie-breaking rules for planets at same degree.

    Traditional order for tie-breaking:
    1. Minutes and seconds (if available)
    2. Natural order: Sun > Moon > Mars > Mercury > Jupiter > Venus > Saturn > Rahu
    """
    # Natural order for tie-breaking
    natural_order = {1: 1, 2: 2, 9: 3, 5: 4, 3: 5, 6: 6, 8: 7, 4: 8}

    # Check for ties and apply natural order
    result = []
    i = 0
    while i < len(planet_degrees):
        # Find all planets with same degree
        same_degree = [planet_degrees[i]]
        j = i + 1
        while (
            j < len(planet_degrees)
            and abs(planet_degrees[j][1] - planet_degrees[i][1]) < 0.01
        ):
            same_degree.append(planet_degrees[j])
            j += 1

        # Sort tied planets by natural order
        if len(same_degree) > 1:
            same_degree.sort(key=lambda x: natural_order.get(x[0], 99))

        result.extend(same_degree)
        i = j

    return result


def calculate_karaka_strengths(
    karakas: CharaKarakas, planets: dict
) -> dict[str, float]:
    """Calculate strength of each Chara Karaka.

    Args:
        karakas: Chara Karaka assignments
        planets: Planet data

    Returns:
        Strength scores for each karaka
    """
    strengths = {}

    for karaka_type, planet_id in karakas.to_dict().items():
        planet_data = planets.get(planet_id, {})
        strength = 50.0  # Base strength

        # Exaltation adds strength
        from constants.relationships import DEBILITATION_SIGNS, EXALTATION_SIGNS

        if planet_data.get("sign") == EXALTATION_SIGNS.get(planet_id):
            strength += 25
        elif planet_data.get("sign") == DEBILITATION_SIGNS.get(planet_id):
            strength -= 25

        # House placement
        house = planet_data.get("house", 1)
        if house in [1, 4, 7, 10]:  # Kendras
            strength += 15
        elif house in [1, 5, 9]:  # Trikonas
            strength += 10
        elif house in [6, 8, 12]:  # Dusthanas
            strength -= 10

        # Retrograde adds strength in Jaimini
        if planet_data.get("retrograde"):
            strength += 10

        # Ensure within bounds
        strength = max(0, min(100, strength))
        strengths[karaka_type] = strength

    return strengths


def get_karaka_significations(karakas: CharaKarakas) -> dict[str, list[str]]:
    """Get significations for each assigned Karaka.

    Args:
        karakas: Chara Karaka assignments

    Returns:
        Significations for each karaka
    """
    significations = {}

    for karaka_type, planet_id in karakas.to_dict().items():
        if karaka_type in KARAKA_SIGNIFICATIONS:
            significations[karaka_type] = KARAKA_SIGNIFICATIONS[karaka_type]

    return significations


def interpret_karakas(karakas: CharaKarakas, planets: dict) -> dict[str, str]:
    """Provide interpretation of Chara Karakas.

    Args:
        karakas: Chara Karaka assignments
        planets: Planet data

    Returns:
        Interpretations
    """
    interpretations = {}

    # Atma Karaka interpretation
    ak_planet = karakas.atma_karaka
    ak_data = planets.get(ak_planet, {})
    ak_sign = ak_data.get("sign", 1)
    ak_house = ak_data.get("house", 1)

    planet_names = {
        1: "Sun",
        2: "Moon",
        3: "Jupiter",
        4: "Rahu",
        5: "Mercury",
        6: "Venus",
        8: "Saturn",
        9: "Mars",
    }

    ak_name = planet_names.get(ak_planet, f"Planet {ak_planet}")

    interpretations["soul_purpose"] = (
        f"{ak_name} as Atma Karaka in house {ak_house} indicates "
        f"soul evolution through {get_ak_theme(ak_planet)}"
    )

    # Relationship insights
    dk_planet = karakas.dara_karaka
    dk_name = planet_names.get(dk_planet, f"Planet {dk_planet}")
    dk_data = planets.get(dk_planet, {})

    interpretations["relationships"] = (
        f"{dk_name} as Dara Karaka suggests partner with "
        f"{get_dk_qualities(dk_planet)} qualities"
    )

    # Career insights
    amk_planet = karakas.amatya_karaka
    amk_name = planet_names.get(amk_planet, f"Planet {amk_planet}")

    interpretations["career"] = (
        f"{amk_name} as Amatya Karaka indicates career in "
        f"{get_amk_profession(amk_planet)}"
    )

    return interpretations


def get_ak_theme(planet_id: int) -> str:
    """Get soul evolution theme for Atma Karaka planet."""
    themes = {
        1: "leadership, authority, and self-realization",
        2: "emotional fulfillment and nurturing",
        3: "wisdom, teaching, and spiritual growth",
        4: "material detachment and karmic resolution",
        5: "communication, learning, and adaptability",
        6: "love, beauty, and harmonious relationships",
        8: "discipline, service, and perseverance",
        9: "courage, action, and transformation",
    }
    return themes.get(planet_id, "self-discovery")


def get_dk_qualities(planet_id: int) -> str:
    """Get partner qualities from Dara Karaka planet."""
    qualities = {
        1: "authoritative, confident, and leadership",
        2: "nurturing, emotional, and caring",
        3: "wise, spiritual, and generous",
        4: "unconventional, foreign, or mysterious",
        5: "intellectual, communicative, and youthful",
        6: "beautiful, artistic, and luxurious",
        8: "mature, disciplined, and hardworking",
        9: "energetic, passionate, and courageous",
    }
    return qualities.get(planet_id, "unique")


def get_amk_profession(planet_id: int) -> str:
    """Get career indications from Amatya Karaka planet."""
    professions = {
        1: "government, administration, or leadership roles",
        2: "public service, hospitality, or care-giving",
        3: "teaching, counseling, or religious work",
        4: "technology, foreign trade, or research",
        5: "business, communication, or writing",
        6: "arts, entertainment, or luxury goods",
        8: "law, construction, or technical fields",
        9: "military, sports, or engineering",
    }
    return professions.get(planet_id, "varied fields")


@require_feature("jaimini")
def find_karakamsa_lagna(chara_karakas: dict, navamsa_data: dict) -> dict[str, any]:
    """Find Karakamsa Lagna (Navamsa position of Atma Karaka).

    Args:
        chara_karakas: Chara Karaka calculation results
        navamsa_data: Navamsa (D9) divisional chart data

    Returns:
        Karakamsa Lagna information
    """
    if "chara_karakas" not in chara_karakas:
        return {}

    ak_planet = chara_karakas["chara_karakas"].get("AK")
    if not ak_planet:
        return {}

    # Get AK's navamsa position
    ak_navamsa = navamsa_data.get("planets", {}).get(ak_planet, {})

    if not ak_navamsa:
        return {}

    karakamsa_sign = ak_navamsa.get("sign", 1)

    return {
        "karakamsa_lagna": karakamsa_sign,
        "interpretation": interpret_karakamsa(karakamsa_sign),
        "special_yogas": check_karakamsa_yogas(karakamsa_sign, navamsa_data),
    }


def interpret_karakamsa(sign: int) -> str:
    """Interpret Karakamsa Lagna sign."""
    interpretations = {
        1: "Independent and pioneering soul path",
        2: "Material and sensual soul evolution",
        3: "Intellectual and communicative dharma",
        4: "Emotional and nurturing soul purpose",
        5: "Creative and leadership-oriented path",
        6: "Service and perfection-seeking dharma",
        7: "Partnership and balance-focused evolution",
        8: "Transformative and mystical soul path",
        9: "Philosophical and teaching-oriented dharma",
        10: "Ambitious and achievement-focused path",
        11: "Humanitarian and innovative soul purpose",
        12: "Spiritual and liberation-seeking dharma",
    }
    return interpretations.get(sign, "Unique soul evolution path")


def check_karakamsa_yogas(karakamsa_sign: int, navamsa_data: dict) -> list[str]:
    """Check for special yogas from Karakamsa Lagna."""
    yogas = []

    # Check planets in houses from Karakamsa
    planets_from_kl = {}
    for planet_id, planet_data in navamsa_data.get("planets", {}).items():
        house_from_kl = ((planet_data.get("sign", 1) - karakamsa_sign) % 12) + 1
        planets_from_kl[house_from_kl] = planets_from_kl.get(house_from_kl, [])
        planets_from_kl[house_from_kl].append(planet_id)

    # Check for specific yogas
    if 2 in planets_from_kl.get(2, []):  # Moon in 2nd from Karakamsa
        yogas.append("Wealthy and eloquent speaker")

    if 6 in planets_from_kl.get(2, []):  # Venus in 2nd
        yogas.append("Governmental authority or political power")

    if 3 in planets_from_kl.get(5, []):  # Jupiter in 5th
        yogas.append("Highly intelligent and scholarly")

    if 5 in planets_from_kl.get(5, []):  # Mercury in 5th
        yogas.append("Expert in mantras and scriptures")

    if any(p in [9, 4, 7] for p in planets_from_kl.get(12, [])):  # Malefics in 12th
        yogas.append("Spiritual liberation (Moksha)")

    return yogas
