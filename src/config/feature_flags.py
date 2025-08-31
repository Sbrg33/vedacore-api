#!/usr/bin/env python3
"""
Feature flag utilities and decorators.

Provides a stable interface expected by various modules:
- get_feature_flags() -> returns a state object with boolean flags and helpers
- require_feature(flag) -> decorator to gate endpoints/functions
- FeatureFlags -> enum-style names for router decorators

Supports both enum-based flags (for API routers) and string keys used by
internal modules (e.g., "yoga_engine", "vedic_aspects").
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


class FeatureFlags(Enum):
    # Transit events (API) feature switches
    ENABLE_TRANSIT_EVENTS = "ENABLE_TRANSIT_EVENTS"
    ENABLE_MOON_GATES = "ENABLE_MOON_GATES"
    ENABLE_RESONANCE_KERNELS = "ENABLE_RESONANCE_KERNELS"
    ENABLE_DISPOSITOR_BRIDGES = "ENABLE_DISPOSITOR_BRIDGES"
    ENABLE_PROMISE_CHECK = "ENABLE_PROMISE_CHECK"
    ENABLE_DASHA_SYNC = "ENABLE_DASHA_SYNC"
    ENABLE_RP_CONFIRM = "ENABLE_RP_CONFIRM"


@dataclass
class FeatureFlagState:
    # Advisory layer toggles
    ENABLE_SHADBALA: bool = field(default_factory=lambda: _env_bool("ENABLE_SHADBALA", True))
    ENABLE_KP_RULING_PLANETS: bool = field(
        default_factory=lambda: _env_bool("ENABLE_KP_RULING_PLANETS", True)
    )
    ENABLE_AVASTHAS: bool = field(default_factory=lambda: _env_bool("ENABLE_AVASTHAS", True))
    ENABLE_ASHTAKAVARGA: bool = field(
        default_factory=lambda: _env_bool("ENABLE_ASHTAKAVARGA", True)
    )
    ENABLE_VEDIC_ASPECTS: bool = field(
        default_factory=lambda: _env_bool("ENABLE_VEDIC_ASPECTS", True)
    )
    ENABLE_PANCHANGA_FULL: bool = field(
        default_factory=lambda: _env_bool("ENABLE_PANCHANGA_FULL", True)
    )
    ENABLE_DAILY_WINDOWS: bool = field(
        default_factory=lambda: _env_bool("ENABLE_DAILY_WINDOWS", True)
    )
    ENABLE_YOGA_ENGINE: bool = field(
        default_factory=lambda: _env_bool("ENABLE_YOGA_ENGINE", True)
    )

    # Varga (Divisional charts) toggles
    ENABLE_VARGA_ADVISORY: bool = field(
        default_factory=lambda: _env_bool("ENABLE_VARGA_ADVISORY", True)
    )
    ENABLE_VARGOTTAMA: bool = field(
        default_factory=lambda: _env_bool("ENABLE_VARGOTTAMA", True)
    )
    ENABLE_VIMSHOPAKA_BALA: bool = field(
        default_factory=lambda: _env_bool("ENABLE_VIMSHOPAKA_BALA", True)
    )
    ENABLE_CUSTOM_VARGA: bool = field(
        default_factory=lambda: _env_bool("ENABLE_CUSTOM_VARGA", False)
    )
    ENABLED_VARGAS: list[str] = field(
        default_factory=lambda: os.getenv(
            "ENABLED_VARGAS",
            "D9,D10,D12",
        ).replace(" ", "").split(",")
    )

    # Transit Events (API) toggles (mirrors FeatureFlags enum)
    ENABLE_TRANSIT_EVENTS: bool = field(
        default_factory=lambda: _env_bool("ENABLE_TRANSIT_EVENTS", True)
    )
    ENABLE_MOON_GATES: bool = field(
        default_factory=lambda: _env_bool("ENABLE_MOON_GATES", True)
    )
    ENABLE_RESONANCE_KERNELS: bool = field(
        default_factory=lambda: _env_bool("ENABLE_RESONANCE_KERNELS", True)
    )
    ENABLE_DISPOSITOR_BRIDGES: bool = field(
        default_factory=lambda: _env_bool("ENABLE_DISPOSITOR_BRIDGES", True)
    )
    ENABLE_PROMISE_CHECK: bool = field(
        default_factory=lambda: _env_bool("ENABLE_PROMISE_CHECK", True)
    )
    ENABLE_DASHA_SYNC: bool = field(
        default_factory=lambda: _env_bool("ENABLE_DASHA_SYNC", True)
    )
    ENABLE_RP_CONFIRM: bool = field(
        default_factory=lambda: _env_bool("ENABLE_RP_CONFIRM", True)
    )

    # System/Router toggles
    ENABLE_ATS: bool = field(
        default_factory=lambda: _env_bool("ENABLE_ATS", True)
    )

    # Advisory tuning
    ADVISORY_TIMEOUT_MS: int = field(
        default_factory=lambda: int(os.getenv("ADVISORY_TIMEOUT_MS", "1000"))
    )

    def enabled_features(self) -> list[str]:
        """Return a list of human-friendly feature names that are enabled."""
        enabled = []
        mapping: dict[str, bool] = self.to_dict()
        for name, value in mapping.items():
            if isinstance(value, bool) and value:
                enabled.append(name)
        return enabled

    def to_dict(self) -> dict[str, Any]:
        return {
            "ENABLE_SHADBALA": self.ENABLE_SHADBALA,
            "ENABLE_KP_RULING_PLANETS": self.ENABLE_KP_RULING_PLANETS,
            "ENABLE_AVASTHAS": self.ENABLE_AVASTHAS,
            "ENABLE_ASHTAKAVARGA": self.ENABLE_ASHTAKAVARGA,
            "ENABLE_VEDIC_ASPECTS": self.ENABLE_VEDIC_ASPECTS,
            "ENABLE_PANCHANGA_FULL": self.ENABLE_PANCHANGA_FULL,
            "ENABLE_DAILY_WINDOWS": self.ENABLE_DAILY_WINDOWS,
            "ENABLE_YOGA_ENGINE": self.ENABLE_YOGA_ENGINE,
            "ENABLE_VARGA_ADVISORY": self.ENABLE_VARGA_ADVISORY,
            "ENABLE_VARGOTTAMA": self.ENABLE_VARGOTTAMA,
            "ENABLE_VIMSHOPAKA_BALA": self.ENABLE_VIMSHOPAKA_BALA,
            "ENABLE_CUSTOM_VARGA": self.ENABLE_CUSTOM_VARGA,
            "ENABLED_VARGAS": self.ENABLED_VARGAS,
            # Transit event flags
            "ENABLE_TRANSIT_EVENTS": self.ENABLE_TRANSIT_EVENTS,
            "ENABLE_MOON_GATES": self.ENABLE_MOON_GATES,
            "ENABLE_RESONANCE_KERNELS": self.ENABLE_RESONANCE_KERNELS,
            "ENABLE_DISPOSITOR_BRIDGES": self.ENABLE_DISPOSITOR_BRIDGES,
            "ENABLE_PROMISE_CHECK": self.ENABLE_PROMISE_CHECK,
            "ENABLE_DASHA_SYNC": self.ENABLE_DASHA_SYNC,
            "ENABLE_RP_CONFIRM": self.ENABLE_RP_CONFIRM,
            # System/Router toggles
            "ENABLE_ATS": self.ENABLE_ATS,
            # Advisory tuning
            "ADVISORY_TIMEOUT_MS": self.ADVISORY_TIMEOUT_MS,
        }


# Module-level singleton
_FLAGS: FeatureFlagState | None = None


def get_feature_flags() -> FeatureFlagState:
    global _FLAGS
    if _FLAGS is None:
        _FLAGS = FeatureFlagState()
    return _FLAGS


# Mapping for string-based require_feature usage
_STRING_FLAG_MAP: dict[str, str] = {
    # modules/* use these short names
    "yoga_engine": "ENABLE_YOGA_ENGINE",
    "vedic_aspects": "ENABLE_VEDIC_ASPECTS",
    "jaimini": "ENABLE_VARGA_ADVISORY",  # use varga advisory gate for now
    "ashtakavarga": "ENABLE_ASHTAKAVARGA",
    "shadbala": "ENABLE_SHADBALA",
    "avasthas": "ENABLE_AVASTHAS",
    "kp_ruling_planets": "ENABLE_KP_RULING_PLANETS",
    "daily_windows": "ENABLE_DAILY_WINDOWS",
    "panchanga_full": "ENABLE_PANCHANGA_FULL",
    "ats": "ENABLE_ATS",
}


def is_feature_enabled(flag: FeatureFlags | str) -> bool:
    flags = get_feature_flags()

    if isinstance(flag, FeatureFlags):
        attr = flag.value
        return getattr(flags, attr, False) is True

    # string name support
    attr = _STRING_FLAG_MAP.get(flag, None)
    if attr is None:
        # Unknown string flag: default to False to be safe
        return False
    return getattr(flags, attr, False) is True


def require_feature(flag: FeatureFlags | str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to gate function/endpoint by feature flag.

    Works with both sync and async callables. For FastAPI endpoints,
    raises HTTPException 403 when disabled. For plain functions,
    raises RuntimeError when disabled.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not is_feature_enabled(flag):
                    try:
                        from fastapi import HTTPException

                        raise HTTPException(status_code=403, detail="Feature disabled")
                    except Exception:
                        raise RuntimeError("Feature disabled")
                return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not is_feature_enabled(flag):
                raise RuntimeError("Feature disabled")
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator
