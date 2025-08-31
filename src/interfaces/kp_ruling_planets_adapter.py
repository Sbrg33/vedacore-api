from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:
    from interfaces.advisory_adapter_protocol import (
        AdvisorySystemAdapter as SystemAdapter,
    )
except Exception:
    from typing import Protocol

    class SystemAdapter(Protocol):
        id: str
        version: str

        def compute(self, ctx: Mapping[str, Any]) -> Mapping[str, Any]: ...
        def explain(self, out: Mapping[str, Any]) -> Mapping[str, Any]: ...
        def schema(self) -> Mapping[str, Any]: ...
        def dependencies(self) -> list[str]: ...


# Try real RP implementation; fallback to minimal stub if unavailable
try:
    from refactor.kp_ruling_planets import RPConfig, ruling_planets  # type: ignore
    _RP_AVAILABLE = True
except Exception:  # pragma: no cover - runtime fallback
    _RP_AVAILABLE = False

    class RPConfig:  # type: ignore
        pass

    def ruling_planets(wd, asc, moon, is_ex, is_own, cfg):  # type: ignore
        # Minimal fallback: rank by a simple deterministic rule
        order = ["SU", "MO", "MA", "ME", "JU", "VE", "SA", "RA", "KE"]
        ranked = [(p, 10 - i) for i, p in enumerate(order)]
        return {"rp_ranked": ranked, "rp_primary": [p for p, _ in ranked[:5]]}


class KPRulingPlanetsAdapter:
    id = "kp_ruling_planets"
    version = "0.1.0"

    def compute(self, ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        wd = int(ctx.get("weekday_idx"))

        # Handle both dict and tuple/list formats for chains
        # Use safe default of Moon chain to avoid "LA" pseudo-planet in rankings
        asc_raw = ctx.get("asc_chain")
        if not asc_raw:
            # If no asc_chain provided, raise validation error for explicit requirement
            return {
                "error": "asc_chain is required",
                "error_type": "validation_error",
                "detail": "ascendant chain (nl, sl, ssl) must be provided for RP calculation",
            }

        if isinstance(asc_raw, dict):
            asc = (
                asc_raw.get("nl", "MO"),
                asc_raw.get("sl", "MO"),
                asc_raw.get("ssl", "MO"),
            )
        else:
            asc = tuple(asc_raw) if len(asc_raw) >= 3 else ("MO", "MO", "MO")

        moon_raw = ctx.get("moon_chain") or {"nl": "MO", "sl": "MO", "ssl": "MO"}
        if isinstance(moon_raw, dict):
            moon = (
                moon_raw.get("nl", "MO"),
                moon_raw.get("sl", "MO"),
                moon_raw.get("ssl", "MO"),
            )
        else:
            moon = tuple(moon_raw) if len(moon_raw) >= 3 else ("MO", "MO", "MO")

        is_ex = ctx.get("is_exalted") or {}
        is_own = ctx.get("is_own") or {}

        out = ruling_planets(wd, asc, moon, is_ex, is_own, RPConfig())

        # Add required fields for Pydantic response model
        out.update(
            {
                "adapter_id": self.id,
                "adapter_version": self.version,
                "weekday_idx": wd,
                "total_score": sum(score for _, score in out.get("rp_ranked", [])),
                "correlation_id": ctx.get("correlation_id", "unknown"),
            }
        )
        return out

    def explain(self, out: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "why": "KP RP scoring = Day lord + Asc chain + Moon chain (+fortification)"
        }

    def schema(self) -> Mapping[str, Any]:
        return {
            "input": {
                "weekday_idx": "0=Mon..6=Sun",
                "asc_chain": "(NL,SL,SSL)",
                "moon_chain": "(NL,SL,SSL)",
            },
            "output": {"rp_ranked": "[(planet,score)]", "rp_primary": "top5"},
        }

    def dependencies(self) -> list[str]:
        return ["kp_chain", "ascendant"]


try:
    from interfaces.advisory_adapter_protocol import advisory_registry

    advisory_registry.register(KPRulingPlanetsAdapter())
except Exception:
    pass


def get_ruling_planets_data(
    *,
    timestamp,
    latitude: float,
    longitude: float,
    include_day_lord: bool = True,
    weights: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Convenience function used by API v1 to compute RP data.

    Uses minimal fallback if full RP implementation is not available.
    """
    from datetime import UTC
    from zoneinfo import ZoneInfo

    # Determine weekday (NY time for trading context)
    try:
        wd = timestamp.astimezone(ZoneInfo("America/New_York")).weekday()
    except Exception:
        wd = timestamp.replace(tzinfo=UTC).weekday()

    # Build simple chains from Moon position if full implementation missing
    if _RP_AVAILABLE:
        # Prefer clients to supply asc/moon chains; for simplicity, use Moon chain only
        ctx = {"weekday_idx": wd, "asc_chain": ("MO", "MO", "MO"), "moon_chain": ("MO", "MO", "MO")}
        # Build config from env and override with request weights
        from refactor.kp_ruling_planets import RPConfig as _RPConf
        cfg = _RPConf.from_env()
        if weights:
            cfg = _RPConf.from_mapping({**cfg.__dict__, **weights})
        if not include_day_lord:
            cfg = _RPConf.from_mapping({**cfg.__dict__, "day_lord": 0.0})
        out = ruling_planets(wd, ctx["asc_chain"], ctx["moon_chain"], {}, {}, cfg)
        out.update({"weekday_idx": wd})
        return out
    else:
        order = ["SU", "MO", "MA", "ME", "JU", "VE", "SA", "RA", "KE"]
        ranked = [(p, 10 - i) for i, p in enumerate(order)]
        return {"weekday_idx": wd, "rp_ranked": ranked, "rp_primary": [p for p, _ in ranked[:5]], "adapter": "minimal"}
