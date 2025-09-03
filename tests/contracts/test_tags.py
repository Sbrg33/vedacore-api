from __future__ import annotations

from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def test_tags_are_normalized():
    r = client.get("/openapi.json")
    spec = r.json()
    allowed = {
        "kp",
        "varga",
        "fortuna",
        "tara",
        "dasha",
        "nodes",
        "moon",
        "eclipse",
        "micro",
        "houses",
        "transit",
        "ats",
        "atlas",
        "panchanga",
        "stream",
        "ws",
        "auth",
        "health",
        "reference",
        "strategy",
        "location",
        "signals",
        "advisory",
        "kp-horary",
        "kp-ruling-planets",
        "enhanced-signals",
    }
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            tags = set(op.get("tags", []))
            assert tags, f"Missing tags for {path} {method}"
            assert tags <= allowed, f"Unexpected tags {tags - allowed} on {path} {method}"


def test_kp_router_has_problem_docs():
    r = client.get("/openapi.json")
    spec = r.json()
    path = "/api/v1/kp/analysis"
    op = spec["paths"][path]["post"]
    responses = op.get("responses", {})
    # Router-level defaults apply
    assert "401" in responses
    assert "429" in responses
