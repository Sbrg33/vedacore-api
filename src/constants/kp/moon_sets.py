"""
KP Moon-Ruled Horary Numbers
Sets of horary numbers where Moon has influence - used for timing boosts
"""

# Moon-ruled Horary Numbers (1-249 system) - where Moon is the star lord or sub-lord
MOON_RULED_HORARY = {
    2, 11, 20, 29, 38, 47, 56, 65, 74,          # First set
    83, 92, 101, 110, 119, 128, 137, 146, 155, # Second set
    164, 173, 182, 191, 200, 209, 218, 227, 236, 245  # Third set
}

# Extended Moon influence (Moon as star or sub in the chain) - includes Moon-ruled plus influenced
MOON_INFLUENCED_HORARY = MOON_RULED_HORARY | {
    3, 12, 21, 30, 39, 48, 57, 66, 75,          # Moon as sub-sub
    84, 93, 102, 111, 120, 129, 138, 147, 156,
    165, 174, 183, 192, 201, 210, 219, 228, 237, 246
}

def is_moon_ruled(horary_num: int) -> bool:
    """Check if a horary number is Moon-ruled (strong Moon influence)"""
    return horary_num in MOON_RULED_HORARY

def is_moon_influenced(horary_num: int) -> bool:
    """Check if a horary number has Moon influence (including extended set)"""
    return horary_num in MOON_INFLUENCED_HORARY

def get_moon_boost_factor(horary_num: int, base_boost: float = 0.15) -> float:
    """Get Moon boost factor for a horary number"""
    if is_moon_ruled(horary_num):
        return base_boost  # Full boost for Moon-ruled
    elif is_moon_influenced(horary_num):
        return base_boost * 0.7  # Partial boost for Moon-influenced
    else:
        return 0.0  # No boost

# Validation
assert len(MOON_RULED_HORARY) == 24, f"Expected 24 Moon-ruled numbers, got {len(MOON_RULED_HORARY)}"
assert len(MOON_INFLUENCED_HORARY) == 48, f"Expected 48 Moon-influenced numbers, got {len(MOON_INFLUENCED_HORARY)}"
assert MOON_RULED_HORARY.issubset(MOON_INFLUENCED_HORARY), "Moon-ruled must be subset of Moon-influenced"
assert all(1 <= num <= 249 for num in MOON_INFLUENCED_HORARY), "All numbers must be in range 1-249"

# Export statistics
MOON_SETS_STATS = {
    "moon_ruled_count": len(MOON_RULED_HORARY),
    "moon_influenced_count": len(MOON_INFLUENCED_HORARY),
    "coverage_percent": round(len(MOON_INFLUENCED_HORARY) / 249 * 100, 1)
}
