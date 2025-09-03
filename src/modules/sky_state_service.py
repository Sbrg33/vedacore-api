#!/usr/bin/env python3
"""
Global Locality Research - Sky State Service
Per-minute global sky calculations shared across all locations.

Implements location-independent celestial state for activation field mapping.
Single-source-of-truth for timestamp alignment with access_service.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple

from app.services.unified_cache import UnifiedCache
from constants.activation_model import (
    CACHE_TTL_SKY_STATE,
    ECLIPSE_EXACT_CORRIDOR_DEG,
    ECLIPSE_WARNING_CORRIDOR_DEG,
    MODEL_VERSION,
    PHASE_INFLUENCE_WEIGHT,
    get_combustion_radius,
    get_model_fingerprint,
    get_profile_config,
)
from refactor.constants import PLANET_IDS, PLANET_NAMES
from refactor.facade import get_positions


class PlanetState(NamedTuple):
    """State of a single planet"""

    longitude: float
    speed: float
    retrograde: bool
    combustion_distance: float | None
    station_within_24h: bool


@dataclass
class SkyState:
    """Complete sky state for activation calculations"""

    timestamp: datetime
    model_version: str
    model_profile: str

    # Sun-Moon phase data
    sun_moon_phase_deg: float  # Angular separation (Φ in formula)
    phase_multiplier: float  # Computed phase influence on Moon term

    # Eclipse & Node data
    eclipse_warning_corridor: bool  # Within 12° of node axis
    eclipse_exact_corridor: bool  # Within 1° of node axis
    node_axis_longitude: float  # Mean longitude of node axis

    # Planet states
    planet_states: dict[int, PlanetState]

    # Global flags
    any_planet_stationary: bool
    any_planet_retrograde: bool
    any_planet_combust: bool

    # Angular speeds (for time-to-exact calculations)
    angular_speeds: dict[int, float]  # degrees per day

    # Computation metadata
    computation_time_ms: float
    cache_hit: bool


def _compute_sun_moon_phase(
    sun_longitude: float, moon_longitude: float
) -> tuple[float, float]:
    """Compute Sun-Moon phase and influence multiplier.

    Args:
        sun_longitude: Sun position in degrees
        moon_longitude: Moon position in degrees

    Returns:
        Tuple of (phase_degrees, phase_multiplier)
    """
    # Angular separation
    phase_deg = abs(moon_longitude - sun_longitude)
    if phase_deg > 180.0:
        phase_deg = 360.0 - phase_deg

    # Phase influence on Moon term (Φ factor)
    # New Moon (0°) = maximum influence, Full Moon (180°) = minimum influence
    phase_radians = math.radians(phase_deg)
    phase_factor = 0.5 * (
        1.0 + math.cos(phase_radians)
    )  # 1.0 at New Moon, 0.0 at Full Moon

    # Apply phase weight to get final multiplier
    phase_multiplier = 1.0 + (phase_factor - 0.5) * PHASE_INFLUENCE_WEIGHT

    return phase_deg, phase_multiplier


def _detect_station_window(planet_id: int, current_speed: float) -> bool:
    """Detect if planet is within ±24h of station (speed change).

    Args:
        planet_id: Planet ID
        current_speed: Current daily motion in degrees

    Returns:
        True if within station window
    """
    # Simple heuristic: planet is near station if speed is very low
    # TODO: Implement proper ephemeris event detection for production
    station_threshold_speeds = {
        1: 0.1,  # Sun (very slow indicates solstice approach)
        2: 5.0,  # Moon (very slow for Moon)
        3: 0.05,  # Jupiter
        4: 0.02,  # Rahu (always retrograde, but speed changes)
        5: 0.3,  # Mercury
        6: 0.3,  # Venus
        7: 0.02,  # Ketu (always retrograde, but speed changes)
        8: 0.02,  # Saturn
        9: 0.1,  # Mars
    }

    threshold = station_threshold_speeds.get(planet_id, 0.1)
    return abs(current_speed) < threshold


def _compute_combustion_distance(
    planet_id: int, planet_longitude: float, sun_longitude: float
) -> float | None:
    """Compute distance from Sun for combustion analysis.

    Args:
        planet_id: Planet ID
        planet_longitude: Planet position in degrees
        sun_longitude: Sun position in degrees

    Returns:
        Distance from Sun in degrees, or None if Sun
    """
    if planet_id == 1:  # Sun doesn't combust itself
        return None

    # Angular distance from Sun
    distance = abs(planet_longitude - sun_longitude)
    if distance > 180.0:
        distance = 360.0 - distance

    return distance


def _detect_eclipse_corridors(
    sun_longitude: float, rahu_longitude: float
) -> tuple[bool, bool, float]:
    """Detect eclipse corridors based on Sun-Rahu axis.

    Args:
        sun_longitude: Sun position in degrees
        rahu_longitude: Rahu (True Node) position in degrees

    Returns:
        Tuple of (warning_corridor, exact_corridor, node_axis)
    """
    # Node axis is Rahu-Ketu line
    node_axis = rahu_longitude

    # Distance from Sun to node axis
    distance_to_axis = abs(sun_longitude - node_axis)
    if distance_to_axis > 180.0:
        distance_to_axis = 360.0 - distance_to_axis

    # Check alternative axis (opposite side)
    alt_distance = abs(distance_to_axis - 180.0)
    distance_to_axis = min(distance_to_axis, alt_distance)

    warning_corridor = distance_to_axis <= ECLIPSE_WARNING_CORRIDOR_DEG
    exact_corridor = distance_to_axis <= ECLIPSE_EXACT_CORRIDOR_DEG

    return warning_corridor, exact_corridor, node_axis


def _compute_angular_speeds(planet_states: dict[int, PlanetState]) -> dict[int, float]:
    """Extract angular speeds from planet states.

    Args:
        planet_states: Dictionary of planet states

    Returns:
        Dictionary of planet_id -> speed in degrees per day
    """
    return {planet_id: state.speed for planet_id, state in planet_states.items()}


async def get_sky_state(
    ts_eff_minute: datetime,
    model_version: str,
    model_profile: str,
    use_cache: bool = True,
) -> SkyState:
    """Get complete sky state for effective minute.

    Args:
        ts_eff_minute: Effective timestamp (KP policy applied, minute bucket)
        model_version: Model version for cache key
        model_profile: Model profile for cache key
        use_cache: Whether to use caching

    Returns:
        Complete SkyState object
    """
    import time

    start_time = time.perf_counter()

    cache = UnifiedCache(system="GLR_SKY_STATE")
    cache_key = (
        f"sky_state:{get_model_fingerprint(model_profile)}:{ts_eff_minute.isoformat()}"
    )
    cache_hit = False

    # Serialization helpers for cache safety (JSON)
    def _sky_state_to_dict(s: SkyState) -> dict[str, Any]:
        return {
            "timestamp": s.timestamp.replace(microsecond=0).isoformat(),
            "model_version": s.model_version,
            "model_profile": s.model_profile,
            "sun_moon_phase_deg": s.sun_moon_phase_deg,
            "phase_multiplier": s.phase_multiplier,
            "eclipse_warning_corridor": s.eclipse_warning_corridor,
            "eclipse_exact_corridor": s.eclipse_exact_corridor,
            "node_axis_longitude": s.node_axis_longitude,
            "planet_states": {
                str(pid): {
                    "longitude": ps.longitude,
                    "speed": ps.speed,
                    "retrograde": ps.retrograde,
                    "combustion_distance": ps.combustion_distance,
                    "station_within_24h": ps.station_within_24h,
                }
                for pid, ps in s.planet_states.items()
            },
            "any_planet_stationary": s.any_planet_stationary,
            "any_planet_retrograde": s.any_planet_retrograde,
            "any_planet_combust": s.any_planet_combust,
            "angular_speeds": {str(pid): spd for pid, spd in s.angular_speeds.items()},
            "computation_time_ms": s.computation_time_ms,
            "cache_hit": s.cache_hit,
        }

    def _sky_state_from_dict(d: dict[str, Any]) -> SkyState:
        ps_map: dict[int, PlanetState] = {}
        for k, v in d.get("planet_states", {}).items():
            ps_map[int(k)] = PlanetState(
                longitude=float(v.get("longitude", 0.0)),
                speed=float(v.get("speed", 0.0)),
                retrograde=bool(v.get("retrograde", False)),
                combustion_distance=(
                    float(v["combustion_distance"])
                    if v.get("combustion_distance") is not None
                    else None
                ),
                station_within_24h=bool(v.get("station_within_24h", False)),
            )
        ang_speeds = {int(k): float(v) for k, v in d.get("angular_speeds", {}).items()}
        return SkyState(
            timestamp=datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")),
            model_version=d.get("model_version", MODEL_VERSION),
            model_profile=d.get("model_profile", "default"),
            sun_moon_phase_deg=float(d.get("sun_moon_phase_deg", 0.0)),
            phase_multiplier=float(d.get("phase_multiplier", 1.0)),
            eclipse_warning_corridor=bool(d.get("eclipse_warning_corridor", False)),
            eclipse_exact_corridor=bool(d.get("eclipse_exact_corridor", False)),
            node_axis_longitude=float(d.get("node_axis_longitude", 0.0)),
            planet_states=ps_map,
            any_planet_stationary=bool(d.get("any_planet_stationary", False)),
            any_planet_retrograde=bool(d.get("any_planet_retrograde", False)),
            any_planet_combust=bool(d.get("any_planet_combust", False)),
            angular_speeds=ang_speeds,
            computation_time_ms=float(d.get("computation_time_ms", 0.0)),
            cache_hit=bool(d.get("cache_hit", False)),
        )

    # Try cache first
    if use_cache:
        cached_result = await cache.get(cache_key)
        if cached_result:
            # Backward compatibility: ignore legacy string blobs written by JSON default(str)
            if isinstance(cached_result, dict) and "timestamp" in cached_result:
                obj = _sky_state_from_dict(cached_result)
                obj.cache_hit = True
                return obj
            else:
                # Corrupted/legacy cache entry — delete and recompute
                try:
                    await cache.delete(cache_key)
                except Exception:
                    pass

    # Compute sky state
    profile_config = get_profile_config(model_profile)

    # Get all planet positions at effective timestamp
    planet_states = {}
    sun_longitude = None
    moon_longitude = None
    rahu_longitude = None

    for planet_id in PLANET_IDS.keys():
        try:
            # Get position with KP offset already applied in ts_eff_minute
            pos_data = get_positions(
                ts_eff_minute, planet_id=planet_id, apply_kp_offset=False
            )

            # Store key positions for global calculations
            if planet_id == 1:  # Sun
                sun_longitude = pos_data.longitude
            elif planet_id == 2:  # Moon
                moon_longitude = pos_data.longitude
            elif planet_id == 4:  # Rahu
                rahu_longitude = pos_data.longitude

            # Check if retrograde
            is_retrograde = pos_data.speed < 0

            # Check station window
            is_stationary = _detect_station_window(planet_id, pos_data.speed)

            # Compute combustion distance
            combustion_dist = None
            if sun_longitude is not None:
                combustion_dist = _compute_combustion_distance(
                    planet_id, pos_data.longitude, sun_longitude
                )

            planet_states[planet_id] = PlanetState(
                longitude=pos_data.longitude,
                speed=pos_data.speed,
                retrograde=is_retrograde,
                combustion_distance=combustion_dist,
                station_within_24h=is_stationary,
            )

        except Exception:
            # Log error but continue with other planets
            continue

    # Compute Sun-Moon phase if both available
    phase_deg = 0.0
    phase_multiplier = 1.0
    if sun_longitude is not None and moon_longitude is not None:
        phase_deg, phase_multiplier = _compute_sun_moon_phase(
            sun_longitude, moon_longitude
        )

    # Detect eclipse corridors if Sun and Rahu available
    eclipse_warning = False
    eclipse_exact = False
    node_axis = 0.0
    if sun_longitude is not None and rahu_longitude is not None:
        eclipse_warning, eclipse_exact, node_axis = _detect_eclipse_corridors(
            sun_longitude, rahu_longitude
        )

    # Update combustion distances now that we have Sun position
    if sun_longitude is not None:
        for planet_id, state in planet_states.items():
            if planet_id != 1:  # Skip Sun itself
                combustion_dist = _compute_combustion_distance(
                    planet_id, state.longitude, sun_longitude
                )
                # Replace the state with updated combustion distance
                planet_states[planet_id] = PlanetState(
                    longitude=state.longitude,
                    speed=state.speed,
                    retrograde=state.retrograde,
                    combustion_distance=combustion_dist,
                    station_within_24h=state.station_within_24h,
                )

    # Compute global flags
    any_stationary = any(state.station_within_24h for state in planet_states.values())
    any_retrograde = any(state.retrograde for state in planet_states.values())
    any_combust = any(
        state.combustion_distance is not None
        and state.combustion_distance <= get_combustion_radius(planet_id)
        for planet_id, state in planet_states.items()
    )

    # Compute angular speeds
    angular_speeds = _compute_angular_speeds(planet_states)

    # Create sky state object
    computation_time = (time.perf_counter() - start_time) * 1000

    sky_state = SkyState(
        timestamp=ts_eff_minute,
        model_version=model_version,
        model_profile=model_profile,
        sun_moon_phase_deg=phase_deg,
        phase_multiplier=phase_multiplier,
        eclipse_warning_corridor=eclipse_warning,
        eclipse_exact_corridor=eclipse_exact,
        node_axis_longitude=node_axis,
        planet_states=planet_states,
        any_planet_stationary=any_stationary,
        any_planet_retrograde=any_retrograde,
        any_planet_combust=any_combust,
        angular_speeds=angular_speeds,
        computation_time_ms=computation_time,
        cache_hit=cache_hit,
    )

    # Cache result (JSON-serializable)
    if use_cache:
        await cache.set(
            cache_key, _sky_state_to_dict(sky_state), ttl=CACHE_TTL_SKY_STATE
        )

    return sky_state


def get_planet_state(sky_state: SkyState, planet_id: int) -> PlanetState | None:
    """Get state for specific planet from sky state.

    Args:
        sky_state: Complete sky state
        planet_id: Planet ID to retrieve

    Returns:
        PlanetState or None if not found
    """
    return sky_state.planet_states.get(planet_id)


def is_planet_combust(sky_state: SkyState, planet_id: int) -> bool:
    """Check if planet is combusted by Sun.

    Args:
        sky_state: Complete sky state
        planet_id: Planet ID to check

    Returns:
        True if planet is within combustion radius of Sun
    """
    state = get_planet_state(sky_state, planet_id)
    if state is None or state.combustion_distance is None:
        return False

    combustion_radius = get_combustion_radius(planet_id)
    return state.combustion_distance <= combustion_radius


def get_moon_void_of_course_status(sky_state: SkyState) -> dict[str, Any]:
    """Determine if Moon is Void of Course using major aspects only.

    Args:
        sky_state: Complete sky state

    Returns:
        Dictionary with VoC status and details
    """
    from constants.activation_model import ASPECT_ORBS_DEG, MAJOR_ASPECTS_DEG

    moon_state = get_planet_state(sky_state, 2)  # Moon
    if moon_state is None:
        return {"is_voc": False, "reason": "moon_position_unavailable"}

    moon_longitude = moon_state.longitude
    moon_sign = int(moon_longitude // 30)
    next_sign_boundary = (moon_sign + 1) * 30

    # Check for applying major aspects to other planets before sign change
    has_applying_major = False
    next_aspect_details = None

    for planet_id, planet_state in sky_state.planet_states.items():
        if planet_id == 2:  # Skip Moon itself
            continue

        planet_longitude = planet_state.longitude

        # Calculate angular separation
        separation = abs(moon_longitude - planet_longitude)
        if separation > 180.0:
            separation = 360.0 - separation

        # Check each major aspect
        for aspect_deg in MAJOR_ASPECTS_DEG:
            aspect_orb = ASPECT_ORBS_DEG.get("conjunction", 5.0)  # Default orb
            if aspect_deg == 60.0:
                aspect_orb = ASPECT_ORBS_DEG.get("sextile", 3.0)
            elif aspect_deg == 90.0:
                aspect_orb = ASPECT_ORBS_DEG.get("square", 4.0)
            elif aspect_deg == 120.0:
                aspect_orb = ASPECT_ORBS_DEG.get("trine", 4.0)
            elif aspect_deg == 180.0:
                aspect_orb = ASPECT_ORBS_DEG.get("opposition", 5.0)

            orb_to_aspect = abs(separation - aspect_deg)

            if orb_to_aspect <= aspect_orb:
                # Check if applying (Moon moving toward exact aspect)
                # Simplified: if Moon is faster, it's likely applying
                if moon_state.speed > planet_state.speed:
                    has_applying_major = True
                    next_aspect_details = {
                        "planet": PLANET_NAMES.get(planet_id, str(planet_id)),
                        "aspect": aspect_deg,
                        "orb": orb_to_aspect,
                        "applying": True,
                    }
                    break

        if has_applying_major:
            break

    # Moon is VoC if no applying major aspects before sign change
    is_voc = not has_applying_major

    degrees_to_sign_change = next_sign_boundary - moon_longitude
    if degrees_to_sign_change < 0:  # Handle 30° boundary wrap
        degrees_to_sign_change += 30

    return {
        "is_voc": is_voc,
        "degrees_to_sign_change": degrees_to_sign_change,
        "next_aspect": next_aspect_details,
        "moon_sign": moon_sign + 1,  # 1-12 for display
        "reason": "no_applying_majors" if is_voc else "has_applying_major",
    }


def get_mercury_retrograde_status(sky_state: SkyState) -> dict[str, Any]:
    """Get Mercury retrograde status for coherence penalty.

    Args:
        sky_state: Complete sky state

    Returns:
        Dictionary with Mercury retrograde details
    """
    mercury_state = get_planet_state(sky_state, 5)  # Mercury
    if mercury_state is None:
        return {"is_retrograde": False, "reason": "mercury_position_unavailable"}

    return {
        "is_retrograde": mercury_state.retrograde,
        "speed": mercury_state.speed,
        "reason": "retrograde_motion" if mercury_state.retrograde else "direct_motion",
    }


# Export main interface
__all__ = [
    "PlanetState",
    "SkyState",
    "get_mercury_retrograde_status",
    "get_moon_void_of_course_status",
    "get_planet_state",
    "get_sky_state",
    "is_planet_combust",
]
