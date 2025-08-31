#!/usr/bin/env python3
"""
Minimal facade provider used by ATS adapter.

Bridges to refactor.facade to fetch planetary data while applying the
307s finance offset logic consistent with the rest of the API.
"""

from __future__ import annotations

from datetime import UTC, datetime

from refactor.facade import get_positions

# Mapping between ATS planet symbols and VedaCore numeric IDs
ATS_TO_ID = {
    "SUN": 1,
    "MOO": 2,
    "JUP": 3,
    "RAH": 4,
    "MER": 5,
    "VEN": 6,
    "KET": 7,
    "SAT": 8,
    "MAR": 9,
}

ID_TO_ATS = {v: k for k, v in ATS_TO_ID.items()}


class VedaCoreFacadeProvider:
    """Fetches ephemeris-derived values for ATS scoring.

    Methods return ATS-style planet keys (e.g., "SUN", "MOO").
    """

    def __init__(self, apply_finance_offset: bool = True) -> None:
        self.apply_finance_offset = apply_finance_offset

    def _ensure_utc(self, ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)

    def get_transit_longs(self, ts: datetime) -> dict[str, float]:
        ts = self._ensure_utc(ts)
        longs: dict[str, float] = {}
        for sym, pid in ATS_TO_ID.items():
            pdata = get_positions(ts, planet_id=pid, apply_kp_offset=self.apply_finance_offset)
            longs[sym] = float(pdata.longitude)
        return longs

    def get_dignities(self, ts: datetime) -> dict[str, str]:
        """Return simple dignity labels per planet.

        Minimal implementation: all 'NEU' (neutral). Replace with
        real dignity evaluation if desired.
        """
        ts = self._ensure_utc(ts)
        return {sym: "NEU" for sym in ATS_TO_ID.keys()}

    def get_conditions(self, ts: datetime) -> dict[str, dict]:
        """Return planet conditions used by ATS core.

        Provides retrograde/stationary flags; combustion/cazimi default false.
        """
        ts = self._ensure_utc(ts)
        conds: dict[str, dict] = {}
        for sym, pid in ATS_TO_ID.items():
            pdata = get_positions(ts, planet_id=pid, apply_kp_offset=self.apply_finance_offset)
            speed = float(pdata.speed)
            conds[sym] = {
                "is_retro": speed < 0,
                "is_station": abs(speed) < 1e-3,
                "is_combust": False,
                "is_cazimi": False,
            }
        return conds

    def get_moon_chain(self, ts: datetime) -> tuple[str, str, str]:
        ts = self._ensure_utc(ts)
        pdata = get_positions(ts, planet_id=2, apply_kp_offset=self.apply_finance_offset)
        # NL/SL/SL2 are numeric IDs; convert to ATS symbols
        nl = ID_TO_ATS.get(pdata.nl, "SUN")
        sl = ID_TO_ATS.get(pdata.sl, "MOO")
        sl2 = ID_TO_ATS.get(pdata.sl2, "MER")
        return nl, sl, sl2

    def get_planet_chains(self, ts: datetime) -> dict[str, tuple[str, str, str]]:
        """Optional convenience for full planet chains.

        Returns mapping { 'SUN': ('...', '...', '...'), ... }
        """
        ts = self._ensure_utc(ts)
        chains: dict[str, tuple[str, str, str]] = {}
        for sym, pid in ATS_TO_ID.items():
            pdata = get_positions(ts, planet_id=pid, apply_kp_offset=self.apply_finance_offset)
            chains[sym] = (
                ID_TO_ATS.get(pdata.nl, "SUN"),
                ID_TO_ATS.get(pdata.sl, "MOO"),
                ID_TO_ATS.get(pdata.sl2, "MER"),
            )
        return chains
