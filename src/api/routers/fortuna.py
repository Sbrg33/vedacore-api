#!/usr/bin/env python3
"""
Fortuna Points API Router
Endpoints for Arabic Parts/Sahams calculations
"""

from datetime import UTC, datetime, time
from datetime import date as Date
from typing import Any

from fastapi import APIRouter, HTTPException
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, ConfigDict, Field

from refactor.facade import (
    get_fortuna_points,
    get_part_of_fortune,
    track_fortuna_movement_for_day,
)
from refactor.fortuna_points import FortunaPoint

router = APIRouter(prefix="/api/v1/fortuna", tags=["fortuna"], responses=DEFAULT_ERROR_RESPONSES)


class FortunaRequest(BaseModel):
    """Request for fortuna points calculation"""

    timestamp: datetime = Field(..., description="Time for calculation (UTC)")
    latitude: float = Field(..., ge=-90, le=90, description="Location latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Location longitude")
    points: list[str] | None = Field(
        None, description="Specific points to calculate (default: all)"
    )
    include_aspects: bool = Field(
        False, description="Include planetary aspects to points"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-08-20T14:30:00Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "points": ["FORTUNE", "SPIRIT", "LOVE"],
                "include_aspects": True,
            }
        }
    )


class PartOfFortuneRequest(BaseModel):
    """Request for Part of Fortune calculation"""

    timestamp: datetime = Field(..., description="Time for calculation (UTC)")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    include_dignity: bool = Field(
        True, description="Include sign/house dignity analysis"
    )
    include_aspects: bool = Field(True, description="Include aspects from planets")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-08-20T14:30:00Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "include_dignity": True,
                "include_aspects": True,
            }
        }
    )


class FortunaMovementRequest(BaseModel):
    """Request for tracking fortuna movement"""

    date: Date = Field(..., description="Date to track (UTC)")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    points: list[str] | None = Field(
        default=["FORTUNE", "SPIRIT"], description="Points to track"
    )
    interval_hours: int = Field(
        1, ge=1, le=24, description="Tracking interval in hours"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2024-08-20",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "points": ["FORTUNE", "SPIRIT"],
                "interval_hours": 1,
            }
        }
    )


class FortunaRangeRequest(BaseModel):
    """Request for fortuna points over time range"""

    start: datetime = Field(..., description="Start time (UTC)")
    end: datetime = Field(..., description="End time (UTC)")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    point: str = Field("FORTUNE", description="Fortuna point to track")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "start": "2024-08-20T00:00:00Z",
                "end": "2024-08-20T23:59:59Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "point": "FORTUNE",
            }
        }
    )


from api.models.responses import (
    FortunaCalculateResponse,
    PartOfFortuneResponse,
    FortunaMovementResponse,
    FortunaRangeResponse,
    FortunaAvailablePoint,
    FortunaHelpResponse,
)


@router.post(
    "/calculate",
    response_model=FortunaCalculateResponse,
    summary="Calculate Fortuna/Arabic Parts",
    operation_id="fortuna_calculate",
)
async def calculate_fortuna_points(request: FortunaRequest) -> FortunaCalculateResponse:
    """
    Calculate Arabic Parts/Fortuna Points.

    Returns positions and interpretations for requested points.
    Includes Part of Fortune, Spirit, Love, Marriage, Career, etc.
    """
    try:
        # Get all fortuna points
        all_points = get_fortuna_points(
            timestamp=request.timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
        )

        # Filter if specific points requested
        if request.points:
            filtered = {}
            for point_name in request.points:
                point_key = point_name.upper()
                if point_key in all_points:
                    filtered[point_key] = all_points[point_key]
            result = filtered if filtered else all_points
        else:
            result = all_points

        # Add aspects if requested
        if request.include_aspects:
            # This would call aspect calculation functions
            # Simplified for now
            for point_data in result.values():
                point_data["aspects"] = {
                    "note": "Aspect calculation would be added here",
                    "conjunctions": [],
                    "oppositions": [],
                    "trines": [],
                    "squares": [],
                }

        return {
            "timestamp": request.timestamp.isoformat(),
            "location": {"latitude": request.latitude, "longitude": request.longitude},
            "fortuna_points": result,
            "count": len(result),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/part-of-fortune",
    response_model=PartOfFortuneResponse,
    summary="Calculate Part of Fortune",
    operation_id="fortuna_partOfFortune",
)
async def calculate_part_of_fortune(request: PartOfFortuneRequest) -> PartOfFortuneResponse:
    """
    Calculate Part of Fortune with detailed analysis.

    The most important Arabic Part, representing worldly success
    and the integration of solar and lunar energies.
    """
    try:
        result = get_part_of_fortune(
            timestamp=request.timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
            include_aspects=request.include_aspects,
        )

        # Add dignity analysis if requested
        if request.include_dignity:
            # Calculate sign ruler and house position
            # Simplified implementation
            longitude = result["longitude"]
            sign = int(longitude / 30) + 1

            sign_names = [
                "Aries",
                "Taurus",
                "Gemini",
                "Cancer",
                "Leo",
                "Virgo",
                "Libra",
                "Scorpio",
                "Sagittarius",
                "Capricorn",
                "Aquarius",
                "Pisces",
            ]

            result["dignity"] = {
                "sign": sign_names[sign - 1],
                "sign_number": sign,
                "degree_in_sign": longitude % 30,
                "interpretation": f"Part of Fortune in {sign_names[sign - 1]}",
            }

        return {
            "timestamp": request.timestamp.isoformat(),
            "location": {"latitude": request.latitude, "longitude": request.longitude},
            "part_of_fortune": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/movement",
    response_model=FortunaMovementResponse,
    summary="Track Fortuna movement",
    operation_id="fortuna_movement",
)
async def track_fortuna_movement(request: FortunaMovementRequest) -> FortunaMovementResponse:
    """
    Track movement of fortuna points throughout a day.

    Shows how Arabic Parts move through houses and signs,
    useful for intraday timing.
    """
    try:
        # Track movement for the day
        # Convert date to datetime at start of day
        start_of_day = datetime.combine(request.date, time.min, tzinfo=UTC)
        movement_data = track_fortuna_movement_for_day(
            date=start_of_day,
            latitude=request.latitude,
            longitude=request.longitude,
            fortuna_type="FORTUNE",
        )

        # Filter for requested points
        if request.points:
            filtered_movement = {}
            for point_name in request.points:
                if point_name in movement_data:
                    filtered_movement[point_name] = movement_data[point_name]
            movement_data = filtered_movement

        # Calculate statistics
        stats = {}
        for point_name, hours in movement_data.items():
            if hours:
                positions = [h["longitude"] for h in hours]
                min_pos = min(positions)
                max_pos = max(positions)
                movement = max_pos - min_pos
                if movement < 0:  # Crossed 0° Aries
                    movement += 360

                stats[point_name] = {
                    "total_movement": round(movement, 2),
                    "average_speed": round(movement / len(hours), 2),
                    "min_longitude": round(min_pos, 2),
                    "max_longitude": round(max_pos, 2),
                }

        return {
            "date": request.date.isoformat(),
            "location": {"latitude": request.latitude, "longitude": request.longitude},
            "interval_hours": request.interval_hours,
            "movement": movement_data,
            "statistics": stats,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/range",
    response_model=FortunaRangeResponse,
    summary="Fortuna over time range",
    operation_id="fortuna_range",
)
async def get_fortuna_range(request: FortunaRangeRequest) -> FortunaRangeResponse:
    """
    Get fortuna point positions over a time range.

    Useful for identifying when a point enters specific houses or signs.
    """
    try:
        # Calculate duration
        duration = (request.end - request.start).total_seconds() / 3600
        if duration > 168:  # More than 7 days
            raise HTTPException(
                status_code=400, detail="Range too large. Maximum 7 days allowed."
            )

        # Sample at regular intervals
        interval_hours = max(1, int(duration / 24))  # Max 24 samples
        current = request.start
        samples = []

        while current <= request.end:
            points = get_fortuna_points(
                timestamp=current,
                latitude=request.latitude,
                longitude=request.longitude,
            )

            if request.point.upper() in points:
                sample = points[request.point.upper()].copy()
                sample["timestamp"] = current.isoformat()
                samples.append(sample)

            current = current + timedelta(hours=interval_hours)

        # Find sign changes
        sign_changes = []
        for i in range(1, len(samples)):
            prev_sign = int(samples[i - 1]["longitude"] / 30) + 1
            curr_sign = int(samples[i]["longitude"] / 30) + 1
            if prev_sign != curr_sign:
                sign_changes.append(
                    {
                        "timestamp": samples[i]["timestamp"],
                        "from_sign": prev_sign,
                        "to_sign": curr_sign,
                    }
                )

        return {
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
            "point": request.point,
            "samples": samples,
            "sign_changes": sign_changes,
            "total_samples": len(samples),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/points",
    response_model=list[FortunaAvailablePoint],
    summary="List available Fortuna Points",
    operation_id="fortuna_pointsList",
)
async def list_available_points() -> list[FortunaAvailablePoint]:
    """
    List all available Fortuna Points/Arabic Parts.

    Returns names, formulas, and interpretations.
    """
    points_info = []
    for point in FortunaPoint:
        info = {
            "name": point.name,
            "display_name": point.value[0],
            "formula": point.value[1],
            "description": point.value[2],
        }

        # Add category
        if point.name in ["FORTUNE", "SPIRIT"]:
            info["category"] = "Primary"
        elif point.name in ["LOVE", "MARRIAGE", "DIVORCE", "SEXUALITY"]:
            info["category"] = "Relationships"
        elif point.name in ["CAREER", "SUCCESS", "FAME", "HONOR"]:
            info["category"] = "Career"
        elif point.name in ["DEATH", "DISEASE", "SURGERY", "CATASTROPHE"]:
            info["category"] = "Health"
        else:
            info["category"] = "Other"

        points_info.append(info)

    return points_info


@router.get(
    "/help",
    response_model=FortunaHelpResponse,
    summary="Fortuna help",
    operation_id="fortuna_help",
)
async def get_fortuna_help() -> FortunaHelpResponse:
    """
    Get help information about Fortuna Points system.

    Explains Arabic Parts and their usage in astrology.
    """
    return {
        "description": "Fortuna Points (Arabic Parts or Sahams) are sensitive points calculated from planetary positions",
        "key_concepts": {
            "calculation": "Most use formula: Ascendant + Planet1 - Planet2",
            "day_night": "Some formulas reverse for night births (Sun below horizon)",
            "movement": "Points move about 1° every 4 minutes due to Ascendant movement",
            "interpretation": "Treated like sensitive points that receive aspects",
        },
        "primary_points": {
            "Part of Fortune": "ASC + Moon - Sun (day) or ASC + Sun - Moon (night)",
            "Part of Spirit": "ASC + Sun - Moon (day) or ASC + Moon - Sun (night)",
        },
        "usage": {
            "natal": "Fixed points in birth chart showing life themes",
            "transits": "Transiting planets aspecting natal parts",
            "intraday": "Fast-moving points for micro-timing",
            "synastry": "Comparing parts between charts",
        },
        "timing_tips": [
            "Part of Fortune conjunct benefics brings opportunities",
            "Transits to Part of Spirit affect life purpose",
            "Part of Love active in relationship timing",
            "Monitor parts crossing house cusps for theme activation",
        ],
    }


# Add this for importing timedelta
from datetime import timedelta
