"""KP Horary numbers (1–249) — core utilities.

Notes
-----
* This module is **self-contained** and does not import ephemeris code.
* Real mapping of 1–249 to sub-lords should come from your constants
  (e.g., `constants.kp.HORARY_1_249_PLANET`). We expose a mapping hook
  and a safe default (9-planet repeat) for tests.
* Designed to be numba-friendly; use `maybe_njit` decorator.

Generated: 2025-08-25 01:24
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

try:
    from numba import njit as _njit  # type: ignore

    def maybe_njit(**kw):  # pragma: no cover
        return _njit(cache=True, **kw)

except Exception:  # pragma: no cover

    def maybe_njit(**kw):
        def deco(fn):
            return fn

        return deco


# Default Vimshottari sequence (True Node)
VIMS_ORDER = ("KE", "VE", "SU", "MO", "MA", "RA", "JU", "SA", "ME")


@dataclass(frozen=True)
class HoraryConfig:
    mode: str = "unix_mod"  # 'unix_mod' | 'daily_mod' | 'sunrise_mod'
    tz_offset_sec: int = 0  # if using daily_mod
    sunrise_ts: int | None = None  # if using sunrise_mod
    boost_if_moon_ruled: float = 0.15  # extra MSI factor when Moon's chain matches


@maybe_njit(fastmath=True, nogil=True)
def _mod_1_249(x: int) -> int:
    m = x % 249
    return m + 1


@maybe_njit(fastmath=True, nogil=True)
def _horary_unix_mod(timestamp_unix: int) -> int:
    """JIT-optimized unix_mod calculation"""
    return _mod_1_249(timestamp_unix)


@maybe_njit(fastmath=True, nogil=True)
def _horary_daily_mod(timestamp_unix: int, tz_offset_sec: int) -> int:
    """JIT-optimized daily_mod calculation"""
    local = timestamp_unix + tz_offset_sec
    secs = local % 86400
    return _mod_1_249(secs)


@maybe_njit(fastmath=True, nogil=True)
def _horary_sunrise_mod(timestamp_unix: int, sunrise_ts: int) -> int:
    """JIT-optimized sunrise_mod calculation"""
    delta = timestamp_unix - sunrise_ts
    if delta < 0:
        delta = (delta % 86400 + 86400) % 86400
    return _mod_1_249(delta)


def default_number_to_planet(num: int, order: tuple[str, ...] = VIMS_ORDER) -> str:
    """Cheap fallback: repeat Vimshottari order every 9 numbers.
    Replace with constants-backed mapping in production.
    """
    return order[(num - 1) % 9]


def horary_number(timestamp_unix: int, cfg: HoraryConfig) -> int:
    """Compute 1–249 horary number with three deterministic modes."""
    if cfg.mode == "unix_mod":
        return _horary_unix_mod(timestamp_unix)
    elif cfg.mode == "daily_mod":
        return _horary_daily_mod(timestamp_unix, cfg.tz_offset_sec)
    elif cfg.mode == "sunrise_mod":
        if cfg.sunrise_ts is None:
            raise ValueError("sunrise_mod requires cfg.sunrise_ts")
        if cfg.sunrise_ts <= 0:
            raise ValueError(f"sunrise_ts must be positive, got {cfg.sunrise_ts}")
        return _horary_sunrise_mod(timestamp_unix, cfg.sunrise_ts)
    else:
        raise ValueError(f"unknown mode: {cfg.mode}")


@dataclass(frozen=True)
class HoraryResult:
    number: int
    planet_ruler: str
    moon_ruled: bool
    horary_boost: float


def compute_horary(
    timestamp_unix: int,
    cfg: HoraryConfig,
    number_to_planet: Callable[[int], str] = default_number_to_planet,
    moon_chain_planets: tuple[str, str, str] = ("MO", "MO", "MO"),
) -> HoraryResult:
    """Top-level compute helper.
    `moon_chain_planets` is (NL, SL, SSL) for the Moon at the moment.
    """
    num = horary_number(timestamp_unix, cfg)
    planet = number_to_planet(num)
    moon_ruled = planet in set(moon_chain_planets)
    boost = cfg.boost_if_moon_ruled if moon_ruled else 0.0
    return HoraryResult(
        number=num, planet_ruler=planet, moon_ruled=moon_ruled, horary_boost=boost
    )
