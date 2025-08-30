"""
Combustion and solar proximity orbs for planetary states.
Based on traditional Vedic astrology texts.
"""


# Combustion orbs from the Sun in degrees
# Format: {planet_id: (combust_orb, deep_combust_orb)}
COMBUSTION_ORBS: dict[int, tuple[float, float]] = {
    2: (12.0, 6.0),   # Moon: combust within 12°, deep within 6°
    3: (11.0, 5.5),   # Jupiter: combust within 11°, deep within 5.5°
    4: (8.0, 4.0),    # Rahu: theoretical (nodes don't combust traditionally)
    5: (14.0, 7.0),   # Mercury: combust within 14°, deep within 7° (retrograde: 12°)
    6: (10.0, 5.0),   # Venus: combust within 10°, deep within 5° (retrograde: 8°)
    7: (8.0, 4.0),    # Ketu: theoretical (nodes don't combust traditionally)
    8: (15.0, 7.5),   # Saturn: combust within 15°, deep within 7.5°
    9: (17.0, 8.5),   # Mars: combust within 17°, deep within 8.5°
}

# Special Mercury retrograde combustion
MERCURY_RETROGRADE_COMBUST = 12.0
MERCURY_RETROGRADE_DEEP = 6.0

# Venus retrograde combustion
VENUS_RETROGRADE_COMBUST = 8.0
VENUS_RETROGRADE_DEEP = 4.0

# Cazimi (heart of the Sun) - extremely close conjunction
# Planet gains strength instead of losing it
CAZIMI_ORB = 0.2833  # 17 minutes of arc (17/60 degrees)

# Under the beams (wider solar influence)
# Planet is weakened but not fully combust
UNDER_BEAMS_ORB = 17.0  # Universal for all planets

# Eclipse orbs for Sun-Moon conjunctions/oppositions
SOLAR_ECLIPSE_ORB = 18.0  # Maximum orb for solar eclipse possibility
LUNAR_ECLIPSE_ORB = 12.0  # Maximum orb for lunar eclipse possibility

# Planet visibility thresholds from Sun (heliacal rising/setting)
HELIACAL_VISIBILITY: dict[int, float] = {
    2: 12.0,   # Moon becomes visible
    3: 9.0,    # Jupiter morning/evening star
    5: 18.0,   # Mercury (varies 16-21° based on elongation)
    6: 8.0,    # Venus morning/evening star
    8: 13.0,   # Saturn visibility
    9: 14.0,   # Mars visibility
}

# Combustion strength reduction percentages
COMBUSTION_STRENGTH_LOSS: dict[str, float] = {
    'deep_combust': 75.0,    # 75% strength loss
    'combust': 50.0,         # 50% strength loss
    'under_beams': 25.0,     # 25% strength loss
    'cazimi': -50.0,         # 50% strength GAIN (negative = gain)
    'normal': 0.0,           # No effect
}

# Special conditions for nodes (Rahu/Ketu)
# Nodes within these orbs of Sun/Moon create eclipse yogas
NODE_ECLIPSE_ORBS: dict[str, float] = {
    'total_solar': 5.0,      # Total solar eclipse
    'partial_solar': 10.0,   # Partial solar eclipse
    'total_lunar': 6.0,      # Total lunar eclipse
    'partial_lunar': 12.0,   # Partial lunar eclipse
}

def get_combustion_state(planet_id: int, distance_from_sun: float,
                         is_retrograde: bool = False) -> str:
    """Determine combustion state of a planet.
    
    Args:
        planet_id: Planet ID (2-9, excluding Sun)
        distance_from_sun: Angular distance from Sun in degrees
        is_retrograde: Whether planet is retrograde
        
    Returns:
        State: 'cazimi', 'deep_combust', 'combust', 'under_beams', or 'normal'
    """
    if planet_id == 1:  # Sun itself
        return 'normal'

    # Check for cazimi first (strongest positive state)
    if distance_from_sun <= CAZIMI_ORB:
        return 'cazimi'

    # Get combustion orbs for this planet
    if planet_id not in COMBUSTION_ORBS:
        return 'normal'

    combust_orb, deep_orb = COMBUSTION_ORBS[planet_id]

    # Adjust for retrograde Mercury or Venus
    if is_retrograde:
        if planet_id == 5:  # Mercury
            combust_orb = MERCURY_RETROGRADE_COMBUST
            deep_orb = MERCURY_RETROGRADE_DEEP
        elif planet_id == 6:  # Venus
            combust_orb = VENUS_RETROGRADE_COMBUST
            deep_orb = VENUS_RETROGRADE_DEEP

    # Check combustion states in order of severity
    if distance_from_sun <= deep_orb:
        return 'deep_combust'
    elif distance_from_sun <= combust_orb:
        return 'combust'
    elif distance_from_sun <= UNDER_BEAMS_ORB:
        return 'under_beams'
    else:
        return 'normal'

def get_strength_modifier(combustion_state: str) -> float:
    """Get strength modification percentage for combustion state.
    
    Args:
        combustion_state: State from get_combustion_state()
        
    Returns:
        Strength modifier as percentage (-50 to 75)
    """
    return COMBUSTION_STRENGTH_LOSS.get(combustion_state, 0.0)

def is_heliacally_visible(planet_id: int, elongation: float) -> bool:
    """Check if planet is heliacally visible (morning/evening star).
    
    Args:
        planet_id: Planet ID
        elongation: Angular distance from Sun
        
    Returns:
        True if planet is visible as morning/evening star
    """
    if planet_id not in HELIACAL_VISIBILITY:
        return True  # Outer planets always visible when above horizon

    return elongation >= HELIACAL_VISIBILITY[planet_id]
