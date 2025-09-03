#!/usr/bin/env python3
"""
Moon API endpoints - Phase 7
Provides REST API for moon factors and anomaly detection
"""

import logging

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, Field, field_validator

from interfaces.kp_moon_adapter import KPMoonAdapter
from refactor.monitoring import (
    track_cache_hit,
    track_cache_miss,
    track_error,
    track_request,
)

router = APIRouter(prefix="/api/v1/moon", tags=["moon"], responses=DEFAULT_ERROR_RESPONSES)
logger = logging.getLogger(__name__)

# Initialize adapter
adapter: KPMoonAdapter | None = None


def get_adapter() -> KPMoonAdapter:
    """Get or create moon adapter"""
    global adapter
    if adapter is None:
        from app.core.session import cache_service

        adapter = KPMoonAdapter(cache_service)
    return adapter


# Request/Response Models


class MoonProfileRequest(BaseModel):
    """Request for moon profile"""

    date: datetime = Field(..., description="Date/time for profile (UTC)")
    system: str = Field("KP_MOON", description="System identifier")


class MoonEventsRequest(BaseModel):
    """Request for moon events"""

    start: datetime = Field(..., description="Start of search range (UTC)")
    end: datetime = Field(..., description="End of search range (UTC)")
    event_types: list[str] = Field(
        ["perigee", "apogee", "standstill"], description="Types of events to find"
    )

    @field_validator("end")
    @classmethod
    def validate_range(cls, v, values):
        if "start" in values.data and v <= values.data["start"]:
            raise ValueError("end must be after start")

        # Enforce max span
        if "start" in values.data:
            max_days = 365
            if (v - values.data["start"]).days > max_days:
                raise ValueError(f"Range cannot exceed {max_days} days")
        return v


class MoonProfileResponse(BaseModel):
    """Response for moon profile"""

    date: datetime
    tithi: str
    tithi_num: int
    paksha: str
    velocity_index: float
    latitude_index: float
    distance_index: float
    strength: str
    strength_score: float
    nakshatra: str
    phase: str
    illumination: float
    anomalies: dict[str, bool]
    system: str
    cached: bool = False


class MoonEventInfo(BaseModel):
    """Moon event information"""

    type: str
    timestamp: datetime
    value: float
    metadata: dict[str, Any]


class MoonEventsResponse(BaseModel):
    """Response for moon events"""

    start: datetime
    end: datetime
    events: list[MoonEventInfo]
    total_count: int
    cached: bool = False


class PanchangaResponse(BaseModel):
    """Response for panchanga elements"""

    timestamp: datetime
    tithi: str
    tithi_num: int
    tithi_percent: float
    paksha: str
    nakshatra: str
    nakshatra_num: int
    pada: int
    yoga: str
    yoga_num: int
    karana: str
    karana_num: int
    cached: bool = False


# Endpoints


@router.post(
    "/profile",
    response_model=MoonProfileResponse,
    summary="Get moon profile",
    operation_id="moon_profile",
)
async def get_moon_profile(request: MoonProfileRequest):
    """
    Get moon profile with Phase 7 indices

    Returns velocity index, latitude index, distance index,
    and overall strength assessment.
    """
    with track_request("moon_profile"):
        try:
            adapter = get_adapter()

            # Check cache
            cache_key = f"moon_profile_{request.date.date()}_{request.system}"

            if adapter.cache_service:
                cached = await adapter.cache_service.get(cache_key)
                if cached:
                    track_cache_hit("moon_profile")
                    cached["cached"] = True
                    return MoonProfileResponse(**cached)
                else:
                    track_cache_miss("moon_profile")

            # Calculate
            result = adapter.calculate(request.date, "profile")

            # Format response
            response_data = {
                "date": request.date,
                "tithi": result["tithi"],
                "tithi_num": result["tithi_num"],
                "paksha": result["paksha"],
                "velocity_index": result["velocity_index"],
                "latitude_index": result["latitude_index"],
                "distance_index": result["distance_index"],
                "strength": result["strength"],
                "strength_score": result["strength_score"],
                "nakshatra": result["nakshatra"],
                "phase": result["phase"],
                "illumination": result["illumination"],
                "anomalies": result["anomalies"],
                "system": request.system,
                "cached": False,
            }

            # Cache for 30 days (moon profiles are stable)
            if adapter.cache_service:
                await adapter.cache_service.set(
                    cache_key, response_data, ttl=86400 * 30
                )

            return MoonProfileResponse(**response_data)

        except ValueError as e:
            track_error("moon_profile", "validation_error")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            track_error("moon_profile", "internal_error")
            logger.error(f"Moon profile error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/events",
    response_model=MoonEventsResponse,
    summary="Find moon events",
    operation_id="moon_events",
)
async def find_moon_events(request: MoonEventsRequest):
    """
    Find moon anomaly events in date range

    Returns perigee, apogee, and standstill events.
    """
    with track_request("moon_events"):
        try:
            adapter = get_adapter()

            # Check cache
            cache_key = f"moon_events_{request.start.date()}_{request.end.date()}_{'-'.join(request.event_types)}"

            if adapter.cache_service:
                cached = await adapter.cache_service.get(cache_key)
                if cached:
                    track_cache_hit("moon_events")
                    cached["cached"] = True
                    return MoonEventsResponse(**cached)
                else:
                    track_cache_miss("moon_events")

            # Calculate
            result = adapter.calculate(
                request.start,
                "events",
                end_utc=request.end,
                event_types=request.event_types,
            )

            # Format response
            events = [
                MoonEventInfo(
                    type=e["type"],
                    timestamp=datetime.fromisoformat(e["timestamp"]),
                    value=e["value"],
                    metadata=e["metadata"],
                )
                for e in result["events"]
            ]

            response_data = {
                "start": request.start,
                "end": request.end,
                "events": events,
                "total_count": len(events),
                "cached": False,
            }

            # Cache for 90 days
            if adapter.cache_service:
                await adapter.cache_service.set(
                    cache_key, response_data, ttl=86400 * 90
                )

            return MoonEventsResponse(**response_data)

        except ValueError as e:
            track_error("moon_events", "validation_error")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            track_error("moon_events", "internal_error")
            logger.error(f"Moon events error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/panchanga",
    response_model=PanchangaResponse,
    summary="Get Panchanga",
    operation_id="moon_panchanga",
)
async def get_panchanga(
    timestamp: datetime = Query(..., description="Time for panchanga (UTC)")
):
    """
    Get panchanga elements for a specific time

    Returns tithi, nakshatra, yoga, karana, and paksha.
    """
    with track_request("moon_panchanga"):
        try:
            # Ensure timezone awareness
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)

            adapter = get_adapter()

            # Check cache
            cache_key = f"moon_panchanga_{timestamp.isoformat()}"

            if adapter.cache_service:
                cached = await adapter.cache_service.get(cache_key)
                if cached:
                    track_cache_hit("moon_panchanga")
                    cached["cached"] = True
                    return PanchangaResponse(**cached)
                else:
                    track_cache_miss("moon_panchanga")

            # Calculate
            result = adapter.calculate(timestamp, "panchanga")

            # Format response
            response_data = {
                "timestamp": timestamp,
                "tithi": result["tithi"],
                "tithi_num": result["tithi_num"],
                "tithi_percent": result["tithi_percent"],
                "paksha": result["paksha"],
                "nakshatra": result["nakshatra"],
                "nakshatra_num": result["nakshatra_num"],
                "pada": result["pada"],
                "yoga": result["yoga"],
                "yoga_num": result["yoga_num"],
                "karana": result["karana"],
                "karana_num": result["karana_num"],
                "cached": False,
            }

            # Cache for 1 day
            if adapter.cache_service:
                await adapter.cache_service.set(cache_key, response_data, ttl=86400)

            return PanchangaResponse(**response_data)

        except Exception as e:
            track_error("moon_panchanga", "internal_error")
            logger.error(f"Panchanga error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/strength",
    summary="Moon strength",
    operation_id="moon_strength",
)
async def get_moon_strength(
    timestamp: datetime = Query(..., description="Time to check (UTC)")
):
    """
    Get moon strength assessment

    Returns strength indices and anomaly flags.
    """
    with track_request("moon_strength"):
        try:
            # Ensure timezone awareness
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)

            adapter = get_adapter()

            # Calculate
            result = adapter.calculate(timestamp, "strength")

            return result

        except Exception as e:
            track_error("moon_strength", "internal_error")
            logger.error(f"Moon strength error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/config",
    summary="Moon config",
    operation_id="moon_config",
)
async def get_moon_config():
    """
    Get current moon configuration
    """
    adapter = get_adapter()
    return adapter.get_metadata()
