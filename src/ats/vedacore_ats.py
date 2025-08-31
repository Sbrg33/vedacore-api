#!/usr/bin/env python3
"""
Lightweight ATS core implementation.

Computes directed edges between transiting planets based on aspect exactness
and aggregates them into per-target scores. Includes simple condition factors
and optional KP moon-chain emphasis via the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple
import math

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


def _ang_sep(a: float, b: float) -> float:
    d = abs(float(a) - float(b)) % 360.0
    return d if d <= 180.0 else 360.0 - d


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

    Aspects used: conj(0,8), opp(180,7), tri(120,6), sqr(90,6), sex(60,4)
    Weight = base * closeness * condition_factor
    - base: conj=1.0, opp=0.8, tri=0.7, sqr=0.6, sex=0.5
    - closeness: 1 - (delta/orb)
    - condition_factor: 0.9 if source retrograde; 1.0 otherwise
    """
    if not longs:
        return []
    planets = list(planets)
    edges: List[Tuple[str, str, float]] = []
    aspects = [
        (0.0, 8.0, 1.0),
        (180.0, 7.0, 0.8),
        (120.0, 6.0, 0.7),
        (90.0, 6.0, 0.6),
        (60.0, 4.0, 0.5),
    ]

    for i, p_from in enumerate(planets):
        lon_from = longs.get(p_from)
        if lon_from is None:
            continue
        cond = conds.get(p_from, {}) or {}
        cond_factor = 0.9 if cond.get("is_retro") else 1.0
        for p_to in planets:
            if p_to == p_from:
                continue
            lon_to = longs.get(p_to)
            if lon_to is None:
                continue
            sep = _ang_sep(lon_from, lon_to)
            w = 0.0
            for angle, orb, base in aspects:
                delta = abs(sep - angle)
                if delta <= orb:
                    closeness = 1.0 - (delta / orb)
                    w = max(w, base * closeness * cond_factor)
            if w > 0.0:
                edges.append((p_from, p_to, w))
    return edges


def score_targets(
    targets: Iterable[str],
    planets: Iterable[str],
    edges: List[Tuple[str, str, float]],
    *,
    ctx: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]], List[dict]]:
    """Score target planets based on edges.

    Returns (totals, by_source, pathlog). Edges are aggregated by destination.
    """
    tset = [t for t in targets]
    totals: Dict[str, float] = {t: 0.0 for t in tset}
    by_source: Dict[str, Dict[str, float]] = {t: {} for t in tset}
    pathlog: List[dict] = []

    for src, dst, w in edges or []:
        if dst not in totals:
            continue
        totals[dst] += float(w)
        by_source[dst][src] = by_source[dst].get(src, 0.0) + float(w)
        # Keep a small pathlog for explainability
        if len(pathlog) < 200:
            pathlog.append({"from": src, "to": dst, "weight": round(float(w), 4)})
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
