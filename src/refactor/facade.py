#!/usr/bin/env python3
"""
Minimal Facade - Compatibility layer for refactored modules
≤200 lines, no domain logic, just orchestration
"""

import logging

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from app.utils.hash_keys import analysis_id_hash

from .angles_indices import (
    find_nakshatra_pada,
    sign_index,
)
from .change_finder import detect_kp_lord_changes
from .constants import PLANET_NAMES
from .core_types import KPLordChange, PlanetData
from .kp_chain import get_kp_lords_for_planet, warmup_kp_calculations
from .moon_factors import MoonFactorsCalculator, get_moon_factors, get_panchanga
from .numerics import degrees_to_dms
from .swe_backend import (
    get_planet_position_full,
    get_planet_state,
)
from .time_utils import validate_utc_datetime

# Import for type annotations (avoid circular imports)
if TYPE_CHECKING:
    from .kp_analysis import KPAnalysis
    from .kp_context import KPContext

# Initialize module logger
logger = logging.getLogger(__name__)

# ============================================================================
# MAIN API FUNCTIONS
# ============================================================================


def get_positions(
    ts: datetime,
    planet_id: int = 2,
    apply_kp_offset: bool = True,
    use_hft_cache: bool = None,
) -> PlanetData:
    """Get planet positions with KP lords - maintains legacy signature

    Args:
        ts: Timestamp (will be validated as UTC)
        planet_id: Planet ID (default: 2 for Moon)
        apply_kp_offset: Whether to apply 307s finance offset to CALCULATION
        use_hft_cache: Enable HFT caching (None=auto-detect, True=force on, False=force off)

    Returns:
        PlanetData object with all fields populated
    """
    # Auto-detect HFT mode if not specified
    if use_hft_cache is None:
        import os

        use_hft_cache = os.environ.get("VEDACORE_HFT_MODE", "").lower() == "true"

    # Use HFT-optimized version if enabled
    if use_hft_cache:
        try:
            from .hft_facade import get_positions_hft

            return get_positions_hft(ts, planet_id, apply_kp_offset)
        except ImportError:
            pass  # Fall back to standard version

    # Validate and ensure UTC
    ts_utc = validate_utc_datetime(ts)

    # IMPORTANT: Legacy applies offset to calculation time, not just display
    if apply_kp_offset:
        from datetime import timedelta

        ts_calc = ts_utc + timedelta(seconds=307)  # Add 307 seconds
    else:
        ts_calc = ts_utc

    # Get full position data from Swiss Ephemeris at calculation time
    pos_data = get_planet_position_full(ts_calc, planet_id)

    # Extract key values
    longitude = pos_data["longitude"]
    speed = pos_data["speed_lon"]
    distance = pos_data["distance"]

    # Calculate KP lords (NL/SL/SL2 only for v1)
    nl, sl, sl2 = get_kp_lords_for_planet(longitude)

    # Calculate sign, nakshatra, pada
    sign = sign_index(longitude) + 1  # 1-12
    nakshatra, pada = find_nakshatra_pada(longitude)

    # Determine state (direct/retrograde/stationary)
    state = get_planet_state(speed)

    # Format DMS
    dms = degrees_to_dms(longitude)

    # Calculate speed percentage (relative to average)
    from .swe_backend import get_planet_average_speed

    avg_speed = get_planet_average_speed(planet_id)
    speed_percentage = (abs(speed) / avg_speed) * 100.0 if avg_speed > 0 else 100.0

    # For display, show the original requested time (offset already applied to calc)
    ts_display = ts_utc

    # Build PlanetData object
    return PlanetData(
        position=longitude,
        speed=speed,
        state=state,
        nl=nl,
        sl=sl,
        sl2=sl2,
        sl3=0,  # Disabled for v1
        sign=sign,
        nakshatra=nakshatra,
        pada=pada,
        dms=dms,
        dec=pos_data.get("latitude", 0.0),
        distance=distance,
        speed_percentage=speed_percentage,
        ra=0.0,  # Not calculated in v1
        phase_angle=None,
        magnitude=None,
        acceleration=0.0,
        extras={
            "timestamp_utc": ts_utc.isoformat(),
            "timestamp_display": ts_display.isoformat(),
            "planet_name": PLANET_NAMES.get(planet_id, f"Planet_{planet_id}"),
            "kp_offset_applied": apply_kp_offset,
        },
    )


def get_kp_lord_changes(
    start_utc: datetime,
    end_utc: datetime,
    planet_id: int = 2,
    levels: tuple[str, ...] = ("nl", "sl", "sl2"),
) -> list[KPLordChange]:
    """Detect KP lord changes in time range

    Detection in raw UTC, offset applied only for display timestamps.

    Args:
        start_utc: Start time (UTC)
        end_utc: End time (UTC)
        planet_id: Planet ID (default: 2 for Moon)
        levels: Lord levels to detect changes for

    Returns:
        List of KPLordChange objects
    """
    # Validate timestamps
    start_utc = validate_utc_datetime(start_utc)
    end_utc = validate_utc_datetime(end_utc)

    # Detect changes (in raw UTC)
    changes = detect_kp_lord_changes(start_utc, end_utc, planet_id, levels)

    return changes


# ============================================================================
# BATCH OPERATIONS
# ============================================================================


def get_positions_batch(
    timestamps: list[datetime], planet_id: int = 2, apply_kp_offset: bool = True
) -> list[PlanetData]:
    """Get positions for multiple timestamps

    Args:
        timestamps: List of timestamps
        planet_id: Planet ID
        apply_kp_offset: Whether to apply finance offset

    Returns:
        List of PlanetData objects
    """
    results = []
    for ts in timestamps:
        pos = get_positions(ts, planet_id, apply_kp_offset)
        results.append(pos)
    return results


# ============================================================================
# INITIALIZATION
# ============================================================================


def initialize_ephemeris():
    """Initialize and warm up the ephemeris system

    Call this once at startup for optimal performance.
    """
    # Warm up KP calculations (triggers Numba JIT compilation)
    warmup_kp_calculations()

    # Test calculation to ensure everything works
    now = datetime.now().astimezone()
    _ = get_positions(now)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_current_moon_position() -> PlanetData:
    """Get current Moon position (convenience function)"""

    now = datetime.now(UTC)
    return get_positions(now, planet_id=2)


def format_position(planet_data: PlanetData) -> str:
    """Format position data for display"""
    return (
        f"{planet_data.dms} "
        f"NL:{planet_data.nl} SL:{planet_data.sl} SL2:{planet_data.sl2} "
        f"Speed:{planet_data.speed:.4f}°/day"
    )


def format_change(change: KPLordChange) -> str:
    """Format change event for display"""
    return (
        f"{change.timestamp_utc.isoformat()} "
        f"{change.level.upper()}: {change.old_lord}→{change.new_lord} "
        f"at {change.position:.4f}°"
    )


# ============================================================================
# KP ANALYSIS FUNCTIONS
# ============================================================================


def get_kp_analysis(
    timestamp: datetime,
    latitude: float,
    longitude: float,
    context: Optional["KPContext"] = None,
    include_timing: bool = True,
    include_matters: list[str] | None = None,
) -> "KPAnalysis":
    """
    Perform complete KP astrological analysis.

    This is the main entry point for KP analysis, providing:
    - Cuspal sub-lords for all houses
    - Complete significator hierarchy
    - Star connections and depositor chains
    - House groupings and life matter analysis
    - Timing through dasha and transits

    Args:
        timestamp: Time for analysis (UTC)
        latitude: Location latitude
        longitude: Location longitude
        context: KP context for variations (uses defaults if None)
        include_timing: Whether to include timing analysis
        include_matters: Specific life matters to analyze

    Returns:
        Complete KPAnalysis object
    """
    import time

    from .houses import compute_houses
    from .kp_analysis import (
        AnalysisStatus,
        KPAnalysis,
        KPHouseAnalysis,
        KPPlanetAnalysis,
    )
    from .kp_context import KPContext
    from .kp_cuspal import get_cuspal_analysis
    from .kp_house_groups import LifeMatter, analyze_life_matter
    from .kp_orbs import get_effective_house_position
    from .kp_significators import get_complete_significator_data
    from .kp_star_links import get_complete_star_link_data

    start_time = time.time()

    # Create default context if not provided
    if context is None:
        context = KPContext()

    # Validate context
    context.validate()

    # Generate analysis ID for caching
    id_str = f"{timestamp.isoformat()}|{latitude}|{longitude}|{context.to_cache_key()}"
    analysis_id = analysis_id_hash(id_str)

    # Create analysis container
    analysis = KPAnalysis(
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        context=context,
        analysis_id=analysis_id,
    )

    try:
        # Step 1: Calculate houses
        analysis.status["houses"] = AnalysisStatus.CALCULATING
        houses = compute_houses(timestamp, latitude, longitude)
        analysis._houses = houses
        analysis.status["houses"] = AnalysisStatus.COMPLETE

        # Step 2: Get planet positions
        analysis.status["planets"] = AnalysisStatus.CALCULATING
        planet_positions = {}
        for planet_id in range(1, 10):  # Planets 1-9
            try:
                pos = get_positions(timestamp, planet_id, apply_kp_offset=False)
                planet_positions[planet_id] = {
                    "longitude": pos.longitude,
                    "latitude": pos.latitude,
                    "speed": pos.speed,
                    "nl": pos.nl,
                    "sl": pos.sl,
                    "sl2": pos.sl2,
                    "nakshatra": pos.nakshatra,
                    "house": _get_planet_house(pos.longitude, houses.cusps),
                }
            except Exception as e:
                analysis.warnings.append(f"Could not calculate planet {planet_id}: {e}")
        analysis.status["planets"] = AnalysisStatus.COMPLETE

        # Step 3: Cuspal analysis
        analysis.status["cuspal"] = AnalysisStatus.CALCULATING
        cuspal = get_cuspal_analysis(houses, planet_positions)
        analysis._cuspal = cuspal
        analysis.status["cuspal"] = AnalysisStatus.COMPLETE

        # Step 4: Significator analysis
        analysis.status["significators"] = AnalysisStatus.CALCULATING
        significators = get_complete_significator_data(planet_positions, houses.cusps)
        analysis._significators = significators
        analysis.status["significators"] = AnalysisStatus.COMPLETE

        # Step 5: Star link analysis
        analysis.status["star_links"] = AnalysisStatus.CALCULATING
        star_links = get_complete_star_link_data(planet_positions, houses.cusps)
        analysis._star_links = star_links
        analysis.status["star_links"] = AnalysisStatus.COMPLETE

        # Step 6: Build planet analyses
        for planet_id, pos_data in planet_positions.items():
            planet_analysis = KPPlanetAnalysis(
                planet_id=planet_id,
                planet_name=PLANET_NAMES.get(planet_id, str(planet_id)),
                longitude=pos_data["longitude"],
                latitude=pos_data["latitude"],
                speed=pos_data["speed"],
                retrograde=pos_data["speed"] < 0,
                sign_lord=_get_sign_lord(int(pos_data["longitude"] / 30) + 1),
                star_lord=pos_data["nl"],
                sub_lord=pos_data["sl"],
                sub_sub_lord=pos_data["sl2"],
                house_occupied=pos_data["house"],
                house_position_type=get_effective_house_position(
                    pos_data["longitude"], houses.cusps, context.get_orb("cusp")
                )[1].value,
                houses_owned=_get_houses_owned(planet_id, houses.cusps),
                houses_signified=significators.planet_significations.get(planet_id, []),
                signification_strength=significators.significator_matrix.get(
                    planet_id, {}
                ),
                is_significator_for=_get_primary_significations(
                    planet_id, significators
                ),
                planets_in_my_star=star_links.planets_in_stars.get(planet_id, []),
                my_star_lord_house=planet_positions.get(pos_data["nl"], {}).get(
                    "house", 0
                ),
                depositor_chain=star_links.depositor_chains.get(planet_id, []),
                overall_strength=_calculate_planet_strength(planet_id, pos_data),
                is_combust=False,  # TODO: implement combustion check
                is_in_own_sign=_is_in_own_sign(planet_id, pos_data["longitude"]),
                is_exalted=_is_exalted(planet_id, pos_data["longitude"]),
                is_debilitated=_is_debilitated(planet_id, pos_data["longitude"]),
            )
            analysis.planet_analyses[planet_id] = planet_analysis

        # Step 7: Build house analyses
        for house_num in range(1, 13):
            house_analysis = KPHouseAnalysis(
                house_num=house_num,
                cusp_degree=houses.cusps[house_num - 1],
                sign_lord=cuspal.cusp_signlords[house_num],
                star_lord=cuspal.cusp_starlords[house_num],
                sub_lord=cuspal.cusp_sublords[house_num],
                csl_promises=[],  # TODO: get from cuspal analysis
                csl_denials=[],
                is_fruitful=house_num in cuspal.fruitful_houses,
                occupants=_get_house_occupants(house_num, planet_positions),
                occupant_strength=_calculate_occupant_strength(
                    house_num, planet_positions
                ),
                primary_significators=significators.primary_significators.get(
                    house_num, []
                ),
                all_significators=significators.house_significators.get(house_num, []),
                supporting_houses=_get_supporting_houses(house_num),
                contradicting_houses=_get_contradicting_houses(house_num),
                favorable_periods=[],  # TODO: implement with dasha
                current_activation=False,  # TODO: check current dasha/transit
            )
            analysis.house_analyses[house_num] = house_analysis

        # Step 8: Analyze life matters if requested
        if include_matters:
            for matter_str in include_matters:
                try:
                    matter = LifeMatter(matter_str)
                    matter_analysis = analyze_life_matter(matter, significators)
                    analysis.matter_analyses[matter_str] = matter_analysis
                except Exception as e:
                    analysis.warnings.append(
                        f"Could not analyze matter {matter_str}: {e}"
                    )

        # TODO: Step 9: Timing analysis (requires dasha implementation)

    except Exception as e:
        analysis.errors.append(f"Analysis error: {e}")
        analysis.status["error"] = AnalysisStatus.ERROR

    # Record performance metrics
    analysis.calculation_time_ms = (time.time() - start_time) * 1000

    return analysis


def get_house_promises(
    timestamp: datetime,
    latitude: float,
    longitude: float,
    house_num: int,
    context: Optional["KPContext"] = None,
) -> dict:
    """
    Get what a specific house promises based on its cuspal sub-lord.

    Args:
        timestamp: Time for analysis
        latitude: Location latitude
        longitude: Location longitude
        house_num: House number (1-12)
        context: KP context for variations

    Returns:
        Dictionary with house promises and significators
    """
    analysis = get_kp_analysis(
        timestamp, latitude, longitude, context, include_timing=False
    )
    return analysis.get_house_promise(house_num) or {}


def get_planet_significations(
    timestamp: datetime,
    planet_id: int,
    latitude: float,
    longitude: float,
    context: Optional["KPContext"] = None,
) -> dict:
    """
    Get which houses a planet signifies in the chart.

    Args:
        timestamp: Time for analysis
        planet_id: Planet ID (1-9)
        latitude: Location latitude
        longitude: Location longitude
        context: KP context for variations

    Returns:
        Dictionary with planet's house significations
    """
    analysis = get_kp_analysis(
        timestamp, latitude, longitude, context, include_timing=False
    )
    return analysis.get_planet_significations(planet_id) or {}


# Helper functions for KP analysis
def _get_planet_house(longitude: float, cusps: list[float]) -> int:
    """Determine which house a planet occupies"""
    for i in range(12):
        cusp1 = cusps[i]
        cusp2 = cusps[(i + 1) % 12]
        if cusp1 > cusp2:  # Crosses 0°
            if longitude >= cusp1 or longitude < cusp2:
                return i + 1
        else:
            if cusp1 <= longitude < cusp2:
                return i + 1
    return 1


def _get_sign_lord(sign_num: int) -> int:
    """Get the lord of a zodiac sign"""
    sign_lords = {
        1: 9,
        2: 6,
        3: 5,
        4: 2,
        5: 1,
        6: 5,
        7: 6,
        8: 9,
        9: 3,
        10: 8,
        11: 8,
        12: 3,
    }
    return sign_lords.get(sign_num, 0)


def _get_houses_owned(planet_id: int, cusps: list[float]) -> list[int]:
    """Get houses owned by a planet"""
    planet_signs = {
        1: [5],
        2: [4],
        3: [9, 12],
        4: [],
        5: [3, 6],
        6: [2, 7],
        7: [],
        8: [10, 11],
        9: [1, 8],
    }
    owned = []
    for house_num in range(1, 13):
        cusp_sign = int(cusps[house_num - 1] / 30) + 1
        if cusp_sign in planet_signs.get(planet_id, []):
            owned.append(house_num)
    return owned


def _get_primary_significations(planet_id: int, sig_data) -> list[int]:
    """Get houses where planet is primary significator"""
    primary = []
    for house, planets in sig_data.primary_significators.items():
        if planet_id in planets:
            primary.append(house)
    return primary


def _get_house_occupants(house_num: int, planet_positions: dict) -> list[int]:
    """Get planets occupying a house"""
    return [p for p, data in planet_positions.items() if data.get("house") == house_num]


def _calculate_occupant_strength(house_num: int, planet_positions: dict) -> float:
    """Calculate house strength from occupants"""
    occupants = _get_house_occupants(house_num, planet_positions)
    return len(occupants) * 20.0  # Simplified


def _calculate_planet_strength(planet_id: int, pos_data: dict) -> float:
    """Calculate overall planet strength"""
    strength = 50.0
    if pos_data["speed"] > 0:
        strength += 10
    if planet_id in {1, 2, 3, 5, 6}:  # Benefics
        strength += 10
    return min(100.0, strength)


def _get_supporting_houses(house_num: int) -> list[int]:
    """Get houses that support this house's matters"""
    support_map = {
        1: [5, 9],
        2: [6, 10, 11],
        3: [9, 11],
        4: [9, 11],
        5: [9, 11],
        6: [10, 11],
        7: [2, 11],
        8: [2, 11],
        9: [5, 11],
        10: [2, 6, 11],
        11: [2, 6, 10],
        12: [3, 9],
    }
    return support_map.get(house_num, [])


def _get_contradicting_houses(house_num: int) -> list[int]:
    """Get houses that contradict this house"""
    contradict_map = {
        1: [7, 8, 12],
        2: [8, 12],
        3: [9, 12],
        4: [8, 10],
        5: [1, 10, 12],
        6: [1, 11, 12],
        7: [1, 6],
        8: [1, 2, 11],
        9: [3, 6, 8],
        10: [4, 5, 9],
        11: [5, 8, 12],
        12: [1, 2, 11],
    }
    return contradict_map.get(house_num, [])


def _is_in_own_sign(planet_id: int, longitude: float) -> bool:
    """Check if planet is in its own sign"""
    sign = int(longitude / 30) + 1
    own_signs = {
        1: [5],
        2: [4],
        3: [9, 12],
        5: [3, 6],
        6: [2, 7],
        8: [10, 11],
        9: [1, 8],
    }
    return sign in own_signs.get(planet_id, [])


def _is_exalted(planet_id: int, longitude: float) -> bool:
    """Check if planet is exalted"""
    exaltation = {
        1: (10, 20),
        2: (33, 43),
        3: (90, 100),
        4: (50, 60),
        5: (155, 165),
        6: (355, 365),
        7: (230, 240),
        8: (200, 210),
        9: (270, 280),
    }
    if planet_id in exaltation:
        start, end = exaltation[planet_id]
        return start <= longitude <= end
    return False


def _is_debilitated(planet_id: int, longitude: float) -> bool:
    """Check if planet is debilitated"""
    debilitation = {
        1: (190, 200),
        2: (213, 223),
        3: (270, 280),
        4: (230, 240),
        5: (335, 345),
        6: (175, 185),
        7: (50, 60),
        8: (20, 30),
        9: (90, 100),
    }
    if planet_id in debilitation:
        start, end = debilitation[planet_id]
        return start <= longitude <= end
    return False


# ============================================================================
# TARA BALA FUNCTIONS
# ============================================================================


def get_tara_bala(
    birth_moon_longitude: float,
    current_timestamp: datetime,
    include_full_cycle: bool = False,
) -> dict:
    """
    Calculate Tārā Bala (nakshatra quality) for timing.

    Args:
        birth_moon_longitude: Moon position at birth (degrees)
        current_timestamp: Current time for analysis
        include_full_cycle: Whether to analyze all 27 nakshatras

    Returns:
        Dictionary with tārā bala analysis
    """
    from .tara_bala import get_personal_tara_bala

    # Get current Moon position
    current_moon = get_positions(current_timestamp, planet_id=2, apply_kp_offset=False)

    # Calculate tārā bala
    analysis = get_personal_tara_bala(birth_moon_longitude, current_moon.longitude)

    return analysis.to_dict()


def get_muhurta_tara(
    muhurta_timestamp: datetime, birth_moon_longitudes: list[float]
) -> dict:
    """
    Evaluate muhurta (electional) quality for multiple people.

    Args:
        muhurta_timestamp: Proposed time for event
        birth_moon_longitudes: List of birth Moon positions

    Returns:
        Dictionary with muhurta evaluation
    """
    from .tara_bala import evaluate_muhurta_tara

    # Get muhurta Moon position
    moon = get_positions(muhurta_timestamp, planet_id=2, apply_kp_offset=False)
    muhurta_nakshatra = moon.nakshatra

    # Get birth nakshatras
    birth_nakshatras = []
    for moon_long in birth_moon_longitudes:
        nak = int((moon_long % 360) * 27 / 360) + 1
        if nak > 27:
            nak = 27
        birth_nakshatras.append(nak)

    # Evaluate
    result = evaluate_muhurta_tara(muhurta_nakshatra, birth_nakshatras)
    result["muhurta_time"] = muhurta_timestamp.isoformat()

    return result


# ============================================================================
# TRANSIT ASPECTS FUNCTIONS
# ============================================================================


def get_transit_aspects(
    timestamp: datetime,
    include_moon: bool = True,
    min_strength: float = 0.0,
    tight_orbs_only: bool = False,
) -> list[dict]:
    """
    Get all planetary aspects at a given time.

    Args:
        timestamp: Time for calculation (UTC)
        include_moon: Whether to include Moon aspects
        min_strength: Minimum aspect strength (0-100)
        tight_orbs_only: Use only tight orbs (within 1°)

    Returns:
        List of aspect dictionaries
    """
    from .transit_aspects import find_transit_aspects

    # Get all planet positions
    planet_positions = {}
    for planet_id in range(1, 10):
        pos = get_positions(timestamp, planet_id, apply_kp_offset=False)
        planet_positions[planet_id] = {
            "longitude": pos.longitude,
            "speed": pos.speed,
            "nl": pos.nl,
            "sl": pos.sl,
        }

    # Find aspects
    aspects = find_transit_aspects(
        planet_positions,
        include_moon=include_moon,
        min_strength=min_strength,
        tight_orbs_only=tight_orbs_only,
    )

    return [asp.to_dict() for asp in aspects]


def get_aspect_patterns(timestamp: datetime) -> list[dict]:
    """
    Detect special aspect patterns (Grand Trine, T-Square, etc).

    Args:
        timestamp: Time for calculation (UTC)

    Returns:
        List of pattern dictionaries
    """
    from .transit_aspects import find_aspect_patterns, find_transit_aspects

    # Get all planet positions
    planet_positions = {}
    for planet_id in range(1, 10):
        pos = get_positions(timestamp, planet_id, apply_kp_offset=False)
        planet_positions[planet_id] = {
            "longitude": pos.longitude,
            "speed": pos.speed,
            "nl": pos.nl,
            "sl": pos.sl,
        }

    # Find aspects and patterns
    aspects = find_transit_aspects(planet_positions)
    patterns = find_aspect_patterns(aspects)

    return [pat.to_dict() for pat in patterns]


def get_current_triggers(
    timestamp: datetime, significator_planets: list[int]
) -> list[dict]:
    """
    Get aspects that could trigger events based on significators.

    Args:
        timestamp: Time for calculation (UTC)
        significator_planets: List of planet IDs that are significators

    Returns:
        List of triggering aspects
    """
    from .transit_aspects import find_transit_aspects, get_active_trigger_aspects

    # Get all planet positions
    planet_positions = {}
    for planet_id in range(1, 10):
        pos = get_positions(timestamp, planet_id, apply_kp_offset=False)
        planet_positions[planet_id] = {
            "longitude": pos.longitude,
            "speed": pos.speed,
            "nl": pos.nl,
            "sl": pos.sl,
        }

    # Find all aspects
    all_aspects = find_transit_aspects(planet_positions)

    # Filter for triggers
    triggers = get_active_trigger_aspects(all_aspects, significator_planets)

    return [trig.to_dict() for trig in triggers]


# ============================================================================
# NAKSHATRA COMPATIBILITY FUNCTIONS
# ============================================================================


def get_nakshatra_compatibility(
    nakshatra1: int, nakshatra2: int, full_analysis: bool = True
) -> dict:
    """
    Calculate nakshatra compatibility between two people.

    Args:
        nakshatra1: First person's birth nakshatra (1-27)
        nakshatra2: Second person's birth nakshatra (1-27)
        full_analysis: Whether to calculate all kutas

    Returns:
        Compatibility analysis dictionary
    """
    from .nakshatra_compatibility import calculate_nakshatra_compatibility

    compat = calculate_nakshatra_compatibility(
        nakshatra1, nakshatra2, include_all_kutas=full_analysis
    )

    return compat.to_dict()


def find_best_matches(nakshatra: int, min_compatibility: float = 65.0) -> list[dict]:
    """
    Find most compatible nakshatras for a given birth star.

    Args:
        nakshatra: Birth nakshatra to match (1-27)
        min_compatibility: Minimum compatibility percentage

    Returns:
        List of compatible nakshatra matches
    """
    from .constants import NAKSHATRA_NAMES
    from .nakshatra_compatibility import find_compatible_nakshatras

    matches = find_compatible_nakshatras(nakshatra, min_compatibility)

    return [
        {
            "nakshatra": match[0],
            "name": NAKSHATRA_NAMES.get(match[0], f"Nakshatra-{match[0]}"),
            "compatibility": round(match[1], 1),
            "quality": match[2],
        }
        for match in matches
    ]


# ============================================================================
# SKY MAP FUNCTIONS
# ============================================================================


def get_sky_map(
    timestamp: datetime, latitude: float, longitude: float, include_aspects: bool = True
) -> dict:
    """
    Get complete sky map at a given time and location.

    Args:
        timestamp: Time for calculation (UTC)
        latitude: Location latitude
        longitude: Location longitude
        include_aspects: Whether to include aspects

    Returns:
        Complete sky map dictionary
    """
    from .sky_map import create_sky_map

    sky_map = create_sky_map(
        timestamp, latitude, longitude, include_aspects=include_aspects
    )

    return sky_map.to_dict()


def get_ruling_planets(
    timestamp: datetime, latitude: float, longitude: float
) -> dict[str, str]:
    """
    Get KP Ruling Planets for a moment.

    Args:
        timestamp: Time for calculation (UTC)
        latitude: Location latitude
        longitude: Location longitude

    Returns:
        Dictionary of ruling planets with names
    """
    from .constants import PLANET_NAMES
    from .sky_map import get_ruling_planets as _get_rp

    rp_ids = _get_rp(timestamp, latitude, longitude)

    # Convert IDs to names
    return {key: PLANET_NAMES.get(value, str(value)) for key, value in rp_ids.items()}


# ============================================================================
# FORTUNA POINTS FUNCTIONS
# ============================================================================


def get_fortuna_points(
    timestamp: datetime,
    latitude: float,
    longitude: float,
    include_minor: bool = False,
    track_movement: bool = False,
) -> dict:
    """
    Calculate all fortuna points (Arabic parts/sahams).

    Args:
        timestamp: Time for calculation
        latitude: Location latitude
        longitude: Location longitude
        include_minor: Include minor fortuna points
        track_movement: Track intraday movement

    Returns:
        Dictionary with fortuna analysis
    """
    from .fortuna_points import get_complete_fortuna_analysis
    from .houses import compute_houses

    # Calculate houses
    houses = compute_houses(timestamp, latitude, longitude)

    # Get planet positions
    planet_positions = {}
    for planet_id in range(1, 10):
        pos = get_positions(timestamp, planet_id, apply_kp_offset=False)
        planet_positions[planet_id] = pos.longitude

    # Get house lords (simplified - using natural zodiac)
    house_lords = _get_house_lords(houses.cusps)

    # Calculate fortuna points
    analysis = get_complete_fortuna_analysis(
        timestamp, planet_positions, houses.cusps, house_lords, track_movement
    )

    return analysis.to_dict()


def get_part_of_fortune(
    timestamp: datetime, latitude: float, longitude: float, with_aspects: bool = False
) -> dict:
    """
    Calculate Part of Fortune with detailed analysis.

    Args:
        timestamp: Time for calculation
        latitude: Location latitude
        longitude: Location longitude
        with_aspects: Include aspect analysis

    Returns:
        Dictionary with Part of Fortune data
    """
    from .fortuna_points import (
        analyze_fortuna_aspects,
        calculate_part_of_fortune,
        find_fortuna_house_transits,
    )
    from .houses import compute_houses

    # Calculate houses
    houses = compute_houses(timestamp, latitude, longitude)

    # Get Sun and Moon positions
    sun = get_positions(timestamp, planet_id=1, apply_kp_offset=False)
    moon = get_positions(timestamp, planet_id=2, apply_kp_offset=False)

    # Determine if day birth (Sun above horizon)
    sun_house = _get_planet_house(sun.longitude, houses.cusps)
    is_day_birth = sun_house in [7, 8, 9, 10, 11, 12]

    # Calculate Part of Fortune
    pof_longitude = calculate_part_of_fortune(
        houses.asc, sun.longitude, moon.longitude, is_day_birth
    )

    # Get additional data
    pof_sign = int(pof_longitude / 30) + 1
    pof_house = _get_planet_house(pof_longitude, houses.cusps)
    pof_nakshatra = int((pof_longitude % 360) * 27 / 360) + 1

    result = {
        "longitude": round(pof_longitude, 4),
        "sign": pof_sign,
        "house": pof_house,
        "nakshatra": pof_nakshatra,
        "is_day_birth": is_day_birth,
    }

    # Add aspects if requested
    if with_aspects:
        planet_positions = {}
        for planet_id in range(1, 10):
            pos = get_positions(timestamp, planet_id, apply_kp_offset=False)
            planet_positions[planet_id] = pos.longitude

        aspects = analyze_fortuna_aspects(pof_longitude, planet_positions)
        result["aspects"] = aspects

        # Add upcoming house transits
        transits = find_fortuna_house_transits(
            pof_longitude, 13.176, houses.cusps, 24  # Moon's average daily motion
        )
        result["next_transits"] = transits

    return result


def track_fortuna_movement_for_day(
    date: datetime, latitude: float, longitude: float, fortuna_type: str = "FORTUNE"
) -> list[dict]:
    """
    Track fortuna point movement throughout a day.

    Args:
        date: Date to track
        latitude: Location latitude
        longitude: Location longitude
        fortuna_type: Which fortuna to track

    Returns:
        List of hourly positions
    """
    from .fortuna_points import FortunaType, calculate_fortuna_point
    from .houses import compute_houses

    movements = []

    # Map string to FortunaType
    type_map = {
        "FORTUNE": FortunaType.FORTUNE,
        "SPIRIT": FortunaType.SPIRIT,
        "LOVE": FortunaType.LOVE,
        "MARRIAGE": FortunaType.MARRIAGE,
        "CAREER": FortunaType.CAREER,
        "WEALTH": FortunaType.WEALTH,
    }

    fortuna_enum = type_map.get(fortuna_type.upper(), FortunaType.FORTUNE)

    # Calculate for each hour
    for hour in range(24):
        timestamp = date.replace(hour=hour, minute=0, second=0)

        # Calculate houses
        houses = compute_houses(timestamp, latitude, longitude)

        # Get planet positions
        planet_positions = {}
        for planet_id in range(1, 10):
            pos = get_positions(timestamp, planet_id, apply_kp_offset=False)
            planet_positions[planet_id] = pos.longitude

        # Calculate fortuna point
        point = calculate_fortuna_point(fortuna_enum, planet_positions, houses.cusps)

        movements.append(
            {
                "hour": hour,
                "timestamp": timestamp.isoformat(),
                "longitude": round(point.longitude, 4),
                "house": point.house,
                "sign": point.sign,
            }
        )

    return movements


# Helper function for house lords
def _get_house_lords(cusps: list[float]) -> dict[int, int]:
    """Get house lords based on cusp signs"""
    house_lords = {}
    sign_lords = {
        1: 9,
        2: 6,
        3: 5,
        4: 2,
        5: 1,
        6: 5,
        7: 6,
        8: 9,
        9: 3,
        10: 8,
        11: 8,
        12: 3,
    }

    for i, cusp in enumerate(cusps):
        sign = int(cusp / 30) + 1
        house_lords[i + 1] = sign_lords.get(sign, 1)

    return house_lords


# ============================================================================
# MOON FACTORS API
# ============================================================================


def get_lunar_panchanga(ts: datetime) -> dict:
    """Get Panchanga (5 limbs) for timestamp

    Args:
        ts: Timestamp (will be validated as UTC)

    Returns:
        Dictionary with tithi, nakshatra, yoga, karana, vara
    """
    ts_utc = validate_utc_datetime(ts)
    return get_panchanga(ts_utc)


def get_lunar_factors(ts: datetime, apply_kp_offset: bool = False):
    """Get comprehensive moon factors

    Args:
        ts: Timestamp (will be validated as UTC)
        apply_kp_offset: Whether to apply 307s finance offset

    Returns:
        MoonFactors object with all lunar calculations
    """
    ts_utc = validate_utc_datetime(ts)

    if apply_kp_offset:
        from datetime import timedelta

        ts_calc = ts_utc + timedelta(seconds=307)
    else:
        ts_calc = ts_utc

    return get_moon_factors(ts_calc)


def find_tithi_changes(start: datetime, end: datetime) -> list[dict]:
    """Find tithi changes in time range

    Args:
        start: Start time (will be validated as UTC)
        end: End time (will be validated as UTC)

    Returns:
        List of tithi change events
    """
    start_utc = validate_utc_datetime(start)
    end_utc = validate_utc_datetime(end)

    calculator = MoonFactorsCalculator()
    return calculator.find_tithi_changes(start_utc, end_utc)


# ============================================================================
# VARGA (DIVISIONAL CHARTS) FUNCTIONS
# ============================================================================


def get_varga_chart_from_longitudes(
    longitudes: dict[int, float], divisor: int, scheme: str = "auto"
) -> dict[int, int]:
    """Calculate varga chart directly from planet longitudes.

    Args:
        longitudes: Dictionary of planet_id -> longitude
        divisor: Divisional chart number (2-300)
        scheme: Calculation scheme ("auto", "linear", "classical", etc.)

    Returns:
        Dictionary of planet_id -> varga sign (0-11)
    """
    from refactor.varga import varga_sign
    from refactor.varga_config import get_varga_config
    from refactor.varga_piecewise import register_piecewise_schemes

    # Register piecewise schemes if not already done
    register_piecewise_schemes()

    config = get_varga_config()

    # Auto-select scheme if requested
    if scheme == "auto":
        scheme = config.get_scheme_for_divisor(divisor)

    results = {}
    for planet_id, longitude in longitudes.items():
        results[planet_id] = varga_sign(longitude, divisor, scheme)

    return results


def get_varga_chart(
    timestamp: datetime, divisor: int, planets: list[int] = None, scheme: str = "auto"
) -> dict[int, int]:
    """Calculate varga chart for a timestamp.

    Args:
        timestamp: UTC datetime
        divisor: Divisional chart number (2-300)
        planets: List of planet IDs (default: all 9 planets)
        scheme: Calculation scheme

    Returns:
        Dictionary of planet_id -> varga sign (0-11)
    """
    ts_utc = validate_utc_datetime(timestamp)

    if planets is None:
        planets = [1, 2, 3, 4, 5, 6, 7, 8, 9]  # All 9 traditional planets

    # Get planet longitudes
    longitudes = {}
    for planet_id in planets:
        pos = get_positions(ts_utc, planet_id)
        longitudes[planet_id] = pos.longitude

    return get_varga_chart_from_longitudes(longitudes, divisor, scheme)


def get_vargottama_status(
    timestamp: datetime, check_vargas: list[int] = None, planets: list[int] = None
) -> dict[int, dict[str, bool]]:
    """Check vargottama status for planets.

    A planet is vargottama when it occupies the same sign in D1 and a varga.

    Args:
        timestamp: UTC datetime
        check_vargas: List of divisors to check (default: [9])
        planets: List of planet IDs (default: all 9)

    Returns:
        Dictionary of planet_id -> {"D9": True/False, ...}
    """
    from refactor.varga import detect_vargottama

    ts_utc = validate_utc_datetime(timestamp)

    if planets is None:
        planets = [1, 2, 3, 4, 5, 6, 7, 8, 9]

    # Get planet longitudes
    longitudes = {}
    for planet_id in planets:
        pos = get_positions(ts_utc, planet_id)
        longitudes[planet_id] = pos.longitude

    return detect_vargottama(longitudes, check_vargas)


def get_all_shodasavarga(timestamp: datetime, planet_id: int = None) -> dict[str, dict]:
    """Calculate all 16 Shodasavarga divisional charts.

    Args:
        timestamp: UTC datetime
        planet_id: Specific planet ID, or None for all planets

    Returns:
        Dictionary of "D{n}" -> {planet_id: sign}
    """
    from refactor.varga_config import get_varga_config

    ts_utc = validate_utc_datetime(timestamp)
    config = get_varga_config()

    # Get Shodasavarga divisors
    divisors = config.get_shodasavarga_divisors()

    # Determine which planets to calculate
    if planet_id is not None:
        planets = [planet_id]
    else:
        planets = [1, 2, 3, 4, 5, 6, 7, 8, 9]

    # Calculate all vargas
    results = {}
    for divisor in divisors:
        varga_name = f"D{divisor}"
        results[varga_name] = get_varga_chart(ts_utc, divisor, planets)

    return results


def get_varga_strength(
    timestamp: datetime, planet_id: int, varga_set: str = "shadvarga"
) -> float:
    """Calculate Vimshopaka Bala strength for a planet.

    Args:
        timestamp: UTC datetime
        planet_id: Planet ID (1-9)
        varga_set: Weight set ("shadvarga", "saptavarga", "dashavarga", "shodasavarga")

    Returns:
        Strength score (0-100)
    """
    from refactor.varga import get_varga_strength as varga_strength_calc
    from refactor.varga_config import get_varga_config

    ts_utc = validate_utc_datetime(timestamp)
    config = get_varga_config()

    # Get weights for the specified set
    weights_dict = config.get_vimshopaka_weights(varga_set)
    check_vargas = list(weights_dict.keys())

    # Get planet longitude
    pos = get_positions(ts_utc, planet_id)
    longitudes = {planet_id: pos.longitude}

    # Calculate strength
    strengths = varga_strength_calc(longitudes, check_vargas, weights_dict)
    return strengths.get(planet_id, 0.0)


def register_custom_varga_scheme(
    name: str, divisor: int, offsets: dict[int, int]
) -> bool:
    """Register a custom varga calculation scheme.

    Args:
        name: Unique name for the scheme
        divisor: Number of divisions
        offsets: Per-sign offset dictionary

    Returns:
        True if successfully registered
    """
    from refactor.varga import make_custom_offsets_scheme

    try:
        make_custom_offsets_scheme(offsets, name)
        return True
    except Exception as e:
        logger.error(f"Failed to register custom varga scheme {name}: {e}")
        return False


# ============================================================================
# VERSION INFO
# ============================================================================

__version__ = "1.2.0"  # Updated for varga charts
__description__ = "Refactored KP Ephemeris Facade with Varga System"


def get_version_info() -> dict:
    """Get version and configuration info"""
    return {
        "version": __version__,
        "description": __description__,
        "modules": {
            "swe_backend": "Swiss Ephemeris interface",
            "kp_chain": "KP lord calculations",
            "change_finder": "Lord change detection",
            "time_utils": "Timezone handling",
        },
        "configuration": {
            "ayanamsa": "Krishnamurti",
            "node_model": "True Node",
            "finance_offset": "307 seconds",
            "levels": ["nl", "sl", "sl2"],
        },
    }
