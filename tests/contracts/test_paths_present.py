from __future__ import annotations

from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def test_critical_paths_present() -> None:
    resp = client.get("/openapi.json")
    resp.raise_for_status()
    spec = resp.json()
    paths = set(spec.get("paths", {}).keys())
    expected = {
        "/api/v1/stream/topics",
        "/api/v1/kp/analysis",
        "/stream/_resume",
        "/stream/_topics",
    }
    missing = expected - paths
    assert not missing, f"Missing expected paths in OpenAPI: {sorted(missing)}"

