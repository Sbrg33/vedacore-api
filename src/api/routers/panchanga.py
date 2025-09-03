"""
Panchanga API Router - SystemAdapter Registry Implementation

Demonstrates the PM-requested pattern of using registry.get() instead of direct imports.
This replaces direct module imports with SystemAdapter registry calls.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_api_logger
from interfaces.advisory_adapter_protocol import advisory_registry
from api.models.responses import (
    PanchangaHealthResponse,
    PanchangaSchemaResponse,
    PanchangaExplanationResponse,
)

router = APIRouter(prefix="/api/v1/panchanga", tags=["panchanga"], responses=DEFAULT_ERROR_RESPONSES)
logger = get_api_logger("panchanga")


class PanchangaRequest(BaseModel):
    """Request for Panchanga calculation via SystemAdapter"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2024-08-24T14:30:00Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "include_recommendations": True,
            }
        }
    )

    timestamp: datetime = Field(
        ..., description="UTC timestamp for Panchanga calculation"
    )
    latitude: float = Field(
        default=None, ge=-90, le=90, description="Location latitude"
    )
    longitude: float = Field(
        default=None, ge=-180, le=180, description="Location longitude"
    )
    include_recommendations: bool = Field(
        default=True, description="Include muhurta recommendations"
    )


class PanchangaResponse(BaseModel):
    """Response from Panchanga SystemAdapter"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "data": {
                    "panchanga": {"tithi": {"name": "Purnima", "number": 15}},
                    "recommendations": {"favorable": ["meditation", "prayers"]},
                    "timestamp": "2024-08-24T14:30:00Z",
                },
                "meta": {
                    "adapter_id": "panchanga",
                    "adapter_version": "1.0.0",
                    "compute_time_ms": 15.4,
                },
            }
        }
    )

    status: str
    data: dict[str, Any]
    meta: dict[str, Any]


@router.post(
    "/calculate",
    response_model=PanchangaResponse,
    summary="Calculate Panchanga",
    operation_id="panchanga_calculate",
)
async def calculate_panchanga(request: PanchangaRequest) -> PanchangaResponse:
    """
    Calculate Panchanga using SystemAdapter registry pattern

    This demonstrates the PM-requested approach:
    - Uses registry.get("panchanga") instead of direct imports
    - Logs include adapter_id + adapter_version
    - No direct imports from modules/panchanga/*
    """
    try:
        # Get adapter from registry (PM requirement)
        adapter = advisory_registry.get("panchanga")

        # Log with adapter metadata (PM requirement)
        logger.info(
            "Panchanga calculation requested",
            extra={
                "adapter_id": adapter.id,
                "adapter_version": adapter.version,
                "timestamp": request.timestamp.isoformat(),
            },
        )

        # Prepare context for adapter
        ctx = {
            "timestamp": request.timestamp,
            "latitude": request.latitude,
            "longitude": request.longitude,
            "include_recommendations": request.include_recommendations,
        }

        # Call adapter through registry (PM requirement)
        result = adapter.compute(ctx)

        # Log completion with adapter metadata
        logger.info(
            "Panchanga calculation completed",
            extra={
                "adapter_id": result["meta"]["adapter_id"],
                "adapter_version": result["meta"]["adapter_version"],
                "compute_time_ms": result["meta"]["compute_time_ms"],
                "cache_hit": result["meta"]["cache_hit"],
            },
        )

        return PanchangaResponse(
            status="success", data=result["data"], meta=result["meta"]
        )

    except KeyError as e:
        logger.error(f"Panchanga adapter not found: {e}")
        raise HTTPException(
            status_code=500, detail=f"Panchanga adapter not available: {e}"
        )
    except Exception as e:
        logger.error(f"Panchanga calculation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Panchanga calculation error: {e!s}"
        )


@router.get(
    "/health",
    response_model=PanchangaHealthResponse,
    summary="Panchanga health",
    operation_id="panchanga_health",
)
async def panchanga_health() -> PanchangaHealthResponse:
    """Check Panchanga adapter health via registry"""
    try:
        adapter = advisory_registry.get("panchanga")
        health = adapter.health_check()

        return PanchangaHealthResponse(
            adapter_id=adapter.id,
            version=adapter.version,
            health=health,
            registry_status="available",
        )
    except KeyError:
        return PanchangaHealthResponse(
            adapter_id="panchanga",
            version="unknown",
            health={"status": "not_registered", "healthy": False},
            registry_status="adapter_missing",
        )


@router.get(
    "/schema",
    response_model=PanchangaSchemaResponse,
    summary="Panchanga schema",
    operation_id="panchanga_schema",
)
async def panchanga_schema() -> PanchangaSchemaResponse:
    """Get Panchanga adapter input/output schema"""
    try:
        adapter = advisory_registry.get("panchanga")
        schema = adapter.schema()

        return PanchangaSchemaResponse(
            adapter_id=adapter.id,
            version=adapter.version,
            schema=schema,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Panchanga adapter not found: {e}")


@router.post(
    "/explain",
    response_model=PanchangaExplanationResponse,
    summary="Explain Panchanga",
    operation_id="panchanga_explain",
)
async def explain_panchanga(request: PanchangaRequest) -> PanchangaExplanationResponse:
    """Get explanation of Panchanga results via registry"""
    try:
        adapter = advisory_registry.get("panchanga")

        # First compute the result
        ctx = request.model_dump()
        result = adapter.compute(ctx)

        # Then explain it
        explanation = adapter.explain(result)

        return PanchangaExplanationResponse(
            status="success",
            result=result,
            explanation=explanation,
            adapter_info={"id": adapter.id, "version": adapter.version},
        )
    except Exception as e:
        logger.error(f"Panchanga explanation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Explanation error: {e!s}")
