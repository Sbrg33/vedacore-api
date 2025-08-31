#!/usr/bin/env python3
"""
Portable API health check helper.

Design goals:
- Trackable (lives in repo), no DigitalOcean coupling.
- Plain Python (stdlib), no extra deps.
- Prefers plaintext liveness (/api/v1/health/up), falls back to readiness.
- Machine-friendly output with exit codes for CI/ops.

Usage examples:
  # Local default (http://127.0.0.1:8000)
  python tools/check_api_health.py

  # Custom base URL
  python tools/check_api_health.py --base https://api.vedacore.io

  # JSON output for scripts
  python tools/check_api_health.py --base https://api.vedacore.io --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _get(url: str, timeout: float) -> tuple[int, bytes, float]:
    start = time.time()
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:  # nosec B310
            body = resp.read() or b""
            code = getattr(resp, "status", 0) or 0
    except HTTPError as e:
        body = e.read() or b""
        code = e.code
    except URLError:
        return 0, b"", 0.0
    except Exception:
        return 0, b"", 0.0
    latency = time.time() - start
    return int(code), body, float(latency)


def check_health(base: str, timeout: float = 5.0) -> dict:
    base = base.rstrip("/")

    # 1) Prefer plaintext liveness
    code, body, lat = _get(f"{base}/api/v1/health/up", timeout)
    if code == 200 and (body.strip() == b"ok" or body.strip() == b"OK"):
        return {
            "ok": True,
            "endpoint": "/api/v1/health/up",
            "status_code": code,
            "latency_sec": round(lat, 3),
            "detail": "ok",
        }

    # 2) Fallback to readiness JSON
    code, body, lat = _get(f"{base}/api/v1/health/ready", timeout)
    detail = None
    try:
        j = json.loads(body.decode("utf-8")) if body else {}
        detail = j.get("status")
    except Exception:
        detail = None

    if code == 200 and detail == "ready":
        return {
            "ok": True,
            "endpoint": "/api/v1/health/ready",
            "status_code": code,
            "latency_sec": round(lat, 3),
            "detail": detail,
        }

    return {
        "ok": False,
        "endpoint": "/api/v1/health/up"
        if code == 200
        else "/api/v1/health/ready",
        "status_code": code,
        "latency_sec": round(lat, 3),
        "detail": detail or (body.decode("utf-8", "ignore")[:120] if body else None),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="VedaCore API health check")
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8000",
        help="Base URL (default: http://127.0.0.1:8000)",
    )
    ap.add_argument("--timeout", type=float, default=5.0, help="Per-request timeout seconds")
    ap.add_argument("--json", action="store_true", help="Emit JSON output")
    args = ap.parse_args()

    result = check_health(args.base, timeout=args.timeout)

    if args.json:
        print(json.dumps(result))
    else:
        status = "OK" if result["ok"] else "FAIL"
        print(
            f"[{status}] {result['endpoint']} code={result['status_code']} "
            f"latency={result['latency_sec']}s detail={result.get('detail')}"
        )

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

