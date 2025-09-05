from starlette.requests import Request
import asyncio

from api.middleware.usage_metering import UsageMeteringMiddleware


def make_request(path: str) -> Request:
    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': 'GET',
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode('utf-8'),
        'query_string': b'',
        'headers': [],
        'client': ('testclient', 12345),
        'server': ('testserver', 80),
    }
    return Request(scope)


async def _dummy_app(scope, receive, send):
    return


def test_compute_units_duration_thresholds():
    # Instantiate middleware (config/logging side effects are acceptable)
    mw = UsageMeteringMiddleware(_dummy_app, enable_metering=False)

    req = make_request('/api/v1/simple')

    # < 1s: no multiplier
    assert mw._calculate_compute_units(req, duration_ms=800, status_code=200) == 1.0

    # > 1s and <= 5s: 1.5x multiplier
    assert mw._calculate_compute_units(req, duration_ms=1500, status_code=200) == 1.5

    # > 5s: 2.0x multiplier (should not be shadowed by >1s branch)
    assert mw._calculate_compute_units(req, duration_ms=6000, status_code=200) == 2.0

