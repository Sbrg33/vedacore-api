from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")

import pytest
from apps.api.main import app  # noqa: E402


def make_stream_token(topic: str, ttl_seconds: int = 60) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "vedacore",
        "aud": "stream",
        "sub": "test-key",
        "tid": "tenant-1",
        "topic": topic,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=ttl_seconds)).timestamp(),
        "jti": "unit-test-jti-2",
    }
    secret = os.environ["AUTH_JWT_SECRET"]
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.integration
def test_event_stream_headers_present(client) -> None:
    token = make_stream_token("kp.moon.chain", ttl_seconds=60)
    with client.stream(
        "GET",
        "/api/v1/stream",
        params={"topic": "kp.moon.chain"},
        headers={
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {token}",
        },
    ) as r:
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert ct.startswith("text/event-stream")
        # must be no-store for SSE
        assert r.headers.get("Cache-Control") == "no-store"
        # first retry line should be present
        first = next(r.iter_lines())
        assert first.strip() == "retry: 15000"
