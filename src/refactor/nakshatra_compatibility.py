#!/usr/bin/env python3
"""
Nakshatra Compatibility Module
Tara Kuta and other nakshatra-based compatibility calculations for KP
"""

from dataclasses import dataclass
from enum import Enum

from .constants import NAKSHATRA_NAMES


class TaraKutaType(Enum):
    """9-fold Tara compatibility types"""

    JANMA = (1, "Birth", 3)  # Same nakshatra - moderate
    SAMPAT = (2, "Wealth", 5)  # Very favorable
    VIPAT = (3, "Danger", 0)  # Unfavorable
    KSHEMA = (4, "Prosperity", 5)  # Very favorable
    PRATYARI = (5, "Obstacles", 0)  # Very unfavorable
    SADHAKA = (6, "Achievement", 5)  # Very favorable
    NAIDHANA = (7, "Destruction", 0)  # Most unfavorable
    MITRA = (8, "Friend", 5)  # Very favorable
    ATI_MITRA = (9, "Best Friend", 4)  # Favorable

    @property
    def position(self) -> int:
        return self.value[0]

    @property
    def name(self) -> str:
        return self.value[1]

    @property
    def points(self) -> int:
        return self.value[2]


class GanaType(Enum):
    """Nakshatra temperament types"""

    DEVA = "Divine"  # Sattvic nature
    MANUSHYA = "Human"  # Rajasic nature
    RAKSHASA = "Demon"  # Tamasic nature


class NadiType(Enum):
    """Nakshatra Nadi (pulse) types"""

    AADI = "Beginning"  # Vata
    MADHYA = "Middle"  # Pitta
    ANTYA = "End"  # Kapha


@dataclass
class NakshatraCompatibility:
    """Complete nakshatra compatibility analysis"""

    nakshatra1: int
    nakshatra2: int

    # Tara Kuta (star compatibility)
    tara_from_1_to_2: TaraKutaType
    tara_from_2_to_1: TaraKutaType
    tara_points: int  # Out of 5

    # Vipat/Pratyari/Naidhana Tara check
    has_vedha_dosha: bool  # Affliction between stars
    vedha_type: str | None

    # Yoni Kuta (sexual compatibility)
    yoni_points: int  # Out of 4

    # Gana Kuta (temperament)
    gana1: GanaType
    gana2: GanaType
    gana_points: int  # Out of 6

    # Nadi Kuta (health/progeny)
    nadi1: NadiType
    nadi2: NadiType
    nadi_points: int  # Out of 8

    # Overall scores
    total_points: int  # Out of 36 (Ashtakuta)
    compatibility_percentage: float
    relationship_quality: str

    def to_dict(self) -> dict:
        """Convert to dictionary for API"""
        return {
            "nakshatras": {
                "person1": {
                    "nakshatra": self.nakshatra1,
                    "name": NAKSHATRA_NAMES.get(
                        self.nakshatra1, f"Nakshatra-{self.nakshatra1}"
                    ),
                    "gana": self.gana1.value,
                    "nadi": self.nadi1.value,
                },
                "person2": {
                    "nakshatra": self.nakshatra2,
                    "name": NAKSHATRA_NAMES.get(
                        self.nakshatra2, f"Nakshatra-{self.nakshatra2}"
                    ),
                    "gana": self.gana2.value,
                    "nadi": self.nadi2.value,
                },
            },
            "tara_kuta": {
                "from_1_to_2": self.tara_from_1_to_2.name,
                "from_2_to_1": self.tara_from_2_to_1.name,
                "points": self.tara_points,
                "max_points": 5,
                "has_vedha": self.has_vedha_dosha,
                "vedha_type": self.vedha_type,
            },
            "other_kutas": {
                "yoni": {"points": self.yoni_points, "max": 4},
                "gana": {"points": self.gana_points, "max": 6},
                "nadi": {"points": self.nadi_points, "max": 8},
            },
            "overall": {
                "total_points": self.total_points,
                "max_points": 36,
                "percentage": round(self.compatibility_percentage, 1),
                "quality": self.relationship_quality,
            },
        }


# Nakshatra properties database
NAKSHATRA_GANA = {
    1: GanaType.DEVA,  # Ashwini
    2: GanaType.MANUSHYA,  # Bharani
    3: GanaType.MANUSHYA,  # Krittika
    4: GanaType.MANUSHYA,  # Rohini
    5: GanaType.DEVA,  # Mrigashira
    6: GanaType.MANUSHYA,  # Ardra
    7: GanaType.DEVA,  # Punarvasu
    8: GanaType.DEVA,  # Pushya
    9: GanaType.RAKSHASA,  # Ashlesha
    10: GanaType.RAKSHASA,  # Magha
    11: GanaType.MANUSHYA,  # Purva Phalguni
    12: GanaType.MANUSHYA,  # Uttara Phalguni
    13: GanaType.DEVA,  # Hasta
    14: GanaType.DEVA,  # Chitra
    15: GanaType.DEVA,  # Swati
    16: GanaType.RAKSHASA,  # Vishakha
    17: GanaType.DEVA,  # Anuradha
    18: GanaType.RAKSHASA,  # Jyeshtha
    19: GanaType.RAKSHASA,  # Moola
    20: GanaType.MANUSHYA,  # Purva Ashadha
    21: GanaType.MANUSHYA,  # Uttara Ashadha
    22: GanaType.DEVA,  # Shravana
    23: GanaType.RAKSHASA,  # Dhanishta
    24: GanaType.RAKSHASA,  # Shatabhisha
    25: GanaType.MANUSHYA,  # Purva Bhadrapada
    26: GanaType.MANUSHYA,  # Uttara Bhadrapada
    27: GanaType.DEVA,  # Revati
}

NAKSHATRA_NADI = {
    1: NadiType.AADI,  # Ashwini
    2: NadiType.MADHYA,  # Bharani
    3: NadiType.ANTYA,  # Krittika
    4: NadiType.ANTYA,  # Rohini
    5: NadiType.MADHYA,  # Mrigashira
    6: NadiType.AADI,  # Ardra
    7: NadiType.AADI,  # Punarvasu
    8: NadiType.MADHYA,  # Pushya
    9: NadiType.ANTYA,  # Ashlesha
    10: NadiType.ANTYA,  # Magha
    11: NadiType.MADHYA,  # Purva Phalguni
    12: NadiType.AADI,  # Uttara Phalguni
    13: NadiType.AADI,  # Hasta
    14: NadiType.MADHYA,  # Chitra
    15: NadiType.ANTYA,  # Swati
    16: NadiType.ANTYA,  # Vishakha
    17: NadiType.MADHYA,  # Anuradha
    18: NadiType.AADI,  # Jyeshtha
    19: NadiType.AADI,  # Moola
    20: NadiType.MADHYA,  # Purva Ashadha
    21: NadiType.ANTYA,  # Uttara Ashadha
    22: NadiType.ANTYA,  # Shravana
    23: NadiType.MADHYA,  # Dhanishta
    24: NadiType.AADI,  # Shatabhisha
    25: NadiType.AADI,  # Purva Bhadrapada
    26: NadiType.MADHYA,  # Uttara Bhadrapada
    27: NadiType.ANTYA,  # Revati
}

# Yoni (animal) compatibility matrix (simplified)
YONI_POINTS = {
    # Same yoni = 4 points, friendly = 3, neutral = 2, enemy = 0
    # This is simplified - full system has 14 animal types
    (1, 1): 4,
    (1, 2): 2,
    (1, 3): 3,  # Ashwini with others
    (2, 2): 4,
    (2, 3): 2,
    (2, 4): 3,  # Bharani with others
    # ... simplified for demonstration
}


def calculate_tara_kuta(nakshatra1: int, nakshatra2: int) -> tuple[TaraKutaType, int]:
    """
    Calculate Tara Kuta (star compatibility) from nakshatra1 to nakshatra2.

    Args:
        nakshatra1: First person's nakshatra (1-27)
        nakshatra2: Second person's nakshatra (1-27)

    Returns:
        Tuple of (TaraKutaType, points)
    """
    # Calculate tara position (1-9)
    count = ((nakshatra2 - nakshatra1) % 27) + 1
    tara_position = ((count - 1) % 9) + 1

    # Map to TaraKutaType
    tara_types = list(TaraKutaType)
    tara_type = tara_types[tara_position - 1]

    return tara_type, tara_type.points


def check_vedha_dosha(nakshatra1: int, nakshatra2: int) -> tuple[bool, str | None]:
    """
    Check for Vedha Dosha (star affliction).

    Certain nakshatra pairs have natural enmity.

    Args:
        nakshatra1: First nakshatra
        nakshatra2: Second nakshatra

    Returns:
        Tuple of (has_vedha, vedha_type)
    """
    # Vedha pairs (mutual affliction)
    vedha_pairs = [
        (1, 18),  # Ashwini - Jyeshtha
        (2, 17),  # Bharani - Anuradha
        (3, 16),  # Krittika - Vishakha
        (4, 15),  # Rohini - Swati
        (6, 14),  # Ardra - Chitra
        (7, 13),  # Punarvasu - Hasta
        (8, 11),  # Pushya - Purva Phalguni
        (9, 10),  # Ashlesha - Magha
        (19, 26),  # Moola - Uttara Bhadrapada
        (20, 25),  # Purva Ashadha - Purva Bhadrapada
        (21, 24),  # Uttara Ashadha - Shatabhisha
        (22, 23),  # Shravana - Dhanishta
    ]

    for pair in vedha_pairs:
        if (nakshatra1, nakshatra2) == pair or (nakshatra2, nakshatra1) == pair:
            return (
                True,
                f"Vedha between {NAKSHATRA_NAMES.get(nakshatra1)} and {NAKSHATRA_NAMES.get(nakshatra2)}",
            )

    # Check for Vipat/Pratyari/Naidhana Tara
    tara_type, _ = calculate_tara_kuta(nakshatra1, nakshatra2)
    if tara_type in [TaraKutaType.VIPAT, TaraKutaType.PRATYARI, TaraKutaType.NAIDHANA]:
        return True, f"{tara_type.name} Tara affliction"

    return False, None


def calculate_gana_kuta(gana1: GanaType, gana2: GanaType) -> int:
    """
    Calculate Gana Kuta points (temperament compatibility).

    Args:
        gana1: First person's gana
        gana2: Second person's gana

    Returns:
        Points (0-6)
    """
    if gana1 == gana2:
        return 6  # Same temperament - excellent

    # Deva-Manushya or Manushya-Deva
    if (gana1 == GanaType.DEVA and gana2 == GanaType.MANUSHYA) or (
        gana1 == GanaType.MANUSHYA and gana2 == GanaType.DEVA
    ):
        return 5  # Good compatibility

    # Manushya-Manushya handled above

    # Rakshasa with Rakshasa handled above

    # Deva-Rakshasa is very bad
    if (gana1 == GanaType.DEVA and gana2 == GanaType.RAKSHASA) or (
        gana1 == GanaType.RAKSHASA and gana2 == GanaType.DEVA
    ):
        return 0  # Very poor compatibility

    # Manushya-Rakshasa
    if (gana1 == GanaType.MANUSHYA and gana2 == GanaType.RAKSHASA) or (
        gana1 == GanaType.RAKSHASA and gana2 == GanaType.MANUSHYA
    ):
        return 1  # Poor compatibility

    return 3  # Default moderate


def calculate_nadi_kuta(nadi1: NadiType, nadi2: NadiType) -> int:
    """
    Calculate Nadi Kuta points (health/progeny compatibility).

    Same Nadi is considered very inauspicious.

    Args:
        nadi1: First person's nadi
        nadi2: Second person's nadi

    Returns:
        Points (0 or 8)
    """
    if nadi1 == nadi2:
        return 0  # Same Nadi - Nadi Dosha - affects progeny
    return 8  # Different Nadi - good for health and progeny


def calculate_yoni_kuta(nakshatra1: int, nakshatra2: int) -> int:
    """
    Calculate Yoni Kuta points (sexual/physical compatibility).

    Simplified version - full system uses 14 animal types.

    Args:
        nakshatra1: First nakshatra
        nakshatra2: Second nakshatra

    Returns:
        Points (0-4)
    """
    # Simplified yoni groups
    yoni_groups = {
        1: [1, 24],  # Horse
        2: [2, 13],  # Elephant
        3: [3, 12, 26],  # Sheep
        4: [4, 14],  # Serpent
        5: [5, 6, 7],  # Dog
        6: [8, 9],  # Cat
        7: [10, 11],  # Rat
        8: [15, 16, 17],  # Buffalo
        9: [18, 19, 20],  # Tiger
        10: [21, 22],  # Deer
        11: [23, 25, 27],  # Monkey
    }

    # Find yoni groups
    group1 = None
    group2 = None

    for group_id, members in yoni_groups.items():
        if nakshatra1 in members:
            group1 = group_id
        if nakshatra2 in members:
            group2 = group_id

    if group1 == group2:
        return 4  # Same yoni - excellent

    # Enemy yonis
    enemy_pairs = [(6, 7), (9, 10), (5, 11)]  # Cat-Rat, Tiger-Deer, Dog-Monkey
    if (group1, group2) in enemy_pairs or (group2, group1) in enemy_pairs:
        return 0  # Enemy yonis

    # Friendly yonis
    friendly_pairs = [(1, 2), (3, 4), (8, 10)]
    if (group1, group2) in friendly_pairs or (group2, group1) in friendly_pairs:
        return 3  # Friendly

    return 2  # Neutral


def calculate_nakshatra_compatibility(
    nakshatra1: int, nakshatra2: int, include_all_kutas: bool = True
) -> NakshatraCompatibility:
    """
    Calculate complete nakshatra compatibility.

    Args:
        nakshatra1: First person's birth nakshatra (1-27)
        nakshatra2: Second person's birth nakshatra (1-27)
        include_all_kutas: Whether to calculate all kutas or just Tara

    Returns:
        NakshatraCompatibility object
    """
    # Tara Kuta (both directions)
    tara_1_to_2, points_1_to_2 = calculate_tara_kuta(nakshatra1, nakshatra2)
    tara_2_to_1, points_2_to_1 = calculate_tara_kuta(nakshatra2, nakshatra1)

    # Average the bidirectional Tara points
    tara_points = min(5, (points_1_to_2 + points_2_to_1) // 2)

    # Check Vedha Dosha
    has_vedha, vedha_type = check_vedha_dosha(nakshatra1, nakshatra2)
    if has_vedha:
        tara_points = max(0, tara_points - 2)  # Reduce points for vedha

    # Get Gana and Nadi
    gana1 = NAKSHATRA_GANA.get(nakshatra1, GanaType.MANUSHYA)
    gana2 = NAKSHATRA_GANA.get(nakshatra2, GanaType.MANUSHYA)
    nadi1 = NAKSHATRA_NADI.get(nakshatra1, NadiType.MADHYA)
    nadi2 = NAKSHATRA_NADI.get(nakshatra2, NadiType.MADHYA)

    if include_all_kutas:
        # Calculate all kutas
        yoni_points = calculate_yoni_kuta(nakshatra1, nakshatra2)
        gana_points = calculate_gana_kuta(gana1, gana2)
        nadi_points = calculate_nadi_kuta(nadi1, nadi2)

        # Total points (simplified Ashtakuta)
        total_points = tara_points + yoni_points + gana_points + nadi_points

        # Add points for other kutas not implemented (Bhakuta, Vashya, etc.)
        # Simplified scoring
        total_points += 8  # Placeholder for other kutas

    else:
        # Just Tara Kuta
        yoni_points = 2  # Default
        gana_points = 3  # Default
        nadi_points = 4  # Default
        total_points = tara_points + 15  # Approximate

    # Calculate percentage and quality
    max_points = 36
    percentage = (total_points / max_points) * 100

    # Determine relationship quality
    if percentage >= 80:
        quality = "Excellent - Highly Compatible"
    elif percentage >= 65:
        quality = "Good - Compatible"
    elif percentage >= 50:
        quality = "Average - Acceptable with remedies"
    elif percentage >= 35:
        quality = "Below Average - Challenges expected"
    else:
        quality = "Poor - Not recommended"

    # Special case: Nadi Dosha
    if nadi_points == 0:
        quality += " (Nadi Dosha present - affects progeny)"

    return NakshatraCompatibility(
        nakshatra1=nakshatra1,
        nakshatra2=nakshatra2,
        tara_from_1_to_2=tara_1_to_2,
        tara_from_2_to_1=tara_2_to_1,
        tara_points=tara_points,
        has_vedha_dosha=has_vedha,
        vedha_type=vedha_type,
        yoni_points=yoni_points,
        gana1=gana1,
        gana2=gana2,
        gana_points=gana_points,
        nadi1=nadi1,
        nadi2=nadi2,
        nadi_points=nadi_points,
        total_points=total_points,
        compatibility_percentage=percentage,
        relationship_quality=quality,
    )


def find_compatible_nakshatras(
    nakshatra: int, min_compatibility: float = 65.0
) -> list[tuple[int, float, str]]:
    """
    Find all compatible nakshatras for a given nakshatra.

    Args:
        nakshatra: Birth nakshatra to match
        min_compatibility: Minimum compatibility percentage

    Returns:
        List of (nakshatra, compatibility%, quality) tuples
    """
    compatible = []

    for other_nakshatra in range(1, 28):
        if other_nakshatra == nakshatra:
            continue  # Skip same nakshatra

        compat = calculate_nakshatra_compatibility(
            nakshatra, other_nakshatra, include_all_kutas=False
        )

        if compat.compatibility_percentage >= min_compatibility:
            compatible.append(
                (
                    other_nakshatra,
                    compat.compatibility_percentage,
                    compat.relationship_quality,
                )
            )

    # Sort by compatibility percentage
    compatible.sort(key=lambda x: x[1], reverse=True)

    return compatible
