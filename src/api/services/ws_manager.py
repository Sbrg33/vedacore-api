"""
ws_manager.py — WebSocket connection manager for VedaCore streaming.
- Client state tracking with subscription management
- JSON message handling (subscribe/unsubscribe/ping/stats)
- Integration with stream_manager for topic forwarding

CRITICAL FIX: Use dict-based client tracking to avoid hashability issues
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .stream_manager import stream_manager

# Import metrics for monitoring
try:
    from .metrics import streaming_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

# --------------------------- Data -----------------------------


@dataclass
class ClientState:
    """Represents a WebSocket client's state and subscriptions."""

    websocket: WebSocket
    subscriptions: set[str] = field(default_factory=set)
    queues: dict[str, asyncio.Queue[str]] = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    client_id: str = ""
    tenant_id: str | None = None


class WSManager:
    """
    WebSocket connection manager with subscription handling.

    CRITICAL FIX: Uses dict-based client tracking to avoid hashability issues
    """

    def __init__(self) -> None:
        # FIXED: Use dict keyed by websocket instead of set (avoids hashability issues)
        self._clients: dict[WebSocket, ClientState] = {}
        self._lock = asyncio.Lock()
        self._metrics = {
            "connections": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "subscriptions": 0,
        }

    # -------------------- Connection Management ---------------

    async def connect(
        self, websocket: WebSocket, client_id: str = "", tenant_id: str | None = None
    ) -> ClientState:
        """Register a new WebSocket client."""
        state = ClientState(
            websocket=websocket, client_id=client_id, tenant_id=tenant_id
        )

        async with self._lock:
            # FIXED: Store by websocket in dict instead of adding to set
            self._clients[websocket] = state
            self._metrics["connections"] = len(self._clients)

        logger.info(f"WebSocket client connected: {client_id} (tenant: {tenant_id})")
        return state

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket client and clean up subscriptions."""
        async with self._lock:
            # FIXED: Pop from dict instead of removing from set
            state = self._clients.pop(websocket, None)
            if state is None:
                return

            self._metrics["connections"] = len(self._clients)

        # Clean up subscriptions
        for topic, queue in state.queues.items():
            await stream_manager.unsubscribe(topic, queue)
            logger.debug(f"Unsubscribed client {state.client_id} from topic {topic}")

        logger.info(f"WebSocket client disconnected: {state.client_id}")

    async def get_client_state(self, websocket: WebSocket) -> ClientState | None:
        """Get client state for a websocket."""
        async with self._lock:
            return self._clients.get(websocket)

    # -------------------- Message Handling --------------------

    async def handle_message(
        self, message: dict[str, Any], websocket: WebSocket
    ) -> None:
        """Handle incoming WebSocket message."""
        action = message.get("action")
        state = await self.get_client_state(websocket)

        if state is None:
            await self._send_error(
                websocket, "client_not_found", "Client state not found"
            )
            return

        state.last_activity = time.time()
        self._metrics["messages_received"] += 1

        if action == "subscribe":
            await self._handle_subscribe(message, state)
        elif action == "unsubscribe":
            await self._handle_unsubscribe(message, state)
        elif action == "ping":
            await self._handle_ping(message, state)
        elif action == "stats":
            await self._handle_stats(message, state)
        else:
            await self._send_error(
                websocket, "unknown_action", f"Unknown action: {action}"
            )

    async def _handle_subscribe(
        self, message: dict[str, Any], state: ClientState
    ) -> None:
        """Handle subscription request."""
        topics = message.get("topics", [])
        if not isinstance(topics, list):
            await self._send_error(
                state.websocket, "invalid_topics", "Topics must be a list"
            )
            return

        for topic in topics:
            if topic in state.subscriptions:
                continue  # Already subscribed

            try:
                # Subscribe to topic via stream manager
                queue = await stream_manager.subscribe(topic)
                state.subscriptions.add(topic)
                state.queues[topic] = queue

                # Start forwarding task for this topic
                asyncio.create_task(self._forward_messages(topic, queue, state))

                logger.debug(f"Client {state.client_id} subscribed to {topic}")
            except Exception as e:
                await self._send_error(
                    state.websocket,
                    "subscribe_error",
                    f"Failed to subscribe to {topic}: {e}",
                )

        # Send acknowledgment
        await self._send_response(
            state.websocket,
            {
                "action": "subscribe",
                "ok": True,
                "subscribed_topics": list(state.subscriptions),
            },
        )

    async def _handle_unsubscribe(
        self, message: dict[str, Any], state: ClientState
    ) -> None:
        """Handle unsubscription request."""
        topics = message.get("topics", [])
        if not isinstance(topics, list):
            await self._send_error(
                state.websocket, "invalid_topics", "Topics must be a list"
            )
            return

        for topic in topics:
            if topic not in state.subscriptions:
                continue  # Not subscribed

            try:
                # Unsubscribe from topic via stream manager
                queue = state.queues.get(topic)
                if queue:
                    await stream_manager.unsubscribe(topic, queue)
                    state.queues.pop(topic, None)

                state.subscriptions.discard(topic)
                logger.debug(f"Client {state.client_id} unsubscribed from {topic}")
            except Exception as e:
                await self._send_error(
                    state.websocket,
                    "unsubscribe_error",
                    f"Failed to unsubscribe from {topic}: {e}",
                )

        # Send acknowledgment
        await self._send_response(
            state.websocket,
            {
                "action": "unsubscribe",
                "ok": True,
                "subscribed_topics": list(state.subscriptions),
            },
        )

    async def _handle_ping(self, message: dict[str, Any], state: ClientState) -> None:
        """Handle ping request."""
        await self._send_response(
            state.websocket, {"action": "pong", "ok": True, "timestamp": time.time()}
        )

    async def _handle_stats(self, message: dict[str, Any], state: ClientState) -> None:
        """Handle stats request."""
        client_stats = {
            "client_id": state.client_id,
            "connected_at": state.connected_at,
            "subscriptions": list(state.subscriptions),
            "subscription_count": len(state.subscriptions),
        }

        await self._send_response(
            state.websocket,
            {
                "action": "stats",
                "ok": True,
                "client": client_stats,
                "manager": self._metrics,
            },
        )

    # -------------------- Message Forwarding ------------------

    async def _forward_messages(
        self, topic: str, queue: asyncio.Queue[str], state: ClientState
    ) -> None:
        """Forward messages from stream queue to WebSocket client."""
        try:
            while topic in state.subscriptions:
                try:
                    # Get next message from stream (includes heartbeats)
                    message = await stream_manager.next_message(
                        queue, heartbeat_secs=15
                    )

                    # Send to WebSocket client
                    await state.websocket.send_text(message)
                    self._metrics["messages_sent"] += 1

                    # Record message delivery metrics
                    if METRICS_AVAILABLE:
                        streaming_metrics.record_websocket_message_sent(
                            state.tenant_id or "unknown", topic
                        )

                except WebSocketDisconnect:
                    logger.debug(
                        f"WebSocket disconnected during message forward: {state.client_id}"
                    )
                    break
                except Exception as e:
                    logger.error(f"Error forwarding message to {state.client_id}: {e}")
                    break
        finally:
            # Clean up subscription if task ends
            if topic in state.subscriptions:
                state.subscriptions.discard(topic)
                state.queues.pop(topic, None)
                await stream_manager.unsubscribe(topic, queue)

    # -------------------- Utility Methods ---------------------

    async def _send_response(
        self, websocket: WebSocket, response: dict[str, Any]
    ) -> None:
        """Send JSON response to WebSocket client."""
        try:
            await websocket.send_text(json.dumps(response))
            self._metrics["messages_sent"] += 1
        except WebSocketDisconnect:
            pass  # Client disconnected
        except Exception as e:
            logger.error(f"Error sending WebSocket response: {e}")

    async def _send_error(self, websocket: WebSocket, error: str, detail: str) -> None:
        """Send error response to WebSocket client."""
        await self._send_response(
            websocket, {"ok": False, "error": error, "detail": detail}
        )

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics."""
        total_subscriptions = sum(
            len(state.subscriptions) for state in self._clients.values()
        )
        return {
            **self._metrics,
            "total_subscriptions": total_subscriptions,
            "clients_by_tenant": self._get_client_count_by_tenant(),
        }

    def _get_client_count_by_tenant(self) -> dict[str, int]:
        """Get client count grouped by tenant."""
        tenant_counts = {}
        for state in self._clients.values():
            tenant = state.tenant_id or "unknown"
            tenant_counts[tenant] = tenant_counts.get(tenant, 0) + 1
        return tenant_counts


# Singleton instance to import across routers
ws_manager = WSManager()
