from __future__ import annotations

import logging
import uuid

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

try:
    from interfaces.advisory_adapter_protocol import advisory_registry
except Exception:
    advisory_registry = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/kp/horary", tags=["kp-horary"])


class MoonChain(BaseModel):
    """Moon KP chain with strict validation"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"nl": "MO", "sl": "MO", "ssl": "SA"}}
    )

    nl: str = Field("MO", description="Nakshatra Lord")
    sl: str = Field("MO", description="Sub Lord")
    ssl: str = Field("MO", description="Sub-Sub Lord")


class HoraryRequest(BaseModel):
    """KP Horary calculation request with strict validation"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp_unix": 1700000000,
                "mode": "sunrise_mod",
                "tz_offset_sec": -18000,
                "sunrise_ts": 1699990800,
                "moon_chain": {"nl": "MO", "sl": "MO", "ssl": "SA"},
            }
        }
    )

    timestamp_unix: int = Field(..., description="UTC timestamp in seconds")
    mode: Literal["unix_mod", "daily_mod", "sunrise_mod"] = Field(
        "unix_mod", description="Horary calculation mode"
    )
    tz_offset_sec: int = Field(
        0, description="Timezone offset in seconds (for daily_mod)"
    )
    sunrise_ts: int | None = Field(
        None, description="Sunrise timestamp in UTC seconds (for sunrise_mod)"
    )
    moon_chain: MoonChain = Field(
        default_factory=MoonChain, description="Moon KP chain for boost calculation"
    )

    @field_validator("mode")
    @classmethod
    def validate_mode_requirements(cls, v, info):
        """Validate mode-specific requirements"""
        if hasattr(info, "data") and info.data:
            data = info.data
            if v == "sunrise_mod" and not data.get("sunrise_ts"):
                raise ValueError("sunrise_mod requires sunrise_ts")
            elif v == "daily_mod" and data.get("tz_offset_sec") is None:
                raise ValueError("daily_mod should specify tz_offset_sec")
        return v

    @field_validator("sunrise_ts")
    @classmethod
    def validate_sunrise_ts(cls, v):
        """Validate sunrise timestamp is positive when provided"""
        if v is not None and v <= 0:
            raise ValueError(f"sunrise_ts must be positive, got {v}")
        return v


class HoraryResponse(BaseModel):
    """KP Horary calculation response"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "adapter_id": "kp_horary",
                "adapter_version": "1.0.0",
                "number": 123,
                "planet_ruler": "MO",
                "moon_ruled": True,
                "horary_boost": 0.15,
                "correlation_id": "abc12345",
            }
        }
    )

    adapter_id: str
    adapter_version: str
    number: int = Field(..., description="Horary number 1-249")
    planet_ruler: str = Field(..., description="Ruling planet for the number")
    moon_ruled: bool = Field(..., description="Whether number is ruled by Moon chain")
    horary_boost: float = Field(..., description="Boost factor if Moon ruled")
    correlation_id: str = Field(..., description="Request correlation ID")


def get_correlation_id() -> str:
    """Generate correlation ID for request tracking"""
    return str(uuid.uuid4())[:8]


@router.post("/calculate", response_model=HoraryResponse)
async def calculate_horary(
    request: HoraryRequest, correlation_id: str = Depends(get_correlation_id)
):
    """
    Calculate KP Horary number (1-249) for a given timestamp.

    Supports three calculation modes:
    - unix_mod: Direct modulo of Unix timestamp
    - daily_mod: Seconds since local midnight
    - sunrise_mod: Seconds since sunrise (traditional KP method)

    Returns horary number with planetary ruler and Moon boost factor.
    """
    if advisory_registry is None:
        raise HTTPException(status_code=500, detail="Adapter registry not available")

    adapter = advisory_registry.get("kp_horary")
    if adapter is None:
        raise HTTPException(status_code=500, detail="kp_horary adapter not registered")

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

        # Log successful calculation for observability
        logger.info(
            "KP Horary calculation completed",
            extra={
                "adapter_id": result.get("adapter_id"),
                "adapter_version": result.get("adapter_version"),
                "mode": request.mode,
                "number": result.get("number"),
                "planet_ruler": result.get("planet_ruler"),
                "correlation_id": correlation_id,
            },
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Horary calculation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check():
    """Health check for Horary service"""
    status = {
        "service": "kp_horary",
        "status": "healthy",
        "registry_available": advisory_registry is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if advisory_registry:
        try:
            adapter = advisory_registry.get("kp_horary")
            status["adapter_registered"] = True
            status["adapter_version"] = getattr(adapter, "version", "unknown")
        except Exception:
            # Adapter not registered yet; report gracefully
            status["adapter_registered"] = False

    return status
