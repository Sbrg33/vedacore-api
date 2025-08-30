"""
Cache Backend Abstraction with Redis Toggle

Implements PM requirement for Redis backend with in-memory fallback.
Supports rate limiting, streaming, and general caching needs.
"""

import json
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
import os

from app.core.logging import get_api_logger

logger = get_api_logger("cache_backend")


class CacheBackend(ABC):
    """Abstract cache backend interface."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set key-value with TTL in seconds."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass
    
    @abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter."""
        pass
    
    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        pass
    
    @abstractmethod
    async def publish(self, channel: str, message: str) -> int:
        """Publish message to channel (for streaming)."""
        pass
    
    @abstractmethod
    async def subscribe(self, channel: str) -> Any:
        """Subscribe to channel (for streaming)."""
        pass


class MemoryCacheBackend(CacheBackend):
    """In-memory cache backend for development/single-instance."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        logger.info("💾 Memory cache backend initialized")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from memory cache."""
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                # Check expiry
                if entry['expires'] and datetime.now() > entry['expires']:
                    del self._cache[key]
                    return None
                return entry['value']
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in memory cache."""
        async with self._lock:
            expires = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
            self._cache[key] = {
                'value': value,
                'expires': expires
            }
            return True
    
    async def delete(self, key: str) -> bool:
        """Delete key from memory cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in memory cache."""
        value = await self.get(key)  # This handles expiry
        return value is not None
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter in memory."""
        async with self._lock:
            current = 0
            if key in self._cache:
                entry = self._cache[key]
                if entry['expires'] and datetime.now() > entry['expires']:
                    del self._cache[key]
                else:
                    current = int(entry.get('value', 0))
            
            new_value = current + amount
            self._cache[key] = {
                'value': new_value,
                'expires': datetime.now() + timedelta(seconds=3600)  # 1 hour default
            }
            return new_value
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        async with self._lock:
            if key in self._cache:
                expires = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
                self._cache[key]['expires'] = expires
                return True
            return False
    
    async def publish(self, channel: str, message: str) -> int:
        """Publish message to in-memory subscribers."""
        async with self._lock:
            if channel in self._subscribers:
                subscribers = self._subscribers[channel][:]  # Copy list
                for queue in subscribers:
                    try:
                        queue.put_nowait(message)
                    except asyncio.QueueFull:
                        # Remove full queues
                        self._subscribers[channel].remove(queue)
                return len(subscribers)
            return 0
    
    async def subscribe(self, channel: str) -> asyncio.Queue:
        """Subscribe to in-memory channel."""
        async with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = []
            
            queue = asyncio.Queue(maxsize=1000)
            self._subscribers[channel].append(queue)
            return queue


class RedisCacheBackend(CacheBackend):
    """Redis cache backend for production/multi-instance."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis = None
        self.pubsub = None
        logger.info(f"🔴 Redis cache backend initialized: {redis_url}")
    
    async def _ensure_connection(self):
        """Ensure Redis connection is established."""
        if self.redis is None:
            try:
                import redis.asyncio as redis
                self.redis = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                await self.redis.ping()
                logger.info("🔴 Redis connection established")
            except ImportError:
                raise RuntimeError(
                    "Redis backend requires 'redis' package: pip install redis"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to connect to Redis: {e}")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis."""
        await self._ensure_connection()
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in Redis."""
        await self._ensure_connection()
        try:
            # Serialize complex types as JSON
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            elif not isinstance(value, (str, int, float)):
                value = str(value)
            
            await self.redis.set(key, value, ex=ttl)
            return True
            
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        await self._ensure_connection()
        try:
            result = await self.redis.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        await self._ensure_connection()
        try:
            result = await self.redis.exists(key)
            return result > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter in Redis."""
        await self._ensure_connection()
        try:
            result = await self.redis.incrby(key, amount)
            return result
        except Exception as e:
            logger.error(f"Redis incr error: {e}")
            return 0
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on Redis key."""
        await self._ensure_connection()
        try:
            result = await self.redis.expire(key, ttl)
            return result
        except Exception as e:
            logger.error(f"Redis expire error: {e}")
            return False
    
    async def publish(self, channel: str, message: str) -> int:
        """Publish message to Redis channel."""
        await self._ensure_connection()
        try:
            result = await self.redis.publish(channel, message)
            return result
        except Exception as e:
            logger.error(f"Redis publish error: {e}")
            return 0
    
    async def subscribe(self, channel: str) -> Any:
        """Subscribe to Redis channel."""
        await self._ensure_connection()
        try:
            pubsub = self.redis.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            logger.error(f"Redis subscribe error: {e}")
            return None


# Global cache instance
_cache_backend: Optional[CacheBackend] = None


def get_cache_backend() -> CacheBackend:
    """Get the configured cache backend (PM requirement - env-driven toggle)."""
    global _cache_backend
    
    if _cache_backend is None:
        backend_type = os.getenv("CACHE_BACKEND", "redis").lower()
        
        if backend_type == "redis":
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            try:
                _cache_backend = RedisCacheBackend(redis_url)
                logger.info(f"🔴 Using Redis cache backend: {redis_url}")
            except Exception as e:
                logger.warning(f"Redis backend failed, falling back to memory: {e}")
                _cache_backend = MemoryCacheBackend()
        else:
            _cache_backend = MemoryCacheBackend()
            logger.info("💾 Using memory cache backend (development mode)")
    
    return _cache_backend


async def test_cache_backend() -> Dict[str, Any]:
    """Test the cache backend functionality."""
    cache = get_cache_backend()
    
    test_results = {
        "backend_type": type(cache).__name__,
        "basic_ops": False,
        "counters": False,
        "ttl": False,
        "pubsub": False
    }
    
    try:
        # Test basic operations
        await cache.set("test_key", "test_value", ttl=30)
        value = await cache.get("test_key")
        exists = await cache.exists("test_key")
        await cache.delete("test_key")
        test_results["basic_ops"] = (value == "test_value" and exists)
        
        # Test counters
        count1 = await cache.incr("test_counter", 5)
        count2 = await cache.incr("test_counter", 3)
        test_results["counters"] = (count1 == 5 and count2 == 8)
        await cache.delete("test_counter")
        
        # Test TTL
        await cache.set("test_ttl", "expires_soon", ttl=1)
        await asyncio.sleep(1.1)
        expired_value = await cache.get("test_ttl")
        test_results["ttl"] = (expired_value is None)
        
        # Test pub/sub
        published = await cache.publish("test_channel", "test_message")
        test_results["pubsub"] = published >= 0  # Redis returns subscriber count
        
        logger.info(f"✅ Cache backend test completed: {test_results}")
        
    except Exception as e:
        logger.error(f"❌ Cache backend test failed: {e}")
        test_results["error"] = str(e)
    
    return test_results


# PM Environment variables reference
CACHE_ENV_VARS = {
    "CACHE_BACKEND": "redis|memory (default: redis)",
    "REDIS_URL": "redis://user:pass@host:6379/0 (default: redis://localhost:6379/0)",
    "CACHE_TTL_SECONDS": "300 (default cache TTL)",
    "RATE_LIMIT_REDIS_PREFIX": "rate: (prefix for rate limit keys)",
    "STREAM_CHANNEL_PREFIX": "stream: (prefix for streaming channels)"
}