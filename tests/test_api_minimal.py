"""
Minimal API smoke checks to verify lean build health without bloat.

Focuses on availability endpoints to keep the suite fast and robust.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from apps.api.main import app
client = TestClient(app)


def _is_angle(v: float) -> bool:
    return isinstance(v, (int, float)) and 0.0 <= float(v) < 360.0


def test_docs_and_metrics_accessible():
    docs = client.get("/api/docs")
    metrics = client.get("/metrics")
    assert docs.status_code in (200, 308)
    assert metrics.status_code == 200


def test_health_ready_endpoint_responds():
    # Ensure readiness endpoint responds with 200 or 503
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code in (200, 503)


    # Nodes and dasha are validated in the full suite; omitted here to keep lean


def test_root_info():
    r = client.get("/")
    assert r.status_code == 200
    info = r.json()
    assert info.get("name")
