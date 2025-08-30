"""
KP Type Definitions
Strict typing contracts for all KP operations
"""
from typing import Literal, TypedDict

# Planet codes - matches VedaCore's 9 Vedic planets only
Planet = Literal["SU", "MO", "MA", "ME", "JU", "VE", "SA", "RA", "KE"]

class Chain(TypedDict):
    """KP Chain (Nakshatra Lord, Sub Lord, Sub-Sub Lord)"""
    nl: Planet   # Nakshatra Lord (Star Lord)
    sl: Planet   # Sub Lord
    ssl: Planet  # Sub-Sub Lord

# Planet to integer mapping for NumPy optimization
PLANET_TO_INT = {
    "SU": 0,  # Sun
    "MO": 1,  # Moon
    "MA": 2,  # Mars
    "ME": 3,  # Mercury
    "JU": 4,  # Jupiter
    "VE": 5,  # Venus
    "SA": 6,  # Saturn
    "RA": 7,  # Rahu
    "KE": 8,  # Ketu
}

# Integer to planet mapping for NumPy optimization
INT_TO_PLANET = ["SU", "MO", "MA", "ME", "JU", "VE", "SA", "RA", "KE"]

# Weekday indexing: Monday=0, Tuesday=1, ..., Sunday=6
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Validate Planet codes match VedaCore constraints
assert len(PLANET_TO_INT) == 9, "Must have exactly 9 planets (Navagraha)"
assert set(PLANET_TO_INT.keys()) == {"SU", "MO", "MA", "ME", "JU", "VE", "SA", "RA", "KE"}, "Planet codes must match VedaCore standard"
assert len(INT_TO_PLANET) == 9, "INT_TO_PLANET must have 9 elements"
assert all(PLANET_TO_INT[p] == i for i, p in enumerate(INT_TO_PLANET)), "PLANET_TO_INT and INT_TO_PLANET must be consistent"
