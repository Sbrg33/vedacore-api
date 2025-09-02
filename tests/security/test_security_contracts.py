from __future__ import annotations

import os
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


@pytest.mark.security
def test_idempotency_replay_header_when_redis_available():
    if not os.getenv("REDIS_URL"):
        pytest.skip("REDIS_URL not set; skipping idempotency test")

    payload = {
        "datetime": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc).isoformat(),
        "lat": 12.0,
        "lon": 77.0,
        "include_day_lord": True,
    }
    key = f"test-{uuid.uuid4().hex}"

    r1 = client.post("/api/v1/kp/ruling-planets", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 200, r1.text

    r2 = client.post("/api/v1/kp/ruling-planets", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code == 200, r2.text
    assert r2.headers.get("X-Idempotency-Replayed") == "true"


def test_cors_preflight_allow_and_deny_matrix():
    # Allowed dev origin
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    }
    ok = client.options("/api/v1/health/live", headers=headers)
    # Starlette may return 200 or 204 for preflight; ensure CORS header present
    assert ok.status_code in (200, 204)
    assert ok.headers.get("access-control-allow-origin") is not None

    # Disallowed origin
    bad_headers = {
        "Origin": "https://not-allowed.example",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    }
    bad = client.options("/api/v1/health/live", headers=bad_headers)
    # No allow-origin header expected
    assert bad.headers.get("access-control-allow-origin") is None

