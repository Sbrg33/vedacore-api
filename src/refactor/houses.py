# refactor/houses.py
from __future__ import annotations

import math

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import swisseph as swe

from .house_config import ensure_config_initialized, is_topocentric_enabled

# NOTE: sidereal mode (Krishnamurti) should already be set once at process start
# e.g., in refactor/swe_backend.py: swe.set_sid_mode(swe.SIDM_KRISHNAMURTI, 0, 0)

HouseSystem = Literal["PLACIDUS", "BHAVA"]

UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class Houses:
    system: HouseSystem
    asc: float  # degrees [0, 360)
    mc: float  # degrees [0, 360)
    cusps: list[float]  # 12 items, degrees [0, 360)


def _julday(ts_utc: datetime) -> float:
    """UTC → Julian Day (UT)."""
    from .time_utils import datetime_to_julian_day

    return datetime_to_julian_day(ts_utc)


def _norm360(x: float) -> float:
    return x % 360.0


def _placidus(ts_utc: datetime, lat: float, lon: float) -> Houses:
    """
    Placidus houses using Swiss Ephemeris.
    - Geocentric by default.
    - Topocentric support (optional) can be enabled at startup with swe.set_topo(lon, lat, elev).
    - Raises ValueError for latitudes where Placidus is undefined (beyond Arctic/Antarctic circles)
    - Applies sidereal correction as Swiss Ephemeris houses() returns tropical values
    """
    # Check for polar latitudes where Placidus may be undefined
    if abs(lat) > 66.5:
        # Try calculation, but prepare for potential failure
        try:
            jd = _julday(ts_utc)
            cusps, ascmc = swe.houses_ex(jd, lat, lon, b"P")

            # Check if Swiss Ephemeris returned valid values
            if cusps is None or ascmc is None or any(math.isnan(c) for c in cusps):
                raise ValueError(
                    f"Placidus houses undefined at latitude {lat:.2f}°. "
                    f"Placidus system is not defined beyond Arctic/Antarctic circles. "
                    f"Consider using Equal or Porphyry house system for polar regions."
                )

            # Get ayanamsa for sidereal correction (Swiss Ephemeris houses returns tropical)
            ayanamsa = swe.get_ayanamsa_ut(jd)

            # Apply sidereal correction
            asc = _norm360(ascmc[0] - ayanamsa)
            mc = _norm360(ascmc[1] - ayanamsa)
            c = [_norm360(cusps[i] - ayanamsa) for i in range(12)]
            return Houses(system="PLACIDUS", asc=asc, mc=mc, cusps=c)

        except Exception as e:
            raise ValueError(
                f"Placidus houses calculation failed at latitude {lat:.2f}°. "
                f"Placidus system is typically undefined beyond ±66.5° latitude. "
                f"Error: {e!s}"
            )

    # Normal calculation for non-polar latitudes
    jd = _julday(ts_utc)
    cusps, ascmc = swe.houses_ex(jd, lat, lon, b"P")

    # Get ayanamsa for sidereal correction (Swiss Ephemeris houses returns tropical)
    ayanamsa = swe.get_ayanamsa_ut(jd)

    # Apply sidereal correction
    asc = _norm360(ascmc[0] - ayanamsa)
    mc = _norm360(ascmc[1] - ayanamsa)
    c = [_norm360(cusps[i] - ayanamsa) for i in range(12)]

    return Houses(system="PLACIDUS", asc=asc, mc=mc, cusps=c)


def _sripati_from_placidus(plac_cusps: list[float]) -> list[float]:
    """
    Sripati (Bhava Chalit) derivation from Placidus cusps:
    - Each bhava cusp is midpoint of adjacent quadrant divisions.
    - This is the classic midpoint approach; if your legacy deviates, mirror that math here.
    """
    c = plac_cusps
    out: list[float] = []
    for i in range(12):
        a = c[i]
        b = c[(i + 1) % 12]
        # shortest arc from a->b in [-180, +180)
        delta = (b - a + 540.0) % 360.0 - 180.0
        mid = _norm360(a + delta / 2.0)
        out.append(mid)
    return out


def compute_houses(
    ts_utc: datetime,
    lat: float,
    lon: float,
    *,
    system: HouseSystem = "PLACIDUS",
    topocentric: bool = False,
) -> Houses:
    """
    Compute house cusps + ASC/MC in sidereal KP mode.
    - ts_utc must be tz-aware.
    - lat in [-90,90], lon in [-180,180].
    - If topocentric, ensure swe.set_topo(lon, lat, elev) was called at startup.
    """
    # Ensure configuration is initialized
    ensure_config_initialized()

    # Check topocentric consistency
    if topocentric and not is_topocentric_enabled():
        raise ValueError(
            "Topocentric mode requested but not enabled at startup. "
            "Set HOUSE_TOPO_ENABLED=true and provide HOUSE_TOPO_LON/LAT/ELEV environment variables."
        )

    # (Optional) safety validations
    if ts_utc.tzinfo is None:
        raise ValueError("ts_utc must be timezone-aware")
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("lat out of range [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("lon out of range [-180, 180]")

    plac = _placidus(ts_utc, lat, lon)
    if system == "PLACIDUS":
        return plac

    # Derive Bhava Chalit (Sripati) from Placidus
    bhava_cusps = _sripati_from_placidus(plac.cusps)
    return Houses(system="BHAVA", asc=plac.asc, mc=plac.mc, cusps=bhava_cusps)
