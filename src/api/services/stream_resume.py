"""
Redis-backed resume store for SSE replay (Upstash-friendly).

Uses a sorted set per topic keyed by monotonically increasing sequence ids.
Replay queries use ZRANGEBYSCORE (last_seq, +inf) LIMIT 0 N for efficient fetch.

Environment:
- STREAM_RESUME_BACKEND: auto|redis|memory (default: auto)
- STREAM_RESUME_TTL_SECONDS: int (default: 3600)
- STREAM_RESUME_MAX_ITEMS: int (default: 5000)
- STREAM_RESUME_REDIS_PREFIX: string (default: sse:resume:)

If REDIS_URL is set, auto prefers redis. Works with Upstash (managed Redis);
CONFIG SET is never used here.
"""

from __future__ import annotations

import os
from typing import List, Optional

try:
    from redis.asyncio import Redis  # type: ignore
except Exception:  # pragma: no cover
    Redis = object  # sentinel

from .redis_config import get_redis


class RedisResumeStore:
    def __init__(self, client: Redis, *, prefix: str, ttl: int, max_items: int):
        self.client = client
        self.prefix = prefix.rstrip(":") + ":"
        self.ttl = ttl
        self.max_items = max_items

    def _key(self, topic: str) -> str:
        return f"{self.prefix}{topic}"

    async def store(self, topic: str, seq: int, data: str) -> None:
        key = self._key(topic)
        # ZADD score=seq, member=data
        await self.client.zadd(key, {data: float(seq)})
        # Trim if too large
        try:
            size = await self.client.zcard(key)
            if size and size > self.max_items:
                # Remove oldest (low scores) to keep last max_items
                remove_count = int(size - self.max_items)
                if remove_count > 0:
                    await self.client.zremrangebyrank(key, 0, remove_count - 1)
        except Exception:
            # Non-fatal
            pass
        # Refresh TTL
        try:
            await self.client.expire(key, self.ttl)
        except Exception:
            pass

    async def replay_since(self, topic: str, last_seq: int, limit: int = 500) -> List[str]:
        key = self._key(topic)
        try:
            # Exclusive lower bound on last_seq
            return await self.client.zrangebyscore(key, f"({last_seq}", "+inf", start=0, num=limit)  # type: ignore
        except Exception:
            return []

    async def stats(self, topic: str) -> dict:
        """Return basic stats: size, min_seq, max_seq for a topic."""
        key = self._key(topic)
        try:
            size = await self.client.zcard(key)  # type: ignore
            min_seq = None
            max_seq = None
            try:
                first = await self.client.zrange(key, 0, 0, withscores=True)  # type: ignore
                last = await self.client.zrange(key, -1, -1, withscores=True)  # type: ignore
                if first:
                    min_seq = int(first[0][1])
                if last:
                    max_seq = int(last[0][1])
            except Exception:
                pass
            return {"size": int(size or 0), "min_seq": min_seq, "max_seq": max_seq}
        except Exception:
            return {"size": 0, "min_seq": None, "max_seq": None}


_resume_backend: Optional[str] = None
_resume_store: Optional[RedisResumeStore] = None


async def get_resume_store() -> Optional[RedisResumeStore]:
    """Create or return Redis resume store if configured and available."""
    global _resume_backend, _resume_store
    if _resume_store is not None:
        return _resume_store

    backend = (os.getenv("STREAM_RESUME_BACKEND", "auto").strip().lower() or "auto")
    _resume_backend = backend

    # Prefer Redis if REDIS_URL present or backend=redis
    prefer_redis = backend == "redis" or (
        backend == "auto" and bool(os.getenv("REDIS_URL"))
    )
    if not prefer_redis:
        return None

    try:
        redis_mgr = await get_redis()
        client = await redis_mgr.get_client()
        prefix = os.getenv(
            "STREAM_RESUME_REDIS_PREFIX",
            f"sse:resume:{os.getenv('VC_ENV','local')}:",
        )
        ttl = int(os.getenv("STREAM_RESUME_TTL_SECONDS", "3600"))
        max_items = int(os.getenv("STREAM_RESUME_MAX_ITEMS", "5000"))
        _resume_store = RedisResumeStore(client, prefix=prefix, ttl=ttl, max_items=max_items)
        return _resume_store
    except Exception:
        # Fallback to memory (handled by stream_manager)
        return None
