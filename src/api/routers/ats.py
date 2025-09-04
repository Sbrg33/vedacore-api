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
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, Field, field_validator

from typing import Optional
from config.feature_flags import require_feature
from api.models.responses import (
    ATSBatchResponse,
    ATSConfigResponse,
    ATSValidationResponse,
    ATSStatusResponse,
    ATSContextsResponse,
)

# Initialize router following project conventions
router = APIRouter(prefix="/api/v1/ats", tags=["ats"], responses=DEFAULT_ERROR_RESPONSES)

# Lazy-initialized service to avoid import errors when ATS core is absent
_service: Optional[object] = None

def _get_service():
    global _service
    if _service is None:
        # Local import to defer adapter import until actually needed
        from app.services.ats_service import ATSService  # type: ignore

        _service = ATSService()
    return _service

# Canonical planet symbol → ID mapping (strict, no aliases)
_SYMBOL_TO_ID = {
    "SUN": 1,
    "MOO": 2,
    "JUP": 3,
    "RAH": 4,
    "MER": 5,
    "VEN": 6,
    "KET": 7,
    "SAT": 8,
    "MAR": 9,
}


class ATSTransitRequest(BaseModel):
    """Request model for ATS transit calculation"""

    timestamp: datetime | None = Field(
        default=None,
        description="UTC timestamp for calculation (defaults to current time)",
    )
    targets: list[int | str] | None = Field(
        default=None,
        description="List of target planet IDs (1-9). Defaults to [6, 5] (Venus, Mercury)",
    )

    @field_validator("targets", mode="before")
    @classmethod
    def _normalize_targets(cls, v):
        if v is None:
            return v
        if isinstance(v, list):
            out: list[int] = []
            for item in v:
                if isinstance(item, int):
                    out.append(item)
                elif isinstance(item, str):
                    token = item.strip().upper()
                    pid = _SYMBOL_TO_ID.get(token)
                    if pid is None:
                        raise ValueError(f"Unknown target token: {item}")
                    out.append(pid)
                else:
                    raise TypeError("targets entries must be int or str")
            return out
        raise TypeError("targets must be a list or null")


class ATSBatchRequest(BaseModel):
    """Request model for batch ATS calculations"""

    start_time: datetime = Field(description="Start of time range (UTC)")
    end_time: datetime = Field(description="End of time range (UTC)")
    interval_minutes: int = Field(
        default=1, ge=1, le=60, description="Interval between calculations in minutes"
    )
    targets: list[int | str] | None = Field(
        default=None, description="List of target planet IDs (1-9)"
    )

    @field_validator("targets", mode="before")
    @classmethod
    def _normalize_targets(cls, v):
        if v is None:
            return v
        if isinstance(v, list):
            out: list[int] = []
            for item in v:
                if isinstance(item, int):
                    out.append(item)
                elif isinstance(item, str):
                    token = item.strip().upper()
                    pid = _SYMBOL_TO_ID.get(token)
                    if pid is None:
                        raise ValueError(f"Unknown target token: {item}")
                    out.append(pid)
                else:
                    raise TypeError("targets entries must be int or str")
            return out
        raise TypeError("targets must be a list or null")


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


@router.post(
    "/transit",
    response_model=ATSResponse,
    summary="Single ATS transit",
    operation_id="ats_transit",
)
@require_feature("ats")
async def calculate_transit(request: ATSTransitRequest):
    """
    Calculate ATS transit scores for given timestamp

    Returns normalized scores (0-100) for target planets based on
    aspect-transfer energy from all planets.

    Performance: <10ms cached, <50ms cold
    """
    try:
        service = _get_service()
        result = service.get_scores(
            timestamp=request.timestamp, targets=request.targets
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/batch",
    response_model=ATSBatchResponse,
    summary="Batch ATS scores",
    operation_id="ats_batch",
)
@require_feature("ats")
async def calculate_batch(request: ATSBatchRequest) -> ATSBatchResponse:
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
        svc = _get_service()
        results = svc.get_scores_batch(
            start_time=request.start_time,
            end_time=request.end_time,
            interval_minutes=request.interval_minutes,
            targets=request.targets,
        )
        return ATSBatchResponse(results=results, count=len(results))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/config",
    response_model=ATSConfigResponse,
    summary="ATS configuration",
    operation_id="ats_config",
)
@require_feature("ats")
async def get_config() -> ATSConfigResponse:
    """
    Get current ATS configuration

    Returns context file, default targets, and other metadata.
    """
    try:
        svc = _get_service()
        context = svc.get_context()
        return ATSConfigResponse(context=context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/validate",
    response_model=ATSValidationResponse,
    summary="Validate ATS scores",
    operation_id="ats_validate",
)
@require_feature("ats")
async def validate_scores(
    timestamp: datetime | None = Query(
        default=None, description="UTC timestamp to validate (defaults to current time)"
    )
) -> ATSValidationResponse:
    """
    Validate ATS scores for correctness

    Checks score ranges, computation time, and other constraints.
    """
    try:
        svc = _get_service()
        result = svc.validate_scores(timestamp)
        return ATSValidationResponse(
            valid=result.get("valid", False),
            scores=result.get("scores", {}),
            computation_time_ms=result.get("computation_time_ms", 0.0),
            timestamp=timestamp or datetime.now(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/status",
    response_model=ATSStatusResponse,
    summary="ATS status",
    operation_id="ats_status",
)
@require_feature("ats")
async def get_status() -> ATSStatusResponse:
    """
    Get ATS system status

    Returns health check and basic system information.
    """
    svc = None
    try:
        # Try a test calculation
        svc = _get_service()
        test_result = svc.get_scores()

        return ATSStatusResponse(
            status="healthy",
            adapter_version=svc.adapter.version,
            context_file=svc.adapter.context_yaml,
            cache_ttl=svc.cache_ttl,
            test_calculation={
                "success": True,
                "compute_ms": test_result.get("compute_ms", 0),
                "cache_hit": test_result.get("cache_hit", False),
            },
        )
    except Exception as e:
        return ATSStatusResponse(
            status="unhealthy",
            adapter_version=getattr(getattr(svc, "adapter", object()), "version", "unknown"),
            context_file=getattr(getattr(svc, "adapter", object()), "context_yaml", "unknown"),
            cache_ttl=getattr(svc, "cache_ttl", 0) if svc else 0,
            test_calculation={"success": False, "error": str(e)},
            error=str(e),
        )


# Backward compatibility endpoints (will deprecate)
@router.get(
    "/health",
    response_model=ATSStatusResponse,
    summary="ATS health (deprecated)",
    operation_id="ats_health",
)
@require_feature("ats")
async def health_check():
    """Check ATS service health (deprecated - use /status)"""
    return await get_status()


@router.get(
    "/contexts",
    response_model=ATSContextsResponse,
    summary="ATS contexts",
    operation_id="ats_contexts",
)
@require_feature("ats")
async def list_contexts() -> ATSContextsResponse:
    """List available ATS contexts"""
    import os

    contexts_dir = "ats/configs"
    contexts = []

    if os.path.exists(contexts_dir):
        for file in os.listdir(contexts_dir):
            if file.endswith(".yaml"):
                name = file.replace(".yaml", "")
                contexts.append({"name": name, "file": file})

    svc = _get_service()
    return ATSContextsResponse(
        contexts=contexts,
        current=os.path.basename(svc.adapter.context_yaml),
    )
