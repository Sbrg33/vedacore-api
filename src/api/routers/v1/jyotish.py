"""
API v1 Jyotish (General Vedic) Router

Core Vedic astrology endpoints following traditional calculations.
All endpoints enforce sidereal zodiac and traditional methods.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from .models import (
    BaseVedicRequest, 
    BaseResponse, 
    ErrorResponse, 
    PlanetPosition, 
    HousePosition,
    PATH_TEMPLATES
)

router = APIRouter(prefix="/api/v1/jyotish", tags=["Jyotish"])


# Request/Response Models
class ChartRequest(BaseVedicRequest):
    """Request for basic Vedic chart calculation."""
    options: Dict[str, Any] = Field(default_factory=dict, description="Additional calculation options")


class ChartResponse(BaseModel):
    """Response for Vedic chart calculation."""
    planets: List[PlanetPosition] = Field(..., description="Planet positions")
    houses: List[HousePosition] = Field(..., description="House cusps and lords")
    ascendant: float = Field(..., description="Ascendant degree")
    midheaven: float = Field(..., description="MC degree")


class TransitsWindowRequest(BaseVedicRequest):
    """Request for transit window analysis."""
    window_hours: int = Field(default=24, ge=1, le=168, description="Analysis window in hours")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Transit filters")


class TransitsWindowResponse(BaseModel):
    """Response for transit window analysis."""
    window_start: datetime = Field(..., description="Window start time")
    window_end: datetime = Field(..., description="Window end time")
    transits: List[Dict[str, Any]] = Field(..., description="Transit events in window")
    scoring: Dict[str, float] = Field(..., description="Overall window scoring")


class VargaRequest(BaseVedicRequest):
    """Request for Varga (divisional chart) calculation."""
    varga_type: str = Field(..., description="Varga division (d9, d10, d60, etc.)")


# Endpoints
@router.post("/chart", response_model=BaseResponse, summary="Generate Vedic Chart")
async def calculate_chart(request: ChartRequest) -> BaseResponse:
    """
    Calculate basic Vedic chart with planets, houses, and essential points.
    
    Returns planet positions, house cusps with lords, ascendant and MC.
    All calculations use sidereal zodiac with specified ayanamsha.
    """
    try:
        # Import here to avoid circular imports
        from interfaces.kp_houses_adapter import get_houses_calculation
        from refactor.houses import get_planet_positions
        
        # Get planet positions
        planets_data = get_planet_positions(
            timestamp=request.datetime,
            latitude=request.lat,
            longitude=request.lon
        )
        
        # Get house cusps and lords  
        houses_data = get_houses_calculation(
            timestamp=request.datetime,
            latitude=request.lat,
            longitude=request.lon,
            house_system=request.house_system
        )
        
        # Format response
        planets = [
            PlanetPosition(
                planet=p["name"],
                longitude=p["longitude"],
                latitude=p.get("latitude", 0),
                speed=p["speed"],
                retrograde=p["speed"] < 0
            )
            for p in planets_data
        ]
        
        houses = [
            HousePosition(
                house=h["house"],
                cusp=h["cusp"],
                lord=h["lord"]
            )
            for h in houses_data
        ]
        
        chart_data = ChartResponse(
            planets=planets,
            houses=houses,
            ascendant=houses_data[0]["cusp"],  # 1st house cusp
            midheaven=houses_data[9]["cusp"]   # 10th house cusp
        )
        
        return BaseResponse.create(
            data=chart_data,
            path_template=PATH_TEMPLATES["jyotish_chart"],
            compute_units=1.0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"Chart calculation failed: {str(e)}"
            ).dict()
        )


@router.post("/transits/window", response_model=BaseResponse, summary="Analyze Transit Window") 
async def analyze_transit_window(request: TransitsWindowRequest) -> BaseResponse:
    """
    Analyze transits within specified time window.
    
    Returns significant transit events, aspects, and overall window scoring
    for timing decisions.
    """
    try:
        # This would integrate with existing transit analysis
        # For now, return basic structure
        from datetime import timedelta
        
        window_start = request.datetime
        window_end = window_start + timedelta(hours=request.window_hours)
        
        # Placeholder - would call actual transit analysis
        transit_data = TransitsWindowResponse(
            window_start=window_start,
            window_end=window_end,
            transits=[],
            scoring={"overall": 0.0}
        )
        
        return BaseResponse.create(
            data=transit_data,
            path_template=PATH_TEMPLATES["jyotish_transits_window"],
            compute_units=2.0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL", 
                message=f"Transit analysis failed: {str(e)}"
            ).dict()
        )


@router.post("/varga/{varga_type}", response_model=BaseResponse, summary="Calculate Varga Chart")
async def calculate_varga(varga_type: str, request: VargaRequest) -> BaseResponse:
    """
    Calculate divisional chart (Varga) for specified division.
    
    Supports standard Varga divisions: d9 (navamsa), d10 (dasamsa), 
    d60 (shashtyamsa), etc.
    """
    try:
        # Validate varga type
        valid_vargas = ["d9", "d10", "d12", "d16", "d20", "d24", "d27", "d30", "d40", "d45", "d60"]
        if varga_type not in valid_vargas:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse.create(
                    code="VALIDATION_ERROR",
                    message=f"Invalid varga type: {varga_type}",
                    details={"valid_types": valid_vargas}
                ).dict()
            )
        
        # Import varga calculation
        from interfaces.kp_adapter import get_varga_calculation
        
        varga_data = get_varga_calculation(
            timestamp=request.datetime,
            latitude=request.lat,
            longitude=request.lon,
            varga_type=varga_type
        )
        
        return BaseResponse.create(
            data=varga_data,
            path_template=PATH_TEMPLATES["jyotish_varga"],
            varga_type=varga_type,
            compute_units=1.5
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"Varga calculation failed: {str(e)}"
            ).dict()
        )


@router.post("/panchanga", response_model=BaseResponse, summary="Calculate Panchanga")
async def calculate_panchanga(request: BaseVedicRequest) -> BaseResponse:
    """
    Calculate Panchanga (five limbs) for given time and place.
    
    Returns Tithi, Vara, Nakshatra, Yoga, Karana and timing windows.
    """
    try:
        # Import panchanga calculation
        from modules.panchanga.panchanga_full import get_panchanga_data
        
        panchanga_data = get_panchanga_data(
            timestamp=request.datetime,
            latitude=request.lat,
            longitude=request.lon
        )
        
        return BaseResponse.create(
            data=panchanga_data,
            path_template=PATH_TEMPLATES["jyotish_panchanga"],
            compute_units=1.0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"Panchanga calculation failed: {str(e)}"
            ).dict()
        )