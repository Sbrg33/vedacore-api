#!/usr/bin/env python3
"""
KP Gate System - Moon to Planet Connectivity
Calculates connection strength between Moon's KP chain and target planets
"""

import logging

from dataclasses import dataclass

from .constants import PLANET_NAMES

logger = logging.getLogger(__name__)


@dataclass
class GateComponents:
    """Breakdown of gate score components"""

    nl: float = 0.0  # Nakshatra Lord match
    sl: float = 0.0  # Sub Lord match
    ssl: float = 0.0  # Sub-Sub Lord match
    s3: float = 0.0  # S3 match (if enabled)
    bridge: float = 0.0  # Dispositor bridge bonus
    total: float = 0.0  # Total capped score

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "NL": round(self.nl, 3),
            "SL": round(self.sl, 3),
            "SSL": round(self.ssl, 3),
            "S3": round(self.s3, 3),
            "bridge": round(self.bridge, 3),
            "total": round(self.total, 3),
        }


class KPGateCalculator:
    """
    Calculate Moon→Planet connectivity strength based on KP chain matching.
    Gate values determine the "plug level" or connection strength.
    """

    # Default weights for each KP level
    DEFAULT_WEIGHTS = {
        "NL": 1.00,  # Nakshatra Lord - strongest
        "SL": 0.60,  # Sub Lord - strong
        "SSL": 0.35,  # Sub-Sub Lord - moderate
        "S3": 0.20,  # S3 - weak (optional)
    }

    # Configuration constants
    MAX_GATE = 1.20  # Maximum gate score cap
    BRIDGE_BONUS = 0.30  # Dispositor bridge bonus
    RETRO_BRIDGE_PENALTY = 0.50  # Reduce bridge by 50% for retro planets

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        max_gate: float = MAX_GATE,
        bridge_bonus: float = BRIDGE_BONUS,
    ):
        """
        Initialize gate calculator.

        Args:
            weights: Custom weights for KP levels (optional)
            max_gate: Maximum gate score cap
            bridge_bonus: Bonus for dispositor bridge
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.max_gate = max_gate
        self.bridge_bonus = bridge_bonus

        logger.info(
            f"KPGateCalculator initialized: max_gate={max_gate}, "
            f"bridge_bonus={bridge_bonus}"
        )

    def calculate_gate(
        self,
        moon_chain: dict[str, int],
        target_planet: int,
        dispositor_map: dict[int, int] | None = None,
        planet_speeds: dict[int, float] | None = None,
        aspect_applying: bool = False,
    ) -> tuple[float, GateComponents]:
        """
        Calculate gate value for Moon→Planet connection.

        Args:
            moon_chain: Moon's KP chain {'NL': id, 'SL': id, 'SSL': id, 'S3': id}
            target_planet: Target planet ID (1-9)
            dispositor_map: Optional map of planet_id -> dispositor_id
            planet_speeds: Optional map of planet_id -> speed (for retro check)
            aspect_applying: Whether aspect to target is applying (for bridge adjustment)

        Returns:
            Tuple of (gate_score, components)
        """
        components = GateComponents()

        # Check NL match
        if moon_chain.get("NL") == target_planet:
            components.nl = self.weights.get("NL", 1.00)

        # Check SL match
        if moon_chain.get("SL") == target_planet:
            components.sl = self.weights.get("SL", 0.60)

        # Check SSL match
        if moon_chain.get("SSL") == target_planet:
            components.ssl = self.weights.get("SSL", 0.35)

        # Check S3 match (if present)
        if "S3" in moon_chain and moon_chain["S3"] == target_planet:
            components.s3 = self.weights.get("S3", 0.20)

        # Check if there's at least one direct KP match
        has_direct_match = (
            components.nl > 0
            or components.sl > 0
            or components.ssl > 0
            or components.s3 > 0
        )

        # Calculate dispositor bridge ONLY if there's a direct match
        if dispositor_map and has_direct_match:
            bridge = self._calculate_bridge(
                moon_chain,
                target_planet,
                dispositor_map,
                planet_speeds,
                aspect_applying,
            )
            components.bridge = bridge
        elif dispositor_map:
            # Log that bridge was skipped due to no direct match
            logger.debug(
                f"Bridge skipped for planet {target_planet} - no direct KP match"
            )

        # Sum components
        raw_total = (
            components.nl
            + components.sl
            + components.ssl
            + components.s3
            + components.bridge
        )

        # Apply cap to total only, keep components raw
        components.total = min(self.max_gate, raw_total)

        return components.total, components

    def calculate_all_gates(
        self,
        moon_chain: dict[str, int],
        planet_positions: dict[int, dict],
        dispositor_map: dict[int, int] | None = None,
        exclude_moon: bool = True,
    ) -> dict[int, tuple[float, GateComponents]]:
        """
        Calculate gates for all planets.

        Args:
            moon_chain: Moon's KP chain
            planet_positions: Dict with planet data including speeds
            dispositor_map: Optional dispositor mappings
            exclude_moon: Whether to exclude Moon itself

        Returns:
            Dict of planet_id -> (gate_score, components)
        """
        results = {}

        # Extract speeds for retro check
        planet_speeds = {
            pid: pdata.get("speed", 0.0) for pid, pdata in planet_positions.items()
        }

        for planet_id in range(1, 10):  # Sun(1) through Ketu(9)
            if exclude_moon and planet_id == 2:  # Skip Moon
                continue

            gate_score, components = self.calculate_gate(
                moon_chain, planet_id, dispositor_map, planet_speeds
            )

            if gate_score > 0:  # Only include planets with connections
                results[planet_id] = (gate_score, components)

        return results

    def _calculate_bridge(
        self,
        moon_chain: dict[str, int],
        target_planet: int,
        dispositor_map: dict[int, int],
        planet_speeds: dict[int, float] | None = None,
        aspect_applying: bool = False,
    ) -> float:
        """
        Calculate dispositor bridge bonus.

        Bridge exists when:
        1. Moon's NL's dispositor == target planet
        2. Moon's chain depositor intersects with target's chain

        Args:
            moon_chain: Moon's KP chain
            target_planet: Target planet ID
            dispositor_map: Planet to dispositor mapping
            planet_speeds: Planet speeds for retro check
            aspect_applying: Whether aspect is applying

        Returns:
            Bridge bonus value
        """
        bridge = 0.0

        # Check if Moon's NL has a dispositor that matches target
        moon_nl = moon_chain.get("NL")
        if moon_nl and moon_nl in dispositor_map:
            moon_nl_dispositor = dispositor_map[moon_nl]
            if moon_nl_dispositor == target_planet:
                bridge = self.bridge_bonus

        # Alternative: Check if any Moon chain lord's dispositor matches target
        if bridge == 0:
            for level in ["SL", "SSL"]:
                lord = moon_chain.get(level)
                if lord and lord in dispositor_map:
                    if dispositor_map[lord] == target_planet:
                        bridge = self.bridge_bonus * 0.7  # Slightly weaker
                        break

        # Check for dispositor chain intersection (deeper check)
        if bridge == 0:
            bridge = self._check_dispositor_intersection(
                moon_chain, target_planet, dispositor_map
            )

        # Apply retro penalty ONLY if target is retrograde AND separating
        if bridge > 0 and planet_speeds:
            target_speed = planet_speeds.get(target_planet, 0)
            if target_speed < 0:  # Retrograde
                if not aspect_applying:  # Only apply penalty when separating
                    bridge *= 0.5  # Apply 50% penalty when retro and separating
                else:
                    # If applying, reduce penalty by half (25% instead of 50%)
                    bridge *= 0.75

        return bridge

    def _check_dispositor_intersection(
        self,
        moon_chain: dict[str, int],
        target_planet: int,
        dispositor_map: dict[int, int],
    ) -> float:
        """
        Check for deeper dispositor chain intersections.

        Args:
            moon_chain: Moon's KP chain
            target_planet: Target planet ID
            dispositor_map: Planet to dispositor mapping

        Returns:
            Intersection bonus (weaker than direct bridge)
        """
        # Get Moon's dispositor chain (up to 3 levels deep)
        moon_dispositors = set()
        for level in ["NL", "SL", "SSL"]:
            lord = moon_chain.get(level)
            if lord:
                moon_dispositors.add(lord)
                # Add lord's dispositor
                if lord in dispositor_map:
                    moon_dispositors.add(dispositor_map[lord])
                    # Add dispositor's dispositor (2 levels)
                    disp2 = dispositor_map.get(dispositor_map[lord])
                    if disp2:
                        moon_dispositors.add(disp2)

        # Get target's dispositor chain
        target_dispositors = {target_planet}
        if target_planet in dispositor_map:
            target_disp = dispositor_map[target_planet]
            target_dispositors.add(target_disp)
            # Add target dispositor's dispositor
            if target_disp in dispositor_map:
                target_dispositors.add(dispositor_map[target_disp])

        # Check intersection
        intersection = moon_dispositors & target_dispositors
        if intersection:
            # Weaker bonus for indirect connection
            return self.bridge_bonus * 0.5

        return 0.0

    def get_strongest_gates(
        self, gates: dict[int, tuple[float, GateComponents]], top_n: int = 3
    ) -> list[tuple[int, float, GateComponents]]:
        """
        Get the strongest gate connections.

        Args:
            gates: Dict of all gate calculations
            top_n: Number of top gates to return

        Returns:
            List of (planet_id, gate_score, components) sorted by strength
        """
        sorted_gates = sorted(
            [(pid, score, comp) for pid, (score, comp) in gates.items()],
            key=lambda x: x[1],
            reverse=True,
        )

        return sorted_gates[:top_n]

    def explain_gate(self, components: GateComponents, target_planet: int) -> str:
        """
        Generate human-readable explanation of gate components.

        Args:
            components: Gate component breakdown
            target_planet: Target planet ID

        Returns:
            Explanation string
        """
        planet_name = PLANET_NAMES.get(target_planet, str(target_planet))

        parts = []
        if components.nl > 0:
            parts.append(f"NL match ({components.nl:.2f})")
        if components.sl > 0:
            parts.append(f"SL match ({components.sl:.2f})")
        if components.ssl > 0:
            parts.append(f"SSL match ({components.ssl:.2f})")
        if components.s3 > 0:
            parts.append(f"S3 match ({components.s3:.2f})")
        if components.bridge > 0:
            parts.append(f"Dispositor bridge ({components.bridge:.2f})")

        if parts:
            return f"Moon→{planet_name}: {', '.join(parts)} = {components.total:.2f}"
        else:
            return f"Moon→{planet_name}: No connection"


def compute_dispositor_map(planet_positions: dict[int, dict]) -> dict[int, int]:
    """
    Compute dispositor map based on sign rulerships.

    Args:
        planet_positions: Dict with planet signs

    Returns:
        Dict of planet_id -> dispositor_id
    """
    # Sign rulerships (1-12)
    sign_rulers = {
        1: 9,  # Aries -> Mars
        2: 6,  # Taurus -> Venus
        3: 5,  # Gemini -> Mercury
        4: 2,  # Cancer -> Moon
        5: 1,  # Leo -> Sun
        6: 5,  # Virgo -> Mercury
        7: 6,  # Libra -> Venus
        8: 9,  # Scorpio -> Mars (traditional)
        9: 3,  # Sagittarius -> Jupiter
        10: 8,  # Capricorn -> Saturn
        11: 8,  # Aquarius -> Saturn (traditional)
        12: 3,  # Pisces -> Jupiter
    }

    dispositor_map = {}

    for planet_id, pdata in planet_positions.items():
        sign = pdata.get("sign", 0)
        if sign > 0 and sign <= 12:
            ruler = sign_rulers.get(sign)
            if ruler and ruler != planet_id:  # Don't map to self
                dispositor_map[planet_id] = ruler

    return dispositor_map
