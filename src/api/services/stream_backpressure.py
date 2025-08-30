"""
Stream Backpressure Management

PM Requirements:
- Cap per-tenant subscribers
- Drop oldest on over-quota
- Expose stream_drop_total metrics
- Prevent memory exhaustion
"""

import asyncio
import time
from typing import Dict, Set, Optional, List, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict
from app.core.logging import get_api_logger
from api.services.redis_config import get_redis

logger = get_api_logger("stream_backpressure")


@dataclass
class StreamSubscriber:
    """Individual stream subscriber tracking."""
    tenant_id: str
    topic: str
    connection_id: str
    connected_at: float
    last_activity: float
    queue_size: int = 0
    dropped_messages: int = 0
    send_callback: Optional[Callable] = field(default=None, compare=False)


class StreamBackpressureManager:
    """
    Manages streaming connections with backpressure controls.
    
    PM Requirements:
    - Per-tenant subscriber limits
    - Global subscriber limits
    - Queue size limits per connection
    - Automatic cleanup of stale connections
    - Metrics exposure for monitoring
    """
    
    def __init__(
        self,
        max_subscribers_per_tenant: int = 100,
        max_total_subscribers: int = 1000,
        max_queue_size_per_connection: int = 100,
        connection_timeout_seconds: int = 300,  # 5 minutes
        cleanup_interval_seconds: int = 60
    ):
        self.max_subscribers_per_tenant = max_subscribers_per_tenant
        self.max_total_subscribers = max_total_subscribers
        self.max_queue_size_per_connection = max_queue_size_per_connection
        self.connection_timeout_seconds = connection_timeout_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        
        # Active subscribers by connection_id
        self.subscribers: Dict[str, StreamSubscriber] = {}
        
        # Tenant tracking
        self.tenant_subscribers: Dict[str, Set[str]] = defaultdict(set)
        
        # Topic tracking
        self.topic_subscribers: Dict[str, Set[str]] = defaultdict(set)
        
        # Metrics
        self.metrics = {
            "total_subscribers": 0,
            "total_connections_created": 0,
            "total_connections_dropped": 0,
            "total_messages_sent": 0,
            "total_messages_dropped": 0,
            "tenant_limit_rejections": 0,
            "global_limit_rejections": 0,
            "queue_overflow_drops": 0
        }
        
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info(f"🔄 Stream backpressure manager initialized")
        logger.info(f"   Max per tenant: {max_subscribers_per_tenant}")
        logger.info(f"   Max global: {max_total_subscribers}")
        logger.info(f"   Max queue size: {max_queue_size_per_connection}")
    
    def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("🧹 Cleanup task started")
    
    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("🧹 Cleanup task stopped")
    
    async def register_subscriber(
        self,
        tenant_id: str,
        topic: str,
        connection_id: str,
        send_callback: Callable
    ) -> bool:
        """
        Register new subscriber with backpressure checks.
        
        Returns True if registered successfully, False if rejected.
        """
        now = time.time()
        
        # Check global limit (PM requirement)
        if len(self.subscribers) >= self.max_total_subscribers:
            self.metrics["global_limit_rejections"] += 1
            await self._record_metric("stream_drop_total", "global_limit")
            logger.warning(f"🚫 Global subscriber limit reached: {len(self.subscribers)}")
            return False
        
        # Check per-tenant limit (PM requirement)
        tenant_count = len(self.tenant_subscribers.get(tenant_id, set()))
        if tenant_count >= self.max_subscribers_per_tenant:
            self.metrics["tenant_limit_rejections"] += 1
            await self._record_metric("stream_drop_total", "tenant_limit")
            logger.warning(f"🚫 Tenant {tenant_id} limit reached: {tenant_count}")
            
            # Drop oldest connection for this tenant (PM requirement)
            await self._drop_oldest_subscriber(tenant_id)
        
        # Create subscriber
        subscriber = StreamSubscriber(
            tenant_id=tenant_id,
            topic=topic,
            connection_id=connection_id,
            connected_at=now,
            last_activity=now,
            send_callback=send_callback
        )
        
        # Register subscriber
        self.subscribers[connection_id] = subscriber
        self.tenant_subscribers[tenant_id].add(connection_id)
        self.topic_subscribers[topic].add(connection_id)
        
        # Update metrics
        self.metrics["total_subscribers"] = len(self.subscribers)
        self.metrics["total_connections_created"] += 1
        
        # Store in Redis for persistence
        redis_mgr = await get_redis()
        await redis_mgr.register_subscriber(tenant_id, topic)
        
        logger.info(f"📡 Subscriber registered: {tenant_id} -> {topic} ({connection_id})")
        return True
    
    async def unregister_subscriber(self, connection_id: str) -> None:
        """Unregister subscriber and clean up tracking."""
        subscriber = self.subscribers.pop(connection_id, None)
        if not subscriber:
            return
        
        # Remove from tracking sets
        self.tenant_subscribers[subscriber.tenant_id].discard(connection_id)
        if not self.tenant_subscribers[subscriber.tenant_id]:
            del self.tenant_subscribers[subscriber.tenant_id]
        
        self.topic_subscribers[subscriber.topic].discard(connection_id)
        if not self.topic_subscribers[subscriber.topic]:
            del self.topic_subscribers[subscriber.topic]
        
        # Update metrics
        self.metrics["total_subscribers"] = len(self.subscribers)
        self.metrics["total_connections_dropped"] += 1
        
        # Update Redis
        redis_mgr = await get_redis()
        await redis_mgr.unregister_subscriber(subscriber.tenant_id, subscriber.topic)
        
        logger.info(f"📡 Subscriber unregistered: {subscriber.tenant_id} -> {subscriber.topic}")
    
    async def send_to_topic(self, topic: str, message: Any, tenant_filter: Optional[str] = None) -> int:
        """
        Send message to all subscribers of a topic.
        
        Returns number of successful sends.
        """
        if topic not in self.topic_subscribers:
            return 0
        
        connection_ids = list(self.topic_subscribers[topic])
        sent_count = 0
        
        for connection_id in connection_ids:
            subscriber = self.subscribers.get(connection_id)
            if not subscriber:
                continue
            
            # Apply tenant filter if specified
            if tenant_filter and subscriber.tenant_id != tenant_filter:
                continue
            
            # Check queue size (backpressure)
            if subscriber.queue_size >= self.max_queue_size_per_connection:
                subscriber.dropped_messages += 1
                self.metrics["queue_overflow_drops"] += 1
                await self._record_metric("stream_drop_total", "queue_overflow")
                logger.warning(f"🚫 Queue overflow for {connection_id}: {subscriber.queue_size}")
                continue
            
            # Send message
            try:
                if subscriber.send_callback:
                    await subscriber.send_callback(message)
                    subscriber.queue_size += 1
                    subscriber.last_activity = time.time()
                    sent_count += 1
                
            except Exception as e:
                logger.error(f"Failed to send to {connection_id}: {e}")
                # Mark for cleanup
                subscriber.last_activity = 0
        
        if sent_count > 0:
            self.metrics["total_messages_sent"] += sent_count
            logger.debug(f"📤 Sent to {sent_count} subscribers on topic {topic}")
        
        return sent_count
    
    async def acknowledge_message(self, connection_id: str) -> None:
        """Acknowledge message delivery (reduces queue size)."""
        subscriber = self.subscribers.get(connection_id)
        if subscriber:
            subscriber.queue_size = max(0, subscriber.queue_size - 1)
            subscriber.last_activity = time.time()
    
    async def _drop_oldest_subscriber(self, tenant_id: str) -> None:
        """Drop the oldest subscriber for a tenant (PM requirement)."""
        tenant_connections = self.tenant_subscribers.get(tenant_id, set())
        if not tenant_connections:
            return
        
        # Find oldest connection
        oldest_connection = None
        oldest_time = float('inf')
        
        for connection_id in tenant_connections:
            subscriber = self.subscribers.get(connection_id)
            if subscriber and subscriber.connected_at < oldest_time:
                oldest_time = subscriber.connected_at
                oldest_connection = connection_id
        
        if oldest_connection:
            logger.info(f"🗑️ Dropping oldest subscriber for tenant {tenant_id}: {oldest_connection}")
            await self.unregister_subscriber(oldest_connection)
    
    async def _cleanup_stale_connections(self) -> int:
        """Clean up stale/inactive connections."""
        now = time.time()
        stale_threshold = now - self.connection_timeout_seconds
        
        stale_connections = [
            connection_id for connection_id, subscriber in self.subscribers.items()
            if subscriber.last_activity < stale_threshold
        ]
        
        for connection_id in stale_connections:
            logger.info(f"🧹 Cleaning up stale connection: {connection_id}")
            await self.unregister_subscriber(connection_id)
        
        if stale_connections:
            logger.info(f"🧹 Cleaned up {len(stale_connections)} stale connections")
        
        return len(stale_connections)
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_stale_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    async def _record_metric(self, metric_name: str, reason: str) -> None:
        """Record metric in Redis for monitoring."""
        try:
            redis_mgr = await get_redis()
            client = await redis_mgr.get_client()
            
            # Increment counter with reason label
            metric_key = f"metrics:{metric_name}:{reason}"
            await client.incr(metric_key)
            
            # Set TTL for metric (24 hours)
            await client.expire(metric_key, 86400)
            
            await client.close()
            
        except Exception as e:
            logger.error(f"Failed to record metric {metric_name}: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current backpressure metrics (PM requirement)."""
        # Calculate per-tenant stats
        tenant_stats = {}
        for tenant_id, connections in self.tenant_subscribers.items():
            tenant_stats[tenant_id] = {
                "active_connections": len(connections),
                "total_queue_size": sum(
                    self.subscribers[conn_id].queue_size
                    for conn_id in connections
                    if conn_id in self.subscribers
                ),
                "total_dropped_messages": sum(
                    self.subscribers[conn_id].dropped_messages
                    for conn_id in connections
                    if conn_id in self.subscribers
                )
            }
        
        # Calculate topic stats
        topic_stats = {
            topic: len(connections)
            for topic, connections in self.topic_subscribers.items()
        }
        
        return {
            **self.metrics,
            "tenant_stats": tenant_stats,
            "topic_stats": topic_stats,
            "limits": {
                "max_subscribers_per_tenant": self.max_subscribers_per_tenant,
                "max_total_subscribers": self.max_total_subscribers,
                "max_queue_size_per_connection": self.max_queue_size_per_connection
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for backpressure system."""
        try:
            metrics = self.get_metrics()
            
            # Calculate health indicators
            total_subs = metrics["total_subscribers"]
            global_usage = total_subs / self.max_total_subscribers
            
            # Check for concerning patterns
            warnings = []
            if global_usage > 0.8:
                warnings.append(f"Global subscriber usage high: {global_usage:.1%}")
            
            if metrics["queue_overflow_drops"] > 0:
                warnings.append(f"Queue overflow drops detected: {metrics['queue_overflow_drops']}")
            
            status = "healthy"
            if global_usage > 0.95:
                status = "degraded"
            if not self.subscribers:
                status = "idle"
            
            return {
                "status": status,
                "total_subscribers": total_subs,
                "global_usage": f"{global_usage:.1%}",
                "warnings": warnings,
                "cleanup_task_running": self._cleanup_task is not None and not self._cleanup_task.done()
            }
            
        except Exception as e:
            logger.error(f"Backpressure health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global backpressure manager
_backpressure_manager: Optional[StreamBackpressureManager] = None


async def get_backpressure_manager() -> StreamBackpressureManager:
    """Get global backpressure manager."""
    global _backpressure_manager
    
    if _backpressure_manager is None:
        import os
        
        _backpressure_manager = StreamBackpressureManager(
            max_subscribers_per_tenant=int(os.getenv("MAX_SUBSCRIBERS_PER_TENANT", "100")),
            max_total_subscribers=int(os.getenv("MAX_TOTAL_SUBSCRIBERS", "1000")),
            max_queue_size_per_connection=int(os.getenv("MAX_QUEUE_SIZE", "100"))
        )
        
        _backpressure_manager.start_cleanup_task()
    
    return _backpressure_manager


async def shutdown_backpressure_manager() -> None:
    """Shutdown global backpressure manager."""
    global _backpressure_manager
    if _backpressure_manager:
        await _backpressure_manager.stop_cleanup_task()
        _backpressure_manager = None


if __name__ == "__main__":
    # Test backpressure manager
    import asyncio
    
    async def test_backpressure():
        print("🔄 Testing stream backpressure manager...")
        
        # Create manager with low limits for testing
        manager = StreamBackpressureManager(
            max_subscribers_per_tenant=2,
            max_total_subscribers=5,
            max_queue_size_per_connection=3
        )
        
        # Test subscriber registration
        async def dummy_callback(message):
            print(f"Received: {message}")
        
        # Register some subscribers
        success1 = await manager.register_subscriber("tenant1", "topic1", "conn1", dummy_callback)
        success2 = await manager.register_subscriber("tenant1", "topic1", "conn2", dummy_callback)
        success3 = await manager.register_subscriber("tenant1", "topic1", "conn3", dummy_callback)  # Should drop oldest
        
        print(f"Registration results: {success1}, {success2}, {success3}")
        
        # Send messages
        sent = await manager.send_to_topic("topic1", {"test": "message"})
        print(f"Messages sent: {sent}")
        
        # Get metrics
        metrics = manager.get_metrics()
        print(f"Metrics: {metrics}")
        
        # Health check
        health = await manager.health_check()
        print(f"Health: {health}")
        
        print("✅ Backpressure test complete")
    
    asyncio.run(test_backpressure())