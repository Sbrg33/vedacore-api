"""
Enhanced Panchanga calculations module.
Complete implementation of the five limbs of Vedic calendar.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from config.feature_flags import require_feature


@dataclass
class PanchangaData:
    """Complete Panchanga information."""

    tithi: dict[str, any]  # Lunar day
    vara: dict[str, any]  # Weekday
    nakshatra: dict[str, any]  # Lunar mansion
    yoga: dict[str, any]  # Sun-Moon yoga
    karana: dict[str, any]  # Half-tithi
    paksha: str  # Lunar fortnight
    masa: dict[str, any]  # Lunar month
    ritu: str  # Season
    special_events: list[str]  # Special days/festivals
    quality_score: float  # Overall muhurta quality

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "tithi": self.tithi,
            "vara": self.vara,
            "nakshatra": self.nakshatra,
            "yoga": self.yoga,
            "karana": self.karana,
            "paksha": self.paksha,
            "masa": self.masa,
            "ritu": self.ritu,
            "special_events": self.special_events,
            "quality_score": round(self.quality_score, 2),
        }


# Tithi (Lunar Day) Names
TITHI_NAMES = {
    1: "Pratipada",
    2: "Dwitiya",
    3: "Tritiya",
    4: "Chaturthi",
    5: "Panchami",
    6: "Shashthi",
    7: "Saptami",
    8: "Ashtami",
    9: "Navami",
    10: "Dashami",
    11: "Ekadashi",
    12: "Dwadashi",
    13: "Trayodashi",
    14: "Chaturdashi",
    15: "Purnima",  # Full Moon
    16: "Pratipada",
    17: "Dwitiya",
    18: "Tritiya",
    19: "Chaturthi",
    20: "Panchami",
    21: "Shashthi",
    22: "Saptami",
    23: "Ashtami",
    24: "Navami",
    25: "Dashami",
    26: "Ekadashi",
    27: "Dwadashi",
    28: "Trayodashi",
    29: "Chaturdashi",
    30: "Amavasya",  # New Moon
}

# Tithi Lords (Deities)
TITHI_LORDS = {
    1: "Agni",
    2: "Brahma",
    3: "Gauri",
    4: "Ganesha",
    5: "Naga",
    6: "Kartikeya",
    7: "Surya",
    8: "Shiva",
    9: "Durga",
    10: "Yama",
    11: "Vishvedeva",
    12: "Vishnu",
    13: "Kamadeva",
    14: "Shiva",
    15: "Moon",
    16: "Agni",
    17: "Brahma",
    18: "Gauri",
    19: "Ganesha",
    20: "Naga",
    21: "Kartikeya",
    22: "Surya",
    23: "Shiva",
    24: "Durga",
    25: "Yama",
    26: "Vishvedeva",
    27: "Vishnu",
    28: "Kamadeva",
    29: "Shiva",
    30: "Pitru",
}

# Tithi categories for quality assessment
GOOD_TITHIS = {1, 2, 3, 5, 7, 10, 11, 13}  # Generally auspicious
BAD_TITHIS = {4, 6, 8, 9, 12, 14, 30}  # Generally inauspicious
SPECIAL_TITHIS = {11, 15, 30}  # Ekadashi, Purnima, Amavasya

# Vara (Weekday) Names and Lords
VARA_NAMES = {
    0: "Ravivara",  # Sunday
    1: "Somavara",  # Monday
    2: "Mangalavara",  # Tuesday
    3: "Budhavara",  # Wednesday
    4: "Guruvara",  # Thursday
    5: "Shukravara",  # Friday
    6: "Shanivara",  # Saturday
}

VARA_LORDS = {
    0: "Sun",
    1: "Moon",
    2: "Mars",
    3: "Mercury",
    4: "Jupiter",
    5: "Venus",
    6: "Saturn",
}

# Nakshatra Names
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
    19: "Mula",
    20: "Purva Ashadha",
    21: "Uttara Ashadha",
    22: "Shravana",
    23: "Dhanishta",
    24: "Shatabhisha",
    25: "Purva Bhadrapada",
    26: "Uttara Bhadrapada",
    27: "Revati",
}

# Nakshatra Deities
NAKSHATRA_DEITIES = {
    1: "Ashwini Kumaras",
    2: "Yama",
    3: "Agni",
    4: "Brahma",
    5: "Soma",
    6: "Rudra",
    7: "Aditi",
    8: "Brihaspati",
    9: "Serpent",
    10: "Pitrus",
    11: "Bhaga",
    12: "Aryama",
    13: "Savitar",
    14: "Twashtar",
    15: "Vayu",
    16: "Indragni",
    17: "Mitra",
    18: "Indra",
    19: "Nirrti",
    20: "Apas",
    21: "Vishvedeva",
    22: "Vishnu",
    23: "Vasus",
    24: "Varuna",
    25: "Ajaikapat",
    26: "Ahirbudhnya",
    27: "Pushan",
}

# Nakshatra Gunas (Qualities)
NAKSHATRA_GUNAS = {
    # Sattva (Harmony)
    "sattva": {4, 8, 13, 17, 21, 22, 26, 27},
    # Rajas (Activity)
    "rajas": {1, 5, 7, 10, 11, 14, 15, 20},
    # Tamas (Inertia)
    "tamas": {2, 3, 6, 9, 12, 16, 18, 19, 23, 24, 25},
}

# Yoga Names (27 Yogas)
YOGA_NAMES = {
    1: "Vishkumbha",
    2: "Priti",
    3: "Ayushman",
    4: "Saubhagya",
    5: "Shobhana",
    6: "Atiganda",
    7: "Sukarman",
    8: "Dhriti",
    9: "Shula",
    10: "Ganda",
    11: "Vriddhi",
    12: "Dhruva",
    13: "Vyaghata",
    14: "Harshana",
    15: "Vajra",
    16: "Siddhi",
    17: "Vyatipata",
    18: "Variyan",
    19: "Parigha",
    20: "Shiva",
    21: "Siddha",
    22: "Sadhya",
    23: "Shubha",
    24: "Shukla",
    25: "Brahma",
    26: "Indra",
    27: "Vaidhriti",
}

# Good and Bad Yogas
GOOD_YOGAS = {2, 3, 4, 5, 7, 8, 11, 12, 14, 16, 20, 21, 22, 23, 24, 25, 26}
BAD_YOGAS = {1, 6, 9, 10, 13, 15, 17, 19, 27}

# Karana Names (11 Karanas, repeated)
KARANA_NAMES = {
    1: "Bava",
    2: "Balava",
    3: "Kaulava",
    4: "Taitila",
    5: "Gara",
    6: "Vanija",
    7: "Vishti",
    8: "Bava",
    9: "Balava",
    10: "Kaulava",
    11: "Taitila",
    12: "Gara",
    13: "Vanija",
    14: "Vishti",
    15: "Bava",
    16: "Balava",
    17: "Kaulava",
    18: "Taitila",
    19: "Gara",
    20: "Vanija",
    21: "Vishti",
    22: "Bava",
    23: "Balava",
    24: "Kaulava",
    25: "Taitila",
    26: "Gara",
    27: "Vanija",
    28: "Vishti",
    29: "Bava",
    30: "Balava",
    31: "Kaulava",
    32: "Taitila",
    33: "Gara",
    34: "Vanija",
    35: "Vishti",
    36: "Bava",
    37: "Balava",
    38: "Kaulava",
    39: "Taitila",
    40: "Gara",
    41: "Vanija",
    42: "Vishti",
    43: "Bava",
    44: "Balava",
    45: "Kaulava",
    46: "Taitila",
    47: "Gara",
    48: "Vanija",
    49: "Vishti",
    50: "Bava",
    51: "Balava",
    52: "Kaulava",
    53: "Taitila",
    54: "Gara",
    55: "Vanija",
    56: "Vishti",
    57: "Shakuni",
    58: "Chatushpada",
    59: "Naga",
    60: "Kimstughna",
}

# Fixed Karanas (last 4)
FIXED_KARANAS = {57: "Shakuni", 58: "Chatushpada", 59: "Naga", 60: "Kimstughna"}
BAD_KARANAS = {7, 14, 21, 28, 35, 42, 49, 56, 57, 58, 59, 60}  # Vishti and fixed

# Lunar Months
LUNAR_MONTHS = {
    1: "Chaitra",
    2: "Vaishakha",
    3: "Jyeshtha",
    4: "Ashadha",
    5: "Shravana",
    6: "Bhadrapada",
    7: "Ashwina",
    8: "Kartika",
    9: "Margashirsha",
    10: "Pausha",
    11: "Magha",
    12: "Phalguna",
}

# Seasons (Ritus)
RITUS = {
    1: "Vasanta",  # Spring (Chaitra-Vaishakha)
    2: "Grishma",  # Summer (Jyeshtha-Ashadha)
    3: "Varsha",  # Monsoon (Shravana-Bhadrapada)
    4: "Sharad",  # Autumn (Ashwina-Kartika)
    5: "Hemanta",  # Pre-winter (Margashirsha-Pausha)
    6: "Shishira",  # Winter (Magha-Phalguna)
}


@require_feature("panchanga_full")
def calculate_enhanced_panchanga(ctx: dict) -> dict[str, any]:
    """Calculate complete Panchanga with all five limbs.

    Args:
        ctx: Context with timestamp, sun_longitude, moon_longitude

    Returns:
        Dictionary with complete Panchanga data
    """
    timestamp = ctx.get("timestamp", datetime.now(UTC))
    sun_long = ctx.get("sun_longitude", 0.0)
    moon_long = ctx.get("moon_longitude", 0.0)

    # Calculate Tithi
    tithi_data = calculate_tithi(sun_long, moon_long)

    # Calculate Vara (Weekday)
    vara_data = calculate_vara(timestamp)

    # Calculate Nakshatra
    nakshatra_data = calculate_nakshatra(moon_long)

    # Calculate Yoga
    yoga_data = calculate_yoga(sun_long, moon_long)

    # Calculate Karana
    karana_data = calculate_karana(tithi_data["number"])

    # Determine Paksha (Lunar Fortnight)
    paksha = "Shukla" if tithi_data["number"] <= 15 else "Krishna"

    # Calculate Lunar Month
    masa_data = calculate_masa(sun_long, moon_long)

    # Calculate Ritu (Season)
    ritu = calculate_ritu(masa_data["number"])

    # Check for special events
    special_events = check_special_events(
        tithi_data["number"],
        vara_data["number"],
        nakshatra_data["number"],
        masa_data["number"],
    )

    # Calculate overall quality score
    quality_score = calculate_muhurta_quality(
        tithi_data, vara_data, nakshatra_data, yoga_data, karana_data, special_events
    )

    # Create PanchangaData object
    panchanga = PanchangaData(
        tithi=tithi_data,
        vara=vara_data,
        nakshatra=nakshatra_data,
        yoga=yoga_data,
        karana=karana_data,
        paksha=paksha,
        masa=masa_data,
        ritu=ritu,
        special_events=special_events,
        quality_score=quality_score,
    )

    return {"panchanga": panchanga.to_dict()}


def calculate_tithi(sun_long: float, moon_long: float) -> dict[str, any]:
    """Calculate Tithi (lunar day) from Sun-Moon positions.

    Args:
        sun_long: Sun's longitude
        moon_long: Moon's longitude

    Returns:
        Tithi information
    """
    # Calculate angular distance
    diff = moon_long - sun_long
    if diff < 0:
        diff += 360

    # Each tithi is 12 degrees
    tithi_num = int(diff / 12) + 1
    if tithi_num > 30:
        tithi_num = 30

    # Calculate progress within tithi
    tithi_progress = (diff % 12) / 12 * 100

    # Calculate time to next tithi (simplified)
    remaining_degrees = 12 - (diff % 12)
    # Moon moves ~13°/day, Sun ~1°/day, relative ~12°/day
    hours_to_next = remaining_degrees / 0.5  # ~0.5°/hour relative motion

    return {
        "number": tithi_num,
        "name": TITHI_NAMES[tithi_num],
        "lord": TITHI_LORDS[tithi_num],
        "progress": round(tithi_progress, 1),
        "hours_to_next": round(hours_to_next, 1),
        "is_auspicious": tithi_num in GOOD_TITHIS,
        "is_special": tithi_num in SPECIAL_TITHIS,
    }


def calculate_vara(timestamp: datetime) -> dict[str, any]:
    """Calculate Vara (weekday) information.

    Args:
        timestamp: Current time

    Returns:
        Vara information
    """
    # Get weekday (0=Monday in Python, adjust to 0=Sunday)
    weekday = (timestamp.weekday() + 1) % 7

    # Calculate progress through the day (sunrise to sunrise)
    # Simplified - using midnight to midnight
    hours_since_midnight = timestamp.hour + timestamp.minute / 60
    day_progress = hours_since_midnight / 24 * 100

    return {
        "number": weekday,
        "name": VARA_NAMES[weekday],
        "lord": VARA_LORDS[weekday],
        "progress": round(day_progress, 1),
        "is_benefic": weekday in {1, 3, 4, 5},  # Moon, Mercury, Jupiter, Venus
    }


def calculate_nakshatra(moon_long: float) -> dict[str, any]:
    """Calculate Nakshatra (lunar mansion) from Moon's position.

    Args:
        moon_long: Moon's longitude

    Returns:
        Nakshatra information
    """
    # Each nakshatra is 13°20' = 13.333°
    nakshatra_num = int(moon_long / 13.333333) + 1
    if nakshatra_num > 27:
        nakshatra_num = 27

    # Calculate pada (quarter)
    pada = int((moon_long % 13.333333) / 3.333333) + 1

    # Calculate progress
    nakshatra_progress = (moon_long % 13.333333) / 13.333333 * 100

    # Determine guna
    guna = "sattva"
    for g, nakshatras in NAKSHATRA_GUNAS.items():
        if nakshatra_num in nakshatras:
            guna = g
            break

    # Calculate time to next (Moon moves ~13°/day)
    remaining = 13.333333 - (moon_long % 13.333333)
    hours_to_next = remaining / (13.176 / 24)  # Moon's average daily motion

    return {
        "number": nakshatra_num,
        "name": NAKSHATRA_NAMES[nakshatra_num],
        "deity": NAKSHATRA_DEITIES[nakshatra_num],
        "pada": pada,
        "guna": guna,
        "progress": round(nakshatra_progress, 1),
        "hours_to_next": round(hours_to_next, 1),
    }


def calculate_yoga(sun_long: float, moon_long: float) -> dict[str, any]:
    """Calculate Yoga from combined Sun-Moon longitudes.

    Args:
        sun_long: Sun's longitude
        moon_long: Moon's longitude

    Returns:
        Yoga information
    """
    # Yoga is based on sum of longitudes
    combined = (sun_long + moon_long) % 360

    # Each yoga is 13°20' = 13.333°
    yoga_num = int(combined / 13.333333) + 1
    if yoga_num > 27:
        yoga_num = 27

    # Calculate progress
    yoga_progress = (combined % 13.333333) / 13.333333 * 100

    # Time to next
    remaining = 13.333333 - (combined % 13.333333)
    # Combined motion ~14°/day
    hours_to_next = remaining / (14 / 24)

    return {
        "number": yoga_num,
        "name": YOGA_NAMES[yoga_num],
        "is_auspicious": yoga_num in GOOD_YOGAS,
        "progress": round(yoga_progress, 1),
        "hours_to_next": round(hours_to_next, 1),
    }


def calculate_karana(tithi_num: int) -> dict[str, any]:
    """Calculate Karana (half-tithi) from Tithi number.

    Args:
        tithi_num: Current tithi number

    Returns:
        Karana information
    """
    # Each tithi has 2 karanas
    # First 56 karanas repeat, last 4 are fixed

    # Calculate karana index (1-60)
    if tithi_num == 30:  # Amavasya has last 4 fixed karanas
        karana_index = 57  # Could be 57-60, simplified
    else:
        # Calculate based on tithi
        karana_base = (tithi_num - 1) * 2 + 1
        # Take modulo for repeating karanas
        if karana_base <= 56:
            karana_index = ((karana_base - 1) % 7) + 1
            if tithi_num > 1:
                karana_index = karana_base
        else:
            karana_index = karana_base

    # Adjust for proper cycling
    if karana_index > 60:
        karana_index = ((karana_index - 1) % 56) + 1

    # Get name
    if karana_index in FIXED_KARANAS:
        karana_name = FIXED_KARANAS[karana_index]
    else:
        cycle_index = ((karana_index - 1) % 7) + 1
        karana_name = list(KARANA_NAMES.values())[cycle_index - 1]

    return {
        "number": karana_index,
        "name": karana_name,
        "is_auspicious": karana_index not in BAD_KARANAS,
        "is_fixed": karana_index in FIXED_KARANAS,
    }


def calculate_masa(sun_long: float, moon_long: float) -> dict[str, any]:
    """Calculate lunar month.

    Args:
        sun_long: Sun's longitude
        moon_long: Moon's longitude

    Returns:
        Masa (month) information
    """
    # Simplified: based on Sun's position in zodiac
    sun_sign = int(sun_long / 30) + 1

    # Map to lunar month (approximate)
    masa_num = ((sun_sign + 8) % 12) + 1  # Offset for lunar calendar

    return {"number": masa_num, "name": LUNAR_MONTHS[masa_num], "solar_month": sun_sign}


def calculate_ritu(masa_num: int) -> str:
    """Calculate season from lunar month.

    Args:
        masa_num: Lunar month number

    Returns:
        Season name
    """
    # Each season is 2 months
    ritu_num = ((masa_num - 1) // 2) + 1
    if ritu_num > 6:
        ritu_num = 6

    return RITUS[ritu_num]


def check_special_events(tithi: int, vara: int, nakshatra: int, masa: int) -> list[str]:
    """Check for special events and observances.

    Args:
        tithi: Tithi number
        vara: Weekday number
        nakshatra: Nakshatra number
        masa: Month number

    Returns:
        List of special events
    """
    events = []

    # Ekadashi (11th day)
    if tithi in {11, 26}:
        events.append("Ekadashi (Fasting day)")

    # Purnima (Full Moon)
    if tithi == 15:
        events.append("Purnima (Full Moon)")
        if masa == 7:  # Ashwina month
            events.append("Sharad Purnima")
        elif masa == 12:  # Phalguna month
            events.append("Holi Purnima")

    # Amavasya (New Moon)
    if tithi == 30:
        events.append("Amavasya (New Moon)")
        if masa == 7:  # Ashwina month
            events.append("Mahalaya Amavasya")

    # Pradosha (13th day)
    if tithi in {13, 28}:
        if vara == 6:  # Saturday
            events.append("Shani Pradosha")
        else:
            events.append("Pradosha Vrata")

    # Shivaratri (14th day of Krishna Paksha)
    if tithi == 29 and masa == 11:  # Magha month
        events.append("Maha Shivaratri")
    elif tithi == 29:
        events.append("Masa Shivaratri")

    # Sankranti (Solar ingress - simplified)
    # This would need actual solar transit calculation

    # Special Nakshatra days
    if nakshatra == 8:  # Pushya
        events.append("Pushya Nakshatra (Auspicious)")
    elif nakshatra == 22:  # Shravana
        if vara == 1:  # Monday
            events.append("Shravana Somavar")

    return events


def calculate_muhurta_quality(
    tithi: dict,
    vara: dict,
    nakshatra: dict,
    yoga: dict,
    karana: dict,
    special_events: list[str],
) -> float:
    """Calculate overall muhurta quality score.

    Args:
        tithi: Tithi data
        vara: Vara data
        nakshatra: Nakshatra data
        yoga: Yoga data
        karana: Karana data
        special_events: List of special events

    Returns:
        Quality score (0-100)
    """
    score = 50.0  # Base score

    # Tithi contribution (20%)
    if tithi["is_auspicious"]:
        score += 10
    else:
        score -= 5

    if tithi["is_special"]:
        score += 5  # Special days have significance

    # Vara contribution (15%)
    if vara["is_benefic"]:
        score += 7.5
    else:
        score -= 3.75

    # Nakshatra contribution (25%)
    if nakshatra["guna"] == "sattva":
        score += 12.5
    elif nakshatra["guna"] == "rajas":
        score += 6.25
    else:  # tamas
        score -= 6.25

    # Yoga contribution (20%)
    if yoga["is_auspicious"]:
        score += 10
    else:
        score -= 10

    # Karana contribution (10%)
    if karana["is_auspicious"]:
        score += 5
    else:
        score -= 5

    # Special events bonus (10%)
    if special_events:
        if any("auspicious" in e.lower() for e in special_events):
            score += 10
        elif any("fasting" in e.lower() for e in special_events):
            score += 5  # Spiritual significance

    # Ensure score is within bounds
    score = max(0, min(100, score))

    return score


@require_feature("panchanga_full")
def get_panchanga_recommendations(panchanga_data: dict) -> dict[str, list[str]]:
    """Get activity recommendations based on Panchanga.

    Args:
        panchanga_data: Panchanga calculation results

    Returns:
        Recommendations for various activities
    """
    if "panchanga" not in panchanga_data:
        return {}

    p = panchanga_data["panchanga"]
    recommendations = {"favorable": [], "avoid": [], "spiritual": [], "timing": []}

    # Based on quality score
    quality = p.get("quality_score", 50)

    if quality >= 75:
        recommendations["favorable"].extend(
            ["New ventures", "Important decisions", "Investments", "Signing contracts"]
        )
    elif quality >= 60:
        recommendations["favorable"].extend(["Routine business", "Meetings", "Travel"])
    else:
        recommendations["avoid"].extend(
            ["Major initiatives", "Financial commitments", "Important negotiations"]
        )

    # Tithi-based recommendations
    tithi = p.get("tithi", {})
    if tithi.get("number") in {11, 26}:  # Ekadashi
        recommendations["spiritual"].append("Fasting recommended")
        recommendations["avoid"].append("Material beginnings")
    elif tithi.get("number") == 30:  # Amavasya
        recommendations["spiritual"].append("Ancestor worship")
        recommendations["avoid"].append("New ventures")

    # Special events
    for event in p.get("special_events", []):
        if "Ekadashi" in event:
            recommendations["spiritual"].append("Vishnu worship")
        elif "Pradosha" in event:
            recommendations["spiritual"].append("Shiva worship")

    # Timing recommendations
    if tithi.get("hours_to_next", 24) < 2:
        recommendations["timing"].append("Tithi change imminent")
    if p.get("nakshatra", {}).get("hours_to_next", 24) < 2:
        recommendations["timing"].append("Nakshatra change imminent")

    return recommendations
