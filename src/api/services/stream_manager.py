"""
stream_manager.py — In‑process pub/sub for SSE & WebSockets (no Redis).
- Topic registry with per-subscriber asyncio.Queue
- Backpressure handling (drop-oldest strategy)
- JSON envelope builder with seq and timestamp
- Heartbeats for idle connections

CRITICAL FIX: Use dict-based subscriber tracking to avoid hashability issues
"""

from __future__ import annotations

import asyncio
import time
import os

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

try:
    import orjson as _orjson

    def _dumps(obj: Any) -> str:
        return _orjson.dumps(obj).decode("utf-8")

except Exception:  # pragma: no cover
    import json as _json

    def _dumps(obj: Any) -> str:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# Import metrics for monitoring
try:
    from .metrics import streaming_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# --------------------------- Config ---------------------------

DEFAULT_QUEUE_SIZE = 1024  # per-subscriber buffer
DEFAULT_HEARTBEAT_SECS = 15  # idle heartbeat cadence
DEFAULT_WAIT_TIMEOUT_SECS = 1  # poll interval while waiting for messages

# --------------------------- Data -----------------------------


@dataclass
class Subscriber:
    """Represents a single subscriber queue attached to a topic."""

    queue: asyncio.Queue[str]
    created_at: float
    last_activity: float


class StreamManager:
    """
    In-memory topic pub/sub suitable for a single FastAPI/Uvicorn worker.
    Scale-out path: replace _broadcast() with Redis/NATS via an adapter.

    CRITICAL FIX: Uses dict-based subscriber tracking to avoid hashability issues
    """

    def __init__(self) -> None:
        # FIXED: Use dict keyed by queue instead of set (avoids hashability issues)
        self._topics: dict[str, dict[asyncio.Queue[str], Subscriber]] = defaultdict(
            dict
        )
        self._lock = asyncio.Lock()
        self._seq = 0
        self._metrics = {
            "published": 0,
            "dropped": 0,
            "subscribers": 0,
        }
        # In-memory ring buffer per topic for SSE resume
        self._ring: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=1000))
        self._ring_size = 1000
        # Optional Redis-backed resume store (Upstash-compatible)
        self._resume_store = None
        self._resume_init_attempted = False
        try:
            from shared.otel import get_tracer  # lazy-safe

            self._tracer = get_tracer("stream")
        except Exception:
            self._tracer = None

    # -------------------- Envelope helpers --------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    @staticmethod
    def _ts() -> str:
        # RFC3339 UTC
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def build_envelope(
        self, *, topic: str, event: str, payload: dict[str, Any], v: int = 1
    ) -> dict[str, Any]:
        return {
            "v": v,
            "ts": self._ts(),
            "seq": self._next_seq(),
            "topic": topic,
            "event": event,
            "payload": payload,
        }

    # -------------------- Public API --------------------------

    async def publish(
        self, topic: str, payload: dict[str, Any], *, event: str = "update", v: int = 1
    ) -> None:
        """Publish a payload to all subscribers of a topic."""
        publish_start = time.time()
        with (self._tracer.start_as_current_span("stream.publish") if self._tracer else _null_cm()) as span:
            # Global monotonic sequence (Upstash/Redis) with in-process fallback
            seq = await self._next_global_seq(topic)
            env = {
                "v": v,
                "ts": self._ts(),
                "seq": seq,
                "topic": topic,
                "event": event,
                "payload": payload,
            }
            data = _dumps(env)
            try:
                span.set_attribute("stream.topic", topic)
                span.set_attribute("stream.seq", int(seq))
            except Exception:
                pass
            # Store to ring buffer for resume
            try:
                self._store_ring(topic, data)
            except Exception:
                pass
            # Also store to Redis resume backend if available
            try:
                await self._maybe_store_resume(topic, int(env.get("seq", 0)), data)
            except Exception:
                pass
            await self._broadcast(topic, data)

        # Record metrics
        if METRICS_AVAILABLE:
            latency = time.time() - publish_start
            streaming_metrics.record_message_published(topic, latency)

    async def heartbeat(self, topic: str) -> None:
        """Broadcast a heartbeat event to a topic (useful for WS groups)."""
        await self.publish(topic, {"kind": "heartbeat"}, event="heartbeat")

        # Record heartbeat metrics
        if METRICS_AVAILABLE:
            streaming_metrics.record_stream_heartbeat(topic)

    async def subscribe(
        self, topic: str, *, max_queue: int = DEFAULT_QUEUE_SIZE
    ) -> asyncio.Queue[str]:
        """Register a new subscriber queue for a topic."""
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=max_queue)
        sub = Subscriber(queue=q, created_at=time.time(), last_activity=time.time())
        async with self._lock:
            # FIXED: Store by queue in dict instead of adding to set
            self._topics[topic][q] = sub
            self._metrics["subscribers"] = sum(
                len(subs) for subs in self._topics.values()
            )

            # Update topic subscriber metrics
            if METRICS_AVAILABLE:
                streaming_metrics.update_topic_subscribers(
                    topic, len(self._topics[topic])
                )

        return q

    async def unsubscribe(self, topic: str, q: asyncio.Queue[str]) -> None:
        """Remove a subscriber queue from a topic and drain it."""
        async with self._lock:
            topic_subs = self._topics.get(topic, {})
            # FIXED: Pop from dict instead of removing from set
            sub = topic_subs.pop(q, None)
            if sub is None:
                return
            # Clean up empty topic
            if not topic_subs:
                self._topics.pop(topic, None)
            self._metrics["subscribers"] = sum(
                len(subs) for subs in self._topics.values()
            )

        # Best-effort drain
        try:
            while True:
                q.get_nowait()
        except Exception:
            pass

    async def next_message(
        self, q: asyncio.Queue[str], *, heartbeat_secs: int = DEFAULT_HEARTBEAT_SECS
    ) -> str:
        """
        Await next message or return a heartbeat if idle.
        SSE: yield the returned string as `data`.
        WS:  send as text/json to the client.
        """
        try:
            msg = await asyncio.wait_for(q.get(), timeout=heartbeat_secs)
            return msg
        except TimeoutError:
            # Emit a heartbeat envelope with a special topic "_hb"
            env = {
                "v": 1,
                "ts": self._ts(),
                "seq": self._next_seq(),
                "topic": "_hb",
                "event": "heartbeat",
                "payload": {"kind": "idle"},
            }
            return _dumps(env)

    def stats(self) -> dict[str, Any]:
        """Return lightweight metrics snapshot."""
        return {
            **self._metrics,
            "topics": {k: len(v) for k, v in self._topics.items()},
        }

    # -------------------- Internal ----------------------------

    async def _broadcast(self, topic: str, data: str) -> None:
        """Fan-out to all subscriber queues with drop-oldest on backpressure."""
        async with self._lock:
            # FIXED: Get dict values instead of set items
            subs = list(self._topics.get(topic, {}).values())
        if not subs:
            return
        dropped = 0
        for sub in subs:
            # Non-blocking put with drop-oldest strategy
            try:
                sub.queue.put_nowait(data)
            except asyncio.QueueFull:
                try:
                    _ = sub.queue.get_nowait()  # drop oldest
                except Exception:
                    pass
                try:
                    sub.queue.put_nowait(data)
                except Exception:
                    dropped += 1
                    continue
        self._metrics["published"] += 1
        self._metrics["dropped"] += dropped

        # Record drop metrics
        if METRICS_AVAILABLE and dropped > 0:
            for _ in range(dropped):
                streaming_metrics.record_message_dropped(topic, "backpressure")

    # -------------------- Ring buffer -------------------------

    def _store_ring(self, topic: str, data: str) -> None:
        self._ring[topic].append(data)

    async def replay_since(self, topic: str, last_seq: int, limit: int = 500) -> list[str]:
        """Return messages with seq > last_seq from Redis if available, else memory ring."""
        with (self._tracer.start_as_current_span("stream.replay") if self._tracer else _null_cm()) as span:
            # Try Redis resume store first
            try:
                store = await self._get_resume_store()
                if store is not None:
                    t0 = time.time()
                    items = await store.replay_since(topic, last_seq, limit)
                    try:
                        span.set_attribute("stream.topic", topic)
                        span.set_attribute("stream.resume.since", int(last_seq))
                        span.set_attribute("redis.duration_ms", round((time.time()-t0)*1000, 3))
                        span.set_attribute("stream.resume.replayed_count", len(items or []))
                    except Exception:
                        pass
                    if items:
                        return items
            except Exception:
                pass
            # Fallback to memory ring
            out: list[str] = []
            try:
                ring = list(self._ring.get(topic, ()))
                for s in ring:
                    try:
                        obj = _orjson.loads(s) if '_orjson' in globals() else _json.loads(s)
                    except Exception:
                        continue
                    if int(obj.get("seq", -1)) > last_seq:
                        out.append(s)
                        if len(out) >= limit:
                            break
            except Exception:
                return out
            try:
                span.set_attribute("stream.topic", topic)
                span.set_attribute("stream.resume.since", int(last_seq))
                span.set_attribute("stream.resume.replayed_count", len(out))
            except Exception:
                pass
            return out

    async def _maybe_store_resume(self, topic: str, seq: int, data: str) -> None:
        try:
            store = await self._get_resume_store()
            if store is not None:
                await store.store(topic, seq, data)
        except Exception:
            pass

    async def _get_resume_store(self):
        if self._resume_store is not None or self._resume_init_attempted:
            return self._resume_store
        self._resume_init_attempted = True
        try:
            from .stream_resume import get_resume_store
            self._resume_store = await get_resume_store()
        except Exception:
            self._resume_store = None
        return self._resume_store

    async def resume_stats(self, topic: str) -> dict:
        """Get resume stats for a topic from Redis and memory.

        Returns keys: redis.size, redis.min_seq, redis.max_seq, memory.size, memory.min_seq, memory.max_seq
        """
        redis_stats = {"size": 0, "min_seq": None, "max_seq": None}
        try:
            store = await self._get_resume_store()
            if store is not None and hasattr(store, "stats"):
                redis_stats = await store.stats(topic)  # type: ignore
        except Exception:
            pass
        mem_size = 0
        mem_min = None
        mem_max = None
        try:
            ring = self._ring.get(topic, ())
            mem_size = len(ring)
            if mem_size:
                try:
                    import json as _json
                    first = _json.loads(ring[0])
                    last = _json.loads(ring[-1])
                    mem_min = int(first.get("seq", 0))
                    mem_max = int(last.get("seq", 0))
                except Exception:
                    pass
        except Exception:
            pass
        return {"redis": redis_stats, "memory": {"size": mem_size, "min_seq": mem_min, "max_seq": mem_max}}

    async def _next_global_seq(self, topic: str) -> int:
        """Return next sequence id from Redis if available; else local counter.

        Uses a per-topic INCR key; compatible with Upstash. No CONFIG required.
        """
        try:
            store = await self._get_resume_store()
            if store is not None and hasattr(store, "client"):
                prefix = os.getenv(
                    "STREAM_SEQ_REDIS_PREFIX",
                    f"sse:seq:{os.getenv('VC_ENV','local')}:",
                )
                key = f"{prefix}{topic}"
                if self._tracer:
                    t0 = time.time()
                    with self._tracer.start_as_current_span("stream.seq.next") as span:
                        val = await store.client.incr(key)  # type: ignore
                        try:
                            span.set_attribute("redis.key", key)
                            span.set_attribute("redis.duration_ms", round((time.time()-t0)*1000, 3))
                        except Exception:
                            pass
                else:
                    val = await store.client.incr(key)  # type: ignore
                return int(val)
        except Exception:
            pass
        return self._next_seq()

# local no-op context manager for tracing
from contextlib import contextmanager


@contextmanager
def _null_cm():
    yield None


# Singleton instance to import across routers/managers
stream_manager = StreamManager()
