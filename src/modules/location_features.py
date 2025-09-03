"""
modules/location_features.py — Location Features Orchestrator

Computes per-location features:
- Angles (Asc/MC/Desc/IC), houses with KP policy alignment
- Per-planet: ecl_lon, ra/dec, topocentric alt/az, house, distance-to-angles, cusp distance
- Derived: aspect-to-angles, declination summary, parans (empty for now)
- Indices: angular_load (primary), aspect_to_angle_load, declinational_emphasis, house_emphasis

Production implementation with PM-specified optimizations and edge case handling.
"""

from __future__ import annotations

import math

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

# Core VedaCore dependencies
from app.services.unified_cache import UnifiedCache

# Location features specific imports
from constants.location_features import (
    APPLYING_ASPECT_BONUS,
    ASPECT_ANGLES_DEG,
    LST_SEGMENTS,
)
from modules.location_features_helpers import (
    angular_load,
    aspect_orb,
    house_class,
    min_arc,
    wrap_deg,
)
from refactor.constants import PLANET_IDS, PLANET_NAMES
from refactor.facade import get_positions
from refactor.houses import compute_houses


def _get_kp_effective_timestamp(ts: datetime, apply_kp_offset: bool = True) -> datetime:
    """Get KP-aligned effective timestamp matching facade.get_positions() policy."""
    if apply_kp_offset:
        # Apply same 307-second offset as get_positions() when apply_kp_offset=True
        return ts + timedelta(seconds=307)
    return ts


# Metrics will be handled by the router to avoid duplication


@dataclass
class Location:
    id: str
    name: str | None
    lat: float
    lon: float
    elevation: float | None = None


def _compute_lst_segment(lst_hours: float) -> dict[str, Any]:
    """Compute LST segment from local sidereal time in hours."""
    segment_index = int((lst_hours % 24.0) / 3.0)  # 8 segments of 3 hours each
    return {"num": segment_index, "label": LST_SEGMENTS[segment_index]}


def _compute_topocentric_altaz(
    ra_hours: float, dec_deg: float, lat: float, lon: float, lst_hours: float
) -> tuple[float, float]:
    """Compute topocentric altitude and azimuth from RA/Dec."""
    # Convert to radians
    ra_rad = math.radians(ra_hours * 15.0)  # RA hours to degrees to radians
    dec_rad = math.radians(dec_deg)
    lat_rad = math.radians(lat)
    lst_rad = math.radians(lst_hours * 15.0)  # LST hours to degrees to radians

    # Hour angle
    ha_rad = lst_rad - ra_rad

    # Altitude calculation
    alt_rad = math.asin(
        math.sin(dec_rad) * math.sin(lat_rad)
        + math.cos(dec_rad) * math.cos(lat_rad) * math.cos(ha_rad)
    )
    alt_deg = math.degrees(alt_rad)

    # Azimuth calculation
    az_rad = math.atan2(
        -math.cos(dec_rad) * math.sin(ha_rad),
        math.sin(dec_rad) * math.cos(lat_rad)
        - math.cos(dec_rad) * math.sin(lat_rad) * math.cos(ha_rad),
    )
    az_deg = wrap_deg(math.degrees(az_rad))

    return alt_deg, az_deg


def _compute_house_membership(planet_lon: float, cusps: list[float]) -> int:
    """Determine which house a planet is in based on cusp positions."""
    wrapped_lon = wrap_deg(planet_lon)

    for i in range(12):
        cusp_start = cusps[i]
        cusp_end = cusps[(i + 1) % 12]

        # Handle wrap-around case
        if cusp_start <= cusp_end:
            if cusp_start <= wrapped_lon < cusp_end:
                return i + 1
        else:  # Crosses 0°
            if wrapped_lon >= cusp_start or wrapped_lon < cusp_end:
                return i + 1

    return 1  # Default to first house


def _compute_cusp_distance(planet_lon: float, cusps: list[float]) -> float:
    """Compute distance to nearest house cusp."""
    wrapped_lon = wrap_deg(planet_lon)
    min_distance = 180.0

    for cusp in cusps:
        distance = min_arc(wrapped_lon, cusp)
        min_distance = min(min_distance, distance)

    return min_distance


def _find_aspects_to_angles(
    planet_lon: float, asc: float, mc: float
) -> list[dict[str, Any]]:
    """Find aspects from planet to ASC/MC angles."""
    aspects = []

    for angle_name, angle_pos in [("asc", asc), ("mc", mc)]:
        for aspect_name, aspect_angle in ASPECT_ANGLES_DEG.items():
            expected_pos = wrap_deg(angle_pos + aspect_angle)
            orb = min_arc(planet_lon, expected_pos)
            max_orb = aspect_orb(aspect_name)

            if orb <= max_orb:
                aspects.append(
                    {
                        "angle": angle_name,
                        "type": aspect_name,
                        "orb": round(orb, 2),
                        "applying": False,  # Will be computed later with delta-t check
                    }
                )

    return aspects


def _check_applying_status(
    planet_lon: float,
    asc: float,
    mc: float,
    planet_lon_next: float,
    asc_next: float,
    mc_next: float,
    aspect: dict[str, Any],
) -> bool:
    """Check if aspect is applying by comparing orbs at t and t+dt."""
    angle_pos = asc if aspect["angle"] == "asc" else mc
    angle_pos_next = asc_next if aspect["angle"] == "asc" else mc_next

    aspect_angle = ASPECT_ANGLES_DEG[aspect["type"]]
    expected_pos = wrap_deg(angle_pos + aspect_angle)
    expected_pos_next = wrap_deg(angle_pos_next + aspect_angle)

    orb_now = min_arc(planet_lon, expected_pos)
    orb_next = min_arc(planet_lon_next, expected_pos_next)

    return orb_next < orb_now


def _compute_declination_analysis(
    dec_deg: float, lat: float, topocentric: bool
) -> dict[str, Any]:
    """Compute declination strength and circumpolar status."""
    circumpolar = abs(lat) + abs(dec_deg) > 90.0

    # Altitude potential at culmination
    h_max = 90.0 - abs(lat - dec_deg)
    dec_strength = max(0.0, min(1.0, h_max / 90.0))

    return {
        "mode": "topo" if topocentric else "geo",
        "dec_strength": round(dec_strength, 4),
        "circumpolar": circumpolar,
    }


def _compute_indices(planets_data: dict[str, Any]) -> dict[str, Any]:
    """Compute all location indices bounded to [0,1]."""
    angular_loads = []
    aspect_loads = []
    dec_strengths = []
    house_counts = {"angular": 0, "succedent": 0, "cadent": 0}

    for planet_data in planets_data.values():
        # Angular load per planet
        dist_to_angles = planet_data["dist_to_angles"]
        house_num = planet_data["house"]
        cusp_dist = planet_data["cusp_dist_deg"]

        ang_load = angular_load(dist_to_angles, house_num, cusp_dist)
        angular_loads.append(ang_load)

        # House emphasis distribution
        hclass = house_class(house_num)
        house_counts[hclass] += 1

        # Declination emphasis
        if "declination" in planet_data:
            dec_strengths.append(planet_data["declination"]["dec_strength"])

    # Compute aspect-to-angle load across all planets
    total_aspect_weight = 0.0
    max_possible_weight = 0.0

    for planet_data in planets_data.values():
        for aspect in planet_data.get("aspect_to_angles", []):
            weight = 1.0 - aspect["orb"] / aspect_orb(aspect["type"])
            if aspect.get("applying", False):
                weight *= APPLYING_ASPECT_BONUS
            total_aspect_weight += weight
            max_possible_weight += APPLYING_ASPECT_BONUS  # Theoretical max

    aspect_to_angle_load = (
        min(1.0, total_aspect_weight / max(1.0, max_possible_weight))
        if max_possible_weight > 0
        else 0.0
    )

    # Overall indices
    avg_angular_load = sum(angular_loads) / max(1, len(angular_loads))
    avg_dec_strength = (
        sum(dec_strengths) / max(1, len(dec_strengths)) if dec_strengths else 0.0
    )

    # Add circumpolar boost
    circumpolar_count = sum(
        1
        for planet_data in planets_data.values()
        if planet_data.get("declination", {}).get("circumpolar", False)
    )
    dec_emphasis = min(1.0, avg_dec_strength * (1.0 + 0.05 * circumpolar_count))

    total_planets = len(planets_data)
    house_emphasis = {
        "angular": house_counts["angular"] / max(1, total_planets),
        "succedent": house_counts["succedent"] / max(1, total_planets),
        "cadent": house_counts["cadent"] / max(1, total_planets),
    }

    return {
        "angular_load": round(min(1.0, max(0.0, avg_angular_load)), 4),
        "house_emphasis": {k: round(v, 4) for k, v in house_emphasis.items()},
        "aspect_to_angle_load": round(min(1.0, max(0.0, aspect_to_angle_load)), 4),
        "declinational_emphasis": round(min(1.0, max(0.0, dec_emphasis)), 4),
    }


async def compute_location_features(
    ts: datetime,
    locations: Iterable[Location],
    *,
    house_system: str = "KP",
    topocentric: bool = True,
    cache_hit_callback=None,
    cache_miss_callback=None,
) -> dict[str, Any]:
    """Compute features for each location with PM-specified optimizations.

    Production implementation with:
    - KP policy alignment for positions AND houses
    - Production-hardened cache keys with coordinate quantization
    - Polar edge case handling with 422 responses
    - Deterministic topocentric flag semantics
    - All indices bounded [0,1]
    """
    # Normalize house system casing
    house_system_norm = house_system.upper()
    if house_system_norm == "KP":
        house_system_norm = "PLACIDUS"  # KP uses Placidus calculations

    # Get KP-aligned effective timestamp for houses and cache alignment
    ts_eff = _get_kp_effective_timestamp(ts, apply_kp_offset=True)

    # Initialize cache service
    cache = UnifiedCache(system="KP_HOUSES")

    response = {
        "timestamp": ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "locations": [],
    }

    # Single sky calculation for all locations (with KP offset)
    sky_positions = {}
    for planet_id in PLANET_IDS.keys():
        try:
            planet_data = get_positions(ts, planet_id=planet_id, apply_kp_offset=True)
            sky_positions[planet_id] = {
                "ecl_lon": wrap_deg(planet_data.longitude),
                "ra": planet_data.ra,
                "dec": planet_data.dec,
                "name": PLANET_NAMES[planet_id].lower(),
            }
        except Exception:
            # Log error but continue with other planets
            continue

    # Process each location
    for loc in locations:
        try:
            # Production cache key with coordinate quantization and effective timestamp
            lat_key = round(float(loc.lat), 6)
            lon_key = round(float(loc.lon), 6)
            ts_min_eff = ts_eff.replace(
                second=0, microsecond=0
            )  # Use effective timestamp
            cache_key = ("houses", ts_min_eff, lat_key, lon_key, house_system_norm)

            # Try cache first
            cached_houses = await cache.get(str(cache_key))
            if cached_houses:
                if cache_hit_callback:
                    cache_hit_callback()
                houses_data = cached_houses
            else:
                if cache_miss_callback:
                    cache_miss_callback()

                # Proactive polar region check for deterministic error response
                if abs(loc.lat) >= 66.5:
                    raise HTTPException(
                        422,
                        f"Polar calculation instability for latitude {loc.lat}° (≥66.5°)",
                    )

                # Compute houses with polar edge case handling
                try:
                    # Use effective timestamp for KP policy alignment
                    houses_obj = compute_houses(
                        ts_eff,
                        loc.lat,
                        loc.lon,  # Use ts_eff instead of ts
                        system=house_system_norm,
                        topocentric=False,  # Houses don't depend on topocentric flag
                    )
                    houses_data = {
                        "system": houses_obj.system,
                        "asc": houses_obj.asc,
                        "mc": houses_obj.mc,
                        "cusps": houses_obj.cusps,
                    }

                    # Cache for 1 minute
                    await cache.set(str(cache_key), houses_data, ttl=60)

                except Exception as e:
                    if abs(loc.lat) >= 66.5:
                        raise HTTPException(
                            422, f"Polar calculation instability at lat={loc.lat}: {e}"
                        )
                    else:
                        raise

            # Compute derived angles
            asc = houses_data["asc"]
            mc = houses_data["mc"]
            desc = wrap_deg(asc + 180.0)
            ic = wrap_deg(mc + 180.0)
            cusps = houses_data["cusps"]

            # LST computation (simplified for MVP)
            lst_hours = (ts.hour + (lon_key / 15.0)) % 24.0
            lst_segment = _compute_lst_segment(lst_hours)

            # Build location payload
            loc_payload = {
                "id": loc.id,
                "name": loc.name or loc.id,
                "lat": loc.lat,
                "lon": loc.lon,
                "angles": {
                    "asc": round(asc, 4),
                    "mc": round(mc, 4),
                    "desc": round(desc, 4),
                    "ic": round(ic, 4),
                    "lst_segment": lst_segment,
                },
                "houses": {
                    "system": house_system,
                    "cusps": [round(c, 4) for c in cusps],
                },
                "planets": {},
                "derived": {
                    "aspect_to_angles": [],
                    "parans": [],  # Empty for Phase 1
                    "declination": {},
                    "indices": {},
                },
            }

            # Process each planet for this location
            all_aspects = []
            planets_for_indices = {}

            for planet_id, sky_data in sky_positions.items():
                planet_name = PLANET_NAMES[planet_id].lower()

                # Distance calculations using helpers
                dist_to_angles = {
                    "asc": min_arc(sky_data["ecl_lon"], asc),
                    "mc": min_arc(sky_data["ecl_lon"], mc),
                    "desc": min_arc(sky_data["ecl_lon"], desc),
                    "ic": min_arc(sky_data["ecl_lon"], ic),
                }

                house_num = _compute_house_membership(sky_data["ecl_lon"], cusps)
                cusp_dist = _compute_cusp_distance(sky_data["ecl_lon"], cusps)

                planet_payload = {
                    "house": house_num,
                    "ecl_lon": round(sky_data["ecl_lon"], 4),
                    "ra": round(sky_data["ra"], 6),  # RA in hours to 6 decimals
                    "dec": round(sky_data["dec"], 4),
                    "dist_to_angles": {
                        k: round(v, 4) for k, v in dist_to_angles.items()
                    },
                    "cusp_dist_deg": round(cusp_dist, 4),
                }

                # Topocentric calculations only if flag is enabled
                if topocentric:
                    alt, az = _compute_topocentric_altaz(
                        sky_data["ra"], sky_data["dec"], loc.lat, loc.lon, lst_hours
                    )
                    planet_payload["topo"] = {"alt": round(alt, 4), "az": round(az, 4)}
                    planet_payload["above_horizon"] = alt > 0.0

                # Find aspects to angles
                aspects = _find_aspects_to_angles(sky_data["ecl_lon"], asc, mc)
                planet_payload["aspect_to_angles"] = aspects
                all_aspects.extend(aspects)

                # Declination analysis
                decl_analysis = _compute_declination_analysis(
                    sky_data["dec"], loc.lat, topocentric
                )
                planet_payload["declination"] = decl_analysis

                loc_payload["planets"][planet_name] = planet_payload
                planets_for_indices[planet_name] = planet_payload

            # Compute applying status for aspects (with delta-t check)
            try:
                # Determine delta-t direction to avoid minute boundary jitter
                dt_seconds = -30 if ts.second >= 30 else 30
                ts_next = ts + timedelta(seconds=dt_seconds)

                # Get positions at t+dt for applying calculation
                sky_positions_next = {}
                for planet_id in PLANET_IDS.keys():
                    try:
                        planet_data_next = get_positions(
                            ts_next, planet_id=planet_id, apply_kp_offset=True
                        )
                        sky_positions_next[planet_id] = wrap_deg(
                            planet_data_next.longitude
                        )
                    except Exception:
                        sky_positions_next[planet_id] = sky_positions[planet_id][
                            "ecl_lon"
                        ]

                # Get houses at t+dt
                try:
                    houses_next = compute_houses(
                        ts_next, loc.lat, loc.lon, system=house_system_norm
                    )
                    asc_next = houses_next.asc
                    mc_next = houses_next.mc
                except Exception:
                    asc_next, mc_next = asc, mc

                # Update applying status
                for planet_name, planet_data in loc_payload["planets"].items():
                    planet_id = next(
                        pid
                        for pid, name in PLANET_NAMES.items()
                        if name.lower() == planet_name
                    )
                    planet_lon_next = sky_positions_next.get(
                        planet_id, sky_positions[planet_id]["ecl_lon"]
                    )

                    for aspect in planet_data["aspect_to_angles"]:
                        aspect["applying"] = _check_applying_status(
                            sky_positions[planet_id]["ecl_lon"],
                            asc,
                            mc,
                            planet_lon_next,
                            asc_next,
                            mc_next,
                            aspect,
                        )

            except Exception:
                # If applying calculation fails, leave all aspects as non-applying
                pass

            # Aggregate aspects to top-level derived.aspect_to_angles
            loc_payload["derived"]["aspect_to_angles"] = all_aspects

            # Compute location indices
            loc_payload["derived"]["indices"] = _compute_indices(planets_for_indices)

            # Overall declination summary (average across planets)
            all_dec_strengths = [
                p["declination"]["dec_strength"] for p in planets_for_indices.values()
            ]
            avg_dec_strength = (
                sum(all_dec_strengths) / len(all_dec_strengths)
                if all_dec_strengths
                else 0.0
            )
            circumpolar_count = sum(
                1
                for p in planets_for_indices.values()
                if p["declination"]["circumpolar"]
            )

            loc_payload["derived"]["declination"] = {
                "mode": "topo" if topocentric else "geo",
                "dec_strength": round(avg_dec_strength, 4),
                "circumpolar": circumpolar_count > 0,
            }

            response["locations"].append(loc_payload)

        except HTTPException:
            raise  # Re-raise HTTP exceptions (like 422 for polar regions)
        except Exception:
            # Log error and skip this location
            continue

    return response
