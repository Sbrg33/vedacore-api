"""
Planetary friendship and relationship constants.
Naisargika (natural) and Tatkalika (temporal) relationships.
"""


# Natural planetary friendships (Naisargika Maitri)
# Based on Brihat Parasara Hora Shastra
NATURAL_FRIENDS: dict[int, set[int]] = {
    1: {2, 9, 3},           # Sun: friends with Moon, Mars, Jupiter
    2: {1, 5},              # Moon: friends with Sun, Mercury
    3: {1, 2, 9},           # Jupiter: friends with Sun, Moon, Mars
    4: {5, 6, 8},           # Rahu: friends with Mercury, Venus, Saturn
    5: {1, 6},              # Mercury: friends with Sun, Venus
    6: {5, 8},              # Venus: friends with Mercury, Saturn
    7: {9, 6, 5},           # Ketu: friends with Mars, Venus, Mercury
    8: {5, 6},              # Saturn: friends with Mercury, Venus
    9: {1, 2, 3},           # Mars: friends with Sun, Moon, Jupiter
}

# Natural planetary enemies (Naisargika Shatru)
NATURAL_ENEMIES: dict[int, set[int]] = {
    1: {6, 8},              # Sun: enemies with Venus, Saturn
    2: {4, 7},              # Moon: enemies with Rahu, Ketu (theoretical)
    3: {5, 6},              # Jupiter: enemies with Mercury, Venus
    4: {1, 2, 9},           # Rahu: enemies with Sun, Moon, Mars
    5: {2},                 # Mercury: enemy with Moon
    6: {1, 2},              # Venus: enemies with Sun, Moon
    7: {1, 2},              # Ketu: enemies with Sun, Moon
    8: {1, 2, 9},           # Saturn: enemies with Sun, Moon, Mars
    9: {5},                 # Mars: enemy with Mercury
}

# Neutral relationships (neither friend nor enemy)
# Calculated as: All planets - Friends - Enemies - Self
def get_natural_neutrals(planet_id: int) -> set[int]:
    """Get naturally neutral planets for a given planet."""
    all_planets = set(range(1, 10))
    friends = NATURAL_FRIENDS.get(planet_id, set())
    enemies = NATURAL_ENEMIES.get(planet_id, set())
    neutrals = all_planets - friends - enemies - {planet_id}
    return neutrals

# Tatkalika (Temporal) Friendship Rules
# Based on house positions from each other
TEMPORAL_FRIEND_HOUSES = [2, 3, 4, 10, 11, 12]  # Houses from planet
TEMPORAL_ENEMY_HOUSES = [1, 5, 6, 7, 8, 9]      # Including conjunction

# Compound relationship calculation
# Natural Friend + Temporal Friend = Best Friend (Adhi Mitra)
# Natural Friend + Temporal Enemy = Neutral
# Natural Neutral + Temporal Friend = Friend
# Natural Neutral + Temporal Enemy = Enemy
# Natural Enemy + Temporal Friend = Neutral
# Natural Enemy + Temporal Enemy = Bitter Enemy (Adhi Shatru)

RELATIONSHIP_SCORES = {
    'best_friend': 2,      # Adhi Mitra
    'friend': 1,           # Mitra
    'neutral': 0,          # Sama
    'enemy': -1,           # Shatru
    'bitter_enemy': -2,    # Adhi Shatru
}

# Panchadha Maitri Chakra (5-fold friendship) scoring
PANCHADHA_POINTS = {
    'best_friend': 1.0,
    'friend': 0.75,
    'neutral': 0.5,
    'enemy': 0.25,
    'bitter_enemy': 0.0,
}

# Sign lordships for friendship calculation
SIGN_LORDS: dict[int, int] = {
    1: 1,    # Aries - Mars
    2: 6,    # Taurus - Venus
    3: 5,    # Gemini - Mercury
    4: 2,    # Cancer - Moon
    5: 1,    # Leo - Sun
    6: 5,    # Virgo - Mercury
    7: 6,    # Libra - Venus
    8: 9,    # Scorpio - Mars (traditional)
    9: 3,    # Sagittarius - Jupiter
    10: 8,   # Capricorn - Saturn
    11: 8,   # Aquarius - Saturn (traditional)
    12: 3,   # Pisces - Jupiter
}

# Exaltation signs for planets
EXALTATION_SIGNS: dict[int, int] = {
    1: 1,    # Sun in Aries
    2: 2,    # Moon in Taurus
    3: 4,    # Jupiter in Cancer
    4: 3,    # Rahu in Gemini (some traditions use Taurus)
    5: 6,    # Mercury in Virgo
    6: 12,   # Venus in Pisces
    7: 9,    # Ketu in Sagittarius (some traditions use Scorpio)
    8: 7,    # Saturn in Libra
    9: 10,   # Mars in Capricorn
}

# Debilitation signs for planets
DEBILITATION_SIGNS: dict[int, int] = {
    1: 7,    # Sun in Libra
    2: 8,    # Moon in Scorpio
    3: 10,   # Jupiter in Capricorn
    4: 9,    # Rahu in Sagittarius (some traditions use Scorpio)
    5: 12,   # Mercury in Pisces
    6: 6,    # Venus in Virgo
    7: 3,    # Ketu in Gemini (some traditions use Taurus)
    8: 1,    # Saturn in Aries
    9: 4,    # Mars in Cancer
}

# Moolatrikona signs and degree ranges
MOOLATRIKONA: dict[int, tuple[int, float, float]] = {
    1: (5, 0, 20),      # Sun: Leo 0-20°
    2: (2, 3, 30),      # Moon: Taurus 3-30°
    3: (9, 0, 10),      # Jupiter: Sagittarius 0-10°
    5: (6, 15, 20),     # Mercury: Virgo 15-20°
    6: (7, 0, 15),      # Venus: Libra 0-15°
    8: (11, 0, 20),     # Saturn: Aquarius 0-20°
    9: (1, 0, 12),      # Mars: Aries 0-12°
}

def calculate_compound_relationship(planet1: int, planet2: int,
                                   house_diff: int) -> str:
    """Calculate compound relationship between two planets.
    
    Args:
        planet1: First planet ID
        planet2: Second planet ID
        house_diff: House difference (1-12) from planet1 to planet2
        
    Returns:
        Relationship type: 'best_friend', 'friend', 'neutral', 'enemy', 'bitter_enemy'
    """
    # Natural relationship
    if planet2 in NATURAL_FRIENDS.get(planet1, set()):
        natural_rel = 1  # Friend
    elif planet2 in NATURAL_ENEMIES.get(planet1, set()):
        natural_rel = -1  # Enemy
    else:
        natural_rel = 0  # Neutral

    # Temporal relationship
    if house_diff in TEMPORAL_FRIEND_HOUSES:
        temporal_rel = 1  # Friend
    else:
        temporal_rel = -1  # Enemy

    # Compound relationship
    total = natural_rel + temporal_rel

    if total >= 2:
        return 'best_friend'
    elif total == 1:
        return 'friend'
    elif total == 0:
        return 'neutral'
    elif total == -1:
        return 'enemy'
    else:
        return 'bitter_enemy'
