"""
rate_limiter.py — Token bucket rate limiting for VedaCore streaming.

Features:
- Per-tenant QPS (queries per second) limits
- Per-tenant connection limits
- Token bucket algorithm with burst allowance
- Thread-safe operation with asyncio locks
- Usage event logging for 429 responses
- Redis backend with in-memory fallback (PM requirement)

Usage:
- Check connection limits before allowing SSE/WebSocket connections
- Check QPS limits on message publishing and API calls
- Log rate limit violations for billing/abuse analysis
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Import cache backend for Redis support (PM requirement)
try:
    from app.services.cache_backend import get_cache_backend
    CACHE_BACKEND_AVAILABLE = True
except ImportError:
    CACHE_BACKEND_AVAILABLE = False

# Import metrics for monitoring
try:
    from .metrics import streaming_metrics

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# Configuration from environment
DEFAULT_QPS_LIMIT = int(os.getenv("STREAM_RATE_LIMIT_QPS", "10"))
DEFAULT_CONNECTION_LIMIT = int(os.getenv("STREAM_RATE_LIMIT_CONNECTIONS", "5"))
DEFAULT_BURST_LIMIT = int(os.getenv("STREAM_RATE_LIMIT_BURST", "20"))
# Idle TTL (seconds) after which inactive tenants can be pruned
IDLE_TTL_SECONDS = float(os.getenv("RATE_LIMITER_IDLE_TTL", "600"))  # 10 minutes default


@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting with burst allowance.

    PM-provided implementation with precise timing.
    """

    rate: float  # tokens per second
    burst: int  # maximum burst capacity
    tokens: float = 0.0
    last_update: float = 0.0

    def __post_init__(self):
        """Initialize with full burst capacity."""
        self.tokens = float(self.burst)
        # Use monotonic clock to avoid drift from system time changes
        self.last_update = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        """
        Check if request can be allowed (PM-specified algorithm).

        Returns True if request allowed, False if rate limited.
        """
        # Monotonic time for stable elapsed calculations
        now = time.monotonic()

        # Refill tokens based on elapsed time
        elapsed = now - self.last_update
        self.tokens = min(self.burst, self.tokens + (elapsed * self.rate))
        self.last_update = now

        # Check if enough tokens available
        if self.tokens >= cost:
            self.tokens -= cost
            return True

        return False

    def remaining_tokens(self) -> float:
        """Get remaining tokens after refill and update bucket state."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.burst, self.tokens + (elapsed * self.rate))
        self.last_update = now
        return self.tokens


@dataclass
class TenantLimits:
    """Rate limits configuration for a tenant."""

    qps_limit: float
    connection_limit: int
    burst_limit: int

    # Token buckets (created on demand)
    qps_bucket: TokenBucket | None = None

    # Connection tracking
    active_connections: int = 0
    # Last activity timestamp (monotonic seconds)
    last_activity: float = 0.0

    def get_qps_bucket(self) -> TokenBucket:
        """Get or create QPS token bucket."""
        if self.qps_bucket is None:
            self.qps_bucket = TokenBucket(rate=self.qps_limit, burst=self.burst_limit)
        return self.qps_bucket


class RateLimiter:
    """
    Multi-tenant rate limiter with connection and QPS limits.

    Enforces:
    - Per-tenant QPS limits on API calls and streaming messages
    - Per-tenant connection limits for SSE and WebSocket connections
    - Burst allowance for temporary spikes
    - Usage logging for billing and abuse analysis
    """

    def __init__(self) -> None:
        self._limits: dict[str, TenantLimits] = defaultdict(self._default_limits)
        # Per-tenant locks to avoid cross-tenant contention
        self._locks: dict[str, asyncio.Lock] = {}
        self._metrics = {
            "qps_violations": 0,
            "connection_violations": 0,
            "total_checks": 0,
        }

    def _default_limits(self) -> TenantLimits:
        """Create default limits for new tenants."""
        return TenantLimits(
            qps_limit=DEFAULT_QPS_LIMIT,
            connection_limit=DEFAULT_CONNECTION_LIMIT,
            burst_limit=DEFAULT_BURST_LIMIT,
        )

    async def allow_qps(self, tenant_id: str, cost: float = 1.0) -> bool:
        """
        Check if QPS request is allowed for tenant.

        Use for:
        - API endpoint calls
        - Message publishing operations
        - Stream subscription requests
        """
        lock = self._locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            limits = self._limits[tenant_id]
            bucket = limits.get_qps_bucket()
            self._metrics["total_checks"] += 1

            allowed = bucket.allow(cost)
            if not allowed:
                self._metrics["qps_violations"] += 1
                logger.warning(f"QPS limit exceeded for tenant {tenant_id}")

                # Record metrics
                if METRICS_AVAILABLE:
                    streaming_metrics.record_rate_limit_violation(
                        tenant_id, "qps", "api_call"
                    )
            else:
                # Update current usage percentage
                if METRICS_AVAILABLE:
                    remaining_tokens = bucket.remaining_tokens()
                    usage_percent = max(
                        0,
                        (limits.burst_limit - remaining_tokens)
                        / limits.burst_limit
                        * 100,
                    )
                    streaming_metrics.update_rate_limit_usage(
                        tenant_id, "qps", usage_percent
                    )

            # Update last activity timestamp and attempt cleanup if idle
            limits.last_activity = time.monotonic()
            self._maybe_cleanup_tenant(tenant_id, limits)

            return allowed

    async def allow_connection(self, tenant_id: str) -> bool:
        """
        Check if new connection is allowed for tenant.

        Use for:
        - SSE connection establishment
        - WebSocket connection establishment
        """
        lock = self._locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            limits = self._limits[tenant_id]
            self._metrics["total_checks"] += 1

            if limits.active_connections >= limits.connection_limit:
                self._metrics["connection_violations"] += 1
                logger.warning(f"Connection limit exceeded for tenant {tenant_id}")

                # Record metrics
                if METRICS_AVAILABLE:
                    streaming_metrics.record_rate_limit_violation(
                        tenant_id, "connection", "streaming"
                    )

                return False

            # Update connection usage percentage
            if METRICS_AVAILABLE:
                usage_percent = (
                    limits.active_connections / limits.connection_limit
                ) * 100
                streaming_metrics.update_rate_limit_usage(
                    tenant_id, "connection", usage_percent
                )

            return True

    async def add_connection(self, tenant_id: str) -> None:
        """Register a new active connection for tenant."""
        lock = self._locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            limits = self._limits[tenant_id]
            limits.active_connections += 1
            limits.last_activity = time.monotonic()

    async def remove_connection(self, tenant_id: str) -> None:
        """Remove an active connection for tenant."""
        lock = self._locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            limits = self._limits.get(tenant_id)
            if not limits:
                return
            if limits.active_connections > 0:
                limits.active_connections -= 1
            # Attempt cleanup of idle tenant state when back to defaults
            self._maybe_cleanup_tenant(tenant_id, limits)

    def _maybe_cleanup_tenant(self, tenant_id: str, limits: TenantLimits | None = None) -> None:
        """Prune idle tenant state to prevent unbounded growth.

        Removes entries when:
        - active_connections == 0
        - limits equal defaults (no custom overrides)
        - qps_bucket not instantiated (transient state)
        """
        try:
            l = limits or self._limits.get(tenant_id)
            if not l:
                return
            no_custom = (
                l.qps_limit == DEFAULT_QPS_LIMIT and
                l.connection_limit == DEFAULT_CONNECTION_LIMIT and
                l.burst_limit == DEFAULT_BURST_LIMIT
            )
            idle = l.active_connections == 0
            now = time.monotonic()
            bucket_absent = (l.qps_bucket is None)
            bucket_inactive = False
            if l.qps_bucket is not None:
                # Refresh bucket to account for elapsed time before evaluating fullness
                prev_last_update = l.qps_bucket.last_update
                try:
                    current_tokens = float(l.qps_bucket.remaining_tokens())
                except Exception:
                    current_tokens = l.qps_bucket.tokens
                # Consider bucket inactive if fully refilled and idle beyond TTL
                tokens_full = current_tokens >= float(l.burst_limit)
                # Use the pre-refresh timestamp to evaluate idleness window
                bucket_idle = (now - prev_last_update) > IDLE_TTL_SECONDS
                bucket_inactive = tokens_full and bucket_idle
            became_stale = (now - (l.last_activity or now)) > IDLE_TTL_SECONDS
            if idle and no_custom and (bucket_absent or bucket_inactive) and became_stale:
                self._limits.pop(tenant_id, None)
                self._locks.pop(tenant_id, None)
        except Exception:
            # Never raise during cleanup
            pass

    async def snapshot_limits(self, tenant_id: str) -> tuple[int | None, float | None]:
        """Safely snapshot current QPS limit and remaining tokens for a tenant.

        Does not implicitly create new tenant entries. Returns (limit, remaining)
        or (None, None) if tenant does not exist.
        """
        limits = self._limits.get(tenant_id)
        if not limits:
            return (None, None)
        lock = self._locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            limit = int(limits.qps_limit)
            bucket = limits.qps_bucket
            if bucket is not None:
                remaining = max(0.0, float(bucket.remaining_tokens()))
            else:
                remaining = float(limits.burst_limit)
            return (limit, remaining)

    async def set_tenant_limits(
        self,
        tenant_id: str,
        *,
        qps_limit: float | None = None,
        connection_limit: int | None = None,
        burst_limit: int | None = None,
    ) -> None:
        """Update rate limits for a specific tenant."""
        lock = self._locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            limits = self._limits[tenant_id]

            if qps_limit is not None:
                limits.qps_limit = qps_limit
                # Reset bucket to apply new rate
                limits.qps_bucket = None

            if connection_limit is not None:
                limits.connection_limit = connection_limit

            if burst_limit is not None:
                limits.burst_limit = burst_limit
                # Reset bucket to apply new burst
                limits.qps_bucket = None

    async def get_tenant_status(self, tenant_id: str) -> dict[str, Any]:
        """Get current rate limiting status for tenant."""
        lock = self._locks.setdefault(tenant_id, asyncio.Lock())
        async with lock:
            limits = self._limits[tenant_id]
            bucket = limits.get_qps_bucket()

            return {
                "tenant_id": tenant_id,
                "qps_limit": limits.qps_limit,
                "connection_limit": limits.connection_limit,
                "burst_limit": limits.burst_limit,
                "active_connections": limits.active_connections,
                "remaining_tokens": bucket.remaining_tokens(),
                "connection_available": limits.active_connections
                < limits.connection_limit,
            }

    def get_metrics(self) -> dict[str, Any]:
        """Get rate limiter metrics."""
        return {
            **self._metrics,
            "total_tenants": len(self._limits),
            "total_connections": sum(
                l.active_connections for l in self._limits.values()
            ),
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


# -------------------- FastAPI Integration --------------------


async def check_qps_limit(tenant_id: str, cost: float = 1.0) -> None:
    """
    FastAPI dependency to check QPS limits.

    Raises HTTPException(429) if rate limited.
    """
    from fastapi import HTTPException

    if not await rate_limiter.allow_qps(tenant_id, cost):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(DEFAULT_QPS_LIMIT),
                "X-RateLimit-Reset": str(int(time.time() + 60)),
                "Retry-After": "60",
            },
        )


async def check_connection_limit(tenant_id: str) -> None:
    """
    FastAPI dependency to check connection limits.

    Raises HTTPException(429) if connection limit exceeded.
    """
    from fastapi import HTTPException

    if not await rate_limiter.allow_connection(tenant_id):
        raise HTTPException(
            status_code=429,
            detail="Connection limit exceeded",
            headers={
                "X-RateLimit-Limit": str(DEFAULT_CONNECTION_LIMIT),
                "X-RateLimit-Reset": str(int(time.time() + 60)),
                "Retry-After": "60",
            },
        )


# -------------------- Usage Logging --------------------


async def log_rate_limit_violation(
    tenant_id: str,
    limit_type: str,  # "qps" or "connection"
    endpoint: str,
    **metadata: Any,
) -> None:
    """
    Log rate limit violation for billing/abuse analysis.

    TODO: Integrate with metering.usage_events table
    """
    logger.warning(
        "Rate limit violation",
        extra={
            "tenant_id": tenant_id,
            "limit_type": limit_type,
            "endpoint": endpoint,
            "timestamp": time.time(),
            **metadata,
        },
    )

    # TODO: Async write to metering.usage_events
    # await write_usage_event({
    #     "tenant_id": tenant_id,
    #     "endpoint": endpoint,
    #     "status_code": 429,
    #     "meta": {"kind": "rate_limit", "limit_type": limit_type, **metadata}
    # })
