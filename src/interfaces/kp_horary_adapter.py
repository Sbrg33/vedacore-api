"""SystemAdapter for KP Horary."""

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


from refactor.kp_horary import HoraryConfig, compute_horary


class KPHoraryAdapter:
    id = "kp_horary"
    version = "0.1.0"

    def compute(self, ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        ts = int(ctx.get("timestamp_unix"))
        mode = str(ctx.get("mode", "unix_mod"))
        tz_off = int(ctx.get("tz_offset_sec", 0))
        sunrise = ctx.get("sunrise_ts")
        sunrise_i = int(sunrise) if sunrise is not None else None

        moon = ctx.get("moon_chain") or {"nl": "MO", "sl": "MO", "ssl": "MO"}

        # Handle both dict and tuple formats for moon_chain
        if isinstance(moon, dict):
            mc = (
                str(moon.get("nl", "MO")),
                str(moon.get("sl", "MO")),
                str(moon.get("ssl", "MO")),
            )
        elif isinstance(moon, (tuple, list)) and len(moon) >= 3:
            mc = (str(moon[0]), str(moon[1]), str(moon[2]))
        else:
            mc = ("MO", "MO", "MO")  # Default fallback

        try:
            cfg = HoraryConfig(mode=mode, tz_offset_sec=tz_off, sunrise_ts=sunrise_i)
            res = compute_horary(ts, cfg, moon_chain_planets=mc)
            return {
                "adapter_id": self.id,
                "adapter_version": self.version,
                "number": res.number,
                "planet_ruler": res.planet_ruler,
                "moon_ruled": res.moon_ruled,
                "horary_boost": res.horary_boost,
                "correlation_id": ctx.get("correlation_id", "unknown"),
            }
        except ValueError as e:
            return {
                "error": str(e),
                "error_type": "validation_error",
                "correlation_id": ctx.get("correlation_id", "unknown"),
            }

    def explain(self, out: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "why": "Horary number maps to a planetary sequence; boost when Moon chain contains the ruler.",
            "inputs": [
                "timestamp_unix",
                "mode",
                "tz_offset_sec",
                "sunrise_ts",
                "moon_chain",
            ],
            "outputs": ["number", "planet_ruler", "moon_ruled", "horary_boost"],
        }

    def schema(self) -> Mapping[str, Any]:
        return {
            "input": {
                "timestamp_unix": "int (UTC seconds)",
                "mode": "unix_mod|daily_mod|sunrise_mod",
                "tz_offset_sec": "int (for daily_mod)",
                "sunrise_ts": "int|None (for sunrise_mod)",
                "moon_chain": "{nl,sl,ssl} planet codes",
            },
            "output": {
                "number": "1..249",
                "planet_ruler": "planet code",
                "moon_ruled": "bool",
                "horary_boost": "float",
            },
        }

    def dependencies(self) -> list[str]:
        return ["kp_chain"]


try:
    from interfaces.advisory_adapter_protocol import advisory_registry

    advisory_registry.register(KPHoraryAdapter())
except Exception:
    pass
