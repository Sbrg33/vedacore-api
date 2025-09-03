"""
OpenAPI contract checks for SSE endpoints.

Validates that streaming routes advertise text/event-stream and
that query token parameter is documented where applicable.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def _get_openapi() -> dict:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def test_stream_topic_declares_event_stream():
    spec = _get_openapi()
    paths = spec.get("paths", {})
    assert "/stream/{topic}" in paths
    get_op = paths["/stream/{topic}"]["get"]
    # content type check
    assert "200" in get_op.get("responses", {})
    content = get_op["responses"]["200"].get("content", {})
    assert "text/event-stream" in content
    # token param exists
    params = get_op.get("parameters", [])
    assert any(p.get("name") == "token" and p.get("in") == "query" for p in params)


def test_location_features_stream_declares_event_stream():
    spec = _get_openapi()
    paths = spec.get("paths", {})
    path = "/api/v1/location/features/stream"
    if path in paths:
        get_op = paths[path]["get"]
        content = get_op.get("responses", {}).get("200", {}).get("content", {})
        assert "text/event-stream" in content


def test_v1_stream_declares_event_stream_if_present():
    spec = _get_openapi()
    paths = spec.get("paths", {})
    path = "/api/v1/stream"
    if path in paths:
        get_op = paths[path]["get"]
        content = get_op.get("responses", {}).get("200", {}).get("content", {})
        assert "text/event-stream" in content

