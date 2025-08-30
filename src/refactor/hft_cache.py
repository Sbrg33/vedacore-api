#!/usr/bin/env python3
"""
High-Frequency Trading Cache Module
Implements microsecond-precision caching with 1-second TTL for KP calculations
Designed for 100k+ calculations per second
"""

import threading
import time

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class CacheEntry:
    """Single cache entry with timestamp and value"""

    value: Any
    timestamp: float  # Unix timestamp when cached
    hit_count: int = 0  # Track popularity for optimization


class HFTCache:
    """
    Thread-safe, high-performance cache for KP calculations.

    Features:
    - 1-second TTL for planet positions (safe for Moon SL2)
    - Thread-safe with minimal lock contention
    - Automatic cleanup of expired entries
    - Sub-microsecond lookup times
    """

    def __init__(self, ttl: float = 1.0, max_size: int = 10000):
        """
        Initialize HFT cache.

        Args:
            ttl: Time-to-live in seconds (default 1.0)
            max_size: Maximum cache entries before cleanup
        """
        self.ttl = ttl
        self.max_size = max_size
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()  # Reentrant lock for nested calls

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        # Start cleanup thread
        self._cleanup_interval = max(
            ttl * 10, 10.0
        )  # Cleanup every 10 TTLs or 10 seconds
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_worker, daemon=True
        )
        self._cleanup_thread.start()

    def _make_key(
        self,
        timestamp: datetime,
        planet_id: int,
        apply_offset: bool,
        calculation_type: str = "position",
    ) -> str:
        """
        Create cache key from parameters.

        For HFT, we round timestamp to nearest second for Moon calculations
        since Moon moves only 0.00015°/second.
        """
        # Round to nearest second for caching
        ts_seconds = int(timestamp.timestamp())

        # Create unique key
        key_parts = [
            str(ts_seconds),
            str(planet_id),
            str(apply_offset),
            calculation_type,
        ]

        return "|".join(key_parts)

    def get(
        self,
        timestamp: datetime,
        planet_id: int,
        apply_offset: bool,
        calculation_type: str = "position",
    ) -> Any | None:
        """
        Get cached value if available and not expired.

        Returns:
            Cached value or None if not found/expired
        """
        key = self._make_key(timestamp, planet_id, apply_offset, calculation_type)

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            # Check if expired
            age = time.time() - entry.timestamp
            if age > self.ttl:
                # Expired - remove it
                del self._cache[key]
                self._misses += 1
                self._evictions += 1
                return None

            # Valid hit
            self._hits += 1
            entry.hit_count += 1
            return entry.value

    def set(
        self,
        timestamp: datetime,
        planet_id: int,
        apply_offset: bool,
        value: Any,
        calculation_type: str = "position",
    ) -> None:
        """
        Store value in cache.
        """
        key = self._make_key(timestamp, planet_id, apply_offset, calculation_type)

        with self._lock:
            # Check size limit
            if len(self._cache) >= self.max_size:
                self._cleanup_old_entries()

            self._cache[key] = CacheEntry(value=value, timestamp=time.time())

    def _cleanup_old_entries(self) -> None:
        """Remove expired entries."""
        current_time = time.time()
        expired_keys = []

        with self._lock:
            for key, entry in self._cache.items():
                if current_time - entry.timestamp > self.ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]
                self._evictions += 1

    def _cleanup_worker(self) -> None:
        """Background thread for periodic cleanup."""
        while not self._stop_cleanup.wait(self._cleanup_interval):
            self._cleanup_old_entries()

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "evictions": self._evictions,
            "size": len(self._cache),
            "ttl": self.ttl,
            "max_size": self.max_size,
        }

    def shutdown(self) -> None:
        """Shutdown cleanup thread."""
        self._stop_cleanup.set()
        self._cleanup_thread.join(timeout=1.0)


class PlanetPositionCache:
    """
    Specialized cache for planet positions with automatic KP lord calculation.
    Optimized for Moon tracking in HFT scenarios.
    """

    def __init__(self, ttl_seconds: dict[int, float] = None):
        """
        Initialize with per-planet TTL settings.

        Args:
            ttl_seconds: Dict mapping planet_id to TTL in seconds
                        Defaults to optimized values for each planet
        """
        if ttl_seconds is None:
            # Optimized TTLs based on planet speeds
            ttl_seconds = {
                1: 60.0,  # Sun: moves ~1°/day, safe for 60s
                2: 1.0,  # Moon: moves ~13°/day, cache for 1s
                3: 300.0,  # Jupiter: slow, cache for 5 min
                4: 10.0,  # Rahu: moderate, cache for 10s
                5: 30.0,  # Mercury: variable, cache for 30s
                6: 30.0,  # Venus: moderate, cache for 30s
                7: 10.0,  # Ketu: same as Rahu
                8: 300.0,  # Saturn: slow, cache for 5 min
                9: 60.0,  # Mars: moderate, cache for 60s
            }

        self.ttl_seconds = ttl_seconds
        self._caches = {
            planet_id: HFTCache(ttl=ttl, max_size=1000)
            for planet_id, ttl in ttl_seconds.items()
        }

    def get_position(
        self, timestamp: datetime, planet_id: int, apply_offset: bool
    ) -> Any | None:
        """Get cached planet position."""
        if planet_id not in self._caches:
            return None

        return self._caches[planet_id].get(
            timestamp, planet_id, apply_offset, "position"
        )

    def set_position(
        self,
        timestamp: datetime,
        planet_id: int,
        apply_offset: bool,
        position_data: Any,
    ) -> None:
        """Cache planet position."""
        if planet_id not in self._caches:
            # Create cache with default TTL
            self._caches[planet_id] = HFTCache(ttl=1.0, max_size=1000)

        self._caches[planet_id].set(
            timestamp, planet_id, apply_offset, position_data, "position"
        )

    def get_all_stats(self) -> dict[int, dict[str, Any]]:
        """Get statistics for all planet caches."""
        return {
            planet_id: cache.get_stats() for planet_id, cache in self._caches.items()
        }

    def clear_all(self) -> None:
        """Clear all planet caches."""
        for cache in self._caches.values():
            cache.clear()

    def shutdown(self) -> None:
        """Shutdown all cache cleanup threads."""
        for cache in self._caches.values():
            cache.shutdown()


# Global cache instance for HFT
_global_hft_cache: PlanetPositionCache | None = None


def get_hft_cache() -> PlanetPositionCache:
    """Get or create global HFT cache instance."""
    global _global_hft_cache
    if _global_hft_cache is None:
        _global_hft_cache = PlanetPositionCache()
    return _global_hft_cache


def warmup_cache(
    start_time: datetime,
    end_time: datetime,
    planet_id: int = 2,
    interval_seconds: int = 60,
) -> int:
    """
    Pre-warm cache with calculations for a time range.

    Args:
        start_time: Start of range
        end_time: End of range
        planet_id: Planet to calculate (default Moon)
        interval_seconds: Calculation interval

    Returns:
        Number of entries cached
    """
    from refactor.facade import get_positions

    cache = get_hft_cache()
    count = 0
    current = start_time

    while current <= end_time:
        # Calculate with offset
        pos = get_positions(current, planet_id, apply_kp_offset=True)
        cache.set_position(current, planet_id, True, pos)

        # Calculate without offset
        pos = get_positions(current, planet_id, apply_kp_offset=False)
        cache.set_position(current, planet_id, False, pos)

        count += 2
        current += timedelta(seconds=interval_seconds)

    return count


# Performance monitoring
class CacheMonitor:
    """Monitor cache performance for HFT optimization."""

    def __init__(self):
        self.request_times = []
        self.cache_times = []
        self.calculation_times = []

    def record_request(self, duration: float, was_cached: bool) -> None:
        """Record a request timing."""
        self.request_times.append(duration)
        if was_cached:
            self.cache_times.append(duration)
        else:
            self.calculation_times.append(duration)

    def get_metrics(self) -> dict[str, float]:
        """Get performance metrics."""

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0.0

        return {
            "avg_request_time_ms": avg(self.request_times) * 1000,
            "avg_cache_time_ms": avg(self.cache_times) * 1000,
            "avg_calculation_time_ms": avg(self.calculation_times) * 1000,
            "cache_speedup": (
                avg(self.calculation_times) / avg(self.cache_times)
                if self.cache_times
                else 0.0
            ),
            "total_requests": len(self.request_times),
            "cached_requests": len(self.cache_times),
            "calculated_requests": len(self.calculation_times),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.request_times.clear()
        self.cache_times.clear()
        self.calculation_times.clear()


# Global monitor instance
_global_monitor = CacheMonitor()


def get_cache_monitor() -> CacheMonitor:
    """Get global cache monitor."""
    return _global_monitor
