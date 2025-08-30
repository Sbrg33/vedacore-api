#!/usr/bin/env python3
"""
Intraday signals router for KP lord changes
"""

import logging

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import NY_TZ
from app.core.session import in_session
from app.core.timeframes import iter_slices
from app.models.requests import IntradayRequest
from app.models.responses import IntradaySlice
from app.services.amd_engine import AMDPhaseDetector
from app.services.cache_service import CacheService
from app.services.facade_adapter import FacadeAdapter
from refactor.monitoring import Timer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["signals"])


# Dependency injection
async def get_cache() -> CacheService:
    """Get cache service instance"""
    return CacheService()


async def get_facade() -> FacadeAdapter:
    """Get facade adapter instance"""
    return FacadeAdapter()


async def get_amd() -> AMDPhaseDetector:
    """Get AMD phase detector instance"""
    return AMDPhaseDetector()


@router.post("/intraday", response_model=list[IntradaySlice])
async def get_intraday_signals(
    request: IntradayRequest,
    cache: CacheService = Depends(get_cache),
    facade: FacadeAdapter = Depends(get_facade),
    amd: AMDPhaseDetector = Depends(get_amd),
) -> list[IntradaySlice]:
    """
    Get intraday KP lord signals for a given date

    Returns time slices with:
    - NL/SL/SL2 lords for each interval
    - AMD phase detection relative to changes
    - Nearest change references
    - Trading session information
    """
    with Timer("intraday_signals"):
        try:
            # Parse date and convert to NY timezone
            date_obj = datetime.strptime(request.date, "%Y-%m-%d")
            ny_date = NY_TZ.localize(date_obj.replace(hour=0, minute=0, second=0))

            # Check cache first
            cache_key = f"intraday:{request.date}:{request.interval}:{'-'.join(request.session_filter)}"
            cached = await cache.get(cache_key)
            if cached:
                # Support only JSON-safe cached payloads (list of dicts)
                if isinstance(cached, list) and (
                    not cached or isinstance(cached[0], dict)
                ):
                    return cached
                # Legacy/invalid cache entry; ignore and recompute

            pass  # Cache miss tracked elsewhere

            # Determine time range based on sessions
            start_time = ny_date.replace(hour=4, minute=0)  # Pre-market start
            end_time = ny_date.replace(hour=20, minute=0)  # After-hours end

            if not request.include_off_hours:
                # Adjust based on session filter
                if "PRE_MARKET" not in request.session_filter:
                    start_time = ny_date.replace(hour=9, minute=30)
                if "AFTER_HOURS" not in request.session_filter:
                    end_time = ny_date.replace(hour=16, minute=0)

            # Get all lord changes for the day
            changes = await facade.get_changes_for_day(ny_date)

            # Generate time slices
            slices = []
            for slice_start, slice_end in iter_slices(
                start_time, end_time, request.interval
            ):
                # Get session type
                session = in_session(slice_start)

                # Skip if not in requested sessions
                if session not in request.session_filter and session != "OFF_HOURS":
                    continue
                if session == "OFF_HOURS" and not request.include_off_hours:
                    continue

                # Get positions at slice midpoint
                midpoint = slice_start + (slice_end - slice_start) / 2
                midpoint_utc = midpoint.astimezone(NY_TZ).replace(tzinfo=None)

                position_data = await facade.get_position(midpoint_utc)

                # Find nearest change
                change_ref = None
                nearest_change = None
                min_delta = float("inf")

                for change in changes:
                    delta = abs((change.timestamp_ny - slice_start).total_seconds())
                    if delta < min_delta:
                        min_delta = delta
                        nearest_change = change

                if nearest_change and min_delta < 3600:  # Within 1 hour
                    change_ref = {
                        "type": nearest_change.level.upper(),
                        "timestamp": nearest_change.timestamp_ny.isoformat(),
                        "delta_seconds": int(
                            (nearest_change.timestamp_ny - slice_start).total_seconds()
                        ),
                        "from_lord": nearest_change.old_lord,
                        "to_lord": nearest_change.new_lord,
                    }

                # Detect AMD phase
                amd_phase = await amd.detect_phase(slice_start, changes)

                # Create slice
                slice_data = IntradaySlice(
                    start=slice_start.isoformat(),
                    end=slice_end.isoformat(),
                    nl=position_data.nl,
                    sl=position_data.sl,
                    sl2=position_data.sl2,
                    amd_phase=amd_phase,
                    change_ref=change_ref,
                    session=session,
                    position=position_data.position,
                    speed=position_data.speed,
                )

                slices.append(slice_data)

            # Cache the result as JSON-safe list of dicts
            try:
                payload = [s.model_dump(mode="json") for s in slices]
            except Exception:
                # Fallback: best-effort conversion
                payload = [s.dict() for s in slices]
            await cache.set(cache_key, payload, ttl=300)  # 5 minute TTL

            return slices

        except Exception as e:
            logger.error(f"Error generating intraday signals: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def signals_health():
    """Health check for signals router"""
    return {"status": "healthy", "service": "signals"}
