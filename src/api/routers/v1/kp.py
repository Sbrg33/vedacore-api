"""
API v1 KP (Krishnamurti Paddhati) Router

KP-specific calculations with enforced KP defaults.
All endpoints use KP ayanamsha and traditional KP methods.
"""

from typing import Dict, List, Optional, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .models import (
    BaseKPRequest,
    BaseResponse, 
    ErrorResponse,
    PATH_TEMPLATES
)

router = APIRouter(prefix="/api/v1/kp", tags=["KP"])


# Request/Response Models
class ChartRequest(BaseKPRequest):
    """Request for KP chart calculation."""
    include_significators: bool = Field(default=True, description="Include KP significators")
    include_cuspal_interlinks: bool = Field(default=False, description="Include CLI analysis")


class ChainRequest(BaseKPRequest):
    """Request for KP chain calculation (NL → SL → SSL)."""
    target: Dict[str, Any] = Field(..., description="Target for chain calculation")
    
    class Target(BaseModel):
        type: Literal["planet", "cusp"] = Field(..., description="Target type")
        id: str = Field(..., description="Planet name or cusp number")


class RulingPlanetsRequest(BaseKPRequest):
    """Request for KP Ruling Planets calculation."""
    include_day_lord: bool = Field(default=True, description="Include day lord analysis")


class HoraryRequest(BaseModel):
    """Request for KP Horary calculation."""
    mode: Literal["number", "datetime"] = Field(..., description="Horary mode")
    value: Any = Field(..., description="Horary number (1-249) or datetime")
    question: Optional[str] = Field(None, description="Horary question for context")


class TransitEventsRequest(BaseKPRequest):
    """Request for KP transit events."""
    window_hours: int = Field(default=24, ge=1, le=168, description="Analysis window")
    orb_degrees: float = Field(default=1.0, ge=0.1, le=5.0, description="Transit orb")


# Response Models
class KPChartResponse(BaseModel):
    """KP chart calculation response."""
    cusps: List[Dict[str, Any]] = Field(..., description="KP house cusps with sub-lords")
    planets: List[Dict[str, Any]] = Field(..., description="Planets with KP details")
    significators: Optional[Dict[str, List[str]]] = Field(None, description="House significators")


class ChainResponse(BaseModel):
    """KP chain calculation response."""
    target: Dict[str, Any] = Field(..., description="Target information")
    chain: Dict[str, Any] = Field(..., description="NL → SL → SSL chain")
    degrees: Dict[str, float] = Field(..., description="Degree positions")
    nakshatra_pada: Dict[str, Any] = Field(..., description="Nakshatra and Pada info")


# Endpoints
@router.post("/chart", response_model=BaseResponse, summary="Generate KP Chart")
async def calculate_kp_chart(request: ChartRequest) -> BaseResponse:
    """
    Calculate complete KP chart with cusps, sub-lords, and significators.
    
    Returns KP house cusps with sub-lords, planet positions with 
    Nakshatra/Pada, and house significators if requested.
    """
    try:
        # Import KP calculation modules
        from interfaces.kp_houses_adapter import get_kp_houses_data
        from refactor.kp_significators import get_house_significators
        
        # Get KP houses data
        kp_data = get_kp_houses_data(
            timestamp=request.datetime,
            latitude=request.lat,
            longitude=request.lon
        )
        
        # Get significators if requested
        significators = None
        if request.include_significators:
            significators = get_house_significators(
                timestamp=request.datetime,
                latitude=request.lat,
                longitude=request.lon
            )
        
        chart_data = KPChartResponse(
            cusps=kp_data["cusps"],
            planets=kp_data["planets"],
            significators=significators
        )
        
        return BaseResponse.create(
            data=chart_data,
            path_template=PATH_TEMPLATES["kp_chart"],
            compute_units=1.5
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"KP chart calculation failed: {str(e)}"
            ).dict()
        )


@router.post("/chain", response_model=BaseResponse, summary="Calculate KP Chain")
async def calculate_kp_chain(request: ChainRequest) -> BaseResponse:
    """
    Calculate KP chain (Nakshatra Lord → Sub Lord → Sub-Sub Lord) for target.
    
    Accepts planet or cusp as target and returns complete chain analysis
    with degrees, Nakshatra/Pada information, and house context.
    """
    try:
        # Validate target format
        target = request.target
        if target.get("type") not in ["planet", "cusp"]:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse.create(
                    code="VALIDATION_ERROR",
                    message="Target type must be 'planet' or 'cusp'",
                    details={"provided": target.get("type")}
                ).dict()
            )
        
        # Import KP chain calculation
        from refactor.kp_chain import get_kp_chain_for_target
        
        chain_data = get_kp_chain_for_target(
            timestamp=request.datetime,
            latitude=request.lat,
            longitude=request.lon,
            target_type=target["type"],
            target_id=target["id"]
        )
        
        response_data = ChainResponse(
            target=target,
            chain=chain_data["chain"],
            degrees=chain_data["degrees"],
            nakshatra_pada=chain_data["nakshatra_pada"]
        )
        
        return BaseResponse.create(
            data=response_data,
            path_template=PATH_TEMPLATES["kp_chain"],
            compute_units=1.0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"KP chain calculation failed: {str(e)}"
            ).dict()
        )


@router.post("/ruling-planets", response_model=BaseResponse, summary="Calculate KP Ruling Planets")
async def calculate_ruling_planets(request: RulingPlanetsRequest) -> BaseResponse:
    """
    Calculate KP Ruling Planets for given time and place.
    
    Returns time-based ruling planets following traditional KP methods
    with day lord analysis if requested.
    """
    try:
        # Import KP ruling planets
        from interfaces.kp_ruling_planets_adapter import get_ruling_planets_data
        
        rp_data = get_ruling_planets_data(
            timestamp=request.datetime,
            latitude=request.lat,
            longitude=request.lon,
            include_day_lord=request.include_day_lord
        )
        
        return BaseResponse.create(
            data=rp_data,
            path_template=PATH_TEMPLATES["kp_ruling_planets"],
            compute_units=1.0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"Ruling planets calculation failed: {str(e)}"
            ).dict()
        )


@router.post("/horary", response_model=BaseResponse, summary="Calculate KP Horary")
async def calculate_kp_horary(request: HoraryRequest) -> BaseResponse:
    """
    Calculate KP Horary chart using number (1-249) or datetime mode.
    
    Traditional KP horary analysis for Prashna (questions).
    Supports both number-based and time-based horary methods.
    """
    try:
        # Import KP horary calculation
        from interfaces.kp_horary_adapter import get_horary_calculation
        
        horary_data = get_horary_calculation(
            mode=request.mode,
            value=request.value,
            question=request.question
        )
        
        return BaseResponse.create(
            data=horary_data,
            path_template=PATH_TEMPLATES["kp_horary"],
            compute_units=1.0
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"KP horary calculation failed: {str(e)}"
            ).dict()
        )


@router.post("/transit-events", response_model=BaseResponse, summary="Calculate KP Transit Events")
async def calculate_transit_events(request: TransitEventsRequest) -> BaseResponse:
    """
    Calculate KP transit events within specified window.
    
    Returns significant transits affecting KP significators
    with applying/separating aspects and timing analysis.
    """
    try:
        # Import KP transit analysis
        from refactor.transit_event_detector import analyze_kp_transit_events
        
        transit_data = analyze_kp_transit_events(
            base_time=request.datetime,
            latitude=request.lat,
            longitude=request.lon,
            window_hours=request.window_hours,
            orb_degrees=request.orb_degrees
        )
        
        return BaseResponse.create(
            data=transit_data,
            path_template=PATH_TEMPLATES["kp_transit_events"],
            compute_units=2.5
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"KP transit events calculation failed: {str(e)}"
            ).dict()
        )