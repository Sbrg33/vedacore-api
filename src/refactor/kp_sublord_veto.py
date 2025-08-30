"""Sub-Lord Veto system — multiplicative factor for positive indications."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VetoConfig:
    combust_deg: float = 6.0
    retro_penalty: float = 0.20
    debil_penalty: float = 0.25
    stationary_speed: float = 0.02  # deg/day
    stationary_penalty: float = 0.30
    cap: float = 0.70  # max total dampening


def veto_factor(
    planet: str,
    angular_to_sun_deg: float,
    retrograde: bool,
    is_debil: bool,
    is_exalt: bool,
    speed_deg_per_day: float,
    is_node: bool = False,
    node_dispositor_flags: dict[str, bool] | None = None,
    cfg: VetoConfig = VetoConfig(),
) -> float:
    penalty = 0.0
    if angular_to_sun_deg < cfg.combust_deg and not is_exalt:
        penalty += 0.25
    if is_debil and not is_exalt:
        penalty += cfg.debil_penalty
    if retrograde:
        penalty += cfg.retro_penalty
    if abs(speed_deg_per_day) <= cfg.stationary_speed:
        penalty += cfg.stationary_penalty
    if is_node and node_dispositor_flags:
        if node_dispositor_flags.get("debil"):
            penalty += 0.10
        if node_dispositor_flags.get("retrograde"):
            penalty += 0.05
        if node_dispositor_flags.get("stationary"):
            penalty += 0.10
    if is_exalt:
        penalty *= 0.6
    penalty = min(penalty, cfg.cap)
    return max(0.3, 1.0 - penalty)
