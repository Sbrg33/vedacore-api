# api/routers/location_stream.py
# Server-Sent Events (SSE) endpoint for streaming Location Features payloads
# Cadence: 60–240s, minute-bucket aligned. Thin wrapper that reuses the existing
# /api/v1/location/features endpoint via httpx so contract stays single-sourced.
from __future__ import annotations

import asyncio
import json
import os

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from starlette.responses import StreamingResponse

# Optional Prometheus instrumentation (safe if not installed)
try:
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # pragma: no cover - optional dep
    Counter = Gauge = Histogram = None  # type: ignore

router = APIRouter(tags=["Location Features Stream"])

# Metrics
REQS = (
    Counter("vedacore_location_stream_requests_total", "SSE stream requests")
    if Counter
    else None
)
CLIENTS = (
    Gauge("vedacore_location_stream_clients", "Active SSE clients") if Gauge else None
)
EVENTS = (
    Counter("vedacore_location_stream_events_total", "SSE events sent")
    if Counter
    else None
)
DUR = (
    Histogram("vedacore_location_stream_tick_seconds", "Tick duration seconds")
    if Histogram
    else None
)

# Config
DEFAULT_INTERVAL_SEC = 120
MIN_INTERVAL_SEC = 60
MAX_INTERVAL_SEC = 240
HEARTBEAT_SEC = 30


def _base_features_url(request: Request) -> str:
    # Prefer explicit env override so this can live behind proxies.
    env_url = os.getenv("VEDACORE_URL")
    if env_url:
        return env_url.rstrip("/") + "/api/v1/location/features"
    # Fallback: derive from current request
    return str(request.base_url).rstrip("/") + "/api/v1/location/features"


def _next_tick(now: datetime, interval: int) -> datetime:
    # Align to the *next* interval boundary in UTC.
    # Example: interval=120 => boundaries at :00, :02, :04, ...
    epoch = int(now.timestamp())
    remainder = epoch % interval
    wait = interval - remainder if remainder else interval
    return now + timedelta(seconds=wait)


def _sse_pack(event: str, data: dict, event_id: str | None = None) -> str:
    # Always single-line JSON in 'data:' for SSE
    buf = []
    if event_id:
        buf.append(f"id: {event_id}")
    buf.append(f"event: {event}")
    buf.append("data: " + json.dumps(data, separators=(",", ":")))
    buf.append("")  # blank line terminator
    return "\n".join(buf) + "\n"


@router.get("/api/v1/location/features/stream")
async def stream_location_features(
    request: Request,
    response: Response,
    timestamp: str | None = Query(
        None, description="ISO8601 UTC start timestamp; defaults to 'now' UTC"
    ),
    cities: str | None = Query(
        None, description="CSV city IDs, same as the GET features endpoint"
    ),
    topocentric: bool = Query(
        True, description="Topocentric toggle (mirrors features endpoint)"
    ),
    house_system: str = Query("KP", description="House system (KP/PLACIDUS/BHAVA)"),
    interval: int = Query(
        DEFAULT_INTERVAL_SEC,
        ge=MIN_INTERVAL_SEC,
        le=MAX_INTERVAL_SEC,
        description="Stream interval seconds",
    ),
    limit: int | None = Query(
        None, description="Optional max number of feature events to send (for testing)"
    ),
    token: str | None = Query(
        None,
        description="Short-lived JWT token for browser EventSource (alternative to Authorization header)",
    ),
    authorization: str | None = Header(None, convert_underscores=False),
    last_event_id: str | None = Header(None, convert_underscores=False),
) -> StreamingResponse:
    """SSE stream that periodically fetches the Location Features payload.

    Contract is intentionally thin: it forwards to the existing /api/v1/location/features
    so the single source of truth for computation remains the features endpoint.

    Security: forwards the caller's Authorization header, if any.
    Versioning: propagates X-VedaCore-Version from the inner call into event payload headers.
    """
    if REQS:
        REQS.inc()

    base_url = _base_features_url(request)

    # Validate early to return a normal 4xx rather than a stream
    if not cities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cities is required"
        )  # keep parity with features

    async def eventgen() -> AsyncGenerator[bytes, None]:
        if CLIENTS:
            CLIENTS.inc()

        # Handle resumption from Last-Event-ID header
        resume_after = None
        if last_event_id:
            try:
                resume_after = datetime.fromisoformat(
                    last_event_id.replace("Z", "+00:00")
                ).astimezone(UTC)
            except Exception:
                resume_after = None  # ignore malformed ID

        # First tick time
        if timestamp:
            try:
                start = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                ).astimezone(UTC)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid timestamp: {e}")
        else:
            start = datetime.now(UTC)

        # Send first event immediately, then align to the next boundary
        events_sent = 0
        keepalive_at = datetime.now(UTC) + timedelta(seconds=HEARTBEAT_SEC)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0)
        ) as client:
            while True:
                # Exit if client disconnected
                if await request.is_disconnected():
                    break

                # Compute ts to query (current UTC, contract applies KP policy internally)
                now = datetime.now(UTC)

                if events_sent == 0 and resume_after:
                    ts = _next_tick(resume_after, interval)
                elif events_sent == 0 and timestamp is None:
                    ts = now  # immediate first push
                else:
                    ts = _next_tick(now, interval)

                # Generate monotonic event ID from effective timestamp
                event_id = ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")

                params = {
                    "timestamp": event_id,
                    "cities": cities,
                    "topocentric": str(topocentric).lower(),
                    "house_system": house_system,
                }
                headers = {"Accept": "application/json"}
                if authorization:
                    headers["Authorization"] = authorization
                elif token:
                    headers["Authorization"] = f"Bearer {token}"

                # Tick timing
                t0 = asyncio.get_running_loop().time()
                try:
                    r = await client.get(base_url, params=params, headers=headers)
                    # If backend returns hard errors, surface error event then close stream
                    if r.status_code in (401, 403, 413):
                        payload = {"status": r.status_code, "error": r.text[:200]}
                        yield _sse_pack("error", payload, event_id=event_id).encode(
                            "utf-8"
                        )
                        break  # Close stream for hard errors
                    elif r.status_code >= 400:
                        # Soft errors - continue streaming
                        payload = {"status": r.status_code, "error": r.text[:200]}
                        yield _sse_pack("error", payload, event_id=event_id).encode(
                            "utf-8"
                        )
                    else:
                        payload = r.json()
                        # Emit 'features' event with monotonic event ID
                        yield _sse_pack("features", payload, event_id=event_id).encode(
                            "utf-8"
                        )
                        if EVENTS:
                            EVENTS.inc()
                        events_sent += 1
                except Exception as e:  # network or serialization
                    yield _sse_pack(
                        "error", {"status": 502, "error": str(e)[:200]}
                    ).encode("utf-8")

                # Histogram
                if DUR:
                    DUR.observe(asyncio.get_running_loop().time() - t0)

                # Optional limit for tests
                if limit is not None and events_sent >= limit:
                    break

                # Heartbeat if needed while waiting for next tick
                # Sleep in small chunks to respond quickly to disconnects
                wake = _next_tick(datetime.now(UTC), interval)
                while True:
                    if await request.is_disconnected():
                        break
                    now2 = datetime.now(UTC)
                    if now2 >= wake:
                        break
                    # heartbeat
                    if now2 >= keepalive_at:
                        yield _sse_pack(
                            "keepalive",
                            {
                                "now": now2.replace(microsecond=0)
                                .isoformat()
                                .replace("+00:00", "Z")
                            },
                        ).encode("utf-8")
                        keepalive_at = now2 + timedelta(seconds=HEARTBEAT_SEC)
                    await asyncio.sleep(0.5)

        if CLIENTS:
            CLIENTS.dec()

    # Reflect client-provided X-Request-ID for correlation
    req_id = request.headers.get("X-Request-ID")
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream; charset=utf-8",
        "Connection": "keep-alive",
        # Surfaced here for convenience; the inner features endpoint already sets it on HTTP responses.
        "X-VedaCore-Version": "1.0.0",
        "X-Request-ID": req_id or "",  # harmless if missing
    }
    return StreamingResponse(eventgen(), headers=headers)
