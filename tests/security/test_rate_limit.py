from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")

from apps.api.main import app  # noqa: E402
from api.services import rate_limiter as rl_mod  # noqa: E402


client = TestClient(app)


def make_token(topic: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "vedacore",
        "aud": "stream",
        "sub": "key",
        "tid": "tenant-rl",
        "topic": topic,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=60)).timestamp(),
        "jti": "rl-test",
    }
    return jwt.encode(payload, os.environ["AUTH_JWT_SECRET"], algorithm="HS256")


def test_sse_handshake_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force allow_qps to return False to trigger 429
    monkeypatch.setattr(rl_mod.rate_limiter, "allow_qps", lambda tenant_id, cost=1.0: False, raising=False)

    token = make_token("kp.moon.chain")
    r = client.get(
        "/api/v1/stream",
        params={"topic": "kp.moon.chain"},
        headers={"Accept": "text/event-stream", "Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 429
    assert r.headers.get("Retry-After") is not None
    body = r.json()
    assert isinstance(body, dict)
    assert body.get("status") == 429
    assert body.get("retry_after_seconds") is not None
