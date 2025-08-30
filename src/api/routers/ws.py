"""
WebSocket router for VedaCore streaming with bidirectional control.

Browser-compatible WebSocket streaming with:
- Query parameter JWT authentication (WebSocket browser limitation)
- Rate limiting for connections and control messages
- Topic subscription management (subscribe/unsubscribe/ping/stats)
- Integration with stream_manager for real-time data forwarding
- Graceful connection handling and cleanup

Critical PM requirements:
- Browser WebSocket API cannot send Authorization headers
- Must use query parameter authentication
- Rate limiting enforced at connection and message levels
- Proper cleanup on disconnect to prevent memory leaks
"""

from __future__ import annotations

import json
import logging

from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..services.auth import AuthError, validate_jwt_token
from ..services.rate_limiter import log_rate_limit_violation, rate_limiter
from ..services.ws_manager import ws_manager

# Import metrics for monitoring
try:
    from ..services.metrics import streaming_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None, description="JWT token for authentication"),
):
    """
    WebSocket endpoint for real-time bidirectional streaming.

    CRITICAL: Uses query parameter authentication because WebSocket API
    cannot send Authorization headers in browsers.

    Usage:
    - Connect: ws://localhost:8000/ws?token=jwt_token_here
    - Subscribe: {"action": "subscribe", "topics": ["kp.v1.moon.chain"]}
    - Unsubscribe: {"action": "unsubscribe", "topics": ["kp.v1.moon.chain"]}
    - Ping: {"action": "ping"}
    - Stats: {"action": "stats"}
    """
    # Validate JWT token from query parameter
    if not token:
        await websocket.close(code=1008, reason="Missing token parameter")
        return

    try:
        auth_context = validate_jwt_token(token)
        tenant_id = auth_context.require_tenant()
    except (AuthError, HTTPException) as e:
        await websocket.close(code=1008, reason=f"Invalid token: {e}")
        return

    # Check connection limits (PM requirement)
    if not await rate_limiter.allow_connection(tenant_id):
        await log_rate_limit_violation(
            tenant_id=tenant_id, limit_type="connection", endpoint="/ws"
        )
        await websocket.close(code=1008, reason="Connection limit exceeded")
        return

    # Accept WebSocket connection
    await websocket.accept()

    # Register client with ws_manager
    try:
        client_state = await ws_manager.connect(
            websocket=websocket,
            client_id=f"{tenant_id}:{websocket.client.host if websocket.client else 'unknown'}",
            tenant_id=tenant_id,
        )
        await rate_limiter.add_connection(tenant_id)

        # Record connection metrics
        import time

        connection_start = time.time()
        messages_sent = 0
        messages_received = 0
        if METRICS_AVAILABLE:
            streaming_metrics.record_connection(tenant_id, "websocket", "ws")

        logger.info(f"WebSocket connected: {client_state.client_id}")

        # Send welcome message
        await websocket.send_text(
            json.dumps(
                {
                    "event": "connected",
                    "ok": True,
                    "client_id": client_state.client_id,
                    "tenant_id": tenant_id,
                    "timestamp": client_state.connected_at,
                }
            )
        )
        messages_sent += 1

        # Message handling loop
        while True:
            try:
                # Receive message from client
                raw_message = await websocket.receive_text()
                messages_received += 1

                # Parse JSON message
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError as e:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "ok": False,
                                "error": "invalid_json",
                                "detail": f"Failed to parse JSON: {e}",
                            }
                        )
                    )
                    messages_sent += 1
                    continue

                # Rate limiting for control messages
                if not await rate_limiter.allow_qps(
                    tenant_id, cost=0.1
                ):  # Lower cost for control
                    await log_rate_limit_violation(
                        tenant_id=tenant_id,
                        limit_type="qps",
                        endpoint="/ws",
                        action=message.get("action", "unknown"),
                    )
                    await websocket.send_text(
                        json.dumps(
                            {
                                "ok": False,
                                "error": "rate_limited",
                                "detail": "Too many requests",
                            }
                        )
                    )
                    messages_sent += 1
                    continue

                # Handle message via ws_manager
                await ws_manager.handle_message(message, websocket)

            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected: {client_state.client_id}")
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                try:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "ok": False,
                                "error": "internal_error",
                                "detail": "An internal error occurred",
                            }
                        )
                    )
                    messages_sent += 1
                except Exception:
                    # Connection may be broken, exit gracefully
                    break

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        # Record connection completion metrics
        try:
            if METRICS_AVAILABLE:
                connection_duration = time.time() - connection_start
                streaming_metrics.record_connection_completed(
                    tenant_id,
                    "websocket",
                    "ws",
                    connection_duration,
                    messages_sent + messages_received,
                )
        except Exception as e:
            logger.warning(f"Failed to record connection completion metrics: {e}")

        # Always clean up resources
        try:
            await ws_manager.disconnect(websocket)
            await rate_limiter.remove_connection(tenant_id)
            logger.info(f"WebSocket cleanup completed for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Error during WebSocket cleanup: {e}")


@router.get("/health")
async def websocket_health() -> dict[str, Any]:
    """
    WebSocket service health check.

    No authentication required for health checks.
    """
    try:
        ws_stats = ws_manager.get_stats()
        rate_stats = rate_limiter.get_metrics()

        healthy = (
            isinstance(ws_stats.get("connections", 0), int)
            and isinstance(ws_stats.get("messages_sent", 0), int)
            and ws_stats.get("connections", 0) >= 0
        )

        return {
            "status": "healthy" if healthy else "unhealthy",
            "service": "vedacore_websocket",
            "version": "1.0.0",
            "stats": {
                "active_connections": ws_stats.get("connections", 0),
                "messages_sent": ws_stats.get("messages_sent", 0),
                "messages_received": ws_stats.get("messages_received", 0),
                "total_subscriptions": ws_stats.get("total_subscriptions", 0),
                "rate_limit_checks": rate_stats.get("total_checks", 0),
            },
        }

    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/stats")
async def websocket_stats() -> dict[str, Any]:
    """
    Detailed WebSocket statistics for monitoring.

    No authentication required for monitoring endpoints.
    """
    ws_stats = ws_manager.get_stats()
    rate_stats = rate_limiter.get_metrics()

    return {
        "websocket_manager": ws_stats,
        "rate_limiter": rate_stats,
        "service_info": {
            "version": "1.0.0",
            "protocol": "websocket",
            "authentication": "jwt_query_parameter",
        },
    }
