"""Lightweight helpers for VedaCore Location Features.

Functions provided:
- wrap_deg(x): wrap an angle to [0, 360)
- min_arc(a, b): shortest arc distance between angles a and b, in [0, 180]
- house_class(h): return 'angular' | 'succedent' | 'cadent' for house number 1..12
- aspect_orb(aspect): return configured orb (deg) for an aspect name
- angular_load(dist_to_angles, house_num, cusp_dist_deg, ...): compute per-planet score in [0,1]

These helpers are dependency-light and safe to use in tight loops.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import fmod

# Import centralized constants. If you need to tune behavior, change constants only.
from constants.location_features import (
    ANGLE_PROX_THRESHOLD_DEG,
    ASPECT_ORBS_DEG,
    CUSP_PENALTY_WEIGHT,
    CUSP_PENALTY_WINDOW_DEG,
    HOUSE_WEIGHTS,
)

__all__ = [
    "angular_load",
    "aspect_orb",
    "house_class",
    "min_arc",
    "wrap_deg",
]


def wrap_deg(x: float) -> float:
    """Wrap an angle to [0, 360).

    Examples:
        >>> wrap_deg(370.0)
        10.0
        >>> wrap_deg(-30.0)
        330.0
    """
    # Python's modulo for negatives is fine; fmod ensures float semantics.
    # ((x % 360) + 360) % 360 pattern also works; choose clarity.
    w = fmod(x, 360.0)
    if w < 0.0:
        w += 360.0
    return 0.0 if w == 360.0 else w


def min_arc(a: float, b: float) -> float:
    """Return the shortest arc distance between angles a and b (degrees).

    Result is in [0, 180]. Inputs can be any real numbers (will be wrapped).
    """
    da = abs(wrap_deg(a) - wrap_deg(b))
    if da > 180.0:
        da = 360.0 - da
    return da


def house_class(house_num: int) -> str:
    """Classify a house number into 'angular' | 'succedent' | 'cadent'.

    Accepts any integer; values are normalized to 1..12 with 0 -> 12.
    """
    h = house_num % 12
    if h == 0:
        h = 12
    if h in (1, 4, 7, 10):
        return "angular"
    if h in (2, 5, 8, 11):
        return "succedent"
    return "cadent"  # 3,6,9,12


def aspect_orb(aspect: str, *, overrides: Mapping[str, float] | None = None) -> float:
    """Return the configured maximum orb (degrees) for an aspect.

    Unknown aspect names raise KeyError to surface config mistakes early.
    You can pass 'overrides' to supply a different orb map for a single call.
    """
    table = overrides if overrides is not None else ASPECT_ORBS_DEG
    if aspect not in table:
        raise KeyError(f"Unknown aspect '{aspect}'. Known: {sorted(table.keys())}")
    return float(table[aspect])


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def angular_load(
    dist_to_angles: Mapping[str, float],
    house_num: int,
    cusp_dist_deg: float,
    *,
    angle_prox_threshold_deg: float | None = None,
    cusp_penalty_window_deg: float | None = None,
    house_weights: Mapping[str, float] | None = None,
) -> float:
    """Compute a per-planet angular load score in [0,1].

    Args:
        dist_to_angles: Mapping with distances (deg) to each of 'asc','mc','desc','ic'.
                        Values may be in [0,360] or [0,180]; we normalize using min arc.
        house_num:      Integer house number (1..12).
        cusp_dist_deg:  Distance (deg) to nearest house cusp.

        angle_prox_threshold_deg: Override ANGLE_PROX_THRESHOLD_DEG if provided.
        cusp_penalty_window_deg:  Override CUSP_PENALTY_WINDOW_DEG if provided.
        house_weights:            Override HOUSE_WEIGHTS if provided.

    Returns:
        Score in [0,1], higher = stronger angular emphasis.
    """
    # Resolve constants (allow call-site overrides).
    theta = float(
        ANGLE_PROX_THRESHOLD_DEG
        if angle_prox_threshold_deg is None
        else angle_prox_threshold_deg
    )
    cusp_win = float(
        CUSP_PENALTY_WINDOW_DEG
        if cusp_penalty_window_deg is None
        else cusp_penalty_window_deg
    )
    hweights: Mapping[str, float] = (
        HOUSE_WEIGHTS if house_weights is None else house_weights
    )

    # Angle proximity: use the shortest arc distance among the four angles.
    # Normalize so 0 deg => 1.0, theta deg => 0.0, beyond theta clamped at 0.
    dmins = []
    for k in ("asc", "mc", "desc", "ic"):
        v = dist_to_angles.get(k)
        if v is None:
            continue
        d = float(v)
        # If caller passed 0..360, compress to shortest arc.
        if d > 180.0:
            d = 360.0 - d
        dmins.append(d)
    d_min = min(dmins) if dmins else 180.0
    w_angle = 1.0 - (d_min / theta)
    if w_angle < 0.0:
        w_angle = 0.0
    elif w_angle > 1.0:
        w_angle = 1.0

    # House weight
    hclass = house_class(house_num)
    w_house = float(hweights.get(hclass, 1.0))

    # Cusp penalty: linear penalty within cusp window; capped by CUSP_PENALTY_WEIGHT.
    if cusp_win <= 0.0:
        effective = 1.0
    else:
        p = cusp_dist_deg / cusp_win
        if p < 0.0:
            p = 0.0
        elif p > 1.0:
            p = 1.0
        effective = 1.0 - (CUSP_PENALTY_WEIGHT * p)

    score = w_angle * w_house * effective
    return _clamp01(score)
