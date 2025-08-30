#!/usr/bin/env python3
"""
Eclipse API endpoints
Provides REST API for eclipse predictions
"""

import logging

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from interfaces.kp_eclipse_adapter import KPEclipseAdapter
from refactor.monitoring import (
    track_cache_hit,
    track_cache_miss,
    track_error,
    track_request,
)

router = APIRouter(prefix="/api/v1/eclipse", tags=["eclipse"])
logger = logging.getLogger(__name__)

# Initialize adapter
adapter: KPEclipseAdapter | None = None


def get_adapter() -> KPEclipseAdapter:
    """Get or create eclipse adapter"""
    global adapter
    if adapter is None:
        from app.core.session import cache_service

        adapter = KPEclipseAdapter(cache_service)
    return adapter


# Request/Response Models


class EclipseSearchRequest(BaseModel):
    """Request for eclipse search"""

    start: datetime = Field(..., description="Start of search range (UTC)")
    end: datetime = Field(..., description="End of search range (UTC)")
    eclipse_type: Literal["solar", "lunar", "both"] = Field(
        "both", description="Type of eclipses to find"
    )

    @field_validator("end")
    @classmethod
    def validate_range(cls, v, values):
        if "start" in values.data and v <= values.data["start"]:
            raise ValueError("end must be after start")

        # Enforce max span from config
        if "start" in values.data:
            max_days = 365 * 5  # Default max_span_years
            if (v - values.data["start"]).days > max_days:
                raise ValueError(f"Range cannot exceed {max_days} days")
        return v


class VisibilityRequest(BaseModel):
    """Request for local visibility check"""

    timestamp: datetime = Field(..., description="Time to check (UTC)")
    latitude: float = Field(
        ..., ge=-90, le=90, description="Latitude in decimal degrees"
    )
    longitude: float = Field(
        ..., ge=-180, le=180, description="Longitude in decimal degrees"
    )
    eclipse_type: Literal["solar", "lunar"] = Field(
        "solar", description="Type of eclipse"
    )

    # Support old field names for backward compatibility
    lat: float | None = Field(default=None, exclude=True)
    lon: float | None = Field(default=None, exclude=True)

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


class PathRequest(BaseModel):
    """Request for solar eclipse path"""

    timestamp: datetime = Field(..., description="Eclipse time (UTC)")


class NextEclipseRequest(BaseModel):
    """Request for next eclipse"""

    after: datetime = Field(..., description="Start searching after this time (UTC)")
    eclipse_type: Literal["solar", "lunar", "any"] = Field(
        "any", description="Type of eclipse"
    )
    classification: str | None = Field(
        None, description="Specific classification (e.g., 'total', 'partial')"
    )


class EclipseInfo(BaseModel):
    """Eclipse information"""

    kind: str
    classification: str
    peak_utc: datetime
    magnitude: float | None
    saros: str | None
    gamma: float | None
    duration_minutes: float | None
    contacts: dict[str, datetime]
    meta: dict[str, Any]


class EclipseSearchResponse(BaseModel):
    """Response for eclipse search"""

    start: datetime
    end: datetime
    solar: list[EclipseInfo] | None = None
    lunar: list[EclipseInfo] | None = None
    total_count: int
    cached: bool = False


class VisibilityResponse(BaseModel):
    """Response for visibility check"""

    eclipse: EclipseInfo | None
    visible: bool
    magnitude: float | None = None
    obscuration: float | None = None
    altitude: float | None = None
    azimuth: float | None = None
    start_time: datetime | None = None
    max_time: datetime | None = None
    end_time: datetime | None = None
    location: dict[str, float]
    cached: bool = False


class PathResponse(BaseModel):
    """Response for eclipse path"""

    found: bool
    eclipse: EclipseInfo | None
    central_line: list[list[float]] | None = None
    northern_limit: list[list[float]] | None = None
    southern_limit: list[list[float]] | None = None
    max_width_km: float | None = None
    timestamps: list[datetime] | None = None
    reason: str | None = None
    cached: bool = False


class NextEclipseResponse(BaseModel):
    """Response for next eclipse"""

    found: bool
    eclipse: EclipseInfo | None
    days_until: int | None
    search_params: dict[str, Any]
    cached: bool = False


# Endpoints


@router.post("/events", response_model=EclipseSearchResponse)
async def search_eclipses(request: EclipseSearchRequest):
    """
    Find eclipses within a date range

    Returns solar and/or lunar eclipses between start and end dates.
    Maximum range is 5 years.
    """
    with track_request("eclipse_events"):
        try:
            adapter = get_adapter()

            # Check cache
            cache_key = f"eclipse_events_{request.start.date()}_{request.end.date()}_{request.eclipse_type}"

            if adapter.cache_service:
                cached = adapter.cache_service.get(cache_key)
                if cached:
                    track_cache_hit("eclipse_events")
                    cached["cached"] = True
                    return EclipseSearchResponse(**cached)
                else:
                    track_cache_miss("eclipse_events")

            # Calculate
            result = adapter.calculate(
                request.start,
                "events",
                end_utc=request.end,
                eclipse_type=request.eclipse_type,
            )

            # Format response
            response_data = {
                "start": request.start,
                "end": request.end,
                "solar": result.get("solar"),
                "lunar": result.get("lunar"),
                "total_count": len(result.get("solar", []))
                + len(result.get("lunar", [])),
                "cached": False,
            }

            # Cache for 1 day (events don't change)
            if adapter.cache_service:
                adapter.cache_service.set(cache_key, response_data, ttl=86400)

            return EclipseSearchResponse(**response_data)

        except ValueError as e:
            track_error("eclipse_events", "validation_error")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            track_error("eclipse_events", "internal_error")
            logger.error(f"Eclipse search error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/visibility", response_model=VisibilityResponse)
async def check_visibility(request: VisibilityRequest):
    """
    Check local visibility of an eclipse

    Determines if an eclipse is visible from a specific location
    and provides visibility details.
    """
    with track_request("eclipse_visibility"):
        try:
            adapter = get_adapter()

            # Check cache
            cache_key = f"eclipse_vis_{request.timestamp.date()}_{request.latitude:.2f}_{request.longitude:.2f}_{request.eclipse_type}"

            if adapter.cache_service:
                cached = adapter.cache_service.get(cache_key)
                if cached:
                    track_cache_hit("eclipse_visibility")
                    cached["cached"] = True
                    return VisibilityResponse(**cached)
                else:
                    track_cache_miss("eclipse_visibility")

            # Calculate
            result = adapter.calculate(
                request.timestamp,
                "visibility",
                lat=request.latitude,
                lon=request.longitude,
                eclipse_type=request.eclipse_type,
            )

            # Format response
            visibility = result.get("visibility", {})
            response_data = {
                "eclipse": result.get("eclipse"),
                "visible": visibility.get("visible", False) if visibility else False,
                "magnitude": visibility.get("magnitude") if visibility else None,
                "obscuration": visibility.get("obscuration") if visibility else None,
                "altitude": visibility.get("altitude") if visibility else None,
                "azimuth": visibility.get("azimuth") if visibility else None,
                "start_time": visibility.get("start_time") if visibility else None,
                "max_time": visibility.get("max_time") if visibility else None,
                "end_time": visibility.get("end_time") if visibility else None,
                "location": result.get(
                    "location", {"lat": request.lat, "lon": request.lon}
                ),
                "cached": False,
            }

            # Cache for 1 hour
            if adapter.cache_service:
                adapter.cache_service.set(cache_key, response_data, ttl=3600)

            return VisibilityResponse(**response_data)

        except ValueError as e:
            track_error("eclipse_visibility", "validation_error")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            track_error("eclipse_visibility", "internal_error")
            logger.error(f"Visibility check error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/path", response_model=PathResponse)
async def get_eclipse_path(request: PathRequest):
    """
    Get the path of a solar eclipse

    Returns the central line and limits of a solar eclipse.
    Only applicable for total, annular, and hybrid eclipses.
    """
    with track_request("eclipse_path"):
        try:
            adapter = get_adapter()

            # Check cache
            cache_key = f"eclipse_path_{request.timestamp.date()}"

            if adapter.cache_service:
                cached = adapter.cache_service.get(cache_key)
                if cached:
                    track_cache_hit("eclipse_path")
                    cached["cached"] = True
                    return PathResponse(**cached)
                else:
                    track_cache_miss("eclipse_path")

            # Calculate
            result = adapter.calculate(request.timestamp, "path")

            # Format response
            path_data = result.get("path", {})
            response_data = {
                "found": result.get("found", False),
                "eclipse": result.get("eclipse"),
                "central_line": path_data.get("central_line") if path_data else None,
                "northern_limit": (
                    path_data.get("northern_limit") if path_data else None
                ),
                "southern_limit": (
                    path_data.get("southern_limit") if path_data else None
                ),
                "max_width_km": path_data.get("max_width_km") if path_data else None,
                "timestamps": path_data.get("timestamps") if path_data else None,
                "reason": result.get("reason"),
                "cached": False,
            }

            # Cache for 1 day
            if adapter.cache_service:
                adapter.cache_service.set(cache_key, response_data, ttl=86400)

            return PathResponse(**response_data)

        except Exception as e:
            track_error("eclipse_path", "internal_error")
            logger.error(f"Path calculation error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/next", response_model=NextEclipseResponse)
async def find_next_eclipse(request: NextEclipseRequest):
    """
    Find the next eclipse after a given time

    Searches for the next eclipse of the specified type and classification.
    """
    with track_request("eclipse_next"):
        try:
            adapter = get_adapter()

            # Check cache (short TTL since "next" changes)
            cache_key = f"eclipse_next_{request.after.date()}_{request.eclipse_type}_{request.classification}"

            if adapter.cache_service:
                cached = adapter.cache_service.get(cache_key)
                if cached:
                    track_cache_hit("eclipse_next")
                    cached["cached"] = True
                    return NextEclipseResponse(**cached)
                else:
                    track_cache_miss("eclipse_next")

            # Calculate
            result = adapter.calculate(
                request.after,
                "next",
                eclipse_type=request.eclipse_type,
                classification=request.classification,
            )

            # Format response
            response_data = {
                "found": result.get("found", False),
                "eclipse": result.get("eclipse"),
                "days_until": result.get("days_until"),
                "search_params": result.get(
                    "search_params",
                    {
                        "eclipse_type": request.eclipse_type,
                        "classification": request.classification,
                    },
                ),
                "cached": False,
            }

            # Cache for 1 hour
            if adapter.cache_service:
                adapter.cache_service.set(cache_key, response_data, ttl=3600)

            return NextEclipseResponse(**response_data)

        except Exception as e:
            track_error("eclipse_next", "internal_error")
            logger.error(f"Next eclipse search error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/config")
async def get_eclipse_config():
    """
    Get current eclipse configuration
    """
    adapter = get_adapter()
    return adapter.get_metadata()
