#!/usr/bin/env python3
"""
KP Transit Aspect Calculator
Real-time planetary aspect calculations for transit-to-transit analysis
"""


from dataclasses import dataclass
from enum import Enum

from .constants import PLANET_NAMES


class AspectType(Enum):
    """KP aspect types with their angles"""

    CONJUNCTION = (0, "Conjunction", 8.0)  # 0° with 8° orb
    SEXTILE = (60, "Sextile", 6.0)  # 60° with 6° orb
    SQUARE = (90, "Square", 7.0)  # 90° with 7° orb
    TRINE = (120, "Trine", 8.0)  # 120° with 8° orb
    OPPOSITION = (180, "Opposition", 8.0)  # 180° with 8° orb

    # KP-specific aspects
    SEMI_SEXTILE = (30, "Semi-sextile", 2.0)  # 30° with 2° orb
    SEMI_SQUARE = (45, "Semi-square", 2.0)  # 45° with 2° orb
    SESQUIQUADRATE = (135, "Sesquiquadrate", 2.0)  # 135° with 2° orb
    QUINCUNX = (150, "Quincunx", 2.0)  # 150° with 2° orb

    @property
    def angle(self) -> float:
        return self.value[0]

    @property
    def name(self) -> str:
        return self.value[1]

    @property
    def orb(self) -> float:
        return self.value[2]


@dataclass
class TransitAspect:
    """Single aspect between two transiting planets"""

    planet1_id: int
    planet2_id: int
    planet1_name: str
    planet2_name: str
    planet1_longitude: float
    planet2_longitude: float
    aspect_type: AspectType
    exact_angle: float  # The exact angle between planets
    orb_used: float  # How far from exact aspect
    is_applying: bool  # True if aspect is forming, False if separating
    is_tight: bool  # True if within 1° orb
    strength: float  # 0-100 based on orb (100 at exact, 0 at max orb)

    # KP specific
    planet1_star_lord: int | None = None
    planet2_star_lord: int | None = None
    planet1_sub_lord: int | None = None
    planet2_sub_lord: int | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "planets": f"{self.planet1_name}-{self.planet2_name}",
            "aspect": self.aspect_type.name,
            "angle": round(self.exact_angle, 2),
            "orb": round(self.orb_used, 2),
            "applying": self.is_applying,
            "tight": self.is_tight,
            "strength": round(self.strength, 1),
            "planet1": {
                "id": self.planet1_id,
                "name": self.planet1_name,
                "longitude": round(self.planet1_longitude, 4),
                "star_lord": (
                    PLANET_NAMES.get(self.planet1_star_lord)
                    if self.planet1_star_lord
                    else None
                ),
                "sub_lord": (
                    PLANET_NAMES.get(self.planet1_sub_lord)
                    if self.planet1_sub_lord
                    else None
                ),
            },
            "planet2": {
                "id": self.planet2_id,
                "name": self.planet2_name,
                "longitude": round(self.planet2_longitude, 4),
                "star_lord": (
                    PLANET_NAMES.get(self.planet2_star_lord)
                    if self.planet2_star_lord
                    else None
                ),
                "sub_lord": (
                    PLANET_NAMES.get(self.planet2_sub_lord)
                    if self.planet2_sub_lord
                    else None
                ),
            },
        }


@dataclass
class AspectPattern:
    """Special aspect patterns (T-square, Grand Trine, etc)"""

    pattern_type: str
    planets: list[int]
    aspects: list[TransitAspect]
    strength: float
    description: str

    def to_dict(self) -> dict:
        return {
            "type": self.pattern_type,
            "planets": [PLANET_NAMES.get(p, str(p)) for p in self.planets],
            "aspect_count": len(self.aspects),
            "strength": round(self.strength, 1),
            "description": self.description,
        }


def calculate_angular_distance(long1: float, long2: float) -> float:
    """
    Calculate shortest angular distance between two longitudes.

    Args:
        long1: First longitude (0-360)
        long2: Second longitude (0-360)

    Returns:
        Angular distance (0-180)
    """
    diff = abs(long1 - long2)
    if diff > 180:
        diff = 360 - diff
    return diff


def is_aspect_applying(
    planet1_long: float,
    planet2_long: float,
    planet1_speed: float,
    planet2_speed: float,
    aspect_angle: float,
) -> bool:
    """
    Determine if aspect is applying (forming) or separating.

    Args:
        planet1_long: First planet longitude
        planet2_long: Second planet longitude
        planet1_speed: First planet daily motion
        planet2_speed: Second planet daily motion
        aspect_angle: Target aspect angle

    Returns:
        True if applying, False if separating
    """
    current_distance = calculate_angular_distance(planet1_long, planet2_long)

    # Project positions forward by small amount
    future1 = (planet1_long + planet1_speed * 0.01) % 360
    future2 = (planet2_long + planet2_speed * 0.01) % 360
    future_distance = calculate_angular_distance(future1, future2)

    # If moving closer to exact aspect angle, it's applying
    current_diff = abs(current_distance - aspect_angle)
    future_diff = abs(future_distance - aspect_angle)

    return future_diff < current_diff


def calculate_aspect_strength(orb_used: float, max_orb: float) -> float:
    """
    Calculate aspect strength based on orb.

    Exact aspect = 100%, decreases linearly to 0% at max orb.

    Args:
        orb_used: Actual orb from exact
        max_orb: Maximum allowed orb

    Returns:
        Strength percentage (0-100)
    """
    if orb_used >= max_orb:
        return 0.0

    return 100.0 * (1.0 - (orb_used / max_orb))


def find_transit_aspects(
    planet_positions: dict[int, dict],
    aspect_types: list[AspectType] | None = None,
    min_strength: float = 0.0,
    include_moon: bool = True,
    tight_orbs_only: bool = False,
) -> list[TransitAspect]:
    """
    Find all aspects between transiting planets.

    Args:
        planet_positions: Dict with planet data including longitude, speed, nl, sl
        aspect_types: Which aspects to look for (default: major aspects)
        min_strength: Minimum aspect strength to include (0-100)
        include_moon: Whether to include Moon aspects (many due to speed)
        tight_orbs_only: Use only tight orbs (within 1°)

    Returns:
        List of TransitAspect objects
    """
    if aspect_types is None:
        # Default to major aspects
        aspect_types = [
            AspectType.CONJUNCTION,
            AspectType.SEXTILE,
            AspectType.SQUARE,
            AspectType.TRINE,
            AspectType.OPPOSITION,
        ]

    aspects = []
    planet_ids = list(planet_positions.keys())

    # Check all planet pairs
    for i, planet1_id in enumerate(planet_ids):
        # Skip Moon if requested
        if not include_moon and planet1_id == 2:
            continue

        for planet2_id in planet_ids[i + 1 :]:
            # Skip Moon if requested
            if not include_moon and planet2_id == 2:
                continue

            p1 = planet_positions[planet1_id]
            p2 = planet_positions[planet2_id]

            long1 = p1.get("longitude", 0)
            long2 = p2.get("longitude", 0)
            distance = calculate_angular_distance(long1, long2)

            # Check each aspect type
            for aspect_type in aspect_types:
                orb_limit = 1.0 if tight_orbs_only else aspect_type.orb
                orb_used = abs(distance - aspect_type.angle)

                if orb_used <= orb_limit:
                    # Calculate strength
                    strength = calculate_aspect_strength(orb_used, orb_limit)

                    if strength >= min_strength:
                        # Determine if applying
                        speed1 = p1.get("speed", 1.0)
                        speed2 = p2.get("speed", 1.0)
                        applying = is_aspect_applying(
                            long1, long2, speed1, speed2, aspect_type.angle
                        )

                        aspect = TransitAspect(
                            planet1_id=planet1_id,
                            planet2_id=planet2_id,
                            planet1_name=PLANET_NAMES.get(planet1_id, str(planet1_id)),
                            planet2_name=PLANET_NAMES.get(planet2_id, str(planet2_id)),
                            planet1_longitude=long1,
                            planet2_longitude=long2,
                            aspect_type=aspect_type,
                            exact_angle=distance,
                            orb_used=orb_used,
                            is_applying=applying,
                            is_tight=(orb_used <= 1.0),
                            strength=strength,
                            planet1_star_lord=p1.get("nl"),
                            planet2_star_lord=p2.get("nl"),
                            planet1_sub_lord=p1.get("sl"),
                            planet2_sub_lord=p2.get("sl"),
                        )
                        aspects.append(aspect)

    # Sort by strength (strongest first)
    aspects.sort(key=lambda x: x.strength, reverse=True)

    return aspects


def find_aspect_patterns(aspects: list[TransitAspect]) -> list[AspectPattern]:
    """
    Identify special aspect patterns like Grand Trine, T-Square, etc.

    Args:
        aspects: List of transit aspects

    Returns:
        List of identified patterns
    """
    patterns = []

    # Build adjacency for pattern detection
    connections = {}
    for aspect in aspects:
        p1, p2 = aspect.planet1_id, aspect.planet2_id

        if p1 not in connections:
            connections[p1] = []
        if p2 not in connections:
            connections[p2] = []

        connections[p1].append((p2, aspect))
        connections[p2].append((p1, aspect))

    # Look for Grand Trine (3 planets in trine)
    for p1 in connections:
        trines_from_p1 = [
            (p2, asp)
            for p2, asp in connections[p1]
            if asp.aspect_type == AspectType.TRINE
        ]

        if len(trines_from_p1) >= 2:
            # Check if the other two planets also trine each other
            for i, (p2, asp1) in enumerate(trines_from_p1):
                for p3, asp2 in trines_from_p1[i + 1 :]:
                    # Check if p2 and p3 are in trine
                    for p, asp in connections[p2]:
                        if p == p3 and asp.aspect_type == AspectType.TRINE:
                            # Found Grand Trine!
                            pattern = AspectPattern(
                                pattern_type="Grand Trine",
                                planets=[p1, p2, p3],
                                aspects=[asp1, asp2, asp],
                                strength=min(
                                    asp1.strength, asp2.strength, asp.strength
                                ),
                                description=f"Harmonious flow between {PLANET_NAMES.get(p1)}, {PLANET_NAMES.get(p2)}, {PLANET_NAMES.get(p3)}",
                            )
                            patterns.append(pattern)

    # Look for T-Square (3 planets: 2 in opposition, both square to third)
    for p1 in connections:
        squares_from_p1 = [
            (p2, asp)
            for p2, asp in connections[p1]
            if asp.aspect_type == AspectType.SQUARE
        ]

        if len(squares_from_p1) >= 2:
            # Check if the other two are in opposition
            for i, (p2, asp1) in enumerate(squares_from_p1):
                for p3, asp2 in squares_from_p1[i + 1 :]:
                    for p, asp in connections[p2]:
                        if p == p3 and asp.aspect_type == AspectType.OPPOSITION:
                            # Found T-Square!
                            pattern = AspectPattern(
                                pattern_type="T-Square",
                                planets=[p1, p2, p3],
                                aspects=[asp1, asp2, asp],
                                strength=min(
                                    asp1.strength, asp2.strength, asp.strength
                                ),
                                description=f"Dynamic tension: {PLANET_NAMES.get(p1)} squares both {PLANET_NAMES.get(p2)} and {PLANET_NAMES.get(p3)}",
                            )
                            patterns.append(pattern)

    # Look for Stellium (3+ planets in conjunction)
    conjunction_groups = {}
    for aspect in aspects:
        if aspect.aspect_type == AspectType.CONJUNCTION:
            p1, p2 = aspect.planet1_id, aspect.planet2_id

            # Find which group each planet belongs to
            group1 = None
            group2 = None

            for group_id, members in conjunction_groups.items():
                if p1 in members:
                    group1 = group_id
                if p2 in members:
                    group2 = group_id

            if group1 and group2 and group1 != group2:
                # Merge groups
                conjunction_groups[group1].update(conjunction_groups[group2])
                del conjunction_groups[group2]
            elif group1:
                conjunction_groups[group1].add(p2)
            elif group2:
                conjunction_groups[group2].add(p1)
            else:
                # Create new group
                new_id = len(conjunction_groups)
                conjunction_groups[new_id] = {p1, p2}

    # Report stelliums (3+ planets)
    for group_id, planets in conjunction_groups.items():
        if len(planets) >= 3:
            planet_list = list(planets)
            pattern = AspectPattern(
                pattern_type="Stellium",
                planets=planet_list,
                aspects=[
                    a
                    for a in aspects
                    if a.aspect_type == AspectType.CONJUNCTION
                    and a.planet1_id in planets
                    and a.planet2_id in planets
                ],
                strength=80.0,  # Stelliums are always significant
                description=f"Concentrated energy: {', '.join([PLANET_NAMES.get(p, str(p)) for p in planet_list])}",
            )
            patterns.append(pattern)

    return patterns


def get_active_trigger_aspects(
    aspects: list[TransitAspect], significator_planets: list[int]
) -> list[TransitAspect]:
    """
    Filter aspects that involve significator planets (KP triggers).

    Args:
        aspects: All transit aspects
        significator_planets: Planets that are significators for an event

    Returns:
        Aspects that could trigger the event
    """
    triggers = []

    for aspect in aspects:
        # Check if either planet is a significator
        if (
            aspect.planet1_id in significator_planets
            or aspect.planet2_id in significator_planets
        ):

            # Tight, applying aspects are strongest triggers
            if aspect.is_tight and aspect.is_applying:
                triggers.append(aspect)
            # Include separating if very tight
            elif aspect.orb_used <= 0.5:
                triggers.append(aspect)

    return triggers
