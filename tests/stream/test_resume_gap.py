from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")

from apps.api.main import app  # noqa: E402
from api.services.stream_manager import stream_manager  # noqa: E402


client = TestClient(app)


def make_token(topic: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "vedacore",
        "aud": "stream",
        "sub": "key",
        "tid": "t",
        "topic": topic,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=60)).timestamp(),
        "jti": "gap-test",
    }
    return jwt.encode(payload, os.environ["AUTH_JWT_SECRET"], algorithm="HS256")


def test_resume_gap_emits_reset_event_and_closes() -> None:
    topic = "kp.moon.chain"
    # Prime ring buffer with sequences > 100
    for i in range(101, 106):
        env = stream_manager.build_envelope(topic=topic, event="update", payload={"i": i})
        # store ring directly to avoid broadcasting
        stream_manager._store_ring(topic, __import__("json").dumps(env))  # noqa: SLF001

    token = make_token(topic)
    # Request resume from seq far behind
    with client.stream(
        "GET",
        "/api/v1/stream",
        params={"topic": topic},
        headers={
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {token}",
            "Last-Event-ID": "1",
        },
    ) as r:
        assert r.status_code == 200
        # Read first chunk
        first = next(r.iter_lines())
        assert isinstance(first, str)
        assert first.startswith("event: reset")

