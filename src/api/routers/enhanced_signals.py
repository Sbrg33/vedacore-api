#!/usr/bin/env python3
"""
Enhanced KP Timing Signals API Router

Advanced multi-timeframe KP signal analysis with enterprise features:
- Multi-timeframe analysis (1m, 5m, 15m, 1h, 4h, 1d)
- Redis-backed high-frequency caching
- Real-time signal streaming via SSE
- Confluence detection across planetary transits
- Performance optimized for sub-150ms P95 response times
- Rate limiting and authentication
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from sse_starlette.sse import EventSourceResponse

from app.models.requests import EnhancedSignalsRequest, SignalStreamRequest
from app.models.responses import (
    EnhancedSignal,
    EnhancedSignalsResponse,
    EnhancedSignalsMetadata,
    TimeframeAnalysis as TimeframeAnalysisModel,
    PlanetSignalAnalysis,
    ConfluenceAnalysis,
    PerformanceStatsResponse,
    SignalStreamUpdate
)
from app.services.enhanced_signals_service import get_enhanced_signals_service
from api.services.auth import AuthContext, require_jwt_query
from api.services.rate_limiter import rate_limiter
from api.services.metrics import streaming_metrics
from api.services.stream_manager import stream_manager
from refactor.monitoring import Timer
from shared.otel import get_tracer
from shared.trace_attrs import set_common_attrs
from shared.normalize import NORMALIZATION_VERSION, EPHEMERIS_DATASET_VERSION

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["enhanced-signals"], responses=DEFAULT_ERROR_RESPONSES)
_tracer = get_tracer("enhanced-signals")

# Stream topics for enhanced signals
SIGNAL_TOPICS = {
    "kp.signals.enhanced": "Enhanced KP timing signals",
    "kp.confluence.alerts": "Multi-timeframe confluence alerts",
    "kp.signals.performance": "Performance and health updates"
}


@router.post(
    "/intraday-enhanced",
    response_model=EnhancedSignalsResponse,
    summary="Enhanced intraday signals",
    operation_id="enhancedSignals_intraday",
)
async def get_enhanced_intraday_signals(
    request: EnhancedSignalsRequest,
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(require_jwt_query)
) -> EnhancedSignalsResponse:
    """
    Enhanced KP timing signals with multi-timeframe analysis and confluence detection.
    
    Features:
    - Multi-timeframe analysis across 1m, 5m, 15m, 1h, 4h, 1d intervals
    - Redis-backed caching for sub-millisecond retrieval
    - Confluence detection across multiple planetary transits
    - Performance metrics and monitoring
    
    Performance targets:
    - Cache hit: <10ms P95
    - Cache miss: <150ms P95
    - Redis failover: <300ms P95
    """
    start_time = time.time()
    tenant_id = auth_context.require_tenant()
    
    # Rate limiting check
    if not await rate_limiter.allow_qps(tenant_id, cost=2.0):  # Higher cost for enhanced signals
        raise HTTPException(
            status_code=429,
            detail="Enhanced signals rate limit exceeded",
            headers={"X-RateLimit-Limit-Type": "enhanced_signals", "Retry-After": "30"}
        )
    
    try:
        with Timer("enhanced_signals_api_request"):
            # Get enhanced signals service
            signals_service = await get_enhanced_signals_service()
            
            # Get multi-timeframe signals analysis
            t0 = time.perf_counter()
            with _tracer.start_as_current_span("enhanced_signals.analyze") as span:
                signals_data = await signals_service.get_multi_timeframe_signals(
                    date=request.date,
                    timeframes=request.timeframes,
                    planet_ids=request.planet_ids,
                    include_confluence=request.include_confluence,
                    use_cache=request.use_cache
                )
                # Best-effort per-request tracing attributes
                try:
                    compute_ms = signals_data.get("metadata", {}).get("processing_time_ms")
                    if compute_ms is None:
                        compute_ms = round((time.perf_counter() - t0) * 1000, 3)
                    set_common_attrs(
                        span,
                        cache_status="BYPASS" if not request.use_cache else "UNKNOWN",
                        compute_ms=compute_ms,
                        algo_version=os.getenv("ALGO_VERSION", "1.0.0"),
                        api_version=os.getenv("OPENAPI_VERSION", "1.1.2"),
                        norm_version=NORMALIZATION_VERSION,
                        eph_version=EPHEMERIS_DATASET_VERSION,
                    )
                except Exception:
                    pass
            
            # Convert service response to API response models
            timeframe_analyses = {}
            for tf, analysis_data in signals_data["timeframes"].items():
                # Convert signals to EnhancedSignal models
                enhanced_signals = [
                    EnhancedSignal(**signal_data) 
                    for signal_data in analysis_data["signals"]
                ]
                
                timeframe_analyses[tf] = TimeframeAnalysisModel(
                    interval_seconds=analysis_data["interval_seconds"],
                    signals=enhanced_signals,
                    signal_count=analysis_data["signal_count"],
                    last_update=analysis_data["last_update"]
                )
            
            # Convert planet analyses
            planet_analyses = {}
            for planet_id_str, planet_data in signals_data["planets"].items():
                planet_signals = [
                    EnhancedSignal(**signal_data) 
                    for signal_data in planet_data["signals"]
                ]
                
                planet_analyses[planet_id_str] = PlanetSignalAnalysis(
                    planet_id=planet_data["planet_id"],
                    signals=planet_signals,
                    signal_count=planet_data["signal_count"]
                )
            
            # Convert confluence analysis
            confluence_events = []
            for event_data in signals_data["confluence"]["events"]:
                # Convert contributing signals
                contributing_signals = [
                    EnhancedSignal(**signal_data) 
                    for signal_data in event_data["signals"]
                ]
                
                confluence_events.append({
                    **event_data,
                    "signals": contributing_signals
                })
            
            confluence_analysis = ConfluenceAnalysis(
                enabled=signals_data["confluence"]["enabled"],
                events=confluence_events,
                event_count=signals_data["confluence"]["event_count"]
            )
            
            # Add performance statistics
            perf_stats = signals_service.get_performance_stats()
            
            # Build API response
            response = EnhancedSignalsResponse(
                date=signals_data["date"],
                timeframes=timeframe_analyses,
                planets=planet_analyses,
                confluence=confluence_analysis,
                metadata=EnhancedSignalsMetadata(
                    generated_at=signals_data["metadata"]["generated_at"],
                    cache_key=signals_data["metadata"]["cache_key"],
                    processing_time_ms=signals_data["metadata"]["processing_time_ms"],
                    performance_stats=perf_stats
                )
            )
            
            # Setup streaming if requested
            if request.streaming_enabled:
                background_tasks.add_task(
                    setup_signal_streaming,
                    tenant_id,
                    request.timeframes,
                    request.planet_ids
                )
            
            # Log performance for monitoring
            total_time_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Enhanced signals request completed: "
                f"tenant={tenant_id} date={request.date} "
                f"timeframes={len(request.timeframes)} "
                f"planets={len(request.planet_ids)} "
                f"confluence={request.include_confluence} "
                f"time={total_time_ms:.2f}ms"
            )
            
            return response
            
    except Exception as e:
        logger.error(f"Enhanced signals request failed: tenant={tenant_id} error={e}")
        raise HTTPException(
            status_code=500,
            detail=f"Enhanced signals analysis failed: {str(e)}"
        )


from api.models.responses import EnhancedInvalidateResponse, EnhancedSignalsHealthResponse, Problem


@router.get(
    "/stream/enhanced",
    summary="SSE enhanced signals",
    operation_id="enhancedSignals_stream",
    responses={
        200: {"content": {"text/event-stream": {}}},
        429: {
            "model": Problem,
            "description": "Too many requests",
            "headers": {
                "Retry-After": {"schema": {"type": "integer"}},
            },
        },
    },
)
async def stream_enhanced_signals(
    timeframes: str = Query(default="1m,5m", description="Comma-separated timeframes"),
    planet_ids: str = Query(default="2", description="Comma-separated planet IDs"),
    confluence_threshold: int = Query(default=3, ge=2, le=10),
    token: str = Query(..., description="JWT stream token (EventSource)"),
    auth_context: AuthContext = Depends(require_jwt_query)
) -> EventSourceResponse:
    """
    Real-time streaming of enhanced KP timing signals via Server-Sent Events.
    
    Stream topics:
    - Enhanced signals as they are detected
    - Confluence alerts when multiple signals align
    - Performance and health updates
    
    Browser compatible with automatic reconnection support.
    """
    tenant_id = auth_context.require_tenant()
    # Stream tracing span (handshake)
    with _tracer.start_as_current_span("enhanced_signals.stream") as span:
        if span:
            try:
                span.set_attribute("tenant", tenant_id)
                span.set_attribute("timeframes", timeframes)
                span.set_attribute("planets.count", len(planet_ids.split(",")))
                span.set_attribute("confluence.threshold", confluence_threshold)
                span.set_attribute("sse.auth_method", "query")
            except Exception:
                pass
    try:
        streaming_metrics.record_sse_handshake("query", "success")
    except Exception:
        pass
    
    # Parse parameters
    try:
        timeframe_list = [tf.strip() for tf in timeframes.split(",")]
        planet_id_list = [int(p.strip()) for p in planet_ids.split(",")]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {e}")
    
    # Rate limiting for streaming connections
    if not await rate_limiter.allow_connection(tenant_id):
        raise HTTPException(
            status_code=429,
            detail="Streaming connection limit exceeded",
            headers={"Retry-After": "60"}
        )
    
    # Subscribe to enhanced signals topics
    topics = ["kp.signals.enhanced", "kp.confluence.alerts"]
    subscriptions = {}
    
    try:
        for topic in topics:
            subscriptions[topic] = await stream_manager.subscribe(topic)
        
        await rate_limiter.add_connection(tenant_id)
        
        async def enhanced_signals_generator():
            """Generate SSE events for enhanced signals"""
            sequence = 0
            last_heartbeat = time.time()
            
            try:
                while True:
                    # Check for new messages on any topic
                    for topic, queue in subscriptions.items():
                        try:
                            # Non-blocking check for messages
                            message = await asyncio.wait_for(
                                stream_manager.next_message(queue, heartbeat_secs=0),
                                timeout=0.1
                            )
                            
                            if message:
                                # Parse and filter message
                                try:
                                    msg_data = json.loads(message)
                                    
                                    # Filter by requested parameters
                                    if should_send_message(msg_data, timeframe_list, planet_id_list, confluence_threshold):
                                        sequence += 1
                                        
                                        yield {
                                            "id": str(sequence),
                                            "event": "enhanced_signal",
                                            "data": json.dumps({
                                                "sequence": sequence,
                                                "topic": topic,
                                                "timestamp": datetime.utcnow().isoformat(),
                                                "tenant_id": tenant_id,
                                                "data": msg_data
                                            })
                                        }
                                        
                                except json.JSONDecodeError:
                                    logger.warning(f"Invalid JSON in stream message: {message}")
                                    
                        except asyncio.TimeoutError:
                            # No message available on this topic
                            continue
                    
                    # Send periodic heartbeats
                    current_time = time.time()
                    if current_time - last_heartbeat > 30:  # Every 30 seconds
                        yield {
                            "id": str(sequence),
                            "event": "heartbeat", 
                            "data": json.dumps({
                                "timestamp": datetime.utcnow().isoformat(),
                                "active_topics": list(topics),
                                "connection_duration": current_time - start_time
                            })
                        }
                        last_heartbeat = current_time
                    
                    # Small delay to prevent tight loop
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in enhanced signals stream: {e}")
                yield {
                    "id": str(sequence + 1),
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
            finally:
                # Cleanup subscriptions
                for topic, queue in subscriptions.items():
                    await stream_manager.unsubscribe(topic, queue)
                await rate_limiter.remove_connection(tenant_id)
        
        return EventSourceResponse(
            enhanced_signals_generator(),
            headers={
                "Cache-Control": "no-cache, no-store, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "X-Stream-Type": "enhanced_signals",
                "X-RateLimit-Tenant": tenant_id
            }
        )
        
    except Exception as e:
        # Cleanup on error
        for topic, queue in subscriptions.items():
            try:
                await stream_manager.unsubscribe(topic, queue)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to setup signal streaming: {e}")


@router.get(
    "/performance",
    response_model=PerformanceStatsResponse,
    summary="Enhanced performance stats",
    operation_id="enhancedSignals_performance",
)
async def get_performance_stats(
    auth_context: AuthContext = Depends(require_jwt_query)
) -> PerformanceStatsResponse:
    """
    Get performance statistics for the enhanced signals service.
    
    Includes:
    - Request/response metrics
    - Cache performance
    - Redis availability
    - Service health indicators
    """
    tenant_id = auth_context.require_tenant()
    
    try:
        signals_service = await get_enhanced_signals_service()
        stats = signals_service.get_performance_stats()
        
        # Determine service health
        health = "healthy"
        if stats["p95_response_time_ms"] > 200:  # Above 200ms P95
            health = "degraded"
        elif stats["cache_hit_rate"] < 50:  # Below 50% cache hit rate
            health = "degraded"
        
        response = PerformanceStatsResponse(
            total_requests=stats["total_requests"],
            cache_hits=stats["cache_hits"], 
            cache_misses=stats["cache_misses"],
            cache_hit_rate=stats["cache_hit_rate"],
            avg_response_time_ms=stats["avg_response_time_ms"],
            p95_response_time_ms=stats["p95_response_time_ms"],
            redis_available=signals_service.redis_manager is not None,
            service_health=health
        )
        
        logger.info(f"Performance stats requested by tenant {tenant_id}: health={health}")
        return response
        
    except Exception as e:
        logger.error(f"Failed to get performance stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance statistics")


@router.post(
    "/invalidate-cache",
    response_model=EnhancedInvalidateResponse,
    summary="Invalidate signal cache",
    operation_id="enhancedSignals_invalidateCache",
)
async def invalidate_signal_cache(
    date: str = Query(..., description="Date to invalidate (YYYY-MM-DD)"),
    planet_id: int = Query(None, description="Specific planet ID to invalidate"),
    auth_context: AuthContext = Depends(require_jwt_query)
) -> EnhancedInvalidateResponse:
    """
    Manually invalidate signal cache for a specific date/planet.
    
    Useful for:
    - Forcing recalculation after astronomical data updates
    - Cache corruption recovery
    - Testing and development
    """
    tenant_id = auth_context.require_tenant()
    
    # Check if user has admin scope (implement based on your auth system)
    # For now, allow all authenticated users
    
    try:
        signals_service = await get_enhanced_signals_service()
        
        if planet_id:
            # Invalidate for specific planet
            change_time = datetime.strptime(date, "%Y-%m-%d")
            await signals_service.invalidate_cache_for_planet_changes(planet_id, change_time)
            
            return {
                "status": "success",
                "invalidated": f"planet {planet_id} on {date}",
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            # Invalidate all for date (would need implementation)
            return {
                "status": "success", 
                "message": "Full date invalidation not yet implemented",
                "date": date,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache invalidation failed: {str(e)}")


@router.get(
    "/health",
    response_model=EnhancedSignalsHealthResponse,
    summary="Enhanced signals health",
    operation_id="enhancedSignals_health",
)
async def enhanced_signals_health() -> EnhancedSignalsHealthResponse:
    """
    Health check for enhanced signals service.
    
    Returns service status and key metrics without authentication.
    """
    try:
        signals_service = await get_enhanced_signals_service()
        stats = signals_service.get_performance_stats()
        
        # Basic health indicators
        healthy = (
            stats["p95_response_time_ms"] < 300 and  # P95 under 300ms
            (stats["total_requests"] == 0 or stats["cache_hit_rate"] > 20)  # Cache working or no requests yet
        )
        
        return {
            "status": "healthy" if healthy else "degraded",
            "service": "enhanced_kp_signals",
            "version": "2.0.0",
            "redis_available": signals_service.redis_manager is not None,
            "metrics": {
                "total_requests": stats["total_requests"],
                "p95_response_time_ms": stats["p95_response_time_ms"],
                "cache_hit_rate": round(stats["cache_hit_rate"], 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "enhanced_kp_signals",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Helper functions

def should_send_message(msg_data: Dict[str, Any], 
                       timeframes: list[str], 
                       planet_ids: list[int],
                       confluence_threshold: int) -> bool:
    """
    Determine if a stream message should be sent based on filters.
    """
    try:
        # Check timeframe filter
        msg_timeframe = msg_data.get("timeframe")
        if msg_timeframe and msg_timeframe not in timeframes:
            return False
        
        # Check planet filter
        msg_planet_id = msg_data.get("planet_id")
        if msg_planet_id and msg_planet_id not in planet_ids:
            return False
        
        # Check confluence threshold
        if msg_data.get("type") == "confluence":
            signal_count = msg_data.get("signal_count", 0)
            if signal_count < confluence_threshold:
                return False
        
        return True
        
    except Exception:
        # On error, send the message (fail open)
        return True


async def setup_signal_streaming(tenant_id: str, 
                                timeframes: list[str], 
                                planet_ids: list[int]) -> None:
    """
    Background task to setup signal streaming for a tenant.
    """
    try:
        logger.info(
            f"Setting up signal streaming: tenant={tenant_id} "
            f"timeframes={timeframes} planets={planet_ids}"
        )
        
        # Implementation would depend on your streaming architecture
        # This is a placeholder for additional streaming setup
        
    except Exception as e:
        logger.error(f"Failed to setup signal streaming for {tenant_id}: {e}")


# Performance monitoring middleware would be added at the router level
# This ensures all endpoints are monitored consistently
