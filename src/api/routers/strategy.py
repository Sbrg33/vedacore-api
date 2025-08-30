"""
Trading Strategy API Router
Phase 9: REST endpoints for strategy confidence timelines
"""

from __future__ import annotations

import logging
import time

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel, Field, field_validator

from interfaces.registry import get_system

logger = logging.getLogger(__name__)
UTC = UTC

# Prometheus metrics
strategy_requests = Counter(
    "vedacore_strategy_requests_total",
    "Total strategy requests",
    ["endpoint", "ticker"],
)

strategy_compute_time = Histogram(
    "vedacore_strategy_compute_seconds",
    "Strategy computation time",
    ["endpoint", "ticker"],
)

strategy_confidence = Gauge(
    "vedacore_strategy_confidence_gauge",
    "Current confidence level",
    ["ticker", "strength"],
)

strategy_rules_applied = Counter(
    "vedacore_strategy_rules_applied_total",
    "Rules applied during confidence synthesis",
    ["rule_name"],
)

strategy_errors = Counter(
    "vedacore_strategy_errors_total",
    "Total strategy errors",
    ["endpoint", "error_type"],
)

# Phase 10: Direction metrics
strategy_direction_seconds = Histogram(
    "vedacore_strategy_direction_seconds",
    "Time spent computing direction",
    ["endpoint"],
)

strategy_direction_flips = Counter(
    "vedacore_strategy_direction_flips_total", "Total direction flips", ["ticker"]
)

strategy_direction_distribution = Gauge(
    "vedacore_strategy_direction_distribution",
    "Distribution of directional signals",
    ["ticker", "direction"],
)

router = APIRouter(
    prefix="/api/v1/strategy",
    tags=["strategy"],
    responses={404: {"description": "Not found"}},
)


class DayRequest(BaseModel):
    """Request for daily confidence timeline."""

    date: str = Field(
        ..., description="Date in YYYY-MM-DD format", example="2025-09-05"
    )
    ticker: str = Field(default="TSLA", description="Ticker symbol", example="TSLA")
    system: str = Field(default="KP_STRATEGY", description="System identifier")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format."""
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid date format: {v}")


class WindowRequest(BaseModel):
    """Request for time window aggregation."""

    start: str = Field(
        ..., description="Start timestamp in ISO format", example="2025-09-05T14:00:00Z"
    )
    end: str = Field(
        ..., description="End timestamp in ISO format", example="2025-09-05T15:00:00Z"
    )
    ticker: str = Field(default="TSLA", description="Ticker symbol", example="TSLA")
    system: str = Field(default="KP_STRATEGY", description="System identifier")

    @field_validator("start", "end")
    @classmethod
    def validate_timestamps(cls, v: str) -> str:
        """Validate timestamp format."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {v}")


class ConfigDryrunRequest(BaseModel):
    """Request for configuration dry run."""

    date: str = Field(..., description="Date to test on", example="2025-09-05")
    ticker: str = Field(default="TSLA", description="Ticker symbol")
    config: dict[str, Any] = Field(..., description="Test configuration")
    system: str = Field(default="KP_STRATEGY", description="System identifier")


@router.post("/day", summary="Get daily confidence timeline")
async def strategy_day(req: DayRequest = Body(...)) -> dict[str, Any]:
    """
    Generate minute-by-minute confidence timeline for a trading day.

    Returns confidence scores, direction hints, and applied rules for each minute.
    """
    strategy_requests.labels(endpoint="day", ticker=req.ticker).inc()

    try:
        start_time = time.time()

        # Get adapter
        adapter = get_system(req.system)
        if adapter is None:
            strategy_errors.labels(endpoint="day", error_type="unknown_system").inc()
            raise HTTPException(status_code=400, detail=f"Unknown system: {req.system}")

        # Parse date
        day = date.fromisoformat(req.date)

        # Generate timeline
        result = adapter.day(day, ticker=req.ticker)

        # Update metrics
        compute_time = time.time() - start_time
        strategy_compute_time.labels(endpoint="day", ticker=req.ticker).observe(
            compute_time
        )

        # Update confidence gauge
        if "summary" in result:
            summary = result["summary"]
            for strength in ["high", "medium", "low"]:
                count = summary.get(f"{strength}_bins", 0)
                strategy_confidence.labels(ticker=req.ticker, strength=strength).set(
                    count
                )

            # Update direction metrics (Phase 10)
            for direction in ["up", "down", "neutral"]:
                count = summary.get(f"{direction}_minutes", 0)
                strategy_direction_distribution.labels(
                    ticker=req.ticker, direction=direction
                ).set(count)

            flip_count = summary.get("flip_count", 0)
            if flip_count > 0:
                strategy_direction_flips.labels(ticker=req.ticker).inc(flip_count)

        # Count rules applied
        for signal in result.get("timeline", []):
            for rule in signal.get("rules_applied", []):
                strategy_rules_applied.labels(rule_name=rule).inc()

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in strategy_day: {e}")
        strategy_errors.labels(endpoint="day", error_type="internal").inc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.post("/window", summary="Get window confidence aggregation")
async def strategy_window(req: WindowRequest = Body(...)) -> dict[str, Any]:
    """
    Get aggregated confidence statistics for a time window.

    Useful for analyzing specific market periods or sessions.
    """
    strategy_requests.labels(endpoint="window", ticker=req.ticker).inc()

    try:
        start_time = time.time()

        # Get adapter
        adapter = get_system(req.system)
        if adapter is None:
            strategy_errors.labels(endpoint="window", error_type="unknown_system").inc()
            raise HTTPException(status_code=400, detail=f"Unknown system: {req.system}")

        # Generate window aggregation
        result = adapter.window(req.start, req.end, ticker=req.ticker)

        # Update metrics
        compute_time = time.time() - start_time
        strategy_compute_time.labels(endpoint="window", ticker=req.ticker).observe(
            compute_time
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in strategy_window: {e}")
        strategy_errors.labels(endpoint="window", error_type="internal").inc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.get("/config", summary="Get strategy configuration")
async def strategy_config(system: str = Query(default="KP_STRATEGY")) -> dict[str, Any]:
    """
    Get current strategy configuration including weights, rules, and thresholds.
    """
    try:
        # Get adapter
        adapter = get_system(system)
        if adapter is None:
            raise HTTPException(status_code=400, detail=f"Unknown system: {system}")

        # Get metadata
        if hasattr(adapter, "get_metadata"):
            return adapter.get_metadata()
        else:
            return {"system": system, "message": "Metadata not available"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in strategy_config: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.post("/config/dryrun", summary="Test configuration without persisting")
async def strategy_config_dryrun(
    req: ConfigDryrunRequest = Body(...),
) -> dict[str, Any]:
    """
    Test a strategy configuration without persisting it.

    Useful for experimenting with different weights and rules.
    """
    strategy_requests.labels(endpoint="config_dryrun", ticker=req.ticker).inc()

    try:
        start_time = time.time()

        # Get adapter
        adapter = get_system(req.system)
        if adapter is None:
            strategy_errors.labels(
                endpoint="config_dryrun", error_type="unknown_system"
            ).inc()
            raise HTTPException(status_code=400, detail=f"Unknown system: {req.system}")

        # Parse date
        day = date.fromisoformat(req.date)

        # Run dryrun
        if hasattr(adapter, "config_dryrun"):
            result = adapter.config_dryrun(req.config, day, req.ticker)
        else:
            raise HTTPException(status_code=501, detail="Config dryrun not implemented")

        # Update metrics
        compute_time = time.time() - start_time
        strategy_compute_time.labels(
            endpoint="config_dryrun", ticker=req.ticker
        ).observe(compute_time)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in config_dryrun: {e}")
        strategy_errors.labels(endpoint="config_dryrun", error_type="internal").inc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e!s}")


@router.get("/health", summary="Check strategy system health")
async def strategy_health() -> dict[str, Any]:
    """
    Check health of strategy system and dependencies.
    """
    try:
        # Check if KP_STRATEGY is registered
        adapter = get_system("KP_STRATEGY")
        if adapter is None:
            return {"status": "unhealthy", "reason": "KP_STRATEGY not registered"}

        # Check dependencies
        dependencies = {
            "KP_MICRO": get_system("KP_MICRO") is not None,
            "KP_MOON": get_system("KP_MOON") is not None,
            "KP_NODES": get_system("KP_NODES") is not None,
        }

        # Overall health
        all_healthy = all(dependencies.values())

        return {
            "status": "healthy" if all_healthy else "degraded",
            "system": "KP_STRATEGY",
            "dependencies": dependencies,
            "version": adapter.version if hasattr(adapter, "version") else "unknown",
        }

    except Exception as e:
        logger.error(f"Error in strategy_health: {e}")
        return {"status": "unhealthy", "error": str(e)}
