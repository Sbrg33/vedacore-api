#!/usr/bin/env python3
"""
KP Ruling Planets (RP) computation

Produces a ranked list of ruling planets based on:
- Day lord (weekday)
- Ascendant KP chain (NL, SL, SSL)
- Moon KP chain (NL, SL, SSL)
- Fortification bonuses (exaltation/own sign)

Reference behavior aligned with common KP practices. Weights are configurable
via RPConfig and normalized to produce intuitive scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple


PlanetCode = str  # "SU","MO","MA","ME","JU","VE","SA","RA","KE"


WEEKDAY_DAY_LORD: Dict[int, PlanetCode] = {
    0: "MO",  # Monday
    1: "MA",  # Tuesday
    2: "ME",  # Wednesday
    3: "JU",  # Thursday
    4: "VE",  # Friday
    5: "SA",  # Saturday
    6: "SU",  # Sunday (Python weekday: 6)
}

ALL_PLANETS: Tuple[PlanetCode, ...] = ("SU", "MO", "MA", "ME", "JU", "VE", "SA", "RA", "KE")


@dataclass
class RPConfig:
    # Base weights
    w_day_lord: float = 3.0

    # Ascendant chain weights
    w_asc_nl: float = 2.5
    w_asc_sl: float = 1.5
    w_asc_ssl: float = 0.5

    # Moon chain weights
    w_moon_nl: float = 2.0
    w_moon_sl: float = 1.0
    w_moon_ssl: float = 0.5

    # Fortification bonuses
    w_exalt: float = 0.75
    w_own: float = 0.5

    # Normalization and output selection
    normalize: bool = True
    top_k_primary: int = 5


def _init_score_map(planets: Iterable[PlanetCode] = ALL_PLANETS) -> Dict[PlanetCode, float]:
    return {p: 0.0 for p in planets}


def _apply_weight(scores: Dict[PlanetCode, float], planet: PlanetCode, w: float) -> None:
    if planet and planet in scores:
        scores[planet] += float(w)


def _normalize(scores: Dict[PlanetCode, float]) -> Dict[PlanetCode, float]:
    max_val = max(scores.values()) if scores else 0.0
    if max_val <= 0.0:
        return {k: 0.0 for k in scores}
    return {k: round((v / max_val) * 100.0, 2) for k, v in scores.items()}


def ruling_planets(
    weekday_idx: int,
    asc_chain: Tuple[PlanetCode, PlanetCode, PlanetCode] | List[PlanetCode],
    moon_chain: Tuple[PlanetCode, PlanetCode, PlanetCode] | List[PlanetCode],
    is_exalted: Mapping[PlanetCode, bool] | None = None,
    is_own: Mapping[PlanetCode, bool] | None = None,
    cfg: RPConfig | None = None,
) -> Dict[str, object]:
    """Compute KP Ruling Planets ranking.

    Args:
        weekday_idx: Monday=0 .. Sunday=6 (Python datetime.weekday())
        asc_chain: (NL, SL, SSL) for ascendant
        moon_chain: (NL, SL, SSL) for Moon
        is_exalted: optional flags per planet
        is_own: optional flags per planet
        cfg: weighting configuration

    Returns:
        Dict with keys:
          - scores: per-planet raw or normalized scores
          - rp_ranked: list[(planet, score)] descending
          - rp_primary: top-K planets (by score)
          - components: breakdown of contributing factors
    """
    cfg = cfg or RPConfig()
    asc_chain = tuple(p.upper() for p in asc_chain[:3])  # type: ignore[index]
    moon_chain = tuple(p.upper() for p in moon_chain[:3])  # type: ignore[index]
    ex = {k.upper(): bool(v) for k, v in (is_exalted or {}).items()}
    own = {k.upper(): bool(v) for k, v in (is_own or {}).items()}

    scores = _init_score_map()
    components: Dict[str, Dict[str, float]] = {p: {} for p in ALL_PLANETS}

    # Day lord
    dl = WEEKDAY_DAY_LORD.get(int(weekday_idx) % 7)
    if dl:
        _apply_weight(scores, dl, cfg.w_day_lord)
        components[dl]["day_lord"] = cfg.w_day_lord

    # Ascendant chain
    if asc_chain:
        labels = ("asc_nl", "asc_sl", "asc_ssl")
        weights = (cfg.w_asc_nl, cfg.w_asc_sl, cfg.w_asc_ssl)
        for p, lab, w in zip(asc_chain, labels, weights):
            _apply_weight(scores, p, w)
            components[p][lab] = components[p].get(lab, 0.0) + w

    # Moon chain
    if moon_chain:
        labels = ("moon_nl", "moon_sl", "moon_ssl")
        weights = (cfg.w_moon_nl, cfg.w_moon_sl, cfg.w_moon_ssl)
        for p, lab, w in zip(moon_chain, labels, weights):
            _apply_weight(scores, p, w)
            components[p][lab] = components[p].get(lab, 0.0) + w

    # Fortifications
    for p in ALL_PLANETS:
        if ex.get(p):
            _apply_weight(scores, p, cfg.w_exalt)
            components[p]["exalt"] = components[p].get("exalt", 0.0) + cfg.w_exalt
        if own.get(p):
            _apply_weight(scores, p, cfg.w_own)
            components[p]["own"] = components[p].get("own", 0.0) + cfg.w_own

    # Normalize and rank
    final_scores = _normalize(scores) if cfg.normalize else {k: round(v, 3) for k, v in scores.items()}
    ranked = sorted(final_scores.items(), key=lambda kv: kv[1], reverse=True)
    primary = [p for p, _ in ranked[: cfg.top_k_primary]]

    return {
        "scores": final_scores,
        "rp_ranked": ranked,
        "rp_primary": primary,
        "components": components,
        "day_lord": dl,
    }
