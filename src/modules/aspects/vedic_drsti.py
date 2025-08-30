"""
Vedic Drishti (Aspects) calculation module.
Implements Parashari special aspects with orbs.
"""

from dataclasses import dataclass

from config.feature_flags import require_feature
from constants.vedic_orbs import (
    ASPECT_ORBS,
    ASPECT_STRENGTH,
    KP_ASPECT_ORBS,
    SPECIAL_ASPECTS,
    get_aspect_orb,
)


@dataclass
class AspectInfo:
    """Information about a single aspect."""

    from_planet: int
    to_planet: int
    aspect_type: str
    angle: float
    orb: float
    strength: float
    is_applying: bool
    is_special: bool

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "from": self.from_planet,
            "to": self.to_planet,
            "type": self.aspect_type,
            "angle": round(self.angle, 2),
            "orb": round(self.orb, 2),
            "strength": round(self.strength, 2),
            "applying": self.is_applying,
            "special": self.is_special,
        }


@dataclass
class AspectMatrix:
    """Complete aspect relationships in chart."""

    aspects: list[AspectInfo]
    planet_aspects: dict[int, dict[int, AspectInfo]]  # From -> To mapping
    received_aspects: dict[int, list[AspectInfo]]  # Planet -> List of received
    aspect_counts: dict[int, dict[str, int]]  # Planet -> aspect type counts

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "aspects": [a.to_dict() for a in self.aspects],
            "aspect_counts": self.aspect_counts,
            "total_aspects": len(self.aspects),
        }


@require_feature("vedic_aspects")
def calculate_vedic_aspects(ctx: dict) -> dict[str, any]:
    """Calculate all Vedic aspects in the chart.

    Args:
        ctx: Context with planet positions

    Returns:
        Dictionary with aspect matrix and analysis
    """
    planets = ctx.get("planets", {})
    if not planets:
        return {}

    # Initialize aspect matrix
    matrix = AspectMatrix(
        aspects=[], planet_aspects={}, received_aspects={}, aspect_counts={}
    )

    # Calculate aspects between all planet pairs
    for from_id in range(1, 10):
        if from_id not in planets:
            continue

        from_data = planets[from_id]
        matrix.planet_aspects[from_id] = {}
        matrix.aspect_counts[from_id] = {}

        for to_id in range(1, 10):
            if to_id == from_id or to_id not in planets:
                continue

            to_data = planets[to_id]

            # Check for aspect
            aspect = check_aspect(
                from_id, from_data, to_id, to_data, ctx.get("use_kp_orbs", False)
            )

            if aspect:
                matrix.aspects.append(aspect)
                matrix.planet_aspects[from_id][to_id] = aspect

                # Track received aspects
                if to_id not in matrix.received_aspects:
                    matrix.received_aspects[to_id] = []
                matrix.received_aspects[to_id].append(aspect)

                # Count aspect types
                aspect_type = aspect.aspect_type
                if aspect_type not in matrix.aspect_counts[from_id]:
                    matrix.aspect_counts[from_id][aspect_type] = 0
                matrix.aspect_counts[from_id][aspect_type] += 1

    # Analyze aspect patterns
    analysis = analyze_aspects(matrix, planets)

    return {"vedic_aspects": matrix.to_dict(), "analysis": analysis}


def check_aspect(
    from_id: int, from_data: dict, to_id: int, to_data: dict, use_kp_orbs: bool = False
) -> AspectInfo | None:
    """Check if one planet aspects another.

    Args:
        from_id: Aspecting planet ID
        from_data: Aspecting planet data
        to_id: Aspected planet ID
        to_data: Aspected planet data
        use_kp_orbs: Use tighter KP orbs

    Returns:
        AspectInfo if aspect exists, None otherwise
    """
    from_long = from_data.get("longitude", 0)
    to_long = to_data.get("longitude", 0)

    # Calculate angular distance
    angle = calculate_angle(from_long, to_long)

    # Check standard aspects first (7th aspect - opposition)
    aspect_info = check_standard_aspect(
        from_id,
        to_id,
        angle,
        from_data.get("speed", 0),
        to_data.get("speed", 0),
        use_kp_orbs,
    )

    if aspect_info:
        return aspect_info

    # Check special Vedic aspects
    if from_id in SPECIAL_ASPECTS:
        aspect_info = check_special_aspect(
            from_id, to_id, angle, from_data, to_data, use_kp_orbs
        )

        if aspect_info:
            return aspect_info

    return None


def check_standard_aspect(
    from_id: int,
    to_id: int,
    angle: float,
    from_speed: float,
    to_speed: float,
    use_kp_orbs: bool,
) -> AspectInfo | None:
    """Check for standard aspects (conjunction, opposition, trine, square, sextile).

    Args:
        from_id: Aspecting planet
        to_id: Aspected planet
        angle: Angular distance
        from_speed: Speed of aspecting planet
        to_speed: Speed of aspected planet
        use_kp_orbs: Use KP orbs

    Returns:
        AspectInfo if standard aspect found
    """
    # Define standard aspects and their angles
    standard_aspects = {
        "conjunction": (0, 10),  # 0° ± orb
        "opposition": (180, 10),  # 180° ± orb
        "trine": (120, 9),  # 120° ± orb
        "square": (90, 8),  # 90° ± orb
        "sextile": (60, 6),  # 60° ± orb
    }

    # Also check supplementary angles for trines and squares
    if 240 - 9 <= angle <= 240 + 9:  # Second trine
        angle_diff = abs(angle - 240)
        aspect_type = "trine"
        base_angle = 240
    elif 270 - 8 <= angle <= 270 + 8:  # Second square
        angle_diff = abs(angle - 270)
        aspect_type = "square"
        base_angle = 270
    elif 300 - 6 <= angle <= 300 + 6:  # Second sextile
        angle_diff = abs(angle - 300)
        aspect_type = "sextile"
        base_angle = 300
    else:
        # Check primary aspects
        for aspect_type, (base_angle, max_orb) in standard_aspects.items():
            angle_diff = abs(angle - base_angle)
            if angle_diff <= max_orb:
                break
        else:
            return None

    # Get appropriate orb
    if use_kp_orbs:
        orb = KP_ASPECT_ORBS.get(aspect_type, 3.0)
    else:
        orb = get_aspect_orb(
            from_id, aspect_type, "natal", is_approaching=(from_speed > to_speed)
        )

    # Check if within orb
    if angle_diff > orb:
        return None

    # Calculate aspect strength
    strength = calculate_aspect_strength(aspect_type, angle_diff, orb)

    # Determine if applying or separating
    is_applying = is_aspect_applying(from_speed, to_speed, angle, base_angle)

    return AspectInfo(
        from_planet=from_id,
        to_planet=to_id,
        aspect_type=aspect_type,
        angle=angle,
        orb=angle_diff,
        strength=strength,
        is_applying=is_applying,
        is_special=False,
    )


def check_special_aspect(
    from_id: int,
    to_id: int,
    angle: float,
    from_data: dict,
    to_data: dict,
    use_kp_orbs: bool,
) -> AspectInfo | None:
    """Check for special Vedic aspects (Mars 4/8, Jupiter 5/9, Saturn 3/10).

    Args:
        from_id: Aspecting planet (must be Mars, Jupiter, or Saturn)
        to_id: Aspected planet
        angle: Angular distance
        from_data: Aspecting planet data
        to_data: Aspected planet data
        use_kp_orbs: Use KP orbs

    Returns:
        AspectInfo if special aspect found
    """
    special_houses = SPECIAL_ASPECTS.get(from_id, [])
    if not special_houses:
        return None

    from_sign = from_data.get("sign", 1)
    to_sign = to_data.get("sign", 1)

    # Calculate house difference
    house_diff = ((to_sign - from_sign) % 12) + 1

    # Check if this is a special aspect house
    if house_diff not in special_houses:
        # Also check by angle for special aspects
        special_angles = {
            9: {  # Mars
                4: 90,  # 4th aspect = 90°
                8: 210,  # 8th aspect = 210°
            },
            3: {  # Jupiter
                5: 120,  # 5th aspect = 120°
                9: 240,  # 9th aspect = 240°
            },
            8: {  # Saturn
                3: 60,  # 3rd aspect = 60°
                10: 270,  # 10th aspect = 270°
            },
        }

        if from_id not in special_angles:
            return None

        # Check angles
        found_special = False
        for house, expected_angle in special_angles[from_id].items():
            if abs(angle - expected_angle) <= 10:  # 10° orb for special
                house_diff = house
                found_special = True
                break

        if not found_special:
            return None

    # Get orb for special aspect
    aspect_type = f"special_{house_diff}th"
    if use_kp_orbs:
        orb = 3.0  # Standard KP orb for special aspects
    else:
        orb = get_aspect_orb(from_id, aspect_type, "natal", True)
        if orb == 3.0:  # Default, use planet's special orb
            orb = ASPECT_ORBS[from_id].get(aspect_type, (8.0, 8.0))[0]

    # Calculate expected angle for this house aspect
    expected_angle = ((house_diff - 1) * 30) % 360
    angle_diff = abs(angle - expected_angle)
    if angle_diff > 180:
        angle_diff = 360 - angle_diff

    if angle_diff > orb:
        return None

    # Calculate strength (special aspects are generally strong)
    base_strength = ASPECT_STRENGTH.get(aspect_type, 75.0)
    strength = base_strength * (1 - angle_diff / orb)

    # Check if applying
    is_applying = is_aspect_applying(
        from_data.get("speed", 0), to_data.get("speed", 0), angle, expected_angle
    )

    return AspectInfo(
        from_planet=from_id,
        to_planet=to_id,
        aspect_type=aspect_type,
        angle=angle,
        orb=angle_diff,
        strength=strength,
        is_applying=is_applying,
        is_special=True,
    )


def calculate_angle(long1: float, long2: float) -> float:
    """Calculate angular distance between two longitudes.

    Args:
        long1: First longitude
        long2: Second longitude

    Returns:
        Angular distance (0-360)
    """
    angle = long2 - long1
    while angle < 0:
        angle += 360
    while angle >= 360:
        angle -= 360
    return angle


def calculate_aspect_strength(aspect_type: str, orb: float, max_orb: float) -> float:
    """Calculate aspect strength based on orb.

    Args:
        aspect_type: Type of aspect
        orb: Actual orb
        max_orb: Maximum allowed orb

    Returns:
        Strength percentage (0-100)
    """
    base_strength = ASPECT_STRENGTH.get(aspect_type, 50.0)

    # Reduce strength based on orb
    if max_orb > 0:
        orb_factor = 1 - (orb / max_orb)
    else:
        orb_factor = 1.0

    return base_strength * orb_factor


def is_aspect_applying(
    from_speed: float, to_speed: float, current_angle: float, exact_angle: float
) -> bool:
    """Determine if aspect is applying or separating.

    Args:
        from_speed: Speed of aspecting planet
        to_speed: Speed of aspected planet
        current_angle: Current angular distance
        exact_angle: Exact aspect angle

    Returns:
        True if applying, False if separating
    """
    # If aspecting planet is faster and angle is less than exact, it's applying
    if from_speed > to_speed:
        return current_angle < exact_angle
    else:
        return current_angle > exact_angle


def analyze_aspects(matrix: AspectMatrix, planets: dict) -> dict[str, any]:
    """Analyze aspect patterns and provide insights.

    Args:
        matrix: Aspect matrix
        planets: Planet data

    Returns:
        Analysis dictionary
    """
    analysis = {
        "total_aspects": len(matrix.aspects),
        "applying_aspects": sum(1 for a in matrix.aspects if a.is_applying),
        "separating_aspects": sum(1 for a in matrix.aspects if not a.is_applying),
        "special_aspects": sum(1 for a in matrix.aspects if a.is_special),
        "strongest_aspects": [],
        "aspect_patterns": [],
        "planetary_stress": {},
    }

    # Find strongest aspects
    sorted_aspects = sorted(matrix.aspects, key=lambda x: x.strength, reverse=True)
    for aspect in sorted_aspects[:5]:
        analysis["strongest_aspects"].append(
            {
                "from": get_planet_name(aspect.from_planet),
                "to": get_planet_name(aspect.to_planet),
                "type": aspect.aspect_type,
                "strength": aspect.strength,
            }
        )

    # Calculate planetary stress (malefic aspects received)
    malefics = {1, 4, 7, 8, 9}  # Sun, Rahu, Ketu, Saturn, Mars

    for planet_id in range(1, 10):
        if planet_id not in planets:
            continue

        received = matrix.received_aspects.get(planet_id, [])
        malefic_aspects = sum(1 for a in received if a.from_planet in malefics)
        benefic_aspects = sum(1 for a in received if a.from_planet not in malefics)

        stress_level = "neutral"
        if malefic_aspects > benefic_aspects + 1:
            stress_level = "high"
        elif malefic_aspects > benefic_aspects:
            stress_level = "moderate"
        elif benefic_aspects > malefic_aspects:
            stress_level = "low"

        analysis["planetary_stress"][get_planet_name(planet_id)] = {
            "level": stress_level,
            "malefic_aspects": malefic_aspects,
            "benefic_aspects": benefic_aspects,
        }

    # Detect aspect patterns (simplified)
    analysis["aspect_patterns"] = detect_aspect_patterns(matrix)

    return analysis


def detect_aspect_patterns(matrix: AspectMatrix) -> list[str]:
    """Detect common aspect patterns.

    Args:
        matrix: Aspect matrix

    Returns:
        List of detected patterns
    """
    patterns = []

    # Check for Grand Trine (3 planets in trine)
    trines = [a for a in matrix.aspects if a.aspect_type == "trine"]
    if len(trines) >= 3:
        # Check if they form a closed triangle
        planets_in_trine = set()
        for trine in trines:
            planets_in_trine.add(trine.from_planet)
            planets_in_trine.add(trine.to_planet)

        if len(planets_in_trine) == 3:
            patterns.append("Grand Trine")

    # Check for T-Square (2 squares and 1 opposition)
    squares = [a for a in matrix.aspects if a.aspect_type == "square"]
    oppositions = [a for a in matrix.aspects if a.aspect_type == "opposition"]

    if len(squares) >= 2 and len(oppositions) >= 1:
        patterns.append("T-Square")

    # Check for Grand Cross (2 oppositions and 4 squares)
    if len(squares) >= 4 and len(oppositions) >= 2:
        patterns.append("Grand Cross")

    # Check for Stellium (4+ planets in conjunction)
    conjunctions = [a for a in matrix.aspects if a.aspect_type == "conjunction"]
    if len(conjunctions) >= 3:
        patterns.append("Stellium Potential")

    return patterns if patterns else ["No major patterns"]


def get_planet_name(planet_id: int) -> str:
    """Get planet name from ID."""
    names = {
        1: "Sun",
        2: "Moon",
        3: "Jupiter",
        4: "Rahu",
        5: "Mercury",
        6: "Venus",
        7: "Ketu",
        8: "Saturn",
        9: "Mars",
    }
    return names.get(planet_id, f"Planet_{planet_id}")
