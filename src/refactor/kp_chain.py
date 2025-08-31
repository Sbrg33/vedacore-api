#!/usr/bin/env python3
"""
KP chain calculation (NL -> SL -> SSL) using Vimshottari dasha order.

Minimal, dependency-free implementation to avoid cross-repo imports.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from .angles_indices import nakshatra_number
from .constants import (
    LORD_ARRAY,
    LORD_INDEX,
    VIMSHOTTARI_CUM,
    VIMSHOTTARI_PROP,
    NAKSHATRA_SPAN,
)


def _rotate(arr: np.ndarray, start_idx: int) -> np.ndarray:
    return np.concatenate((arr[start_idx:], arr[:start_idx]))


def _chain_for_fraction(start_lord_idx: int, frac: float) -> Tuple[int, int, int]:
    """Compute (NL, SL, SSL) for a fractional position within nakshatra [0,1).

    Uses rotated Vimshottari proportions starting at the nakshatra lord.
    """
    nl = int(LORD_ARRAY[start_lord_idx])

    # Rotate proportions and lords so index 0 is the starting lord
    props1 = _rotate(VIMSHOTTARI_PROP, start_lord_idx)
    lords1 = _rotate(LORD_ARRAY, start_lord_idx)
    cum1 = np.cumsum(props1)

    # Find sub-lord segment
    sl_idx = int(np.searchsorted(cum1, frac, side="right"))
    if sl_idx >= len(lords1):
        sl_idx = len(lords1) - 1
    sl = int(lords1[sl_idx])

    # Compute position within sub-lord segment
    prev_cum = 0.0 if sl_idx == 0 else float(cum1[sl_idx - 1])
    seg_len = float(props1[sl_idx])
    inner_frac = 0.0 if seg_len <= 0 else (frac - prev_cum) / seg_len

    # Rotate again for SSL starting at sub-lord
    start2 = LORD_INDEX[sl]
    props2 = _rotate(VIMSHOTTARI_PROP, start2)
    lords2 = _rotate(LORD_ARRAY, start2)
    cum2 = np.cumsum(props2)
    ssl_idx = int(np.searchsorted(cum2, inner_frac, side="right"))
    if ssl_idx >= len(lords2):
        ssl_idx = len(lords2) - 1
    ssl = int(lords2[ssl_idx])

    return nl, sl, ssl


def kp_chain_for_longitude(longitude: float, levels: int = 3) -> Tuple[int, ...]:
    """Return KP chain for a longitude as planet IDs (1-9).

    levels: 1..3 for NL, NL->SL, NL->SL->SSL
    """
    # Determine nakshatra and fractional position within it
    nak_num = nakshatra_number(longitude)
    start_idx = int((nak_num - 1) % 9)  # index into LORD_ARRAY
    # Fraction within nakshatra
    deg_in_nak = (longitude % 360.0) - ((nak_num - 1) * NAKSHATRA_SPAN)
    if deg_in_nak < 0:
        deg_in_nak += NAKSHATRA_SPAN
    frac = float(deg_in_nak) / float(NAKSHATRA_SPAN)

    nl, sl, ssl = _chain_for_fraction(start_idx, frac)
    if levels <= 1:
        return (nl,)
    if levels == 2:
        return (nl, sl)
    return (nl, sl, ssl)


def get_kp_lords_for_planet(longitude: float) -> Tuple[int, int, int]:
    """Return (NL, SL, SSL) for a planetary longitude (degrees)."""
    chain = kp_chain_for_longitude(longitude, levels=3)
    # Always return 3 elements
    return int(chain[0]), int(chain[1]) if len(chain) > 1 else 0, int(chain[2]) if len(chain) > 2 else 0


def warmup_kp_calculations() -> None:  # pragma: no cover - trivial
    """Warmup placeholder: precomputes nothing but validates functions are importable."""
    _ = kp_chain_for_longitude(0.0, levels=3)


def get_kp_chain_for_target(
    *,
    timestamp,
    latitude: float,
    longitude: float,
    target_type: str,
    target_id: str | int,
) -> dict:
    """Minimal chain calculation for API v1 endpoint.

    Supports target_type="planet" with numeric ID (1-9).
    """
    from .swe_backend import get_planet_position_full
    from .angles_indices import find_nakshatra_pada, sign_number

    if target_type != "planet":
        raise ValueError("Only planet target_type is supported in minimal implementation")

    try:
        pid = int(target_id)
    except Exception as e:
        raise ValueError(f"Invalid planet id: {target_id}") from e

    pos = get_planet_position_full(timestamp, pid)
    lon = float(pos["longitude"]) % 360.0
    nl, sl, ssl = get_kp_lords_for_planet(lon)
    nak, pada = find_nakshatra_pada(lon)

    return {
        "chain": {"nl": nl, "sl": sl, "ssl": ssl},
        "degrees": {"longitude": lon, "sign": sign_number(lon)},
        "nakshatra_pada": {"nakshatra": nak, "pada": pada},
    }
