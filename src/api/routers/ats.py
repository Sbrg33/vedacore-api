#!/usr/bin/env python3
"""
ATS API Router - Endpoints for Aspect-Transfer Scoring

Notes:
- Feature Flag: ENABLE_ATS controls access. When disabled, endpoints return 403.
- Minimal Mode: The default in-repo ATS implementation provides neutral (zero)
  scores to keep production startup healthy. Replace with full ATS engine for
  production scoring when available.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.ats_service import ATSService
from config.feature_flags import require_feature

# Initialize router following project conventions
router = APIRouter(prefix="/api/v1/ats", tags=["ATS"])

# Initialize service (singleton)
service = ATSService()


class ATSTransitRequest(BaseModel):
    """Request model for ATS transit calculation"""

    timestamp: datetime | None = Field(
        default=None,
        description="UTC timestamp for calculation (defaults to current time)",
    )
    targets: list[int] | None = Field(
        default=None,
        description="List of target planet IDs (1-9). Defaults to [6, 5] (Venus, Mercury)",
    )


class ATSBatchRequest(BaseModel):
    """Request model for batch ATS calculations"""

    start_time: datetime = Field(description="Start of time range (UTC)")
    end_time: datetime = Field(description="End of time range (UTC)")
    interval_minutes: int = Field(
        default=1, ge=1, le=60, description="Interval between calculations in minutes"
    )
    targets: list[int] | None = Field(
        default=None, description="List of target planet IDs (1-9)"
    )


class ATSResponse(BaseModel):
    """Standard ATS response model"""

    timestamp: str
    scores_norm: dict[str, float] = Field(
        description="Normalized scores (0-100 scale) by planet ID"
    )
    scores_raw: dict[str, float] = Field(description="Raw scores before normalization")
    by_source: dict[str, dict[str, float]] = Field(
        description="Score breakdown by source planet"
    )
    targets: list[int] = Field(description="Target planet IDs used")
    context: str = Field(description="Context configuration file used")
    compute_ms: float = Field(description="Computation time in milliseconds")
    cache_hit: bool = Field(description="Whether result was from cache")
    deltas: dict[str, float] | None = Field(
        default=None, description="Score changes from previous minute"
    )


@router.post("/transit", response_model=ATSResponse)
@require_feature("ats")
async def calculate_transit(request: ATSTransitRequest):
    """
    Calculate ATS transit scores for given timestamp

    Returns normalized scores (0-100) for target planets based on
    aspect-transfer energy from all planets.

    Performance: <10ms cached, <50ms cold
    """
    try:
        result = service.get_scores(
            timestamp=request.timestamp, targets=request.targets
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
@require_feature("ats")
async def calculate_batch(request: ATSBatchRequest):
    """
    Calculate ATS scores for a time range

    Returns list of score calculations at specified intervals.
    Maximum range: 24 hours.
    """
    # Validate time range
    time_diff = (request.end_time - request.start_time).total_seconds()
    if time_diff > 86400:  # 24 hours
        raise HTTPException(status_code=400, detail="Time range cannot exceed 24 hours")

    if time_diff < 0:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    try:
        results = service.get_scores_batch(
            start_time=request.start_time,
            end_time=request.end_time,
            interval_minutes=request.interval_minutes,
            targets=request.targets,
        )
        return {"results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
@require_feature("ats")
async def get_config():
    """
    Get current ATS configuration

    Returns context file, default targets, and other metadata.
    """
    try:
        return service.get_context()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validate")
@require_feature("ats")
async def validate_scores(
    timestamp: datetime | None = Query(
        default=None, description="UTC timestamp to validate (defaults to current time)"
    )
):
    """
    Validate ATS scores for correctness

    Checks score ranges, computation time, and other constraints.
    """
    try:
        return service.validate_scores(timestamp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
@require_feature("ats")
async def get_status():
    """
    Get ATS system status

    Returns health check and basic system information.
    """
    try:
        # Try a test calculation
        test_result = service.get_scores()

        return {
            "status": "healthy",
            "adapter_version": service.adapter.version,
            "context_file": service.adapter.context_yaml,
            "cache_ttl": service.cache_ttl,
            "test_calculation": {
                "success": True,
                "compute_ms": test_result.get("compute_ms", 0),
                "cache_hit": test_result.get("cache_hit", False),
            },
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "adapter_version": getattr(service.adapter, "version", "unknown"),
            "test_calculation": {"success": False, "error": str(e)},
        }


# Backward compatibility endpoints (will deprecate)
@router.get("/health")
@require_feature("ats")
async def health_check():
    """Check ATS service health (deprecated - use /status)"""
    return await get_status()


@router.get("/contexts")
@require_feature("ats")
async def list_contexts():
    """List available ATS contexts"""
    import os

    contexts_dir = "ats/configs"
    contexts = []

    if os.path.exists(contexts_dir):
        for file in os.listdir(contexts_dir):
            if file.endswith(".yaml"):
                name = file.replace(".yaml", "")
                contexts.append({"name": name, "file": file})

    return {
        "contexts": contexts,
        "current": os.path.basename(service.adapter.context_yaml),
    }
