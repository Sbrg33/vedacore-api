#!/usr/bin/env python3
"""
Real-time Sky Map Module
Complete snapshot of planetary positions, aspects, and KP significators at any moment
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .constants import NAKSHATRA_NAMES, PLANET_NAMES
from .facade import get_positions
from .houses import compute_houses
from .transit_aspects import find_aspect_patterns, find_transit_aspects


@dataclass
class PlanetSnapshot:
    """Complete data for a planet at a moment"""

    planet_id: int
    name: str
    longitude: float
    latitude: float
    speed: float
    retrograde: bool

    # Position details
    sign: int
    sign_name: str
    degree_in_sign: float
    nakshatra: int
    nakshatra_name: str
    pada: int

    # KP lords
    sign_lord: int
    star_lord: int
    sub_lord: int
    sub_sub_lord: int

    # House position
    house: int | None = None

    # Significator summary
    signifies_houses: list[int] = field(default_factory=list)
    primary_significator_for: list[int] = field(default_factory=list)

    # Strength indicators
    is_combust: bool = False
    is_exalted: bool = False
    is_debilitated: bool = False
    is_own_sign: bool = False

    def to_dict(self) -> dict:
        """Convert to API response format"""
        return {
            "id": self.planet_id,
            "name": self.name,
            "position": {
                "longitude": round(self.longitude, 4),
                "latitude": round(self.latitude, 4),
                "speed": round(self.speed, 4),
                "retrograde": self.retrograde,
            },
            "zodiac": {
                "sign": self.sign,
                "sign_name": self.sign_name,
                "degree": round(self.degree_in_sign, 2),
            },
            "nakshatra": {
                "id": self.nakshatra,
                "name": self.nakshatra_name,
                "pada": self.pada,
            },
            "kp_lords": {
                "sign_lord": PLANET_NAMES.get(self.sign_lord),
                "star_lord": PLANET_NAMES.get(self.star_lord),
                "sub_lord": PLANET_NAMES.get(self.sub_lord),
                "sub_sub_lord": PLANET_NAMES.get(self.sub_sub_lord),
            },
            "house": self.house,
            "significations": {
                "houses": self.signifies_houses,
                "primary_for": self.primary_significator_for,
            },
            "dignity": {
                "combust": self.is_combust,
                "exalted": self.is_exalted,
                "debilitated": self.is_debilitated,
                "own_sign": self.is_own_sign,
            },
        }


@dataclass
class HouseSnapshot:
    """House data at a moment"""

    house_num: int
    cusp_degree: float
    sign: int
    sign_name: str

    # KP cuspal lords
    sign_lord: int
    star_lord: int
    sub_lord: int

    # Occupants
    occupant_planets: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "house": self.house_num,
            "cusp": round(self.cusp_degree, 2),
            "sign": self.sign,
            "sign_name": self.sign_name,
            "lords": {
                "sign": PLANET_NAMES.get(self.sign_lord),
                "star": PLANET_NAMES.get(self.star_lord),
                "sub": PLANET_NAMES.get(self.sub_lord),
            },
            "occupants": [PLANET_NAMES.get(p) for p in self.occupant_planets],
        }


@dataclass
class SkyMap:
    """Complete sky map at a moment"""

    timestamp: datetime
    latitude: float
    longitude: float

    # Planetary data
    planets: dict[int, PlanetSnapshot]

    # House data
    houses: list[HouseSnapshot]
    ascendant: float
    midheaven: float

    # Active aspects
    aspects: list[dict]
    aspect_patterns: list[dict]

    # KP Ruling Planets
    ruling_planets: dict[str, int]

    # Active significators (planets currently activating houses)
    active_significators: dict[int, list[int]]  # house -> planets

    # Quick reference
    retrograde_planets: list[int]
    fast_moving_planets: list[int]  # Moving faster than average
    slow_moving_planets: list[int]  # Moving slower than average

    def to_dict(self) -> dict:
        """Convert to comprehensive API response"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "location": {"latitude": self.latitude, "longitude": self.longitude},
            "angles": {
                "ascendant": round(self.ascendant, 2),
                "midheaven": round(self.midheaven, 2),
                "descendant": round((self.ascendant + 180) % 360, 2),
                "ic": round((self.midheaven + 180) % 360, 2),
            },
            "planets": {pid: p.to_dict() for pid, p in self.planets.items()},
            "houses": [h.to_dict() for h in self.houses],
            "aspects": {
                "active": self.aspects,
                "patterns": self.aspect_patterns,
                "count": len(self.aspects),
            },
            "ruling_planets": self.ruling_planets,
            "active_significators": {
                h: [PLANET_NAMES.get(p) for p in planets]
                for h, planets in self.active_significators.items()
            },
            "status": {
                "retrograde": [PLANET_NAMES.get(p) for p in self.retrograde_planets],
                "fast_moving": [PLANET_NAMES.get(p) for p in self.fast_moving_planets],
                "slow_moving": [PLANET_NAMES.get(p) for p in self.slow_moving_planets],
            },
        }


SIGN_NAMES = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]

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

# Planet average speeds (degrees per day)
AVERAGE_SPEEDS = {
    1: 0.985,  # Sun
    2: 13.176,  # Moon
    3: 0.524,  # Jupiter
    4: 4.092,  # Rahu (retrograde)
    5: 1.383,  # Mercury
    6: 1.229,  # Venus
    7: 4.092,  # Ketu (retrograde)
    8: 0.033,  # Saturn
    9: 0.686,  # Mars
}


def check_combustion(sun_long: float, planet_long: float, planet_id: int) -> bool:
    """
    Check if planet is combust (too close to Sun).

    Args:
        sun_long: Sun's longitude
        planet_long: Planet's longitude
        planet_id: Planet ID to check

    Returns:
        True if combust
    """
    # Combustion orbs in degrees
    combustion_orbs = {
        2: 12.0,  # Moon
        3: 11.0,  # Jupiter
        5: 14.0,  # Mercury (17 when retrograde)
        6: 10.0,  # Venus (8 when retrograde)
        8: 15.0,  # Saturn
        9: 17.0,  # Mars
    }

    if planet_id not in combustion_orbs:
        return False

    distance = abs(sun_long - planet_long)
    if distance > 180:
        distance = 360 - distance

    return distance <= combustion_orbs[planet_id]


def check_dignity(planet_id: int, sign: int) -> tuple[bool, bool, bool]:
    """
    Check if planet is exalted, debilitated, or in own sign.

    Args:
        planet_id: Planet ID
        sign: Current sign (1-12)

    Returns:
        Tuple of (is_exalted, is_debilitated, is_own_sign)
    """
    exaltation_signs = {
        1: 1,  # Sun in Aries
        2: 2,  # Moon in Taurus
        3: 4,  # Jupiter in Cancer
        5: 6,  # Mercury in Virgo
        6: 12,  # Venus in Pisces
        8: 7,  # Saturn in Libra
        9: 10,  # Mars in Capricorn
    }

    debilitation_signs = {
        1: 7,  # Sun in Libra
        2: 8,  # Moon in Scorpio
        3: 10,  # Jupiter in Capricorn
        5: 12,  # Mercury in Pisces
        6: 6,  # Venus in Virgo
        8: 1,  # Saturn in Aries
        9: 4,  # Mars in Cancer
    }

    own_signs = {
        1: [5],  # Sun - Leo
        2: [4],  # Moon - Cancer
        3: [9, 12],  # Jupiter - Sagittarius, Pisces
        5: [3, 6],  # Mercury - Gemini, Virgo
        6: [2, 7],  # Venus - Taurus, Libra
        8: [10, 11],  # Saturn - Capricorn, Aquarius
        9: [1, 8],  # Mars - Aries, Scorpio
    }

    is_exalted = exaltation_signs.get(planet_id) == sign
    is_debilitated = debilitation_signs.get(planet_id) == sign
    is_own_sign = sign in own_signs.get(planet_id, [])

    return is_exalted, is_debilitated, is_own_sign


def get_planet_snapshot(
    planet_id: int, timestamp: datetime, house_cusps: list[float] | None = None
) -> PlanetSnapshot:
    """
    Get complete snapshot of a planet.

    Args:
        planet_id: Planet ID (1-9)
        timestamp: Time for calculation
        house_cusps: Optional house cusps for house position

    Returns:
        PlanetSnapshot object
    """
    # Get position from facade
    pos = get_positions(timestamp, planet_id, apply_kp_offset=False)

    # Sign calculations
    sign = int(pos.longitude / 30) + 1
    degree_in_sign = pos.longitude % 30

    # Check dignity
    is_exalted, is_debilitated, is_own_sign = check_dignity(planet_id, sign)

    # Check combustion (if not Sun itself)
    is_combust = False
    if planet_id != 1:
        sun_pos = get_positions(timestamp, 1, apply_kp_offset=False)
        is_combust = check_combustion(sun_pos.longitude, pos.longitude, planet_id)

    # House position if cusps provided
    house = None
    if house_cusps:
        for i in range(12):
            cusp1 = house_cusps[i]
            cusp2 = house_cusps[(i + 1) % 12] if i < 11 else house_cusps[0]

            if cusp1 > cusp2:  # Crosses 0°
                if pos.longitude >= cusp1 or pos.longitude < cusp2:
                    house = i + 1
                    break
            else:
                if cusp1 <= pos.longitude < cusp2:
                    house = i + 1
                    break

    return PlanetSnapshot(
        planet_id=planet_id,
        name=PLANET_NAMES.get(planet_id, f"Planet-{planet_id}"),
        longitude=pos.longitude,
        latitude=pos.latitude,
        speed=pos.speed,
        retrograde=pos.speed < 0,
        sign=sign,
        sign_name=SIGN_NAMES[sign - 1],
        degree_in_sign=degree_in_sign,
        nakshatra=pos.nakshatra,
        nakshatra_name=NAKSHATRA_NAMES.get(pos.nakshatra, f"Nakshatra-{pos.nakshatra}"),
        pada=pos.pada,
        sign_lord=SIGN_LORDS[sign],
        star_lord=pos.nl,
        sub_lord=pos.sl,
        sub_sub_lord=pos.sl2,
        house=house,
        is_combust=is_combust,
        is_exalted=is_exalted,
        is_debilitated=is_debilitated,
        is_own_sign=is_own_sign,
    )


def get_ruling_planets(
    timestamp: datetime, latitude: float, longitude: float
) -> dict[str, int]:
    """
    Calculate KP Ruling Planets for a moment.

    Args:
        timestamp: Time for calculation
        latitude: Location latitude
        longitude: Location longitude

    Returns:
        Dictionary of ruling planet positions
    """
    # Calculate houses for ASC
    houses = compute_houses(timestamp, latitude, longitude)
    asc = houses.cusps[0]

    # Get ASC position details
    asc_pos = get_positions(timestamp, 1, apply_kp_offset=False)  # Use Sun as dummy
    asc_pos.longitude = asc  # Override with ASC

    # Recalculate nakshatra for ASC
    asc_nakshatra = int((asc % 360) * 27 / 360) + 1
    asc_sign = int(asc / 30) + 1

    # Get Moon position
    moon_pos = get_positions(timestamp, 2, apply_kp_offset=False)

    # Day lord (weekday planet)
    weekday = timestamp.weekday()
    day_lords = [2, 9, 5, 3, 6, 8, 1]  # Mon=Moon, Tue=Mars, etc.
    day_lord = day_lords[weekday]

    # Hora lord (planetary hour - simplified)
    hour = timestamp.hour
    hora_sequence = [1, 6, 5, 2, 8, 3, 9]  # Sun start, then planetary order
    hora_lord = hora_sequence[(weekday * 24 + hour) % 7]

    # Note: For accurate KP lords of ASC, we'd need to run KP calculations on ASC degree
    # Using simplified version here

    return {
        "asc_sign_lord": SIGN_LORDS[asc_sign],
        "asc_star_lord": ((asc_nakshatra - 1) % 9) + 1,  # Simplified
        "asc_sub_lord": ((asc_nakshatra - 1) % 9) + 1,  # Would need full KP calc
        "moon_sign_lord": SIGN_LORDS[int(moon_pos.longitude / 30) + 1],
        "moon_star_lord": moon_pos.nl,
        "moon_sub_lord": moon_pos.sl,
        "day_lord": day_lord,
        "hora_lord": hora_lord,
    }


def create_sky_map(
    timestamp: datetime,
    latitude: float,
    longitude: float,
    include_aspects: bool = True,
    include_patterns: bool = True,
    aspect_min_strength: float = 0.0,
) -> SkyMap:
    """
    Create complete sky map for a moment.

    Args:
        timestamp: Time for analysis
        latitude: Location latitude
        longitude: Location longitude
        include_aspects: Whether to calculate aspects
        include_patterns: Whether to detect aspect patterns
        aspect_min_strength: Minimum aspect strength to include

    Returns:
        SkyMap object with complete celestial snapshot
    """
    # Ensure UTC
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    # Calculate houses
    houses_data = compute_houses(timestamp, latitude, longitude)
    house_cusps = houses_data.cusps

    # Get all planet snapshots
    planets = {}
    planet_positions = {}  # For aspect calculation

    for planet_id in range(1, 10):  # Planets 1-9
        snapshot = get_planet_snapshot(planet_id, timestamp, house_cusps)
        planets[planet_id] = snapshot

        # Store for aspect calculation
        planet_positions[planet_id] = {
            "longitude": snapshot.longitude,
            "speed": snapshot.speed,
            "nl": snapshot.star_lord,
            "sl": snapshot.sub_lord,
        }

    # Create house snapshots
    houses = []
    for i in range(12):
        cusp = house_cusps[i]
        sign = int(cusp / 30) + 1

        # Find occupants
        occupants = []
        for pid, planet in planets.items():
            if planet.house == i + 1:
                occupants.append(pid)

        # Get KP lords for cusp (simplified)
        cusp_nakshatra = int((cusp % 360) * 27 / 360) + 1

        house_snapshot = HouseSnapshot(
            house_num=i + 1,
            cusp_degree=cusp,
            sign=sign,
            sign_name=SIGN_NAMES[sign - 1],
            sign_lord=SIGN_LORDS[sign],
            star_lord=((cusp_nakshatra - 1) % 9) + 1,  # Simplified
            sub_lord=((cusp_nakshatra - 1) % 9) + 1,  # Would need full KP calc
            occupant_planets=occupants,
        )
        houses.append(house_snapshot)

    # Calculate aspects
    aspects = []
    aspect_patterns = []

    if include_aspects:
        transit_aspects = find_transit_aspects(
            planet_positions, min_strength=aspect_min_strength
        )
        aspects = [asp.to_dict() for asp in transit_aspects]

        if include_patterns:
            patterns = find_aspect_patterns(transit_aspects)
            aspect_patterns = [pat.to_dict() for pat in patterns]

    # Get ruling planets
    ruling_planets = get_ruling_planets(timestamp, latitude, longitude)

    # Identify active significators (simplified)
    active_significators = {}
    for house_num in range(1, 13):
        active = []
        # Occupants are always active for that house
        for pid in houses[house_num - 1].occupant_planets:
            active.append(pid)

        # Owners are active
        owner = houses[house_num - 1].sign_lord
        if owner not in active:
            active.append(owner)

        if active:
            active_significators[house_num] = active

    # Categorize planets by speed
    retrograde = []
    fast_moving = []
    slow_moving = []

    for pid, planet in planets.items():
        if planet.retrograde:
            retrograde.append(pid)

        avg_speed = AVERAGE_SPEEDS.get(pid, 1.0)
        if abs(planet.speed) > avg_speed * 1.2:
            fast_moving.append(pid)
        elif abs(planet.speed) < avg_speed * 0.8:
            slow_moving.append(pid)

    return SkyMap(
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        planets=planets,
        houses=houses,
        ascendant=house_cusps[0],
        midheaven=house_cusps[9],
        aspects=aspects,
        aspect_patterns=aspect_patterns,
        ruling_planets=ruling_planets,
        active_significators=active_significators,
        retrograde_planets=retrograde,
        fast_moving_planets=fast_moving,
        slow_moving_planets=slow_moving,
    )
