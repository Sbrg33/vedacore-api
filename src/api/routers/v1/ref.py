"""
API v1 Reference Data Router

Reference endpoints for Vedic/KP constants, validation data,
and system information.
"""

from typing import List, Dict, Any

from fastapi import APIRouter
from pydantic import BaseModel

from .models import BaseResponse, PATH_TEMPLATES

from app.openapi.common import DEFAULT_ERROR_RESPONSES

router = APIRouter(prefix="/api/v1/ref", tags=["reference"], responses=DEFAULT_ERROR_RESPONSES)


class AyanamshaInfo(BaseModel):
    """Ayanamsha system information."""
    name: str
    description: str
    default: bool
    supported_calculations: List[str]


class VargaTypeInfo(BaseModel):
    """Varga division information."""
    name: str
    division: int
    description: str
    usage: str


class AspectModeInfo(BaseModel):
    """Aspect calculation mode information."""
    name: str
    description: str
    orbs: Dict[str, float]
    supported_systems: List[str]


@router.get(
    "/ayanamshas",
    response_model=BaseResponse,
    summary="List Available Ayanamshas",
    operation_id="v1_ref_ayanamshas",
)
async def get_ayanamshas() -> BaseResponse:
    """
    Get list of supported Ayanamsha systems.
    
    Returns available ayanamsha calculations with descriptions
    and supported calculation types.
    """
    ayanamshas = [
        AyanamshaInfo(
            name="kp",
            description="KP Ayanamsha (Krishnamurti Paddhati)",
            default=True,
            supported_calculations=["kp", "horary", "ruling_planets"]
        ),
        AyanamshaInfo(
            name="lahiri",
            description="Lahiri Ayanamsha (Chitrapaksha)",
            default=False,
            supported_calculations=["jyotish", "panchanga"]
        )
    ]
    
    return BaseResponse.create(
        data=ayanamshas,
        path_template=PATH_TEMPLATES["ref_ayanamshas"],
        count=len(ayanamshas)
    )


@router.get(
    "/varga-types",
    response_model=BaseResponse,
    summary="List Available Varga Types",
    operation_id="v1_ref_vargaTypes",
)
async def get_varga_types() -> BaseResponse:
    """
    Get list of supported Varga (divisional chart) types.
    
    Returns standard Varga divisions with descriptions and usage guidance.
    """
    varga_types = [
        VargaTypeInfo(name="d9", division=9, description="Navamsa - Marriage & Dharma", usage="relationships"),
        VargaTypeInfo(name="d10", division=10, description="Dasamsa - Career & Profession", usage="career"),
        VargaTypeInfo(name="d12", division=12, description="Dwadasamsa - Parents & Ancestry", usage="family"),
        VargaTypeInfo(name="d16", division=16, description="Shodasamsa - Vehicles & Comforts", usage="material"),
        VargaTypeInfo(name="d20", division=20, description="Vimsamsa - Spiritual Practice", usage="spirituality"),
        VargaTypeInfo(name="d24", division=24, description="Chaturvimsamsa - Education", usage="learning"),
        VargaTypeInfo(name="d27", division=27, description="Nakshatramsa - Strengths & Weaknesses", usage="character"),
        VargaTypeInfo(name="d30", division=30, description="Trimsamsa - Misfortunes & Evils", usage="challenges"),
        VargaTypeInfo(name="d40", division=40, description="Khavedamsa - Maternal Heritage", usage="maternal"),
        VargaTypeInfo(name="d45", division=45, description="Akshavedamsa - Paternal Heritage", usage="paternal"),
        VargaTypeInfo(name="d60", division=60, description="Shashtyamsa - All General Matters", usage="general")
    ]
    
    return BaseResponse.create(
        data=varga_types,
        path_template=PATH_TEMPLATES["ref_varga_types"],
        count=len(varga_types)
    )


@router.get(
    "/aspect-modes",
    response_model=BaseResponse,
    summary="List Available Aspect Modes",
    operation_id="v1_ref_aspectModes",
)
async def get_aspect_modes() -> BaseResponse:
    """
    Get list of supported aspect calculation modes.
    
    Returns available aspect systems with orbs and supported calculations.
    """
    aspect_modes = [
        AspectModeInfo(
            name="parashara",
            description="Traditional Parashara aspects",
            orbs={"conjunction": 10.0, "opposition": 10.0, "trine": 8.0, "square": 8.0},
            supported_systems=["jyotish", "kp"]
        ),
        AspectModeInfo(
            name="jaimini",
            description="Jaimini rasi aspects",
            orbs={"rasi": 0.0, "graha": 5.0},
            supported_systems=["jaimini"]
        ),
        AspectModeInfo(
            name="kp",
            description="KP aspect system",
            orbs={"conjunction": 5.0, "opposition": 5.0},
            supported_systems=["kp"]
        )
    ]
    
    return BaseResponse.create(
        data=aspect_modes,
        path_template=PATH_TEMPLATES["ref_aspect_modes"],
        count=len(aspect_modes)
    )
