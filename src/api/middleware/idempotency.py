"""
Idempotency Middleware

PM Requirements:
- Honor Idempotency-Key header on all POSTs
- Persist hash → response for 24h (Redis)
- Prevent duplicate operations
"""

import hashlib
import json
import time
from typing import Callable, Optional, Dict, Any
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_api_logger
from api.services.redis_config import get_redis

logger = get_api_logger("idempotency")


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Idempotency middleware for POST requests.
    
    PM Requirements:
    - Honor Idempotency-Key header on all POSTs
    - Store response hash for 24 hours in Redis
    - Return cached response for duplicate requests
    """
    
    IDEMPOTENCY_TTL = 24 * 3600  # 24 hours (PM requirement)
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        logger.info("🔄 Idempotency middleware initialized")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with idempotency checking."""
        
        # Only apply to POST requests
        if request.method != "POST":
            return await call_next(request)
        
        # Get idempotency key from header
        idempotency_key = request.headers.get("idempotency-key")
        if not idempotency_key:
            # No idempotency key - process normally
            return await call_next(request)
        
        # Validate idempotency key format
        if not self._is_valid_key(idempotency_key):
            raise HTTPException(
                status_code=400,
                detail="Invalid Idempotency-Key format. Use UUID or similar unique identifier."
            )
        
        try:
            # Check for cached response
            cached_response = await self._get_cached_response(request, idempotency_key)
            if cached_response:
                logger.info(f"🔄 Idempotency hit: {idempotency_key[:16]}...")
                return self._create_response_from_cache(cached_response)
            
            # Process request normally
            response = await call_next(request)
            
            # Cache successful responses (2xx status codes)
            if 200 <= response.status_code < 300:
                await self._cache_response(request, idempotency_key, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Idempotency middleware error: {e}")
            # Don't fail the request due to idempotency issues
            return await call_next(request)
    
    def _is_valid_key(self, key: str) -> bool:
        """Validate idempotency key format."""
        # Must be 1-255 characters, printable ASCII
        if not (1 <= len(key) <= 255):
            return False
        
        if not key.isprintable():
            return False
        
        # Reject common bad patterns
        bad_patterns = ["test", "example", "null", "undefined", ""]
        if key.lower() in bad_patterns:
            return False
        
        return True
    
    async def _get_request_hash(self, request: Request) -> str:
        """Generate hash of request for comparison."""
        # Read request body
        body = await request.body()
        
        # Create hash components
        components = [
            request.method,
            str(request.url.path),
            str(sorted(request.query_params.items())),
            body.decode('utf-8', errors='ignore') if body else "",
            request.headers.get("content-type", "")
        ]
        
        # Generate hash
        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def _get_cached_response(self, request: Request, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response for idempotency key."""
        try:
            redis_mgr = await get_redis()
            client = await redis_mgr.get_client()
            
            # Generate cache key
            request_hash = await self._get_request_hash(request)
            cache_key = f"idempotency:{idempotency_key}:{request_hash}"
            
            # Get cached data
            cached_data = await client.get(cache_key)
            await client.close()
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached idempotency response: {e}")
            return None
    
    async def _cache_response(self, request: Request, idempotency_key: str, response: Response) -> None:
        """Cache response for idempotency."""
        try:
            # Read response body
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            # Recreate response with readable body
            new_response = Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
            
            # Cache data structure
            cache_data = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body.decode('utf-8', errors='ignore'),
                "media_type": response.media_type,
                "timestamp": int(time.time()),
                "idempotency_key": idempotency_key
            }
            
            # Store in Redis
            redis_mgr = await get_redis()
            client = await redis_mgr.get_client()
            
            request_hash = await self._get_request_hash(request)
            cache_key = f"idempotency:{idempotency_key}:{request_hash}"
            
            await client.setex(
                cache_key,
                self.IDEMPOTENCY_TTL,
                json.dumps(cache_data)
            )
            
            await client.close()
            
            logger.info(f"🔄 Response cached for idempotency: {idempotency_key[:16]}...")
            
            # Replace response body iterator
            response.body_iterator = self._iter_body(response_body)
            
        except Exception as e:
            logger.error(f"Failed to cache idempotency response: {e}")
    
    def _create_response_from_cache(self, cache_data: Dict[str, Any]) -> Response:
        """Create response from cached data."""
        # Add idempotency headers
        headers = dict(cache_data["headers"])
        headers["X-Idempotency-Replayed"] = "true"
        headers["X-Idempotency-Timestamp"] = str(cache_data["timestamp"])
        
        return Response(
            content=cache_data["body"],
            status_code=cache_data["status_code"],
            headers=headers,
            media_type=cache_data["media_type"]
        )
    
    async def _iter_body(self, body: bytes):
        """Iterator for response body."""
        yield body


# Idempotency utilities
async def generate_idempotency_key(prefix: str = "veda") -> str:
    """Generate a new idempotency key."""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex}"


async def check_idempotency_status(idempotency_key: str) -> Optional[Dict[str, Any]]:
    """Check if an idempotency key has been used."""
    try:
        redis_mgr = await get_redis()
        client = await redis_mgr.get_client()
        
        # Search for any cached responses with this key
        pattern = f"idempotency:{idempotency_key}:*"
        keys = await client.keys(pattern)
        
        if keys:
            # Get first matching cache entry
            cached_data = await client.get(keys[0])
            await client.close()
            
            if cached_data:
                data = json.loads(cached_data)
                return {
                    "used": True,
                    "timestamp": data["timestamp"],
                    "status_code": data["status_code"],
                    "ttl_remaining": await client.ttl(keys[0])
                }
        
        await client.close()
        return {"used": False}
        
    except Exception as e:
        logger.error(f"Failed to check idempotency status: {e}")
        return None


# Health check endpoint for idempotency system
async def idempotency_health_check() -> Dict[str, Any]:
    """Health check for idempotency system."""
    try:
        redis_mgr = await get_redis()
        client = await redis_mgr.get_client()
        
        # Test basic operations
        test_key = "idempotency:health_test:abc123"
        test_data = {"test": "data", "timestamp": int(time.time())}
        
        # Store and retrieve test data
        await client.setex(test_key, 60, json.dumps(test_data))
        retrieved = await client.get(test_key)
        await client.delete(test_key)
        
        if not retrieved or json.loads(retrieved) != test_data:
            raise Exception("Idempotency cache test failed")
        
        # Count active idempotency keys
        pattern = "idempotency:*"
        keys = await client.keys(pattern)
        
        await client.close()
        
        return {
            "status": "healthy",
            "cache_test": "ok",
            "active_keys": len(keys),
            "ttl": f"{IdempotencyMiddleware.IDEMPOTENCY_TTL}s"
        }
        
    except Exception as e:
        logger.error(f"Idempotency health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


if __name__ == "__main__":
    # Test idempotency functionality
    import asyncio
    
    async def test_idempotency():
        print("🔄 Testing idempotency system...")
        
        # Generate test key
        key = await generate_idempotency_key("test")
        print(f"Generated key: {key}")
        
        # Check status (should be unused)
        status = await check_idempotency_status(key)
        print(f"Initial status: {status}")
        
        # Health check
        health = await idempotency_health_check()
        print(f"Health: {health}")
        
        print("✅ Idempotency test complete")
    
    asyncio.run(test_idempotency())