"""
Varga (Divisional Charts) calculation system for VedaCore.

This module provides flexible divisional chart calculations supporting:
- Equal segment divisions (linear)
- Classical schemes (Navamsa D9, Dasamsa D10)
- Custom offset-based schemes
- High-performance batch processing with Numba JIT

All calculations are pure mathematical operations without ephemeris dependencies,
making them suitable for high-frequency trading applications.
"""

from __future__ import annotations

import logging

from collections.abc import Callable, Iterable

from numba import njit

__all__ = [
    "detect_vargottama",
    "get_varga_strength",
    "list_schemes",
    "make_custom_offsets_scheme",
    "register_scheme",
    "varga_pada",
    "varga_sign",
    "varga_sign_batch",
]

logger = logging.getLogger(__name__)

# Type aliases
SchemeFn = Callable[[float, int], int]

# Global scheme registry
_SCHEMES: dict[str, SchemeFn] = {}


@njit(cache=True)
def _normalize_longitude(longitude: float) -> float:
    """Normalize longitude to [0, 360) range.

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Normalized longitude in [0, 360) range
    """
    lon = longitude % 360.0
    return lon if lon >= 0.0 else lon + 360.0


@njit(cache=True)
def _get_segment_size(divisor: int) -> float:
    """Calculate segment size for equal division.

    Args:
        divisor: Number of divisions (1-300)

    Returns:
        Size of each segment in degrees

    Raises:
        ValueError: If divisor is out of valid range
    """
    if not (1 <= divisor <= 300):
        raise ValueError(f"Divisor must be between 1 and 300, got {divisor}")
    return 30.0 / float(divisor)


@njit(cache=True)
def _calculate_pada(longitude: float, divisor: int) -> int:
    """Calculate pada (segment) index within a sign.

    Args:
        longitude: Ecliptic longitude in degrees
        divisor: Number of divisions

    Returns:
        Pada index (0 to divisor-1)
    """
    lon = _normalize_longitude(longitude)
    within_sign = lon % 30.0
    segment_size = _get_segment_size(divisor)
    pada_idx = int(within_sign // segment_size)

    # Clamp to valid range (handles edge case at 30.0)
    if pada_idx >= divisor:
        pada_idx = divisor - 1

    return pada_idx


@njit(cache=True)
def _get_base_sign(longitude: float) -> int:
    """Get the base sign (D1 rasi) for a longitude.

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Sign index (0=Aries to 11=Pisces)
    """
    lon = _normalize_longitude(longitude)
    return int(lon // 30.0)


@njit(cache=True)
def _linear_varga(longitude: float, divisor: int) -> int:
    """Calculate varga sign using linear (equal segment) method.

    This is the baseline method that works for any divisor.
    Formula: (base_sign * divisor + pada) % 12

    Args:
        longitude: Ecliptic longitude in degrees
        divisor: Number of divisions

    Returns:
        Varga sign index (0-11)
    """
    base_sign = _get_base_sign(longitude)
    pada = _calculate_pada(longitude, divisor)
    return (base_sign * divisor + pada) % 12


@njit(cache=True)
def _get_modality(sign_idx: int) -> int:
    """Get modality of a sign.

    Args:
        sign_idx: Sign index (0-11)

    Returns:
        0=Movable, 1=Fixed, 2=Dual
    """
    # Movable: Aries(0), Cancer(3), Libra(6), Capricorn(9)
    # Fixed: Taurus(1), Leo(4), Scorpio(7), Aquarius(10)
    # Dual: Gemini(2), Virgo(5), Sagittarius(8), Pisces(11)
    return sign_idx % 3


@njit(cache=True)
def _navamsa_classical(longitude: float) -> int:
    """Calculate D9 Navamsa using classical rules.

    Starting sign depends on modality:
    - Movable signs: Start at same sign (+0)
    - Fixed signs: Start at 9th from sign (+8)
    - Dual signs: Start at 5th from sign (+4)

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Navamsa sign index (0-11)
    """
    base_sign = _get_base_sign(longitude)
    pada = _calculate_pada(longitude, 9)
    modality = _get_modality(base_sign)

    # Offset based on modality
    if modality == 0:  # Movable
        offset = 0
    elif modality == 1:  # Fixed
        offset = 8
    else:  # Dual
        offset = 4

    start_sign = (base_sign + offset) % 12
    return (start_sign + pada) % 12


@njit(cache=True)
def _dasamsa_classical(longitude: float) -> int:
    """Calculate D10 Dasamsa using classical rules.

    Starting sign depends on sign parity:
    - Odd signs: Start at same sign (+0)
    - Even signs: Start at 9th from sign (+8)

    Args:
        longitude: Ecliptic longitude in degrees

    Returns:
        Dasamsa sign index (0-11)
    """
    base_sign = _get_base_sign(longitude)
    pada = _calculate_pada(longitude, 10)

    # Offset based on parity
    offset = 0 if base_sign % 2 == 0 else 8

    start_sign = (base_sign + offset) % 12
    return (start_sign + pada) % 12


# Wrapper functions for scheme registry (non-JIT)


def _navamsa_wrapper(longitude: float, divisor: int) -> int:
    """Wrapper for navamsa classical calculation."""
    if divisor != 9:
        return _linear_varga(longitude, divisor)
    return _navamsa_classical(longitude)


def _dasamsa_wrapper(longitude: float, divisor: int) -> int:
    """Wrapper for dasamsa classical calculation."""
    if divisor != 10:
        return _linear_varga(longitude, divisor)
    return _dasamsa_classical(longitude)


def register_scheme(name: str, fn: SchemeFn) -> None:
    """Register a varga calculation scheme.

    Args:
        name: Scheme identifier
        fn: Function that takes (longitude, divisor) and returns sign index

    Raises:
        ValueError: If name is empty or fn is not callable
    """
    if not name:
        raise ValueError("Scheme name cannot be empty")
    if not callable(fn):
        raise ValueError("Scheme function must be callable")

    _SCHEMES[name] = fn
    logger.debug(f"Registered varga scheme: {name}")


def list_schemes() -> list[str]:
    """Get list of available varga schemes.

    Returns:
        Sorted list of scheme names
    """
    return sorted(_SCHEMES.keys())


def make_custom_offsets_scheme(offsets: dict[int, int], name: str) -> None:
    """Create a custom varga scheme with per-sign offsets.

    Args:
        offsets: Dictionary mapping sign index (0-11) to offset value
        name: Name for the custom scheme

    Example:
        # Create scheme where all signs start 4 signs ahead
        make_custom_offsets_scheme({i: 4 for i in range(12)}, "custom_plus4")
    """
    # Create offset table with defaults
    offset_table = {i: offsets.get(i, 0) % 12 for i in range(12)}

    def custom_fn(longitude: float, divisor: int) -> int:
        """Custom offset-based varga calculation."""
        base_sign = _get_base_sign(longitude)
        pada = _calculate_pada(longitude, divisor)
        start_sign = (base_sign + offset_table[base_sign]) % 12
        return (start_sign + pada) % 12

    register_scheme(name, custom_fn)


def varga_pada(longitude: float, divisor: int) -> int:
    """Get the pada (segment) index within a sign.

    Args:
        longitude: Ecliptic longitude in degrees
        divisor: Number of divisions

    Returns:
        Pada index (0 to divisor-1)
    """
    return _calculate_pada(longitude, divisor)


def varga_sign(longitude: float, divisor: int, scheme: str = "linear") -> int:
    """Calculate varga sign for a given longitude.

    Args:
        longitude: Ecliptic longitude in degrees
        divisor: Number of divisions (1-300, where 1 = D1 Rasi chart)
        scheme: Calculation scheme to use

    Returns:
        Varga sign index (0=Aries to 11=Pisces)

    Raises:
        KeyError: If scheme is not registered
    """
    import time

    # Special case for D1 (Rasi chart)
    if divisor == 1:
        # D1 is just the base sign itself
        return _get_base_sign(longitude)

    fn = _SCHEMES.get(scheme)
    if fn is None:
        available = list_schemes()
        raise KeyError(f"Unknown varga scheme: {scheme}. Available: {available}")

    # Track timing if monitoring is available
    try:
        from refactor.monitoring import track_varga_calculation

        start = time.perf_counter()
        result = fn(longitude, divisor)
        duration = time.perf_counter() - start
        track_varga_calculation(divisor, scheme, duration)
        return result
    except ImportError:
        # Monitoring not available, just calculate
        return fn(longitude, divisor)


def varga_sign_batch(
    longitudes: Iterable[float], divisor: int, scheme: str = "linear"
) -> list[int]:
    """Calculate varga signs for multiple longitudes.

    Args:
        longitudes: Iterable of ecliptic longitudes
        divisor: Number of divisions
        scheme: Calculation scheme to use

    Returns:
        List of varga sign indices
    """
    fn = _SCHEMES.get(scheme)
    if fn is None:
        available = list_schemes()
        raise KeyError(f"Unknown varga scheme: {scheme}. Available: {available}")

    return [fn(lon, divisor) for lon in longitudes]


@njit(cache=True)
def _is_vargottama_single(d1_sign: int, varga_sign: int) -> bool:
    """Check if a planet is vargottama (same sign in D1 and varga).

    Args:
        d1_sign: Sign in D1 (rasi chart)
        varga_sign: Sign in divisional chart

    Returns:
        True if signs match (vargottama)
    """
    return d1_sign == varga_sign


def detect_vargottama(
    longitudes: dict[int, float], check_vargas: list[int] = None
) -> dict[int, dict[str, bool]]:
    """Detect vargottama status for planets across multiple vargas.

    A planet is vargottama when it occupies the same sign in D1 (rasi)
    and a divisional chart. This strengthens the planet's significations.

    Args:
        longitudes: Dictionary of planet_id -> longitude
        check_vargas: List of divisors to check (default: [9])

    Returns:
        Dictionary of planet_id -> {f"D{divisor}": bool}

    Example:
        >>> detect_vargottama({1: 45.5, 2: 123.4}, [9, 10])
        {1: {"D9": True, "D10": False}, 2: {"D9": False, "D10": True}}
    """
    if check_vargas is None:
        check_vargas = [9]  # Default to D9 (Navamsa)

    results = {}

    for planet_id, longitude in longitudes.items():
        d1_sign = _get_base_sign(longitude)
        planet_results = {}

        for divisor in check_vargas:
            # Select appropriate scheme
            if divisor == 1:
                # D1 is always the same as base sign (always vargottama with itself)
                varga_sign = d1_sign
            elif divisor == 9 and "navamsa_classical" in _SCHEMES:
                varga_sign = _navamsa_classical(longitude)
            elif divisor == 10 and "dasamsa_classical" in _SCHEMES:
                varga_sign = _dasamsa_classical(longitude)
            else:
                varga_sign = _linear_varga(longitude, divisor)

            planet_results[f"D{divisor}"] = _is_vargottama_single(d1_sign, varga_sign)

        results[planet_id] = planet_results

    return results


def get_varga_strength(
    longitudes: dict[int, float],
    check_vargas: list[int] = None,
    weights: dict[int, float] = None,
) -> dict[int, float]:
    """Calculate varga-based strength for planets.

    Strength increases when a planet is vargottama in multiple charts.
    Can be used as input for Vimshopaka Bala calculations.

    Args:
        longitudes: Dictionary of planet_id -> longitude
        check_vargas: List of divisors to check
        weights: Optional weights for each varga (default: equal)

    Returns:
        Dictionary of planet_id -> strength (0-100 scale)
    """
    if check_vargas is None:
        check_vargas = [9, 10, 12, 30]  # Common important vargas

    if weights is None:
        weights = {d: 1.0 for d in check_vargas}

    # Normalize weights
    total_weight = sum(weights.values())
    norm_weights = {d: w / total_weight for d, w in weights.items()}

    vargottama_results = detect_vargottama(longitudes, check_vargas)
    strength_scores = {}

    for planet_id in longitudes:
        score = 0.0
        for divisor in check_vargas:
            varga_key = f"D{divisor}"
            if vargottama_results[planet_id].get(varga_key, False):
                score += norm_weights.get(divisor, 0.0)

        # Convert to 0-100 scale
        strength_scores[planet_id] = score * 100.0

    return strength_scores


# Register default schemes
register_scheme("linear", _linear_varga)
register_scheme("navamsa_classical", _navamsa_wrapper)
register_scheme("dasamsa_classical", _dasamsa_wrapper)


# Initialize common custom schemes
def _initialize_common_schemes():
    """Initialize commonly used classical varga schemes."""

    # D3 Drekkana - Trinal distribution
    make_custom_offsets_scheme(
        {
            0: 0,
            1: 4,
            2: 8,  # Fire signs
            3: 0,
            4: 4,
            5: 8,  # Water signs
            6: 0,
            7: 4,
            8: 8,  # Air signs
            9: 0,
            10: 4,
            11: 8,  # Earth signs
        },
        "drekkana_classical",
    )

    # D12 Dwadasamsa - Sequential from same sign
    make_custom_offsets_scheme({i: 0 for i in range(12)}, "dwadasamsa_classical")

    logger.info("Initialized common varga schemes")


# Initialize on module load
_initialize_common_schemes()
