#!/usr/bin/env python3
"""
Nodes API Router - Rahu/Ketu perturbation and stationary detection endpoints.
Provides REST API for node events and current state.
"""

import logging
import time

from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field, field_validator

from app.services.cache_service import CacheService
from app.utils.hash_keys import cache_key_hash
from interfaces.kp_nodes_adapter import get_kp_nodes_adapter
from refactor.nodes_config import get_node_config, initialize_node_config
from refactor.time_utils import validate_utc_datetime

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1", tags=["nodes"])

# Initialize cache service
cache_service = CacheService()

# Initialize node configuration if not already done
try:
    config = get_node_config()
except RuntimeError:
    config = initialize_node_config()

# Prometheus metrics
nodes_requests_total = Counter(
    "vedacore_nodes_requests_total", "Total node calculation requests", ["endpoint"]
)

nodes_compute_seconds = Histogram(
    "vedacore_nodes_compute_seconds", "Node computation time in seconds", ["endpoint"]
)

nodes_cache_hits_total = Counter(
    "vedacore_nodes_cache_hits_total", "Total node cache hits"
)

nodes_cache_misses_total = Counter(
    "vedacore_nodes_cache_misses_total", "Total node cache misses"
)

nodes_events_total = Counter(
    "vedacore_nodes_events_total", "Total node events detected", ["type"]
)

nodes_errors_total = Counter(
    "vedacore_nodes_errors_total", "Total node calculation errors", ["type"]
)


# Request/Response models
class NodeEventsRequest(BaseModel):
    """Request model for node events"""

    start: datetime = Field(..., description="Start of search period (UTC)")
    end: datetime = Field(..., description="End of search period (UTC)")
    system: str = Field("KP_NODES", description="Node system (always KP_NODES)")
    include_wobbles: bool = Field(
        False, description="Include wobble/perturbation peaks"
    )
    include_diagnostics: bool = Field(
        False, description="Include solar elongation diagnostics"
    )

    @field_validator("start", "end")
    @classmethod
    def validate_timestamps(cls, v):
        """Ensure timestamps are timezone-aware UTC"""
        try:
            return validate_utc_datetime(v)
        except Exception as e:
            raise ValueError(f"Invalid timestamp: {e}")

    @field_validator("system")
    @classmethod
    def validate_system(cls, v):
        """Ensure only KP_NODES system is used"""
        if v != "KP_NODES":
            raise ValueError("Only KP_NODES system is supported")
        return v

    @field_validator("end")
    @classmethod
    def validate_time_range(cls, v, info):
        """Ensure end is after start and range is reasonable"""
        if "start" in info.data:
            if v <= info.data["start"]:
                raise ValueError("End time must be after start time")
            if (v - info.data["start"]).days > 365:
                raise ValueError("Time range cannot exceed 365 days")
        return v


class NodeStateResponse(BaseModel):
    """Response model for current node state"""

    timestamp: str
    speed: float
    direction: str
    stationary: bool
    longitude: float
    ketu_longitude: float
    solar_elongation: float | None = None
    meta: dict[str, Any]


def generate_cache_key(prefix: str, **kwargs) -> str:
    """Generate cache key from parameters"""
    # Sort kwargs for consistent key generation
    sorted_items = sorted(kwargs.items())
    key_str = f"{prefix}:" + ":".join(
        f"{k}={v}" for k, v in sorted_items if v is not None
    )

    # Hash long keys
    if len(key_str) > 200:
        return f"{prefix}:{cache_key_hash(key_str)}"

    return key_str


@router.post("/nodes/events", response_model=list[dict[str, Any]])
async def get_node_events(request: NodeEventsRequest) -> list[dict[str, Any]]:
    """
    Get node events (stationary, direction changes) in a time range.

    Returns list of events with:
    - type: Event type (stationary_start, stationary_end, direction_change, wobble_peak)
    - timestamp: Exact time of event
    - speed: Node speed at event time
    - Additional metadata based on event type
    """
    start_time = time.time()
    cache_hit = False

    try:
        # Update metrics
        nodes_requests_total.labels(endpoint="events").inc()

        # Generate cache key (cache per day)
        cache_key = generate_cache_key(
            "NODE_EVENTS",
            start=request.start.date().isoformat(),
            end=request.end.date().isoformat(),
            wobbles=request.include_wobbles,
            diagnostics=request.include_diagnostics,
        )

        # Check cache
        cached_result = cache_service.get(cache_key)
        if cached_result:
            nodes_cache_hits_total.inc()
            cache_hit = True
            events = cached_result
        else:
            nodes_cache_misses_total.inc()

            # Get adapter
            adapter = get_kp_nodes_adapter()

            # Update config if needed for wobbles/diagnostics
            if request.include_wobbles and not config.enable_wobble_detection:
                logger.warning("Wobble detection requested but not enabled in config")
            if request.include_diagnostics and not config.enable_diagnostics:
                logger.warning("Diagnostics requested but not enabled in config")

            # Get events
            events = adapter.get_events(request.start, request.end)

            # Filter out wobbles if not requested
            if not request.include_wobbles:
                events = [e for e in events if e.get("type") != "wobble_peak"]

            # Update event metrics
            for event in events:
                nodes_events_total.labels(type=event.get("type", "unknown")).inc()

            # Cache result (TTL: 1 day)
            cache_service.set(cache_key, events, ttl=86400)

        # Add metadata to each event
        compute_time = time.time() - start_time
        for event in events:
            if "meta" not in event:
                event["meta"] = {}
            event["meta"]["cache_hit"] = cache_hit
            event["meta"]["compute_time_ms"] = round(
                compute_time * 1000 / len(events) if events else 0, 3
            )

        # Update metrics
        nodes_compute_seconds.labels(endpoint="events").observe(compute_time)

        return events

    except Exception as e:
        logger.error(f"Error getting node events: {e}")
        nodes_errors_total.labels(type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes/now", response_model=NodeStateResponse)
async def get_current_node_state(
    system: str = Query("KP_NODES", description="Node system"),
    timestamp: datetime | None = Query(None, description="Timestamp (default: now)"),
) -> NodeStateResponse:
    """
    Get current node state (position, speed, direction, stationary flag).

    This endpoint provides live calculation with minimal caching (5s TTL).
    """
    start_time = time.time()

    try:
        # Validate system
        if system != "KP_NODES":
            raise ValueError("Only KP_NODES system is supported")

        # Update metrics
        nodes_requests_total.labels(endpoint="now").inc()

        # Use current time if not provided
        if timestamp is None:
            timestamp = datetime.now(UTC)
        else:
            timestamp = validate_utc_datetime(timestamp)

        # Generate cache key (short TTL)
        cache_key = generate_cache_key(
            "NODE_NOW", system=system, ts=timestamp.isoformat()[:16]  # Round to minute
        )

        # Check cache (very short TTL)
        cached_result = await cache_service.get(cache_key)
        if cached_result:
            nodes_cache_hits_total.inc()
            state = cached_result
        else:
            nodes_cache_misses_total.inc()

            # Get adapter
            adapter = get_kp_nodes_adapter()

            # Get current state
            state = adapter.get_current_state(timestamp)

            # Cache result (TTL: 5 seconds)
            await cache_service.set(cache_key, state, ttl=5)

        # Add performance metadata
        compute_time = time.time() - start_time
        state["meta"]["compute_time_ms"] = round(compute_time * 1000, 3)

        # Update metrics
        nodes_compute_seconds.labels(endpoint="now").observe(compute_time)

        return NodeStateResponse(**state)

    except Exception as e:
        logger.error(f"Error getting current node state: {e}")
        nodes_errors_total.labels(type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes/next-event")
async def get_next_event(
    event_type: str | None = Query(None, description="Specific event type to find"),
    from_time: datetime | None = Query(
        None, description="Start searching from (default: now)"
    ),
    max_days: int = Query(30, description="Maximum days to search", ge=1, le=365),
) -> dict[str, Any]:
    """
    Find the next node event of a specific type.

    Event types:
    - stationary_start: Node entering stationary phase
    - stationary_end: Node exiting stationary phase
    - direction_change: Node changing direction (retro/direct)
    - wobble_peak: Local speed extrema (if enabled)
    """
    start_time = time.time()

    try:
        # Update metrics
        nodes_requests_total.labels(endpoint="next-event").inc()

        # Validate event type if provided
        valid_types = [
            "stationary_start",
            "stationary_end",
            "direction_change",
            "wobble_peak",
        ]
        if event_type and event_type not in valid_types:
            raise ValueError(f"Invalid event type. Must be one of: {valid_types}")

        # Use current time if not provided
        if from_time is None:
            from_time = datetime.now(UTC)
        else:
            from_time = validate_utc_datetime(from_time)

        # Get adapter
        adapter = get_kp_nodes_adapter()

        # Find next event
        event = adapter.find_next_event(from_time, event_type, max_days)

        if event is None:
            result = {
                "found": False,
                "message": f"No {event_type or 'node'} event found within {max_days} days",
                "search_start": from_time.isoformat(),
                "search_days": max_days,
            }
        else:
            result = {
                "found": True,
                "event": event,
                "days_until": (
                    datetime.fromisoformat(event["timestamp"]) - from_time
                ).days,
            }

            # Update event metric
            nodes_events_total.labels(type=event.get("type", "unknown")).inc()

        # Add performance metadata
        compute_time = time.time() - start_time
        result["compute_time_ms"] = round(compute_time * 1000, 3)

        # Update metrics
        nodes_compute_seconds.labels(endpoint="next-event").observe(compute_time)

        return result

    except Exception as e:
        logger.error(f"Error finding next event: {e}")
        nodes_errors_total.labels(type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nodes/statistics")
async def get_node_statistics(
    start: datetime = Body(..., description="Start of analysis period"),
    end: datetime = Body(..., description="End of analysis period"),
) -> dict[str, Any]:
    """
    Get statistical analysis of node behavior over a period.

    Returns:
    - Event counts by type
    - Speed statistics (min, max, average)
    - Configuration used
    """
    start_time = time.time()

    try:
        # Validate timestamps
        start = validate_utc_datetime(start)
        end = validate_utc_datetime(end)

        if end <= start:
            raise ValueError("End time must be after start time")

        if (end - start).days > 365:
            raise ValueError("Analysis period cannot exceed 365 days")

        # Update metrics
        nodes_requests_total.labels(endpoint="statistics").inc()

        # Get adapter
        adapter = get_kp_nodes_adapter()

        # Get statistics
        stats = adapter.get_statistics(start, end)

        # Add performance metadata
        compute_time = time.time() - start_time
        stats["compute_time_ms"] = round(compute_time * 1000, 3)

        # Update metrics
        nodes_compute_seconds.labels(endpoint="statistics").observe(compute_time)

        return stats

    except Exception as e:
        logger.error(f"Error calculating statistics: {e}")
        nodes_errors_total.labels(type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes/config")
async def get_node_configuration() -> dict[str, Any]:
    """
    Get current node detection configuration.

    Shows thresholds, feature flags, and cache settings.
    """
    config = get_node_config()

    return {
        "system": "KP_NODES",
        "configuration": config.to_dict(),
        "features": {
            "stationary_detection": "enabled",
            "direction_changes": "enabled",
            "wobble_detection": (
                "enabled" if config.enable_wobble_detection else "disabled"
            ),
            "solar_diagnostics": "enabled" if config.enable_diagnostics else "disabled",
            "hysteresis": "enabled" if config.enable_hysteresis else "disabled",
        },
        "thresholds": {
            "stationary_speed": f"{config.speed_threshold}°/day",
            "exit_threshold": f"{config.get_exit_threshold()}°/day",
            "wobble_minimum": f"{config.wobble_min_amplitude}°/day",
        },
        "performance": {
            "scan_step": f"{config.scan_step_seconds} seconds",
            "bisection_tolerance": f"{config.bisection_tolerance_seconds} seconds",
            "max_iterations": config.bisection_max_iters,
        },
        "cache": {
            "events_ttl": f"{config.cache_ttl_seconds} seconds",
            "live_ttl": f"{config.live_ttl_seconds} seconds",
        },
    }


@router.get("/nodes/systems")
async def list_node_systems() -> dict[str, Any]:
    """
    List available node systems and their capabilities.
    """
    return {
        "systems": [
            {
                "id": "KP_NODES",
                "name": "KP True Nodes (Rahu/Ketu)",
                "description": "True lunar node calculations with stationary and perturbation detection",
                "features": [
                    "Stationary window detection",
                    "Direction change detection (retro/direct)",
                    "Wobble/perturbation peaks (optional)",
                    "Solar elongation diagnostics (optional)",
                    "Hysteresis for stable transitions",
                ],
                "accuracy": {
                    "time_precision": "≤ 0.5 seconds",
                    "speed_threshold": "0.005°/day default",
                    "bisection_refinement": "24 iterations max",
                },
                "performance": {
                    "24_hour_scan": "< 150ms",
                    "single_event": "< 10ms",
                    "cache_ttl": "1 day for events, 5s for live",
                },
            }
        ],
        "endpoints": [
            {
                "path": "/api/v1/nodes/events",
                "method": "POST",
                "description": "Get node events in a time range",
            },
            {
                "path": "/api/v1/nodes/now",
                "method": "GET",
                "description": "Get current node state",
            },
            {
                "path": "/api/v1/nodes/next-event",
                "method": "GET",
                "description": "Find next node event",
            },
            {
                "path": "/api/v1/nodes/statistics",
                "method": "POST",
                "description": "Get statistical analysis",
            },
            {
                "path": "/api/v1/nodes/config",
                "method": "GET",
                "description": "View configuration",
            },
        ],
    }
