from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")

from apps.api.main import app  # noqa: E402  (import after env)


client = TestClient(app)


def make_stream_token(topic: str, ttl_seconds: int = 120) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "vedacore",
        "aud": "stream",
        "sub": "test-key",
        "tid": "tenant-1",
        "topic": topic,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=ttl_seconds)).timestamp(),
        "jti": "unit-test-jti",
    }
    secret = os.environ["AUTH_JWT_SECRET"]
    return jwt.encode(payload, secret, algorithm="HS256")


def test_header_only_succeeds_event_stream() -> None:
    token = make_stream_token("kp.moon.chain", ttl_seconds=120)
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
        assert "text/event-stream" in ct


def test_query_only_succeeds_with_deprecation_headers() -> None:
    token = make_stream_token("kp.moon.chain", ttl_seconds=120)
    with client.stream(
        "GET",
        "/api/v1/stream",
        params={"topic": "kp.moon.chain", "token": token},
        headers={"Accept": "text/event-stream"},
    ) as r:
        assert r.status_code == 200
        assert r.headers.get("Warning", "").startswith("299")
        assert r.headers.get("Deprecation") == "true"
        assert r.headers.get("Sunset") is not None
        assert r.headers.get("Cache-Control") == "no-store"


def test_both_present_header_wins() -> None:
    good = make_stream_token("kp.moon.chain", ttl_seconds=120)
    # Make a token with excessive TTL to be rejected if evaluated (query path)
    bad = make_stream_token("kp.moon.chain", ttl_seconds=1200)
    with client.stream(
        "GET",
        "/api/v1/stream",
        params={"topic": "kp.moon.chain", "token": bad},
        headers={
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {good}",
        },
    ) as r:
        assert r.status_code == 200


def test_invalid_token_yields_401_www_authenticate() -> None:
    bad = make_stream_token("kp.moon.chain", ttl_seconds=1200)  # query TTL too long => invalid
    r = client.get(
        "/api/v1/stream",
        params={"topic": "kp.moon.chain", "token": bad},
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 401
    www = r.headers.get("WWW-Authenticate", "")
    assert www.startswith("Bearer ")

