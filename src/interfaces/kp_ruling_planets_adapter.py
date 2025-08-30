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


from refactor.kp_ruling_planets import RPConfig, ruling_planets


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
