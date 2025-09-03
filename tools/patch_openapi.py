#!/usr/bin/env python3
"""
Patch the committed openapi.json to align with PM requirements when live export
is not available. This updates:
 - info.version
 - servers[0].url
 - Global bearer security scheme and default security
 - SSE endpoints to advertise text/event-stream and token query parameter

Usage:
  OPENAPI_VERSION=1.1.0 OPENAPI_PUBLIC_URL=/ python tools/patch_openapi.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def ensure_list(v):
    if isinstance(v, list):
        return v
    return [v]


def patch_sse_operation(op: dict) -> None:
    # Ensure 200 content advertises text/event-stream
    responses = op.setdefault("responses", {})
    resp200 = responses.setdefault("200", {})
    content = resp200.setdefault("content", {})
    content.pop("application/json", None)
    content["text/event-stream"] = {}
    # Ensure token query param is documented
    params = op.setdefault("parameters", [])
    has_token = any((p.get("name") == "token" and p.get("in") == "query") for p in params)
    if not has_token:
        params.append({
            "name": "token",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "JWT stream token (query param)"
        })


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    spec_path = root / "openapi.json"
    if not spec_path.exists():
        raise SystemExit(f"openapi.json not found at {spec_path}")
    spec = json.loads(spec_path.read_text())

    # Version
    version = os.getenv("OPENAPI_VERSION", "1.1.0")
    spec.setdefault("info", {})["version"] = version

    # Servers
    public_url = os.getenv("OPENAPI_PUBLIC_URL", "/")
    spec["servers"] = [{"url": public_url}]

    # Security schemes (bearer)
    components = spec.setdefault("components", {})
    sec_schemes = components.setdefault("securitySchemes", {})
    sec_schemes["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT"
    }
    # Apply global security (does not affect SSE token-based but OK)
    spec["security"] = [{"bearerAuth": []}]

    # SSE endpoints to patch
    sse_paths = [
        ("/stream/{topic}", "get"),
        ("/api/v1/stream", "get"),
        ("/api/v1/signals/stream/enhanced", "get"),
        ("/api/v1/location/features/stream", "get"),
        ("/api/v1/location/activation/stream", "get"),
    ]

    paths = spec.get("paths", {})
    for path, method in sse_paths:
        if path in paths and method in paths[path]:
            op = paths[path][method]
            if isinstance(op, dict):
                patch_sse_operation(op)

    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Patched OpenAPI spec written to {spec_path} (version={version}, servers[0].url={public_url})")


if __name__ == "__main__":
    main()

