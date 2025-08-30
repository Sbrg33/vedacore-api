# interfaces/kp_houses_adapter.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from refactor.houses import Houses, HouseSystem, compute_houses

# If you defined a formal Protocol, import it; otherwise this adapter is shape-compatible.
# from interfaces.system_adapter import SystemAdapter

UTC = ZoneInfo("UTC")


class KPHousesAdapter:
    """
    KP Houses adapter exposing snapshot() only (no 'changes' concept for houses).
    system = "KP_HOUSES" to keep it distinct from core KP signals.
    """

    system: str = "KP_HOUSES"
    version: str = "1.0.0"

    def snapshot(
        self,
        ts_utc: datetime,
        *,
        lat: float,
        lon: float,
        house_system: HouseSystem = "PLACIDUS",
        topocentric: bool = False,
    ) -> dict[str, Any]:
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=UTC)
        h: Houses = compute_houses(
            ts_utc, lat, lon, system=house_system, topocentric=topocentric
        )
        return {
            "system": h.system,
            "asc": h.asc,
            "mc": h.mc,
            "cusps": h.cusps,
            "meta": {
                "adapter": self.system,
                "version": self.version,
                "sidereal": "Krishnamurti",
                "topocentric": topocentric,
                "lat": lat,
                "lon": lon,
                "timestamp": ts_utc.isoformat(),
            },
        }

    # Optional; houses are not event-based, so return an empty list or omit.
    def changes(self, day_utc: date, **kwargs) -> list[dict[str, Any]]:
        return []
