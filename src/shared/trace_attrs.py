from __future__ import annotations

from typing import Optional


def set_common_attrs(
    span,
    *,
    cache_status: str,
    compute_ms: float | int,
    algo_version: str,
    api_version: str,
    norm_version: str,
    eph_version: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> None:
    """Apply a consistent set of tracing attributes.

    Keep naming stable for cross-service queries.
    """
    try:
        span.set_attribute("cache.status", cache_status)
        span.set_attribute("compute.time_ms", compute_ms)
        span.set_attribute("algo.version", algo_version)
        span.set_attribute("api.version", api_version)
        span.set_attribute("normalization.version", norm_version)
        span.set_attribute("ephemeris.dataset_version", eph_version)
        if target_type is not None:
            span.set_attribute("kp.target.type", target_type)
        if target_id is not None:
            span.set_attribute("kp.target.id", str(target_id))
    except Exception:
        # Safe no-op on any instrumentation errors
        pass

