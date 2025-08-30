"""
Daily timing windows module.
Calculates Rahu Kaal, Yamaganda, Gulika and other daily periods.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config.feature_flags import require_feature


@dataclass
class TimeWindow:
    """Represents a time window with quality."""

    name: str
    start_time: datetime
    end_time: datetime
    quality: str  # 'avoid', 'neutral', 'good', 'excellent'
    planet_lord: str | None = None
    description: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "start": self.start_time.isoformat(),
            "end": self.end_time.isoformat(),
            "duration_minutes": int(
                (self.end_time - self.start_time).total_seconds() / 60
            ),
            "quality": self.quality,
            "planet_lord": self.planet_lord,
            "description": self.description,
        }


@dataclass
class DailyWindows:
    """Container for all daily timing windows."""

    rahu_kaal: TimeWindow
    yamaganda: TimeWindow
    gulika: TimeWindow
    abhijit_muhurta: TimeWindow | None
    brahma_muhurta: TimeWindow
    hora_windows: list[TimeWindow]
    choghadiya_windows: list[TimeWindow]
    quality_summary: dict[str, int]  # Count by quality

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "rahu_kaal": self.rahu_kaal.to_dict(),
            "yamaganda": self.yamaganda.to_dict(),
            "gulika": self.gulika.to_dict(),
            "abhijit_muhurta": (
                self.abhijit_muhurta.to_dict() if self.abhijit_muhurta else None
            ),
            "brahma_muhurta": self.brahma_muhurta.to_dict(),
            "hora_windows": [h.to_dict() for h in self.hora_windows],
            "choghadiya_windows": [c.to_dict() for c in self.choghadiya_windows],
            "quality_summary": self.quality_summary,
        }


# Daily inauspicious periods by weekday
# Each day divided into 8 parts, these indicate which part is inauspicious
RAHU_KAAL_PARTS = {
    0: 8,  # Sunday - 8th part
    1: 2,  # Monday - 2nd part
    2: 7,  # Tuesday - 7th part
    3: 5,  # Wednesday - 5th part
    4: 6,  # Thursday - 6th part
    5: 4,  # Friday - 4th part
    6: 3,  # Saturday - 3rd part
}

YAMAGANDA_PARTS = {
    0: 5,  # Sunday - 5th part
    1: 4,  # Monday - 4th part
    2: 3,  # Tuesday - 3rd part
    3: 2,  # Wednesday - 2nd part
    4: 1,  # Thursday - 1st part
    5: 7,  # Friday - 7th part
    6: 6,  # Saturday - 6th part
}

GULIKA_PARTS = {
    0: 7,  # Sunday - 7th part
    1: 6,  # Monday - 6th part
    2: 5,  # Tuesday - 5th part
    3: 4,  # Wednesday - 4th part
    4: 3,  # Thursday - 3rd part
    5: 2,  # Friday - 2nd part
    6: 1,  # Saturday - 1st part
}

# Hora sequence (planetary hours)
HORA_SEQUENCE = {
    0: ["Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars"],  # Sunday
    1: ["Moon", "Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury"],  # Monday
    2: ["Mars", "Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter"],  # Tuesday
    3: ["Mercury", "Moon", "Saturn", "Jupiter", "Mars", "Sun", "Venus"],  # Wednesday
    4: ["Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon", "Saturn"],  # Thursday
    5: ["Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars", "Sun"],  # Friday
    6: ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"],  # Saturday
}

# Hora quality by planet
HORA_QUALITY = {
    "Sun": "neutral",
    "Moon": "good",
    "Mars": "avoid",
    "Mercury": "good",
    "Jupiter": "excellent",
    "Venus": "good",
    "Saturn": "avoid",
    "Rahu": "avoid",
    "Ketu": "avoid",
}

# Choghadiya names and qualities (for day and night)
CHOGHADIYA_DAY = [
    ("Amrit", "excellent"),  # Nectar
    ("Kaal", "avoid"),  # Death
    ("Shubh", "good"),  # Auspicious
    ("Rog", "avoid"),  # Disease
    ("Udveg", "neutral"),  # Anxiety
    ("Char", "good"),  # Mobile
    ("Labh", "excellent"),  # Gain
    ("Amrit", "excellent"),  # Repeats
]

CHOGHADIYA_NIGHT = [
    ("Shubh", "good"),
    ("Amrit", "excellent"),
    ("Char", "good"),
    ("Rog", "avoid"),
    ("Kaal", "avoid"),
    ("Labh", "excellent"),
    ("Udveg", "neutral"),
    ("Shubh", "good"),
]


@require_feature("daily_windows")
def calculate_daily_windows(ctx: dict) -> dict[str, any]:
    """Calculate all daily timing windows.

    Args:
        ctx: Context with date, sunrise, sunset, latitude, longitude

    Returns:
        Dictionary with all daily windows
    """
    date = ctx.get("date", datetime.now(UTC).date())
    sunrise = ctx.get("sunrise")
    sunset = ctx.get("sunset")

    # If sunrise/sunset not provided, use default (6 AM / 6 PM)
    if not sunrise:
        sunrise = datetime.combine(
            date, datetime.min.time().replace(hour=6, tzinfo=UTC)
        )
    if not sunset:
        sunset = datetime.combine(
            date, datetime.min.time().replace(hour=18, tzinfo=UTC)
        )

    # Ensure timezone aware
    if sunrise.tzinfo is None:
        sunrise = sunrise.replace(tzinfo=UTC)
    if sunset.tzinfo is None:
        sunset = sunset.replace(tzinfo=UTC)

    # Get weekday (0=Sunday)
    weekday = (date.weekday() + 1) % 7

    # Calculate day duration
    day_duration = sunset - sunrise
    day_minutes = day_duration.total_seconds() / 60

    # Calculate night duration (to next sunrise)
    next_sunrise = sunrise + timedelta(days=1)
    night_duration = next_sunrise - sunset
    night_minutes = night_duration.total_seconds() / 60

    # Calculate inauspicious periods
    rahu_kaal = calculate_inauspicious_period(
        sunrise, sunset, weekday, RAHU_KAAL_PARTS, "Rahu Kaal"
    )

    yamaganda = calculate_inauspicious_period(
        sunrise, sunset, weekday, YAMAGANDA_PARTS, "Yamaganda"
    )

    gulika = calculate_inauspicious_period(
        sunrise, sunset, weekday, GULIKA_PARTS, "Gulika"
    )

    # Calculate Abhijit Muhurta (midday - most auspicious)
    abhijit = calculate_abhijit_muhurta(sunrise, sunset, weekday)

    # Calculate Brahma Muhurta (pre-dawn - spiritual)
    brahma = calculate_brahma_muhurta(sunrise)

    # Calculate Hora windows
    hora_windows = calculate_hora_windows(sunrise, sunset, next_sunrise, weekday)

    # Calculate Choghadiya windows
    choghadiya_windows = calculate_choghadiya(sunrise, sunset, next_sunrise)

    # Calculate quality summary
    quality_summary = {
        "avoid": 3,  # Rahu Kaal, Yamaganda, Gulika
        "neutral": sum(1 for h in hora_windows if h.quality == "neutral"),
        "good": sum(1 for h in hora_windows if h.quality == "good"),
        "excellent": 2 if abhijit else 1,  # Brahma Muhurta + optional Abhijit
    }

    # Add choghadiya to summary
    for c in choghadiya_windows:
        quality_summary[c.quality] = quality_summary.get(c.quality, 0) + 1

    # Create DailyWindows object
    daily_windows = DailyWindows(
        rahu_kaal=rahu_kaal,
        yamaganda=yamaganda,
        gulika=gulika,
        abhijit_muhurta=abhijit,
        brahma_muhurta=brahma,
        hora_windows=hora_windows,
        choghadiya_windows=choghadiya_windows,
        quality_summary=quality_summary,
    )

    return {"daily_windows": daily_windows.to_dict()}


def calculate_inauspicious_period(
    sunrise: datetime,
    sunset: datetime,
    weekday: int,
    parts_dict: dict[int, int],
    name: str,
) -> TimeWindow:
    """Calculate an inauspicious period (Rahu Kaal, etc.).

    Args:
        sunrise: Sunrise time
        sunset: Sunset time
        weekday: Day of week (0=Sunday)
        parts_dict: Dictionary mapping weekday to part number
        name: Name of the period

    Returns:
        TimeWindow for the inauspicious period
    """
    # Get which part of the day
    part_num = parts_dict[weekday]

    # Divide day into 8 equal parts
    day_duration = sunset - sunrise
    part_duration = day_duration / 8

    # Calculate start and end
    start_time = sunrise + part_duration * (part_num - 1)
    end_time = start_time + part_duration

    # Determine description
    descriptions = {
        "Rahu Kaal": "Avoid new ventures and important decisions",
        "Yamaganda": "Inauspicious for travel and meetings",
        "Gulika": "Avoid financial transactions",
    }

    return TimeWindow(
        name=name,
        start_time=start_time,
        end_time=end_time,
        quality="avoid",
        planet_lord="Rahu" if "Rahu" in name else "Saturn",
        description=descriptions.get(name, "Inauspicious period"),
    )


def calculate_abhijit_muhurta(
    sunrise: datetime, sunset: datetime, weekday: int
) -> TimeWindow | None:
    """Calculate Abhijit Muhurta (victory moment).

    Args:
        sunrise: Sunrise time
        sunset: Sunset time
        weekday: Day of week

    Returns:
        TimeWindow for Abhijit Muhurta, None on Wednesday
    """
    # No Abhijit Muhurta on Wednesday
    if weekday == 3:
        return None

    # Calculate local noon
    day_duration = sunset - sunrise
    local_noon = sunrise + day_duration / 2

    # Abhijit Muhurta is 48 minutes (24 minutes before and after noon)
    start_time = local_noon - timedelta(minutes=24)
    end_time = local_noon + timedelta(minutes=24)

    return TimeWindow(
        name="Abhijit Muhurta",
        start_time=start_time,
        end_time=end_time,
        quality="excellent",
        planet_lord="Sun",
        description="Most auspicious time for success and victory",
    )


def calculate_brahma_muhurta(sunrise: datetime) -> TimeWindow:
    """Calculate Brahma Muhurta (pre-dawn spiritual time).

    Args:
        sunrise: Sunrise time

    Returns:
        TimeWindow for Brahma Muhurta
    """
    # Brahma Muhurta is 1 hour 36 minutes before sunrise
    # (2 muhurtas of 48 minutes each)
    start_time = sunrise - timedelta(minutes=96)
    end_time = sunrise - timedelta(minutes=48)

    return TimeWindow(
        name="Brahma Muhurta",
        start_time=start_time,
        end_time=end_time,
        quality="excellent",
        planet_lord="Brahma",
        description="Best time for spiritual practices and meditation",
    )


def calculate_hora_windows(
    sunrise: datetime, sunset: datetime, next_sunrise: datetime, weekday: int
) -> list[TimeWindow]:
    """Calculate planetary hour (Hora) windows.

    Args:
        sunrise: Today's sunrise
        sunset: Today's sunset
        next_sunrise: Tomorrow's sunrise
        weekday: Day of week

    Returns:
        List of 24 hora windows
    """
    hora_windows = []

    # Day horas (sunrise to sunset) - 12 hours
    day_duration = sunset - sunrise
    day_hora_duration = day_duration / 12

    day_sequence = HORA_SEQUENCE[weekday]

    for i in range(12):
        planet = day_sequence[i % 7]
        start_time = sunrise + day_hora_duration * i
        end_time = start_time + day_hora_duration

        hora_windows.append(
            TimeWindow(
                name=f"{planet} Hora (Day)",
                start_time=start_time,
                end_time=end_time,
                quality=HORA_QUALITY[planet],
                planet_lord=planet,
                description=f"Planetary hour ruled by {planet}",
            )
        )

    # Night horas (sunset to next sunrise) - 12 hours
    night_duration = next_sunrise - sunset
    night_hora_duration = night_duration / 12

    # Continue sequence from where day left off
    night_sequence = day_sequence[5:] + day_sequence[:5]  # Rotate by 5

    for i in range(12):
        planet = night_sequence[i % 7]
        start_time = sunset + night_hora_duration * i
        end_time = start_time + night_hora_duration

        hora_windows.append(
            TimeWindow(
                name=f"{planet} Hora (Night)",
                start_time=start_time,
                end_time=end_time,
                quality=HORA_QUALITY[planet],
                planet_lord=planet,
                description=f"Planetary hour ruled by {planet}",
            )
        )

    return hora_windows


def calculate_choghadiya(
    sunrise: datetime, sunset: datetime, next_sunrise: datetime
) -> list[TimeWindow]:
    """Calculate Choghadiya periods (8 day + 8 night).

    Args:
        sunrise: Today's sunrise
        sunset: Today's sunset
        next_sunrise: Tomorrow's sunrise

    Returns:
        List of 16 choghadiya windows
    """
    choghadiya_windows = []

    # Day Choghadiyas (sunrise to sunset)
    day_duration = sunset - sunrise
    day_choghadiya_duration = day_duration / 8

    for i, (name, quality) in enumerate(CHOGHADIYA_DAY):
        start_time = sunrise + day_choghadiya_duration * i
        end_time = start_time + day_choghadiya_duration

        choghadiya_windows.append(
            TimeWindow(
                name=f"{name} Choghadiya (Day)",
                start_time=start_time,
                end_time=end_time,
                quality=quality,
                description=get_choghadiya_description(name, quality),
            )
        )

    # Night Choghadiyas (sunset to next sunrise)
    night_duration = next_sunrise - sunset
    night_choghadiya_duration = night_duration / 8

    for i, (name, quality) in enumerate(CHOGHADIYA_NIGHT):
        start_time = sunset + night_choghadiya_duration * i
        end_time = start_time + night_choghadiya_duration

        choghadiya_windows.append(
            TimeWindow(
                name=f"{name} Choghadiya (Night)",
                start_time=start_time,
                end_time=end_time,
                quality=quality,
                description=get_choghadiya_description(name, quality),
            )
        )

    return choghadiya_windows


def get_choghadiya_description(name: str, quality: str) -> str:
    """Get description for a Choghadiya period.

    Args:
        name: Choghadiya name
        quality: Quality rating

    Returns:
        Description string
    """
    descriptions = {
        "Amrit": "Highly auspicious for all activities",
        "Shubh": "Good for general activities",
        "Labh": "Excellent for business and gains",
        "Char": "Good for travel and movement",
        "Udveg": "Neutral - routine work only",
        "Kaal": "Avoid important activities",
        "Rog": "Inauspicious - avoid if possible",
    }

    return descriptions.get(name, f"{quality.capitalize()} period")


@require_feature("daily_windows")
def find_best_windows(
    daily_windows_data: dict,
    duration_minutes: int = 30,
    quality_threshold: str = "good",
) -> list[TimeWindow]:
    """Find best time windows for activities.

    Args:
        daily_windows_data: Daily windows calculation results
        duration_minutes: Required duration
        quality_threshold: Minimum quality required

    Returns:
        List of suitable time windows
    """
    if "daily_windows" not in daily_windows_data:
        return []

    dw = daily_windows_data["daily_windows"]
    suitable_windows = []

    # Define quality hierarchy
    quality_levels = {"excellent": 4, "good": 3, "neutral": 2, "avoid": 1}

    min_quality = quality_levels.get(quality_threshold, 3)

    # Check Abhijit Muhurta first (if available)
    if dw.get("abhijit_muhurta"):
        abhijit = dw["abhijit_muhurta"]
        if quality_levels.get("excellent", 0) >= min_quality:
            suitable_windows.append(
                TimeWindow(
                    name="Abhijit Muhurta",
                    start_time=datetime.fromisoformat(abhijit["start"]),
                    end_time=datetime.fromisoformat(abhijit["end"]),
                    quality="excellent",
                    description=abhijit.get("description"),
                )
            )

    # Check Hora windows
    for hora in dw.get("hora_windows", []):
        if quality_levels.get(hora["quality"], 0) >= min_quality:
            if hora["duration_minutes"] >= duration_minutes:
                suitable_windows.append(
                    TimeWindow(
                        name=hora["name"],
                        start_time=datetime.fromisoformat(hora["start"]),
                        end_time=datetime.fromisoformat(hora["end"]),
                        quality=hora["quality"],
                        planet_lord=hora.get("planet_lord"),
                        description=hora.get("description"),
                    )
                )

    # Check Choghadiya windows
    for chogha in dw.get("choghadiya_windows", []):
        if quality_levels.get(chogha["quality"], 0) >= min_quality:
            if chogha["duration_minutes"] >= duration_minutes:
                # Avoid if overlaps with Rahu Kaal etc
                start = datetime.fromisoformat(chogha["start"])
                end = datetime.fromisoformat(chogha["end"])

                # Check for overlap with inauspicious periods
                rahu = dw["rahu_kaal"]
                if not is_overlapping(
                    start,
                    end,
                    datetime.fromisoformat(rahu["start"]),
                    datetime.fromisoformat(rahu["end"]),
                ):
                    suitable_windows.append(
                        TimeWindow(
                            name=chogha["name"],
                            start_time=start,
                            end_time=end,
                            quality=chogha["quality"],
                            description=chogha.get("description"),
                        )
                    )

    # Sort by quality and start time
    suitable_windows.sort(key=lambda x: (-quality_levels[x.quality], x.start_time))

    return suitable_windows[:10]  # Return top 10 windows


def is_overlapping(
    start1: datetime, end1: datetime, start2: datetime, end2: datetime
) -> bool:
    """Check if two time periods overlap.

    Args:
        start1, end1: First period
        start2, end2: Second period

    Returns:
        True if periods overlap
    """
    return not (end1 <= start2 or end2 <= start1)
