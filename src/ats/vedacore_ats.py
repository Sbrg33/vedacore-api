#!/usr/bin/env python3
"""
Minimal ATS core compatibility layer.

Implements the interfaces used by ATSSystemAdapter with neutral scoring.
This unblocks API startup without shipping the full ATS engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

# Canonical ATS planet symbols
PLANETS: Tuple[str, ...] = (
    "SUN",
    "MOON",
    "JUP",
    "RAH",
    "MERC",
    "VEN",
    "KET",
    "SAT",
    "MAR",
)


@dataclass
class KPState:
    """Moon KP chain and optional planet chains (ATS expects this)."""

    moon_nl: str
    moon_sl: str
    moon_ssl: str
    planet_chain: Dict[str, Tuple[str, str, str]] | None = None


def context_from_dict(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Pass-through context factory.

    Full ATS uses a structured context; for our minimal layer, a dict suffices.
    """
    return cfg or {}


def build_edges_transit(
    planets: Iterable[str],
    longs: Dict[str, float],
    dign: Dict[str, str],
    conds: Dict[str, Dict[str, Any]],
    *,
    kp: KPState,
    ctx: Dict[str, Any],
) -> List[Tuple[str, str, float]]:
    """Compute directed edges between planets with weights.

    Minimal implementation returns an empty edge list, meaning no
    transfer influence is applied. This is acceptable for startup
    and health checks; replace with real calculation to enable ATS.
    """
    return []


def score_targets(
    targets: Iterable[str],
    planets: Iterable[str],
    edges: List[Tuple[str, str, float]],
    *,
    ctx: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]], List[dict]]:
    """Score target planets based on edges.

    Returns (totals, by_source, pathlog).
    Minimal implementation assigns 0.0 to all targets with empty logs.
    """
    totals: Dict[str, float] = {t: 0.0 for t in targets}
    by_source: Dict[str, Dict[str, float]] = {t: {} for t in targets}
    pathlog: List[dict] = []
    return totals, by_source, pathlog


def normalize_scores(totals: Dict[str, float], ref: float = 1.5) -> Dict[str, float]:
    """Normalize raw scores to 0-100 scale.

    Minimal implementation maps linearly with guard for zero totals.
    """
    # If all totals are zero, return zeros
    if not totals or all(abs(v) < 1e-12 for v in totals.values()):
        return {k: 0.0 for k in totals}

    max_val = max(1e-9, max(abs(v) for v in totals.values()))
    return {k: max(0.0, min(100.0, (v / max_val) * 100.0)) for k, v in totals.items()}

