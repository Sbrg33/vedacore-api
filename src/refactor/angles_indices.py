#!/usr/bin/env python3
"""
Angle and index calculations for zodiac signs, nakshatras, and padas
Extracted from master_ephe for clean separation of concerns
"""


from .constants import (
    BOUNDARY_EPSILON,
    NAKSHATRA_NAMES,
    NAKSHATRA_SPAN,
    PADA_SPAN,
    SIGN_NAMES,
)
from .numerics import clamp_value, normalize_angle

# ============================================================================
# ZODIAC SIGN CALCULATIONS
# ============================================================================


def sign_index(longitude: float) -> int:
    """Get zodiac sign index (0-11) from longitude

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Sign index (0=Aries, 11=Pisces)
    """
    longitude = normalize_angle(longitude)
    return int(longitude // 30.0)


def sign_number(longitude: float) -> int:
    """Get zodiac sign number (1-12) from longitude

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Sign number (1=Aries, 12=Pisces)
    """
    return sign_index(longitude) + 1


def deg_in_sign(longitude: float) -> float:
    """Get degrees within current zodiac sign

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Degrees within sign (0-30)
    """
    longitude = normalize_angle(longitude)
    return longitude % 30.0


def sign_name(longitude: float) -> str:
    """Get zodiac sign name from longitude

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Sign name (e.g., "Aries", "Taurus")
    """
    sign_num = sign_number(longitude)
    return SIGN_NAMES.get(sign_num, f"Sign_{sign_num}")


# ============================================================================
# NAKSHATRA CALCULATIONS
# ============================================================================


def nakshatra_index(longitude: float) -> int:
    """Get nakshatra index (0-26) from longitude

    Handles boundary cases with epsilon tolerance.

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Nakshatra index (0=Ashwini, 26=Revati)
    """
    longitude = normalize_angle(longitude)

    # Handle edge case at zodiac boundary
    if longitude >= 359.999999:
        return 26

    nak_idx = int(longitude / NAKSHATRA_SPAN)

    # Check for boundary proximity
    next_boundary = (nak_idx + 1) * NAKSHATRA_SPAN
    if next_boundary - longitude < BOUNDARY_EPSILON * 10:
        nak_idx += 1

    return int(clamp_value(nak_idx, 0, 26))


def nakshatra_number(longitude: float) -> int:
    """Get nakshatra number (1-27) from longitude

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Nakshatra number (1=Ashwini, 27=Revati)
    """
    return nakshatra_index(longitude) + 1


def nakshatra_name(longitude: float) -> str:
    """Get nakshatra name from longitude

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Nakshatra name (e.g., "Ashwini", "Bharani")
    """
    nak_num = nakshatra_number(longitude)
    return NAKSHATRA_NAMES.get(nak_num, f"Nakshatra_{nak_num}")


def deg_in_nakshatra(longitude: float) -> float:
    """Get degrees within current nakshatra

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Degrees within nakshatra (0-13.333...)
    """
    longitude = normalize_angle(longitude)
    nak_idx = nakshatra_index(longitude)
    nak_start = nak_idx * NAKSHATRA_SPAN
    deg_within = longitude - nak_start

    if deg_within < 0:
        deg_within = 0
    elif deg_within > NAKSHATRA_SPAN:
        deg_within = NAKSHATRA_SPAN

    return deg_within


# ============================================================================
# PADA CALCULATIONS
# ============================================================================


def pada_index(longitude: float) -> int:
    """Get pada index (0-3) within current nakshatra

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Pada index within nakshatra (0-3)
    """
    deg_within = deg_in_nakshatra(longitude)

    # Handle boundary at exactly 10.0 degrees (pada 3/4 boundary)
    if abs(deg_within - 10.0) < BOUNDARY_EPSILON:
        return 2  # Pada 3 (0-indexed)

    pada_idx = int(deg_within / PADA_SPAN)
    return min(pada_idx, 3)


def pada_number(longitude: float) -> int:
    """Get pada number (1-4) within current nakshatra

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Pada number within nakshatra (1-4)
    """
    return pada_index(longitude) + 1


def find_nakshatra_pada(longitude: float) -> tuple[int, int]:
    """Find nakshatra number (1-27) and pada (1-4)

    This matches the signature from master_ephe/lib/kp_system.py

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Tuple of (nakshatra_number, pada_number)
    """
    nak_num = nakshatra_number(longitude)
    pada_num = pada_number(longitude)
    return nak_num, pada_num


# ============================================================================
# NAVAMSA CALCULATIONS
# ============================================================================


def navamsa_sign(longitude: float) -> int:
    """Calculate Navamsa (D9) sign

    Navamsa is the 9th divisional chart, dividing each sign into 9 parts.

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Navamsa sign number (1-12)
    """
    longitude = normalize_angle(longitude)

    # Each pada corresponds to one navamsa
    # Total 108 padas (27 nakshatras * 4 padas)
    # Which cycle through 12 signs 9 times

    total_padas = int(longitude / PADA_SPAN)
    navamsa_sign_idx = total_padas % 12

    return navamsa_sign_idx + 1


# ============================================================================
# DEEP POSITION CALCULATIONS
# ============================================================================


def deep_abs_deg(longitude: float, nakshatra: int = None, pada: int = None) -> float:
    """Calculate deep absolute degrees including nakshatra and pada

    This is used for fine-grained position calculations.

    Args:
        longitude: Ecliptic longitude in degrees
        nakshatra: Nakshatra number (1-27), auto-calculated if None
        pada: Pada number (1-4), auto-calculated if None

    Returns:
        Deep absolute degrees
    """
    longitude = normalize_angle(longitude)

    if nakshatra is None:
        nakshatra = nakshatra_number(longitude)
    if pada is None:
        pada = pada_number(longitude)

    # Base calculation
    base_deg = longitude

    # Add nakshatra weight (optional enhancement)
    nak_weight = (nakshatra - 1) * 0.01  # Small weight for differentiation

    # Add pada weight (optional enhancement)
    pada_weight = (pada - 1) * 0.001  # Smaller weight for pada

    return base_deg + nak_weight + pada_weight


# ============================================================================
# BOUNDARY DETECTION
# ============================================================================


def is_near_sign_boundary(longitude: float, tolerance: float = 0.1) -> bool:
    """Check if longitude is near a sign boundary

    Args:
        longitude: Ecliptic longitude in degrees
        tolerance: Degrees of tolerance for boundary

    Returns:
        True if within tolerance of a sign boundary
    """
    deg_in_s = deg_in_sign(longitude)
    return deg_in_s < tolerance or deg_in_s > (30.0 - tolerance)


def is_near_nakshatra_boundary(longitude: float, tolerance: float = 0.01) -> bool:
    """Check if longitude is near a nakshatra boundary

    Args:
        longitude: Ecliptic longitude in degrees
        tolerance: Degrees of tolerance for boundary

    Returns:
        True if within tolerance of a nakshatra boundary
    """
    deg_in_n = deg_in_nakshatra(longitude)
    return deg_in_n < tolerance or deg_in_n > (NAKSHATRA_SPAN - tolerance)


def is_near_pada_boundary(longitude: float, tolerance: float = 0.001) -> bool:
    """Check if longitude is near a pada boundary

    Args:
        longitude: Ecliptic longitude in degrees
        tolerance: Degrees of tolerance for boundary

    Returns:
        True if within tolerance of a pada boundary
    """
    deg_in_n = deg_in_nakshatra(longitude)
    pada_position = deg_in_n % PADA_SPAN
    return pada_position < tolerance or pada_position > (PADA_SPAN - tolerance)


# ============================================================================
# PROGRESSION CALCULATIONS
# ============================================================================


def next_sign_boundary(longitude: float) -> float:
    """Calculate distance to next sign boundary

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Degrees until next sign boundary
    """
    deg_in_s = deg_in_sign(longitude)
    return 30.0 - deg_in_s


def next_nakshatra_boundary(longitude: float) -> float:
    """Calculate distance to next nakshatra boundary

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Degrees until next nakshatra boundary
    """
    deg_in_n = deg_in_nakshatra(longitude)
    return NAKSHATRA_SPAN - deg_in_n


def next_pada_boundary(longitude: float) -> float:
    """Calculate distance to next pada boundary

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Degrees until next pada boundary
    """
    deg_in_n = deg_in_nakshatra(longitude)
    pada_position = deg_in_n % PADA_SPAN
    return PADA_SPAN - pada_position
