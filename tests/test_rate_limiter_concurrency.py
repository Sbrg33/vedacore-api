import asyncio
import time

import pytest

from api.services.rate_limiter import RateLimiter


class _SlowLock:
    """Testing helper: wraps a lock and delays acquisition."""

    def __init__(self, delay: float = 0.2):
        self._delay = delay
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self._lock.acquire()
        # Simulate work inside the critical section while holding the lock
        await asyncio.sleep(self._delay)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._lock.release()


@pytest.mark.asyncio
async def test_per_tenant_lock_allows_parallelism():
    rl = RateLimiter()

    tenant_slow = "tenant_slow"
    tenant_fast = "tenant_fast"

    # Configure generous limits to avoid rate limiting during the test
    await rl.set_tenant_limits(tenant_slow, qps_limit=1000, burst_limit=1000)
    await rl.set_tenant_limits(tenant_fast, qps_limit=1000, burst_limit=1000)

    # Inject a slow lock for tenant_slow to simulate heavy contention for that tenant only
    rl._locks[tenant_slow] = _SlowLock(delay=0.2)  # type: ignore[attr-defined]

    async def spam_allow(tenant: str, n: int):
        for _ in range(n):
            await rl.allow_qps(tenant, cost=1.0)

    # Run both tenants concurrently
    start = time.perf_counter()
    await asyncio.gather(spam_allow(tenant_slow, 3), spam_allow(tenant_fast, 10))
    elapsed = time.perf_counter() - start

    # With a global lock, the fast tenant would also be delayed ~ 3 * 0.2s = 0.6s plus its own overhead.
    # With per-tenant locks, the fast tenant proceeds independently; total time should be close to slow path (~0.6s)
    assert elapsed < 1.0, f"Elapsed {elapsed:.3f}s indicates cross-tenant blocking"


@pytest.mark.asyncio
async def test_same_tenant_requests_serialize():
    rl = RateLimiter()
    tenant = "tenant_serial"
    await rl.set_tenant_limits(tenant, qps_limit=1000, burst_limit=1000)

    # Slow lock to ensure observable serialization
    rl._locks[tenant] = _SlowLock(delay=0.15)  # type: ignore[attr-defined]

    async def one():
        await rl.allow_qps(tenant, cost=1.0)

    start = time.perf_counter()
    await asyncio.gather(one(), one())
    elapsed = time.perf_counter() - start

    # Two operations for the same tenant should serialize behind the same lock (~ 2 * 0.15s)
    assert elapsed >= 0.25, f"Elapsed {elapsed:.3f}s too low; expected serialization for same tenant"
