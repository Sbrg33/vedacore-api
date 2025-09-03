"""
FastAPI router for KP Ruling Planets with enhanced validation.

Enhanced with PM's requirements:
- 422 status codes for validation errors
- Strict Pydantic V2 typing with Planet Literal
- Enhanced observability with correlation IDs

Generated: 2025-08-25 (Production-Ready)
"""

from __future__ import annotations

import logging
import uuid

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, ConfigDict, Field, field_validator

from constants.kp.types import Planet

# Try to import the registry
try:
    from interfaces.advisory_adapter_protocol import advisory_registry
except Exception:
    advisory_registry = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/kp/rp", tags=["kp-ruling-planets"], responses=DEFAULT_ERROR_RESPONSES)


class PlanetChain(BaseModel):
    """Planet chain with strict validation"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"nl": "MA", "sl": "RA", "ssl": "MO"}}
    )

    nl: Planet = Field(..., description="Nakshatra Lord (Star Lord)")
    sl: Planet = Field(..., description="Sub Lord")
    ssl: Planet = Field(..., description="Sub-Sub Lord")


class RPConfig(BaseModel):
    """Configuration for RP calculation weights"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "weight_day": 1.0,
                "weight_asc": 1.0,
                "weight_moon": 1.2,
                "fortify_exalted": 0.2,
                "fortify_own": 0.1,
            }
        }
    )

    weight_day: float = Field(1.0, ge=0.0, le=5.0, description="Day lord weight")
    weight_asc: float = Field(1.0, ge=0.0, le=5.0, description="Ascendant chain weight")
    weight_moon: float = Field(1.2, ge=0.0, le=5.0, description="Moon chain weight")
    fortify_exalted: float = Field(0.2, ge=0.0, le=1.0, description="Exaltation bonus")
    fortify_own: float = Field(0.1, ge=0.0, le=1.0, description="Own sign bonus")


class RulingPlanetsRequest(BaseModel):
    """KP Ruling Planets calculation request"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "weekday_idx": 0,
                "asc_chain": {"nl": "MA", "sl": "RA", "ssl": "MO"},
                "moon_chain": {"nl": "MO", "sl": "MO", "ssl": "SA"},
                "is_exalted": {"JU": True},
                "is_own": {"MA": True},
            }
        }
    )

    weekday_idx: int = Field(
        ..., description="Weekday index: 0=Monday, 1=Tuesday, ..., 6=Sunday"
    )
    asc_chain: PlanetChain = Field(..., description="Ascendant KP chain")
    moon_chain: PlanetChain = Field(..., description="Moon KP chain")
    is_exalted: dict[Planet, bool] = Field(
        default_factory=dict, description="Exaltation flags per planet"
    )
    is_own: dict[Planet, bool] = Field(
        default_factory=dict, description="Own sign flags per planet"
    )
    config: RPConfig | None = Field(None, description="Custom configuration weights")

    @field_validator("weekday_idx")
    @classmethod
    def validate_weekday(cls, v: int) -> int:
        if not 0 <= v <= 6:
            raise ValueError("weekday_idx must be 0-6 (Monday=0, Sunday=6)")
        return v

    @field_validator("is_exalted", "is_own")
    @classmethod
    def validate_planet_flags(cls, v: dict[Planet, bool]) -> dict[Planet, bool]:
        valid_planets = {"SU", "MO", "MA", "ME", "JU", "VE", "SA", "RA", "KE"}
        for planet, flag in v.items():
            if planet not in valid_planets:
                raise ValueError(f"Invalid planet '{planet}' in flags")
            if not isinstance(flag, bool):
                raise ValueError(f"Flag for {planet} must be boolean")
        return v


class RulingPlanetsResponse(BaseModel):
    """KP Ruling Planets calculation response"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "adapter_id": "kp_ruling_planets",
                "adapter_version": "1.0.0",
                "day_lord": "MO",
                "rp_ranked": [["MO", 3.4], ["MA", 2.0], ["RA", 1.0]],
                "rp_primary": ["MO", "MA", "RA", "SA", "JU"],
                "total_score": 6.4,
                "correlation_id": "abc12345",
            }
        }
    )

    adapter_id: str
    adapter_version: str
    day_lord: Planet
    rp_ranked: list[tuple[Planet, float]]
    rp_primary: list[Planet]
    rp_unique: list[Planet]
    weekday_idx: int
    total_score: float
    correlation_id: str


def get_correlation_id() -> str:
    """Generate correlation ID for request tracking"""
    return str(uuid.uuid4())[:8]


@router.post(
    "/compute",
    response_model=RulingPlanetsResponse,
    summary="Compute Ruling Planets",
    operation_id="kpRP_compute",
)
async def compute_ruling_planets(
    request: RulingPlanetsRequest, correlation_id: str = Depends(get_correlation_id)
):
    """
    Compute KP Ruling Planets for a given moment.

    Calculates the planetary rulers at any moment based on:
    - Day lord (weekday ruler)
    - Ascendant sign lord, nakshatra lord, sub lord
    - Moon sign lord, nakshatra lord, sub lord
    - Fortification bonuses for exalted/own sign planets

    Returns ranked list with stable ordering and total strength score.
    """
    if advisory_registry is None:
        raise HTTPException(status_code=500, detail="Adapter registry not available")

    adapter = advisory_registry.get("kp_ruling_planets")
    if adapter is None:
        raise HTTPException(
            status_code=500, detail="kp_ruling_planets adapter not registered"
        )

    # Add correlation ID to context
    ctx = request.model_dump()
    ctx["correlation_id"] = correlation_id

    try:
        result = adapter.compute(ctx)

        # Check for adapter errors
        if "error" in result:
            if result.get("error_type") == "validation_error":
                raise HTTPException(status_code=422, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in RP calculation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/weekday-info/{weekday_idx}",
    summary="Weekday info",
    operation_id="kpRP_weekdayInfo",
)
async def get_weekday_info(weekday_idx: int):
    """
    Get information about a specific weekday.

    Args:
        weekday_idx: 0=Monday, 1=Tuesday, ..., 6=Sunday
    """
    if not 0 <= weekday_idx <= 6:
        raise HTTPException(status_code=422, detail="weekday_idx must be 0-6")

    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    day_lords = ["MO", "MA", "ME", "JU", "VE", "SA", "SU"]

    return {
        "weekday_idx": weekday_idx,
        "weekday_name": weekday_names[weekday_idx],
        "day_lord": day_lords[weekday_idx],
        "day_lord_name": {
            "MO": "Moon",
            "MA": "Mars",
            "ME": "Mercury",
            "JU": "Jupiter",
            "VE": "Venus",
            "SA": "Saturn",
            "SU": "Sun",
        }.get(day_lords[weekday_idx]),
    }


@router.get(
    "/schema",
    summary="RP schema",
    operation_id="kpRP_schema",
)
async def get_schema():
    """Get API schema for Ruling Planets endpoints"""
    if advisory_registry is None:
        raise HTTPException(status_code=500, detail="Adapter registry not available")

    adapter = advisory_registry.get("kp_ruling_planets")
    if adapter is None:
        raise HTTPException(
            status_code=500, detail="kp_ruling_planets adapter not registered"
        )

    return adapter.schema()


@router.get(
    "/explain",
    summary="RP explain",
    operation_id="kpRP_explain",
)
async def get_explanation():
    """Get explanation of Ruling Planets calculation logic"""
    if advisory_registry is None:
        raise HTTPException(status_code=500, detail="Adapter registry not available")

    adapter = advisory_registry.get("kp_ruling_planets")
    if adapter is None:
        raise HTTPException(
            status_code=500, detail="kp_ruling_planets adapter not registered"
        )

    return adapter.explain({})


@router.get(
    "/health",
    summary="RP health",
    operation_id="kpRP_health",
)
async def health_check():
    """Health check for Ruling Planets service"""
    status = {
        "service": "kp_ruling_planets",
        "status": "healthy",
        "registry_available": advisory_registry is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if advisory_registry:
        adapter = advisory_registry.get("kp_ruling_planets")
        status["adapter_registered"] = adapter is not None
        if adapter:
            status["adapter_version"] = adapter.version

    return status
