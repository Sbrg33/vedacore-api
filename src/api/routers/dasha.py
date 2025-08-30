#!/usr/bin/env python3
"""
Dasha API Router - Vimshottari Dasha period endpoints.
Provides REST API for dasha calculations with caching and metrics.
"""

import logging
import time

from datetime import date as DateType
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.cache_service import CacheService
from app.utils.hash_keys import cache_key_hash
from interfaces.kp_dasha_adapter import get_kp_dasha_adapter
from refactor.time_utils import validate_utc_datetime

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1", tags=["dasha"])

# Initialize cache service
cache_service = CacheService()

# Prometheus metrics
dasha_requests_total = Counter(
    "vedacore_dasha_requests_total",
    "Total dasha calculation requests",
    ["endpoint", "system", "levels"],
)

dasha_compute_seconds = Histogram(
    "vedacore_dasha_compute_seconds",
    "Dasha computation time in seconds",
    ["endpoint", "system", "levels"],
)

dasha_cache_hits_total = Counter(
    "vedacore_dasha_cache_hits_total", "Total dasha cache hits"
)

dasha_cache_misses_total = Counter(
    "vedacore_dasha_cache_misses_total", "Total dasha cache misses"
)

dasha_errors_total = Counter(
    "vedacore_dasha_errors_total", "Total dasha calculation errors", ["error_type"]
)


# Request/Response models
class DashaRequest(BaseModel):
    """Request model for dasha calculations"""

    model_config = ConfigDict(str_strip_whitespace=True)

    timestamp: datetime = Field(..., description="Reference UTC timestamp")
    birth_time: datetime = Field(..., description="Birth UTC timestamp")
    moon_longitude: float | None = Field(
        None, description="Pre-calculated Moon longitude at birth", ge=0, le=360
    )
    system: str = Field("KP_DASHA", description="Dasha system (always KP_DASHA)")
    levels: int = Field(
        3, description="Number of levels to calculate (1-5)", ge=1, le=5
    )
    chart_id: str | None = Field(
        None, description="Optional chart identifier for caching"
    )

    @field_validator("timestamp", "birth_time")
    @classmethod
    def validate_timestamps(cls, v):
        """Ensure timestamps are timezone-aware UTC"""
        try:
            return validate_utc_datetime(v)
        except Exception as e:
            raise ValueError(f"Invalid timestamp: {e}")

    @field_validator("system")
    @classmethod
    def validate_system(cls, v):
        """Ensure only KP_DASHA system is used"""
        if v != "KP_DASHA":
            raise ValueError("Only KP_DASHA system is supported")
        return v


class DashaChangesRequest(BaseModel):
    """Request model for dasha changes on a specific date"""

    model_config = ConfigDict(str_strip_whitespace=True)

    date: DateType = Field(..., description="Date to check for changes (UTC)")
    birth_time: datetime = Field(..., description="Birth UTC timestamp")
    moon_longitude: float | None = Field(
        None, description="Pre-calculated Moon longitude at birth", ge=0, le=360
    )
    system: str = Field("KP_DASHA", description="Dasha system (always KP_DASHA)")
    levels: int = Field(3, description="Number of levels to check (1-5)", ge=1, le=5)
    chart_id: str | None = Field(None, description="Optional chart identifier")

    @field_validator("birth_time")
    @classmethod
    def validate_birth_time(cls, v):
        """Ensure birth_time is timezone-aware UTC"""
        try:
            return validate_utc_datetime(v)
        except Exception as e:
            raise ValueError(f"Invalid birth_time: {e}")

    @field_validator("system")
    @classmethod
    def validate_system(cls, v):
        """Ensure only KP_DASHA system is used"""
        if v != "KP_DASHA":
            raise ValueError("Only KP_DASHA system is supported")
        return v


class DashaCycleRequest(BaseModel):
    """Request model for full dasha cycle"""

    birth_time: datetime = Field(..., description="Birth UTC timestamp")
    moon_longitude: float | None = Field(
        None, description="Pre-calculated Moon longitude at birth", ge=0, le=360
    )
    system: str = Field("KP_DASHA", description="Dasha system (always KP_DASHA)")
    levels: int = Field(2, description="Depth of nesting (1-5)", ge=1, le=5)
    chart_id: str | None = Field(None, description="Optional chart identifier")

    @field_validator("birth_time")
    @classmethod
    def validate_birth_time(cls, v):
        """Ensure birth_time is timezone-aware UTC"""
        try:
            return validate_utc_datetime(v)
        except Exception as e:
            raise ValueError(f"Invalid birth_time: {e}")

    @field_validator("system")
    @classmethod
    def validate_system(cls, v):
        """Ensure only KP_DASHA system is used"""
        if v != "KP_DASHA":
            raise ValueError("Only KP_DASHA system is supported")
        return v


def generate_cache_key(prefix: str, **kwargs) -> str:
    """Generate cache key from parameters"""
    # Sort kwargs for consistent key generation
    sorted_items = sorted(kwargs.items())
    key_str = f"{prefix}:" + ":".join(
        f"{k}={v}" for k, v in sorted_items if v is not None
    )

    # Hash long keys
    if len(key_str) > 200:
        return f"{prefix}:{cache_key_hash(key_str)}"

    return key_str


@router.post("/dasha", response_model=dict[str, Any])
async def calculate_dasha(request: DashaRequest) -> dict[str, Any]:
    """
    Calculate current Vimshottari Dasha periods.

    Returns active dasha chain at specified levels:
    - Level 1: Mahadasha only
    - Level 2: Mahadasha + Antardasha
    - Level 3: + Pratyantardasha
    - Level 4: + Sookshma
    - Level 5: + Prana
    """
    start_time = time.time()
    cache_hit = False

    try:
        # Update metrics
        dasha_requests_total.labels(
            endpoint="dasha", system=request.system, levels=str(request.levels)
        ).inc()

        # Generate cache key (cache for 1 day per chart)
        cache_key = generate_cache_key(
            "DASHA",
            system=request.system,
            birth=request.birth_time.isoformat(),
            ref=request.timestamp.date().isoformat(),
            levels=request.levels,
            moon=request.moon_longitude,
            chart=request.chart_id,
        )

        # Check cache
        cached_result = cache_service.get(cache_key)
        if cached_result:
            dasha_cache_hits_total.inc()
            cache_hit = True
            result = cached_result
        else:
            dasha_cache_misses_total.inc()

            # Get adapter
            adapter = get_kp_dasha_adapter()

            # Set birth data if chart_id provided
            if request.chart_id:
                adapter.set_birth_data(
                    chart_id=request.chart_id,
                    birth_time=request.birth_time,
                    moon_longitude=request.moon_longitude,
                )

            # Calculate dashas
            result = adapter.snapshot(
                ts_utc=request.timestamp,
                chart_id=request.chart_id,
                birth_time=request.birth_time if not request.chart_id else None,
                moon_longitude=request.moon_longitude,
                levels=request.levels,
            )

            # Cache result (TTL: 1 day)
            cache_service.set(cache_key, result, ttl=86400)

        # Add performance metadata
        compute_time = time.time() - start_time
        result["meta"]["cache_hit"] = cache_hit
        result["meta"]["compute_time_ms"] = round(compute_time * 1000, 3)

        # Update metrics
        dasha_compute_seconds.labels(
            endpoint="dasha", system=request.system, levels=str(request.levels)
        ).observe(compute_time)

        return result

    except Exception as e:
        logger.error(f"Error calculating dasha: {e}")
        dasha_errors_total.labels(error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dasha/changes", response_model=list[dict[str, Any]])
async def get_dasha_changes(request: DashaChangesRequest) -> list[dict[str, Any]]:
    """
    Get all dasha transitions occurring on a specific date.

    Returns list of change events with:
    - level: Which dasha level changed
    - type: 'start' or 'end'
    - planet: Planet involved
    - timestamp: Exact time of change
    """
    start_time = time.time()
    cache_hit = False

    try:
        # Update metrics
        dasha_requests_total.labels(
            endpoint="changes", system=request.system, levels=str(request.levels)
        ).inc()

        # Generate cache key
        cache_key = generate_cache_key(
            "DASHA_CHANGES",
            system=request.system,
            birth=request.birth_time.isoformat(),
            date=request.date.isoformat(),
            levels=request.levels,
            moon=request.moon_longitude,
            chart=request.chart_id,
        )

        # Check cache
        cached_result = cache_service.get(cache_key)
        if cached_result:
            dasha_cache_hits_total.inc()
            cache_hit = True
            changes = cached_result
        else:
            dasha_cache_misses_total.inc()

            # Get adapter
            adapter = get_kp_dasha_adapter()

            # Set birth data if chart_id provided
            if request.chart_id:
                adapter.set_birth_data(
                    chart_id=request.chart_id,
                    birth_time=request.birth_time,
                    moon_longitude=request.moon_longitude,
                )

            # Get changes
            changes = adapter.changes(
                day_utc=request.date,
                chart_id=request.chart_id,
                birth_time=request.birth_time if not request.chart_id else None,
                moon_longitude=request.moon_longitude,
                levels=request.levels,
            )

            # Cache result (TTL: 1 day)
            cache_service.set(cache_key, changes, ttl=86400)

        # Add metadata
        compute_time = time.time() - start_time
        for change in changes:
            change["meta"] = {
                "cache_hit": cache_hit,
                "compute_time_ms": round(compute_time * 1000, 3),
            }

        # Update metrics
        dasha_compute_seconds.labels(
            endpoint="changes", system=request.system, levels=str(request.levels)
        ).observe(compute_time)

        return changes

    except Exception as e:
        logger.error(f"Error getting dasha changes: {e}")
        dasha_errors_total.labels(error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dasha/cycle", response_model=dict[str, Any])
async def get_full_cycle(request: DashaCycleRequest) -> dict[str, Any]:
    """
    Get full 120-year Vimshottari cycle with nested periods.

    Returns hierarchical structure with all dasha periods.
    Warning: Response can be large with higher level values.
    """
    start_time = time.time()
    cache_hit = False

    try:
        # Update metrics
        dasha_requests_total.labels(
            endpoint="cycle", system=request.system, levels=str(request.levels)
        ).inc()

        # Warn about large responses
        if request.levels > 3:
            logger.warning(f"Large dasha cycle requested with {request.levels} levels")

        # Generate cache key
        cache_key = generate_cache_key(
            "DASHA_CYCLE",
            system=request.system,
            birth=request.birth_time.isoformat(),
            levels=request.levels,
            moon=request.moon_longitude,
            chart=request.chart_id,
        )

        # Check cache
        cached_result = cache_service.get(cache_key)
        if cached_result:
            dasha_cache_hits_total.inc()
            cache_hit = True
            result = cached_result
        else:
            dasha_cache_misses_total.inc()

            # Get adapter
            adapter = get_kp_dasha_adapter()

            # Set birth data if chart_id provided
            if request.chart_id:
                adapter.set_birth_data(
                    chart_id=request.chart_id,
                    birth_time=request.birth_time,
                    moon_longitude=request.moon_longitude,
                )

            # Get full cycle
            result = adapter.get_full_cycle(
                chart_id=request.chart_id,
                birth_time=request.birth_time if not request.chart_id else None,
                moon_longitude=request.moon_longitude,
                levels=request.levels,
            )

            # Cache result (TTL: 7 days for full cycles)
            cache_service.set(cache_key, result, ttl=604800)

        # Add performance metadata
        compute_time = time.time() - start_time
        result["meta"]["cache_hit"] = cache_hit
        result["meta"]["compute_time_ms"] = round(compute_time * 1000, 3)

        # Update metrics
        dasha_compute_seconds.labels(
            endpoint="cycle", system=request.system, levels=str(request.levels)
        ).observe(compute_time)

        return result

    except Exception as e:
        logger.error(f"Error getting full cycle: {e}")
        dasha_errors_total.labels(error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dasha/balance", response_model=dict[str, Any])
async def get_birth_balance(
    birth_time: datetime = Body(..., description="Birth UTC timestamp"),
    moon_longitude: float | None = Body(
        None, description="Pre-calculated Moon longitude", ge=0, le=360
    ),
) -> dict[str, Any]:
    """
    Get birth balance dasha information.

    Returns:
    - Birth nakshatra and lord
    - Elapsed and remaining days in birth dasha
    - Elapsed and remaining portions
    """
    start_time = time.time()

    try:
        # Validate timestamp
        birth_time = validate_utc_datetime(birth_time)

        # Update metrics
        dasha_requests_total.labels(
            endpoint="balance", system="KP_DASHA", levels="1"
        ).inc()

        # Get adapter
        adapter = get_kp_dasha_adapter()

        # Calculate birth balance
        result = adapter.get_birth_balance(
            birth_time=birth_time, moon_longitude=moon_longitude
        )

        # Add performance metadata
        compute_time = time.time() - start_time
        result["compute_time_ms"] = round(compute_time * 1000, 3)

        # Update metrics
        dasha_compute_seconds.labels(
            endpoint="balance", system="KP_DASHA", levels="1"
        ).observe(compute_time)

        return result

    except Exception as e:
        logger.error(f"Error calculating birth balance: {e}")
        dasha_errors_total.labels(error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dasha/systems")
async def list_dasha_systems() -> dict[str, Any]:
    """
    List available dasha systems and their capabilities.
    """
    return {
        "systems": [
            {
                "id": "KP_DASHA",
                "name": "Vimshottari Dasha",
                "description": "120-year planetary period system",
                "levels": [
                    "Mahadasha (major periods)",
                    "Antardasha (sub-periods)",
                    "Pratyantardasha (sub-sub-periods)",
                    "Sookshma (sub-sub-sub-periods)",
                    "Prana (sub-sub-sub-sub-periods)",
                ],
                "planets": [
                    "Ketu (7 years)",
                    "Venus (20 years)",
                    "Sun (6 years)",
                    "Moon (10 years)",
                    "Mars (7 years)",
                    "Rahu (18 years)",
                    "Jupiter (16 years)",
                    "Saturn (19 years)",
                    "Mercury (17 years)",
                ],
                "total_cycle": "120 years",
                "cache_ttl": {
                    "snapshot": "1 day",
                    "changes": "1 day",
                    "cycle": "7 days",
                },
            }
        ],
        "endpoints": [
            {
                "path": "/api/v1/dasha",
                "method": "POST",
                "description": "Get current active dasha periods",
            },
            {
                "path": "/api/v1/dasha/changes",
                "method": "POST",
                "description": "Get dasha transitions on a date",
            },
            {
                "path": "/api/v1/dasha/cycle",
                "method": "POST",
                "description": "Get full 120-year cycle",
            },
            {
                "path": "/api/v1/dasha/balance",
                "method": "POST",
                "description": "Get birth balance information",
            },
        ],
    }
