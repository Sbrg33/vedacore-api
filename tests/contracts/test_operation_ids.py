from __future__ import annotations

from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def _openapi() -> dict:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def test_operation_ids_unique():
    spec = _openapi()
    op_ids = []
    for path_item in spec.get("paths", {}).values():
        for op in path_item.values():
            if isinstance(op, dict):
                oid = op.get("operationId")
                assert oid, "Missing operationId"
                op_ids.append(oid)
    assert len(op_ids) == len(set(op_ids)), "Duplicate operationIds found"


def test_sse_contracts_have_token_param():
    spec = _openapi()
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            content = op.get("responses", {}).get("200", {}).get("content", {})
            if "text/event-stream" in content:
                params = op.get("parameters", [])
                assert any(
                    p.get("name") == "token" and p.get("in") == "query"
                    for p in params
                ), f"SSE route {path} missing token query param in OpenAPI"


def test_basic_openapi_metadata_present():
    spec = _openapi()
    # Servers URL present
    servers = spec.get("servers", [])
    assert servers and isinstance(servers[0].get("url"), str) and servers[0]["url"]
    info = spec.get("info", {})
    assert info.get("version"), "API version must be set"


def test_sse_has_429_problem_docs():
    spec = _openapi()
    # Check known SSE paths
    for path in ["/stream/{topic}", "/signals/stream/enhanced"]:
        if path in spec.get("paths", {}):
            op = spec["paths"][path]["get"]
            responses = op.get("responses", {})
            if "429" in responses:
                headers = responses["429"].get("headers", {})
                assert "Retry-After" in headers


def test_200_201_json_have_schema():
    spec = _openapi()
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            for status in ("200", "201"):
                resp = op.get("responses", {}).get(status)
                if not resp:
                    continue
                content = resp.get("content", {})
                # Skip non-JSON or pure text endpoints
                if "application/json" in content:
                    schema = content["application/json"].get("schema")
                    assert schema is not None, f"Missing schema for {path} {method} {status}"
