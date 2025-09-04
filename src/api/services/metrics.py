"""
metrics.py — Prometheus metrics for VedaCore streaming platform.

PM-specified metrics:
- vc_stream_connections{tenant,topic,protocol} - Active connections
- vc_stream_publish_total{topic} - Messages published
- vc_stream_dropped_total{topic} - Backpressure drops
- vc_auth_fail_total{reason} - Authentication failures
- vc_quota_violation_total{tenant,limit_type} - Rate limit violations
- vc_stream_latency_seconds{topic} - Publish to delivery latency

Integration with existing Prometheus setup in VedaCore.
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, Histogram, Info

# ===========================
# STREAMING METRICS
# ===========================

# Active connections by tenant, topic, and protocol (SSE/WebSocket)
vc_stream_connections = Gauge(
    "vc_stream_connections",
    "Active streaming connections",
    ["tenant", "topic", "protocol"],
)

# Total messages published to topics
vc_stream_publish_total = Counter(
    "vc_stream_publish_total", "Total messages published to streaming topics", ["topic"]
)

# Messages dropped due to backpressure
vc_stream_dropped_total = Counter(
    "vc_stream_dropped_total",
    "Messages dropped due to backpressure or client disconnect",
    ["topic", "reason"],  # reason: backpressure, disconnect, error
)

# Latency from publish to delivery
vc_stream_latency_seconds = Histogram(
    "vc_stream_latency_seconds",
    "Time from message publish to client delivery",
    ["topic"],
    buckets=(
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        float("inf"),
    ),
)

# SSE handshake outcomes by auth method
vc_sse_handshake_total = Counter(
    "vc_sse_handshake_total",
    "SSE handshake attempts by method and outcome",
    ["method", "outcome"],  # method: header, query, unknown; outcome: success, invalid_token, missing_token, rate_limited
)

# SSE handshake latency
vc_sse_handshake_latency_seconds = Histogram(
    "vc_sse_handshake_latency_seconds",
    "Latency of SSE handshake",
    ["method", "outcome"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, float("inf")),
)

# SSE reset events (resume gap)
vc_sse_reset_total = Counter(
    "vc_sse_reset_total", "Total SSE resets due to resume gap", ["topic"]
)

# SSE resume replayed count
vc_sse_resume_replayed_total = Counter(
    "vc_sse_resume_replayed_total",
    "Total number of replayed events on SSE resume",
    ["topic"],
)

# ===========================
# AUTHENTICATION METRICS
# ===========================

# Authentication failures by reason
vc_auth_fail_total = Counter(
    "vc_auth_fail_total",
    "Authentication failures by reason",
    ["reason", "endpoint"],  # reason: invalid_token, missing_token, expired, etc.
)

# Successful authentications
vc_auth_success_total = Counter(
    "vc_auth_success_total", "Successful authentications", ["tenant", "endpoint"]
)

# ===========================
# RATE LIMITING METRICS
# ===========================

# Rate limit violations
vc_quota_violation_total = Counter(
    "vc_quota_violation_total",
    "Rate limit violations by tenant and type",
    ["tenant", "limit_type", "endpoint"],  # limit_type: qps, connection
)

# Current rate limit usage
vc_rate_limit_usage = Gauge(
    "vc_rate_limit_usage",
    "Current rate limit usage as percentage of limit",
    ["tenant", "limit_type"],
)

# ===========================
# CONNECTION LIFECYCLE
# ===========================

# Connection duration
vc_connection_duration_seconds = Histogram(
    "vc_connection_duration_seconds",
    "Duration of streaming connections",
    ["tenant", "protocol", "disconnect_reason"],
    buckets=(1, 5, 15, 30, 60, 300, 900, 1800, 3600, 7200, float("inf")),
)

# Messages per connection
vc_messages_per_connection = Histogram(
    "vc_messages_per_connection",
    "Number of messages delivered per connection",
    ["tenant", "topic", "protocol"],
    buckets=(1, 10, 50, 100, 500, 1000, 5000, 10000, float("inf")),
)

# ===========================
# WEBSOCKET-SPECIFIC METRICS
# ===========================

# WebSocket message flow
vc_stream_websocket_messages = Counter(
    "vc_stream_websocket_messages_total",
    "WebSocket messages sent/received",
    ["tenant", "topic", "direction"],  # direction: sent, received
)

# ===========================
# TOPIC-SPECIFIC METRICS
# ===========================

# Active subscribers per topic
vc_topic_subscribers = Gauge(
    "vc_topic_subscribers", "Number of active subscribers per topic", ["topic"]
)

# Topic message rate
vc_topic_message_rate = Gauge(
    "vc_topic_message_rate_per_second",
    "Current message publishing rate per topic",
    ["topic"],
)

# ===========================
# ACTIVATION STREAM METRICS (PM-specified)
# ===========================

# Activation stream requests
vc_activation_stream_requests_total = Counter(
    "vc_activation_stream_requests_total",
    "Total activation stream requests",
    ["status"],  # status: success, error, timeout, auth_fail
)

# Activation stream connection duration
vc_activation_stream_duration_seconds = Histogram(
    "vc_activation_stream_duration_seconds",
    "Duration of activation stream connections",
    buckets=(1, 5, 15, 30, 60, 300, 900, 1800, 3600, 7200, float("inf")),
)

# Stream bus heartbeats
vc_stream_bus_heartbeats_total = Counter(
    "vc_stream_bus_heartbeats_total",
    "Total heartbeats sent on streaming topics",
    ["topic"],
)

# Stream publish events
vc_stream_publish_events_total = Counter(
    "vc_stream_publish_events_total",
    "Total publish events on streaming topics",
    ["topic"],
)

# Stream disconnects with reason
vc_stream_disconnects_total = Counter(
    "vc_stream_disconnects_total",
    "Total stream disconnections by reason",
    ["reason"],  # reason: normal, error, timeout, client_disconnect
)

# ===========================
# SYSTEM HEALTH METRICS
# ===========================

# Service info
vc_streaming_info = Info("vc_streaming_info", "VedaCore streaming service information")

# Queue sizes (for backpressure monitoring)
vc_queue_size = Gauge(
    "vc_queue_size_messages",
    "Current streaming queue sizes",
    ["tenant", "topic", "queue_type"],  # queue_type: subscriber, broadcast
)

# Memory usage by streaming components
vc_memory_usage_bytes = Gauge(
    "vc_memory_usage_bytes",
    "Memory usage by streaming components",
    ["component"],  # component: stream_manager, ws_manager, rate_limiter
)

# ===========================
# METRIC COLLECTION HELPERS
# ===========================


class StreamingMetricsCollector:
    """Helper class to collect and update streaming metrics."""

    def __init__(self):
        self._message_rates: dict[str, float] = {}
        self._last_update = time.time()

    def record_connection(self, tenant: str, topic: str, protocol: str):
        """Record a new streaming connection."""
        vc_stream_connections.labels(
            tenant=tenant, topic=topic, protocol=protocol
        ).inc()

    def record_disconnection(
        self,
        tenant: str,
        topic: str,
        protocol: str,
        duration_seconds: float,
        reason: str = "normal",
        messages_delivered: int = 0,
    ):
        """Record a streaming disconnection with metrics."""
        # Decrement active connections
        vc_stream_connections.labels(
            tenant=tenant, topic=topic, protocol=protocol
        ).dec()

        # Record connection duration
        vc_connection_duration_seconds.labels(
            tenant=tenant, protocol=protocol, disconnect_reason=reason
        ).observe(duration_seconds)

        # Record messages per connection
        vc_messages_per_connection.labels(
            tenant=tenant, topic=topic, protocol=protocol
        ).observe(messages_delivered)

    def record_message_published(
        self, topic: str, latency_seconds: float | None = None
    ):
        """Record a message published to a topic."""
        vc_stream_publish_total.labels(topic=topic).inc()

        if latency_seconds is not None:
            vc_stream_latency_seconds.labels(topic=topic).observe(latency_seconds)

    def record_sse_handshake(self, method: str, outcome: str, latency_seconds: float | None = None):
        """Record SSE handshake attempt."""
        vc_sse_handshake_total.labels(method=method, outcome=outcome).inc()
        if latency_seconds is not None:
            vc_sse_handshake_latency_seconds.labels(method=method, outcome=outcome).observe(latency_seconds)

    def record_sse_reset(self, topic: str):
        vc_sse_reset_total.labels(topic=topic).inc()

    def record_sse_resume_replayed(self, topic: str, count: int):
        if count > 0:
            vc_sse_resume_replayed_total.labels(topic=topic).inc(count)

    def record_message_dropped(self, topic: str, reason: str = "backpressure"):
        """Record a message dropped."""
        vc_stream_dropped_total.labels(topic=topic, reason=reason).inc()

    def record_websocket_message_sent(self, tenant: str, topic: str):
        """Record a WebSocket message sent to client."""
        vc_stream_websocket_messages.labels(
            tenant=tenant, topic=topic, direction="sent"
        ).inc()

    def record_connection_completed(
        self,
        tenant: str,
        topic: str,
        protocol: str,
        duration_seconds: float,
        messages_delivered: int,
    ):
        """Record a completed streaming connection."""
        self.record_disconnection(
            tenant=tenant,
            topic=topic,
            protocol=protocol,
            duration_seconds=duration_seconds,
            reason="completed",
            messages_delivered=messages_delivered,
        )

    def record_auth_success(self, tenant: str, endpoint: str):
        """Record successful authentication."""
        vc_auth_success_total.labels(tenant=tenant, endpoint=endpoint).inc()

    def record_auth_failure(self, reason: str, endpoint: str):
        """Record authentication failure."""
        vc_auth_fail_total.labels(reason=reason, endpoint=endpoint).inc()

    def record_rate_limit_violation(self, tenant: str, limit_type: str, endpoint: str):
        """Record rate limit violation."""
        vc_quota_violation_total.labels(
            tenant=tenant, limit_type=limit_type, endpoint=endpoint
        ).inc()

    def update_rate_limit_usage(
        self, tenant: str, limit_type: str, usage_percent: float
    ):
        """Update current rate limit usage percentage."""
        vc_rate_limit_usage.labels(tenant=tenant, limit_type=limit_type).set(
            usage_percent
        )

    def update_topic_subscribers(self, topic: str, count: int):
        """Update subscriber count for a topic."""
        vc_topic_subscribers.labels(topic=topic).set(count)

    def update_queue_size(self, tenant: str, topic: str, queue_type: str, size: int):
        """Update queue size metric."""
        vc_queue_size.labels(tenant=tenant, topic=topic, queue_type=queue_type).set(
            size
        )

    def update_memory_usage(self, component: str, bytes_used: int):
        """Update memory usage for a component."""
        vc_memory_usage_bytes.labels(component=component).set(bytes_used)

    def calculate_message_rates(self, topic_message_counts: dict[str, int]):
        """Calculate and update message rates per topic."""
        current_time = time.time()
        time_delta = current_time - self._last_update

        if time_delta > 0:
            for topic, count in topic_message_counts.items():
                previous_count = self._message_rates.get(topic, count)
                rate = max(0, (count - previous_count) / time_delta)

                vc_topic_message_rate.labels(topic=topic).set(rate)
                self._message_rates[topic] = count

        self._last_update = current_time

    # PM-specified activation stream metrics
    def record_activation_stream_request(self, status: str):
        """Record activation stream request with status."""
        vc_activation_stream_requests_total.labels(status=status).inc()

    def record_activation_stream_duration(self, duration_seconds: float):
        """Record activation stream connection duration."""
        vc_activation_stream_duration_seconds.observe(duration_seconds)

    def record_stream_heartbeat(self, topic: str):
        """Record a heartbeat sent on a topic."""
        vc_stream_bus_heartbeats_total.labels(topic=topic).inc()

    def record_stream_publish_event(self, topic: str):
        """Record a publish event on a topic."""
        vc_stream_publish_events_total.labels(topic=topic).inc()

    def record_stream_disconnect(self, reason: str):
        """Record a stream disconnection with reason."""
        vc_stream_disconnects_total.labels(reason=reason).inc()


# Global metrics collector instance
streaming_metrics = StreamingMetricsCollector()

# ===========================
# INITIALIZATION
# ===========================


def initialize_streaming_metrics():
    """Initialize streaming service metrics with static information."""
    vc_streaming_info.info(
        {
            "version": "1.0.0",
            "service": "vedacore_streaming",
            "protocols": "sse,websocket",
            "authentication": "jwt_query_parameter",
            "rate_limiting": "token_bucket",
        }
    )


# ===========================
# INTEGRATION HELPERS
# ===========================


def get_all_streaming_metrics() -> dict[str, float]:
    """Get current values of all streaming metrics for monitoring."""
    from prometheus_client import REGISTRY

    metrics = {}
    for collector in REGISTRY._collector_to_names:
        for metric_family in collector.collect():
            if (
                metric_family.name.startswith("vc_stream_")
                or metric_family.name.startswith("vc_auth_")
                or metric_family.name.startswith("vc_quota_")
            ):
                for sample in metric_family.samples:
                    key = f"{sample.name}_{hash(str(sample.labels))}"
                    metrics[key] = sample.value

    return metrics
