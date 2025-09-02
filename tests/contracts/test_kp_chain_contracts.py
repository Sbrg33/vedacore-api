from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def test_kp_chain_contract_and_determinism():
    # Minimal, stable payload: use planet id 2 (Moon), lat/lon at origin
    payload = {
        "datetime": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc).isoformat(),
        "lat": 0.0,
        "lon": 0.0,
        "target": {"type": "planet", "id": "2"},
    }

    r1 = client.post("/api/v1/kp/chain", json=payload)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()

    # Response envelope and core keys
    data = j1.get("data", {})
    chain = data.get("chain", {})
    degrees = data.get("degrees", {})
    assert set(chain.keys()) == {"nl", "sl", "ssl"}
    assert all(isinstance(chain[k], int) and 1 <= chain[k] <= 9 for k in chain)
    assert 0.0 <= float(degrees.get("longitude", 0.0)) < 360.0

    # Determinism on same payload
    r2 = client.post("/api/v1/kp/chain", json=payload)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j1 == j2

