#!/usr/bin/env python3
"""
Tara Bala API Router
Endpoints for nakshatra quality assessment and timing
"""

from datetime import UTC, date, datetime, time
from typing import Any

from fastapi import APIRouter, HTTPException
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, ConfigDict, Field

from refactor.facade import get_muhurta_tara, get_positions, get_tara_bala
from refactor.tara_bala import TaraType

router = APIRouter(prefix="/api/v1/tara", tags=["tara"], responses=DEFAULT_ERROR_RESPONSES)


class TaraAnalysisRequest(BaseModel):
    """Request for personal tara analysis"""

    birth_moon_longitude: float = Field(
        ..., ge=0, lt=360, description="Birth Moon longitude in degrees"
    )
    analysis_timestamp: datetime = Field(..., description="Time to analyze (UTC)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "birth_moon_longitude": 45.5,
                "analysis_timestamp": "2024-08-20T14:30:00Z",
            }
        }
    )


class MuhurtaTaraRequest(BaseModel):
    """Request for muhurta/electional tara analysis"""

    event_timestamp: datetime = Field(..., description="Proposed event time (UTC)")
    birth_moon_longitudes: list[float] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Birth Moon longitudes of participants (degrees)",
    )
    weights: list[float] | None = Field(
        None, description="Importance weights for each person (sum to 1.0)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_timestamp": "2024-08-25T10:00:00Z",
                "birth_moon_longitudes": [45.5, 120.3, 210.7],
                "weights": [0.5, 0.25, 0.25],
            }
        }
    )


class TaraDayRequest(BaseModel):
    """Request for tara analysis over a day"""

    birth_moon_longitude: float = Field(..., ge=0, lt=360)
    analysis_date: date = Field(..., description="Date to analyze (UTC)")
    hourly: bool = Field(True, description="Return hourly breakdown")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "birth_moon_longitude": 45.5,
                "analysis_date": "2024-08-20",
                "hourly": True,
            }
        }
    )


class UniversalTaraRequest(BaseModel):
    """Request for universal tara (no birth data)"""

    timestamp: datetime = Field(..., description="Time to analyze (UTC)")

    model_config = ConfigDict(
        json_schema_extra={"example": {"timestamp": "2024-08-20T14:30:00Z"}}
    )


from api.models.responses import (
    TaraPersonalResponse,
    MuhurtaTaraResponse,
    TaraDayScanResponse,
    UniversalTaraResponse,
    TaraTypeInfo,
    TaraHelpResponse,
)


@router.post(
    "/personal",
    response_model=TaraPersonalResponse,
    summary="Personal Tara analysis",
    operation_id="tara_personal",
)
async def get_personal_tara(request: TaraAnalysisRequest) -> TaraPersonalResponse:
    """
    Calculate personal Tara Bala based on birth Moon.

    Returns the 9-fold Tara position and quality assessment
    for timing decisions based on nakshatra relationships.
    """
    try:
        result = get_tara_bala(
            birth_moon_longitude=request.birth_moon_longitude,
            current_timestamp=request.analysis_timestamp,
        )

        return {
            "timestamp": request.analysis_timestamp.isoformat(),
            "birth_moon_longitude": request.birth_moon_longitude,
            "tara_analysis": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/muhurta",
    response_model=MuhurtaTaraResponse,
    summary="Muhurta Tara analysis",
    operation_id="tara_muhurta",
)
async def get_muhurta_analysis(request: MuhurtaTaraRequest) -> MuhurtaTaraResponse:
    """
    Evaluate muhurta quality for multiple participants.

    Useful for selecting event timing that works for
    multiple people based on their birth Moons.
    """
    try:
        result = get_muhurta_tara(
            event_timestamp=request.event_timestamp,
            birth_moon_longitudes=request.birth_moon_longitudes,
            weights=request.weights,
        )

        return {
            "event_timestamp": request.event_timestamp.isoformat(),
            "participants": len(request.birth_moon_longitudes),
            "muhurta_analysis": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/day-scan",
    response_model=TaraDayScanResponse,
    summary="Tara day scan",
    operation_id="tara_dayScan",
)
async def scan_tara_for_day(request: TaraDayRequest) -> TaraDayScanResponse:
    """
    Scan Tara quality throughout a day.

    Returns hourly or summary assessment of Tara positions
    to identify favorable and unfavorable windows.
    """
    try:
        # Build timestamps for the day
        timestamps = []
        qualities = []

        if request.hourly:
            # Hourly scan
            for hour in range(24):
                ts = datetime.combine(
                    request.analysis_date, time(hour, 0, 0), tzinfo=UTC
                )
                timestamps.append(ts)

                tara = get_tara_bala(
                    birth_moon_longitude=request.birth_moon_longitude,
                    current_timestamp=ts,
                )
                qualities.append(
                    {
                        "hour": hour,
                        "timestamp": ts.isoformat(),
                        "tara_type": tara["tara_type"],
                        "quality_score": tara["quality_score"],
                        "favorable": tara["quality_score"] >= 50,
                    }
                )
        else:
            # Key points only (sunrise, noon, sunset)
            key_hours = [6, 12, 18]  # Simplified, would calculate actual times
            for hour in key_hours:
                ts = datetime.combine(
                    request.analysis_date, time(hour, 0, 0), tzinfo=UTC
                )

                tara = get_tara_bala(
                    birth_moon_longitude=request.birth_moon_longitude,
                    current_timestamp=ts,
                )
                qualities.append(
                    {
                        "time": f"{hour:02d}:00",
                        "tara_type": tara["tara_type"],
                        "quality_score": tara["quality_score"],
                    }
                )

        # Find best and worst times
        best_time = max(qualities, key=lambda x: x["quality_score"])
        worst_time = min(qualities, key=lambda x: x["quality_score"])

        # Count favorable hours
        favorable_hours = sum(
            1 for q in qualities if q.get("favorable", q["quality_score"] >= 50)
        )

        return {
            "date": request.analysis_date.isoformat(),
            "birth_moon_longitude": request.birth_moon_longitude,
            "summary": {
                "favorable_hours": favorable_hours,
                "unfavorable_hours": 24 - favorable_hours if request.hourly else None,
                "best_time": best_time,
                "worst_time": worst_time,
            },
            "hourly_data": qualities if request.hourly else None,
            "key_points": qualities if not request.hourly else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/universal",
    response_model=UniversalTaraResponse,
    summary="Universal Tara",
    operation_id="tara_universal",
)
async def get_universal_tara(request: UniversalTaraRequest) -> UniversalTaraResponse:
    """
    Calculate universal Tara based on current Moon nakshatra.

    Provides general timing quality without personal birth data.
    Uses day's starting nakshatra as reference.
    """
    try:
        # Get current Moon position
        moon_pos = get_positions(request.timestamp, planet_id=2, apply_kp_offset=False)
        current_nakshatra = moon_pos.nakshatra

        # For universal, we use sunrise Moon as reference (simplified)
        # In production, would calculate actual sunrise
        sunrise = datetime.combine(request.timestamp.date(), time(6, 0, 0), tzinfo=UTC)
        sunrise_moon = get_positions(sunrise, planet_id=2, apply_kp_offset=False)

        # Calculate tara from sunrise nakshatra
        tara_number = ((current_nakshatra - sunrise_moon.nakshatra - 1) % 27) // 3 + 1

        # Map to TaraType
        tara_types = list(TaraType)
        tara_type = tara_types[(tara_number - 1) % 9]

        return {
            "timestamp": request.timestamp.isoformat(),
            "current_nakshatra": current_nakshatra,
            "reference_nakshatra": sunrise_moon.nakshatra,
            "universal_tara": {
                "tara_number": tara_number,
                "tara_name": tara_type.value[0],
                "description": tara_type.value[2],
                "general_quality": (
                    "favorable"
                    if tara_number in [2, 4, 6, 8]
                    else "unfavorable" if tara_number in [3, 5, 7] else "mixed"
                ),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/types",
    response_model=list[TaraTypeInfo],
    summary="List Tara types",
    operation_id="tara_types",
)
async def get_tara_types() -> list[TaraTypeInfo]:
    """
    Get information about all 9 Tara types.

    Returns descriptions and quality indicators for each Tara.
    """
    return [
        {
            "number": tara.value[1],
            "name": tara.value[0],
            "description": tara.value[2],
            "quality": (
                "favorable"
                if tara.value[1] in [2, 4, 6, 8]
                else "unfavorable" if tara.value[1] in [3, 5, 7] else "mixed"
            ),
        }
        for tara in TaraType
    ]


@router.get(
    "/help",
    response_model=TaraHelpResponse,
    summary="Tara help",
    operation_id="tara_help",
)
async def get_tara_help() -> TaraHelpResponse:
    """
    Get help information about Tara Bala system.

    Explains the 9-fold cycle and how to use it for timing.
    """
    return {
        "description": "Tara Bala is a nakshatra-based timing system that divides the 27 nakshatras into 9 groups of 3 each",
        "usage": {
            "personal": "Compare current Moon nakshatra to birth Moon nakshatra",
            "muhurta": "Evaluate event timing for multiple participants",
            "universal": "General daily quality without birth data",
        },
        "tara_cycle": [
            {"position": 1, "name": "Janma", "quality": "Mixed - birth star, neutral"},
            {"position": 2, "name": "Sampat", "quality": "Very favorable - wealth"},
            {"position": 3, "name": "Vipat", "quality": "Unfavorable - danger"},
            {"position": 4, "name": "Kshema", "quality": "Favorable - prosperity"},
            {
                "position": 5,
                "name": "Pratyari",
                "quality": "Very unfavorable - obstacles",
            },
            {"position": 6, "name": "Sadhaka", "quality": "Favorable - achievement"},
            {
                "position": 7,
                "name": "Naidhana",
                "quality": "Very unfavorable - destruction",
            },
            {"position": 8, "name": "Mitra", "quality": "Very favorable - friendship"},
            {
                "position": 9,
                "name": "Ati-Mitra",
                "quality": "Favorable - great friendship",
            },
        ],
        "best_taras": [2, 4, 6, 8],
        "worst_taras": [3, 5, 7],
        "neutral_taras": [1, 9],
    }
