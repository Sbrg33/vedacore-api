#!/usr/bin/env python3
"""
Transit Event Detector - Main Event Detection and Scoring Logic
Implements the complete transit event detection system with Promise + Dasha + Transit + RP formula
"""

import json
import logging
import time

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .constants import PLANET_NAMES
from .monitoring import (
    confirm_score_summary,
    gate_score_summary,
    kernel_score_summary,
    transit_events_detect_duration,
    transit_events_emitted,
    transit_events_suppressed,
)
from .transit_gate_system import (
    GateComponents,
    KPGateCalculator,
    compute_dispositor_map,
)
from .transit_moon_engine import MoonChainData, MoonTransitEngine
from .transit_resonance import ResonanceKernel, ResonanceResult

logger = logging.getLogger(__name__)


@dataclass
class TransitEvent:
    """Complete transit event with scoring and explanation"""

    id: str  # Deterministic hash for deduplication
    ts: datetime
    trigger: str = "MOON"  # Always Moon for this system
    target: int = 0  # Target planet ID
    target_name: str = ""
    kind: str = "TRANSIT_TO_TRANSIT"

    # Components
    gates: GateComponents = field(default_factory=GateComponents)
    kernel: ResonanceResult | None = None
    promise_score: float = 0.0
    dasha_score: float = 0.0
    rp_score: float = 0.0

    # Final score
    score: int = 0

    # Timing window
    window_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    window_end: datetime | None = None

    # Explanation
    explain: str = ""

    # Additional metadata
    moon_chain_sig: str = ""
    combo_bonus: float = 0.0  # For double/triple transits

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "ts": self.ts.isoformat(),
            "trigger": self.trigger,
            "target": self.target,
            "target_name": self.target_name,
            "kind": self.kind,
            "gates": self.gates.to_dict(),
            "kernel": self.kernel.to_dict() if self.kernel else None,
            "confirm": {
                "promise": round(self.promise_score, 2),
                "dasha": round(self.dasha_score, 2),
                "rp": round(self.rp_score, 2),
            },
            "score": self.score,
            "window": {
                "start": self.window_start.isoformat(),
                "end": self.window_end.isoformat() if self.window_end else None,
            },
            "explain": self.explain,
        }


class TransitEventDetector:
    """
    Main transit event detection engine with scoring and deduplication.
    Implements the KP formula: Event = Promise + Dasha + Transit + RP
    """

    # Default configuration
    FIRE_THRESHOLD = 60  # Minimum score to fire event
    UP_THRESHOLD = 75  # Score increase threshold for re-firing
    COOLDOWN_MINUTES = 10  # Dedup cooldown period

    # Scoring weights
    SCORE_WEIGHTS = {
        "gate": 0.55,  # Gates dominate (Moon chain connection)
        "kernel": 0.25,  # Aspect geometry
        "confirm": 0.20,  # Confirmations (Promise + Dasha + RP)
    }

    # Confirmation sub-weights
    CONFIRM_WEIGHTS = {"promise": 0.50, "dasha": 0.30, "rp": 0.20}

    def __init__(
        self,
        moon_engine: MoonTransitEngine | None = None,
        gate_calculator: KPGateCalculator | None = None,
        resonance_kernel: ResonanceKernel | None = None,
        ledger_path: Path | None = None,
        fire_threshold: int = FIRE_THRESHOLD,
        cooldown_minutes: int = COOLDOWN_MINUTES,
    ):
        """
        Initialize event detector with components.

        Args:
            moon_engine: Moon transit engine (creates if None)
            gate_calculator: Gate calculator (creates if None)
            resonance_kernel: Resonance kernel (creates if None)
            ledger_path: Path for event ledger persistence
            fire_threshold: Minimum score to fire event
            cooldown_minutes: Deduplication cooldown period
        """
        self.moon_engine = moon_engine or MoonTransitEngine()
        self.gate_calculator = gate_calculator or KPGateCalculator()
        self.resonance_kernel = resonance_kernel or ResonanceKernel()

        self.fire_threshold = fire_threshold
        self.cooldown_minutes = cooldown_minutes

        # Event tracking
        self.fired_events: dict[str, datetime] = {}  # event_key -> last_fire_time
        self.event_scores: dict[str, int] = {}  # event_key -> last_score
        self.event_history: list[TransitEvent] = []

        # Ledger for persistence
        self.ledger_path = ledger_path or Path("transit_events.json")
        self._load_ledger()

        logger.info(
            f"TransitEventDetector initialized: threshold={fire_threshold}, "
            f"cooldown={cooldown_minutes}min"
        )

    def detect_events(
        self,
        ts: datetime,
        planet_positions: dict[int, dict],
        aspects: list[dict] | None = None,
        dasha_data: dict | None = None,
        rp_data: dict | None = None,
        promise_data: dict | None = None,
    ) -> list[TransitEvent]:
        """
        Main detection loop - analyze sky and detect transit events.

        Args:
            ts: UTC timestamp for detection
            planet_positions: Current planetary positions
            aspects: Optional pre-calculated aspects
            dasha_data: Current dasha periods
            rp_data: Current ruling planets
            promise_data: Birth chart promise tags

        Returns:
            List of detected transit events
        """
        # Start timing for metrics
        start_time = time.perf_counter()
        events = []
        suppressed_count = {"dedup": 0, "low_score": 0, "session_filter": 0}

        # Get Moon's KP chain
        moon_chain = self.moon_engine.get_moon_chain(ts)
        moon_chain_dict = moon_chain.get_chain_dict()
        moon_signature = moon_chain.get_signature()

        # Get Moon position for aspects
        moon_lon = moon_chain.longitude
        moon_speed = moon_chain.speed

        # Calculate dispositor map
        dispositor_map = compute_dispositor_map(planet_positions)

        # Calculate gates for all planets
        all_gates = self.gate_calculator.calculate_all_gates(
            moon_chain_dict, planet_positions, dispositor_map, exclude_moon=True
        )

        # Calculate resonances (aspects) if not provided
        if aspects is None:
            resonances = self.resonance_kernel.calculate_multi_resonance(
                moon_lon, moon_speed, planet_positions
            )
        else:
            resonances = self._process_aspect_list(aspects, moon_lon, moon_speed)

        # Process each planet with a gate connection
        for planet_id, (gate_score, gate_components) in all_gates.items():
            if gate_score < 0.1:  # Skip very weak gates
                continue

            # Get resonance for this planet
            resonance = resonances.get(planet_id)
            kernel_value = resonance.kernel_value if resonance else 0.0

            # Calculate confirmation scores
            promise_score = self._calculate_promise_score(planet_id, promise_data)
            dasha_score = self._calculate_dasha_score(
                planet_id, dasha_data, dispositor_map
            )
            rp_score = self._calculate_rp_score(
                moon_chain_dict, planet_id, rp_data, dispositor_map
            )

            # Calculate final score
            score = self._calculate_final_score(
                gate_score, kernel_value, promise_score, dasha_score, rp_score
            )

            # Observe component scores for metrics
            gate_score_summary.observe(gate_score)
            kernel_score_summary.observe(kernel_value)
            confirm_score_summary.observe((promise_score + dasha_score + rp_score) / 3)

            # Check if should fire
            event_key = self._generate_event_key(
                moon_signature,
                planet_id,
                resonance.aspect_type.name if resonance else "NONE",
                ts,
            )

            if self._should_fire_event(event_key, score):
                # Create event
                event = TransitEvent(
                    id=event_key,
                    ts=ts,
                    target=planet_id,
                    target_name=PLANET_NAMES.get(planet_id, str(planet_id)),
                    gates=gate_components,
                    kernel=resonance,
                    promise_score=promise_score,
                    dasha_score=dasha_score,
                    rp_score=rp_score,
                    score=score,
                    window_start=ts,
                    moon_chain_sig=moon_signature,
                )

                # Generate explanation
                event.explain = self._generate_explanation(event, moon_chain)

                events.append(event)

                # Update tracking
                self.fired_events[event_key] = ts
                self.event_scores[event_key] = score

        # Check for double/triple transits and add combo bonus
        events = self._apply_combo_bonus(events)

        # Save to history
        self.event_history.extend(events)
        if len(self.event_history) > 1000:
            self.event_history = self.event_history[-1000:]

        # Persist ledger
        if events:
            self._save_ledger()

        # Record detection duration
        duration = time.perf_counter() - start_time
        transit_events_detect_duration.observe(duration)

        logger.debug(
            f"Detection completed: {len(events)} events in {duration*1000:.2f}ms, "
            f"suppressed: {suppressed_count}"
        )

        return events

    def _calculate_final_score(
        self, gate: float, kernel: float, promise: float, dasha: float, rp: float
    ) -> int:
        """
        Calculate final event score using weighted formula.

        Score = 100 * [0.55*gate + 0.25*kernel + 0.20*(0.5*promise + 0.3*dasha + 0.2*rp)]

        Args:
            gate: Gate score (0-1.2)
            kernel: Resonance kernel (0-1)
            promise: Promise score (0-1)
            dasha: Dasha score (0-1)
            rp: RP score (0-1)

        Returns:
            Final score (0-100)
        """
        # Normalize gate to [0, 1] range
        gate_norm = min(1.0, gate / 1.2)

        # Calculate confirmation composite
        confirm = (
            self.CONFIRM_WEIGHTS["promise"] * promise
            + self.CONFIRM_WEIGHTS["dasha"] * dasha
            + self.CONFIRM_WEIGHTS["rp"] * rp
        )

        # Calculate weighted score
        raw = 100 * (
            self.SCORE_WEIGHTS["gate"] * gate_norm
            + self.SCORE_WEIGHTS["kernel"] * kernel
            + self.SCORE_WEIGHTS["confirm"] * confirm
        )

        # Clamp and round
        return round(min(100, max(0, raw)))

    def _calculate_promise_score(
        self, planet_id: int, promise_data: dict | None
    ) -> float:
        """
        Calculate promise score for planet.

        Args:
            planet_id: Target planet
            promise_data: Birth chart promise tags

        Returns:
            Promise score (0-1)
        """
        if not promise_data:
            return 0.3  # Default neutral score

        # Check if planet is in promised themes
        for theme, planets in promise_data.items():
            if isinstance(planets, list) and planet_id in planets:
                return 1.0  # Direct promise
            elif isinstance(planets, list):
                # Check if planet name matches
                planet_name = PLANET_NAMES.get(planet_id, "")
                if planet_name in planets:
                    return 1.0

        # Check for indirect connections (simplified)
        return 0.6 if planet_id in [3, 6] else 0.3  # Benefics get higher default

    def _calculate_dasha_score(
        self, planet_id: int, dasha_data: dict | None, dispositor_map: dict[int, int]
    ) -> float:
        """
        Calculate dasha alignment score.

        Args:
            planet_id: Target planet
            dasha_data: Current dasha periods
            dispositor_map: Planet dispositor mapping

        Returns:
            Dasha score (0-1)
        """
        if not dasha_data:
            return 0.4  # Default score

        # Get active dasha lord
        active_lord = dasha_data.get("active")
        sub_lord = dasha_data.get("sub")

        # Convert names to IDs if needed
        if isinstance(active_lord, str):
            # Map planet names to IDs (simplified)
            name_to_id = {v: k for k, v in PLANET_NAMES.items()}
            active_lord = name_to_id.get(active_lord.upper())
            sub_lord = name_to_id.get(sub_lord.upper()) if sub_lord else None

        # Check direct match
        if active_lord == planet_id or sub_lord == planet_id:
            return 1.0

        # Check dispositor match
        if planet_id in dispositor_map:
            if dispositor_map[planet_id] in [active_lord, sub_lord]:
                return 0.7

        # Default score
        return 0.4

    def _calculate_rp_score(
        self,
        moon_chain: dict[str, int],
        planet_id: int,
        rp_data: dict | None,
        dispositor_map: dict[int, int],
    ) -> float:
        """
        Calculate Ruling Planets confirmation score.

        Args:
            moon_chain: Moon's KP chain
            planet_id: Target planet
            rp_data: Current ruling planets
            dispositor_map: Planet dispositor mapping

        Returns:
            RP score (0-1)
        """
        if not rp_data:
            return 0.25  # Default minimum

        # Collect all relevant planets
        relevant = set()
        relevant.add(planet_id)
        relevant.update(moon_chain.values())
        if planet_id in dispositor_map:
            relevant.add(dispositor_map[planet_id])

        # Count matches with RP
        rp_planets = set()
        for key in ["asc", "moon", "day", "hour", "asc_star", "moon_star"]:
            if rp_data.get(key):
                rp_planets.add(rp_data[key])

        # Calculate match fraction
        matches = len(relevant & rp_planets)
        if matches == 0:
            return 0.25

        # Map to [0.25, 1.0] range
        fraction = matches / len(rp_planets) if rp_planets else 0
        return 0.25 + (0.75 * fraction)

    def _should_fire_event(
        self,
        event_key: str,
        score: int,
        market: str = "DEFAULT",
        session: str = "REGULAR",
    ) -> bool:
        """
        Determine if event should fire based on score and cooldown.

        Args:
            event_key: Unique event identifier
            score: Current event score
            market: Market type for metrics
            session: Session type for metrics

        Returns:
            True if should fire
        """
        # Check score threshold
        if score < self.fire_threshold:
            transit_events_suppressed.labels(reason="low_score").inc()
            return False

        # Check if recently fired
        if event_key in self.fired_events:
            last_fire = self.fired_events[event_key]
            cooldown_end = last_fire + timedelta(minutes=self.cooldown_minutes)

            if datetime.now(UTC) < cooldown_end:
                # Check for significant score increase
                last_score = self.event_scores.get(event_key, 0)
                if score >= self.UP_THRESHOLD and score > last_score + 10:
                    transit_events_emitted.labels(market=market, session=session).inc()
                    return True  # Re-fire for significant increase
                transit_events_suppressed.labels(reason="dedup").inc()
                return False

        transit_events_emitted.labels(market=market, session=session).inc()
        return True

    def _generate_event_key(
        self, moon_sig: str, planet_id: int, aspect: str, ts: datetime
    ) -> str:
        """
        Generate deterministic event key for deduplication (idempotent).

        Args:
            moon_sig: Moon chain signature
            planet_id: Target planet
            aspect: Aspect type name
            ts: Timestamp

        Returns:
            Idempotent event key
        """
        # Format timestamp to minute precision (idempotent)
        ts_min = ts.strftime("%Y%m%d_%H%M")

        # Extract orb bucket if aspect contains orb info (for future use)
        orb_bucket = 0
        if hasattr(aspect, "orb"):
            orb_bucket = int(aspect.orb * 10)

        # Get current dasha if available (simplified - would come from context)
        dasha_id = "NOD"  # Default no-dasha

        # Create idempotent key (transparent, no hash)
        key_parts = [
            ts_min,
            moon_sig,
            str(planet_id),
            aspect[:3].upper() if aspect != "NONE" else "NON",
            str(orb_bucket),
            dasha_id,
        ]

        return "_".join(key_parts)

    def _generate_explanation(
        self, event: TransitEvent, moon_chain: MoonChainData
    ) -> str:
        """
        Generate human-readable explanation for event.

        Args:
            event: Transit event
            moon_chain: Moon's chain data

        Returns:
            Explanation string
        """
        parts = []

        # Gate explanation
        if event.gates.nl > 0:
            parts.append(f"Moon NL {PLANET_NAMES.get(moon_chain.nl)} matches")
        elif event.gates.sl > 0:
            parts.append(f"Moon SL {PLANET_NAMES.get(moon_chain.sl)} matches")
        elif event.gates.ssl > 0:
            parts.append(f"Moon SSL {PLANET_NAMES.get(moon_chain.ssl)} matches")

        if event.gates.bridge > 0:
            parts.append("dispositor bridge active")

        # Aspect explanation
        if event.kernel:
            aspect_str = f"{event.kernel.aspect_type.name} "
            if event.kernel.is_applying:
                aspect_str += "applying"
            else:
                aspect_str += "separating"
            if event.kernel.is_tight:
                aspect_str += " (tight)"
            parts.append(aspect_str)

        # Confirmations
        confirms = []
        if event.promise_score > 0.7:
            confirms.append("promise confirmed")
        if event.dasha_score > 0.7:
            confirms.append("dasha aligned")
        if event.rp_score > 0.7:
            confirms.append("RP match")

        if confirms:
            parts.append("; ".join(confirms))

        return "; ".join(parts) if parts else "Transit event detected"

    def _apply_combo_bonus(self, events: list[TransitEvent]) -> list[TransitEvent]:
        """
        Apply combo bonus for double/triple transits.

        Args:
            events: List of detected events

        Returns:
            Events with combo bonus applied
        """
        if len(events) < 2:
            return events

        # Group by similar themes (simplified - could use promise data)
        benefic_ids = {3, 6}  # Jupiter, Venus
        malefic_ids = {8, 9}  # Saturn, Mars

        benefic_count = sum(1 for e in events if e.target in benefic_ids)
        malefic_count = sum(1 for e in events if e.target in malefic_ids)

        # Apply bonus for multiple hits in same family
        for event in events:
            original_score = event.score

            if event.target in benefic_ids and benefic_count > 1:
                # Cap combo bonus at 10
                bonus = min(10, 5 * (benefic_count - 1))
                event.combo_bonus = bonus
                # Apply final clamp to 100
                event.score = min(100, event.score + bonus)
                logger.debug(
                    f"Combo bonus for {event.target}: pre={original_score}, "
                    f"bonus={bonus}, post={event.score}"
                )
            elif event.target in malefic_ids and malefic_count > 1:
                bonus = min(10, 5 * (malefic_count - 1))
                event.combo_bonus = bonus
                event.score = min(100, event.score + bonus)
                logger.debug(
                    f"Combo bonus for {event.target}: pre={original_score}, "
                    f"bonus={bonus}, post={event.score}"
                )

        return events

    def _process_aspect_list(
        self, aspects: list[dict], moon_lon: float, moon_speed: float
    ) -> dict:
        """
        Process pre-calculated aspect list into resonance results.

        Args:
            aspects: List of aspect dictionaries
            moon_lon: Moon's longitude
            moon_speed: Moon's speed

        Returns:
            Dict of planet_id -> ResonanceResult
        """
        resonances = {}

        for aspect in aspects:
            # Extract relevant data from aspect dict
            planet1 = aspect.get("p1", aspect.get("planet1"))
            planet2 = aspect.get("p2", aspect.get("planet2"))

            # Check if Moon is involved
            if planet1 == 2:  # Moon is first planet
                target = planet2
            elif planet2 == 2:  # Moon is second planet
                target = planet1
            else:
                continue  # Not a Moon aspect

            # Calculate resonance for this aspect
            result = self.resonance_kernel.calculate_kernel(
                moon_lon,
                aspect.get("longitude", aspect.get("position", 0)),
                moon_speed,
                aspect.get("speed", 0),
            )

            if result.kernel_value > 0:
                resonances[target] = result

        return resonances

    def _load_ledger(self) -> None:
        """Load persisted event ledger"""
        if self.ledger_path.exists():
            try:
                with open(self.ledger_path) as f:
                    data = json.load(f)
                    # Convert ISO strings to datetime
                    for key, iso_str in data.get("fired_events", {}).items():
                        self.fired_events[key] = datetime.fromisoformat(iso_str)
                    self.event_scores = data.get("event_scores", {})
                logger.info(f"Loaded {len(self.fired_events)} events from ledger")
            except Exception as e:
                logger.warning(f"Could not load ledger: {e}")

    def _save_ledger(self) -> None:
        """Save event ledger for persistence"""
        try:
            # Clean old entries
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            self.fired_events = {
                k: v for k, v in self.fired_events.items() if v > cutoff
            }

            data = {
                "fired_events": {
                    k: v.isoformat() for k, v in self.fired_events.items()
                },
                "event_scores": self.event_scores,
                "last_save": datetime.now(UTC).isoformat(),
            }

            with open(self.ledger_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save ledger: {e}")

    def clear_history(self) -> None:
        """Clear event history and caches"""
        self.fired_events.clear()
        self.event_scores.clear()
        self.event_history.clear()
        logger.info("Event history cleared")
