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
import os

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


def _aspect_config_from_env() -> List[Tuple[float, float, float]]:
    def _f(name: str, default: float) -> float:
        v = os.getenv(name)
        try:
            return float(v) if v is not None else default
        except Exception:
            return default

    return [
        (0.0, _f("ATS_ORB_CONJ", 8.0), _f("ATS_W_CONJ", 1.0)),
        (180.0, _f("ATS_ORB_OPP", 7.0), _f("ATS_W_OPP", 0.8)),
        (120.0, _f("ATS_ORB_TRI", 6.0), _f("ATS_W_TRI", 0.7)),
        (90.0, _f("ATS_ORB_SQR", 6.0), _f("ATS_W_SQR", 0.6)),
        (60.0, _f("ATS_ORB_SEX", 4.0), _f("ATS_W_SEX", 0.5)),
    ]


def _aspect_config_from_ctx(ctx: Dict[str, Any] | None) -> List[Tuple[float, float, float]]:
    if not ctx:
        return []
    aspects = ctx.get("aspects") or {}
    if not isinstance(aspects, dict):
        return []
    def _entry(key: str, angle: float, default_orb: float, default_w: float) -> Tuple[float, float, float]:
        cfg = aspects.get(key) or {}
        orb = cfg.get("orb", default_orb)
        w = cfg.get("weight", default_w)
        try:
            return angle, float(orb), float(w)
        except Exception:
            return angle, default_orb, default_w
    return [
        _entry("conj", 0.0, 8.0, 1.0),
        _entry("opp", 180.0, 7.0, 0.8),
        _entry("tri", 120.0, 6.0, 0.7),
        _entry("sqr", 90.0, 6.0, 0.6),
        _entry("sex", 60.0, 4.0, 0.5),
    ]


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
    aspects = _aspect_config_from_ctx(ctx) or _aspect_config_from_env() or [
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


def _kp_emphasis_from_env() -> Tuple[float, float, float]:
    def _f(name: str, default: float) -> float:
        v = os.getenv(name)
        try:
            return float(v) if v is not None else default
        except Exception:
            return default
    return (
        _f("ATS_KP_NL", 1.0),
        _f("ATS_KP_SL", 1.0),
        _f("ATS_KP_SSL", 1.0),
    )


def _kp_emphasis_from_ctx(ctx: Dict[str, Any] | None) -> Tuple[float, float, float]:
    if not ctx:
        return (1.0, 1.0, 1.0)
    ke = ctx.get("kp_emphasis") or {}
    def _g(k: str, d: float) -> float:
        try:
            return float(ke.get(k, d))
        except Exception:
            return d
    return (_g("nl", 1.0), _g("sl", 1.0), _g("ssl", 1.0))


def score_targets(
    targets: Iterable[str],
    planets: Iterable[str],
    edges: List[Tuple[str, str, float]],
    *,
    ctx: Dict[str, Any],
    kp: KPState | None = None,
) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]], List[dict]]:
    """Score target planets based on edges.

    Returns (totals, by_source, pathlog). Edges are aggregated by destination.
    """
    tset = [t for t in targets]
    totals: Dict[str, float] = {t: 0.0 for t in tset}
    by_source: Dict[str, Dict[str, float]] = {t: {} for t in tset}
    pathlog: List[dict] = []

    # KP emphasis factors
    kp_nl_w, kp_sl_w, kp_ssl_w = _kp_emphasis_from_ctx(ctx)
    env_nl_w, env_sl_w, env_ssl_w = _kp_emphasis_from_env()
    kp_nl_w = kp_nl_w if kp_nl_w is not None else 1.0
    kp_sl_w = kp_sl_w if kp_sl_w is not None else 1.0
    kp_ssl_w = kp_ssl_w if kp_ssl_w is not None else 1.0
    # Env overrides multiply
    kp_nl_w *= env_nl_w
    kp_sl_w *= env_sl_w
    kp_ssl_w *= env_ssl_w

    nl = getattr(kp, "moon_nl", None) if kp else None
    sl = getattr(kp, "moon_sl", None) if kp else None
    ssl = getattr(kp, "moon_ssl", None) if kp else None

    for src, dst, w in edges or []:
        if dst not in totals:
            continue
        mult = 1.0
        if kp:
            if dst == nl:
                mult *= kp_nl_w
            elif dst == sl:
                mult *= kp_sl_w
            elif dst == ssl:
                mult *= kp_ssl_w
        val = float(w) * mult
        totals[dst] += val
        by_source[dst][src] = by_source[dst].get(src, 0.0) + val
        # Keep a small pathlog for explainability
        if len(pathlog) < 200:
            pathlog.append({"from": src, "to": dst, "weight": round(val, 4)})
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
