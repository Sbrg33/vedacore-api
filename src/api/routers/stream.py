"""
SSE (Server-Sent Events) router for VedaCore streaming.

Browser-compatible streaming with:
- Query parameter JWT authentication (EventSource limitation)
- Anti-buffering headers for nginx/Cloudflare compatibility
- Rate limiting with tenant-based quotas
- Per-client queue management with graceful cleanup
- SSE resumption support with event IDs

Critical PM requirements:
- Browser EventSource cannot send Authorization headers
- Must use query parameter authentication
- Anti-buffering headers prevent proxy buffering issues
- Rate limiting enforced at connection and message levels
"""

from __future__ import annotations

import json
import os

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from sse_starlette.sse import EventSourceResponse

from ..services.auth import AuthContext, require_jwt_query
from api.models.responses import Problem
from ..services.rate_limiter import log_rate_limit_violation, rate_limiter
from ..services.stream_manager import stream_manager

# Import metrics for monitoring
try:
    from ..services.metrics import streaming_metrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

router = APIRouter(prefix="/stream", tags=["stream"], responses=DEFAULT_ERROR_RESPONSES)

# Dev-only publishing token (disabled in production)
DEV_PUBLISH_ENABLED = os.getenv("STREAM_DEV_PUBLISH_ENABLED", "true").lower() == "true"
DEV_PUBLISH_TOKEN = os.getenv("STREAM_DEV_PUBLISH_TOKEN", "")

# JWT-protected publisher system (production-ready)
PUBLISHER_ENABLED = os.getenv("STREAM_PUBLISHER_ENABLED", "false").lower() == "true"
MOON_PUBLISHER_ENABLED = os.getenv("MOON_PUBLISHER_ENABLED", "false").lower() == "true"
ALLOWED_TOPICS = (
    set(os.getenv("STREAM_ALLOWED_TOPICS", "").split(","))
    if os.getenv("STREAM_ALLOWED_TOPICS")
    else {"kp.v1.moon.chain"}
)


@router.get(
    "/{topic}",
    summary="SSE stream for a topic",
    operation_id="stream_sse_topic",
    responses={
        200: {"content": {"text/event-stream": {}}},
        429: {
            "model": Problem,
            "description": "Too many requests",
            "headers": {
                "X-RateLimit-Limit": {"schema": {"type": "integer"}},
                "X-RateLimit-Remaining": {"schema": {"type": "integer"}},
                "Retry-After": {"schema": {"type": "integer", "description": "Seconds"}},
            },
        },
    },
)
async def stream_topic(
    topic: str,
    request: Request,
    token: str = Query(
        ..., description="JWT stream token (query param)"
    ),
    auth_context: AuthContext = Depends(require_jwt_query),  # Browser-compatible auth
    last_event_id: str | None = Header(None, convert_underscores=False),
) -> EventSourceResponse:
    """
    SSE endpoint for real-time topic streaming.

    CRITICAL: Uses query parameter authentication because EventSource API
    cannot send Authorization headers in browsers.

    Usage: GET /stream/kp.v1.moon.chain?token=jwt_token_here
    """
    tenant_id = auth_context.require_tenant()

    # Check connection limits first (PM requirement)
    if not await rate_limiter.allow_connection(tenant_id):
        await log_rate_limit_violation(
            tenant_id=tenant_id, limit_type="connection", endpoint=f"/stream/{topic}"
        )
        raise HTTPException(
            status_code=429,
            detail="Connection limit exceeded",
            headers={"X-RateLimit-Limit-Type": "connections", "Retry-After": "60"},
        )

    # Check QPS limits for subscription
    if not await rate_limiter.allow_qps(tenant_id, cost=1.0):
        await log_rate_limit_violation(
            tenant_id=tenant_id, limit_type="qps", endpoint=f"/stream/{topic}"
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"X-RateLimit-Limit-Type": "qps", "Retry-After": "60"},
        )

    # Subscribe to topic and track connection
    q = await stream_manager.subscribe(topic)
    await rate_limiter.add_connection(tenant_id)

    # Record connection metrics
    import time

    connection_start = time.time()
    messages_delivered = 0
    if METRICS_AVAILABLE:
        streaming_metrics.record_connection(tenant_id, topic, "sse")

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        """Generate SSE events with proper cleanup."""
        try:
            # Hint client about retry interval
            yield {"retry": 15000}
            # Replay backlog if Last-Event-ID provided
            if last_event_id:
                try:
                    last_seq = int(str(last_event_id).strip())
                except ValueError:
                    last_seq = -1
                try:
                    backlog = await stream_manager.replay_since(topic, last_seq)
                    for raw in backlog:
                        try:
                            msg_obj = json.loads(raw)
                        except Exception:
                            continue
                        yield {
                            "id": str(msg_obj.get("seq", "")),
                            "event": str(msg_obj.get("event", "update")),
                            "data": raw,
                        }
                except Exception:
                    pass

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                # Get next message (includes heartbeats)
                data = await stream_manager.next_message(q, heartbeat_secs=15)

                # Extract sequence number for SSE resumption (PM requirement)
                try:
                    msg_obj = json.loads(data)
                    event_id = str(msg_obj.get("seq", ""))
                    event_type = str(msg_obj.get("event", "update"))
                except (json.JSONDecodeError, KeyError):
                    event_id = ""
                    event_type = "update"

                # Yield SSE event with resumption support
                yield {
                    "id": event_id,
                    "event": event_type,
                    "data": data,  # JSON payload as string
                }

                # Count delivered messages
                nonlocal messages_delivered
                messages_delivered += 1

        except Exception as e:
            # Log error but don't break the stream
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error in SSE stream for {tenant_id}/{topic}: {e}")
        finally:
            # Record connection completion metrics
            if METRICS_AVAILABLE:
                connection_duration = time.time() - connection_start
                streaming_metrics.record_connection_completed(
                    tenant_id, topic, "sse", connection_duration, messages_delivered
                )

            # Always clean up subscription and connection tracking
            await stream_manager.unsubscribe(topic, q)
            await rate_limiter.remove_connection(tenant_id)

    # Return EventSource response with anti-buffering headers (PM-critical)
    return EventSourceResponse(
        event_generator(),
        ping=15000,  # 15-second ping to prevent timeouts
        headers={
            # CRITICAL: SSE and proxy headers (PM requirements)
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-store, no-transform",
            "X-Accel-Buffering": "no",  # nginx anti-buffering
            "Connection": "keep-alive",  # Keep connection alive
            # PM Security headers - prevent token leakage
            "Referrer-Policy": "no-referrer",  # Prevent JWT token leakage via Referer header
            # CORS headers for browser compatibility
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            # Rate limiting info
            "X-RateLimit-Tenant": tenant_id,
            "X-RateLimit-Topic": topic,
        },
    )


from api.models.responses import StreamStatsResponse, StreamHealthResponse


@router.get("/_stats", response_model=StreamStatsResponse, operation_id="stream_stats")
async def stream_stats(
    request: Request, auth_context: AuthContext = Depends(require_jwt_query)
) -> StreamStatsResponse:
    """
    Get streaming statistics for debugging and monitoring.

    CRITICAL: This is a plain JSON endpoint, NOT a stream.
    Requires authentication but accessible to all tenants.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Log request received for debugging
    request_id = request.headers.get("x-request-id", "unknown")
    tenant_id = auth_context.require_tenant()
    logger.info(f"Stats request received: request_id={request_id} tenant={tenant_id}")

    try:
        # Get general stats (no sensitive data)
        stream_stats = stream_manager.stats()
        rate_stats = rate_limiter.get_metrics()

        # Get tenant-specific stats
        tenant_status = await rate_limiter.get_tenant_status(tenant_id)

        # Get Moon publisher stats if available
        publisher_stats = {}
        try:
            from ..services.moon_publisher import moon_publisher

            publisher_stats = moon_publisher.get_stats()
        except Exception:
            pass  # Moon publisher not available

        response_data = {
            "stream_manager": stream_stats,
            "rate_limiter": rate_stats,
            "tenant_status": tenant_status,
            "moon_publisher": publisher_stats,
            "timestamp": stream_manager._ts(),
            "request_id": request_id,
        }

        # Log successful response
        logger.info(
            f"Stats response prepared: request_id={request_id} tenant={tenant_id}"
        )
        return response_data

    except Exception as e:
        logger.error(
            f"Stats request failed: request_id={request_id} tenant={tenant_id} error={e}"
        )
        raise


_RESUME_EXAMPLE = {
    "topic": "kp.v1.moon.chain",
    "redis": {"size": 128, "min_seq": 1012, "max_seq": 1140},
    "memory": {"size": 16},
    "timestamp": "2025-09-03T12:34:56Z",
}

@router.get(
    "/_resume",
    summary="Resume store stats",
    description="Requires admin role or 'stream:debug' scope.",
    operation_id="stream_resumeStats",
    responses={
        200: {
            "description": "Resume stats",
            "content": {"application/json": {"example": _RESUME_EXAMPLE}},
        },
        401: {"model": Problem, "description": "Unauthorized (missing/invalid token)"},
        403: {"model": Problem, "description": "Forbidden (admin or stream:debug required)"},
    },
)
async def resume_stats(
    topic: str = Query(..., description="Topic name"),
    auth_context: AuthContext = Depends(require_jwt_query),
) -> dict[str, Any]:
    """Return Redis + memory resume stats for a topic (auth required)."""
    from ..services.stream_manager import stream_manager

    # Admin or stream:debug scope required
    role = (auth_context.role or "").lower() if hasattr(auth_context, "role") else ""
    scopes = (auth_context.scopes or "") if hasattr(auth_context, "scopes") else ""
    if role not in ("admin", "owner") and "stream:debug" not in scopes.split():
        # RFC7807 Problem body
        from fastapi.responses import JSONResponse
        problem = Problem(
            type="https://api.vedacore.io/problems/forbidden",
            title="Forbidden",
            status=403,
            detail="Admin role or 'stream:debug' scope required",
            code="FORBIDDEN_DEBUG",
        )
        return JSONResponse(status_code=403, content=problem.model_dump())

    stats = await stream_manager.resume_stats(topic)
    return {
        "topic": topic,
        "redis": stats.get("redis", {}),
        "memory": stats.get("memory", {}),
        "timestamp": stream_manager._ts(),
    }


_TOPICS_EXAMPLE = {
    "topics": [
        {
            "topic": "kp.v1.moon.chain",
            "subscribers": 3,
            "resume": {"redis": {"size": 128, "min_seq": 2001, "max_seq": 2050}, "memory": {"size": 16}},
        }
    ],
    "published": 1024,
    "dropped": 0,
    "timestamp": "2025-09-03T12:34:56Z",
}

@router.get(
    "/_topics",
    summary="List topics with subscribers and resume stats",
    description="Requires admin role or 'stream:debug' scope.",
    operation_id="stream_topics_debug",
    responses={
        200: {
            "description": "Topic stats",
            "content": {"application/json": {"example": _TOPICS_EXAMPLE}},
        },
        401: {"model": Problem, "description": "Unauthorized (missing/invalid token)"},
        403: {"model": Problem, "description": "Forbidden (admin or stream:debug required)"},
    },
)
async def list_topics_debug(
    auth_context: AuthContext = Depends(require_jwt_query),
    include_resume: bool = Query(True, description="Include resume stats"),
) -> dict[str, Any]:
    """Debug endpoint listing current topics with subscriber counts.

    Requires a JWT in query param. If include_resume=true, adds Redis/memory
    resume stats per topic (can be slower on large sets).
    """
    from ..services.stream_manager import stream_manager

    # Admin or stream:debug scope required
    role = (auth_context.role or "").lower() if hasattr(auth_context, "role") else ""
    scopes = (auth_context.scopes or "") if hasattr(auth_context, "scopes") else ""
    if role not in ("admin", "owner") and "stream:debug" not in scopes.split():
        from fastapi.responses import JSONResponse
        problem = Problem(
            type="https://api.vedacore.io/problems/forbidden",
            title="Forbidden",
            status=403,
            detail="Admin role or 'stream:debug' scope required",
            code="FORBIDDEN_DEBUG",
        )
        return JSONResponse(status_code=403, content=problem.model_dump())

    stats = stream_manager.stats()
    topics = []
    for topic, subs in stats.get("topics", {}).items():
        entry = {"topic": topic, "subscribers": subs}
        if include_resume:
            entry["resume"] = await stream_manager.resume_stats(topic)
        topics.append(entry)
    return {
        "topics": topics,
        "published": stats.get("published", 0),
        "dropped": stats.get("dropped", 0),
        "timestamp": stream_manager._ts(),
    }


@router.post(
    "/_dev_publish/{topic}",
    summary="Dev publish",
    operation_id="stream_devPublish",
)
async def dev_publish(
    topic: str,
    payload: dict[str, Any],
    dev_token: str | None = Query(None, alias="token"),
) -> dict[str, Any]:
    """
    DEV ONLY: Publish a test message to a topic.

    CRITICAL: This endpoint is gated by STREAM_DEV_PUBLISH_TOKEN and
    disabled in production via STREAM_DEV_PUBLISH_ENABLED=false.

    Usage: POST /_dev_publish/kp.v1.moon.chain?token=dev_secret
    Body: {"degree": 123.45, "speed": 13.06, ...}
    """
    # Check if dev publishing is enabled
    if not DEV_PUBLISH_ENABLED:
        raise HTTPException(
            status_code=404, detail="Development endpoints disabled in production"
        )

    # Validate dev token
    if not DEV_PUBLISH_TOKEN or dev_token != DEV_PUBLISH_TOKEN:
        raise HTTPException(
            status_code=403, detail="Invalid or missing development token"
        )

    # Payload size clamping (PM requirement: prevent HOL blocking)
    payload_size = len(json.dumps(payload))
    if payload_size > 65536:  # 64KB limit
        raise HTTPException(
            status_code=413,
            detail=f"Payload too large: {payload_size} bytes (max 64KB)",
        )

    # Publish to topic
    try:
        await stream_manager.publish(topic, payload, event="update", v=1)

        # Get current subscriber count for this topic
        stats = stream_manager.stats()
        subscriber_count = stats.get("topics", {}).get(topic, 0)

        return {
            "ok": True,
            "topic": topic,
            "payload_size": payload_size,
            "subscribers": subscriber_count,
            "timestamp": stream_manager._ts(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish message: {e}")


@router.post(
    "/publish/{topic}",
    summary="JWT publish",
    operation_id="stream_jwtPublish",
)
async def jwt_publish(
    topic: str,
    payload: dict[str, Any],
    request: Request,
    auth_context: AuthContext = Depends(require_jwt_query),
) -> dict[str, Any]:
    """
    JWT-protected publish endpoint for production streaming.

    CRITICAL: Requires 'stream:publish' scope and topic ACL validation.
    This replaces dev-publish for production use with proper auth.

    Usage: POST /stream/publish/kp.v1.moon.chain?token=jwt_with_publish_scope
    Body: {"degree": 123.45, "speed": 13.06, ...}
    """
    import logging

    logger = logging.getLogger(__name__)

    # Check if publisher system is enabled
    if not PUBLISHER_ENABLED:
        raise HTTPException(
            status_code=404,
            detail="Publisher endpoints disabled - set STREAM_PUBLISHER_ENABLED=true",
        )

    tenant_id = auth_context.require_tenant()
    request_id = request.headers.get("x-request-id", "unknown")

    # Log publish attempt
    logger.info(
        f"Publish request: topic={topic} tenant={tenant_id} request_id={request_id}"
    )

    # Validate topic ACLs (PM requirement: avoid wildcard publish)
    if topic not in ALLOWED_TOPICS:
        logger.warning(
            f"Publish denied - topic not allowed: topic={topic} tenant={tenant_id}"
        )
        raise HTTPException(
            status_code=403,
            detail=f"Topic '{topic}' not in allowed list. Allowed: {sorted(ALLOWED_TOPICS)}",
        )

    # Check for stream:publish scope (PM requirement)
    # Note: This assumes auth_context has scope validation - adjust as needed
    if not hasattr(auth_context, "has_scope") or not auth_context.has_scope(
        "stream:publish"
    ):
        logger.warning(
            f"Publish denied - missing scope: tenant={tenant_id} topic={topic}"
        )
        raise HTTPException(
            status_code=403, detail="Missing required scope: stream:publish"
        )

    # Rate limiting for publish API (PM requirement)
    if not await rate_limiter.allow_qps(tenant_id, cost=2.0):  # Higher cost for publish
        await log_rate_limit_violation(
            tenant_id=tenant_id,
            limit_type="publish_qps",
            endpoint=f"/stream/publish/{topic}",
        )
        raise HTTPException(
            status_code=429,
            detail="Publish rate limit exceeded",
            headers={"X-RateLimit-Limit-Type": "publish_qps", "Retry-After": "60"},
        )

    # Payload size validation (same as dev endpoint)
    payload_size = len(json.dumps(payload))
    if payload_size > 65536:  # 64KB limit
        raise HTTPException(
            status_code=413,
            detail=f"Payload too large: {payload_size} bytes (max 64KB)",
        )

    # Publish to topic
    try:
        await stream_manager.publish(topic, payload, event="update", v=1)

        # Get current subscriber count for this topic
        stats = stream_manager.stats()
        subscriber_count = stats.get("topics", {}).get(topic, 0)

        # Log successful publish
        logger.info(
            f"Published successfully: topic={topic} tenant={tenant_id} size={payload_size} subscribers={subscriber_count}"
        )

        return {
            "ok": True,
            "topic": topic,
            "payload_size": payload_size,
            "subscribers": subscriber_count,
            "publisher": "jwt_protected",
            "tenant_id": tenant_id,
            "request_id": request_id,
            "timestamp": stream_manager._ts(),
        }

    except Exception as e:
        logger.error(f"Publish failed: topic={topic} tenant={tenant_id} error={e}")
        raise HTTPException(status_code=500, detail=f"Failed to publish message: {e}")


@router.get("/_health", response_model=StreamHealthResponse, operation_id="stream_health")
async def stream_health() -> StreamHealthResponse:
    """
    Health check endpoint for streaming service.

    No authentication required for health checks.
    """
    try:
        # Test stream manager functionality
        stats = stream_manager.stats()
        rate_stats = rate_limiter.get_metrics()

        # Basic health indicators
        healthy = (
            isinstance(stats.get("published", 0), int)
            and isinstance(stats.get("subscribers", 0), int)
            and isinstance(rate_stats.get("total_checks", 0), int)
        )

        return {
            "status": "healthy" if healthy else "unhealthy",
            "service": "vedacore_streaming",
            "version": "1.0.0",
            "stats": {
                "published_messages": stats.get("published", 0),
                "active_subscribers": stats.get("subscribers", 0),
                "active_topics": len(stats.get("topics", {})),
                "rate_checks": rate_stats.get("total_checks", 0),
            },
            "timestamp": stream_manager._ts(),
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": stream_manager._ts(),
        }
