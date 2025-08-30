#!/usr/bin/env python3
"""
ATS Service - Business logic layer for ATS scoring
Handles caching, metrics, and orchestration
"""

import json
import logging
import os
import time

from datetime import UTC, datetime, timedelta
from typing import Any

from app.utils.hash_keys import context_hash
from interfaces.ats_system_adapter import ATSSystemAdapter
from refactor.monitoring import timed


# Simple metric functions (would be replaced with actual Prometheus client in production)
def increment_counter(name: str, labels: dict = None):
    """Increment a counter metric"""
    # In production, this would use prometheus_client.Counter
    pass


def observe_value(name: str, value: float, labels: dict = None):
    """Observe a value for histogram/gauge"""
    # In production, this would use prometheus_client.Histogram or Gauge
    pass


# Try to import cache client if available
try:
    from app.core.cache import get_cache_client
except ImportError:
    # Fallback if cache module doesn't exist
    def get_cache_client():
        return None


logger = logging.getLogger(__name__)


class ATSError(Exception):
    """Base exception for ATS-related errors"""

    pass


class ATSConfigError(ATSError):
    """Configuration-related errors (missing files, invalid YAML, etc)"""

    pass


class ATSCalculationError(ATSError):
    """Runtime calculation errors"""

    pass


class ATSCacheError(ATSError):
    """Cache-related errors"""

    pass


class ATSService:
    """
    ATS Service Layer

    Responsibilities:
    - Cache management (60s TTL)
    - Metrics emission
    - Error handling
    - No business logic - just orchestration
    """

    def __init__(self, context_yaml: str | None = None):
        """
        Initialize ATS service

        Args:
            context_yaml: Optional path to context YAML file
        """
        self.adapter = ATSSystemAdapter(context_yaml=context_yaml)
        self.cache_ttl = 60  # 60 seconds cache TTL
        self._cache = {}  # Simple in-memory cache if Redis not available

        # Try to get Redis cache client
        try:
            self.redis_client = get_cache_client()
        except:
            self.redis_client = None
            logger.warning("Redis not available, using in-memory cache")

    def _get_cache_key(self, ts: datetime) -> str:
        """Generate cache key for given timestamp"""
        # Round to minute for caching
        ts_minute = ts.replace(second=0, microsecond=0)
        ts_epoch = int(ts_minute.timestamp())
        ctx_hash = context_hash(self.adapter.context_yaml)
        return f"ats:{ctx_hash}:{ts_epoch}"

    def _get_from_cache(self, key: str) -> dict | None:
        """Get value from cache"""
        if self.redis_client:
            try:
                cached = self.redis_client.get(key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Cache get failed: {e}")
        else:
            # In-memory cache fallback
            if key in self._cache:
                cached_data, cached_time = self._cache[key]
                if time.time() - cached_time < self.cache_ttl:
                    return cached_data
                else:
                    del self._cache[key]
        return None

    def _set_cache(self, key: str, value: dict):
        """Set value in cache with TTL"""
        if self.redis_client:
            try:
                self.redis_client.setex(key, self.cache_ttl, json.dumps(value))
            except Exception as e:
                logger.warning(f"Cache set failed: {e}")
        else:
            # In-memory cache fallback
            self._cache[key] = (value, time.time())
            # Clean old entries if cache gets too large
            if len(self._cache) > 1000:
                current_time = time.time()
                self._cache = {
                    k: v
                    for k, v in self._cache.items()
                    if current_time - v[1] < self.cache_ttl
                }

    @timed("ats_service.get_scores")
    def get_scores(
        self, timestamp: datetime | None = None, targets: list[int] | None = None
    ) -> dict[str, Any]:
        """
        Get ATS scores for given timestamp

        Args:
            timestamp: UTC timestamp (defaults to current time)
            targets: Optional list of target planet IDs

        Returns:
            Dictionary with scores and metadata
        """
        # Default to current time if not specified
        if timestamp is None:
            timestamp = datetime.now(UTC)
        elif timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Round to minute for caching
        ts_minute = timestamp.replace(second=0, microsecond=0)
        cache_key = self._get_cache_key(ts_minute)

        # Check cache first
        cached = self._get_from_cache(cache_key)
        if cached:
            increment_counter("ats_cache_hits", labels={"status": "hit"})
            observe_value("ats_cache_hit_ratio", 1.0)
            return {**cached, "cache_hit": True}

        # Cache miss - calculate
        increment_counter("ats_cache_hits", labels={"status": "miss"})
        observe_value("ats_cache_hit_ratio", 0.0)

        start_time = time.perf_counter()

        try:
            # Call adapter
            result = self.adapter.calculate(ts_minute, targets=targets)

            # Calculate timing
            compute_ms = (time.perf_counter() - start_time) * 1000
            result["compute_ms"] = round(compute_ms, 2)

            # Emit metrics with context label
            context_name = os.path.basename(self.adapter.context_yaml).replace(
                ".yaml", ""
            )
            observe_value(
                "ats_compute_ms", compute_ms, labels={"context": context_name}
            )

            # Track scores for each target with context
            for planet_id, score in result.get("scores_norm", {}).items():
                observe_value(
                    "ats_score",
                    score,
                    labels={"planet": str(planet_id), "context": context_name},
                )

            # Calculate deltas from previous minute if available
            prev_ts = ts_minute - timedelta(minutes=1)
            prev_key = self._get_cache_key(prev_ts)
            prev_cached = self._get_from_cache(prev_key)

            if prev_cached and "scores_norm" in prev_cached:
                deltas = {}
                for planet_id, score in result.get("scores_norm", {}).items():
                    prev_score = prev_cached["scores_norm"].get(planet_id, 0)
                    delta = score - prev_score
                    deltas[planet_id] = round(delta, 2)
                    observe_value(
                        "ats_score_delta",
                        abs(delta),
                        labels={"planet": str(planet_id), "context": context_name},
                    )
                result["deltas"] = deltas

            # Cache the result
            self._set_cache(cache_key, result)

            return {**result, "cache_hit": False}

        except Exception as e:
            increment_counter("ats_errors", labels={"type": "calculation"})
            logger.error(f"ATS calculation failed: {e}")
            # Wrap in custom exception for structured handling
            raise ATSCalculationError(f"Failed to calculate ATS scores: {e!s}") from e

    def get_context(self) -> dict[str, Any]:
        """
        Get current ATS context configuration

        Returns:
            Dictionary with context information
        """
        return {
            "context_file": self.adapter.context_yaml,
            "ref_norm": self.adapter.ref_norm,
            "default_targets": self.adapter.default_targets,
            "cache_ttl": self.cache_ttl,
            "metadata": self.adapter.get_metadata(),
        }

    def get_scores_batch(
        self,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 1,
        targets: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get ATS scores for a time range

        Args:
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)
            interval_minutes: Interval between calculations
            targets: Optional list of target planet IDs

        Returns:
            List of score dictionaries
        """
        results = []
        current = start_time

        while current <= end_time:
            try:
                score = self.get_scores(current, targets=targets)
                results.append(score)
            except Exception as e:
                logger.warning(f"Failed to get scores for {current}: {e}")
                results.append({"timestamp": current.isoformat(), "error": str(e)})

            current += timedelta(minutes=interval_minutes)

        return results

    def validate_scores(self, timestamp: datetime | None = None) -> dict[str, Any]:
        """
        Validate ATS scores against expected ranges

        Args:
            timestamp: UTC timestamp to validate

        Returns:
            Validation report
        """
        result = self.get_scores(timestamp)

        issues = []

        # Check score ranges (should be 0-100 after normalization)
        for planet_id, score in result.get("scores_norm", {}).items():
            if not (0 <= score <= 100):
                issues.append(f"Planet {planet_id} score {score} out of range [0, 100]")

        # Check that raw scores are positive
        for planet_id, score in result.get("scores_raw", {}).items():
            if score < 0:
                issues.append(f"Planet {planet_id} raw score {score} is negative")

        # Check computation time (aligned targets: cached <10ms, cold <50ms)
        compute_ms = result.get("compute_ms", 0)
        cache_hit = result.get("cache_hit", False)

        if cache_hit and compute_ms > 10:
            issues.append(f"Cached computation time {compute_ms}ms exceeds 10ms target")
        elif not cache_hit and compute_ms > 50:
            issues.append(f"Cold computation time {compute_ms}ms exceeds 50ms target")

        return {
            "timestamp": result.get("timestamp"),
            "valid": len(issues) == 0,
            "issues": issues,
            "scores": result.get("scores_norm"),
            "compute_ms": compute_ms,
            "cache_hit": result.get("cache_hit", False),
        }
