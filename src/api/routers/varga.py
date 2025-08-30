"""
API endpoints for Varga (Divisional Charts) calculations.
"""

import re

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from config.feature_flags import get_feature_flags
from refactor.facade import (
    get_all_shodasavarga,
    get_varga_chart,
    get_varga_chart_from_longitudes,
    get_varga_strength,
    get_vargottama_status,
    register_custom_varga_scheme,
)

router = APIRouter(prefix="/api/v1/varga", tags=["varga"])


class VargaCalculateDirectRequest(BaseModel):
    """Direct varga calculation from longitudes."""

    longitudes: dict[int, float] = Field(
        ...,
        description="Planet ID to longitude mapping",
        example={1: 45.5, 2: 123.4, 3: 234.5},
    )
    divisor: int = Field(..., ge=2, le=300, description="Divisional chart number")
    scheme: str = Field(default="auto", description="Calculation scheme")

    @field_validator("longitudes")
    @classmethod
    def validate_longitudes(cls, v):
        for planet_id, lon in v.items():
            if not (1 <= planet_id <= 9):
                raise ValueError(f"Invalid planet ID: {planet_id}")
            if not (0 <= lon < 360):
                raise ValueError(f"Invalid longitude: {lon}")
        return v


class VargaCalculateRequest(BaseModel):
    """Timestamp-based varga calculation."""

    timestamp: datetime = Field(..., description="UTC timestamp")
    divisor: int = Field(..., ge=2, le=300, description="Divisional chart number")
    planets: list[int] | None = Field(None, description="Planet IDs (default: all)")
    scheme: str = Field(default="auto", description="Calculation scheme")


class VargottamaRequest(BaseModel):
    """Vargottama detection request."""

    timestamp: datetime = Field(..., description="UTC timestamp")
    check_vargas: list[int] | None = Field(
        default=[9, 10, 12], description="Vargas to check for vargottama"
    )
    planets: list[int] | None = Field(None, description="Planet IDs (default: all)")


class ShodasavargaRequest(BaseModel):
    """All 16 divisional charts request."""

    timestamp: datetime = Field(..., description="UTC timestamp")
    planet_id: int | None = Field(None, ge=1, le=9, description="Specific planet")


class VargaStrengthRequest(BaseModel):
    """Vimshopaka Bala strength calculation."""

    timestamp: datetime = Field(..., description="UTC timestamp")
    planet_id: int = Field(..., ge=1, le=9, description="Planet ID")
    varga_set: str = Field(
        default="shadvarga",
        description="Weight set (shadvarga/saptavarga/dashavarga/shodasavarga)",
    )


class CustomVargaRequest(BaseModel):
    """Custom varga scheme registration."""

    name: str = Field(..., min_length=3, max_length=50, description="Scheme name")
    divisor: int = Field(..., ge=2, le=300, description="Number of divisions")
    offsets: dict[int, int] = Field(..., description="Per-sign offset mapping")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Name must contain only alphanumeric, underscore, and hyphen"
            )
        return v

    @field_validator("offsets")
    @classmethod
    def validate_offsets(cls, v):
        if len(v) != 12:
            raise ValueError("Must provide offsets for all 12 signs")
        for sign, offset in v.items():
            if not (0 <= sign <= 11):
                raise ValueError(f"Invalid sign index: {sign}")
            if not (0 <= offset <= 11):
                raise ValueError(f"Invalid offset: {offset}")
        return v


@router.post("/calculate_direct", summary="Calculate varga from longitudes")
async def calculate_varga_direct(request: VargaCalculateDirectRequest):
    """Calculate divisional chart positions directly from planet longitudes.

    This endpoint is useful when you already have planet positions
    and want to calculate their varga positions without timestamp lookup.
    """
    flags = get_feature_flags()

    if not flags.ENABLE_VARGA_ADVISORY:
        raise HTTPException(
            status_code=403, detail="Varga calculations are not enabled"
        )

    try:
        result = get_varga_chart_from_longitudes(
            request.longitudes, request.divisor, request.scheme
        )

        # Convert 0-11 to 1-12 for display
        display_result = {planet_id: sign + 1 for planet_id, sign in result.items()}

        return {
            "divisor": request.divisor,
            "scheme": request.scheme,
            "positions": display_result,
            "note": "Signs are 1-12 (Aries-Pisces)",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate", summary="Calculate varga for timestamp")
async def calculate_varga(request: VargaCalculateRequest):
    """Calculate divisional chart positions for a given timestamp.

    Fetches planet positions internally and calculates their varga positions.
    """
    flags = get_feature_flags()

    if not flags.ENABLE_VARGA_ADVISORY:
        raise HTTPException(
            status_code=403, detail="Varga calculations are not enabled"
        )

    # Check if requested varga is in enabled list
    varga_name = f"D{request.divisor}"
    if varga_name not in flags.ENABLED_VARGAS:
        raise HTTPException(
            status_code=403,
            detail=f"{varga_name} is not in enabled vargas: {flags.ENABLED_VARGAS}",
        )

    try:
        # Ensure UTC
        if request.timestamp.tzinfo is None:
            request.timestamp = request.timestamp.replace(tzinfo=UTC)

        result = get_varga_chart(
            request.timestamp, request.divisor, request.planets, request.scheme
        )

        # Convert 0-11 to 1-12 for display
        display_result = {
            str(planet_id): sign + 1 for planet_id, sign in result.items()
        }

        return {
            "timestamp": request.timestamp.isoformat(),
            "divisor": request.divisor,
            "scheme": request.scheme,
            "positions": display_result,
            "note": "Signs are 1-12 (Aries-Pisces)",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vargottama", summary="Detect vargottama planets")
async def detect_vargottama(request: VargottamaRequest):
    """Check which planets are vargottama (same sign in D1 and varga).

    Vargottama planets have enhanced strength and deliver more reliable results.
    """
    flags = get_feature_flags()

    if not flags.ENABLE_VARGOTTAMA:
        raise HTTPException(
            status_code=403, detail="Vargottama detection is not enabled"
        )

    try:
        # Ensure UTC
        if request.timestamp.tzinfo is None:
            request.timestamp = request.timestamp.replace(tzinfo=UTC)

        result = get_vargottama_status(
            request.timestamp, request.check_vargas, request.planets
        )

        # Add planet names for clarity
        planet_names = {
            1: "Sun",
            2: "Moon",
            3: "Mars",
            4: "Rahu",
            5: "Mercury",
            6: "Venus",
            7: "Ketu",
            8: "Saturn",
            9: "Jupiter",
        }

        display_result = {}
        for planet_id, varga_status in result.items():
            planet_name = planet_names.get(planet_id, f"Planet {planet_id}")
            display_result[planet_name] = varga_status

        return {
            "timestamp": request.timestamp.isoformat(),
            "vargottama_status": display_result,
            "checked_vargas": request.check_vargas,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shodasavarga", summary="Calculate all 16 divisional charts")
async def calculate_shodasavarga(request: ShodasavargaRequest):
    """Calculate all 16 Shodasavarga divisional charts.

    Returns positions in all standard divisional charts used in Vedic astrology.
    """
    flags = get_feature_flags()

    if not flags.ENABLE_VARGA_ADVISORY:
        raise HTTPException(
            status_code=403, detail="Varga calculations are not enabled"
        )

    try:
        # Ensure UTC
        if request.timestamp.tzinfo is None:
            request.timestamp = request.timestamp.replace(tzinfo=UTC)

        result = get_all_shodasavarga(request.timestamp, request.planet_id)

        # Convert 0-11 to 1-12 for display
        display_result = {}
        for varga_name, positions in result.items():
            display_result[varga_name] = {
                str(planet_id): sign + 1 for planet_id, sign in positions.items()
            }

        return {
            "timestamp": request.timestamp.isoformat(),
            "planet_id": request.planet_id,
            "shodasavarga": display_result,
            "note": "Signs are 1-12 (Aries-Pisces)",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strength", summary="Calculate Vimshopaka Bala")
async def calculate_varga_strength(request: VargaStrengthRequest):
    """Calculate Vimshopaka Bala (composite varga strength) for a planet.

    Uses weighted vargottama status across multiple divisional charts.
    """
    flags = get_feature_flags()

    if not flags.ENABLE_VIMSHOPAKA_BALA:
        raise HTTPException(
            status_code=403, detail="Vimshopaka Bala calculation is not enabled"
        )

    try:
        # Ensure UTC
        if request.timestamp.tzinfo is None:
            request.timestamp = request.timestamp.replace(tzinfo=UTC)

        strength = get_varga_strength(
            request.timestamp, request.planet_id, request.varga_set
        )

        planet_names = {
            1: "Sun",
            2: "Moon",
            3: "Mars",
            4: "Rahu",
            5: "Mercury",
            6: "Venus",
            7: "Ketu",
            8: "Saturn",
            9: "Jupiter",
        }

        return {
            "timestamp": request.timestamp.isoformat(),
            "planet": planet_names.get(
                request.planet_id, f"Planet {request.planet_id}"
            ),
            "varga_set": request.varga_set,
            "strength": round(strength, 2),
            "scale": "0-100",
            "interpretation": (
                "Very Strong"
                if strength >= 75
                else (
                    "Strong"
                    if strength >= 60
                    else (
                        "Medium"
                        if strength >= 40
                        else "Weak" if strength >= 25 else "Very Weak"
                    )
                )
            ),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register_custom", summary="Register custom varga scheme")
async def register_custom_varga(
    request: CustomVargaRequest, authorization: str | None = Header(None)
):
    """Register a custom varga calculation scheme.

    Requires authorization for security. Custom schemes are useful
    for research and exploring non-traditional divisional patterns.
    """
    flags = get_feature_flags()

    if not flags.ENABLE_CUSTOM_VARGA:
        raise HTTPException(
            status_code=403, detail="Custom varga registration is not enabled"
        )

    # Simple auth check (in production, use proper authentication)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization required for custom scheme registration",
        )

    try:
        success = register_custom_varga_scheme(
            request.name, request.divisor, request.offsets
        )

        if success:
            return {
                "status": "success",
                "name": request.name,
                "divisor": request.divisor,
                "message": f"Custom scheme '{request.name}' registered successfully",
            }
        else:
            raise HTTPException(
                status_code=400, detail="Failed to register custom scheme"
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schemes", summary="List available varga schemes")
async def list_varga_schemes():
    """Get list of all available varga calculation schemes.

    Includes both classical and custom registered schemes.
    """
    from refactor.varga import list_schemes
    from refactor.varga_piecewise import register_piecewise_schemes

    # Ensure piecewise schemes are registered
    register_piecewise_schemes()

    schemes = list_schemes()

    return {
        "schemes": schemes,
        "count": len(schemes),
        "categories": {
            "classical": [s for s in schemes if "classical" in s],
            "custom": [s for s in schemes if "custom" in s],
            "other": [s for s in schemes if "classical" not in s and "custom" not in s],
        },
    }


@router.get("/config", summary="Get varga configuration")
async def get_varga_configuration():
    """Get current varga system configuration.

    Shows enabled features, classical scheme mappings, and limits.
    """
    from refactor.varga_config import get_varga_config

    flags = get_feature_flags()
    config = get_varga_config()

    return {
        "features": {
            "varga_advisory": flags.ENABLE_VARGA_ADVISORY,
            "enabled_vargas": flags.ENABLED_VARGAS,
            "vargottama": flags.ENABLE_VARGOTTAMA,
            "vimshopaka_bala": flags.ENABLE_VIMSHOPAKA_BALA,
            "custom_varga": flags.ENABLE_CUSTOM_VARGA,
        },
        "limits": {
            "min_divisor": config.min_divisor,
            "max_divisor": config.max_divisor,
            "max_custom_schemes": config.max_custom_schemes,
        },
        "classical_schemes": config.classical_schemes,
        "vimshopaka_sets": list(config.vimshopaka_sets.keys()),
        "standard_vargas": config.get_standard_vargas(),
        "shodasavarga": config.get_shodasavarga_divisors(),
    }
