from __future__ import annotations

import pytest


def _has_json_200(path_item: dict, method: str) -> bool:
    try:
        resp = path_item[method]["responses"]["200"]["content"]
        return any(k.lower().startswith("application/json") for k in resp.keys())
    except Exception:
        return False


def test_openapi_includes_representative_routes(openapi_spec):
    spec = openapi_spec
    paths = spec.get("paths", {})

    # Representative endpoints updated with response models
    expected = {
        ("/api/v1/health/live", "get"),
        ("/api/v1/ats/transit", "post"),
        ("/api/v1/panchanga/calculate", "post"),
    }

    for route, method in expected:
        assert route in paths, f"Missing route in OpenAPI: {route}"
        assert _has_json_200(paths[route], method), f"Missing 200 application/json for {route}"
