"""
Ashtakavarga benefic point constants.
Based on traditional Parashari system.
"""


# Ashtakavarga benefic points
# Format: {planet_id: {from_planet_id: [benefic_houses]}}
# Houses are counted from the planet's position

BENEFIC_POINTS: dict[int, dict[int, list[int]]] = {
    1: {  # Sun's Ashtakavarga
        1: [1, 2, 4, 7, 8, 9, 10, 11],     # From Sun itself
        2: [3, 6, 10, 11],                  # From Moon
        3: [5, 6, 9, 11],                   # From Jupiter
        4: [],                              # From Rahu (not used)
        5: [3, 5, 6, 9, 10, 11, 12],        # From Mercury
        6: [6, 7, 12],                      # From Venus
        7: [],                              # From Ketu (not used)
        8: [1, 2, 4, 7, 8, 9, 10, 11],     # From Saturn
        9: [1, 2, 4, 7, 8, 9, 10, 11],     # From Mars
        0: [3, 4, 6, 10, 11, 12],           # From Ascendant
    },
    2: {  # Moon's Ashtakavarga
        1: [3, 6, 7, 8, 10, 11],            # From Sun
        2: [1, 3, 6, 7, 9, 10, 11],         # From Moon itself
        3: [1, 3, 4, 5, 7, 8, 10, 11],     # From Jupiter
        4: [],                              # From Rahu
        5: [1, 3, 4, 5, 7, 8, 10, 11],     # From Mercury
        6: [3, 4, 5, 7, 9, 10, 11],         # From Venus
        7: [],                              # From Ketu
        8: [3, 5, 6, 11],                   # From Saturn
        9: [2, 3, 5, 6, 9, 10, 11],         # From Mars
        0: [3, 6, 10, 11],                  # From Ascendant
    },
    3: {  # Jupiter's Ashtakavarga
        1: [1, 2, 3, 4, 7, 8, 9, 10, 11],  # From Sun
        2: [2, 5, 7, 9, 11],                # From Moon
        3: [1, 2, 3, 4, 7, 8, 10, 11],     # From Jupiter itself
        4: [],                              # From Rahu
        5: [1, 2, 4, 5, 6, 9, 11],          # From Mercury
        6: [2, 5, 6, 9, 10, 11],            # From Venus
        7: [],                              # From Ketu
        8: [3, 5, 6, 12],                   # From Saturn
        9: [1, 2, 4, 7, 8, 10, 11],         # From Mars
        0: [1, 2, 4, 5, 6, 7, 9, 10, 11],   # From Ascendant
    },
    5: {  # Mercury's Ashtakavarga
        1: [5, 6, 9, 11, 12],               # From Sun
        2: [2, 4, 6, 8, 10, 11],            # From Moon
        3: [1, 2, 4, 7, 8, 9, 10, 11],     # From Jupiter
        4: [],                              # From Rahu
        5: [1, 3, 5, 6, 9, 10, 11, 12],    # From Mercury itself
        6: [1, 2, 3, 4, 5, 8, 9, 11],       # From Venus
        7: [],                              # From Ketu
        8: [1, 2, 4, 7, 8, 9, 10, 11],     # From Saturn
        9: [1, 2, 4, 7, 8, 9, 10, 11],     # From Mars
        0: [1, 2, 4, 6, 8, 10, 11],         # From Ascendant
    },
    6: {  # Venus's Ashtakavarga
        1: [8, 11, 12],                     # From Sun
        2: [1, 2, 3, 4, 5, 8, 9, 11, 12],  # From Moon
        3: [1, 2, 3, 4, 5, 8, 9, 10, 11],  # From Jupiter
        4: [],                              # From Rahu
        5: [3, 5, 6, 9, 11],                # From Mercury
        6: [1, 2, 3, 4, 5, 8, 9, 10, 11],  # From Venus itself
        7: [],                              # From Ketu
        8: [3, 4, 5, 8, 9, 10, 11],         # From Saturn
        9: [3, 5, 6, 9, 11, 12],            # From Mars
        0: [1, 2, 3, 4, 5, 8, 9, 11],       # From Ascendant
    },
    8: {  # Saturn's Ashtakavarga
        1: [1, 2, 4, 7, 8, 10, 11],         # From Sun
        2: [3, 6, 11],                      # From Moon
        3: [5, 6, 11, 12],                  # From Jupiter
        4: [],                              # From Rahu
        5: [6, 8, 9, 10, 11, 12],           # From Mercury
        6: [6, 11, 12],                     # From Venus
        7: [],                              # From Ketu
        8: [3, 5, 6, 11],                   # From Saturn itself
        9: [3, 5, 6, 10, 11, 12],           # From Mars
        0: [1, 3, 4, 6, 10, 11],            # From Ascendant
    },
    9: {  # Mars's Ashtakavarga
        1: [3, 5, 6, 10, 11],               # From Sun
        2: [3, 6, 11],                      # From Moon
        3: [1, 2, 4, 7, 8, 10, 11],         # From Jupiter
        4: [],                              # From Rahu
        5: [3, 5, 6, 11],                   # From Mercury
        6: [6, 8, 11, 12],                  # From Venus
        7: [],                              # From Ketu
        8: [1, 4, 7, 8, 9, 10, 11],         # From Saturn
        9: [1, 2, 4, 7, 8, 10, 11],         # From Mars itself
        0: [1, 3, 6, 10, 11],               # From Ascendant
    },
}

# Nodes (Rahu/Ketu) don't have traditional Ashtakavarga
# But we can assign them based on their shadow nature
BENEFIC_POINTS[4] = BENEFIC_POINTS[8].copy()  # Rahu like Saturn
BENEFIC_POINTS[7] = BENEFIC_POINTS[9].copy()  # Ketu like Mars

# Standard SAV (Sarvashtakavarga) reduction rules
SAV_REDUCTION_RULES = {
    'trikashuddhi': True,    # Reduction of malefic houses (6, 8, 12)
    'ekadhipatya': True,     # Reduction for dual lordship
    'minimum_points': 2,      # Minimum points to retain in a house
    'maximum_points': 8,      # Maximum points in a house
}

# Interpretation thresholds
BINDHU_INTERPRETATION = {
    'excellent': 6,    # 6-8 bindus - Excellent results
    'good': 5,         # 5 bindus - Good results
    'average': 4,      # 4 bindus - Average results
    'below_avg': 3,    # 3 bindus - Below average
    'poor': 2,         # 0-2 bindus - Poor results
}

# SAV (Total) interpretation
SAV_INTERPRETATION = {
    'excellent': 33,   # 33+ points - Excellent
    'good': 28,        # 28-32 points - Good
    'average': 25,     # 25-27 points - Average
    'weak': 20,        # 20-24 points - Weak
    'very_weak': 19,   # Below 20 - Very weak
}

# Transit activation thresholds
TRANSIT_ACTIVATION = {
    'strong': 5,       # 5+ bindus for strong transit effects
    'moderate': 4,     # 4 bindus for moderate effects
    'weak': 3,         # 3 bindus for weak effects
    'negligible': 2,   # 2 or less - negligible effects
}

def get_benefic_houses(from_planet: int, to_planet: int) -> list[int]:
    """Get benefic houses from one planet to another.
    
    Args:
        from_planet: Source planet ID (0 for Ascendant)
        to_planet: Target planet ID
        
    Returns:
        List of benefic house positions
    """
    if to_planet not in BENEFIC_POINTS:
        return []

    return BENEFIC_POINTS[to_planet].get(from_planet, [])
