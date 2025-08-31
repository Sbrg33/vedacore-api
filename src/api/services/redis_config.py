"""
Redis Configuration & Durability

PM Requirements:
- Redis durability: Enable key TTLs for JTI store
- Set reasonable eviction policy (allkeys-lru) 
- Alert at 80% memory usage
- Backpressure controls for streaming
"""

import os
import redis.asyncio as redis
from urllib.parse import urlparse
from typing import Optional, Dict, Any
from dataclasses import dataclass
from app.core.logging import get_api_logger

logger = get_api_logger("redis_config")


@dataclass
class RedisConfig:
    """Redis configuration for production durability."""
    
    # Connection settings
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    
    # Durability settings (PM requirements)
    maxmemory_policy: str = "allkeys-lru"  # PM required
    maxmemory: str = "512mb"  # Adjust based on deployment
    
    # TTL settings for different data types
    jti_ttl_seconds: int = 3600  # 1 hour for one-time tokens
    cache_ttl_seconds: int = 300  # 5 minutes for response cache
    stream_token_ttl_seconds: int = 180  # 3 minutes for streaming tokens
    
    # Backpressure settings
    max_subscribers_per_tenant: int = 100  # Per-tenant streaming limit
    max_total_subscribers: int = 1000  # Global streaming limit
    memory_alert_threshold: float = 0.8  # Alert at 80% memory usage
    
    # Connection pool settings
    max_connections: int = 20
    retry_on_timeout: bool = True
    socket_keepalive: bool = True
    health_check_interval: int = 30


class RedisManager:
    """Production Redis manager with durability and backpressure."""
    
    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or RedisConfig()
        self._pool = None
        self._subscriber_counts: Dict[str, int] = {}
        self._total_subscribers = 0
        
    async def initialize(self) -> None:
        """Initialize Redis connection pool with production settings."""
        try:
            # Prefer REDIS_URL if provided (e.g., Upstash rediss://)
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                self._pool = redis.ConnectionPool.from_url(
                    redis_url,
                    max_connections=self.config.max_connections,
                    health_check_interval=self.config.health_check_interval,
                    decode_responses=True,
                )
            else:
                # Create connection pool from host/port
                self._pool = redis.ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    max_connections=self.config.max_connections,
                    retry_on_timeout=self.config.retry_on_timeout,
                    socket_keepalive=self.config.socket_keepalive,
                    health_check_interval=self.config.health_check_interval,
                    decode_responses=True,
                )
            
            # Configure Redis for production durability
            client = redis.Redis(connection_pool=self._pool)
            
            # Set memory/persistence policy when allowed (managed providers like Upstash forbid CONFIG SET)
            try:
                await client.config_set("maxmemory-policy", self.config.maxmemory_policy)
                await client.config_set("maxmemory", self.config.maxmemory)
                await client.config_set("save", "900 1 300 10 60 10000")  # RDB snapshots
            except Exception as e:
                logger.warning(f"Skipping Redis CONFIG SET (managed provider?): {e}")
            
            logger.info(f"✅ Redis configured: {self.config.host}:{self.config.port}")
            logger.info(f"🔧 Memory policy: {self.config.maxmemory_policy}")
            logger.info(f"💾 Max memory: {self.config.maxmemory}")
            
            await client.close()
            
        except Exception as e:
            logger.error(f"❌ Redis initialization failed: {e}")
            # Do not crash app; let production hardening skip Redis-dependent features
            raise
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client from pool."""
        if not self._pool:
            await self.initialize()
        return redis.Redis(connection_pool=self._pool)
    
    async def store_jti(self, jti: str, tenant_id: str) -> None:
        """Store JTI with TTL for one-time token validation (PM requirement)."""
        client = await self.get_client()
        try:
            key = f"jti:{jti}"
            await client.setex(key, self.config.jti_ttl_seconds, tenant_id)
            logger.debug(f"JTI stored: {jti[:8]}... TTL={self.config.jti_ttl_seconds}s")
        finally:
            await client.close()
    
    async def check_jti(self, jti: str) -> Optional[str]:
        """Check if JTI exists and return tenant_id, then delete (one-time use)."""
        client = await self.get_client()
        try:
            key = f"jti:{jti}"
            
            # Get and delete atomically
            pipe = client.pipeline()
            pipe.get(key)
            pipe.delete(key)
            results = await pipe.execute()
            
            tenant_id = results[0]
            if tenant_id:
                logger.debug(f"JTI consumed: {jti[:8]}... tenant={tenant_id}")
            
            return tenant_id
        finally:
            await client.close()
    
    async def cache_response(self, key: str, data: Any, ttl_override: Optional[int] = None) -> None:
        """Cache API response with TTL."""
        client = await self.get_client()
        try:
            ttl = ttl_override or self.config.cache_ttl_seconds
            await client.setex(f"cache:{key}", ttl, str(data))
        finally:
            await client.close()
    
    async def get_cached_response(self, key: str) -> Optional[str]:
        """Get cached response."""
        client = await self.get_client()
        try:
            return await client.get(f"cache:{key}")
        finally:
            await client.close()
    
    async def register_subscriber(self, tenant_id: str, topic: str) -> bool:
        """Register subscriber with backpressure control (PM requirement)."""
        # Check global limit
        if self._total_subscribers >= self.config.max_total_subscribers:
            logger.warning(f"🚫 Global subscriber limit reached: {self._total_subscribers}")
            return False
        
        # Check per-tenant limit
        tenant_count = self._subscriber_counts.get(tenant_id, 0)
        if tenant_count >= self.config.max_subscribers_per_tenant:
            logger.warning(f"🚫 Tenant {tenant_id} subscriber limit reached: {tenant_count}")
            return False
        
        # Register subscriber
        self._subscriber_counts[tenant_id] = tenant_count + 1
        self._total_subscribers += 1
        
        client = await self.get_client()
        try:
            # Store subscriber info with TTL
            subscriber_key = f"subscriber:{tenant_id}:{topic}"
            await client.setex(subscriber_key, self.config.stream_token_ttl_seconds, "active")
            
            # Update metrics
            await client.incr("metrics:total_subscribers")
            await client.incr(f"metrics:tenant_subscribers:{tenant_id}")
            
            logger.info(f"📡 Subscriber registered: {tenant_id} -> {topic}")
            return True
        finally:
            await client.close()
    
    async def unregister_subscriber(self, tenant_id: str, topic: str) -> None:
        """Unregister subscriber and update counts."""
        if tenant_id in self._subscriber_counts:
            self._subscriber_counts[tenant_id] = max(0, self._subscriber_counts[tenant_id] - 1)
            if self._subscriber_counts[tenant_id] == 0:
                del self._subscriber_counts[tenant_id]
        
        self._total_subscribers = max(0, self._total_subscribers - 1)
        
        client = await self.get_client()
        try:
            subscriber_key = f"subscriber:{tenant_id}:{topic}"
            await client.delete(subscriber_key)
            
            # Update metrics
            await client.decr("metrics:total_subscribers")
            await client.decr(f"metrics:tenant_subscribers:{tenant_id}")
            
            logger.info(f"📡 Subscriber unregistered: {tenant_id} -> {topic}")
        finally:
            await client.close()
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """Get Redis memory usage for alerting (PM requirement)."""
        client = await self.get_client()
        try:
            info = await client.memory_usage()
            stats = await client.memory_stats()
            
            used_memory = stats.get('used_memory', 0)
            max_memory = stats.get('maxmemory', 0)
            
            if max_memory > 0:
                usage_ratio = used_memory / max_memory
                alert = usage_ratio > self.config.memory_alert_threshold
            else:
                usage_ratio = 0.0
                alert = False
            
            return {
                "used_memory_bytes": used_memory,
                "max_memory_bytes": max_memory,
                "usage_ratio": usage_ratio,
                "memory_alert": alert,
                "total_subscribers": self._total_subscribers,
                "tenant_counts": dict(self._subscriber_counts)
            }
        finally:
            await client.close()
    
    async def health_check(self) -> Dict[str, Any]:
        """Redis health check for monitoring."""
        try:
            client = await self.get_client()
            
            # Test basic operations
            test_key = "health_check"
            await client.set(test_key, "ok", ex=10)
            value = await client.get(test_key)
            await client.delete(test_key)
            
            if value != "ok":
                raise Exception("Redis read/write test failed")
            
            # Get memory stats
            memory_stats = await self.get_memory_usage()
            
            await client.close()
            
            return {
                "status": "healthy",
                "connection": "ok",
                "read_write": "ok",
                "memory_usage": memory_stats
            }
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._pool:
            await self._pool.disconnect()
            logger.info("Redis connection pool closed")


# Global Redis manager instance
_redis_manager: Optional[RedisManager] = None


async def get_redis() -> RedisManager:
    """Get global Redis manager instance."""
    global _redis_manager
    
    if _redis_manager is None:
        # Load config from environment
        config = RedisConfig(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
            maxmemory=os.getenv("REDIS_MAX_MEMORY", "512mb"),
            max_subscribers_per_tenant=int(os.getenv("MAX_SUBSCRIBERS_PER_TENANT", "100")),
            max_total_subscribers=int(os.getenv("MAX_TOTAL_SUBSCRIBERS", "1000"))
        )
        
        _redis_manager = RedisManager(config)
        await _redis_manager.initialize()
    
    return _redis_manager


async def close_redis() -> None:
    """Close global Redis manager."""
    global _redis_manager
    if _redis_manager:
        await _redis_manager.close()
        _redis_manager = None


if __name__ == "__main__":
    # Test Redis configuration
    import asyncio
    
    async def test_redis():
        print("🔧 Testing Redis configuration...")
        
        redis_mgr = await get_redis()
        
        # Test JTI operations
        await redis_mgr.store_jti("test_jti_123", "tenant_1")
        tenant = await redis_mgr.check_jti("test_jti_123")
        print(f"JTI test: {tenant}")
        
        # Test subscriber registration
        success = await redis_mgr.register_subscriber("tenant_1", "test_topic")
        print(f"Subscriber registration: {success}")
        
        # Test memory usage
        memory = await redis_mgr.get_memory_usage()
        print(f"Memory usage: {memory}")
        
        # Health check
        health = await redis_mgr.health_check()
        print(f"Health: {health}")
        
        await close_redis()
        print("✅ Redis test complete")
    
    asyncio.run(test_redis())
