"""
api/routers/location.py — Location Features API (Draft)

Versioned endpoints for location-differentiated astronomical features.
Follows VedaCore conventions: Pydantic v2, Prometheus metrics, CacheService.
"""

from __future__ import annotations

import logging
import math
import time
import uuid

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, Field, field_validator
from api.models.responses import LocationFeaturesResponse

from app.services.atlas_service import get_by_id as _atlas_get_by_id
from app.services.atlas_service import load_atlas as _load_atlas
from app.services.atlas_service import search as _atlas_search
from constants.location_features import MAX_LOCATIONS_PER_REQUEST

# VedaCore production imports
from modules.location_features import Location, compute_location_features

router = APIRouter(tags=["location"], responses=DEFAULT_ERROR_RESPONSES)

# Structured logging for PM7 operational visibility
logger = logging.getLogger(__name__)


def _get_or_create_request_id(request: Request, response: Response) -> str:
    """Get or create correlation ID for request tracing (PM8 requirement)"""
    # Check if client provided X-Request-ID
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        # Generate new correlation ID
        request_id = str(uuid.uuid4())

    # Reflect back to client for tracing
    response.headers["X-Request-ID"] = request_id
    return request_id


# --- Prometheus metrics (mirror houses.py style) ---
try:
    from prometheus_client import Counter, Histogram

    location_requests_total = Counter(
        "vedacore_location_features_requests_total",
        "Total number of location feature requests",
        ["house_system", "topocentric", "mode"],
    )
    location_compute_seconds = Histogram(
        "vedacore_location_features_compute_seconds",
        "Time spent computing location features",
        ["house_system", "topocentric", "mode"],
    )
    location_cache_hits = Counter(
        "vedacore_location_features_cache_hits_total",
        "Total number of cache hits for location features",
    )
    location_cache_misses = Counter(
        "vedacore_location_features_cache_misses_total",
        "Total number of cache misses for location features",
    )
    location_errors_total = Counter(
        "vedacore_location_features_errors_total",
        "Total errors in location features",
        ["error_type"],
    )
except Exception:  # Prometheus optional in test envs

    class _Noop:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

        def observe(self, *a, **k):
            return None

    location_requests_total = _Noop()
    location_compute_seconds = _Noop()
    location_cache_hits = _Noop()
    location_cache_misses = _Noop()
    location_errors_total = _Noop()


HouseSystem = Literal["KP", "PLACIDUS", "BHAVA"]

# Simple city mapping for MVP (can be moved to config later)
CITY_COORDS = {
    "NYC": {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    "LON": {"name": "London", "lat": 51.5074, "lon": -0.1278},
    "MUM": {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    "SYD": {"name": "Sydney", "lat": -33.8688, "lon": 151.2093},
    "TKY": {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    "LAX": {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
}


def _resolve_cities(cities_csv: str) -> list[Location]:
    """Resolve CSV city IDs to Location objects."""
    if not cities_csv:
        return []

    city_ids = [city.strip().upper() for city in cities_csv.split(",")]
    locations = []
    unknown_cities = []

    for city_id in city_ids:
        if city_id in CITY_COORDS:
            coord = CITY_COORDS[city_id]
            locations.append(
                Location(
                    id=city_id, name=coord["name"], lat=coord["lat"], lon=coord["lon"]
                )
            )
        else:
            unknown_cities.append(city_id)

    if unknown_cities:
        raise HTTPException(
            400, detail={"error": "Unknown city IDs", "unknown_cities": unknown_cities}
        )

    return locations


class CityRef(BaseModel):
    id: str
    name: str | None = None
    latitude: float = Field(
        ..., ge=-90.0, le=90.0, description="Latitude in degrees [-90, 90]"
    )
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Longitude in degrees [-180, 180]"
    )
    elevation: float | None = Field(
        None, ge=-1000.0, le=10000.0, description="Elevation in meters [-1000, 10000]"
    )

    @field_validator("latitude", "longitude", "elevation")
    @classmethod
    def validate_finite_numbers(cls, v):
        if v is not None and (math.isnan(v) or math.isinf(v)):
            raise ValueError("Coordinates must be finite numbers (no NaN or Infinity)")
        return v


class FeaturesGetRequest(BaseModel):
    timestamp: str = Field(..., description="ISO8601 timestamp (UTC)")
    cities: str | None = Field(None, description="CSV of city IDs, server-mapped")
    latitude: float | None = None
    longitude: float | None = None
    elevation: float | None = None
    house_system: HouseSystem = Field("KP", description="House system")
    topocentric: bool = Field(True, description="Topocentric positions for angles")

    @field_validator("timestamp")
    @classmethod
    def _validate_ts(cls, v: str) -> str:
        try:
            _ = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except Exception:
            raise ValueError("timestamp must be ISO 8601 (e.g., 2025-08-25T12:00:00Z)")


class FeaturesPostRequest(BaseModel):
    timestamp: str = Field(..., description="ISO8601 timestamp (UTC)")
    locations: list[CityRef]
    house_system: HouseSystem = Field("KP", description="House system")
    topocentric: bool = Field(True, description="Topocentric positions for angles")

    @field_validator("timestamp")
    @classmethod
    def _validate_ts(cls, v: str) -> str:
        try:
            _ = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except Exception:
            raise ValueError("timestamp must be ISO 8601 (e.g., 2025-08-25T12:00:00Z)")


@router.get(
    "/features",
    response_model=LocationFeaturesResponse,
    summary="Get location features",
    operation_id="location_getFeatures",
)
async def get_location_features(
    request: Request,
    response: Response,
    timestamp: str = Query(..., description="ISO8601 timestamp (UTC)"),
    cities: str | None = Query(
        None, description="CSV of city IDs (legacy, server-mapped)"
    ),
    city_query: str | None = Query(
        None, description="Free-text city query resolved via atlas"
    ),
    city_id: str | None = Query(
        None, description="Exact atlas city id (country::name::admin1)"
    ),
    country: str | None = Query(None, description="Country filter for city_query"),
    admin1: str | None = Query(None, description="Admin1/State filter for city_query"),
    limit: int = Query(
        1, ge=1, le=MAX_LOCATIONS_PER_REQUEST, description="Max matches for city_query"
    ),
    latitude: float | None = None,
    longitude: float | None = None,
    elevation: float | None = None,
    house_system: HouseSystem = "KP",
    topocentric: bool = True,
):
    """GET endpoint for location features (single lat/lon or server-mapped cities)."""
    # Set API version header (PM6 requirement)
    response.headers["X-VedaCore-Version"] = "1.0.0"

    # PM8 correlation ID tracking
    request_id = _get_or_create_request_id(request, response)

    # Request metric
    location_requests_total.labels(house_system, str(topocentric), "GET").inc()

    start = time.perf_counter()
    try:
        # Parse timestamp
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Resolve locations
        locations = []
        if cities:
            locations = _resolve_cities(cities)
        elif city_id or city_query:
            # Resolve via atlas
            _load_atlas()
            atlas_entries = []
            if city_id:
                entry = _atlas_get_by_id(city_id)
                if not entry:
                    raise HTTPException(
                        404, detail={"error": "City not found", "city_id": city_id}
                    )
                atlas_entries = [entry]
            else:
                matches = _atlas_search(
                    city_query or "", country=country, admin1=admin1, limit=limit
                )
                if not matches:
                    raise HTTPException(
                        404,
                        detail={
                            "error": "No matches for city_query",
                            "query": city_query,
                        },
                    )
                atlas_entries = matches

            for e in atlas_entries:
                locations.append(
                    Location(
                        id=e.id,
                        name=f"{e.name}{', ' + e.admin1 if e.admin1 else ''}",
                        lat=e.latitude,
                        lon=e.longitude,
                        elevation=None,
                    )
                )
        elif latitude is not None and longitude is not None:
            # PM7 security: validate lat/lon bounds and finite numbers
            if not (-90.0 <= latitude <= 90.0):
                raise HTTPException(
                    400, f"Latitude must be in range [-90, 90], got: {latitude}"
                )
            if not (-180.0 <= longitude <= 180.0):
                raise HTTPException(
                    400, f"Longitude must be in range [-180, 180], got: {longitude}"
                )
            if math.isnan(latitude) or math.isinf(latitude):
                raise HTTPException(
                    400, "Latitude must be a finite number (no NaN or Infinity)"
                )
            if math.isnan(longitude) or math.isinf(longitude):
                raise HTTPException(
                    400, "Longitude must be a finite number (no NaN or Infinity)"
                )
            if elevation is not None and (
                math.isnan(elevation) or math.isinf(elevation)
            ):
                raise HTTPException(
                    400, "Elevation must be a finite number (no NaN or Infinity)"
                )
            if elevation is not None and not (-1000.0 <= elevation <= 10000.0):
                raise HTTPException(
                    400,
                    f"Elevation must be in range [-1000, 10000] meters, got: {elevation}",
                )

            locations = [
                Location(
                    id="custom",
                    name=f"Custom ({latitude}, {longitude})",
                    lat=latitude,
                    lon=longitude,
                    elevation=elevation,
                )
            ]
        else:
            raise HTTPException(
                400, "Either 'cities' or 'latitude'/'longitude' must be provided"
            )

        if not locations:
            raise HTTPException(400, "No valid locations specified")

        # PM6 guardrail: enforce location count limit
        if len(locations) > MAX_LOCATIONS_PER_REQUEST:
            raise HTTPException(
                413,
                f"Too many locations: {len(locations)} (max: {MAX_LOCATIONS_PER_REQUEST})",
            )

        # Compute location features
        result = await compute_location_features(
            ts=ts,
            locations=locations,
            house_system=house_system,
            topocentric=topocentric,
        )

        # PM7 structured logging on success
        ts_eff_minute = ts.replace(second=0, microsecond=0).isoformat() + "Z"
        logger.info(
            "location_features_request",
            extra={
                "request_id": request_id,
                "ts_eff_minute": ts_eff_minute,
                "city_ids": cities if cities else "custom",
                "house_system": house_system,
                "topocentric": topocentric,
                "n_locations": len(locations),
                "status": 200,
                "method": "GET",
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            },
        )

        return result

    except HTTPException as he:
        # PM7 structured error logging (no request bodies for 4xx)
        logger.warning(
            "location_features_error",
            extra={
                "request_id": request_id,
                "status": he.status_code,
                "error": str(he.detail)[:200],  # Truncate long error messages
                "method": "GET",
            },
        )
        raise
    except ValueError as e:
        location_errors_total.labels("validation_error").inc()
        logger.warning(
            "location_features_validation_error",
            extra={
                "request_id": request_id,
                "status": 400,
                "error": str(e)[:200],
                "method": "GET",
            },
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        location_errors_total.labels("calculation_error").inc()
        logger.error(
            "location_features_calculation_error",
            extra={
                "request_id": request_id,
                "status": 500,
                "error": str(e)[:200],
                "method": "GET",
            },
        )
        raise HTTPException(status_code=500, detail=f"Location features failed: {e}")
    finally:
        location_compute_seconds.labels(house_system, str(topocentric), "GET").observe(
            time.perf_counter() - start
        )


@router.post(
    "/features",
    response_model=LocationFeaturesResponse,
    summary="Post location features",
    operation_id="location_postFeatures",
)
async def post_location_features(
    request: Request, response: Response, req: FeaturesPostRequest
):
    """POST endpoint for location features (explicit coordinates list)."""
    # Set API version header (PM6 requirement)
    response.headers["X-VedaCore-Version"] = "1.0.0"

    # PM8 correlation ID tracking
    request_id = _get_or_create_request_id(request, response)

    location_requests_total.labels(req.house_system, str(req.topocentric), "POST").inc()

    start = time.perf_counter()
    try:
        # Parse timestamp
        ts = datetime.fromisoformat(req.timestamp.replace("Z", "+00:00"))

        # Convert Pydantic locations to Location objects
        locations = [
            Location(
                id=loc.id,
                name=loc.name,
                lat=loc.latitude,
                lon=loc.longitude,
                elevation=loc.elevation,
            )
            for loc in req.locations
        ]

        if not locations:
            raise HTTPException(400, "No locations specified")

        # PM6 guardrail: enforce location count limit
        if len(locations) > MAX_LOCATIONS_PER_REQUEST:
            raise HTTPException(
                413,
                f"Too many locations: {len(locations)} (max: {MAX_LOCATIONS_PER_REQUEST})",
            )

        # Compute location features
        result = await compute_location_features(
            ts=ts,
            locations=locations,
            house_system=req.house_system,
            topocentric=req.topocentric,
        )

        # PM7 structured logging on success
        ts_eff_minute = ts.replace(second=0, microsecond=0).isoformat() + "Z"
        logger.info(
            "location_features_request",
            extra={
                "request_id": request_id,
                "ts_eff_minute": ts_eff_minute,
                "city_ids": ",".join(
                    [loc.id for loc in req.locations[:5]]
                ),  # First 5 IDs only
                "house_system": req.house_system,
                "topocentric": req.topocentric,
                "n_locations": len(locations),
                "status": 200,
                "method": "POST",
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            },
        )

        return result

    except HTTPException as he:
        # PM7 structured error logging (no request bodies for 4xx)
        logger.warning(
            "location_features_error",
            extra={
                "request_id": request_id,
                "status": he.status_code,
                "error": str(he.detail)[:200],  # Truncate long error messages
                "method": "POST",
            },
        )
        raise
    except ValueError as e:
        location_errors_total.labels("validation_error").inc()
        logger.warning(
            "location_features_validation_error",
            extra={
                "request_id": request_id,
                "status": 400,
                "error": str(e)[:200],
                "method": "POST",
            },
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        location_errors_total.labels("calculation_error").inc()
        logger.error(
            "location_features_calculation_error",
            extra={
                "request_id": request_id,
                "status": 500,
                "error": str(e)[:200],
                "method": "POST",
            },
        )
        raise HTTPException(status_code=500, detail=f"Location features failed: {e}")
    finally:
        location_compute_seconds.labels(
            req.house_system, str(req.topocentric), "POST"
        ).observe(time.perf_counter() - start)
