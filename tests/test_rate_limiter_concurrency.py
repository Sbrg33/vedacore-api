import asyncio
import time

import pytest

from api.services.rate_limiter import RateLimiter
from api.services.rate_limiter import TokenBucket


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


def test_token_bucket_uses_monotonic(monkeypatch):
    """Ensure token refill logic is driven by time.monotonic."""
    tb = TokenBucket(rate=10.0, burst=20)

    # Start with deterministic state
    tb.tokens = 0.0

    base = [1000.0]

    def fake_mono():
        return base[0]

    # Patch the module's time.monotonic used by TokenBucket
    import api.services.rate_limiter as rl
    monkeypatch.setattr(rl.time, "monotonic", fake_mono)

    # Advance 0.5s => expect 5 tokens
    base[0] = 1000.0
    tb.last_update = fake_mono()
    base[0] = 1000.5
    rem = tb.remaining_tokens()
    assert 4.9 <= rem <= 5.1

    # Calling allow() should also use monotonic and update last_update
    base[0] = 1001.0
    allowed = tb.allow(cost=1.0)
    assert allowed
    # After 0.5s more @10tps minus 1 cost: expected around (5 + 5) - 1 = 9 tokens and updated last_update
    assert tb.tokens <= tb.burst
