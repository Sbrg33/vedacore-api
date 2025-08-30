#!/usr/bin/env python3
"""
Eclipse Prediction Module - Phase 6
Solar and Lunar Eclipse Detection using Swiss Ephemeris

This module provides eclipse prediction capabilities including:
- Solar eclipse detection (total/annular/hybrid/partial)
- Lunar eclipse detection (total/partial/penumbral)
- Central path calculation for solar eclipses
- Local visibility computation
- Contact times and magnitudes

Author: VedaCore Team
Version: 1.0.0
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import swisseph as swe

from .eclipse_config import EclipseConfig, get_eclipse_config

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")

# Type aliases
Kind = Literal["solar", "lunar", "both"]
SolarClass = Literal["total", "annular", "hybrid", "partial"]
LunarClass = Literal["total", "partial", "penumbral"]


@dataclass(frozen=True)
class EclipseEvent:
    """Represents a single eclipse event."""

    kind: Literal["solar", "lunar"]
    classification: str  # Type of eclipse
    peak_utc: datetime  # Peak time in UTC
    magnitude: float | None = None  # Eclipse magnitude
    saros: str | None = None  # Saros series number
    gamma: float | None = None  # Gamma parameter
    duration_minutes: float | None = None  # Total duration
    contacts: dict[str, datetime] = field(default_factory=dict)  # Contact times
    meta: dict[str, Any] = field(default_factory=dict)  # Additional metadata


@dataclass(frozen=True)
class SolarPath:
    """Solar eclipse central path information."""

    central_line: list[tuple[float, float]]  # [(lat, lon), ...]
    northern_limit: list[tuple[float, float]]  # Northern boundary
    southern_limit: list[tuple[float, float]]  # Southern boundary
    max_width_km: float  # Maximum path width
    timestamps: list[datetime]  # Time at each point
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Visibility:
    """Eclipse visibility from a specific location."""

    visible: bool
    magnitude: float  # Local magnitude
    obscuration: float  # Percentage of sun/moon obscured
    altitude: float  # Altitude of eclipsed body
    azimuth: float  # Azimuth of eclipsed body
    start_time: datetime | None = None
    max_time: datetime | None = None
    end_time: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# Helper functions


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC timezone-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _julday(dt_utc: datetime) -> float:
    """Convert datetime to Julian day number."""
    dt_utc = _ensure_utc(dt_utc)
    return swe.julday(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0,
        swe.GREG_CAL,
    )


def _jd_to_dt(jd: float) -> datetime:
    """Convert Julian day to datetime."""
    y, m, d, ut = swe.revjul(jd, swe.GREG_CAL)
    hour = int(ut)
    minute = int((ut - hour) * 60.0)
    second = int((((ut - hour) * 60.0) - minute) * 60.0)
    microsecond = int((((((ut - hour) * 60.0) - minute) * 60.0) - second) * 1000000.0)
    return datetime(y, m, d, hour, minute, second, microsecond, tzinfo=UTC)


def _classify_solar(flag: int) -> str:
    """Classify solar eclipse based on Swiss Ephemeris flags."""
    if flag & swe.ECL_TOTAL:
        if flag & swe.ECL_CENTRAL:
            if flag & swe.ECL_NONCENTRAL:
                return "hybrid"
            return "total"
        return "total"
    if flag & swe.ECL_ANNULAR:
        if flag & swe.ECL_TOTAL:
            return "hybrid"
        return "annular"
    if flag & swe.ECL_PARTIAL:
        return "partial"
    return "partial"  # Default


def _classify_lunar(flag: int) -> str:
    """Classify lunar eclipse based on Swiss Ephemeris flags."""
    if flag & swe.ECL_TOTAL:
        return "total"
    if flag & swe.ECL_PARTIAL:
        return "partial"
    if flag & swe.ECL_PENUMBRAL:
        return "penumbral"
    return "penumbral"  # Default


# Main eclipse detection functions


def solar_events_between(
    start_utc: datetime, end_utc: datetime, cfg: EclipseConfig | None = None
) -> list[EclipseEvent]:
    """
    Find solar eclipses between start and end dates.

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        cfg: Eclipse configuration (uses global if not provided)

    Returns:
        List of solar eclipse events
    """
    if cfg is None:
        cfg = get_eclipse_config()

    start_utc = _ensure_utc(start_utc)
    end_utc = _ensure_utc(end_utc)

    if end_utc <= start_utc:
        return []

    # Check span limit
    span_years = (end_utc - start_utc).days / 365.25
    if span_years > cfg.max_span_years:
        raise ValueError(
            f"Time span {span_years:.1f} years exceeds maximum {cfg.max_span_years} years"
        )

    # Set ephemeris path
    swe.set_ephe_path(cfg.ephemeris_path)

    events: list[EclipseEvent] = []
    current = start_utc

    while current <= end_utc:
        jd = _julday(current)

        # Find next solar eclipse
        # Search forward for next eclipse
        retflag, tret = swe.sol_eclipse_when_glob(
            jd, swe.FLG_SWIEPH, swe.ECL_ALLTYPES_SOLAR, False
        )

        if retflag < 0:
            logger.warning(f"Solar eclipse search failed at {current}")
            break

        # Extract peak time
        peak_jd = tret[0]  # Maximum eclipse
        peak_dt = _jd_to_dt(peak_jd)

        if peak_dt > end_utc:
            break

        if peak_dt >= start_utc:
            # Get more details about the eclipse
            classification = _classify_solar(retflag)

            # Get eclipse attributes at maximum
            ret2, geopos, attr = swe.sol_eclipse_where(peak_jd, swe.FLG_SWIEPH)

            magnitude = None
            gamma = None

            if ret2 >= 0:
                # attr[0] = fraction of solar diameter covered
                # attr[1] = ratio of lunar diameter to solar diameter
                magnitude = attr[0] if len(attr) > 0 else None
                # Gamma can be calculated from geopos
                if len(geopos) >= 2:
                    # Approximate gamma from latitude of greatest eclipse
                    gamma = geopos[1] / 90.0  # Normalize latitude

            # Extract contact times if available
            contacts = {}
            if len(tret) >= 6:
                if tret[2] > 0:  # First contact (eclipse begin)
                    contacts["C1"] = _jd_to_dt(tret[2])
                if tret[4] > 0:  # Second contact (totality begin)
                    contacts["C2"] = _jd_to_dt(tret[4])
                if tret[5] > 0:  # Third contact (totality end)
                    contacts["C3"] = _jd_to_dt(tret[5])
                if tret[3] > 0:  # Fourth contact (eclipse end)
                    contacts["C4"] = _jd_to_dt(tret[3])

            # Calculate duration if total or annular
            duration_minutes = None
            if (
                classification in ["total", "annular"]
                and "C2" in contacts
                and "C3" in contacts
            ):
                duration_minutes = (
                    contacts["C3"] - contacts["C2"]
                ).total_seconds() / 60.0

            event = EclipseEvent(
                kind="solar",
                classification=classification,
                peak_utc=peak_dt,
                magnitude=magnitude,
                gamma=gamma,
                duration_minutes=duration_minutes,
                contacts=contacts,
                meta={
                    "retflag": retflag,
                    "central_lat": geopos[1] if len(geopos) > 1 else None,
                    "central_lon": geopos[0] if len(geopos) > 0 else None,
                },
            )

            events.append(event)

        # Move past this eclipse
        current = peak_dt + timedelta(days=1)

    return events


def lunar_events_between(
    start_utc: datetime, end_utc: datetime, cfg: EclipseConfig | None = None
) -> list[EclipseEvent]:
    """
    Find lunar eclipses between start and end dates.

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        cfg: Eclipse configuration (uses global if not provided)

    Returns:
        List of lunar eclipse events
    """
    if cfg is None:
        cfg = get_eclipse_config()

    start_utc = _ensure_utc(start_utc)
    end_utc = _ensure_utc(end_utc)

    if end_utc <= start_utc:
        return []

    # Check span limit
    span_years = (end_utc - start_utc).days / 365.25
    if span_years > cfg.max_span_years:
        raise ValueError(
            f"Time span {span_years:.1f} years exceeds maximum {cfg.max_span_years} years"
        )

    # Set ephemeris path
    swe.set_ephe_path(cfg.ephemeris_path)

    events: list[EclipseEvent] = []
    current = start_utc

    while current <= end_utc:
        jd = _julday(current)

        # Find next lunar eclipse
        # Search forward for next eclipse
        retflag, tret = swe.lun_eclipse_when(
            jd, swe.FLG_SWIEPH, swe.ECL_ALLTYPES_LUNAR, False
        )

        if retflag < 0:
            logger.warning(f"Lunar eclipse search failed at {current}")
            break

        # Extract peak time
        peak_jd = tret[0]  # Maximum eclipse
        peak_dt = _jd_to_dt(peak_jd)

        if peak_dt > end_utc:
            break

        if peak_dt >= start_utc:
            # Get more details about the eclipse
            classification = _classify_lunar(retflag)

            # Get magnitude
            ret2, attr = swe.lun_eclipse_how(peak_jd, (0, 0, 0), swe.FLG_SWIEPH)

            magnitude = None
            if ret2 >= 0 and len(attr) > 0:
                magnitude = attr[0]  # Umbral magnitude

            # Extract contact times
            contacts = {}
            if len(tret) >= 7:
                contact_names = ["P1", "U1", "U2", "Max", "U3", "U4", "P4"]
                contact_indices = [6, 2, 4, 0, 5, 3, 7]  # Swiss Ephemeris ordering

                for name, idx in zip(contact_names, contact_indices, strict=False):
                    if idx < len(tret) and tret[idx] > 0:
                        contacts[name] = _jd_to_dt(tret[idx])

            # Calculate total duration
            duration_minutes = None
            if "P1" in contacts and "P4" in contacts:
                duration_minutes = (
                    contacts["P4"] - contacts["P1"]
                ).total_seconds() / 60.0

            event = EclipseEvent(
                kind="lunar",
                classification=classification,
                peak_utc=peak_dt,
                magnitude=magnitude,
                duration_minutes=duration_minutes,
                contacts=contacts,
                meta={
                    "retflag": retflag,
                    "penumbral_mag": attr[1] if len(attr) > 1 else None,
                },
            )

            events.append(event)

        # Move past this eclipse
        current = peak_dt + timedelta(days=1)

    return events


def events_between(
    start_utc: datetime,
    end_utc: datetime,
    kind: Kind = "both",
    cfg: EclipseConfig | None = None,
) -> list[EclipseEvent]:
    """
    Find eclipses of specified type between dates.

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        kind: Type of eclipses to find ("solar", "lunar", or "both")
        cfg: Eclipse configuration

    Returns:
        List of eclipse events sorted by time
    """
    if kind == "solar":
        return solar_events_between(start_utc, end_utc, cfg)
    elif kind == "lunar":
        return lunar_events_between(start_utc, end_utc, cfg)
    else:  # both
        solar = solar_events_between(start_utc, end_utc, cfg)
        lunar = lunar_events_between(start_utc, end_utc, cfg)
        combined = solar + lunar
        return sorted(combined, key=lambda e: e.peak_utc)


def solar_visibility(
    ts_utc: datetime, lat: float, lon: float, altitude: float = 0.0
) -> Visibility:
    """
    Calculate solar eclipse visibility from a specific location.

    Args:
        ts_utc: Time to check (UTC)
        lat: Observer latitude (-90 to 90)
        lon: Observer longitude (-180 to 180)
        altitude: Observer altitude in meters

    Returns:
        Visibility information
    """
    ts_utc = _ensure_utc(ts_utc)
    jd = _julday(ts_utc)

    # Get local circumstances
    attr = [0.0] * 20
    geopos = [lon, lat, altitude]

    retflag, attr = swe.sol_eclipse_how(jd, tuple(geopos), swe.FLG_SWIEPH)

    visible = retflag > 0

    if visible:
        # Extract attributes
        # attr[0] = fraction of solar diameter covered (magnitude)
        # attr[1] = ratio of lunar diameter to solar diameter
        # attr[2] = fraction of solar disc covered (obscuration)
        # attr[3] = diameter of core shadow in km (if applicable)
        # attr[4] = azimuth of sun
        # attr[5] = altitude of sun

        magnitude = attr[0] if len(attr) > 0 else 0.0
        obscuration = attr[2] * 100 if len(attr) > 2 else 0.0  # Convert to percentage
        azimuth = attr[4] if len(attr) > 4 else 0.0
        altitude_deg = attr[5] if len(attr) > 5 else 0.0

        # Get contact times for this location
        tret = [0.0] * 10
        ret2, tret, attr2 = swe.sol_eclipse_when_loc(
            jd - 1, tuple(geopos), swe.FLG_SWIEPH, False
        )

        start_time = None
        max_time = None
        end_time = None

        if ret2 >= 0:
            if tret[1] > 0:  # First contact
                start_time = _jd_to_dt(tret[1])
            if tret[0] > 0:  # Maximum
                max_time = _jd_to_dt(tret[0])
            if tret[4] > 0:  # Last contact
                end_time = _jd_to_dt(tret[4])

        return Visibility(
            visible=True,
            magnitude=magnitude,
            obscuration=obscuration,
            altitude=altitude_deg,
            azimuth=azimuth,
            start_time=start_time,
            max_time=max_time,
            end_time=end_time,
            meta={"retflag": retflag},
        )
    else:
        return Visibility(
            visible=False,
            magnitude=0.0,
            obscuration=0.0,
            altitude=0.0,
            azimuth=0.0,
            meta={"retflag": retflag},
        )


def lunar_visibility(
    ts_utc: datetime, lat: float, lon: float, altitude: float = 0.0
) -> Visibility:
    """
    Calculate lunar eclipse visibility from a specific location.

    Args:
        ts_utc: Time to check (UTC)
        lat: Observer latitude
        lon: Observer longitude
        altitude: Observer altitude in meters

    Returns:
        Visibility information
    """
    ts_utc = _ensure_utc(ts_utc)
    jd = _julday(ts_utc)

    # Get local circumstances
    attr = [0.0] * 20
    geopos = [lon, lat, altitude]

    retflag, attr = swe.lun_eclipse_how(jd, tuple(geopos), swe.FLG_SWIEPH)

    visible = retflag > 0

    if visible:
        # attr[0] = umbral magnitude
        # attr[1] = penumbral magnitude
        # attr[4] = azimuth of moon
        # attr[5] = altitude of moon

        magnitude = attr[0] if len(attr) > 0 else 0.0
        penumbral_mag = attr[1] if len(attr) > 1 else 0.0
        azimuth = attr[4] if len(attr) > 4 else 0.0
        altitude_deg = attr[5] if len(attr) > 5 else 0.0

        # For lunar eclipses, obscuration can be calculated from magnitude
        obscuration = min(magnitude * 100, 100.0)

        return Visibility(
            visible=True,
            magnitude=magnitude,
            obscuration=obscuration,
            altitude=altitude_deg,
            azimuth=azimuth,
            meta={"retflag": retflag, "penumbral_magnitude": penumbral_mag},
        )
    else:
        return Visibility(
            visible=False,
            magnitude=0.0,
            obscuration=0.0,
            altitude=0.0,
            azimuth=0.0,
            meta={"retflag": retflag},
        )


def solar_path(
    eclipse_time: datetime, cfg: EclipseConfig | None = None
) -> SolarPath | None:
    """
    Calculate the central path of a solar eclipse.

    Args:
        eclipse_time: Time near eclipse maximum
        cfg: Eclipse configuration

    Returns:
        SolarPath object with central line and boundaries, or None if not a central eclipse
    """
    if cfg is None:
        cfg = get_eclipse_config()

    eclipse_time = _ensure_utc(eclipse_time)
    jd = _julday(eclipse_time)

    # First check if this is actually a solar eclipse
    tret = [0.0] * 10
    retflag, tret = swe.sol_eclipse_when_glob(
        jd, swe.FLG_SWIEPH, swe.ECL_ALLTYPES_SOLAR, False
    )

    if retflag < 0:
        return None

    classification = _classify_solar(retflag)
    if classification not in ["total", "annular", "hybrid"]:
        return None  # No central path for partial eclipses

    # Get the eclipse duration
    start_jd = tret[2] if tret[2] > 0 else tret[1]  # First contact
    end_jd = tret[5] if tret[5] > 0 else tret[4]  # Last contact

    if start_jd <= 0 or end_jd <= 0:
        return None

    # Sample points along the path
    central_line = []
    timestamps = []

    # Calculate number of sample points based on duration and sampling resolution
    duration_hours = (end_jd - start_jd) * 24
    num_samples = min(
        int(duration_hours * 60 / 5), cfg.path_points_max
    )  # Sample every 5 minutes or max points

    for i in range(num_samples):
        sample_jd = start_jd + (end_jd - start_jd) * i / (num_samples - 1)

        # Get the geographic position of maximum eclipse at this time
        ret2, geopos, attr = swe.sol_eclipse_where(sample_jd, swe.FLG_SWIEPH)

        if ret2 >= 0 and len(geopos) >= 2:
            central_line.append((geopos[1], geopos[0]))  # (lat, lon)
            timestamps.append(_jd_to_dt(sample_jd))

    if not central_line:
        return None

    # Calculate approximate path width (simplified)
    # Real calculation would need more complex geometry
    max_width_km = 300.0  # Approximate maximum for total solar eclipse

    # For now, return simplified boundaries (parallel to central line)
    # Real implementation would calculate actual northern/southern limits
    northern_limit = [(lat + 2.0, lon) for lat, lon in central_line]
    southern_limit = [(lat - 2.0, lon) for lat, lon in central_line]

    return SolarPath(
        central_line=central_line,
        northern_limit=northern_limit,
        southern_limit=southern_limit,
        max_width_km=max_width_km,
        timestamps=timestamps,
        meta={"classification": classification, "num_samples": num_samples},
    )


def next_eclipse(
    after: datetime | None = None, kind: Kind = "both"
) -> EclipseEvent | None:
    """
    Find the next eclipse after a given time.

    Args:
        after: Start searching after this time (default: now)
        kind: Type of eclipse to find

    Returns:
        Next eclipse event or None
    """
    if after is None:
        after = datetime.now(UTC)
    else:
        after = _ensure_utc(after)

    # Search for next year
    end = after + timedelta(days=365)

    events = events_between(after, end, kind)

    if events:
        return events[0]

    return None
