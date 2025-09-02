"""
Unified Cache Service - PM requirement implementation

Standardizes cache backends:
- Production: Redis backend via cache_backend (scalable, distributed)
- Development: File-based cache via cache_service (local, persistent)

Environment-driven switching with consistent interface.
"""

import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
USE_REDIS_CACHE = ENVIRONMENT == "production"


class UnifiedCache:
    """
    Unified cache interface that switches between Redis and file cache based on environment.
    
    PM requirement: Use Redis for production, file cache for dev only.
    """
    
    def __init__(self, system: str = "KP"):
        self.system = system
        self._backend = None
        self._setup_backend()
    
    def _setup_backend(self):
        """Setup appropriate cache backend based on environment."""
        if USE_REDIS_CACHE:
            try:
                from app.services.cache_backend import get_cache_backend
                self._backend = get_cache_backend()
                self._backend_type = "redis"
                logger.info(f"🔴 UnifiedCache[{self.system}] using Redis backend (production)")
            except Exception as e:
                logger.warning(f"Redis backend failed, falling back to file cache: {e}")
                self._setup_file_backend()
        else:
            self._setup_file_backend()
    
    def _setup_file_backend(self):
        """Setup file-based cache backend for development."""
        from app.services.cache_service import CacheService
        self._backend = CacheService(system=self.system)
        self._backend_type = "file"
        logger.info(f"📁 UnifiedCache[{self.system}] using file backend (development)")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with unified interface."""
        try:
            if self._backend_type == "redis":
                return await self._backend.get(key)
            else:
                # File backend is sync, wrap in async
                return await self._backend.get(key)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache with unified interface."""
        try:
            if self._backend_type == "redis":
                return await self._backend.set(key, value, ttl)
            else:
                # File backend is sync, wrap in async
                return await self._backend.set(key, value, ttl)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        try:
            if self._backend_type == "redis":
                return await self._backend.delete(key)
            else:
                return await self._backend.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            if self._backend_type == "redis":
                return await self._backend.exists(key)
            else:
                # File backend doesn't have exists, use get
                value = await self._backend.get(key)
                return value is not None
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    async def clear(self) -> int:
        """Clear cache entries."""
        try:
            if self._backend_type == "redis":
                # Redis backend doesn't have clear method, skip for now
                logger.warning("Clear operation not supported for Redis backend")
                return 0
            else:
                return await self._backend.clear()
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return 0
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        base_stats = {
            "backend_type": self._backend_type,
            "environment": ENVIRONMENT
        }
        
        try:
            if hasattr(self._backend, 'get_stats'):
                backend_stats = self._backend.get_stats()
                return {**base_stats, **backend_stats}
            else:
                # Redis backend doesn't have get_stats, provide basic info
                return {
                    **base_stats,
                    "status": "active",
                    "note": "Redis backend active - detailed stats not available"
                }
        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {
                **base_stats,
                "error": str(e)
            }


# Global cache instances for different systems
_cache_instances = {}


def get_unified_cache(system: str = "KP") -> UnifiedCache:
    """
    Get unified cache instance for a system.
    
    PM requirement: Environment-driven cache backend selection.
    """
    if system not in _cache_instances:
        _cache_instances[system] = UnifiedCache(system)
    return _cache_instances[system]


# Backward compatibility helpers
def get_production_cache(system: str = "KP"):
    """Get cache instance optimized for production (Redis)."""
    return get_unified_cache(system)


def get_development_cache(system: str = "KP"):
    """Get cache instance for development (file-based)."""
    return get_unified_cache(system)


# PM Environment variables reference
CACHE_ENV_VARS = {
    "ENVIRONMENT": "development|production (determines cache backend)",
    "CACHE_BACKEND": "redis|memory (Redis backend configuration)", 
    "REDIS_URL": "redis://host:port/db (Redis connection string)",
    "USE_REDIS_CACHE": "true|false (override environment-based selection)"
}