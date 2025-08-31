from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def test_ats_targets_accept_integers():
    r = client.post("/api/v1/ats/transit", json={"targets": [6, 5]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("targets") == [6, 5]


def test_ats_targets_accept_strict_symbols():
    r = client.post("/api/v1/ats/transit", json={"targets": ["VEN", "MER"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("targets") == [6, 5]


def test_ats_targets_reject_old_tokens():
    r = client.post("/api/v1/ats/transit", json={"targets": ["MERC", "MOON"]})
    assert r.status_code == 422

