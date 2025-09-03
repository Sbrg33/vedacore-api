#!/usr/bin/env python3
"""
Export the live OpenAPI schema from the FastAPI app to ./openapi.json

Usage:
  PYTHONPATH=./src:. OPENAPI_VERSION=1.1.2 OPENAPI_PUBLIC_URL=https://api.vedacore.io \
    python tools/export_openapi.py

Honors environment-based customizations in apps.api.main.custom_openapi.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> None:
    # Ensure env defaults
    os.environ.setdefault("ENVIRONMENT", "development")
    # Import app after env so custom_openapi picks it up
    from apps.api.main import app  # type: ignore

    client = TestClient(app)
    r = client.get("/openapi.json")
    r.raise_for_status()
    spec = r.json()

    out = Path(__file__).resolve().parents[1] / "openapi.json"
    out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Wrote OpenAPI to {out} (version={spec.get('info',{}).get('version')})")


if __name__ == "__main__":
    main()
