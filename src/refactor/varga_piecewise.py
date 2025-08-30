"""
Piecewise varga calculations for unequal segment divisions.

This module handles divisional charts that don't follow equal segment patterns,
such as D30 Trimsamsa and special D2 Hora calculations.
"""

from numba import njit

from refactor.varga import _get_base_sign, _normalize_longitude

__all__ = [
    "calculate_hora",
    "calculate_special_d2",
    "calculate_trimsamsa",
    "register_piecewise_schemes",
]


# D30 Trimsamsa segment definitions
# Odd signs: Mars(5°), Saturn(5°), Jupiter(8°), Mercury(7°), Venus(5°)
# Even signs: Venus(5°), Mercury(7°), Jupiter(8°), Saturn(5°), Mars(5°)
TRIMSAMSA_ODD_SEGMENTS = [(5, 8), (5, 10), (8, 3), (7, 5), (5, 6)]  # (span, ruler_id)
TRIMSAMSA_EVEN_SEGMENTS = [(5, 6), (7, 5), (8, 3), (5, 10), (5, 8)]

# Sign mapping for Trimsamsa rulers
TRIMSAMSA_SIGN_MAP = {
    8: 0,  # Mars -> Aries
    10: 9,  # Saturn -> Capricorn
    3: 8,  # Jupiter -> Sagittarius
    5: 2,  # Mercury -> Gemini
    6: 1,  # Venus -> Taurus
}


@njit(cache=True)
def _get_trimsamsa_segment(within_sign: float, is_odd: bool) -> int:
    """Determine which Trimsamsa segment a degree falls into.

    Args:
        within_sign: Degrees within the sign (0-30)
        is_odd: True if odd sign, False if even

    Returns:
        Trimsamsa sign index (0-11)
    """
    cumulative = 0.0

    if is_odd:
        # Odd signs: Mars, Saturn, Jupiter, Mercury, Venus
        if within_sign < 5.0:
            return 0  # Mars -> Aries
        elif within_sign < 10.0:
            return 9  # Saturn -> Capricorn
        elif within_sign < 18.0:
            return 8  # Jupiter -> Sagittarius
        elif within_sign < 25.0:
            return 2  # Mercury -> Gemini
        else:
            return 1  # Venus -> Taurus
    else:
        # Even signs: Venus, Mercury, Jupiter, Saturn, Mars
        if within_sign < 5.0:
            return 1  # Venus -> Taurus
        elif within_sign < 12.0:
            return 2  # Mercury -> Gemini
        elif within_sign < 20.0:
            return 8  # Jupiter -> Sagittarius
        elif within_sign < 25.0:
            return 9  # Saturn -> Capricorn
        else:
            return 0  # Mars -> Aries


def calculate_trimsamsa(longitude: float) -> int:
    """Calculate D30 Trimsamsa with unequal segments.

    Trimsamsa uses unequal divisions based on planetary rulerships:
    - Odd signs: Mars(5°), Saturn(5°), Jupiter(8°), Mercury(7°), Venus(5°)
    - Even signs: Venus(5°), Mercury(7°), Jupiter(8°), Saturn(5°), Mars(5°)

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Trimsamsa sign index (0-11)
    """
    lon = _normalize_longitude(longitude)
    base_sign = _get_base_sign(lon)
    within_sign = lon % 30.0

    # Determine if odd or even sign
    is_odd = base_sign % 2 == 0  # Aries(0) is odd, Taurus(1) is even

    return _get_trimsamsa_segment(within_sign, is_odd)


@njit(cache=True)
def _calculate_hora_classical(longitude: float) -> int:
    """Calculate D2 Hora using Sun/Moon alternation rule.

    Classical Hora divides each sign into two 15° halves:
    - First half (0-15°): Sun's hora for odd signs, Moon's for even
    - Second half (15-30°): Moon's hora for odd signs, Sun's for even

    Returns Cancer (3) for Moon hora, Leo (4) for Sun hora.

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Hora sign: 3 (Cancer/Moon) or 4 (Leo/Sun)
    """
    lon = _normalize_longitude(longitude)
    base_sign = _get_base_sign(lon)
    within_sign = lon % 30.0

    is_odd = base_sign % 2 == 0  # Aries(0) is odd
    is_first_half = within_sign < 15.0

    # Logic for Sun/Moon hora
    if is_odd:
        # Odd sign: First half = Sun, Second half = Moon
        return 4 if is_first_half else 3
    else:
        # Even sign: First half = Moon, Second half = Sun
        return 3 if is_first_half else 4


def calculate_hora(longitude: float) -> int:
    """Calculate D2 Hora divisional chart.

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Hora sign index (3=Cancer/Moon or 4=Leo/Sun)
    """
    return _calculate_hora_classical(longitude)


def calculate_special_d2(longitude: float, variant: str = "classical") -> int:
    """Calculate D2 with different variants.

    Args:
        longitude: Ecliptic longitude in degrees
        variant: "classical" for Sun/Moon, "equal" for standard division

    Returns:
        D2 sign index
    """
    if variant == "classical":
        return _calculate_hora_classical(longitude)
    else:
        # Equal division D2 (standard linear)
        from refactor.varga import _linear_varga

        return _linear_varga(longitude, 2)


# Additional piecewise vargas


@njit(cache=True)
def _calculate_saptamsa(longitude: float) -> int:
    """Calculate D7 Saptamsa for children/progeny.

    - Odd signs: Count from same sign
    - Even signs: Count from 7th sign

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Saptamsa sign index (0-11)
    """
    lon = _normalize_longitude(longitude)
    base_sign = _get_base_sign(lon)
    within_sign = lon % 30.0

    # Calculate pada (7 equal divisions)
    pada = int(within_sign * 7.0 / 30.0)
    if pada >= 7:
        pada = 6

    # Starting point based on odd/even
    is_odd = base_sign % 2 == 0
    start_sign = base_sign if is_odd else (base_sign + 6) % 12

    return (start_sign + pada) % 12


def calculate_saptamsa(longitude: float) -> int:
    """Calculate D7 Saptamsa divisional chart.

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Saptamsa sign index (0-11)
    """
    return _calculate_saptamsa(longitude)


def register_piecewise_schemes():
    """Register all piecewise varga schemes with the main registry."""
    from refactor.varga import register_scheme

    # D30 Trimsamsa
    def trimsamsa_wrapper(longitude: float, divisor: int) -> int:
        if divisor != 30:
            from refactor.varga import _linear_varga

            return _linear_varga(longitude, divisor)
        return calculate_trimsamsa(longitude)

    register_scheme("trimsamsa_classical", trimsamsa_wrapper)

    # D2 Hora
    def hora_wrapper(longitude: float, divisor: int) -> int:
        if divisor != 2:
            from refactor.varga import _linear_varga

            return _linear_varga(longitude, divisor)
        return calculate_hora(longitude)

    register_scheme("hora_classical", hora_wrapper)

    # D7 Saptamsa
    def saptamsa_wrapper(longitude: float, divisor: int) -> int:
        if divisor != 7:
            from refactor.varga import _linear_varga

            return _linear_varga(longitude, divisor)
        return calculate_saptamsa(longitude)

    register_scheme("saptamsa_classical", saptamsa_wrapper)


# Additional unequal vargas can be added here:
# - D16 Shodasamsa (happiness from vehicles)
# - D20 Vimsamsa (spiritual progress)
# - D24 Chaturvimsamsa (education/learning)
# - D27 Nakshatramsa/Bhamsa (strengths/weaknesses)
# - D40 Khavedamsa (maternal lineage)
# - D45 Akshavedamsa (paternal lineage)
# - D60 Shashtyamsa (past karma)

# Each would need their specific piecewise rules based on classical texts
