"""
API endpoints for Vedic/KP/Jaimini advisory layers.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.advisory_service import get_advisory_service

router = APIRouter(prefix="/api/v1/advisory", tags=["advisory"])


class AdvisoryRequest(BaseModel):
    """Request for advisory calculations."""

    timestamp: datetime = Field(..., description="UTC timestamp for calculations")
    latitude: float = Field(default=40.7128, description="Location latitude")
    longitude: float = Field(default=-74.0060, description="Location longitude")
    include_timing: bool = Field(default=False, description="Include timing metrics")


class AdvisoryRangeRequest(BaseModel):
    """Request for advisory calculations over a time range."""

    start_time: datetime = Field(..., description="Start of time range (UTC)")
    end_time: datetime = Field(..., description="End of time range (UTC)")
    interval_minutes: int = Field(
        default=60, ge=1, le=1440, description="Sampling interval in minutes"
    )
    latitude: float = Field(default=40.7128, description="Location latitude")
    longitude: float = Field(default=-74.0060, description="Location longitude")


class RulingPlanetsRequest(BaseModel):
    """Request for KP Ruling Planets calculation."""

    timestamp: datetime = Field(..., description="UTC timestamp")
    ascendant: float = Field(..., ge=0, lt=360, description="Ascendant longitude")
    moon_longitude: float = Field(..., ge=0, lt=360, description="Moon longitude")
    sunrise: datetime | None = Field(None, description="Sunrise time (UTC)")


@router.post("/snapshot", summary="Get advisory snapshot at timestamp")
async def get_advisory_snapshot(request: AdvisoryRequest):
    """Get all enabled advisory calculations for a specific moment.

    Returns advisory layers based on enabled feature flags.
    Only modules with enabled flags will be included in the response.
    """
    try:
        service = get_advisory_service()

        # Ensure UTC
        if request.timestamp.tzinfo is None:
            request.timestamp = request.timestamp.replace(tzinfo=UTC)

        result = service.collect_advisory_layers(
            timestamp=request.timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
            include_timing=request.include_timing,
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/range", summary="Get advisory data for time range")
async def get_advisory_range(request: AdvisoryRangeRequest):
    """Get advisory snapshots over a time range.

    Samples advisory data at regular intervals across the specified range.
    Useful for identifying patterns and timing windows.
    """
    try:
        service = get_advisory_service()

        # Validate time range
        if request.end_time <= request.start_time:
            raise ValueError("End time must be after start time")

        # Limit range to prevent excessive computation
        max_hours = 168  # 1 week
        duration = (request.end_time - request.start_time).total_seconds() / 3600
        if duration > max_hours:
            raise ValueError(f"Time range exceeds maximum of {max_hours} hours")

        # Ensure UTC
        if request.start_time.tzinfo is None:
            request.start_time = request.start_time.replace(tzinfo=UTC)
        if request.end_time.tzinfo is None:
            request.end_time = request.end_time.replace(tzinfo=UTC)

        snapshots = service.get_advisory_for_range(
            start_time=request.start_time,
            end_time=request.end_time,
            interval_minutes=request.interval_minutes,
            latitude=request.latitude,
            longitude=request.longitude,
        )

        return {
            "start": request.start_time.isoformat(),
            "end": request.end_time.isoformat(),
            "interval_minutes": request.interval_minutes,
            "count": len(snapshots),
            "snapshots": snapshots,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features", summary="Get feature flag status")
async def get_feature_status():
    """Get current status of advisory feature flags.

    Shows which advisory modules are enabled, available, and their configuration.
    """
    try:
        service = get_advisory_service()
        return service.get_feature_status()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ruling-planets", summary="Calculate KP Ruling Planets")
async def calculate_ruling_planets(request: RulingPlanetsRequest):
    """Calculate KP Ruling Planets for a given moment.

    Returns the ruling planets based on:
    - Ascendant sign, star, and sub lords
    - Moon sign, star, and sub lords
    - Day lord (Vara)
    - Hora lord (planetary hour)

    Requires ENABLE_KP_RULING_PLANETS feature flag.
    """
    try:
        from config.feature_flags import is_feature_enabled

        if not is_feature_enabled("kp_ruling_planets"):
            raise HTTPException(
                status_code=503, detail="KP Ruling Planets feature is not enabled"
            )

        from modules.transits.ruling_planets import calculate_ruling_planets

        # Ensure UTC
        if request.timestamp.tzinfo is None:
            request.timestamp = request.timestamp.replace(tzinfo=UTC)

        ctx = {
            "timestamp": request.timestamp,
            "ascendant": request.ascendant,
            "moon_longitude": request.moon_longitude,
            "sunrise": request.sunrise,
        }

        result = calculate_ruling_planets(ctx)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shadbala", summary="Calculate Shadbala strength")
async def calculate_shadbala(request: AdvisoryRequest):
    """Calculate six-fold planetary strength (Shadbala).

    Returns strength components:
    - Sthana Bala (positional)
    - Dig Bala (directional)
    - Kala Bala (temporal)
    - Chesta Bala (motional)
    - Naisargika Bala (natural)
    - Drik Bala (aspectual)

    Requires ENABLE_SHADBALA feature flag.
    """
    try:
        from config.feature_flags import is_feature_enabled

        if not is_feature_enabled("shadbala"):
            raise HTTPException(
                status_code=503, detail="Shadbala feature is not enabled"
            )

        from app.services.advisory_service import AdvisoryContext
        from modules.vedic_strength.shadbala import compute_shadbala

        # Create context
        ctx = AdvisoryContext(
            timestamp=request.timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
        )

        result = compute_shadbala(ctx.to_dict())

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", summary="Advisory service health check")
async def health_check():
    """Check advisory service health and configuration."""
    try:
        service = get_advisory_service()
        status = service.get_feature_status()

        return {
            "status": "healthy",
            "enabled_count": len(status["enabled"]),
            "available_count": len(status["available"]),
            "features": status["enabled"],
        }

    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
