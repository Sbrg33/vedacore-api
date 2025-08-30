#!/usr/bin/env python3
"""
Transit Events API Router
Endpoints for transit event detection and analysis
"""

import logging

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config.feature_flags import FeatureFlags, require_feature
from modules.transits.ruling_planets import calculate_ruling_planets
from refactor.facade import get_positions, get_sky_map
from refactor.transit_aspects import find_transit_aspects
from refactor.transit_event_detector import TransitEventDetector
from refactor.transit_gate_system import KPGateCalculator, compute_dispositor_map
from refactor.transit_moon_engine import get_moon_engine
from refactor.transit_promise_checker import TransitPromiseChecker
from refactor.transit_resonance import get_resonance_kernel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/transit-events", tags=["Transit Events"])


# Request/Response Models
class DetectEventsRequest(BaseModel):
    """Request for event detection"""

    ts: datetime = Field(..., description="UTC timestamp for detection")
    return_mode: str = Field(
        "topN", description="Return mode: 'topN', 'all', 'threshold'"
    )
    n: int = Field(10, description="Number of events to return (for topN mode)")
    threshold: int = Field(60, description="Score threshold (for threshold mode)")
    include_aspects: bool = Field(True, description="Include aspect calculations")
    include_dasha: bool = Field(True, description="Include dasha alignment")
    include_promise: bool = Field(True, description="Include promise checking")
    include_rp: bool = Field(True, description="Include ruling planets")
    birth_time: datetime | None = Field(None, description="Birth time for dasha")
    moon_longitude: float | None = Field(None, description="Birth moon longitude")
    latitude: float | None = Field(None, description="Location latitude for RP")
    longitude: float | None = Field(None, description="Location longitude for RP")


class MoonTriggersRequest(BaseModel):
    """Request for Moon triggers on specific planets"""

    ts: datetime = Field(..., description="UTC timestamp")
    planets: list[int] = Field(..., description="Planet IDs to check (1-9)")
    include_weak: bool = Field(False, description="Include weak gates (<0.3)")


class GatesRequest(BaseModel):
    """Request for gate calculations"""

    ts: datetime = Field(..., description="UTC timestamp")
    show_all: bool = Field(False, description="Show all planets including zero gates")


class PromiseCheckRequest(BaseModel):
    """Request for promise checking"""

    natal_data: dict | None = Field(None, description="Birth chart data")
    themes: list[str] = Field(["FINANCE", "GAINS"], description="Themes to check")
    planet_id: int | None = Field(None, description="Specific planet to check")


class EventResponse(BaseModel):
    """Transit event response"""

    events: list[dict] = Field(..., description="List of detected events")
    metrics: dict = Field(..., description="Performance metrics")
    moon_chain: dict | None = Field(None, description="Current Moon KP chain")


# Singleton instances
_event_detector: TransitEventDetector | None = None


def get_event_detector() -> TransitEventDetector:
    """Get or create event detector singleton"""
    global _event_detector
    if _event_detector is None:
        _event_detector = TransitEventDetector()
    return _event_detector


@router.post("/detect", response_model=EventResponse)
@require_feature(FeatureFlags.ENABLE_TRANSIT_EVENTS)
async def detect_events(request: DetectEventsRequest) -> EventResponse:
    """
    Detect transit events at given timestamp.

    Main endpoint for transit event detection using the
    Moon-centric KP chain triggering system.
    """
    try:
        start_time = datetime.now()

        # Get detector
        detector = get_event_detector()

        # Get current sky data
        sky_data = get_sky_map(
            request.ts, request.latitude or 0.0, request.longitude or 0.0
        )

        # Extract planet positions
        planet_positions = {}
        for planet_data in sky_data.planets:
            planet_positions[planet_data["id"]] = {
                "longitude": planet_data["longitude"],
                "speed": planet_data["speed"],
                "sign": planet_data["sign"],
                "nakshatra": planet_data.get("nakshatra"),
                "house": planet_data.get("house"),
            }

        # Calculate aspects if requested
        aspects = None
        if request.include_aspects:
            aspects = find_transit_aspects(
                sky_data.planets, min_strength=30.0  # Include weak aspects
            )

        # Get dasha data if requested
        dasha_data = None
        if request.include_dasha and request.birth_time and request.moon_longitude:
            # Simplified - would call dasha engine
            dasha_data = {"active": "VENUS", "sub": "MERCURY"}  # Example

        # Get ruling planets if requested
        rp_data = None
        if request.include_rp and request.latitude and request.longitude:
            # Get sky map for ascendant and moon position
            sky = get_sky_map(request.ts, request.latitude, request.longitude)
            ctx = {
                "timestamp": request.ts,
                "ascendant": sky.get("ascendant", 0.0),
                "moon_longitude": sky.get("planets", {})
                .get(2, {})
                .get("longitude", 0.0),
            }
            rp_result = calculate_ruling_planets(ctx)
            rp_data = rp_result.get("ruling_planets") if rp_result else None

        # Get promise data (simplified for now)
        promise_data = None
        if request.include_promise:
            promise_data = {
                "FINANCE": [2, 3, 6],  # Moon, Jupiter, Venus
                "GAINS": [3, 6, 11],
            }

        # Detect events
        events = detector.detect_events(
            request.ts, planet_positions, aspects, dasha_data, rp_data, promise_data
        )

        # Filter based on return mode
        if request.return_mode == "topN":
            # Sort by score and return top N
            events.sort(key=lambda e: e.score, reverse=True)
            events = events[: request.n]
        elif request.return_mode == "threshold":
            # Filter by threshold
            events = [e for e in events if e.score >= request.threshold]
        # else return all

        # Get Moon chain for reference
        moon_engine = get_moon_engine()
        moon_chain = moon_engine.get_moon_chain(request.ts)

        # Calculate metrics
        calc_time = (datetime.now() - start_time).total_seconds() * 1000

        return EventResponse(
            events=[e.to_dict() for e in events],
            metrics={
                "calc_ms": round(calc_time, 2),
                "n_candidates": len(planet_positions) - 1,  # Exclude Moon
                "n_events": len(events),
                "cache_stats": moon_engine.get_cache_stats(),
            },
            moon_chain=moon_chain.to_dict(),
        )

    except Exception as e:
        logger.error(f"Error detecting events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/moon-triggers", response_model=EventResponse)
@require_feature(FeatureFlags.ENABLE_TRANSIT_EVENTS)
async def get_moon_triggers(request: MoonTriggersRequest) -> EventResponse:
    """
    Get Moon triggers for specific planets.

    Check how Moon's current KP chain triggers specific planets
    through gates and resonances.
    """
    try:
        # Get Moon engine and current chain
        moon_engine = get_moon_engine()
        moon_chain = moon_engine.get_moon_chain(request.ts)
        moon_chain_dict = moon_chain.get_chain_dict()

        # Get planet positions for requested planets
        planet_positions = {}
        for planet_id in request.planets:
            pdata = get_positions(request.ts, planet_id)
            planet_positions[planet_id] = {
                "longitude": pdata.position,
                "speed": pdata.speed,
                "sign": pdata.sign,
            }

        # Calculate dispositor map
        dispositor_map = compute_dispositor_map(planet_positions)

        # Calculate gates
        gate_calc = KPGateCalculator()
        events = []

        for planet_id in request.planets:
            gate_score, gate_components = gate_calc.calculate_gate(
                moon_chain_dict, planet_id, dispositor_map
            )

            # Skip weak gates unless requested
            if not request.include_weak and gate_score < 0.3:
                continue

            # Calculate resonance
            kernel = get_resonance_kernel()
            resonance = kernel.calculate_kernel(
                moon_chain.longitude,
                planet_positions[planet_id]["longitude"],
                moon_chain.speed,
                planet_positions[planet_id]["speed"],
            )

            # Create simplified event
            event = {
                "target": planet_id,
                "gate_score": round(gate_score, 3),
                "gate_components": gate_components.to_dict(),
                "resonance": (
                    resonance.to_dict() if resonance.kernel_value > 0 else None
                ),
                "moon_chain": moon_chain.get_signature(),
            }

            events.append(event)

        return EventResponse(
            events=events,
            metrics={
                "n_planets_checked": len(request.planets),
                "n_triggers": len(events),
            },
            moon_chain=moon_chain.to_dict(),
        )

    except Exception as e:
        logger.error(f"Error getting moon triggers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gates")
@require_feature(FeatureFlags.ENABLE_MOON_GATES)
async def get_gates(
    ts: datetime = Query(..., description="UTC timestamp"),
    show_all: bool = Query(False, description="Show all planets"),
) -> dict:
    """
    Get current gate values for all planets.

    Returns the Moon→Planet connectivity strength for inspection.
    """
    try:
        # Get Moon chain
        moon_engine = get_moon_engine()
        moon_chain = moon_engine.get_moon_chain(ts)
        moon_chain_dict = moon_chain.get_chain_dict()

        # Get all planet positions
        sky_data = get_sky_map(ts, 0, 0)
        planet_positions = {}
        for pdata in sky_data.planets:
            planet_positions[pdata["id"]] = {
                "longitude": pdata["longitude"],
                "speed": pdata["speed"],
                "sign": pdata["sign"],
            }

        # Calculate dispositor map
        dispositor_map = compute_dispositor_map(planet_positions)

        # Calculate all gates
        gate_calc = KPGateCalculator()
        all_gates = gate_calc.calculate_all_gates(
            moon_chain_dict, planet_positions, dispositor_map
        )

        # Format results
        gates_list = []
        for planet_id, (score, components) in all_gates.items():
            if show_all or score > 0:
                gates_list.append(
                    {
                        "planet_id": planet_id,
                        "planet_name": sky_data.planets[planet_id - 1]["name"],
                        "gate_score": round(score, 3),
                        "components": components.to_dict(),
                        "explanation": gate_calc.explain_gate(components, planet_id),
                    }
                )

        # Sort by gate score
        gates_list.sort(key=lambda x: x["gate_score"], reverse=True)

        return {
            "timestamp": ts.isoformat(),
            "moon_chain": moon_chain.to_dict(),
            "gates": gates_list,
            "strongest": gates_list[0] if gates_list else None,
        }

    except Exception as e:
        logger.error(f"Error getting gates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/promise-check")
@require_feature(FeatureFlags.ENABLE_PROMISE_CHECK)
async def check_promise(request: PromiseCheckRequest) -> dict:
    """
    Check birth chart promise for themes.

    Validates whether planets promise specific themes based on
    their natal positions and significator relationships.
    """
    try:
        checker = TransitPromiseChecker(request.natal_data)

        results = []
        for theme in request.themes:
            if request.planet_id:
                # Check specific planet
                result = checker.check_promise(theme, request.planet_id)
            else:
                # Check all planets
                result = checker.check_promise(theme)

            results.append(
                {
                    "theme": theme,
                    "result": result.to_dict(),
                    "explanation": checker.explain_promise(result),
                }
            )

        # If specific planet, also get all themes
        all_themes = []
        if request.planet_id:
            all_themes = checker.get_all_themes_for_planet(request.planet_id)

        return {
            "promise_results": results,
            "planet_themes": all_themes if request.planet_id else None,
        }

    except Exception as e:
        logger.error(f"Error checking promise: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_config() -> dict:
    """Get current transit event configuration and feature flags."""
    return {
        "features": {
            "transit_events": FeatureFlags.ENABLE_TRANSIT_EVENTS,
            "moon_gates": FeatureFlags.ENABLE_MOON_GATES,
            "resonance_kernels": FeatureFlags.ENABLE_RESONANCE_KERNELS,
            "dispositor_bridges": FeatureFlags.ENABLE_DISPOSITOR_BRIDGES,
            "promise_check": FeatureFlags.ENABLE_PROMISE_CHECK,
            "dasha_sync": FeatureFlags.ENABLE_DASHA_SYNC,
            "rp_confirm": FeatureFlags.ENABLE_RP_CONFIRM,
        },
        "thresholds": {
            "fire_threshold": 60,
            "up_threshold": 75,
            "cooldown_minutes": 10,
        },
        "weights": {"gate": 0.55, "kernel": 0.25, "confirm": 0.20},
    }


@router.get("/health")
async def health_check() -> dict:
    """Health check for transit event system."""
    try:
        # Test basic functionality
        moon_engine = get_moon_engine()
        current_chain = moon_engine.get_moon_chain(datetime.now(UTC))

        return {
            "status": "healthy",
            "moon_chain": current_chain.get_signature(),
            "cache_stats": moon_engine.get_cache_stats(),
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
