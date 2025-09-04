from __future__ import annotations

import os
import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import httpx

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")

from apps.api.main import app  # noqa: E402
from api.services.stream_manager import stream_manager  # noqa: E402


def _make_short_ttl_token(topic: str, ttl_seconds: int = 1) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "vedacore",
        "aud": "stream",
        "sub": "test-key",
        "tid": "tenant-expire",
        "topic": topic,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=ttl_seconds)).timestamp(),
        "jti": "expire-mid-stream",
    }
    return jwt.encode(payload, os.environ["AUTH_JWT_SECRET"], algorithm="HS256")


@pytest.mark.asyncio
async def test_query_token_expired_mid_stream_emits_error_and_closes():
    topic = "kp.moon.chain"
    token = _make_short_ttl_token(topic, ttl_seconds=1)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        async with client.stream(
            "GET",
            "/api/v1/stream",
            params={"topic": topic, "token": token},
            headers={"Accept": "text/event-stream"},
        ) as r:
            assert r.status_code == 200

            line_iter = r.aiter_lines()
            # First line should be retry hint
            first = await anext(line_iter)
            assert first.strip() == "retry: 15000"

            # Wait for token to expire
            await asyncio.sleep(1.2)

            # Publish a message to trigger the live loop iteration
            await stream_manager.publish(topic, {"hello": "world"})

            # Expect an error event due to token_expired
            event_line = None
            data_line = None
            # Read a few lines to capture the error event
            for _ in range(10):
                try:
                    line = await asyncio.wait_for(anext(line_iter), timeout=2.0)
                except Exception:
                    break
                if line.startswith("event: "):
                    event_line = line
                elif line.startswith("data: ") and event_line and event_line.strip() == "event: error":
                    data_line = line
                    break
    assert event_line is not None and event_line.strip() == "event: error"
    assert data_line is not None and "token_expired" in data_line


@pytest.mark.asyncio
async def test_header_token_does_not_emit_expired_error_mid_stream():
    topic = "kp.moon.chain"
    # Short TTL header token; header path should not emit mid-stream token_expired
    token = _make_short_ttl_token(topic, ttl_seconds=1)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        async with client.stream(
            "GET",
            "/api/v1/stream",
            params={"topic": topic},
            headers={"Accept": "text/event-stream", "Authorization": f"Bearer {token}"},
        ) as r:
            assert r.status_code == 200
            line_iter = r.aiter_lines()
            # First line is retry
            first = await anext(line_iter)
            assert first.strip() == "retry: 15000"
            # Wait for token to expire
            await asyncio.sleep(1.2)
            # Publish to trigger loop
            await stream_manager.publish(topic, {"hello": "from_header"})

            saw_error = False
            saw_update = False
            # Read a handful of lines to detect behavior
            for _ in range(20):
                try:
                    line = await asyncio.wait_for(anext(line_iter), timeout=2.0)
                except Exception:
                    break
                if line.startswith("event: error"):
                    saw_error = True
                    break
                if line.startswith("event: update") or line.startswith("id: "):
                    saw_update = True
                    # We can stop once we see an update event chunk starting
                    break
            # Ensure no token_expired error occurred for header tokens
            assert not saw_error
            assert saw_update
