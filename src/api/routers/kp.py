#!/usr/bin/env python3
"""
KP Analysis API Router
Endpoints for complete KP astrological analysis
"""

from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, ConfigDict, Field
from api.models.responses import (
    KPAnalysisResponse,
    KPHousePromisesResponse,
    KPPlanetSignificationsResponse,
    KPCuspalSublordsResponse,
    KPSignificatorsResponse,
    KPConfigResponse,
)
from api.models.responses import HorarySignificatorsResponse

from refactor.facade import (
    get_house_promises,
    get_kp_analysis,
    get_planet_significations,
)
from refactor.kp_config import get_kp_config, initialize_kp_config
from refactor.kp_context import (
    KPContext,
    create_horary_context,
    create_intraday_context,
    create_mundane_context,
    create_natal_context,
)

# Initialize KP configuration on module load
initialize_kp_config()

router = APIRouter(prefix="/api/v1/kp", tags=["kp"], responses=DEFAULT_ERROR_RESPONSES)


class KPMode(str, Enum):
    """Analysis modes"""

    natal = "natal"
    horary = "horary"
    mundane = "mundane"
    intraday = "intraday"


class KPSubject(str, Enum):
    """Common subjects for analysis"""

    general = "general"
    marriage = "marriage"
    career = "career"
    health = "health"
    wealth = "wealth"
    education = "education"
    property = "property"
    speculation = "speculation"
    foreign = "foreign"
    spirituality = "spirituality"


class KPAnalysisRequest(BaseModel):
    """Request for complete KP analysis"""

    timestamp: datetime = Field(..., description="Time for analysis (UTC)")
    latitude: float = Field(..., ge=-90, le=90, description="Location latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Location longitude")

    # Context options
    mode: KPMode = Field(KPMode.natal, description="Analysis mode")
    subject: KPSubject | None = Field(None, description="Subject matter focus")

    # Analysis options
    include_timing: bool = Field(True, description="Include timing analysis")
    include_matters: list[str] | None = Field(
        None, description="Specific life matters to analyze"
    )
    analyze_houses: list[int] | None = Field(
        None, description="Specific houses to analyze (1-12)"
    )
    analyze_planets: list[int] | None = Field(
        None, description="Specific planets to analyze (1-9)"
    )

    # Advanced options
    use_retrograde_reversal: bool = Field(
        False, description="Apply retrograde sublord reversal"
    )
    strict_orbs: bool = Field(False, description="Use stricter orbs")
    custom_orbs: dict[str, float] | None = Field(None, description="Custom orb values")

    # Horary specific
    horary_number: int | None = Field(
        None, ge=1, le=249, description="KP horary number (1-249)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-08-20T14:30:00Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "mode": "natal",
                "include_timing": True,
                "include_matters": ["marriage", "career"],
            }
        }
    )


class HousePromiseRequest(BaseModel):
    """Request for house promise analysis"""

    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    house_num: int = Field(..., ge=1, le=12, description="House number (1-12)")
    mode: KPMode = KPMode.natal
    strict_orbs: bool = False


class PlanetSignificationRequest(BaseModel):
    """Request for planet signification analysis"""

    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    planet_id: int = Field(..., ge=1, le=9, description="Planet ID (1-9)")
    mode: KPMode = KPMode.natal


class CuspalAnalysisRequest(BaseModel):
    """Request for cuspal sub-lord analysis"""

    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    include_all_houses: bool = Field(True, description="Analyze all 12 houses")
    houses: list[int] | None = Field(None, description="Specific houses to analyze")


class SignificatorRequest(BaseModel):
    """Request for significator analysis"""

    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    house_num: int | None = Field(None, ge=1, le=12, description="Specific house")
    planet_id: int | None = Field(None, ge=1, le=9, description="Specific planet")
    min_strength: float = Field(25.0, description="Minimum significator strength")


@router.post(
    "/analysis",
    response_model=KPAnalysisResponse,
    summary="Run full KP analysis",
    operation_id="kp_runAnalysis",
)
async def complete_kp_analysis(request: KPAnalysisRequest) -> KPAnalysisResponse:
    """
    Perform complete KP astrological analysis.

    This endpoint provides:
    - Cuspal sub-lords for all houses
    - Complete significator hierarchy
    - Star connections and depositor chains
    - House groupings and life matter analysis
    - Timing through dasha and transits (if enabled)
    """
    try:
        # Create context based on request
        if request.mode == KPMode.horary and request.horary_number:
            context = create_horary_context(
                horary_number=request.horary_number,
                use_retrograde=request.use_retrograde_reversal,
                strict_orbs=request.strict_orbs,
            )
        elif request.mode == KPMode.intraday:
            context = create_intraday_context(time_sensitive=True)
        elif request.mode == KPMode.mundane:
            context = create_mundane_context(subject=request.subject or "world_events")
        else:  # natal
            context = create_natal_context(
                use_retrograde=request.use_retrograde_reversal,
                strict_orbs=request.strict_orbs,
                subject=request.subject,
            )

        # Apply custom orbs if provided
        if request.custom_orbs:
            context.custom_orbs = request.custom_orbs

        # Perform analysis
        analysis = get_kp_analysis(
            timestamp=request.timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
            context=context,
            include_timing=request.include_timing,
            include_matters=request.include_matters,
        )

        # Filter results if specific houses/planets requested
        result = analysis.to_dict(
            include_all=not (request.analyze_houses or request.analyze_planets),
            include_planets=True,
            include_houses=True,
            include_timing=request.include_timing,
        )

        # Filter by specific houses if requested
        if request.analyze_houses:
            result["houses"] = {
                h: data
                for h, data in result.get("houses", {}).items()
                if h in request.analyze_houses
            }

        # Filter by specific planets if requested
        if request.analyze_planets:
            result["planets"] = {
                p: data
                for p, data in result.get("planets", {}).items()
                if p in request.analyze_planets
            }

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/house-promises",
    response_model=KPHousePromisesResponse,
    summary="Analyze house promises",
    operation_id="kp_housePromises",
)
async def get_house_promise_analysis(request: HousePromiseRequest) -> KPHousePromisesResponse:
    """
    Get what a specific house promises based on its cuspal sub-lord.

    In KP, the sub-lord of a house cusp determines:
    - Whether house matters will fructify
    - Nature of results (positive/negative)
    - Timing of results through significators
    """
    try:
        context = KPContext(mode=request.mode, strict_orbs=request.strict_orbs)

        result = get_house_promises(
            timestamp=request.timestamp,
            latitude=request.latitude,
            longitude=request.longitude,
            house_num=request.house_num,
            context=context,
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/planet-significations",
    response_model=KPPlanetSignificationsResponse,
    summary="Analyze planet significations",
    operation_id="kp_planetSignifications",
)
async def get_planet_signification_analysis(
    request: PlanetSignificationRequest,
) -> KPPlanetSignificationsResponse:
    """
    Get which houses a planet signifies in the chart.

    A planet signifies houses through:
    - Occupation (being in the house)
    - Ownership (ruling the sign on cusp)
    - Star lord position
    - Aspects to houses
    """
    try:
        context = KPContext(mode=request.mode)

        result = get_planet_significations(
            timestamp=request.timestamp,
            planet_id=request.planet_id,
            latitude=request.latitude,
            longitude=request.longitude,
            context=context,
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/cuspal-sublords",
    response_model=KPCuspalSublordsResponse,
    summary="Cuspal sub-lords",
    operation_id="kp_cuspalSublords",
)
async def get_cuspal_sublords(request: CuspalAnalysisRequest) -> KPCuspalSublordsResponse:
    """
    Get cuspal sub-lords for all or specific houses.

    Returns the sign lord, star lord, and sub-lord for each house cusp.
    """
    try:
        from refactor.facade import get_positions
        from refactor.houses import compute_houses
        from refactor.kp_cuspal import get_cuspal_analysis

        # Calculate houses
        houses = compute_houses(request.timestamp, request.latitude, request.longitude)

        # Get planet positions for analysis
        planet_positions = {}
        for planet_id in range(1, 10):
            pos = get_positions(request.timestamp, planet_id, apply_kp_offset=False)
            planet_positions[planet_id] = {
                "longitude": pos.longitude,
                "house": int((pos.longitude - houses.cusps[0]) % 360 / 30) + 1,
            }

        # Get cuspal analysis
        cuspal = get_cuspal_analysis(houses, planet_positions)

        # Filter if specific houses requested
        result = cuspal.to_dict()
        if not request.include_all_houses and request.houses:
            filtered = {}
            for house in request.houses:
                if house in result["cuspal_sublords"]:
                    filtered[house] = result["cuspal_sublords"][house]
            result["cuspal_sublords"] = filtered

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/significators",
    response_model=KPSignificatorsResponse,
    summary="Significator hierarchy",
    operation_id="kp_significators",
)
async def get_significator_analysis(request: SignificatorRequest) -> KPSignificatorsResponse:
    """
    Get KP significator hierarchy for houses or planets.

    Returns the complete 5-level significator hierarchy:
    1. Planets in stars of occupants
    2. Occupants
    3. Planets in stars of owners
    4. Owners
    5. Aspecters
    """
    try:
        from refactor.facade import get_positions
        from refactor.houses import compute_houses
        from refactor.kp_significators import get_complete_significator_data

        # Calculate houses
        houses = compute_houses(request.timestamp, request.latitude, request.longitude)

        # Get planet positions
        planet_positions = {}
        for planet_id in range(1, 10):
            pos = get_positions(request.timestamp, planet_id, apply_kp_offset=False)
            planet_positions[planet_id] = {
                "longitude": pos.longitude,
                "nakshatra": pos.nakshatra,
                "nl": pos.nl,
                "sl": pos.sl,
                "house": int((pos.longitude - houses.cusps[0]) % 360 / 30) + 1,
            }

        # Get significator data
        sig_data = get_complete_significator_data(planet_positions, houses.cusps)
        result = sig_data.to_dict()

        # Filter by house if specified
        if request.house_num:
            result = {
                "house": request.house_num,
                "significators": result["house_significators"].get(
                    request.house_num, []
                ),
                "primary": result["primary_significators"].get(request.house_num, []),
            }

        # Filter by planet if specified
        elif request.planet_id:
            result = {
                "planet": request.planet_id,
                "signifies": result["planet_significations"].get(request.planet_id, []),
            }

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/config",
    response_model=KPConfigResponse,
    summary="KP configuration",
    operation_id="kp_getConfig",
)
async def get_kp_configuration() -> KPConfigResponse:
    """Get current KP configuration settings"""
    config = get_kp_config()

    return {
        "retrograde": {
            "reverses_sublord": config.retrograde_reverses_sublord,
            "strength_factor": config.retrograde_strength_factor,
            "rahu_ketu_always_retrograde": config.rahu_ketu_always_retrograde,
        },
        "orbs": {
            "natal": config.natal_orbs,
            "horary": config.horary_orbs,
            "mundane": config.mundane_orbs,
            "intraday": config.intraday_orbs,
        },
        "significators": {
            "min_strength": config.significator_min_strength,
            "primary_count": config.primary_significator_count,
            "include_aspects": config.include_aspect_significators,
        },
        "defaults": {
            "mode": config.default_mode,
            "house_system": config.default_house_system,
            "strict_kp_rules": config.strict_kp_rules,
        },
        "performance": {
            "caching_enabled": config.enable_caching,
            "cache_ttl": config.cache_ttl_seconds,
            "lazy_evaluation": config.enable_lazy_evaluation,
        },
    }


@router.get(
    "/horary/{number}",
    response_model=HorarySignificatorsResponse,
    operation_id="kp_horarySignificators",
)
async def get_horary_significators(
    number: int = Query(..., ge=1, le=249, description="KP horary number (1-249)")
) -> dict[str, Any]:
    """
    Get significators for a KP horary number.

    The 249 horary numbers map to specific sign-star-sub combinations.
    """
    # Calculate sign, star, sub from horary number
    # This is a simplified calculation - full implementation would use KP tables

    # Each sign has 9*2.25 = 20.25 numbers
    # But distribution is based on star lord periods

    # Simplified mapping (would use exact KP horary table in production)
    sign = ((number - 1) // 21) + 1  # Rough approximation
    remainder = (number - 1) % 21
    star = (remainder // 3) + 1
    sub = (remainder % 3) + 1

    # Map to actual planet lords
    sign_lords = {
        1: "Mars",
        2: "Venus",
        3: "Mercury",
        4: "Moon",
        5: "Sun",
        6: "Mercury",
        7: "Venus",
        8: "Mars",
        9: "Jupiter",
        10: "Saturn",
        11: "Saturn",
        12: "Jupiter",
    }

    star_sequence = [
        "Ketu",
        "Venus",
        "Sun",
        "Moon",
        "Mars",
        "Rahu",
        "Jupiter",
        "Saturn",
        "Mercury",
    ]

    return {
        "horary_number": number,
        "sign": sign,
        "sign_lord": sign_lords.get(sign, "Unknown"),
        "star": star,
        "star_lord": star_sequence[(star - 1) % 9],
        "sub": sub,
        "interpretation": "Use these significators for horary analysis",
    }


@router.get(
    "/life-matters",
    response_model=list[str],
    summary="List available life matters",
    operation_id="kp_lifeMatters",
)
async def get_available_life_matters() -> list[str]:
    """Get list of life matters available for analysis"""
    from refactor.kp_house_groups import LifeMatter

    return [matter.value for matter in LifeMatter]
