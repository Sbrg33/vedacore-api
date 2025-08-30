#!/usr/bin/env python3
"""
Tārā Bala Module
Nakshatra-based quality scoring for daily and personal timing
Based on the 9-fold tārā cycle from Janma Nakshatra
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TaraType(Enum):
    """9-fold Tārā cycle types"""

    JANMA = ("Janma", 1, "Birth star - Mixed results")
    SAMPAT = ("Sampat", 2, "Wealth star - Very favorable")
    VIPAT = ("Vipat", 3, "Danger star - Unfavorable")
    KSHEMA = ("Kshema", 4, "Well-being star - Favorable")
    PRATYAK = ("Pratyak", 5, "Obstacle star - Unfavorable")
    SADHANA = ("Sadhana", 6, "Achievement star - Favorable")
    NAIDHANA = ("Naidhana", 7, "Death star - Very unfavorable")
    MITRA = ("Mitra", 8, "Friend star - Favorable")
    PARAMA_MITRA = ("Parama Mitra", 9, "Best friend star - Very favorable")

    def __init__(self, display_name: str, number: int, description: str):
        self.display_name = display_name
        self.number = number
        self.description = description


@dataclass
class TaraScore:
    """Score for a specific tārā"""

    nakshatra_num: int  # 1-27
    nakshatra_name: str
    tara_type: TaraType
    tara_number: int  # 1-9
    score: float  # -2 to +2
    favorable: bool
    description: str

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "nakshatra": {"number": self.nakshatra_num, "name": self.nakshatra_name},
            "tara": {
                "type": self.tara_type.display_name,
                "number": self.tara_number,
                "description": self.tara_type.description,
            },
            "score": round(self.score, 2),
            "favorable": self.favorable,
            "description": self.description,
        }


@dataclass
class TaraBalaAnalysis:
    """Complete Tārā Bala analysis"""

    birth_nakshatra: int
    birth_nakshatra_name: str
    current_nakshatra: int
    current_nakshatra_name: str
    current_tara: TaraScore

    # 27-nakshatra cycle analysis
    full_cycle: list[TaraScore]

    # Summary scores
    favorable_count: int
    unfavorable_count: int
    neutral_count: int
    overall_quality: str  # "Excellent", "Good", "Mixed", "Challenging", "Difficult"

    # Timing windows
    next_favorable: dict | None  # Next favorable tārā period
    next_unfavorable: dict | None  # Next unfavorable period

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "birth_nakshatra": {
                "number": self.birth_nakshatra,
                "name": self.birth_nakshatra_name,
            },
            "current": {
                "nakshatra": {
                    "number": self.current_nakshatra,
                    "name": self.current_nakshatra_name,
                },
                "tara": self.current_tara.to_dict(),
            },
            "summary": {
                "favorable": self.favorable_count,
                "unfavorable": self.unfavorable_count,
                "neutral": self.neutral_count,
                "quality": self.overall_quality,
            },
            "timing": {
                "next_favorable": self.next_favorable,
                "next_unfavorable": self.next_unfavorable,
            },
        }


# Nakshatra names (1-27)
NAKSHATRA_NAMES = {
    1: "Ashwini",
    2: "Bharani",
    3: "Krittika",
    4: "Rohini",
    5: "Mrigashira",
    6: "Ardra",
    7: "Punarvasu",
    8: "Pushya",
    9: "Ashlesha",
    10: "Magha",
    11: "Purva Phalguni",
    12: "Uttara Phalguni",
    13: "Hasta",
    14: "Chitra",
    15: "Swati",
    16: "Vishakha",
    17: "Anuradha",
    18: "Jyeshtha",
    19: "Moola",
    20: "Purva Ashadha",
    21: "Uttara Ashadha",
    22: "Shravana",
    23: "Dhanishta",
    24: "Shatabhisha",
    25: "Purva Bhadrapada",
    26: "Uttara Bhadrapada",
    27: "Revati",
}

# Tārā scores (traditional values)
TARA_SCORES = {
    TaraType.JANMA: 0.0,  # Neutral/mixed
    TaraType.SAMPAT: 2.0,  # Very favorable
    TaraType.VIPAT: -1.5,  # Unfavorable
    TaraType.KSHEMA: 1.5,  # Favorable
    TaraType.PRATYAK: -1.0,  # Obstacles
    TaraType.SADHANA: 1.0,  # Achievement
    TaraType.NAIDHANA: -2.0,  # Very unfavorable (Vadha)
    TaraType.MITRA: 1.5,  # Favorable
    TaraType.PARAMA_MITRA: 2.0,  # Very favorable
}


def calculate_tara_from_janma(
    janma_nakshatra: int, current_nakshatra: int
) -> tuple[TaraType, int]:
    """
    Calculate tārā type from janma nakshatra to current nakshatra.

    The 27 nakshatras are divided into 3 cycles of 9 tārās each.

    Args:
        janma_nakshatra: Birth nakshatra (1-27)
        current_nakshatra: Current nakshatra (1-27)

    Returns:
        Tuple of (TaraType, tara_number)
    """
    # Calculate distance from janma to current
    if current_nakshatra >= janma_nakshatra:
        distance = current_nakshatra - janma_nakshatra
    else:
        distance = (27 - janma_nakshatra) + current_nakshatra

    # Map to 9-fold cycle
    tara_num = (distance % 9) + 1

    # Map number to type
    tara_map = {
        1: TaraType.JANMA,
        2: TaraType.SAMPAT,
        3: TaraType.VIPAT,
        4: TaraType.KSHEMA,
        5: TaraType.PRATYAK,
        6: TaraType.SADHANA,
        7: TaraType.NAIDHANA,
        8: TaraType.MITRA,
        9: TaraType.PARAMA_MITRA,
    }

    return tara_map[tara_num], tara_num


def get_tara_score(janma_nakshatra: int, target_nakshatra: int) -> TaraScore:
    """
    Get tārā score for a specific nakshatra relative to janma.

    Args:
        janma_nakshatra: Birth nakshatra (1-27)
        target_nakshatra: Target nakshatra to evaluate (1-27)

    Returns:
        TaraScore object
    """
    tara_type, tara_num = calculate_tara_from_janma(janma_nakshatra, target_nakshatra)
    score = TARA_SCORES[tara_type]

    # Special adjustments for specific combinations
    description = tara_type.description

    # Janma tārā in same pāda is more challenging
    if tara_type == TaraType.JANMA and target_nakshatra == janma_nakshatra:
        score = -0.5
        description = "Same birth star - Generally avoid important activities"

    # Some texts give different scores for 2nd and 3rd cycles
    cycle = ((target_nakshatra - 1) // 9) + 1  # Which cycle (1, 2, or 3)
    if cycle == 2:
        score *= 0.9  # Slightly reduced in 2nd cycle
    elif cycle == 3:
        score *= 0.8  # Further reduced in 3rd cycle

    return TaraScore(
        nakshatra_num=target_nakshatra,
        nakshatra_name=NAKSHATRA_NAMES[target_nakshatra],
        tara_type=tara_type,
        tara_number=tara_num,
        score=score,
        favorable=score > 0.5,
        description=description,
    )


def analyze_tara_bala(
    janma_nakshatra: int,
    current_moon_longitude: float,
    include_full_cycle: bool = False,
) -> TaraBalaAnalysis:
    """
    Perform complete Tārā Bala analysis.

    Args:
        janma_nakshatra: Birth nakshatra (1-27)
        current_moon_longitude: Current Moon longitude in degrees
        include_full_cycle: Whether to analyze all 27 nakshatras

    Returns:
        TaraBalaAnalysis object
    """
    # Calculate current nakshatra
    current_nakshatra = int((current_moon_longitude % 360) * 27 / 360) + 1
    if current_nakshatra > 27:
        current_nakshatra = 27

    # Get current tārā score
    current_tara = get_tara_score(janma_nakshatra, current_nakshatra)

    # Analyze full cycle if requested
    full_cycle = []
    favorable_count = 0
    unfavorable_count = 0
    neutral_count = 0

    if include_full_cycle:
        for nak in range(1, 28):
            score = get_tara_score(janma_nakshatra, nak)
            full_cycle.append(score)

            if score.score > 0.5:
                favorable_count += 1
            elif score.score < -0.5:
                unfavorable_count += 1
            else:
                neutral_count += 1
    else:
        # Just count for current
        if current_tara.score > 0.5:
            favorable_count = 1
        elif current_tara.score < -0.5:
            unfavorable_count = 1
        else:
            neutral_count = 1

    # Determine overall quality
    if current_tara.score >= 1.5:
        overall_quality = "Excellent"
    elif current_tara.score >= 0.5:
        overall_quality = "Good"
    elif current_tara.score >= -0.5:
        overall_quality = "Mixed"
    elif current_tara.score >= -1.5:
        overall_quality = "Challenging"
    else:
        overall_quality = "Difficult"

    # Find next favorable and unfavorable periods
    next_favorable = _find_next_tara_period(janma_nakshatra, current_nakshatra, True)
    next_unfavorable = _find_next_tara_period(janma_nakshatra, current_nakshatra, False)

    return TaraBalaAnalysis(
        birth_nakshatra=janma_nakshatra,
        birth_nakshatra_name=NAKSHATRA_NAMES[janma_nakshatra],
        current_nakshatra=current_nakshatra,
        current_nakshatra_name=NAKSHATRA_NAMES[current_nakshatra],
        current_tara=current_tara,
        full_cycle=full_cycle,
        favorable_count=favorable_count,
        unfavorable_count=unfavorable_count,
        neutral_count=neutral_count,
        overall_quality=overall_quality,
        next_favorable=next_favorable,
        next_unfavorable=next_unfavorable,
    )


def _find_next_tara_period(
    janma_nakshatra: int, current_nakshatra: int, find_favorable: bool
) -> dict | None:
    """
    Find the next favorable or unfavorable tārā period.

    Args:
        janma_nakshatra: Birth nakshatra
        current_nakshatra: Current nakshatra
        find_favorable: True to find favorable, False for unfavorable

    Returns:
        Dictionary with period details or None
    """
    # Check next 9 nakshatras (one complete tārā cycle)
    for i in range(1, 10):
        next_nak = ((current_nakshatra + i - 1) % 27) + 1
        score = get_tara_score(janma_nakshatra, next_nak)

        if find_favorable and score.score > 0.5:
            # Calculate approximate hours until this nakshatra
            # Moon travels ~13.33° per day, each nakshatra is 13.33°
            hours_away = i * 24  # Roughly 1 nakshatra per day

            return {
                "nakshatra": next_nak,
                "nakshatra_name": NAKSHATRA_NAMES[next_nak],
                "tara_type": score.tara_type.display_name,
                "score": score.score,
                "hours_away": hours_away,
                "description": score.description,
            }
        elif not find_favorable and score.score < -0.5:
            hours_away = i * 24

            return {
                "nakshatra": next_nak,
                "nakshatra_name": NAKSHATRA_NAMES[next_nak],
                "tara_type": score.tara_type.display_name,
                "score": score.score,
                "hours_away": hours_away,
                "description": score.description,
            }

    return None


def get_personal_tara_bala(
    birth_moon_longitude: float, current_moon_longitude: float
) -> TaraBalaAnalysis:
    """
    Calculate personal Tārā Bala based on birth Moon.

    This is the traditional personal tārā calculation.

    Args:
        birth_moon_longitude: Moon longitude at birth
        current_moon_longitude: Current Moon longitude

    Returns:
        TaraBalaAnalysis object
    """
    # Calculate janma nakshatra from birth Moon
    janma_nakshatra = int((birth_moon_longitude % 360) * 27 / 360) + 1
    if janma_nakshatra > 27:
        janma_nakshatra = 27

    return analyze_tara_bala(janma_nakshatra, current_moon_longitude, True)


def get_universal_tara_bala(
    reference_nakshatra: int, current_moon_longitude: float
) -> TaraBalaAnalysis:
    """
    Calculate universal Tārā Bala from a reference nakshatra.

    This can be used for muhurta (electional astrology) or
    when analyzing from a specific nakshatra like Ashwini.

    Args:
        reference_nakshatra: Reference nakshatra (1-27)
        current_moon_longitude: Current Moon longitude

    Returns:
        TaraBalaAnalysis object
    """
    return analyze_tara_bala(reference_nakshatra, current_moon_longitude, False)


def get_tara_windows_for_day(
    janma_nakshatra: int,
    date: datetime,
    moon_positions: list[tuple[datetime, float]] | None = None,
) -> list[dict]:
    """
    Get all tārā changes for a specific day.

    Args:
        janma_nakshatra: Birth nakshatra
        date: Date to analyze
        moon_positions: Optional pre-calculated Moon positions

    Returns:
        List of tārā windows with timings
    """
    windows = []

    if moon_positions is None:
        # Would calculate Moon positions for the day
        # For now, using approximation
        moon_speed = 13.33  # Average degrees per day
        start_long = 0  # Would get actual position

        for hour in range(24):
            moon_long = start_long + (hour * moon_speed / 24)
            nakshatra = int((moon_long % 360) * 27 / 360) + 1
            if nakshatra > 27:
                nakshatra = 27
    else:
        # Use provided positions
        last_nakshatra = None

        for timestamp, moon_long in moon_positions:
            nakshatra = int((moon_long % 360) * 27 / 360) + 1
            if nakshatra > 27:
                nakshatra = 27

            if nakshatra != last_nakshatra:
                # Nakshatra changed
                score = get_tara_score(janma_nakshatra, nakshatra)

                windows.append(
                    {
                        "time": timestamp.isoformat(),
                        "nakshatra": nakshatra,
                        "nakshatra_name": NAKSHATRA_NAMES[nakshatra],
                        "tara": score.tara_type.display_name,
                        "score": score.score,
                        "favorable": score.favorable,
                        "description": score.description,
                    }
                )

                last_nakshatra = nakshatra

    return windows


def evaluate_muhurta_tara(muhurta_nakshatra: int, birth_nakshatras: list[int]) -> dict:
    """
    Evaluate a muhurta nakshatra against multiple birth nakshatras.

    Used for finding suitable time for group events.

    Args:
        muhurta_nakshatra: Proposed nakshatra for event
        birth_nakshatras: List of janma nakshatras of participants

    Returns:
        Dictionary with evaluation results
    """
    scores = []
    favorable = 0
    unfavorable = 0

    for janma_nak in birth_nakshatras:
        score = get_tara_score(janma_nak, muhurta_nakshatra)
        scores.append(score)

        if score.favorable:
            favorable += 1
        elif score.score < -0.5:
            unfavorable += 1

    # Calculate average score
    avg_score = sum(s.score for s in scores) / len(scores) if scores else 0

    # Determine suitability
    if avg_score > 1.0:
        suitability = "Excellent"
    elif avg_score > 0.5:
        suitability = "Good"
    elif avg_score > 0:
        suitability = "Fair"
    elif avg_score > -0.5:
        suitability = "Poor"
    else:
        suitability = "Avoid"

    return {
        "muhurta_nakshatra": muhurta_nakshatra,
        "muhurta_name": NAKSHATRA_NAMES[muhurta_nakshatra],
        "participants": len(birth_nakshatras),
        "favorable_for": favorable,
        "unfavorable_for": unfavorable,
        "average_score": round(avg_score, 2),
        "suitability": suitability,
        "individual_scores": [s.to_dict() for s in scores],
    }
