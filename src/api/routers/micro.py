"""
Market Micro-Timing API Router
Phase 8: REST endpoints for volatility window generation
"""

from __future__ import annotations

import logging
import time

from datetime import UTC, date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel, Field, field_validator

from interfaces.registry import get_system
from api.models.responses import (
    MicroDayResponse,
    MicroRangeResponse,
    MicroNextResponse,
    MicroInstantResponse,
    MicroConfigResponse,
)

logger = logging.getLogger(__name__)
UTC = UTC

# Prometheus metrics
micro_requests = Counter(
    "vedacore_micro_requests_total",
    "Total micro-timing requests",
    ["endpoint", "system"],
)

micro_compute_time = Histogram(
    "vedacore_micro_compute_seconds",
    "Micro-timing computation time",
    ["endpoint", "system"],
)

micro_window_count = Gauge(
    "vedacore_micro_window_count",
    "Number of volatility windows generated",
    ["strength", "system"],
)

micro_errors = Counter(
    "vedacore_micro_errors_total",
    "Total micro-timing errors",
    ["endpoint", "error_type"],
)

router = APIRouter(
    prefix="/api/v1/micro",
    tags=["micro-timing"],
    responses={404: {"description": "Not found"}},
)

Strength = Literal["low", "medium", "high"]


class DayRequest(BaseModel):
    """Request for single day volatility timeline."""

    date: str = Field(
        ..., description="Date in YYYY-MM-DD format", example="2025-09-05"
    )
    system: str = Field(default="KP_MICRO", description="System identifier")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format."""
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}")


class RangeRequest(BaseModel):
    """Request for date range volatility timeline."""

    start: str = Field(
        ..., description="Start date in YYYY-MM-DD format", example="2025-09-01"
    )
    end: str = Field(
        ..., description="End date in YYYY-MM-DD format", example="2025-09-07"
    )
    system: str = Field(default="KP_MICRO", description="System identifier")

    @field_validator("start", "end")
    @classmethod
    def validate_dates(cls, v: str) -> str:
        """Validate date format."""
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}")


class InstantRequest(BaseModel):
    """Request for instantaneous volatility score."""

    timestamp: str = Field(
        ..., description="ISO format timestamp", example="2025-09-05T14:30:00Z"
    )
    system: str = Field(default="KP_MICRO", description="System identifier")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate timestamp format."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {v}")


@router.post("/day", summary="Get volatility windows for a day", response_model=MicroDayResponse)
async def micro_day(req: DayRequest = Body(...)) -> MicroDayResponse:
    """
    Generate volatility windows for a single day.

    Returns a timeline of micro-volatility windows with scores and factors.
    """
    micro_requests.labels(endpoint="day", system=req.system).inc()

    try:
        start_time = time.time()

        # Get adapter
        adapter = get_system(req.system)
        if adapter is None:
            micro_errors.labels(endpoint="day", error_type="unknown_system").inc()
            raise HTTPException(status_code=400, detail=f"Unknown system: {req.system}")

        # Parse date
        day = date.fromisoformat(req.date)

        # Generate timeline
        result = adapter.day(day)

        # Update metrics
        compute_time = time.time() - start_time
        micro_compute_time.labels(endpoint="day", system=req.system).observe(
            compute_time
        )

        # Count windows by strength
        for strength in ["high", "medium", "low"]:
            count = sum(
                1 for w in result.get("windows", []) if w.get("strength") == strength
            )
            micro_window_count.labels(strength=strength, system=req.system).set(count)

        return MicroDayResponse(
            date=req.date,
            system=req.system,
            windows=result.get("windows", []),
            summary=result.get("summary", {}),
            computation_time_ms=compute_time * 1000,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in micro_day: {e}")
        micro_errors.labels(endpoint="day", error_type="internal").inc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.post("/range", summary="Get volatility windows for date range", response_model=MicroRangeResponse)
async def micro_range(req: RangeRequest = Body(...)) -> MicroRangeResponse:
    """
    Generate volatility windows for a date range.

    Returns merged timeline across multiple days.
    """
    micro_requests.labels(endpoint="range", system=req.system).inc()

    try:
        start_time = time.time()

        # Get adapter
        adapter = get_system(req.system)
        if adapter is None:
            micro_errors.labels(endpoint="range", error_type="unknown_system").inc()
            raise HTTPException(status_code=400, detail=f"Unknown system: {req.system}")

        # Parse dates
        start_day = date.fromisoformat(req.start)
        end_day = date.fromisoformat(req.end)

        if end_day < start_day:
            micro_errors.labels(endpoint="range", error_type="invalid_range").inc()
            raise HTTPException(
                status_code=400, detail="End date must be >= start date"
            )

        # Generate timeline
        result = adapter.range(start_day, end_day)

        # Update metrics
        compute_time = time.time() - start_time
        micro_compute_time.labels(endpoint="range", system=req.system).observe(
            compute_time
        )

        return MicroRangeResponse(
            start_date=req.start,
            end_date=req.end,
            system=req.system,
            timeline=result.get("timeline", []),
            summary=result.get("summary", {}),
            computation_time_ms=compute_time * 1000,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in micro_range: {e}")
        micro_errors.labels(endpoint="range", error_type="internal").inc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.get("/next", summary="Find next volatility window", response_model=MicroNextResponse)
async def micro_next(
    system: str = Query(default="KP_MICRO", description="System identifier"),
    threshold: Strength = Query(
        default="high", description="Minimum volatility strength"
    ),
) -> MicroNextResponse:
    """
    Find the next upcoming volatility window meeting the threshold.

    Searches up to max_days_range (default 31) days ahead.
    """
    micro_requests.labels(endpoint="next", system=system).inc()

    try:
        start_time = time.time()

        # Get adapter
        adapter = get_system(system)
        if adapter is None:
            micro_errors.labels(endpoint="next", error_type="unknown_system").inc()
            raise HTTPException(status_code=400, detail=f"Unknown system: {system}")

        # Find next window
        result = adapter.next(threshold)

        # Update metrics
        compute_time = time.time() - start_time
        micro_compute_time.labels(endpoint="next", system=system).observe(compute_time)

        return MicroNextResponse(
            system=system,
            threshold=threshold,
            next_window=result.get("next_window"),
            search_range_days=result.get("search_range_days", 31),
            found=result.get("found", False),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in micro_next: {e}")
        micro_errors.labels(endpoint="next", error_type="internal").inc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.post("/instant", summary="Get instantaneous volatility score", response_model=MicroInstantResponse)
async def micro_instant(req: InstantRequest = Body(...)) -> MicroInstantResponse:
    """
    Calculate volatility score at a specific timestamp.

    Returns score, strength, and active contributing factors.
    """
    micro_requests.labels(endpoint="instant", system=req.system).inc()

    try:
        start_time = time.time()

        # Get adapter
        adapter = get_system(req.system)
        if adapter is None:
            micro_errors.labels(endpoint="instant", error_type="unknown_system").inc()
            raise HTTPException(status_code=400, detail=f"Unknown system: {req.system}")

        # Parse timestamp
        ts = datetime.fromisoformat(req.timestamp.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        # Calculate instant score
        result = adapter.instant(ts)

        # Update metrics
        compute_time = time.time() - start_time
        micro_compute_time.labels(endpoint="instant", system=req.system).observe(
            compute_time
        )

        return MicroInstantResponse(
            timestamp=req.timestamp,
            system=req.system,
            score=result.get("score", 0),
            strength=result.get("strength", "low"),
            factors=result.get("factors", []),
            computation_time_ms=compute_time * 1000,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in micro_instant: {e}")
        micro_errors.labels(endpoint="instant", error_type="internal").inc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.get("/config", summary="Get micro-timing configuration", response_model=MicroConfigResponse)
async def micro_config(system: str = Query(default="KP_MICRO")) -> MicroConfigResponse:
    """
    Get current micro-timing configuration and metadata.

    Returns weights, thresholds, window sizes, and feature flags.
    """
    try:
        # Get adapter
        adapter = get_system(system)
        if adapter is None:
            raise HTTPException(status_code=400, detail=f"Unknown system: {system}")

        # Get metadata
        if hasattr(adapter, "get_metadata"):
            metadata = adapter.get_metadata()
            return MicroConfigResponse(
                system=system,
                config=metadata.get("config", {}),
                weights=metadata.get("weights", {}),
                thresholds=metadata.get("thresholds", {}),
                features=metadata.get("features", {}),
            )
        else:
            return MicroConfigResponse(
                system=system,
                config={},
                weights={},
                thresholds={},
                features={"message": "Metadata not available"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in micro_config: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")
