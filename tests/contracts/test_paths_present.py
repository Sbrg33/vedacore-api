from __future__ import annotations

def test_critical_paths_present(openapi_spec) -> None:
    spec = openapi_spec
    paths = set(spec.get("paths", {}).keys())
    expected = {
        "/api/v1/stream/topics",
        "/api/v1/kp/analysis",
        "/stream/_resume",
        "/stream/_topics",
    }
    missing = expected - paths
    assert not missing, f"Missing expected paths in OpenAPI: {sorted(missing)}"
