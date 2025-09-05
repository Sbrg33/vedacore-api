from starlette.responses import Response

from api.middleware.usage_metering import UsageMeteringMiddleware


async def _dummy_app(scope, receive, send):
    return


def test_rate_limit_reset_rollover(monkeypatch):
    # Monkeypatch datetime.now in the usage_metering module to 23:30 UTC
    import api.middleware.usage_metering as um
    from datetime import datetime, timezone, timedelta

    class FakeDT:
        @staticmethod
        def now(tz=None):
            return datetime(2025, 1, 1, 23, 30, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(um, "datetime", FakeDT)

    mw = UsageMeteringMiddleware(_dummy_app, enable_metering=False)
    resp = Response(content=b"ok", status_code=200)
    out = mw._add_rate_limit_headers(resp, {"tenant_id": "t"})
    reset = int(out.headers.get("X-RateLimit-Reset"))
    expected = int(((datetime(2025, 1, 1, 23, 30, 0, tzinfo=timezone.utc) + timedelta(hours=1))
                    .replace(minute=0, second=0, microsecond=0)).timestamp())
    assert reset == expected

