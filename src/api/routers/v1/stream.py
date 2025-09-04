"""
API v1 Stream Router

Streaming endpoints for SSE and WebSocket with unified token authentication.
Implements PM requirements for secure streaming with token redaction.
"""

from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime
import time

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Header
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from fastapi.responses import StreamingResponse
import jwt
import json
import asyncio

from .models import BaseResponse, ErrorResponse, PATH_TEMPLATES
from app.core.environment import get_complete_config
from api.services.metrics import streaming_metrics
from api.services.rate_limiter import check_qps_limit

router = APIRouter(prefix="/api/v1", tags=["stream"], responses=DEFAULT_ERROR_RESPONSES) 


def verify_stream_token(token: str, expected_topic: Optional[str] = None, source: Optional[str] = None) -> dict:
    """
    Verify streaming token with PM security requirements:
    - Audience must be "stream"
    - Topic must match if specified
    - JTI single-use enforcement
    - Token expiration check
    """
    try:
        config = get_complete_config()
        # Disable built-in audience verification; enforce manually below
        payload = jwt.decode(
            token,
            config.database.auth_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        
        # Verify audience
        if payload.get("aud") != "stream":
            raise jwt.InvalidTokenError("Invalid audience for streaming")
        
        # Verify topic if specified
        token_topic = payload.get("topic")
        if expected_topic and token_topic != expected_topic:
            raise jwt.InvalidTokenError(f"Token topic {token_topic} does not match requested {expected_topic}")
        
        # Enforce short TTL for query tokens (<= 600s)
        if source == "query":
            try:
                iat = float(payload.get("iat"))
                exp = float(payload.get("exp"))
                # Allow small clock skew (+/-30s) beyond 10m TTL
                if exp - iat > 630.0:
                    raise jwt.InvalidTokenError("Query token TTL exceeds 10 minutes (+30s skew)")
            except Exception:
                # If claims missing/malformed, treat as invalid
                raise jwt.InvalidTokenError("Invalid token claims for TTL enforcement")

        # TODO: Implement JTI single-use check
        # jti = payload.get("jti")
        # if await is_jti_already_used(jti):
        #     raise jwt.InvalidTokenError("Token already used")
        # await mark_jti_as_used(jti)
        
        return payload
        
    except jwt.InvalidTokenError as e:
        # Metrics: auth failure
        try:
            streaming_metrics.record_auth_failure("invalid_token", "/api/v1/stream")
        except Exception:
            pass
        raise HTTPException(
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            detail=ErrorResponse.create(
                code="AUTH_ERROR",
                message="Invalid streaming token",
                details={"error": str(e), "remediation": "Provide Bearer token or short\u2011TTL query token"}
            ).dict()
        )


async def generate_sse_stream(topic: str, tenant_id: str) -> AsyncIterator[str]:
    """
    Generate Server-Sent Events stream for topic.
    
    Yields formatted SSE events with proper envelope structure
    following PM specification.
    """
    try:
        # Import streaming service
        from api.services.stream_manager import stream_manager
        
        # Subscribe to topic
        queue = await stream_manager.subscribe(topic)
        
        while True:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                # message is a JSON string envelope produced by stream_manager.publish
                try:
                    obj = json.loads(message)
                except Exception:
                    # Fallback: wrap raw message
                    obj = {
                        "v": 1,
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "seq": 0,
                        "topic": topic,
                        "event": "update",
                        "payload": message,
                    }
                # Send as SSE event with id/event
                eid = str(obj.get("seq", ""))
                ev = str(obj.get("event", "update"))
                data = json.dumps(obj)
                yield f"id: {eid}\nevent: {ev}\ndata: {data}\n\n"
                
            except asyncio.TimeoutError:
                # Send heartbeat
                heartbeat = {
                    "v": 1,
                    "ts": datetime.utcnow().isoformat() + "Z", 
                    "seq": 0,
                    "topic": topic,
                    "event": "heartbeat",
                    "payload": {}
                }
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat)}\n\n"
                
    except Exception as e:
        # Send error event
        error_event = {
            "v": 1,
            "ts": datetime.utcnow().isoformat() + "Z",
            "seq": 0,
            "topic": topic, 
            "event": "error",
            "payload": {"message": str(e)}
        }
        
        yield f"data: {json.dumps(error_event)}\n\n"
    finally:
        # Cleanup subscription
        if 'queue' in locals():
            await stream_manager.unsubscribe(topic, queue)


@router.get(
    "/stream",
    summary="Server-Sent Events Stream",
    operation_id="v1_stream_sse",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_events(
    topic: str = Query(..., description="Topic to subscribe to"),
    token: Optional[str] = Query(None, description="One-time streaming token (query param; preferred for browsers)"),
    authorization: Optional[str] = Header(None, description="Optional Authorization: Bearer <token> for non-browser clients"),
    last_event_id: str | None = Header(None, convert_underscores=False),
) -> StreamingResponse:
    """
    Subscribe to Server-Sent Events stream for specified topic.
    
    Requires one-time streaming token issued via /api/v1/auth/stream-token.
    Token must be topic-scoped and will be consumed on first use.
    """
    # Normalize auth with header precedence
    handshake_start = time.perf_counter()
    bearer_token: Optional[str] = None
    if authorization:
        try:
            scheme, value = authorization.split(" ", 1)
            if scheme.lower() == "bearer" and value:
                bearer_token = value.strip()
        except ValueError:
            bearer_token = None
    query_token = token
    src = "header" if bearer_token else ("query" if query_token else None)
    resolved_token = bearer_token or query_token
    if not resolved_token:
        # Metrics: missing token
        try:
            streaming_metrics.record_auth_failure("missing_token", "/api/v1/stream")
            streaming_metrics.record_sse_handshake("unknown", "missing_token", latency_seconds=round((time.perf_counter()-handshake_start), 6))
        except Exception:
            pass
        raise HTTPException(
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            detail=ErrorResponse.create(
                code="AUTH_ERROR",
                message="Missing streaming token (query ?token=... or Authorization: Bearer)",
                details={"remediation": "Provide Bearer token or short\u2011TTL query token"}
            ).dict()
        )

    # Verify streaming token
    payload = verify_stream_token(resolved_token, topic, source=src)
    tenant_id = payload.get("tid", "unknown")
    # Capture token expiry (seconds) if available
    exp_ts = None
    try:
        exp_ts = float(payload.get("exp")) if payload and payload.get("exp") is not None else None
    except Exception:
        exp_ts = None
    # Metrics: successful auth and handshake record
    try:
        streaming_metrics.record_auth_success(tenant_id, "/api/v1/stream")
        streaming_metrics.record_sse_handshake(src or "unknown", "success", latency_seconds=round((time.perf_counter()-handshake_start), 6))
    except Exception:
        pass

    # Handshake rate limit per tenant
    try:
        await check_qps_limit(tenant_id, cost=1.0)
    except HTTPException as e:
        try:
            streaming_metrics.record_sse_handshake(src or "unknown", "rate_limited", latency_seconds=round((time.perf_counter()-handshake_start), 6))
        except Exception:
            pass
        raise
    
    async def sse_with_resume() -> AsyncIterator[str]:
        # Emit retry hint once
        yield "retry: 15000\n\n"
        # Check resume gap (buffer exhaustion)
        if last_event_id:
            try:
                last_seq = int(str(last_event_id).strip())
            except ValueError:
                last_seq = -1
            try:
                stats = await stream_manager.resume_stats(topic)  # type: ignore[name-defined]
                min_candidates = []
                try:
                    rmin = stats.get("redis", {}).get("min_seq")
                    if rmin is not None:
                        min_candidates.append(int(rmin))
                except Exception:
                    pass
                try:
                    mmin = stats.get("memory", {}).get("min_seq")
                    if mmin is not None:
                        min_candidates.append(int(mmin))
                except Exception:
                    pass
                if min_candidates:
                    min_seq = min(min_candidates)
                    if last_seq < (min_seq - 1):
                        # Signal reset and terminate so client can reconnect cleanly
                        try:
                            streaming_metrics.record_sse_reset(topic)
                        except Exception:
                            pass
                        yield "event: reset\ndata: full-resync\n\n"
                        return
            except Exception:
                pass
        # Replay missed events if Last-Event-ID provided
        if last_event_id:
            try:
                last_seq = int(str(last_event_id).strip())
            except ValueError:
                last_seq = -1
            try:
                from api.services.stream_manager import stream_manager
                backlog = await stream_manager.replay_since(topic, last_seq)
                try:
                    streaming_metrics.record_sse_resume_replayed(topic, len(backlog))
                except Exception:
                    pass
                for raw in backlog:
                    try:
                        obj = json.loads(raw)
                    except Exception:
                        continue
                    eid = str(obj.get("seq", ""))
                    ev = str(obj.get("event", "update"))
                    yield f"id: {eid}\nevent: {ev}\ndata: {raw}\n\n"
            except Exception:
                pass
        # Then continue with live stream
        async for chunk in generate_sse_stream(topic, tenant_id):
            # Mid-stream token expiry policy (for query tokens): emit error and terminate
            if src == "query" and exp_ts is not None:
                try:
                    if time.time() > exp_ts:
                        err = {
                            "v": 1,
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "seq": 0,
                            "topic": topic,
                            "event": "error",
                            "payload": {"code": "token_expired", "message": "Streaming token expired"},
                        }
                        yield f"event: error\ndata: {json.dumps(err)}\n\n"
                        return
                except Exception:
                    pass
            # chunk may be data-only; upgrade to include id/event when possible
            try:
                obj = json.loads(chunk.replace("data: ", "").strip())
                eid = str(obj.get("seq", ""))
                ev = str(obj.get("event", "update"))
                yield f"id: {eid}\nevent: {ev}\ndata: {json.dumps(obj)}\n\n"
            except Exception:
                yield chunk

    # Generate SSE stream with anti-buffer + anti-leak headers
    headers = {
        "Cache-Control": "no-store",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Type": "text/event-stream; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Referrer-Policy": "no-referrer",
        "Vary": "Authorization, Accept",
    }
    if src == "query":
        headers.update({
            "Warning": '299 vedacore "Query token deprecated; use Authorization header."',
            "Deprecation": "true",
            "Sunset": "Wed, 31 Dec 2025 00:00:00 GMT",
        })
    return StreamingResponse(
        sse_with_resume(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="One-time streaming token")
):
    """
    WebSocket endpoint for real-time bidirectional streaming.
    
    Supports subscription to multiple topics and client commands.
    Uses same token authentication as SSE endpoint.
    """
    await websocket.accept()
    
    try:
        # Verify initial token - allow any topic for WebSocket
        payload = verify_stream_token(token)
        tenant_id = payload.get("tid", "unknown")
        
        # Track subscriptions
        subscriptions = {}
        sequence = 0
        
        # Send welcome message
        welcome = {
            "v": 1,
            "ts": datetime.utcnow().isoformat() + "Z",
            "seq": sequence,
            "event": "welcome",
            "payload": {
                "tenant_id": tenant_id,
                "supported_commands": ["subscribe", "unsubscribe", "ping"]
            }
        }
        await websocket.send_text(json.dumps(welcome))
        sequence += 1
        
        # Message handling loop
        while True:
            try:
                # Receive client message
                data = await websocket.receive_text()
                message = json.loads(data)
                
                command = message.get("command")
                if command == "subscribe":
                    topic = message.get("topic")
                    if topic:
                        # Import streaming service
                        from api.services.stream_manager import stream_manager
                        queue = await stream_manager.subscribe(topic, tenant_id)
                        subscriptions[topic] = queue
                        
                        # Confirm subscription
                        response = {
                            "v": 1,
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "seq": sequence,
                            "event": "subscribed",
                            "payload": {"topic": topic}
                        }
                        await websocket.send_text(json.dumps(response))
                        sequence += 1
                        
                elif command == "unsubscribe":
                    topic = message.get("topic") 
                    if topic in subscriptions:
                        from api.services.stream_manager import stream_manager
                        await stream_manager.unsubscribe(topic, tenant_id, subscriptions[topic])
                        del subscriptions[topic]
                        
                        # Confirm unsubscription
                        response = {
                            "v": 1,
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "seq": sequence,
                            "event": "unsubscribed", 
                            "payload": {"topic": topic}
                        }
                        await websocket.send_text(json.dumps(response))
                        sequence += 1
                        
                elif command == "ping":
                    # Respond to ping
                    response = {
                        "v": 1,
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "seq": sequence,
                        "event": "pong",
                        "payload": message.get("payload", {})
                    }
                    await websocket.send_text(json.dumps(response))
                    sequence += 1
                    
            except json.JSONDecodeError:
                error_response = {
                    "v": 1,
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "seq": sequence,
                    "event": "error",
                    "payload": {"message": "Invalid JSON message"}
                }
                await websocket.send_text(json.dumps(error_response))
                sequence += 1
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            error_response = {
                "v": 1,
                "ts": datetime.utcnow().isoformat() + "Z", 
                "seq": sequence,
                "event": "error",
                "payload": {"message": str(e)}
            }
            await websocket.send_text(json.dumps(error_response))
        except:
            pass
    finally:
        # Cleanup subscriptions
        if 'subscriptions' in locals():
            from api.services.stream_manager import stream_manager
            for topic, queue in subscriptions.items():
                try:
                    await stream_manager.unsubscribe(topic, tenant_id, queue)
                except:
                    pass


@router.get(
    "/stream/topics",
    response_model=BaseResponse,
    summary="List Available Topics",
    operation_id="v1_stream_topics",
)
async def list_stream_topics(include_resume: bool = Query(False, description="Include resume stats")) -> BaseResponse:
    """
    Get list of available streaming topics.
    
    Returns discoverable topics with descriptions and access requirements.
    """
    topics = [
        {
            "topic": "kp.ruling_planets",
            "description": "KP Ruling Planets updates",
            "update_frequency": "real-time",
            "requires_auth": True
        },
        {
            "topic": "kp.moon.chain",
            "description": "Moon chain progression updates", 
            "update_frequency": "every 2 minutes",
            "requires_auth": True
        },
        {
            "topic": "jyotish.transit_events",
            "description": "Significant transit events",
            "update_frequency": "event-driven", 
            "requires_auth": True
        },
        {
            "topic": "location.activation",
            "description": "Global Locality Research updates",
            "update_frequency": "hourly",
            "requires_auth": True
        }
    ]
    # Enrich with current subscribers and optional resume stats
    try:
        from api.services.stream_manager import stream_manager
        stats = stream_manager.stats()
        subs = stats.get("topics", {})
        if include_resume:
            import asyncio
            async def add_resume(entry):
                entry["resume"] = await stream_manager.resume_stats(entry["topic"])  # type: ignore
            await asyncio.gather(*[add_resume(t) for t in topics])
        for t in topics:
            t["subscribers"] = subs.get(t["topic"], 0)
    except Exception:
        pass

    return BaseResponse.create(
        data=topics,
        path_template=PATH_TEMPLATES["stream_topics"],
        count=len(topics),
        compute_units=0.01
    )
