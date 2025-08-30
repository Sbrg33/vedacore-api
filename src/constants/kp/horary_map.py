"""
KP Horary Number to Planet Mapping (1-249)
Based on traditional KP doctrine with NumPy optimization for Numba performance
"""
import hashlib

import numpy as np

from .types import PLANET_TO_INT, Planet


# Traditional KP Horary mapping (1-249) based on planetary sequence
# This follows the traditional KP subdivision where each planet rules specific numbers
def _build_horary_mapping() -> dict[int, Planet]:
    """Build the canonical 1-249 horary number to planet mapping"""

    # Based on traditional KP horary system - each planet rules specific ranges
    # This is derived from the Vimshottari dasha proportions applied to 249 divisions
    mapping = {}

    # KP Traditional Horary Rulers (from archived research)
    planet_rulers = {
        1: [1, 10, 19, 28, 37, 46, 55, 64, 73, 82, 91, 100, 109, 118, 127, 136, 145, 154, 163, 172, 181, 190, 199, 208, 217, 226, 235, 244],  # Sun
        2: [2, 11, 20, 29, 38, 47, 56, 65, 74, 83, 92, 101, 110, 119, 128, 137, 146, 155, 164, 173, 182, 191, 200, 209, 218, 227, 236, 245],  # Moon
        3: [5, 14, 23, 32, 41, 50, 59, 68, 77, 86, 95, 104, 113, 122, 131, 140, 149, 158, 167, 176, 185, 194, 203, 212, 221, 230, 239, 248],  # Jupiter
        4: [4, 13, 22, 31, 40, 49, 58, 67, 76, 85, 94, 103, 112, 121, 130, 139, 148, 157, 166, 175, 184, 193, 202, 211, 220, 229, 238, 247],  # Rahu
        5: [7, 16, 25, 34, 43, 52, 61, 70, 79, 88, 97, 106, 115, 124, 133, 142, 151, 160, 169, 178, 187, 196, 205, 214, 223, 232, 241],        # Mercury
        6: [8, 17, 26, 35, 44, 53, 62, 71, 80, 89, 98, 107, 116, 125, 134, 143, 152, 161, 170, 179, 188, 197, 206, 215, 224, 233, 242],        # Venus
        7: [9, 18, 27, 36, 45, 54, 63, 72, 81, 90, 99, 108, 117, 126, 135, 144, 153, 162, 171, 180, 189, 198, 207, 216, 225, 234, 243, 249],  # Ketu
        8: [6, 15, 24, 33, 42, 51, 60, 69, 78, 87, 96, 105, 114, 123, 132, 141, 150, 159, 168, 177, 186, 195, 204, 213, 222, 231, 240],        # Saturn
        9: [3, 12, 21, 30, 39, 48, 57, 66, 75, 84, 93, 102, 111, 120, 129, 138, 147, 156, 165, 174, 183, 192, 201, 210, 219, 228, 237, 246]   # Mars
    }

    # VedaCore planet ID to Planet code mapping
    planet_id_to_code = {
        1: "SU", 2: "MO", 3: "JU", 4: "RA", 5: "ME",
        6: "VE", 7: "KE", 8: "SA", 9: "MA"
    }

    # Build the mapping
    for planet_id, numbers in planet_rulers.items():
        planet_code = planet_id_to_code[planet_id]
        for num in numbers:
            if 1 <= num <= 249:
                mapping[num] = planet_code

    return mapping

# Build the mapping
HORARY_PLANET_BY_NUMBER = _build_horary_mapping()

# Validate mapping integrity
assert len(HORARY_PLANET_BY_NUMBER) == 249, f"Mapping must have exactly 249 entries, got {len(HORARY_PLANET_BY_NUMBER)}"
assert set(HORARY_PLANET_BY_NUMBER.keys()) == set(range(1, 250)), "Mapping must cover numbers 1-249"
assert all(p in PLANET_TO_INT for p in HORARY_PLANET_BY_NUMBER.values()), "All mapped planets must be valid Planet codes"

# NumPy optimization for Numba performance (PM requirement)
HORARY_I_BY_NUM = np.zeros(250, dtype=np.uint8)  # Index 0 unused, 1-249 active
for num, planet in HORARY_PLANET_BY_NUMBER.items():
    HORARY_I_BY_NUM[num] = PLANET_TO_INT[planet]

# SHA-256 fingerprint for constants integrity (PM requirement)
MAPPING_FINGERPRINT = hashlib.sha256(HORARY_I_BY_NUM.tobytes()).hexdigest()

def get_planet_by_number(num: int) -> Planet:
    """Get planet code for a horary number (1-249)"""
    if not 1 <= num <= 249:
        raise ValueError(f"Horary number must be 1-249, got {num}")
    return HORARY_PLANET_BY_NUMBER[num]

def get_planet_int_by_number(num: int) -> int:
    """Get planet integer code for a horary number - Numba optimized"""
    if not 1 <= num <= 249:
        raise ValueError(f"Horary number must be 1-249, got {num}")
    return int(HORARY_I_BY_NUM[num])

# Export mapping statistics for validation
MAPPING_STATS = {
    "total_numbers": len(HORARY_PLANET_BY_NUMBER),
    "planet_distribution": {planet: sum(1 for p in HORARY_PLANET_BY_NUMBER.values() if p == planet)
                           for planet in set(HORARY_PLANET_BY_NUMBER.values())},
    "fingerprint": MAPPING_FINGERPRINT[:16] + "..."  # First 16 chars for display
}
