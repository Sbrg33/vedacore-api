#!/usr/bin/env python3
"""
Global Locality Research - Activation API Router
HTTP endpoints for planetary activation field mapping.

Provides GET/POST endpoints and SSE streaming for real-time activation data.
Implements single timestamp truth and clean service orchestration.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import uuid

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.services.atlas_service import get_by_id as atlas_get_by_id

# VedaCore imports
from app.services.atlas_service import load_atlas
from app.services.atlas_service import search as atlas_search
from constants.activation_model import (
    BREAKDOWN_KEY_ORDER,
    MODEL_VERSION,
    NUMERIC_PRECISION_DP,
    VALID_PROFILES,
    get_latitude_reliability,
    should_apply_polar_hard_limit,
)
from constants.location_features import MAX_LOCATIONS_PER_REQUEST
from modules.access_service import get_access_geometry
from modules.activation_engine import compute_activation, validate_activation_result
from modules.sky_state_service import get_sky_state

# Feature flag check
ACTIVATION_ENABLED = os.getenv("ACTIVATION_ENABLED", "false").lower() == "true"

router = APIRouter(tags=["activation"])
logger = logging.getLogger(__name__)

# Import streaming metrics
try:
    from api.services.metrics import streaming_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


def _get_kp_effective_timestamp(ts: datetime) -> datetime:
    """Get KP-aligned effective timestamp (single source of truth).

    Args:
        ts: Input timestamp

    Returns:
        Effective timestamp with KP offset applied, minute-bucked
    """
    # Apply 307-second KP offset
    ts_with_offset = ts + timedelta(seconds=307)
    # Bucket to minute for cache alignment
    ts_eff_minute = ts_with_offset.replace(second=0, microsecond=0)
    return ts_eff_minute


def _get_or_create_request_id(request: Request, response: Response) -> str:
    """Get or create correlation ID for request tracing."""
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())

    response.headers["X-Request-ID"] = request_id
    return request_id


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================
try:
    from prometheus_client import Counter, Histogram

    activation_requests_total = Counter(
        "vedacore_activation_requests_total",
        "Total activation requests",
        ["model_version", "model_profile", "method", "status"],
    )

    activation_duration_seconds = Histogram(
        "vedacore_activation_duration_seconds",
        "Activation computation duration",
        ["model_version", "model_profile", "method"],
    )

    activation_cache_hits = Counter(
        "vedacore_activation_cache_hits_total",
        "Activation cache hits",
        ["component"],  # "sky_state" or "access_geometry"
    )

    activation_cache_misses = Counter(
        "vedacore_activation_cache_misses_total",
        "Activation cache misses",
        ["component"],
    )

    activation_errors = Counter(
        "vedacore_activation_errors_total",
        "Activation computation errors",
        ["error_type", "model_version"],
    )

except ImportError:
    # Fallback for test environments
    class _NoOpMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

    activation_requests_total = _NoOpMetric()
    activation_duration_seconds = _NoOpMetric()
    activation_cache_hits = _NoOpMetric()
    activation_cache_misses = _NoOpMetric()
    activation_errors = _NoOpMetric()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class LocationRef(BaseModel):
    """Location reference for activation calculation"""

    id: str
    name: str | None = None
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude [-90, 90]")
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Longitude [-180, 180]"
    )
    elevation: float | None = Field(
        None, ge=-1000.0, le=10000.0, description="Elevation in meters"
    )

    @field_validator("latitude", "longitude", "elevation")
    @classmethod
    def validate_finite(cls, v):
        if v is not None and (math.isnan(v) or math.isinf(v)):
            raise ValueError("Coordinates must be finite (no NaN or Infinity)")
        return v


class ActivationRequest(BaseModel):
    """Activation calculation request"""

    timestamp: str = Field(..., description="ISO8601 timestamp (UTC)")
    locations: list[LocationRef] = Field(
        ..., min_items=1, max_items=MAX_LOCATIONS_PER_REQUEST
    )
    profile: str = Field("default", description="Model profile")
    house_system: str = Field("KP", description="House system")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except Exception as e:
            raise ValueError("Invalid ISO8601 timestamp") from e

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, v: str) -> str:
        if v not in VALID_PROFILES:
            raise ValueError(f"Unknown profile '{v}'. Valid: {list(VALID_PROFILES)}")
        return v


# ============================================================================
# LOCATION RESOLUTION HELPERS
# ============================================================================


def _resolve_location_from_params(
    cities: str | None,
    city_query: str | None,
    city_id: str | None,
    country: str | None,
    admin1: str | None,
    limit: int,
    latitude: float | None,
    longitude: float | None,
    elevation: float | None,
) -> list[LocationRef]:
    """Resolve locations from various parameter combinations."""

    locations = []

    # Legacy cities CSV mapping (keep for compatibility)
    if cities:
        city_coords = {
            "NYC": {"name": "New York", "lat": 40.7128, "lon": -74.0060},
            "LON": {"name": "London", "lat": 51.5074, "lon": -0.1278},
            "MUM": {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777},
            "SYD": {"name": "Sydney", "lat": -33.8688, "lon": 151.2093},
            "TKY": {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
            "LAX": {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
        }

        city_ids = [c.strip().upper() for c in cities.split(",")]
        for city_id_from_csv in city_ids:
            if city_id_from_csv in city_coords:
                coord = city_coords[city_id_from_csv]
                locations.append(
                    LocationRef(
                        id=city_id_from_csv,
                        name=coord["name"],
                        latitude=coord["lat"],
                        longitude=coord["lon"],
                    )
                )
            else:
                raise HTTPException(
                    400,
                    {
                        "error": "Unknown city ID",
                        "unknown_city": city_id_from_csv,
                        "available": list(city_coords.keys()),
                    },
                )

    # Atlas-based resolution
    elif city_id or city_query:
        load_atlas()  # Ensure atlas is loaded

        if city_id:
            entry = atlas_get_by_id(city_id)
            if not entry:
                raise HTTPException(
                    404, {"error": "City not found", "city_id": city_id}
                )
            locations.append(
                LocationRef(
                    id=entry.id,
                    name=f"{entry.name}{', ' + entry.admin1 if entry.admin1 else ''}",
                    latitude=entry.latitude,
                    longitude=entry.longitude,
                )
            )
        else:
            matches = atlas_search(
                city_query, country=country, admin1=admin1, limit=limit
            )
            if not matches:
                raise HTTPException(
                    404,
                    {
                        "error": "No matches for city query",
                        "query": city_query,
                        "country": country,
                        "admin1": admin1,
                    },
                )

            for entry in matches:
                locations.append(
                    LocationRef(
                        id=entry.id,
                        name=f"{entry.name}{', ' + entry.admin1 if entry.admin1 else ''}",
                        latitude=entry.latitude,
                        longitude=entry.longitude,
                    )
                )

    # Direct coordinate specification
    elif latitude is not None and longitude is not None:
        # Validate coordinate bounds
        if not (-90.0 <= latitude <= 90.0):
            raise HTTPException(400, f"Latitude must be [-90, 90], got: {latitude}")
        if not (-180.0 <= longitude <= 180.0):
            raise HTTPException(400, f"Longitude must be [-180, 180], got: {longitude}")
        if math.isnan(latitude) or math.isinf(latitude):
            raise HTTPException(400, "Latitude must be finite")
        if math.isnan(longitude) or math.isinf(longitude):
            raise HTTPException(400, "Longitude must be finite")
        if elevation is not None:
            if math.isnan(elevation) or math.isinf(elevation):
                raise HTTPException(400, "Elevation must be finite")
            if not (-1000.0 <= elevation <= 10000.0):
                raise HTTPException(
                    400, f"Elevation must be [-1000, 10000]m, got: {elevation}"
                )

        locations.append(
            LocationRef(
                id="custom",
                name=f"Custom ({latitude:.4f}, {longitude:.4f})",
                latitude=latitude,
                longitude=longitude,
                elevation=elevation,
            )
        )

    else:
        raise HTTPException(
            400, "Must provide cities, city_query/city_id, or latitude/longitude"
        )

    return locations


# ============================================================================
# SKY STATE RESPONSE BUILDER
# ============================================================================


def _build_sky_response(sky_state) -> dict[str, Any]:
    """Build comprehensive sky response block from sky_state object.

    Creates complete sky block with all 9 planets expected by client.
    Extracts planetary data from planet_states using correct planet IDs.

    Args:
        sky_state: SkyState object with planet_states dict

    Returns:
        Dict containing all planetary information
    """
    from refactor.angles_indices import find_nakshatra_pada, nakshatra_name, sign_name

    sky_response = {}

    # Planet ID mapping for comprehensive response
    planet_mapping = {
        1: "sun",
        2: "moon",
        3: "jupiter",
        4: "rahu",
        5: "mercury",
        6: "venus",
        7: "ketu",
        8: "saturn",
        9: "mars",
    }

    # Process all planets available in sky_state
    if hasattr(sky_state, "planet_states"):
        for planet_id, planet_name in planet_mapping.items():
            if planet_id in sky_state.planet_states:
                planet_state = sky_state.planet_states[planet_id]
                longitude = planet_state.longitude

                planet_data = {
                    "sign": sign_name(longitude),
                    "longitude": round(longitude, 2),
                    "retrograde": planet_state.retrograde,
                }

                # Special handling for Moon (include nakshatra and sub-lunar data)
                if planet_id == 2:  # Moon
                    nakshatra_num, pada_num = find_nakshatra_pada(longitude)

                    # Calculate sub-lunar coordinates
                    sub_lunar_longitude = longitude - 180.0
                    if sub_lunar_longitude < -180:
                        sub_lunar_longitude += 360
                    elif sub_lunar_longitude > 180:
                        sub_lunar_longitude -= 360

                    planet_data.update(
                        {
                            "nakshatra": {
                                "name": nakshatra_name(longitude),
                                "pada": pada_num,
                            },
                            "sub_lunar_lat": round(0.0, 1),  # Simplified
                            "sub_lunar_lon": round(sub_lunar_longitude, 1),
                            "voc": False,  # Would need aspect analysis
                            "station": planet_state.station_within_24h,
                        }
                    )
                    # Keep retrograde as "retro" for Moon compatibility
                    planet_data["retro"] = planet_data.pop("retrograde")

                # Special handling for Sun (include degree within sign)
                elif planet_id == 1:  # Sun
                    planet_data.update({"degree": round(longitude % 30, 2)})
                    # Keep retrograde as "retro" for Sun compatibility
                    planet_data["retro"] = planet_data.pop("retrograde")

                # Add station information for all planets
                if hasattr(planet_state, "station_within_24h"):
                    planet_data["station"] = planet_state.station_within_24h

                sky_response[planet_name] = planet_data

            else:
                # Provide fallback data for missing planets
                fallback_data = {
                    "sign": "Unknown",
                    "longitude": 0.0,
                    "retrograde": False,
                }

                if planet_name == "moon":
                    fallback_data.update(
                        {
                            "nakshatra": {"name": "Unknown", "pada": 1},
                            "sub_lunar_lat": 0.0,
                            "sub_lunar_lon": 0.0,
                            "voc": False,
                            "retro": False,
                            "station": False,
                        }
                    )
                    fallback_data.pop("retrograde")  # Use "retro" for Moon
                elif planet_name == "sun":
                    fallback_data.update({"degree": 0.0, "retro": False})
                    fallback_data.pop("retrograde")  # Use "retro" for Sun

                sky_response[planet_name] = fallback_data

    else:
        # Complete fallback if no planet_states available
        for planet_id, planet_name in planet_mapping.items():
            fallback_data = {"sign": "Unknown", "longitude": 0.0, "retrograde": False}

            if planet_name == "moon":
                fallback_data.update(
                    {
                        "nakshatra": {"name": "Unknown", "pada": 1},
                        "sub_lunar_lat": 0.0,
                        "sub_lunar_lon": 0.0,
                        "voc": False,
                        "retro": False,
                        "station": False,
                    }
                )
                fallback_data.pop("retrograde")
            elif planet_name == "sun":
                fallback_data.update({"degree": 0.0, "retro": False})
                fallback_data.pop("retrograde")

            sky_response[planet_name] = fallback_data

    return sky_response


# ============================================================================
# CORE ACTIVATION COMPUTATION
# ============================================================================


async def _compute_activation_for_locations(
    ts_eff_minute: datetime,
    locations: list[LocationRef],
    profile: str,
    house_system: str,
    request_id: str,
    include_sky: bool = False,
) -> dict[str, Any]:
    """Core activation computation with proper service orchestration."""

    # Validate house system
    if house_system.upper() not in ["KP", "PLACIDUS"]:
        raise HTTPException(
            400,
            {
                "error": "Unsupported house system",
                "provided": house_system,
                "accepted": ["KP", "PLACIDUS"],
            },
        )

    # Validate profile
    if profile not in VALID_PROFILES:
        raise HTTPException(
            400,
            {
                "error": "Unknown profile",
                "provided": profile,
                "accepted": list(VALID_PROFILES),
            },
        )

    # Check location count limit
    if len(locations) > MAX_LOCATIONS_PER_REQUEST:
        raise HTTPException(
            413,
            {
                "error": "Too many locations",
                "provided": len(locations),
                "maximum": MAX_LOCATIONS_PER_REQUEST,
            },
        )

    # ========================================================================
    # SINGLE TIMESTAMP TRUTH: Compute sky state once per request
    # ========================================================================

    try:
        sky_state = await get_sky_state(
            ts_eff_minute=ts_eff_minute,
            model_version=MODEL_VERSION,
            model_profile=profile,
            use_cache=True,
        )

        # Track cache performance
        if sky_state.cache_hit:
            activation_cache_hits.labels(component="sky_state").inc()
        else:
            activation_cache_misses.labels(component="sky_state").inc()

    except Exception as e:
        activation_errors.labels(
            error_type="sky_state", model_version=MODEL_VERSION
        ).inc()
        logger.error(
            "Sky state computation failed",
            extra={
                "request_id": request_id,
                "error": str(e),
                "ts_eff_minute": ts_eff_minute.isoformat(),
            },
        )
        raise HTTPException(500, f"Sky state computation failed: {e}") from e

    # ========================================================================
    # Process each location
    # ========================================================================

    response_locations = []

    for location in locations:
        try:
            # Check polar hard limit
            if should_apply_polar_hard_limit(location.latitude):
                raise HTTPException(
                    422,
                    {
                        "error": "Polar calculation limit exceeded",
                        "latitude": location.latitude,
                        "limit": 66.5,
                        "location_id": location.id,
                    },
                )

            # Get access geometry (uses same ts_eff_minute)
            access = await get_access_geometry(
                ts_eff_minute=ts_eff_minute,
                latitude=location.latitude,
                longitude=location.longitude,
                house_system=house_system,
                model_version=MODEL_VERSION,
                model_profile=profile,
                altitude=location.elevation,
                use_cache=True,
            )

            # Track cache performance
            if access.cache_hit:
                activation_cache_hits.labels(component="access_geometry").inc()
            else:
                activation_cache_misses.labels(component="access_geometry").inc()

            # Compute activation
            activation_result = compute_activation(
                sky_state=sky_state, access=access, model_profile=profile
            )

            # Validate result
            validations = validate_activation_result(activation_result)
            if not all(validations.values()):
                logger.warning(
                    "Activation validation failed",
                    extra={
                        "request_id": request_id,
                        "location_id": location.id,
                        "validations": validations,
                    },
                )

            # Format breakdown with deterministic ordering and precision
            breakdown = {}
            for planet_key in BREAKDOWN_KEY_ORDER:
                if planet_key in activation_result.planet_contributions:
                    contrib = activation_result.planet_contributions[planet_key]
                    breakdown[planet_key] = round(
                        contrib.modulated_contribution, NUMERIC_PRECISION_DP
                    )

            # Build location response
            location_response = {
                "id": location.id,
                "name": location.name,
                "lat": location.latitude,
                "lon": location.longitude,
                "activation": {
                    "absolute": round(
                        activation_result.scaled_activation, NUMERIC_PRECISION_DP
                    ),
                    "delta": None,  # TODO: Implement novelty service
                    "exposure_weighted": None,  # TODO: Implement exposure service
                },
                "breakdown": breakdown,
                "sun_cap": activation_result.sun_cap_factor,
                "phase_multiplier": activation_result.phase_multiplier,
                "drivers": {
                    "planet": activation_result.primary_drivers.strongest_planet,
                    "angle": activation_result.primary_drivers.strongest_angle,
                    "kind": activation_result.primary_drivers.connection_type,
                    "applying": activation_result.primary_drivers.applying,
                },
                "flags": activation_result.flags,
                "confidence": {
                    "reliability_lat": get_latitude_reliability(location.latitude)
                },
            }

            response_locations.append(location_response)

        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            activation_errors.labels(
                error_type="location_processing", model_version=MODEL_VERSION
            ).inc()
            logger.error(
                "Location processing failed",
                extra={
                    "request_id": request_id,
                    "location_id": location.id,
                    "error": str(e),
                },
            )
            # Skip failed location, continue with others
            continue

    if not response_locations:
        raise HTTPException(500, "No locations could be processed successfully")

    # Build final response
    response = {
        "timestamp": ts_eff_minute.replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "model_version": MODEL_VERSION,
        "model_profile": profile,
        "locations": response_locations,
    }

    # Add sky block if requested (PM requirement: fix "Moon — • —" display)
    if include_sky:
        try:
            response["sky"] = _build_sky_response(sky_state)
        except NameError:
            # sky_state wasn't created due to error - provide fallback
            response["sky"] = {
                "moon": {
                    "sign": "Unknown",
                    "nakshatra": {"name": "Unknown", "pada": 1},
                },
                "sun": {"sign": "Unknown"},
            }

    return response


# ============================================================================
# API ENDPOINTS
# ============================================================================


def _check_feature_flag():
    """Check if activation API is enabled."""
    if not ACTIVATION_ENABLED:
        raise HTTPException(
            503,
            {
                "error": "Activation API disabled",
                "message": "Set ACTIVATION_ENABLED=1 to enable",
            },
        )


@router.get("/activation", response_model=dict[str, Any])
async def get_activation(
    request: Request,
    response: Response,
    timestamp: str = Query(..., description="ISO8601 timestamp (UTC)"),
    profile: str = Query("default", description="Model profile"),
    cities: str | None = Query(None, description="Legacy CSV city IDs"),
    city_query: str | None = Query(None, description="City search query"),
    city_id: str | None = Query(None, description="Exact atlas city ID"),
    country: str | None = Query(None, description="Country filter"),
    admin1: str | None = Query(None, description="Admin1 filter"),
    limit: int = Query(
        1, ge=1, le=MAX_LOCATIONS_PER_REQUEST, description="Query limit"
    ),
    latitude: float | None = Query(None, description="Direct latitude"),
    longitude: float | None = Query(None, description="Direct longitude"),
    elevation: float | None = Query(None, description="Elevation (m)"),
    house_system: str = Query("KP", description="House system"),
    include_sky: bool = Query(
        False, description="Include sky state (Moon/Sun) in response"
    ),
):
    """GET endpoint for activation field calculation."""
    _check_feature_flag()

    start_time = time.perf_counter()
    request_id = _get_or_create_request_id(request, response)

    # Set headers
    response.headers["X-VedaCore-Version"] = "1.0.0"
    response.headers["X-Model-Version"] = MODEL_VERSION
    response.headers["X-Model-Profile"] = profile
    response.headers["Cache-Control"] = "no-store"

    try:
        # Parse timestamp and compute effective minute
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        ts_eff_minute = _get_kp_effective_timestamp(ts)

        # Resolve locations
        locations = _resolve_location_from_params(
            cities,
            city_query,
            city_id,
            country,
            admin1,
            limit,
            latitude,
            longitude,
            elevation,
        )

        # Compute activation
        result = await _compute_activation_for_locations(
            ts_eff_minute,
            locations,
            profile,
            house_system,
            request_id,
            include_sky=include_sky,
        )

        # Record metrics
        activation_requests_total.labels(
            model_version=MODEL_VERSION,
            model_profile=profile,
            method="GET",
            status="200",
        ).inc()

        duration = time.perf_counter() - start_time
        activation_duration_seconds.labels(
            model_version=MODEL_VERSION, model_profile=profile, method="GET"
        ).observe(duration)

        # Structured logging
        logger.info(
            "activation_request_completed",
            extra={
                "request_id": request_id,
                "method": "GET",
                "ts_eff_minute": ts_eff_minute.replace(
                    second=0, microsecond=0
                ).isoformat()
                + "Z",
                "model_version": MODEL_VERSION,
                "model_profile": profile,
                "house_system": house_system,
                "n_locations": len(locations),
                "status": 200,
                "duration_ms": round(duration * 1000, 2),
            },
        )

        return result

    except HTTPException:
        activation_requests_total.labels(
            model_version=MODEL_VERSION,
            model_profile=profile,
            method="GET",
            status="4xx",
        ).inc()
        raise
    except Exception as e:
        activation_requests_total.labels(
            model_version=MODEL_VERSION,
            model_profile=profile,
            method="GET",
            status="500",
        ).inc()
        activation_errors.labels(
            error_type="request_processing", model_version=MODEL_VERSION
        ).inc()

        logger.error(
            "activation_request_failed",
            extra={
                "request_id": request_id,
                "method": "GET",
                "error": str(e)[:200],
                "status": 500,
            },
        )

        raise HTTPException(500, f"Activation computation failed: {e}") from e


@router.post("/activation", response_model=dict[str, Any])
async def post_activation(request: Request, response: Response, req: ActivationRequest):
    """POST endpoint for activation field calculation."""
    _check_feature_flag()

    start_time = time.perf_counter()
    request_id = _get_or_create_request_id(request, response)

    # Set headers
    response.headers["X-VedaCore-Version"] = "1.0.0"
    response.headers["X-Model-Version"] = MODEL_VERSION
    response.headers["X-Model-Profile"] = req.profile
    response.headers["Cache-Control"] = "no-store"

    try:
        # Parse timestamp and compute effective minute
        ts = datetime.fromisoformat(req.timestamp.replace("Z", "+00:00"))
        ts_eff_minute = _get_kp_effective_timestamp(ts)

        # Compute activation
        result = await _compute_activation_for_locations(
            ts_eff_minute, req.locations, req.profile, req.house_system, request_id
        )

        # Record metrics
        activation_requests_total.labels(
            model_version=MODEL_VERSION,
            model_profile=req.profile,
            method="POST",
            status="200",
        ).inc()

        duration = time.perf_counter() - start_time
        activation_duration_seconds.labels(
            model_version=MODEL_VERSION, model_profile=req.profile, method="POST"
        ).observe(duration)

        # Structured logging
        location_ids = ",".join([loc.id for loc in req.locations[:5]])  # First 5 IDs
        logger.info(
            "activation_request_completed",
            extra={
                "request_id": request_id,
                "method": "POST",
                "ts_eff_minute": ts_eff_minute.replace(
                    second=0, microsecond=0
                ).isoformat()
                + "Z",
                "model_version": MODEL_VERSION,
                "model_profile": req.profile,
                "house_system": req.house_system,
                "location_ids": location_ids,
                "n_locations": len(req.locations),
                "status": 200,
                "duration_ms": round(duration * 1000, 2),
            },
        )

        return result

    except HTTPException:
        activation_requests_total.labels(
            model_version=MODEL_VERSION,
            model_profile=req.profile,
            method="POST",
            status="4xx",
        ).inc()
        raise
    except Exception as e:
        activation_requests_total.labels(
            model_version=MODEL_VERSION,
            model_profile=req.profile,
            method="POST",
            status="500",
        ).inc()
        activation_errors.labels(
            error_type="request_processing", model_version=MODEL_VERSION
        ).inc()

        logger.error(
            "activation_request_failed",
            extra={
                "request_id": request_id,
                "method": "POST",
                "error": str(e)[:200],
                "status": 500,
            },
        )

        raise HTTPException(500, f"Activation computation failed: {e}") from e


# ============================================================================
# SSE STREAMING ENDPOINT
# ============================================================================


async def _generate_activation_stream(
    timestamp: str,
    profile: str,
    locations: list[LocationRef],
    house_system: str,
    request_id: str,
    interval_seconds: int = 60,
    include_sky: bool = False,
) -> AsyncGenerator[str, None]:
    """Generate SSE stream for activation updates."""

    event_id = 0
    stream_start = time.time()

    try:
        while True:
            try:
                # Parse current timestamp
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                ts_eff_minute = _get_kp_effective_timestamp(ts)

                # Compute activation
                result = await _compute_activation_for_locations(
                    ts_eff_minute,
                    locations,
                    profile,
                    house_system,
                    request_id,
                    include_sky=include_sky,
                )

                # Format as SSE event
                import json

                event_data = json.dumps(result, separators=(",", ":"))

                sse_event = f"id: {event_id}\n"
                sse_event += "event: activation\n"
                sse_event += f"data: {event_data}\n\n"

                yield sse_event

                event_id += 1

                # Wait for next interval
                await asyncio.sleep(interval_seconds)

                # Update timestamp for next iteration
                next_ts = ts + timedelta(seconds=interval_seconds)
                timestamp = next_ts.isoformat().replace("+00:00", "Z")

            except Exception as e:
                error_event = f"id: {event_id}\n"
                error_event += "event: error\n"
                error_event += f'data: {{"error": "{str(e)[:100]}"}}\n\n'

                yield error_event
                break

    except asyncio.CancelledError:
        # Client disconnected - record duration (PM-specified metric)
        if METRICS_AVAILABLE:
            duration = time.time() - stream_start
            streaming_metrics.record_activation_stream_duration(duration)

        final_event = f"id: {event_id}\n"
        final_event += "event: close\n"
        final_event += 'data: {"message": "Stream closed"}\n\n'

        yield final_event

    finally:
        # Always record duration on stream end
        if METRICS_AVAILABLE:
            duration = time.time() - stream_start
            streaming_metrics.record_activation_stream_duration(duration)


@router.get("/activation/stream")
async def stream_activation(
    request: Request,
    response: Response,
    timestamp: str = Query(..., description="Starting ISO8601 timestamp"),
    profile: str = Query("default", description="Model profile"),
    cities: str | None = Query(None, description="Legacy CSV city IDs"),
    city_query: str | None = Query(None, description="City search query"),
    city_id: str | None = Query(None, description="Exact atlas city ID"),
    country: str | None = Query(None, description="Country filter"),
    admin1: str | None = Query(None, description="Admin1 filter"),
    limit: int = Query(
        1, ge=1, le=10, description="Query limit (max 10 for streaming)"
    ),
    latitude: float | None = Query(None, description="Direct latitude"),
    longitude: float | None = Query(None, description="Direct longitude"),
    elevation: float | None = Query(None, description="Elevation (m)"),
    house_system: str = Query("KP", description="House system"),
    interval: int = Query(60, ge=30, le=300, description="Update interval (seconds)"),
    include_sky: bool = Query(
        False, description="Include sky state (Moon/Sun) in stream events"
    ),
):
    """SSE streaming endpoint for real-time activation updates."""
    _check_feature_flag()

    request_id = _get_or_create_request_id(request, response)

    # Record activation stream request start (PM-specified metric)
    connection_start = time.time()
    if METRICS_AVAILABLE:
        streaming_metrics.record_activation_stream_request("started")

    try:
        # Resolve locations (limit to 10 for streaming)
        if limit > 10:
            raise HTTPException(400, "Maximum 10 locations for streaming")

        locations = _resolve_location_from_params(
            cities,
            city_query,
            city_id,
            country,
            admin1,
            limit,
            latitude,
            longitude,
            elevation,
        )

        # Generate stream
        stream = _generate_activation_stream(
            timestamp,
            profile,
            locations,
            house_system,
            request_id,
            interval,
            include_sky,
        )

        # Set SSE headers
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Request-ID": request_id,
            "X-VedaCore-Version": "1.0.0",
            "X-Model-Version": MODEL_VERSION,
            "X-Model-Profile": profile,
        }

        # Record successful activation stream setup
        if METRICS_AVAILABLE:
            streaming_metrics.record_activation_stream_request("success")

        return StreamingResponse(
            stream, media_type="text/event-stream", headers=headers
        )

    except Exception as e:
        # Record activation stream error (PM-specified metric)
        if METRICS_AVAILABLE:
            streaming_metrics.record_activation_stream_request("error")

        activation_errors.labels(
            error_type="streaming", model_version=MODEL_VERSION
        ).inc()

        logger.error(
            "activation_stream_failed",
            extra={"request_id": request_id, "error": str(e)[:200]},
        )

        raise HTTPException(500, f"Streaming setup failed: {e}")


# Export router
__all__ = ["router"]
