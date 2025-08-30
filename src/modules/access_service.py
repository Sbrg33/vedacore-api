#!/usr/bin/env python3
"""
Global Locality Research - Access Service
Per-location access geometry calculations for activation field mapping.

Computes how celestial energies can access each Earth location through
angles (ASC/MC/DESC/IC) and their nakshatra/pada/lord relationships.
Maintains identical timestamp with sky_state_service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple

from app.services.cache_service import CacheService
from constants.activation_model import (
    CACHE_TTL_ACCESS,
    GANDANTA_BOUNDARIES_DEG,
    GANDANTA_ORB_DEG,
    GATEKEEPER_BOUNDS,
    MODEL_VERSION,
    get_latitude_reliability,
    get_model_fingerprint,
    get_profile_config,
    should_apply_polar_hard_limit,
)
from refactor.angles_indices import find_nakshatra_pada
from refactor.houses import compute_houses
from refactor.kp_chain import get_kp_lords_for_planet


class AxisInfo(NamedTuple):
    """Information about a chart axis"""

    degree: float
    nakshatra: int
    pada: int
    nakshatra_lord: int  # NL
    sub_lord: int  # SL
    sub_sub_lord: int  # SL2


class GatekeeperScore(NamedTuple):
    """Gatekeeper (axis-lord condition) scoring"""

    asc_lord_strength: float
    mc_lord_strength: float
    overall_score: float  # Within GATEKEEPER_BOUNDS (0.85-1.15)
    dignity_bonus: float  # Dignity-based adjustments
    angularity_bonus: float  # Angular house placement bonus


@dataclass
class AccessGeometry:
    """Complete access geometry for a location"""

    timestamp: datetime
    latitude: float
    longitude: float
    model_version: str
    model_profile: str

    # Chart axes with nakshatra/lord information
    asc: AxisInfo
    mc: AxisInfo
    desc: AxisInfo
    ic: AxisInfo

    # House cusps (full 12-house system)
    cusps: list[float]
    house_system: str

    # Local time factors
    is_day_birth: bool
    local_sidereal_time_hours: float
    altitude_above_sea_level: float | None

    # Gatekeeper analysis
    gatekeeper: GatekeeperScore

    # Gandānta (boundary junction) flags
    gandanta_axis: bool  # Any axis in gandānta
    gandanta_asc: bool  # ASC specifically in gandānta
    gandanta_mc: bool  # MC specifically in gandānta

    # Reliability assessment
    latitude_reliability: str  # "high", "med", "low"
    polar_risk: bool  # True if approaching polar calculation limits

    # Computation metadata
    computation_time_ms: float
    cache_hit: bool


def _wrap_360(degrees: float) -> float:
    """Wrap degrees to [0, 360) range."""
    return degrees % 360.0


def _compute_axis_info(axis_degree: float) -> AxisInfo:
    """Compute nakshatra and lord information for axis.

    Args:
        axis_degree: Axis position in degrees

    Returns:
        AxisInfo with nakshatra and lord details
    """
    wrapped_degree = _wrap_360(axis_degree)

    # Get nakshatra and pada
    nakshatra, pada = find_nakshatra_pada(wrapped_degree)

    # Get KP lords for this degree
    nl, sl, sl2 = get_kp_lords_for_planet(wrapped_degree)

    return AxisInfo(
        degree=wrapped_degree,
        nakshatra=nakshatra,
        pada=pada,
        nakshatra_lord=nl,
        sub_lord=sl,
        sub_sub_lord=sl2,
    )


def _is_day_birth(
    sun_longitude: float, asc_longitude: float, mc_longitude: float
) -> bool:
    """Determine if chart represents day birth (Sun above horizon).

    Args:
        sun_longitude: Sun position in degrees
        asc_longitude: Ascendant in degrees
        mc_longitude: Midheaven in degrees

    Returns:
        True if day birth (Sun above ASC-DESC horizon)
    """
    # Convert to house position relative to ASC
    sun_from_asc = _wrap_360(sun_longitude - asc_longitude)

    # Day birth: Sun in houses 7, 8, 9, 10, 11, 12 (above horizon)
    # This corresponds to 180° to 360° from ASC
    return 180.0 <= sun_from_asc <= 360.0


def _compute_local_sidereal_time(longitude: float, timestamp: datetime) -> float:
    """Compute Local Sidereal Time in hours.

    Args:
        longitude: Location longitude in degrees
        timestamp: UTC timestamp

    Returns:
        LST in hours [0, 24)
    """
    # Simplified LST calculation for MVP
    # Production version should use proper sidereal time calculations

    # Greenwich Sidereal Time approximation
    hours_since_j2000 = (timestamp.timestamp() - 946728000) / 3600  # J2000 epoch
    gst = (18.697374558 + 24.06570982441908 * (hours_since_j2000 / 24.0)) % 24.0

    # Convert to Local Sidereal Time
    lst = (gst + longitude / 15.0) % 24.0

    return lst


def _detect_gandanta_position(degree: float) -> bool:
    """Check if position is in Gandānta (junction between water/fire signs).

    Args:
        degree: Position in degrees

    Returns:
        True if within gandānta orb of junction
    """
    wrapped = _wrap_360(degree)

    for start_deg, end_deg in GANDANTA_BOUNDARIES_DEG:
        # Handle boundary wrap-around
        if start_deg > end_deg:  # Crosses 0°
            if wrapped >= start_deg or wrapped <= end_deg + GANDANTA_ORB_DEG:
                return True
            if (
                wrapped <= start_deg + GANDANTA_ORB_DEG
                or wrapped >= end_deg - GANDANTA_ORB_DEG
            ):
                return True
        else:
            if start_deg - GANDANTA_ORB_DEG <= wrapped <= end_deg + GANDANTA_ORB_DEG:
                return True

    return False


def _compute_gatekeeper_score(
    asc_info: AxisInfo,
    mc_info: AxisInfo,
    planet_longitudes: dict[int, float],
    cusps: list[float],
    profile_config: dict[str, Any],
) -> GatekeeperScore:
    """Compute gatekeeper (axis-lord condition) score.

    Args:
        asc_info: Ascendant axis information
        mc_info: Midheaven axis information
        planet_longitudes: Current planet positions
        cusps: House cusp positions
        profile_config: Model profile configuration

    Returns:
        GatekeeperScore with detailed analysis
    """

    def _get_planet_house(longitude: float) -> int:
        """Determine house for planet longitude."""
        for i in range(12):
            cusp_start = cusps[i]
            cusp_end = cusps[(i + 1) % 12]

            if cusp_start <= cusp_end:
                if cusp_start <= longitude < cusp_end:
                    return i + 1
            else:  # Crosses 0°
                if longitude >= cusp_start or longitude < cusp_end:
                    return i + 1
        return 1

    def _compute_planet_strength(planet_id: int, longitude: float) -> float:
        """Compute relative strength of planet."""
        house = _get_planet_house(longitude)

        # Angular houses (1,4,7,10) get strength bonus
        angular_bonus = 0.15 if house in [1, 4, 7, 10] else 0.0

        # TODO: Add dignity calculations (own sign, exaltation, etc.)
        dignity_bonus = 0.0

        # Base strength
        base_strength = 1.0

        return base_strength + angular_bonus + dignity_bonus

    # Analyze ASC lord strength
    asc_lord_id = asc_info.nakshatra_lord
    asc_lord_longitude = planet_longitudes.get(asc_lord_id, 0.0)
    asc_lord_strength = _compute_planet_strength(asc_lord_id, asc_lord_longitude)

    # Analyze MC lord strength
    mc_lord_id = mc_info.nakshatra_lord
    mc_lord_longitude = planet_longitudes.get(mc_lord_id, 0.0)
    mc_lord_strength = _compute_planet_strength(mc_lord_id, mc_lord_longitude)

    # Compute overall gatekeeper score (average of axis lord strengths)
    raw_score = (asc_lord_strength + mc_lord_strength) / 2.0

    # Apply bounds to keep within GATEKEEPER_BOUNDS
    min_score, max_score = GATEKEEPER_BOUNDS
    overall_score = max(min_score, min(max_score, raw_score))

    # Compute component bonuses for analysis
    dignity_bonus = 0.0  # TODO: Implement dignity calculations
    angularity_bonus = (
        0.05
        if any(
            _get_planet_house(planet_longitudes.get(pid, 0.0)) in [1, 4, 7, 10]
            for pid in [asc_lord_id, mc_lord_id]
        )
        else 0.0
    )

    return GatekeeperScore(
        asc_lord_strength=asc_lord_strength,
        mc_lord_strength=mc_lord_strength,
        overall_score=overall_score,
        dignity_bonus=dignity_bonus,
        angularity_bonus=angularity_bonus,
    )


async def get_access_geometry(
    ts_eff_minute: datetime,
    latitude: float,
    longitude: float,
    house_system: str,
    model_version: str,
    model_profile: str,
    altitude: float | None = None,
    use_cache: bool = True,
) -> AccessGeometry:
    """Compute complete access geometry for location.

    Args:
        ts_eff_minute: Effective timestamp (same as sky_state_service)
        latitude: Location latitude in degrees
        longitude: Location longitude in degrees
        house_system: House system to use ("KP" -> "PLACIDUS")
        model_version: Model version for cache key
        model_profile: Model profile for cache key
        altitude: Elevation above sea level in meters (optional)
        use_cache: Whether to use caching

    Returns:
        Complete AccessGeometry object
    """
    import time

    from refactor.facade import get_positions

    start_time = time.perf_counter()

    # Validate latitude bounds
    if should_apply_polar_hard_limit(latitude):
        raise ValueError(f"Latitude {latitude}° exceeds polar calculation limit")

    # Serialization helpers for cache safety (JSON)
    def _axis_to_dict(ax: AxisInfo) -> dict[str, Any]:
        return {
            "degree": ax.degree,
            "nakshatra": ax.nakshatra,
            "pada": ax.pada,
            "nakshatra_lord": ax.nakshatra_lord,
            "sub_lord": ax.sub_lord,
            "sub_sub_lord": ax.sub_sub_lord,
        }

    def _axis_from_dict(d: dict[str, Any]) -> AxisInfo:
        return AxisInfo(
            degree=float(d.get("degree", 0.0)),
            nakshatra=int(d.get("nakshatra", 0)),
            pada=int(d.get("pada", 0)),
            nakshatra_lord=int(d.get("nakshatra_lord", 0)),
            sub_lord=int(d.get("sub_lord", 0)),
            sub_sub_lord=int(d.get("sub_sub_lord", 0)),
        )

    def _gate_to_dict(g: GatekeeperScore) -> dict[str, Any]:
        return {
            "asc_lord_strength": g.asc_lord_strength,
            "mc_lord_strength": g.mc_lord_strength,
            "overall_score": g.overall_score,
            "dignity_bonus": g.dignity_bonus,
            "angularity_bonus": g.angularity_bonus,
        }

    def _gate_from_dict(d: dict[str, Any]) -> GatekeeperScore:
        return GatekeeperScore(
            asc_lord_strength=float(d.get("asc_lord_strength", 0.0)),
            mc_lord_strength=float(d.get("mc_lord_strength", 0.0)),
            overall_score=float(d.get("overall_score", 0.0)),
            dignity_bonus=float(d.get("dignity_bonus", 0.0)),
            angularity_bonus=float(d.get("angularity_bonus", 0.0)),
        )

    def _access_to_dict(a: AccessGeometry) -> dict[str, Any]:
        return {
            "timestamp": a.timestamp.replace(microsecond=0).isoformat(),
            "latitude": a.latitude,
            "longitude": a.longitude,
            "model_version": a.model_version,
            "model_profile": a.model_profile,
            "asc": _axis_to_dict(a.asc),
            "mc": _axis_to_dict(a.mc),
            "desc": _axis_to_dict(a.desc),
            "ic": _axis_to_dict(a.ic),
            "cusps": list(a.cusps),
            "house_system": a.house_system,
            "is_day_birth": a.is_day_birth,
            "local_sidereal_time_hours": a.local_sidereal_time_hours,
            "altitude_above_sea_level": a.altitude_above_sea_level,
            "gatekeeper": _gate_to_dict(a.gatekeeper),
            "gandanta_axis": a.gandanta_axis,
            "gandanta_asc": a.gandanta_asc,
            "gandanta_mc": a.gandanta_mc,
            "latitude_reliability": a.latitude_reliability,
            "polar_risk": a.polar_risk,
            "computation_time_ms": a.computation_time_ms,
            "cache_hit": a.cache_hit,
        }

    def _access_from_dict(d: dict[str, Any]) -> AccessGeometry:
        return AccessGeometry(
            timestamp=datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")),
            latitude=float(d.get("latitude", 0.0)),
            longitude=float(d.get("longitude", 0.0)),
            model_version=d.get("model_version", MODEL_VERSION),
            model_profile=d.get("model_profile", "default"),
            asc=_axis_from_dict(d.get("asc", {})),
            mc=_axis_from_dict(d.get("mc", {})),
            desc=_axis_from_dict(d.get("desc", {})),
            ic=_axis_from_dict(d.get("ic", {})),
            cusps=[float(x) for x in d.get("cusps", [0.0] * 12)],
            house_system=d.get("house_system", "KP"),
            is_day_birth=bool(d.get("is_day_birth", True)),
            local_sidereal_time_hours=float(d.get("local_sidereal_time_hours", 0.0)),
            altitude_above_sea_level=(
                float(d["altitude_above_sea_level"])
                if d.get("altitude_above_sea_level") is not None
                else None
            ),
            gatekeeper=_gate_from_dict(d.get("gatekeeper", {})),
            gandanta_axis=bool(d.get("gandanta_axis", False)),
            gandanta_asc=bool(d.get("gandanta_asc", False)),
            gandanta_mc=bool(d.get("gandanta_mc", False)),
            latitude_reliability=d.get("latitude_reliability", "high"),
            polar_risk=bool(d.get("polar_risk", False)),
            computation_time_ms=float(d.get("computation_time_ms", 0.0)),
            cache_hit=bool(d.get("cache_hit", False)),
        )

    # Setup caching
    cache = CacheService(system="GLR_ACCESS")
    lat_key = round(latitude, 6)
    lon_key = round(longitude, 6)
    cache_key = f"access:{get_model_fingerprint(model_profile)}:{ts_eff_minute.isoformat()}:{lat_key}:{lon_key}:{house_system}"
    cache_hit = False

    # Try cache first
    if use_cache:
        cached_result = await cache.get(cache_key)
        if cached_result:
            if isinstance(cached_result, dict) and "timestamp" in cached_result:
                obj = _access_from_dict(cached_result)
                obj.cache_hit = True
                return obj
            else:
                try:
                    await cache.delete(cache_key)
                except Exception:
                    pass

    # Get profile configuration
    profile_config = get_profile_config(model_profile)

    # Normalize house system
    normalized_house_system = house_system.upper()
    if normalized_house_system == "KP":
        normalized_house_system = "PLACIDUS"

    # Compute houses (this uses the same effective timestamp)
    houses = compute_houses(
        ts_eff_minute,
        latitude,
        longitude,
        system=normalized_house_system,
        topocentric=False,
    )

    # Extract angles
    asc_degree = houses.asc
    mc_degree = houses.mc
    desc_degree = _wrap_360(asc_degree + 180.0)
    ic_degree = _wrap_360(mc_degree + 180.0)

    # Compute axis information with nakshatra/lords
    asc_info = _compute_axis_info(asc_degree)
    mc_info = _compute_axis_info(mc_degree)
    desc_info = _compute_axis_info(desc_degree)
    ic_info = _compute_axis_info(ic_degree)

    # Get current planet positions for gatekeeper analysis
    planet_longitudes = {}
    sun_longitude = None

    try:
        # Get Sun for day/night determination
        sun_pos = get_positions(ts_eff_minute, planet_id=1, apply_kp_offset=False)
        sun_longitude = sun_pos.longitude
        planet_longitudes[1] = sun_longitude

        # Get other planets for gatekeeper analysis
        for planet_id in [2, 3, 4, 5, 6, 7, 8, 9]:  # Skip Sun (already got it)
            try:
                pos = get_positions(
                    ts_eff_minute, planet_id=planet_id, apply_kp_offset=False
                )
                planet_longitudes[planet_id] = pos.longitude
            except Exception:
                continue  # Skip if planet position unavailable

    except Exception:
        sun_longitude = 0.0  # Fallback
        planet_longitudes[1] = 0.0

    # Determine day/night birth
    is_day = (
        _is_day_birth(sun_longitude or 0.0, asc_degree, mc_degree)
        if sun_longitude
        else True
    )

    # Compute Local Sidereal Time
    lst_hours = _compute_local_sidereal_time(longitude, ts_eff_minute)

    # Compute gatekeeper score
    gatekeeper_score = _compute_gatekeeper_score(
        asc_info, mc_info, planet_longitudes, houses.cusps, profile_config
    )

    # Detect Gandānta positions
    gandanta_asc = _detect_gandanta_position(asc_degree)
    gandanta_mc = _detect_gandanta_position(mc_degree)
    gandanta_any_axis = (
        gandanta_asc
        or gandanta_mc
        or _detect_gandanta_position(desc_degree)
        or _detect_gandanta_position(ic_degree)
    )

    # Assess reliability
    lat_reliability = get_latitude_reliability(latitude)
    polar_risk = abs(latitude) > 60.0  # Flag higher latitudes as risky

    # Create access geometry object
    computation_time = (time.perf_counter() - start_time) * 1000

    access_geometry = AccessGeometry(
        timestamp=ts_eff_minute,
        latitude=latitude,
        longitude=longitude,
        model_version=model_version,
        model_profile=model_profile,
        asc=asc_info,
        mc=mc_info,
        desc=desc_info,
        ic=ic_info,
        cusps=houses.cusps,
        house_system=house_system,
        is_day_birth=is_day,
        local_sidereal_time_hours=lst_hours,
        altitude_above_sea_level=altitude,
        gatekeeper=gatekeeper_score,
        gandanta_axis=gandanta_any_axis,
        gandanta_asc=gandanta_asc,
        gandanta_mc=gandanta_mc,
        latitude_reliability=lat_reliability,
        polar_risk=polar_risk,
        computation_time_ms=computation_time,
        cache_hit=cache_hit,
    )

    # Cache result
    if use_cache:
        await cache.set(
            cache_key, _access_to_dict(access_geometry), ttl=CACHE_TTL_ACCESS
        )

    return access_geometry


def get_axis_nakshatra_lords(access: AccessGeometry) -> dict[str, dict[str, int]]:
    """Extract nakshatra lords for all axes.

    Args:
        access: AccessGeometry object

    Returns:
        Dictionary mapping axis names to lord information
    """
    return {
        "asc": {
            "nakshatra": access.asc.nakshatra,
            "nl": access.asc.nakshatra_lord,
            "sl": access.asc.sub_lord,
            "sl2": access.asc.sub_sub_lord,
        },
        "mc": {
            "nakshatra": access.mc.nakshatra,
            "nl": access.mc.nakshatra_lord,
            "sl": access.mc.sub_lord,
            "sl2": access.mc.sub_sub_lord,
        },
        "desc": {
            "nakshatra": access.desc.nakshatra,
            "nl": access.desc.nakshatra_lord,
            "sl": access.desc.sub_lord,
            "sl2": access.desc.sub_sub_lord,
        },
        "ic": {
            "nakshatra": access.ic.nakshatra,
            "nl": access.ic.nakshatra_lord,
            "sl": access.ic.sub_lord,
            "sl2": access.ic.sub_sub_lord,
        },
    }


def compute_planet_to_angle_distances(
    planet_longitude: float, access: AccessGeometry
) -> dict[str, float]:
    """Compute angular distances from planet to all chart angles.

    Args:
        planet_longitude: Planet position in degrees
        access: AccessGeometry object

    Returns:
        Dictionary of angle names to distances in degrees
    """

    def min_arc_distance(pos1: float, pos2: float) -> float:
        """Minimum arc distance between two positions."""
        diff = abs(pos1 - pos2)
        return min(diff, 360.0 - diff)

    return {
        "asc": min_arc_distance(planet_longitude, access.asc.degree),
        "mc": min_arc_distance(planet_longitude, access.mc.degree),
        "desc": min_arc_distance(planet_longitude, access.desc.degree),
        "ic": min_arc_distance(planet_longitude, access.ic.degree),
    }


def get_strongest_angle_connection(
    planet_longitude: float, access: AccessGeometry, max_orb: float = 10.0
) -> dict[str, Any] | None:
    """Find strongest connection between planet and chart angles.

    Args:
        planet_longitude: Planet position in degrees
        access: AccessGeometry object
        max_orb: Maximum orb to consider (degrees)

    Returns:
        Dictionary with strongest connection details, or None
    """
    distances = compute_planet_to_angle_distances(planet_longitude, access)

    # Find closest angle within orb
    closest_angle = None
    closest_distance = max_orb + 1.0

    for angle_name, distance in distances.items():
        if distance < closest_distance:
            closest_distance = distance
            closest_angle = angle_name

    if closest_angle and closest_distance <= max_orb:
        return {
            "angle": closest_angle,
            "distance": closest_distance,
            "orb_ratio": closest_distance / max_orb,
            "strength": 1.0 - (closest_distance / max_orb),
        }

    return None


# Export main interface
__all__ = [
    "AccessGeometry",
    "AxisInfo",
    "GatekeeperScore",
    "compute_planet_to_angle_distances",
    "get_access_geometry",
    "get_axis_nakshatra_lords",
    "get_strongest_angle_connection",
]
