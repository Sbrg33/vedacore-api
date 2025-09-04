from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")

from apps.api.main import app  # noqa: E402


client = TestClient(app)


def make_token(topic: str, ttl: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "vedacore",
        "aud": "stream",
        "sub": "key",
        "tid": "t",
        "topic": topic,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=ttl)).timestamp(),
        "jti": "ttl-boundary",
    }
    return jwt.encode(payload, os.environ["AUTH_JWT_SECRET"], algorithm="HS256")


def test_ttl_600_allowed_query() -> None:
    tok = make_token("kp.moon.chain", 600)
    with client.stream(
        "GET",
        "/api/v1/stream",
        params={"topic": "kp.moon.chain", "token": tok},
        headers={"Accept": "text/event-stream"},
    ) as r:
        assert r.status_code == 200


def test_ttl_601_allowed_with_skew() -> None:
    tok = make_token("kp.moon.chain", 601)
    with client.stream(
        "GET",
        "/api/v1/stream",
        params={"topic": "kp.moon.chain", "token": tok},
        headers={"Accept": "text/event-stream"},
    ) as r:
        assert r.status_code == 200


def test_ttl_too_large_rejected() -> None:
    tok = make_token("kp.moon.chain", 1200)
    r = client.get(
        "/api/v1/stream",
        params={"topic": "kp.moon.chain", "token": tok},
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 401

