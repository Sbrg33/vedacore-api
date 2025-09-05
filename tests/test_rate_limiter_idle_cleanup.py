import pytest


def test_idle_tenant_cleanup_with_refilled_bucket(monkeypatch):
    """Tenants with refilled buckets are pruned after idle TTL.

    Simulates elapsed time beyond IDLE_TTL_SECONDS and ensures that after
    refreshing bucket state, the cleanup removes tenant entries when
    defaults are in use and there are no active connections.
    """
    import api.services.rate_limiter as rl

    r = rl.RateLimiter()
    tenant = "tenant_idle_cleanup"

    # Create limits and bucket for tenant
    limits = r._limits[tenant]
    limits.active_connections = 0
    limits.qps_limit = rl.DEFAULT_QPS_LIMIT
    limits.connection_limit = rl.DEFAULT_CONNECTION_LIMIT
    limits.burst_limit = rl.DEFAULT_BURST_LIMIT
    bucket = limits.get_qps_bucket()

    # Control time via monkeypatching time.monotonic used in the module
    base = [1000.0]
    monkeypatch.setattr(rl.time, "monotonic", lambda: base[0])

    # Start with empty bucket and old last_activity
    bucket.tokens = 0.0
    bucket.last_update = base[0]
    limits.last_activity = base[0]

    # Advance time beyond idle TTL so bucket refills to full and tenant becomes stale
    base[0] = base[0] + rl.IDLE_TTL_SECONDS + 1.0

    # Trigger cleanup path explicitly
    r._maybe_cleanup_tenant(tenant)

    # Expect tenant state to be pruned
    assert tenant not in r._limits
    assert tenant not in r._locks

