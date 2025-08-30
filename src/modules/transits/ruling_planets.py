"""
KP Ruling Planets framework implementation.
Critical for KP system timing and prediction.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config.feature_flags import require_feature


@dataclass
class RulingPlanets:
    """Container for ruling planets at a moment."""

    ascendant_sign_lord: int
    ascendant_star_lord: int
    ascendant_sub_lord: int
    moon_sign_lord: int
    moon_star_lord: int
    moon_sub_lord: int
    day_lord: int
    hora_lord: int

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary format."""
        return {
            "asc_sign": self.ascendant_sign_lord,
            "asc_star": self.ascendant_star_lord,
            "asc_sub": self.ascendant_sub_lord,
            "moon_sign": self.moon_sign_lord,
            "moon_star": self.moon_star_lord,
            "moon_sub": self.moon_sub_lord,
            "day": self.day_lord,
            "hora": self.hora_lord,
        }

    def get_unique_planets(self) -> set[int]:
        """Get set of unique ruling planets."""
        return {
            self.ascendant_sign_lord,
            self.ascendant_star_lord,
            self.ascendant_sub_lord,
            self.moon_sign_lord,
            self.moon_star_lord,
            self.moon_sub_lord,
            self.day_lord,
            self.hora_lord,
        }

    def get_strength_order(self) -> list[int]:
        """Get ruling planets in order of strength."""
        # Count occurrences
        planet_counts = {}
        for planet in [
            self.ascendant_sign_lord,
            self.ascendant_star_lord,
            self.ascendant_sub_lord,
            self.moon_sign_lord,
            self.moon_star_lord,
            self.moon_sub_lord,
            self.day_lord,
            self.hora_lord,
        ]:
            planet_counts[planet] = planet_counts.get(planet, 0) + 1

        # Sort by count (descending) and planet ID (ascending)
        sorted_planets = sorted(planet_counts.items(), key=lambda x: (-x[1], x[0]))

        return [planet for planet, _ in sorted_planets]


# KP Sign Lords (Rashi Lords)
SIGN_LORDS = {
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

# KP Nakshatra Lords (Star Lords)
NAKSHATRA_LORDS = {
    1: 7,  # Ashwini - Ketu
    2: 6,  # Bharani - Venus
    3: 1,  # Krittika - Sun
    4: 2,  # Rohini - Moon
    5: 9,  # Mrigashira - Mars
    6: 4,  # Ardra - Rahu
    7: 3,  # Punarvasu - Jupiter
    8: 8,  # Pushya - Saturn
    9: 5,  # Ashlesha - Mercury
    10: 7,  # Magha - Ketu
    11: 6,  # Purva Phalguni - Venus
    12: 1,  # Uttara Phalguni - Sun
    13: 2,  # Hasta - Moon
    14: 9,  # Chitra - Mars
    15: 4,  # Swati - Rahu
    16: 3,  # Vishakha - Jupiter
    17: 8,  # Anuradha - Saturn
    18: 5,  # Jyeshtha - Mercury
    19: 7,  # Mula - Ketu
    20: 6,  # Purva Ashadha - Venus
    21: 1,  # Uttara Ashadha - Sun
    22: 2,  # Shravana - Moon
    23: 9,  # Dhanishta - Mars
    24: 4,  # Shatabhisha - Rahu
    25: 3,  # Purva Bhadrapada - Jupiter
    26: 8,  # Uttara Bhadrapada - Saturn
    27: 5,  # Revati - Mercury
}

# KP Sub Lords sequence (249 divisions)
# This is the Vimshottari sequence repeated
VIMSHOTTARI_SEQUENCE = [7, 6, 1, 2, 9, 4, 3, 8, 5]  # Ketu starts
VIMSHOTTARI_YEARS = {
    1: 6,  # Sun
    2: 10,  # Moon
    3: 16,  # Jupiter
    4: 18,  # Rahu
    5: 17,  # Mercury
    6: 20,  # Venus
    7: 7,  # Ketu
    8: 19,  # Saturn
    9: 7,  # Mars
}

# Day Lords (Vara Lords)
DAY_LORDS = {
    0: 1,  # Sunday - Sun
    1: 2,  # Monday - Moon
    2: 9,  # Tuesday - Mars
    3: 5,  # Wednesday - Mercury
    4: 3,  # Thursday - Jupiter
    5: 6,  # Friday - Venus
    6: 8,  # Saturday - Saturn
}

# Hora sequence (planetary hours)
HORA_SEQUENCE = [1, 6, 5, 2, 8, 3, 9]  # Starting from Sun
HORA_ORDER = {
    0: [1, 6, 5, 2, 8, 3, 9],  # Sunday
    1: [2, 8, 3, 9, 1, 6, 5],  # Monday
    2: [9, 1, 6, 5, 2, 8, 3],  # Tuesday
    3: [5, 2, 8, 3, 9, 1, 6],  # Wednesday
    4: [3, 9, 1, 6, 5, 2, 8],  # Thursday
    5: [6, 5, 2, 8, 3, 9, 1],  # Friday
    6: [8, 3, 9, 1, 6, 5, 2],  # Saturday
}


@require_feature("kp_ruling_planets")
def calculate_ruling_planets(ctx: dict) -> dict[str, any]:
    """Calculate KP Ruling Planets for a given moment.

    Args:
        ctx: Context with timestamp, ascendant, moon position, location

    Returns:
        Dictionary with ruling planets information
    """
    timestamp = ctx.get("timestamp")
    if not timestamp:
        return {}

    # Ensure timezone aware
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    # Get positions
    asc_longitude = ctx.get("ascendant", 0.0)
    moon_longitude = ctx.get("moon_longitude", 0.0)

    # Calculate Ascendant lords
    asc_sign = int(asc_longitude / 30) + 1
    asc_nakshatra = int(asc_longitude * 27 / 360) + 1
    asc_sub = calculate_sub_lord(asc_longitude)

    asc_sign_lord = SIGN_LORDS[asc_sign]
    asc_star_lord = NAKSHATRA_LORDS[asc_nakshatra]
    asc_sub_lord = asc_sub

    # Calculate Moon lords
    moon_sign = int(moon_longitude / 30) + 1
    moon_nakshatra = int(moon_longitude * 27 / 360) + 1
    moon_sub = calculate_sub_lord(moon_longitude)

    moon_sign_lord = SIGN_LORDS[moon_sign]
    moon_star_lord = NAKSHATRA_LORDS[moon_nakshatra]
    moon_sub_lord = moon_sub

    # Day lord
    weekday = timestamp.weekday()
    # Convert Python weekday (0=Monday) to our system (0=Sunday)
    weekday = (weekday + 1) % 7
    day_lord = DAY_LORDS[weekday]

    # Hora lord
    hora_lord = calculate_hora_lord(timestamp, ctx.get("sunrise"), weekday)

    # Create RulingPlanets object
    rp = RulingPlanets(
        ascendant_sign_lord=asc_sign_lord,
        ascendant_star_lord=asc_star_lord,
        ascendant_sub_lord=asc_sub_lord,
        moon_sign_lord=moon_sign_lord,
        moon_star_lord=moon_star_lord,
        moon_sub_lord=moon_sub_lord,
        day_lord=day_lord,
        hora_lord=hora_lord,
    )

    return {
        "ruling_planets": rp.to_dict(),
        "unique_rp": list(rp.get_unique_planets()),
        "strength_order": rp.get_strength_order(),
        "rp_count": len(rp.get_unique_planets()),
    }


def calculate_sub_lord(longitude: float) -> int:
    """Calculate KP Sub Lord for a given longitude.

    The zodiac is divided into 249 subs based on Vimshottari proportions.
    """
    # Each nakshatra is 13°20' = 800'
    # Total zodiac = 360° = 21600'

    # Convert longitude to minutes
    total_minutes = longitude * 60

    # Calculate which sub we're in (0-248)
    sub_index = 0
    accumulated = 0.0

    for nak in range(27):  # 27 nakshatras
        nak_lord = NAKSHATRA_LORDS[nak + 1]

        for sub_planet in VIMSHOTTARI_SEQUENCE:
            # Calculate this sub's span in minutes
            sub_span = (800 * VIMSHOTTARI_YEARS[sub_planet]) / 120

            if accumulated + sub_span > total_minutes:
                return sub_planet

            accumulated += sub_span
            sub_index += 1

    return VIMSHOTTARI_SEQUENCE[-1]  # Fallback


def calculate_hora_lord(
    timestamp: datetime, sunrise: datetime | None, weekday: int
) -> int:
    """Calculate planetary hour (Hora) lord.

    Each day is divided into 24 planetary hours, starting from sunrise.
    """
    if not sunrise:
        # Default to 6 AM if sunrise not provided
        sunrise = timestamp.replace(hour=6, minute=0, second=0, microsecond=0)

    # Calculate hours since sunrise
    time_diff = timestamp - sunrise
    hours_since_sunrise = time_diff.total_seconds() / 3600

    # Get hora index (0-23)
    hora_index = int(hours_since_sunrise) % 24

    # Handle negative hours (before sunrise)
    if hours_since_sunrise < 0:
        # Use previous day's sequence
        prev_weekday = (weekday - 1) % 7
        hora_sequence = HORA_ORDER[prev_weekday]
        hora_index = 24 + int(hours_since_sunrise)
    else:
        hora_sequence = HORA_ORDER[weekday]

    # Adjust for day/night hours (12 day, 12 night)
    if hora_index < 12:
        # Day hora
        planet_index = hora_index % 7
    else:
        # Night hora
        planet_index = (hora_index - 12) % 7

    return hora_sequence[planet_index]


@require_feature("kp_ruling_planets")
def find_rp_activation_windows(ctx: dict, duration_hours: int = 24) -> list[dict]:
    """Find time windows when specific ruling planets are activated.

    Args:
        ctx: Context with starting timestamp and target planets
        duration_hours: Hours to scan ahead

    Returns:
        List of activation windows
    """
    start_time = ctx.get("timestamp", datetime.now(UTC))
    target_planets = set(ctx.get("target_planets", []))

    if not target_planets:
        return []

    windows = []
    current_time = start_time
    end_time = start_time + timedelta(hours=duration_hours)

    # Scan in 1-minute intervals
    while current_time < end_time:
        # Calculate ruling planets at this moment
        temp_ctx = ctx.copy()
        temp_ctx["timestamp"] = current_time

        rp_data = calculate_ruling_planets(temp_ctx)
        if not rp_data:
            current_time += timedelta(minutes=1)
            continue

        current_rp = set(rp_data.get("unique_rp", []))

        # Check if target planets are in current RP
        matches = target_planets.intersection(current_rp)

        if matches:
            # Found activation
            if not windows or windows[-1]["end"] < current_time - timedelta(minutes=1):
                # Start new window
                windows.append(
                    {
                        "start": current_time,
                        "end": current_time,
                        "planets": list(matches),
                        "strength": len(matches),
                    }
                )
            else:
                # Extend current window
                windows[-1]["end"] = current_time
                windows[-1]["planets"] = list(
                    set(windows[-1]["planets"]).union(matches)
                )
                windows[-1]["strength"] = max(windows[-1]["strength"], len(matches))

        current_time += timedelta(minutes=1)

    return windows


@require_feature("kp_ruling_planets")
def evaluate_rp_strength(
    ruling_planets: RulingPlanets, significators: list[int]
) -> float:
    """Evaluate strength of ruling planets for given significators.

    Args:
        ruling_planets: Current ruling planets
        significators: List of required significator planets

    Returns:
        Strength score (0-100)
    """
    if not significators:
        return 0.0

    rp_set = ruling_planets.get_unique_planets()
    matches = len(rp_set.intersection(set(significators)))

    # Base score from matches
    base_score = (matches / len(significators)) * 60

    # Bonus for repetition in RP
    rp_list = [
        ruling_planets.ascendant_sign_lord,
        ruling_planets.ascendant_star_lord,
        ruling_planets.ascendant_sub_lord,
        ruling_planets.moon_sign_lord,
        ruling_planets.moon_star_lord,
        ruling_planets.moon_sub_lord,
        ruling_planets.day_lord,
        ruling_planets.hora_lord,
    ]

    repetition_bonus = 0
    for sig in significators:
        count = rp_list.count(sig)
        if count > 1:
            repetition_bonus += (count - 1) * 5

    # Special bonus if Moon or Ascendant sublord matches
    if ruling_planets.moon_sub_lord in significators:
        repetition_bonus += 10
    if ruling_planets.ascendant_sub_lord in significators:
        repetition_bonus += 10

    return min(100, base_score + repetition_bonus)


def get_rp_interpretation(ruling_planets: RulingPlanets) -> dict[str, str]:
    """Provide interpretation of ruling planets configuration.

    Args:
        ruling_planets: Current ruling planets

    Returns:
        Dictionary with interpretations
    """
    interpretations = {}

    # Check for strong repetitions
    rp_list = [
        ruling_planets.ascendant_sign_lord,
        ruling_planets.ascendant_star_lord,
        ruling_planets.ascendant_sub_lord,
        ruling_planets.moon_sign_lord,
        ruling_planets.moon_star_lord,
        ruling_planets.moon_sub_lord,
        ruling_planets.day_lord,
        ruling_planets.hora_lord,
    ]

    planet_counts = {}
    for planet in rp_list:
        planet_counts[planet] = planet_counts.get(planet, 0) + 1

    # Find strongest planet
    max_count = max(planet_counts.values())
    strongest = [p for p, c in planet_counts.items() if c == max_count]

    if max_count >= 4:
        interpretations["strength"] = "Very Strong"
        interpretations["dominant"] = strongest[0]
    elif max_count >= 3:
        interpretations["strength"] = "Strong"
        interpretations["dominant"] = strongest[0]
    elif max_count >= 2:
        interpretations["strength"] = "Medium"
        interpretations["dominant"] = strongest[0] if len(strongest) == 1 else None
    else:
        interpretations["strength"] = "Scattered"
        interpretations["dominant"] = None

    # Check for benefic/malefic dominance
    benefics = {2, 3, 5, 6}  # Moon, Jupiter, Mercury, Venus
    malefics = {1, 4, 7, 8, 9}  # Sun, Rahu, Ketu, Saturn, Mars

    rp_set = ruling_planets.get_unique_planets()
    benefic_count = len(rp_set.intersection(benefics))
    malefic_count = len(rp_set.intersection(malefics))

    if benefic_count > malefic_count:
        interpretations["nature"] = "Benefic"
    elif malefic_count > benefic_count:
        interpretations["nature"] = "Malefic"
    else:
        interpretations["nature"] = "Mixed"

    return interpretations
