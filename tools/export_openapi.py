#!/usr/bin/env python3
"""
Export OpenAPI schema to openapi.json.

Usage:
  - From a running API (preferred):
      python tools/export_openapi.py --base http://127.0.0.1:8000 --out openapi.json

  - From local app import (requires FastAPI + project deps installed):
      python tools/export_openapi.py --local --out openapi.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen, Request


def fetch_from_base(base: str) -> dict:
    url = base.rstrip("/") + "/openapi.json"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=10) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def build_local() -> dict:
    # Import app and build schema
    # Requires FastAPI and project dependencies installable in this environment.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from apps.api.main import app  # type: ignore

    return app.openapi()


def main() -> int:
    ap = argparse.ArgumentParser(description="Export VedaCore OpenAPI schema")
    ap.add_argument("--base", help="Base URL of a running API (e.g. http://127.0.0.1:8000)")
    ap.add_argument("--local", action="store_true", help="Build schema by importing app locally")
    ap.add_argument("--out", default="openapi.json", help="Output file path")
    args = ap.parse_args()

    if not args.base and not args.local:
        ap.error("Provide --base or --local")

    if args.base:
        spec = fetch_from_base(args.base)
    else:
        spec = build_local()

    out = Path(args.out)
    out.write_text(json.dumps(spec, indent=2))
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

