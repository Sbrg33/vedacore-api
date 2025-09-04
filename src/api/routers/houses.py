# api/routers/houses.py
from __future__ import annotations

import time

from datetime import datetime
import os
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field, field_validator

from interfaces.registry import get_system
from shared.otel import get_tracer
from shared.trace_attrs import set_common_attrs
from shared.normalize import NORMALIZATION_VERSION, EPHEMERIS_DATASET_VERSION

# Prometheus metrics for house calculations
houses_requests_total = Counter(
    "vedacore_houses_requests_total",
    "Total number of house calculation requests",
    ["system", "house_system", "topocentric"],
)

houses_compute_seconds = Histogram(
    "vedacore_houses_compute_seconds",
    "Time spent computing houses",
    ["system", "house_system", "topocentric"],
)

houses_cache_hits = Counter(
    "vedacore_houses_cache_hits_total",
    "Total number of cache hits for house calculations",
)

houses_cache_misses = Counter(
    "vedacore_houses_cache_misses_total",
    "Total number of cache misses for house calculations",
)

houses_errors_total = Counter(
    "vedacore_houses_errors_total",
    "Total number of errors in house calculations",
    ["error_type"],
)

router = APIRouter(tags=["houses"], responses=DEFAULT_ERROR_RESPONSES)
_tracer = get_tracer("houses")

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

HouseSystem = Literal["PLACIDUS", "BHAVA"]


class HousesRequest(BaseModel):
    """Request for house calculations - using standardized field names"""

    timestamp: str = Field(..., description="ISO timestamp (UTC or with TZ)")
    latitude: float = Field(
        ..., ge=-90, le=90, description="Latitude in decimal degrees"
    )
    longitude: float = Field(
        ..., ge=-180, le=180, description="Longitude in decimal degrees"
    )
    house_system: HouseSystem = Field(
        default="PLACIDUS", description="House system to use"
    )
    topocentric: bool = Field(default=False, description="Use topocentric calculations")
    system: str = Field(default="KP_HOUSES", description="Calculation system")

    # Support old field names for backward compatibility
    lat: float | None = Field(default=None, exclude=True)
    lon: float | None = Field(default=None, exclude=True)

    @field_validator("timestamp")
    @classmethod
    def _validate_ts(cls, v: str) -> str:
        try:
            _ = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except Exception:
            raise ValueError("timestamp must be ISO 8601 (e.g., 2025-08-20T14:32:00Z)")

    @field_validator("latitude", mode="before")
    @classmethod
    def _check_lat_compat(cls, v, info):
        """Support old 'lat' field for backward compatibility"""
        if v is None and info.data.get("lat") is not None:
            return info.data["lat"]
        return v

    @field_validator("longitude", mode="before")
    @classmethod
    def _check_lon_compat(cls, v, info):
        """Support old 'lon' field for backward compatibility"""
        if v is None and info.data.get("lon") is not None:
            return info.data["lon"]
        return v


class HousesResponse(BaseModel):
    system: HouseSystem
    asc: float
    mc: float
    cusps: list[float]
    meta: dict


@router.post(
    "/houses",
    response_model=HousesResponse,
    summary="Calculate houses",
    operation_id="houses_calculate",
)
async def compute_houses_endpoint(req: HousesRequest, request: Request):
    # Import unified cache service (Redis in production, file in dev)
    from app.services.unified_cache import UnifiedCache

    # Record request metric
    houses_requests_total.labels(
        system=req.system,
        house_system=req.house_system,
        topocentric=str(req.topocentric),
    ).inc()

    # parse ts with TZ-awareness; default to UTC if naive
    ts = datetime.fromisoformat(req.timestamp.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    # Content-addressed cache key using normalization + version stamps
    from shared.normalize import normalize_inputs, content_addressed_key
    api_version = os.getenv("OPENAPI_VERSION", "1.1.2")
    algo_version = os.getenv("ALGO_VERSION", "1.0.0")
    normalized = normalize_inputs(
        timestamp_iso=ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        lat=req.latitude,
        lon=req.longitude,
        alt_m=None,
    )
    cache_key = content_addressed_key(
        prefix="HOUSES",
        normalized=normalized,
        algo_version=algo_version,
        api_version=api_version,
    )

    # Initialize cache service for KP_HOUSES system
    cache = UnifiedCache(system="KP_HOUSES")

    # Try to get from cache
    cached = await cache.get(cache_key)
    if cached:
        # Record cache hit
        houses_cache_hits.inc()
        # Add cache hit indicator to meta
        cached["meta"]["cache_hit"] = True
        try:
            request.state.cache_status = "HIT"
        except Exception:
            pass
        # Trace cache hit
        with _tracer.start_as_current_span("houses.cache.hit") as span:
            set_common_attrs(
                span,
                cache_status="HIT",
                compute_ms=0.0,
                algo_version=os.getenv("ALGO_VERSION", "1.0.0"),
                api_version=os.getenv("OPENAPI_VERSION", "1.1.2"),
                norm_version=NORMALIZATION_VERSION,
                eph_version=EPHEMERIS_DATASET_VERSION,
            )
        return HousesResponse(**cached)

    # Record cache miss
    houses_cache_misses.inc()

    adapter = get_system(req.system)
    if adapter is None:
        houses_errors_total.labels(error_type="unknown_system").inc()
        raise HTTPException(status_code=400, detail=f"Unknown system: {req.system}")

    try:
        # Time the computation
        start_time = time.perf_counter()

        t0 = time.perf_counter()
        with _tracer.start_as_current_span("houses.compute") as span:
            payload = adapter.snapshot(
                ts_utc=ts.astimezone(UTC),
                lat=req.latitude,
                lon=req.longitude,
                house_system=req.house_system,
                topocentric=req.topocentric,
            )
            set_common_attrs(
                span,
                cache_status="MISS",
                compute_ms=round((time.perf_counter()-t0) * 1000, 3),
                algo_version=os.getenv("ALGO_VERSION", "1.0.0"),
                api_version=os.getenv("OPENAPI_VERSION", "1.1.2"),
                norm_version=NORMALIZATION_VERSION,
                eph_version=EPHEMERIS_DATASET_VERSION,
            )

        # Record computation time
        compute_time = time.perf_counter() - start_time
        houses_compute_seconds.labels(
            system=req.system,
            house_system=req.house_system,
            topocentric=str(req.topocentric),
        ).observe(compute_time)

        # Cache the result with 300s TTL
        await cache.set(cache_key, payload, ttl=300)

        # Add cache hit indicator and timing
        payload["meta"]["cache_hit"] = False
        payload["meta"]["compute_time_ms"] = round(compute_time * 1000, 3)

        try:
            request.state.cache_status = "MISS"
        except Exception:
            pass
    except ValueError as e:
        # Likely polar latitude error
        houses_errors_total.labels(error_type="polar_latitude").inc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        houses_errors_total.labels(error_type="calculation_error").inc()
        raise HTTPException(status_code=500, detail=f"House calculation failed: {e}")

    return HousesResponse(**payload)
