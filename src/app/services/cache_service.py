#!/usr/bin/env python3
"""
Cache service for storing computed results
Uses JSON files for simplicity, can be replaced with Redis later

DEPRECATED: Use unified_cache.py for new code - provides environment-driven
Redis (production) vs file cache (development) selection per PM requirements.
"""

import asyncio
import json
import logging

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.utils.hash_keys import cache_key_hash

logger = logging.getLogger(__name__)


class CacheService:
    """
    Simple file-based cache service with multi-system support

    Features:
    - JSON file storage in data/cache/{system}/ directory
    - TTL-based expiration
    - Async-safe operations
    - Automatic cleanup of expired entries
    - System namespacing for multi-system support
    """

    def __init__(self, cache_dir: str = "data/cache", system: str = "KP"):
        self.base_cache_dir = Path(cache_dir)
        self.system = system
        self.cache_dir = self.base_cache_dir / system
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._stats = {"hits": 0, "misses": 0, "writes": 0, "evictions": 0}

    def _get_cache_path(self, key: str) -> Path:
        """Generate cache file path from key with system namespace"""
        # Hash the key to avoid filesystem issues
        key_hash = cache_key_hash(key)

        # Support date-based cache organization if key contains date
        # Format: data/cache/{system}/YYYY-MM-DD/{hash}.json
        if ":" in key:
            parts = key.split(":")
            # Try to extract date from common key formats
            for part in parts:
                if len(part) == 10 and part[4] == "-" and part[7] == "-":
                    # Looks like YYYY-MM-DD
                    date_dir = self.cache_dir / part
                    date_dir.mkdir(exist_ok=True)
                    return date_dir / f"{key_hash}.json"

        return self.cache_dir / f"{key_hash}.json"

    async def get(self, key: str) -> Any | None:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            cache_path = self._get_cache_path(key)

            if not cache_path.exists():
                self._stats["misses"] += 1
                return None

            try:
                with open(cache_path) as f:
                    data = json.load(f)

                # Check expiration
                expires_at = datetime.fromisoformat(data["expires_at"])
                if datetime.utcnow() > expires_at:
                    # Expired, remove file
                    cache_path.unlink()
                    self._stats["evictions"] += 1
                    self._stats["misses"] += 1
                    return None

                self._stats["hits"] += 1
                return data["value"]

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Cache read error for {key}: {e}")
                # Remove corrupted cache file
                cache_path.unlink(missing_ok=True)
                self._stats["misses"] += 1
                return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (default 5 minutes)

        Returns:
            True if successful
        """
        async with self._lock:
            try:
                cache_path = self._get_cache_path(key)
                expires_at = datetime.utcnow() + timedelta(seconds=ttl)

                data = {
                    "key": key,
                    "value": value,
                    "created_at": datetime.utcnow().isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "ttl": ttl,
                }

                with open(cache_path, "w") as f:
                    json.dump(data, f, indent=2, default=str)

                self._stats["writes"] += 1
                return True

            except Exception as e:
                logger.error(f"Cache write error for {key}: {e}")
                return False

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            cache_path = self._get_cache_path(key)
            if cache_path.exists():
                cache_path.unlink()
                return True
            return False

    async def clear(self) -> int:
        """
        Clear all cache entries

        Returns:
            Number of entries cleared
        """
        async with self._lock:
            count = 0
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
                count += 1
            self._stats["evictions"] += count
            return count

    async def cleanup_expired(self) -> int:
        """
        Remove expired cache entries

        Returns:
            Number of entries removed
        """
        async with self._lock:
            count = 0
            now = datetime.utcnow()

            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file) as f:
                        data = json.load(f)

                    expires_at = datetime.fromisoformat(data["expires_at"])
                    if now > expires_at:
                        cache_file.unlink()
                        count += 1

                except Exception as e:
                    logger.error(f"Error checking cache file {cache_file}: {e}")
                    # Remove corrupted files
                    cache_file.unlink(missing_ok=True)
                    count += 1

            self._stats["evictions"] += count
            return count

    def get_stats(self) -> dict:
        """Get cache statistics"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0.0

        return {
            **self._stats,
            "hit_rate": hit_rate,
            "total_requests": total,
            "cache_files": len(list(self.cache_dir.glob("*.json"))),
        }

    async def warmup(self, keys: list[str]) -> int:
        """
        Pre-warm cache with common keys

        Args:
            keys: List of keys to warm up

        Returns:
            Number of keys warmed
        """
        warmed = 0
        for key in keys:
            # Just check if key exists to warm it
            result = await self.get(key)
            if result is not None:
                warmed += 1
        return warmed


class CacheKey:
    """Helper class for generating consistent cache keys with system support"""

    @staticmethod
    def intraday(
        date: str, interval: str, sessions: list[str], system: str = "KP"
    ) -> str:
        """Generate key for intraday data"""
        sessions_str = "-".join(sorted(sessions))
        return f"{system}:intraday:{date}:{interval}:{sessions_str}"

    @staticmethod
    def position(
        timestamp: datetime, planet_id: int, offset: bool, system: str = "KP"
    ) -> str:
        """Generate key for position data"""
        ts_str = timestamp.isoformat()
        return f"{system}:position:{ts_str}:{planet_id}:{offset}"

    @staticmethod
    def changes(
        start: str, end: str, planet_id: int, levels: list[str], system: str = "KP"
    ) -> str:
        """Generate key for change events"""
        levels_str = "-".join(sorted(levels))
        return f"{system}:changes:{start}:{end}:{planet_id}:{levels_str}"

    @staticmethod
    def amd_analysis(date: str, system: str = "KP") -> str:
        """Generate key for AMD analysis"""
        return f"{system}:amd_analysis:{date}"

    @staticmethod
    def snapshot(timestamp: datetime, system: str = "KP") -> str:
        """Generate key for system snapshot"""
        ts_str = timestamp.isoformat()
        return f"{system}:snapshot:{ts_str}"
