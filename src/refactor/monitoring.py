#!/usr/bin/env python3
"""
Monitoring hooks for performance tracking and observability
Lightweight counters and timers for production dashboards
"""

import threading
import time

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import Any

# ============================================================================
# METRICS STORAGE
# ============================================================================


@dataclass
class MetricStats:
    """Statistics for a single metric"""

    count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    last_time: float = 0.0
    errors: int = 0

    @property
    def avg_time(self) -> float:
        """Average time per call"""
        return self.total_time / self.count if self.count > 0 else 0.0

    def record(self, duration: float, error: bool = False):
        """Record a metric observation"""
        self.count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.last_time = duration
        if error:
            self.errors += 1


@dataclass
class CacheStats:
    """Cache hit/miss statistics"""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        """Cache hit rate"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


# ============================================================================
# METRICS COLLECTOR
# ============================================================================


class MetricsCollector:
    """Thread-safe metrics collection"""

    def __init__(self):
        self._metrics: dict[str, MetricStats] = {}
        self._cache_stats = CacheStats()
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._feature_flags: dict[str, bool] = {}

    def record_timing(self, name: str, duration: float, error: bool = False):
        """Record a timing metric"""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = MetricStats()
            self._metrics[name].record(duration, error)

    def record_cache_hit(self):
        """Record a cache hit"""
        with self._lock:
            self._cache_stats.hits += 1

    def record_cache_miss(self):
        """Record a cache miss"""
        with self._lock:
            self._cache_stats.misses += 1

    def record_cache_eviction(self):
        """Record a cache eviction"""
        with self._lock:
            self._cache_stats.evictions += 1

    def update_cache_size(self, size: int):
        """Update current cache size"""
        with self._lock:
            self._cache_stats.size = size

    def record_error(self, error_type: str):
        """Record an error occurrence"""
        # For now, we'll increment error count in a generic metric
        # This could be expanded to track specific error types
        with self._lock:
            if "errors" not in self._metrics:
                self._metrics["errors"] = MetricStats()
            self._metrics["errors"].record(0, error=True)

    def set_feature_flag(self, name: str, enabled: bool):
        """Set a feature flag status"""
        with self._lock:
            self._feature_flags[name] = enabled

    def get_metrics(self) -> dict[str, Any]:
        """Get all metrics as a dictionary"""
        with self._lock:
            uptime = time.time() - self._start_time

            # Convert metrics to dict
            metrics_dict = {}
            for name, stats in self._metrics.items():
                metrics_dict[name] = {
                    "count": stats.count,
                    "total_time": stats.total_time,
                    "avg_time": stats.avg_time,
                    "min_time": stats.min_time if stats.count > 0 else 0,
                    "max_time": stats.max_time,
                    "last_time": stats.last_time,
                    "errors": stats.errors,
                    "error_rate": stats.errors / stats.count if stats.count > 0 else 0,
                }

            return {
                "uptime_seconds": uptime,
                "metrics": metrics_dict,
                "cache": {
                    "hits": self._cache_stats.hits,
                    "misses": self._cache_stats.misses,
                    "hit_rate": self._cache_stats.hit_rate,
                    "evictions": self._cache_stats.evictions,
                    "size": self._cache_stats.size,
                },
                "feature_flags": self._feature_flags.copy(),
            }

    def reset(self):
        """Reset all metrics"""
        with self._lock:
            self._metrics.clear()
            self._cache_stats = CacheStats()
            self._start_time = time.time()


# Global metrics collector instance
_collector = MetricsCollector()

# ============================================================================
# DECORATORS
# ============================================================================


def timed(name: str | None = None):
    """Decorator to time function execution

    Usage:
        @timed("kp_calculation")
        def calculate_kp_lords(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        metric_name = name or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            error = False
            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                error = True
                raise
            finally:
                duration = time.perf_counter() - start
                _collector.record_timing(metric_name, duration, error)

        return wrapper

    return decorator


def cached_timed(func: Callable) -> Callable:
    """Decorator for cached functions to track hit/miss"""
    metric_name = f"{func.__module__}.{func.__name__}"

    @wraps(func)
    def wrapper(*args, **kwargs):
        # This would integrate with actual cache implementation
        # For now, just time the function
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.perf_counter() - start
            _collector.record_timing(metric_name, duration)

    return wrapper


# ============================================================================
# CONTEXT MANAGERS
# ============================================================================


class Timer:
    """Context manager for timing code blocks

    Usage:
        with Timer("complex_calculation"):
            # code to time
            pass
    """

    def __init__(self, name: str):
        self.name = name
        self.start = None

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start
        error = exc_type is not None
        _collector.record_timing(self.name, duration, error)


# ============================================================================
# PUBLIC API
# ============================================================================


def record_timing(name: str, duration: float, error: bool = False):
    """Record a timing metric"""
    _collector.record_timing(name, duration, error)


def record_cache_hit():
    """Record a cache hit"""
    _collector.record_cache_hit()


def record_cache_miss():
    """Record a cache miss"""
    _collector.record_cache_miss()


def get_metrics() -> dict[str, Any]:
    """Get current metrics snapshot"""
    return _collector.get_metrics()


def reset_metrics():
    """Reset all metrics"""
    _collector.reset()


def set_feature_flag(name: str, enabled: bool):
    """Set a feature flag"""
    _collector.set_feature_flag(name, enabled)


# ============================================================================
# PROMETHEUS INTEGRATION (Optional)
# ============================================================================


def setup_prometheus_metrics(port: int = 9090):
    """Setup Prometheus metrics endpoint

    Requires: pip install prometheus-client
    """
    try:
        import atexit

        from prometheus_client import (
            REGISTRY,
            CollectorRegistry,
            Counter,
            Gauge,
            Histogram,
        )

        # Define Prometheus metrics
        global prom_request_count, prom_request_duration, prom_cache_hits, prom_cache_misses
        global prom_active_requests, prom_uptime

        prom_request_count = Counter(
            "vedacore_requests_total",
            "Total requests",
            ["method", "endpoint", "status"],
        )
        prom_request_duration = Histogram(
            "vedacore_request_duration_seconds",
            "Request duration",
            ["method", "endpoint"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )
        prom_cache_hits = Counter("vedacore_cache_hits_total", "Cache hits")
        prom_cache_misses = Counter("vedacore_cache_misses_total", "Cache misses")
        prom_active_requests = Gauge("vedacore_active_requests", "Active requests")
        prom_uptime = Gauge("vedacore_uptime_seconds", "Application uptime")

        # Set uptime function
        prom_uptime.set_function(lambda: time.time() - _collector._start_time)

        # Note: In FastAPI, metrics are exposed via /metrics endpoint
        # So we don't start a separate server here

        return True
    except ImportError:
        return False


# ============================================================================
# TRACKING HELPERS
# ============================================================================

from contextlib import contextmanager


@contextmanager
def track_request(endpoint: str):
    """Track an API request"""
    start = time.perf_counter()
    try:
        if "prom_active_requests" in globals():
            prom_active_requests.inc()
        yield
        duration = time.perf_counter() - start
        if "prom_request_duration" in globals():
            prom_request_duration.labels(method="POST", endpoint=endpoint).observe(
                duration
            )
        if "prom_request_count" in globals():
            prom_request_count.labels(
                method="POST", endpoint=endpoint, status="success"
            ).inc()
    except Exception:
        duration = time.perf_counter() - start
        if "prom_request_count" in globals():
            prom_request_count.labels(
                method="POST", endpoint=endpoint, status="error"
            ).inc()
        raise
    finally:
        if "prom_active_requests" in globals():
            prom_active_requests.dec()


@contextmanager
def track_computation(name: str):
    """Track a computation"""
    with Timer(name):
        yield


def track_cache_hit(cache_type: str):
    """Track a cache hit"""
    record_cache_hit()
    if "prom_cache_hits" in globals():
        prom_cache_hits.inc()


def track_cache_miss(cache_type: str):
    """Track a cache miss"""
    record_cache_miss()
    if "prom_cache_misses" in globals():
        prom_cache_misses.inc()


def track_error(endpoint: str, error_type: str):
    """Track an error"""
    _collector.record_error(error_type)


# ============================================================================
# VARGA-SPECIFIC METRICS
# ============================================================================


def setup_varga_metrics():
    """Setup varga-specific Prometheus metrics"""
    try:
        from prometheus_client import Counter, Gauge, Histogram

        global prom_varga_requests, prom_varga_duration, prom_vargottama_checks
        global prom_vimshopaka_calculations, prom_varga_errors, prom_custom_schemes

        prom_varga_requests = Counter(
            "vedacore_varga_requests_total",
            "Total varga calculation requests",
            ["divisor", "scheme"],
        )

        prom_varga_duration = Histogram(
            "vedacore_varga_duration_seconds",
            "Varga calculation duration",
            ["divisor", "scheme"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
        )

        prom_vargottama_checks = Counter(
            "vedacore_vargottama_checks_total",
            "Total vargottama checks performed",
            ["check_count"],  # Number of vargas checked
        )

        prom_vimshopaka_calculations = Counter(
            "vedacore_vimshopaka_calculations_total",
            "Total Vimshopaka Bala calculations",
            ["varga_set"],  # shadvarga, saptavarga, etc.
        )

        prom_varga_errors = Counter(
            "vedacore_varga_errors_total",
            "Total varga calculation errors",
            ["error_type"],
        )

        prom_custom_schemes = Gauge(
            "vedacore_varga_custom_schemes", "Number of registered custom varga schemes"
        )

        return True
    except ImportError:
        return False


def track_varga_calculation(divisor: int, scheme: str, duration: float):
    """Track a varga calculation"""
    record_timing(f"varga.D{divisor}.{scheme}", duration)
    if "prom_varga_requests" in globals():
        prom_varga_requests.labels(divisor=str(divisor), scheme=scheme).inc()
    if "prom_varga_duration" in globals():
        prom_varga_duration.labels(divisor=str(divisor), scheme=scheme).observe(
            duration
        )


def track_vargottama_check(vargas_checked: int):
    """Track a vargottama check"""
    record_timing("vargottama_check", 0)  # Just count, no timing
    if "prom_vargottama_checks" in globals():
        prom_vargottama_checks.labels(check_count=str(vargas_checked)).inc()


def track_vimshopaka_calculation(varga_set: str):
    """Track a Vimshopaka Bala calculation"""
    if "prom_vimshopaka_calculations" in globals():
        prom_vimshopaka_calculations.labels(varga_set=varga_set).inc()


def track_varga_error(error_type: str):
    """Track a varga error"""
    if "prom_varga_errors" in globals():
        prom_varga_errors.labels(error_type=error_type).inc()


def update_custom_scheme_count(count: int):
    """Update the count of custom varga schemes"""
    if "prom_custom_schemes" in globals():
        prom_custom_schemes.set(count)


# ============================================================================
# ECLIPSE-SPECIFIC METRICS
# ============================================================================


# Eclipse metrics (if Prometheus is available)
def setup_eclipse_metrics():
    """Setup eclipse-specific Prometheus metrics"""
    try:
        from prometheus_client import Counter, Gauge, Histogram

        global prom_eclipse_requests, prom_eclipse_compute, prom_eclipse_cache_hits
        global prom_eclipse_cache_misses, prom_eclipse_errors

        prom_eclipse_requests = Counter(
            "vedacore_eclipse_requests_total",
            "Eclipse endpoint requests",
            ["endpoint", "kind"],
        )

        prom_eclipse_compute = Histogram(
            "vedacore_eclipse_compute_seconds",
            "Eclipse computation time",
            ["operation"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )

        prom_eclipse_cache_hits = Counter(
            "vedacore_eclipse_cache_hits_total", "Eclipse cache hits"
        )

        prom_eclipse_cache_misses = Counter(
            "vedacore_eclipse_cache_misses_total", "Eclipse cache misses"
        )

        prom_eclipse_errors = Counter(
            "vedacore_eclipse_errors_total", "Eclipse errors", ["type"]
        )

        return True
    except ImportError:
        return False


# ============================================================================
# PERFORMANCE PROFILING
# ============================================================================


class PerformanceProfile:
    """Performance profiling helper"""

    @staticmethod
    def profile_kp_calculation(iterations: int = 1000) -> dict[str, float]:
        """Profile KP calculation performance"""
        import random

        from refactor.kp_chain import kp_chain_for_longitude

        times = []
        for _ in range(iterations):
            longitude = random.uniform(0, 360)
            start = time.perf_counter()
            _ = kp_chain_for_longitude(longitude, levels=3)
            times.append(time.perf_counter() - start)

        return {
            "iterations": iterations,
            "total_time": sum(times),
            "avg_time": sum(times) / len(times),
            "min_time": min(times),
            "max_time": max(times),
            "median_time": sorted(times)[len(times) // 2],
        }

    @staticmethod
    def profile_change_detection(hours: int = 24) -> dict[str, float]:
        """Profile change detection performance"""
        from datetime import timedelta

        from refactor.facade import get_kp_lord_changes

        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(hours=hours)

        start = time.perf_counter()
        changes = get_kp_lord_changes(start_time, end_time)
        duration = time.perf_counter() - start

        return {
            "hours": hours,
            "changes_found": len(changes),
            "total_time": duration,
            "time_per_hour": duration / hours,
            "changes_per_hour": len(changes) / hours,
        }


# ============================================================================
# TRANSIT EVENT METRICS (Added per PM guidance)
# ============================================================================

# Try to use prometheus_client if available
try:
    from prometheus_client import Counter, Gauge, Histogram, Summary

    # Transit event metrics
    transit_events_detect_duration = Histogram(
        "transit_events_detect_duration_seconds",
        "Time taken for transit event detection",
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    )

    transit_events_emitted = Counter(
        "transit_events_emitted_total",
        "Total transit events emitted",
        ["market", "session"],
    )

    transit_events_suppressed = Counter(
        "transit_events_suppressed_total",
        "Transit events suppressed",
        ["reason"],  # dedup, low_score, session_filter
    )

    gate_score_summary = Summary("gate_score", "Gate scores distribution")

    kernel_score_summary = Summary("kernel_score", "Kernel scores distribution")

    confirm_score_summary = Summary("confirm_score", "Confirmation scores distribution")

    moon_cache_hit_ratio = Gauge(
        "moon_cache_hit_ratio", "Moon calculation cache hit ratio"
    )

    aspects_cache_hit_ratio = Gauge(
        "aspects_cache_hit_ratio", "Aspects cache hit ratio"
    )

    PROMETHEUS_ENABLED = True

except ImportError:
    # Prometheus not available - create dummy metrics
    PROMETHEUS_ENABLED = False

    class DummyMetric:
        def observe(self, *args, **kwargs):
            pass

        def inc(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

    transit_events_detect_duration = DummyMetric()
    transit_events_emitted = DummyMetric()
    transit_events_suppressed = DummyMetric()
    gate_score_summary = DummyMetric()
    kernel_score_summary = DummyMetric()
    confirm_score_summary = DummyMetric()
    moon_cache_hit_ratio = DummyMetric()
    aspects_cache_hit_ratio = DummyMetric()

# Initialize feature flags from config
try:
    from refactor.constants import FINANCE_LATENCY_ENABLED, KP_TIMING_OFFSET_ENABLED

    set_feature_flag("finance_latency", FINANCE_LATENCY_ENABLED)
    set_feature_flag("kp_timing_offset", KP_TIMING_OFFSET_ENABLED)
    set_feature_flag("numba_jit", True)  # From pyproject.toml
except ImportError:
    pass
