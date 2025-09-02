from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def _make_token() -> str:
    # Use the server's own helper to ensure matching secret/audience
    from api.services.auth import create_jwt_token

    return create_jwt_token(tenant_id="test-tenant", user_id="tester", ttl_seconds=60)


def test_ws_health_and_stats_available():
    r1 = client.get("/ws/health")
    r2 = client.get("/ws/stats")
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_websocket_connect_and_close_quickly():
    # Skip if token creation not possible (e.g., JWKS mode)
    try:
        token = _make_token()
    except Exception:
        pytest.skip("JWT token creation unavailable; skipping WS lifecycle test")

    with client.websocket_connect(f"/ws?token={token}") as ws:
        # Immediately close; if accept succeeded, context manager exits cleanly
        pass

