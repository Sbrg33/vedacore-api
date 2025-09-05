import asyncio
from datetime import datetime, timezone

import pytest
from starlette.requests import Request
from starlette.responses import Response

from api.middleware.usage_metering import UsageMeteringMiddleware
from api.services.rate_limiter import rate_limiter


def make_request(path: str = "/api/v1/simple") -> Request:
    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': 'GET',
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode('utf-8'),
        'query_string': b'',
        'headers': [(b'authorization', b'')],
        'client': ('testclient', 12345),
        'server': ('testserver', 80),
    }
    return Request(scope)


async def _dummy_app(scope, receive, send):
    return


@pytest.mark.asyncio
async def test_emit_usage_event_persists(monkeypatch):
    mw = UsageMeteringMiddleware(_dummy_app, enable_metering=True)

    recorded = {}

    async def fake_insert(event):
        recorded.update(event)

    monkeypatch.setattr(mw, "_insert_usage_event", fake_insert)

    req = make_request()
    await mw._emit_usage_event(
        request=req,
        response=Response(content=b"ok", status_code=200),
        tenant_info={"tenant_id": "t1", "api_key_id": "a1"},
        timestamp=datetime.now(timezone.utc),
        duration_ms=123,
        bytes_in=10,
        bytes_out=20,
        status_code=200,
    )

    assert recorded.get("tenant_id") == "t1"
    assert recorded.get("status_code") == 200
    assert recorded.get("duration_ms") == 123


@pytest.mark.asyncio
async def test_emit_usage_event_failure_non_blocking(monkeypatch):
    mw = UsageMeteringMiddleware(_dummy_app, enable_metering=True)

    async def failing_insert(event):
        raise RuntimeError("DB down")

    monkeypatch.setattr(mw, "_insert_usage_event", failing_insert)

    req = make_request()
    # Should not raise despite insert failure
    await mw._emit_usage_event(
        request=req,
        response=Response(content=b"ok", status_code=200),
        tenant_info={"tenant_id": "t2", "api_key_id": "a2"},
        timestamp=datetime.now(timezone.utc),
        duration_ms=50,
        bytes_in=1,
        bytes_out=2,
        status_code=200,
    )


import pytest


@pytest.mark.asyncio
async def test_rate_limit_headers_reflect_remaining_tokens():
    mw = UsageMeteringMiddleware(_dummy_app, enable_metering=False)
    resp = Response(content=b"ok", status_code=200)

    tenant = "tenant_headers"
    # Configure limits and bucket state
    limits = rate_limiter._limits[tenant]
    limits.qps_limit = 15
    limits.burst_limit = 20
    bucket = limits.get_qps_bucket()
    bucket.tokens = 7.0
    bucket.last_update = __import__('time').monotonic()

    resp = await mw._add_rate_limit_headers(resp, {"tenant_id": tenant})
    assert resp.headers.get("X-RateLimit-Limit") == "15"
    remaining = int(resp.headers.get("X-RateLimit-Remaining", "0"))
    assert remaining >= 7  # may increment slightly due to timing

    # Different tenant with different state
    resp2 = Response(content=b"ok", status_code=200)
    tenant2 = "tenant_headers_2"
    limits2 = rate_limiter._limits[tenant2]
    limits2.qps_limit = 9
    limits2.burst_limit = 9
    bucket2 = limits2.get_qps_bucket()
    bucket2.tokens = 2.0
    bucket2.last_update = __import__('time').monotonic()
    resp2 = await mw._add_rate_limit_headers(resp2, {"tenant_id": tenant2})
    assert resp2.headers.get("X-RateLimit-Limit") == "9"
    remaining2 = int(resp2.headers.get("X-RateLimit-Remaining", "0"))
    assert remaining2 >= 2
