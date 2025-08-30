"""
Vedic aspect orbs and influence ranges.
Based on traditional Parashari and KP principles.
"""


# Planetary aspect orbs in degrees
# Format: {planet_id: {aspect_type: (approaching_orb, separating_orb)}}
ASPECT_ORBS: dict[int, dict[str, tuple[float, float]]] = {
    1: {  # Sun
        'conjunction': (8.0, 8.0),
        'opposition': (8.0, 8.0),
        'square': (6.0, 6.0),
        'trine': (6.0, 6.0),
        'sextile': (4.0, 4.0),
    },
    2: {  # Moon
        'conjunction': (12.0, 12.0),
        'opposition': (12.0, 12.0),
        'square': (9.0, 9.0),
        'trine': (9.0, 9.0),
        'sextile': (6.0, 6.0),
    },
    3: {  # Jupiter
        'conjunction': (9.0, 9.0),
        'opposition': (9.0, 9.0),
        'square': (7.0, 7.0),
        'trine': (9.0, 9.0),  # Special 5th/9th aspects
        'sextile': (5.0, 5.0),
        'special_5th': (9.0, 9.0),  # 120-degree aspect
        'special_9th': (9.0, 9.0),  # 240-degree aspect
    },
    4: {  # Rahu (Node)
        'conjunction': (5.0, 5.0),
        'opposition': (5.0, 5.0),
        'square': (3.0, 3.0),
        'trine': (3.0, 3.0),
        'sextile': (2.0, 2.0),
    },
    5: {  # Mercury
        'conjunction': (7.0, 7.0),
        'opposition': (7.0, 7.0),
        'square': (5.0, 5.0),
        'trine': (5.0, 5.0),
        'sextile': (3.0, 3.0),
    },
    6: {  # Venus
        'conjunction': (7.0, 7.0),
        'opposition': (7.0, 7.0),
        'square': (5.0, 5.0),
        'trine': (5.0, 5.0),
        'sextile': (3.0, 3.0),
    },
    7: {  # Ketu (Node)
        'conjunction': (5.0, 5.0),
        'opposition': (5.0, 5.0),
        'square': (3.0, 3.0),
        'trine': (3.0, 3.0),
        'sextile': (2.0, 2.0),
    },
    8: {  # Saturn
        'conjunction': (10.0, 10.0),
        'opposition': (10.0, 10.0),
        'square': (7.5, 7.5),
        'trine': (7.5, 7.5),
        'sextile': (5.0, 5.0),
        'special_3rd': (10.0, 10.0),  # 60-degree aspect
        'special_10th': (10.0, 10.0),  # 270-degree aspect
    },
    9: {  # Mars
        'conjunction': (8.0, 8.0),
        'opposition': (8.0, 8.0),
        'square': (8.0, 8.0),  # Special 4th aspect
        'trine': (6.0, 6.0),
        'sextile': (4.0, 4.0),
        'special_4th': (8.0, 8.0),  # 90-degree aspect
        'special_8th': (8.0, 8.0),  # 210-degree aspect
    },
}

# Special Vedic aspects (Parashari system)
# Mars aspects 4th and 8th houses/signs
# Jupiter aspects 5th and 9th houses/signs
# Saturn aspects 3rd and 10th houses/signs
SPECIAL_ASPECTS: dict[int, list[int]] = {
    9: [4, 8],    # Mars: 4th and 8th from itself
    3: [5, 9],    # Jupiter: 5th and 9th from itself
    8: [3, 10],   # Saturn: 3rd and 10th from itself
}

# Aspect strength percentages based on angular distance
# Full aspects: 7th (100%), special aspects (75-100%)
# Other aspects decrease with distance
ASPECT_STRENGTH: dict[str, float] = {
    'conjunction': 100.0,
    'opposition': 100.0,
    'trine': 75.0,
    'square': 50.0,
    'sextile': 25.0,
    'special_3rd': 100.0,   # Saturn's 3rd aspect
    'special_4th': 100.0,   # Mars's 4th aspect
    'special_5th': 100.0,   # Jupiter's 5th aspect
    'special_8th': 100.0,   # Mars's 8th aspect
    'special_9th': 100.0,   # Jupiter's 9th aspect
    'special_10th': 100.0,  # Saturn's 10th aspect
}

# KP system uses tighter orbs for sublord activation
KP_ASPECT_ORBS: dict[str, float] = {
    'conjunction': 3.20,  # 3°12' traditional KP orb
    'opposition': 3.20,
    'square': 2.40,       # 2°24'
    'trine': 2.40,
    'sextile': 1.60,      # 1°36'
}

# Orb modifiers for different calculation contexts
ORB_MODIFIERS: dict[str, float] = {
    'natal': 1.0,         # Standard orbs
    'transit': 0.5,       # Half orbs for transits
    'progression': 0.25,  # Quarter orbs for progressions
    'solar_return': 0.75, # 3/4 orbs for solar returns
    'lunar_return': 0.6,  # Tighter for lunar returns
    'horary': 0.4,        # Very tight for horary
}

def get_aspect_orb(planet_id: int, aspect_type: str,
                   context: str = 'natal', is_approaching: bool = True) -> float:
    """Get the orb for a specific planet and aspect type.
    
    Args:
        planet_id: Planet ID (1-9)
        aspect_type: Type of aspect (conjunction, square, etc.)
        context: Calculation context (natal, transit, etc.)
        is_approaching: Whether aspect is applying or separating
        
    Returns:
        Orb in degrees
    """
    if planet_id not in ASPECT_ORBS:
        return 5.0  # Default orb

    planet_orbs = ASPECT_ORBS[planet_id]
    if aspect_type not in planet_orbs:
        return 3.0  # Default for unknown aspect

    approaching_orb, separating_orb = planet_orbs[aspect_type]
    base_orb = approaching_orb if is_approaching else separating_orb

    modifier = ORB_MODIFIERS.get(context, 1.0)
    return base_orb * modifier
