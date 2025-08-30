#!/usr/bin/env python3
"""
Fortuna Points Module (Sahams/Arabic Parts)
Calculates sensitive points based on planetary and house positions
Used in KP for fine-timing and additional signification layers
"""


from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .constants import PLANET_NAMES


class FortunaType(Enum):
    """Common Arabic Parts/Sahams used in KP"""

    FORTUNE = ("Part of Fortune", "ASC + Moon - Sun", "Wealth and success")
    SPIRIT = ("Part of Spirit", "ASC + Sun - Moon", "Character and vitality")
    LOVE = ("Part of Love", "ASC + Venus - Sun", "Romance and relationships")
    MARRIAGE = ("Part of Marriage", "ASC + DESC - Venus", "Marriage timing")
    CAREER = ("Part of Career", "ASC + MC - Sun", "Professional success")
    WEALTH = ("Part of Wealth", "ASC + 2nd - 2nd_Lord", "Financial gains")
    SPECULATION = ("Part of Speculation", "ASC + 5th - Mercury", "Gambling/trading")
    DISEASE = ("Part of Disease", "ASC + Mars - Saturn", "Health concerns")
    DEATH = ("Part of Death", "ASC + 8th - Moon", "Transformation")
    TRAVEL = ("Part of Travel", "ASC + 9th - 9th_Lord", "Foreign journeys")
    FATHER = ("Part of Father", "ASC + Sun - Saturn", "Father's wellbeing")
    MOTHER = ("Part of Mother", "ASC + Moon - Venus", "Mother's wellbeing")
    CHILDREN = ("Part of Children", "ASC + Jupiter - Moon", "Progeny matters")
    FRIENDS = ("Part of Friends", "ASC + Moon - Mercury", "Friendships")
    ENEMIES = ("Part of Enemies", "ASC + 12th - 6th_Lord", "Hidden enemies")

    def __init__(self, display_name: str, formula: str, signification: str):
        self.display_name = display_name
        self.formula = formula
        self.signification = signification


@dataclass
class FortunaPoint:
    """Single fortuna point calculation"""

    type: FortunaType
    longitude: float  # Position in degrees
    sign: int  # Zodiac sign (1-12)
    house: int  # House position
    nakshatra: int  # Nakshatra (1-27)
    sub_lord: int  # KP sub-lord

    # Movement data
    daily_motion: float  # Degrees per day
    is_retrograde: bool  # If components cause retrograde motion

    # Strength factors
    strength: float  # Overall strength (0-100)
    is_afflicted: bool  # If conjunct/aspected by malefics

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "name": self.type.display_name,
            "formula": self.type.formula,
            "signification": self.type.signification,
            "position": {
                "longitude": round(self.longitude, 4),
                "sign": self.sign,
                "house": self.house,
                "nakshatra": self.nakshatra,
                "sub_lord": PLANET_NAMES.get(self.sub_lord, str(self.sub_lord)),
            },
            "movement": {
                "daily_motion": round(self.daily_motion, 4),
                "retrograde": self.is_retrograde,
            },
            "strength": round(self.strength, 2),
            "afflicted": self.is_afflicted,
        }


@dataclass
class FortunaAnalysis:
    """Complete fortuna points analysis"""

    timestamp: datetime
    # Primary fortuna points
    part_of_fortune: FortunaPoint
    part_of_spirit: FortunaPoint | None

    # All calculated points
    all_points: dict[str, FortunaPoint]

    # House-wise fortuna points
    points_by_house: dict[int, list[str]]

    # Activated points (by transit/dasha)
    activated_points: list[str]

    # Intraday movement tracking
    hourly_positions: dict[str, list[tuple[datetime, float]]] | None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "part_of_fortune": self.part_of_fortune.to_dict(),
            "part_of_spirit": (
                self.part_of_spirit.to_dict() if self.part_of_spirit else None
            ),
            "all_points": {
                name: point.to_dict() for name, point in self.all_points.items()
            },
            "houses": {house: points for house, points in self.points_by_house.items()},
            "activated": self.activated_points,
            "tracking": {"hourly_data": bool(self.hourly_positions)},
        }


def calculate_part_of_fortune(
    asc_longitude: float,
    sun_longitude: float,
    moon_longitude: float,
    is_day_birth: bool = True,
) -> float:
    """
    Calculate Part of Fortune (Pars Fortunae).

    Day formula: ASC + Moon - Sun
    Night formula: ASC + Sun - Moon

    Args:
        asc_longitude: Ascendant longitude
        sun_longitude: Sun's longitude
        moon_longitude: Moon's longitude
        is_day_birth: Whether Sun is above horizon

    Returns:
        Part of Fortune longitude in degrees
    """
    if is_day_birth:
        # Day formula: ASC + Moon - Sun
        fortune = asc_longitude + moon_longitude - sun_longitude
    else:
        # Night formula: ASC + Sun - Moon (reverses the luminaries)
        fortune = asc_longitude + sun_longitude - moon_longitude

    # Normalize to 0-360
    fortune = fortune % 360

    return fortune


def calculate_arabic_part(
    formula_parts: list[tuple[str, float, bool]],
) -> float:
    """
    Calculate any Arabic Part based on formula.

    Formula parts are tuples of (component_name, longitude, is_additive)
    Example: [("ASC", 120.5, True), ("Moon", 45.3, True), ("Sun", 23.7, False)]

    Args:
        formula_parts: List of formula components

    Returns:
        Calculated longitude in degrees
    """
    result = 0.0

    for name, longitude, is_additive in formula_parts:
        if is_additive:
            result += longitude
        else:
            result -= longitude

    # Normalize to 0-360
    result = result % 360

    return result


def calculate_fortuna_point(
    fortuna_type: FortunaType,
    planet_positions: dict[int, float],
    house_cusps: list[float],
    house_lords: dict[int, int] | None = None,
    is_day_birth: bool | None = None,
) -> FortunaPoint:
    """
    Calculate a specific fortuna point.

    Args:
        fortuna_type: Type of fortuna point
        planet_positions: Planet ID -> longitude mapping
        house_cusps: List of 12 house cusps
        house_lords: Optional house -> lord planet mapping
        is_day_birth: Whether it's a day birth (Sun above horizon)

    Returns:
        FortunaPoint object
    """
    asc = house_cusps[0]
    mc = house_cusps[9] if len(house_cusps) > 9 else asc + 270
    desc = (asc + 180) % 360

    # Determine if day birth (Sun above horizon) if not provided
    if is_day_birth is None:
        sun_longitude = planet_positions.get(1, 0)
        # Sun is above horizon if between ASC and DESC (7th house cusp)
        is_day_birth = _is_above_horizon(sun_longitude, asc)

    # Calculate based on type
    if fortuna_type == FortunaType.FORTUNE:
        longitude = calculate_part_of_fortune(
            asc,
            planet_positions.get(1, 0),  # Sun
            planet_positions.get(2, 0),  # Moon
            is_day_birth,
        )

    elif fortuna_type == FortunaType.SPIRIT:
        # Part of Spirit reverses the Part of Fortune formula
        if is_day_birth:
            # Day: ASC + Sun - Moon
            longitude = calculate_arabic_part(
                [
                    ("ASC", asc, True),
                    ("Sun", planet_positions.get(1, 0), True),
                    ("Moon", planet_positions.get(2, 0), False),
                ]
            )
        else:
            # Night: ASC + Moon - Sun
            longitude = calculate_arabic_part(
                [
                    ("ASC", asc, True),
                    ("Moon", planet_positions.get(2, 0), True),
                    ("Sun", planet_positions.get(1, 0), False),
                ]
            )

    elif fortuna_type == FortunaType.LOVE:
        longitude = calculate_arabic_part(
            [
                ("ASC", asc, True),
                ("Venus", planet_positions.get(6, 0), True),
                ("Sun", planet_positions.get(1, 0), False),
            ]
        )

    elif fortuna_type == FortunaType.MARRIAGE:
        longitude = calculate_arabic_part(
            [
                ("ASC", asc, True),
                ("DESC", desc, True),
                ("Venus", planet_positions.get(6, 0), False),
            ]
        )

    elif fortuna_type == FortunaType.CAREER:
        longitude = calculate_arabic_part(
            [
                ("ASC", asc, True),
                ("MC", mc, True),
                ("Sun", planet_positions.get(1, 0), False),
            ]
        )

    elif fortuna_type == FortunaType.WEALTH:
        # Need 2nd house cusp and its lord
        second_cusp = house_cusps[1] if len(house_cusps) > 1 else asc + 30
        second_lord_id = house_lords.get(2, 6) if house_lords else 6  # Venus default
        longitude = calculate_arabic_part(
            [
                ("ASC", asc, True),
                ("2nd", second_cusp, True),
                ("2nd_Lord", planet_positions.get(second_lord_id, 0), False),
            ]
        )

    elif fortuna_type == FortunaType.SPECULATION:
        fifth_cusp = house_cusps[4] if len(house_cusps) > 4 else asc + 120
        longitude = calculate_arabic_part(
            [
                ("ASC", asc, True),
                ("5th", fifth_cusp, True),
                ("Mercury", planet_positions.get(5, 0), False),
            ]
        )

    elif fortuna_type == FortunaType.DISEASE:
        longitude = calculate_arabic_part(
            [
                ("ASC", asc, True),
                ("Mars", planet_positions.get(9, 0), True),
                ("Saturn", planet_positions.get(8, 0), False),
            ]
        )

    elif fortuna_type == FortunaType.CHILDREN:
        longitude = calculate_arabic_part(
            [
                ("ASC", asc, True),
                ("Jupiter", planet_positions.get(3, 0), True),
                ("Moon", planet_positions.get(2, 0), False),
            ]
        )

    else:
        # Default to Part of Fortune
        longitude = calculate_part_of_fortune(
            asc, planet_positions.get(1, 0), planet_positions.get(2, 0)
        )

    # Calculate derived values
    sign = int(longitude / 30) + 1
    house = _get_house_position(longitude, house_cusps)
    nakshatra = int((longitude % 360) * 27 / 360) + 1
    sub_lord = _get_kp_sublord(longitude)

    # Calculate daily motion (simplified - based on Moon's motion)
    moon_speed = 13.176  # Average Moon speed
    daily_motion = moon_speed  # Simplified for now

    # Calculate strength (simplified)
    strength = _calculate_fortuna_strength(longitude, planet_positions, house)

    return FortunaPoint(
        type=fortuna_type,
        longitude=longitude,
        sign=sign,
        house=house,
        nakshatra=nakshatra,
        sub_lord=sub_lord,
        daily_motion=daily_motion,
        is_retrograde=False,  # Fortuna points don't retrograde
        strength=strength,
        is_afflicted=_check_affliction(longitude, planet_positions),
    )


def calculate_all_fortuna_points(
    planet_positions: dict[int, float],
    house_cusps: list[float],
    house_lords: dict[int, int] | None = None,
    include_minor: bool = False,
    is_day_birth: bool | None = None,
) -> dict[str, FortunaPoint]:
    """
    Calculate all major fortuna points.

    Args:
        planet_positions: Planet positions
        house_cusps: House cusps
        house_lords: House lordships
        include_minor: Include minor/specialized points

    Returns:
        Dictionary of fortuna points
    """
    points = {}

    # Major points always calculated
    major_types = [
        FortunaType.FORTUNE,
        FortunaType.SPIRIT,
        FortunaType.LOVE,
        FortunaType.MARRIAGE,
        FortunaType.CAREER,
        FortunaType.WEALTH,
    ]

    # Additional points if requested
    if include_minor:
        major_types.extend(
            [
                FortunaType.SPECULATION,
                FortunaType.DISEASE,
                FortunaType.CHILDREN,
                FortunaType.TRAVEL,
            ]
        )

    for fortuna_type in major_types:
        try:
            point = calculate_fortuna_point(
                fortuna_type, planet_positions, house_cusps, house_lords, is_day_birth
            )
            points[fortuna_type.name] = point
        except Exception:
            # Skip if calculation fails
            continue

    return points


def track_fortuna_movement(
    fortuna_type: FortunaType,
    start_time: datetime,
    end_time: datetime,
    interval_hours: int = 1,
    planet_positions_func=None,
) -> list[tuple[datetime, float, int]]:
    """
    Track fortuna point movement through the day.

    Args:
        fortuna_type: Which fortuna to track
        start_time: Start of tracking period
        end_time: End of tracking period
        interval_hours: Hours between calculations
        planet_positions_func: Function to get planet positions at time

    Returns:
        List of (timestamp, longitude, house) tuples
    """
    movements = []
    current_time = start_time

    while current_time <= end_time:
        # Get positions at this time
        # In real implementation, would call planet_positions_func
        # For now, using approximation

        hours_elapsed = (current_time - start_time).total_seconds() / 3600

        # Approximate movement based on Moon (main driver of fortune)
        moon_movement = hours_elapsed * 0.549  # ~13.176° per day

        # Mock calculation
        base_longitude = 120.0  # Would calculate actual
        longitude = (base_longitude + moon_movement) % 360
        house = int(longitude / 30) + 1

        movements.append((current_time, longitude, house))

        current_time += timedelta(hours=interval_hours)

    return movements


def find_fortuna_house_transits(
    fortuna_longitude: float,
    daily_motion: float,
    house_cusps: list[float],
    hours_ahead: int = 24,
) -> list[dict]:
    """
    Find when fortuna point will transit house cusps.

    Args:
        fortuna_longitude: Current position
        daily_motion: Daily motion in degrees
        house_cusps: House cusp positions
        hours_ahead: How many hours to look ahead

    Returns:
        List of transit events
    """
    transits = []
    hourly_motion = daily_motion / 24

    for hour in range(hours_ahead):
        future_position = (fortuna_longitude + hour * hourly_motion) % 360

        # Check if crosses any cusp
        for i, cusp in enumerate(house_cusps):
            # Check if position will cross this cusp
            current_distance = _angular_distance(fortuna_longitude, cusp)
            future_distance = _angular_distance(future_position, cusp)

            if current_distance > 1 and future_distance < 1:
                # Will cross this cusp
                transits.append(
                    {
                        "house": i + 1,
                        "cusp_degree": cusp,
                        "hours_until": hour,
                        "type": "ingress",
                    }
                )

    return transits


def analyze_fortuna_aspects(
    fortuna_longitude: float, planet_positions: dict[int, float], orb: float = 5.0
) -> list[dict]:
    """
    Find aspects between fortuna point and planets.

    Args:
        fortuna_longitude: Fortuna position
        planet_positions: Planet positions
        orb: Aspect orb in degrees

    Returns:
        List of aspects
    """
    aspects = []
    aspect_angles = {
        "conjunction": 0,
        "sextile": 60,
        "square": 90,
        "trine": 120,
        "opposition": 180,
    }

    for planet_id, planet_long in planet_positions.items():
        for aspect_name, angle in aspect_angles.items():
            separation = abs(_angular_distance(fortuna_longitude, planet_long))

            if abs(separation - angle) <= orb:
                aspects.append(
                    {
                        "planet": PLANET_NAMES.get(planet_id, str(planet_id)),
                        "aspect": aspect_name,
                        "angle": angle,
                        "orb": abs(separation - angle),
                        "applying": _is_applying(
                            fortuna_longitude, planet_long, 13.176
                        ),
                    }
                )

    return aspects


def get_complete_fortuna_analysis(
    timestamp: datetime,
    planet_positions: dict[int, float],
    house_cusps: list[float],
    house_lords: dict[int, int] | None = None,
    track_movement: bool = False,
) -> FortunaAnalysis:
    """
    Perform complete fortuna points analysis.

    Args:
        timestamp: Time of analysis
        planet_positions: Planet positions
        house_cusps: House cusps
        house_lords: House lordships
        track_movement: Whether to track intraday movement

    Returns:
        FortunaAnalysis object
    """
    # Determine if it's a day or night birth
    sun_longitude = planet_positions.get(1, 0)
    asc_longitude = house_cusps[0]
    is_day_birth = _is_above_horizon(sun_longitude, asc_longitude)

    # Calculate Part of Fortune (always)
    part_of_fortune = calculate_fortuna_point(
        FortunaType.FORTUNE, planet_positions, house_cusps, house_lords, is_day_birth
    )

    # Calculate Part of Spirit
    part_of_spirit = calculate_fortuna_point(
        FortunaType.SPIRIT, planet_positions, house_cusps, house_lords, is_day_birth
    )

    # Calculate all points
    all_points = calculate_all_fortuna_points(
        planet_positions,
        house_cusps,
        house_lords,
        include_minor=True,
        is_day_birth=is_day_birth,
    )

    # Organize by house
    points_by_house = {}
    for name, point in all_points.items():
        house = point.house
        if house not in points_by_house:
            points_by_house[house] = []
        points_by_house[house].append(name)

    # Find activated points (simplified - would check transits/dasha)
    activated_points = []
    for name, point in all_points.items():
        # Check if in angular houses (considered activated)
        if point.house in [1, 4, 7, 10]:
            activated_points.append(name)

    # Track hourly movement if requested
    hourly_positions = None
    if track_movement:
        hourly_positions = {}
        for name, point in list(all_points.items())[:3]:  # Track top 3
            movements = track_fortuna_movement(
                point.type, timestamp, timestamp + timedelta(hours=24), 1
            )
            hourly_positions[name] = movements

    return FortunaAnalysis(
        timestamp=timestamp,
        part_of_fortune=part_of_fortune,
        part_of_spirit=part_of_spirit,
        all_points=all_points,
        points_by_house=points_by_house,
        activated_points=activated_points,
        hourly_positions=hourly_positions,
    )


# Helper functions


def _is_above_horizon(sun_longitude: float, asc_longitude: float) -> bool:
    """
    Determine if Sun is above horizon (day birth).

    Sun is above horizon if it's in houses 7-12 (from DESC to ASC).

    Args:
        sun_longitude: Sun's longitude in degrees
        asc_longitude: Ascendant longitude in degrees

    Returns:
        True if day birth, False if night birth
    """
    desc_longitude = (asc_longitude + 180) % 360

    # Calculate angular distance from ASC
    sun_from_asc = (sun_longitude - asc_longitude) % 360

    # Sun is above horizon if between 180-360 degrees from ASC
    # (i.e., in houses 7, 8, 9, 10, 11, 12)
    return 180 <= sun_from_asc < 360


def _get_house_position(longitude: float, cusps: list[float]) -> int:
    """Get house position for a longitude"""
    for i in range(12):
        cusp1 = cusps[i]
        cusp2 = cusps[(i + 1) % 12] if i < 11 else cusps[0]

        if cusp1 > cusp2:  # Crosses 0°
            if longitude >= cusp1 or longitude < cusp2:
                return i + 1
        else:
            if cusp1 <= longitude < cusp2:
                return i + 1
    return 1


def _get_kp_sublord(longitude: float) -> int:
    """Get KP sub-lord for a longitude (simplified)"""
    # This would use actual KP calculation
    # For now, using nakshatra lord as approximation
    nakshatra = int((longitude % 360) * 27 / 360) + 1

    nakshatra_lords = {
        1: 7,
        2: 6,
        3: 1,
        4: 2,
        5: 9,
        6: 4,
        7: 3,
        8: 8,
        9: 5,
        10: 7,
        11: 6,
        12: 1,
        13: 2,
        14: 9,
        15: 4,
        16: 3,
        17: 8,
        18: 5,
        19: 7,
        20: 6,
        21: 1,
        22: 2,
        23: 9,
        24: 4,
        25: 3,
        26: 8,
        27: 5,
    }

    return nakshatra_lords.get(nakshatra, 1)


def _calculate_fortuna_strength(
    longitude: float, planet_positions: dict[int, float], house: int
) -> float:
    """Calculate strength of fortuna point"""
    strength = 50.0

    # Angular houses are stronger
    if house in [1, 4, 7, 10]:
        strength += 20
    elif house in [5, 9]:  # Trines
        strength += 15
    elif house in [6, 8, 12]:  # Dusthanas
        strength -= 10

    # Check for benefic aspects (simplified)
    for planet_id in [3, 5, 6]:  # Jupiter, Mercury, Venus
        if planet_id in planet_positions:
            distance = abs(_angular_distance(longitude, planet_positions[planet_id]))
            if distance < 10:  # Conjunction
                strength += 10
            elif 115 < distance < 125:  # Trine
                strength += 5

    return min(100, max(0, strength))


def _check_affliction(longitude: float, planet_positions: dict[int, float]) -> bool:
    """Check if fortuna point is afflicted"""
    # Check for malefic aspects
    for planet_id in [4, 7, 8, 9]:  # Rahu, Ketu, Saturn, Mars
        if planet_id in planet_positions:
            distance = abs(_angular_distance(longitude, planet_positions[planet_id]))
            if distance < 10 or 85 < distance < 95 or 175 < distance < 185:
                return True
    return False


def _angular_distance(long1: float, long2: float) -> float:
    """Calculate angular distance between two longitudes"""
    diff = long2 - long1
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
    return diff


def _is_applying(long1: float, long2: float, speed1: float) -> bool:
    """Check if aspect is applying or separating"""
    distance = _angular_distance(long1, long2)
    return (distance > 0 and speed1 > 0) or (distance < 0 and speed1 < 0)
