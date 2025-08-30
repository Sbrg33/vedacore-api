#!/usr/bin/env python3
"""
Global Locality Research - Activation Engine
Pure mathematical engine for planetary activation field calculations.

Implements the core activation formula with all PM-approved modifiers.
NO I/O, NO state fetching - processes only inputs for maximum testability.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any, NamedTuple

from constants.activation_model import (
    ACTIVATION_MAX,
    ACTIVATION_MIN,
    ACTIVATION_SCALE_FACTOR,
    ANGLE_PROXIMITY_THRESHOLD_DEG,
    APPLYING_ASPECT_BONUS,
    BREAKDOWN_KEY_ORDER,
    DAY_BIRTH_MULTIPLIER,
    NIGHT_BIRTH_MULTIPLIER,
    NUMERIC_PRECISION_DP,
    PLANET_CONTRIB_MAX,
    PLANET_CONTRIB_MIN,
    SUN_CAP_MAX,
    SUN_CAP_MIN,
    get_combustion_radius,
    get_profile_config,
)
from modules.access_service import AccessGeometry, compute_planet_to_angle_distances
from modules.sky_state_service import SkyState, get_planet_state


class PlanetContribution(NamedTuple):
    """Individual planet's contribution to activation"""

    planet_id: int
    planet_name: str
    base_contribution: float  # C_p before modifiers
    modulated_contribution: float  # After D_p modifiers
    primary_angle: str  # Strongest angle connection
    connection_strength: float  # 0-1 strength to primary angle
    applying_bonus_applied: bool  # Whether applying bonus was used
    modifiers_applied: list[str]  # List of modifier names applied


class ActivationDrivers(NamedTuple):
    """Primary drivers of activation at this location"""

    strongest_planet: str
    strongest_angle: str
    connection_type: str  # "aspect" or "proximity"
    orb_degrees: float
    applying: bool
    contribution_strength: float


@dataclass
class ActivationResult:
    """Complete activation calculation result"""

    # Core results (all bounded [0,1] before scaling)
    total_activation: float  # Total before Sun cap and scaling
    sun_capped_activation: float  # After Sun cap application
    scaled_activation: float  # Final 0-100 scaled result

    # Component analysis
    planet_contributions: dict[str, PlanetContribution]
    phase_multiplier: float  # Φ applied to Moon term
    sun_cap_factor: float  # S_cap factor applied

    # Drivers and modifiers
    primary_drivers: ActivationDrivers
    active_modifiers: list[str]  # All modifiers that affected result

    # Flags for API response
    flags: dict[str, bool]  # eclipse_corridor, voc, retro, etc.

    # Mathematical validation
    bounds_valid: bool  # All intermediate results within [0,1]
    sun_additive_check: bool  # Confirms Sun not in additive terms


def _enforce_bounds(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Enforce bounds on activation values."""
    return max(min_val, min(max_val, value))


def _compute_base_planet_contribution(
    planet_id: int, planet_longitude: float, access: AccessGeometry
) -> tuple[float, str, float]:
    """Compute base planet contribution (C_p) to location activation.

    Args:
        planet_id: Planet ID
        planet_longitude: Planet position in degrees
        access: AccessGeometry for this location

    Returns:
        Tuple of (base_contribution, primary_angle, connection_strength)
    """
    # Compute distances to all angles
    angle_distances = compute_planet_to_angle_distances(planet_longitude, access)

    # Find primary angle connection (closest within threshold)
    primary_angle = "asc"  # Default
    min_distance = angle_distances["asc"]

    for angle_name, distance in angle_distances.items():
        if distance < min_distance:
            min_distance = distance
            primary_angle = angle_name

    # Compute base contribution using strictly monotonic distance decay
    # Scale contribution to ensure sum of all planets stays within bounds
    MAX_PLANET_CONTRIB = 0.20  # Each planet max 20% so 8 planets = 160% max

    # Use simple monotonic distance decay for predictable behavior
    distance_factor = 1.0 - (min_distance / 180.0)  # [1.0 at 0°, 0.0 at 180°]

    # Apply angular threshold boost for planets near angles
    if min_distance <= ANGLE_PROXIMITY_THRESHOLD_DEG:
        angular_boost = 1.5  # 50% boost for angular planets
        base_contribution = distance_factor * angular_boost * MAX_PLANET_CONTRIB
    else:
        base_contribution = distance_factor * MAX_PLANET_CONTRIB

    # Connection strength for analysis
    connection_strength = 1.0 - (min_distance / 180.0)

    # Ensure within bounds
    base_contribution = _enforce_bounds(base_contribution)
    connection_strength = _enforce_bounds(connection_strength)

    return base_contribution, primary_angle, connection_strength


def _apply_planet_modifiers(
    planet_id: int,
    base_contribution: float,
    sky_state: SkyState,
    access: AccessGeometry,
    profile_config: dict[str, Any],
) -> tuple[float, list[str], bool]:
    """Apply planet-specific modifiers (D_p factors).

    Args:
        planet_id: Planet ID
        base_contribution: Base C_p value
        sky_state: Global sky state
        access: Location access geometry
        profile_config: Model profile configuration

    Returns:
        Tuple of (modulated_contribution, modifiers_applied, applying_bonus_used)
    """
    modulated = base_contribution
    modifiers = []
    applying_bonus_used = False

    planet_state = get_planet_state(sky_state, planet_id)
    if planet_state is None:
        return modulated, modifiers, applying_bonus_used

    # Mercury retrograde penalty (PM requirement: Mercury only)
    if planet_id == 5 and planet_state.retrograde:  # Mercury
        retro_penalty = profile_config.get("mercury_retro_penalty", 0) / 100.0
        modulated *= 1.0 + retro_penalty  # -10% becomes 0.9 multiplier
        modifiers.append("mercury_retrograde")

    # Station window bonus (±24h from station)
    if planet_state.station_within_24h:
        station_bonus = profile_config.get("station_window_bonus", 0) / 100.0
        modulated *= 1.0 + station_bonus
        modifiers.append("station_window")

    # Combustion penalty (distance to Sun)
    if planet_id != 1 and planet_state.combustion_distance is not None:
        combustion_radius = get_combustion_radius(planet_id)
        if planet_state.combustion_distance <= combustion_radius:
            # Linear penalty based on distance to Sun
            penalty_factor = (
                1.0 - (planet_state.combustion_distance / combustion_radius) * 0.3
            )
            modulated *= penalty_factor
            modifiers.append("combustion")

    # Void of Course penalty (Moon only, major aspects)
    if planet_id == 2:  # Moon
        voc_status = get_moon_void_of_course_status(sky_state)
        if voc_status.get("is_voc", False):
            voc_penalty = profile_config.get("voc_penalty", 0) / 100.0
            modulated *= 1.0 + voc_penalty  # -30% becomes 0.7 multiplier
            modifiers.append("void_of_course")

    # Mutual reception bonus (research profile only)
    mutual_bonus = profile_config.get("mutual_reception_bonus")
    if mutual_bonus is not None:
        # Mutual reception detection (research profile only)
        if _detect_mutual_reception(planet_id, sky_state, access):
            modulated *= 1.0 + mutual_bonus / 100.0
            modifiers.append("mutual_reception")

    # Eclipse corridor modulation
    if profile_config.get("eclipse_modulation", False):
        if sky_state.eclipse_exact_corridor:
            modulated *= 1.15  # +15% boost in exact eclipse corridor
            modifiers.append("eclipse_exact")
        elif sky_state.eclipse_warning_corridor:
            modulated *= 1.08  # +8% boost in warning corridor
            modifiers.append("eclipse_warning")

    # Gandānta handling
    if profile_config.get("gandanta_handling", False):
        if access.gandanta_axis:
            modulated *= 0.95  # -5% penalty for boundary confusion
            modifiers.append("gandanta")

    # Applying aspect bonus (if planet is applying to angle)
    if _is_planet_applying_to_angles(planet_id, sky_state, access):
        modulated *= APPLYING_ASPECT_BONUS
        applying_bonus_used = True
        modifiers.append("applying_aspect")

    # Ensure bounds after all modifiers
    modulated = _enforce_bounds(modulated)

    return modulated, modifiers, applying_bonus_used


def _detect_mutual_reception(
    planet_id: int, sky_state: SkyState, access: AccessGeometry
) -> bool:
    """Detect mutual reception between planet and nakshatra lord.

    Args:
        planet_id: Planet ID to check
        sky_state: Global sky state
        access: Location access geometry

    Returns:
        True if mutual reception detected
    """
    # Mutual reception detection for research profile (placeholder)
    return False


def _is_planet_applying_to_angles(
    planet_id: int, sky_state: SkyState, access: AccessGeometry
) -> bool:
    """Check if planet is applying to any chart angle.

    Args:
        planet_id: Planet ID
        sky_state: Global sky state
        access: Location access geometry

    Returns:
        True if planet is applying (orb decreasing) to any angle
    """
    planet_state = get_planet_state(sky_state, planet_id)
    if planet_state is None:
        return False

    # Simplified applying logic: faster planets are generally applying
    base_speed = sky_state.angular_speeds.get(planet_id, 0.0)
    return abs(base_speed) > 0.5  # Arbitrary threshold for "fast enough to apply"


def _compute_sun_cap_factor(sky_state: SkyState, access: AccessGeometry) -> float:
    """Compute Sun cap factor (S_cap) for total activation.

    Args:
        sky_state: Global sky state
        access: Location access geometry

    Returns:
        Sun cap factor within [SUN_CAP_MIN, SUN_CAP_MAX]
    """
    sun_state = get_planet_state(sky_state, 1)  # Sun
    if sun_state is None:
        return 1.0

    sun_longitude = sun_state.longitude

    # Compute Sun's proximity to angles
    sun_distances = compute_planet_to_angle_distances(sun_longitude, access)
    min_sun_distance = min(sun_distances.values())

    # Sun cap increases when Sun is angular (close to ASC/MC/DESC/IC)
    angular_factor = 1.0 - (min_sun_distance / 90.0)  # Normalize to [0,1]
    angular_factor = _enforce_bounds(angular_factor)

    # Base cap with angular modulation
    base_cap = 1.0 + angular_factor * 0.3  # Up to +30% when angular

    # Day/night modulation
    day_night_factor = (
        DAY_BIRTH_MULTIPLIER if access.is_day_birth else NIGHT_BIRTH_MULTIPLIER
    )
    sun_cap = base_cap * day_night_factor

    # Apply bounds
    sun_cap = max(SUN_CAP_MIN, min(SUN_CAP_MAX, sun_cap))

    return sun_cap


def _find_primary_drivers(
    contributions: dict[str, PlanetContribution],
) -> ActivationDrivers:
    """Identify primary activation drivers.

    Args:
        contributions: Planet contribution details

    Returns:
        ActivationDrivers with strongest connections
    """
    strongest_planet = "moon"
    strongest_contrib = 0.0
    strongest_angle = "asc"
    strongest_strength = 0.0
    applying = False

    for planet_name, contrib in contributions.items():
        if contrib.modulated_contribution > strongest_contrib:
            strongest_contrib = contrib.modulated_contribution
            strongest_planet = planet_name
            strongest_angle = contrib.primary_angle
            strongest_strength = contrib.connection_strength
            applying = contrib.applying_bonus_applied

    return ActivationDrivers(
        strongest_planet=strongest_planet,
        strongest_angle=strongest_angle,
        connection_type="proximity",  # Simplified for MVP
        orb_degrees=strongest_strength * 30.0,  # Approximate orb
        applying=applying,
        contribution_strength=strongest_contrib,
    )


def get_moon_void_of_course_status(sky_state: SkyState) -> dict[str, Any]:
    """Get Moon VoC status from sky state service."""
    from modules.sky_state_service import get_moon_void_of_course_status as _get_voc

    return _get_voc(sky_state)


def compute_activation(
    sky_state: SkyState, access: AccessGeometry, model_profile: str
) -> ActivationResult:
    """Compute complete activation for location (CORE ENGINE FUNCTION).

    Args:
        sky_state: Global sky state
        access: Location access geometry
        model_profile: Model profile to use

    Returns:
        Complete ActivationResult
    """
    from refactor.constants import PLANET_NAMES

    profile_config = get_profile_config(model_profile)

    # ========================================================================
    # PHASE 1: Compute base planet contributions (C_p)
    # ========================================================================

    planet_contributions = {}
    total_activation = 0.0
    all_modifiers = []

    # Process each planet (EXCLUDING SUN - PM requirement)
    for planet_id in [2, 3, 4, 5, 6, 7, 8, 9]:  # Moon through Mars (NO SUN)
        planet_state = get_planet_state(sky_state, planet_id)
        if planet_state is None:
            continue

        planet_name = PLANET_NAMES.get(planet_id, f"planet_{planet_id}").lower()
        planet_longitude = planet_state.longitude

        # Compute base contribution
        base_contrib, primary_angle, connection_strength = (
            _compute_base_planet_contribution(planet_id, planet_longitude, access)
        )

        # Apply planet-specific modifiers
        modulated_contrib, modifiers, applying_used = _apply_planet_modifiers(
            planet_id, base_contrib, sky_state, access, profile_config
        )

        # Store contribution details
        planet_contributions[planet_name] = PlanetContribution(
            planet_id=planet_id,
            planet_name=planet_name,
            base_contribution=base_contrib,
            modulated_contribution=modulated_contrib,
            primary_angle=primary_angle,
            connection_strength=connection_strength,
            applying_bonus_applied=applying_used,
            modifiers_applied=modifiers,
        )

        all_modifiers.extend(modifiers)

        # Add to total (Sun NOT included - PM enforcement)
        total_activation += modulated_contrib

    # Normalize total to [0,1] bounds if needed (PM requirement)
    if total_activation > ACTIVATION_MAX:
        normalization_factor = ACTIVATION_MAX / total_activation
        # Apply normalization to all planet contributions
        for planet_name in planet_contributions:
            contrib = planet_contributions[planet_name]
            planet_contributions[planet_name] = PlanetContribution(
                planet_id=contrib.planet_id,
                planet_name=contrib.planet_name,
                base_contribution=contrib.base_contribution,
                modulated_contribution=contrib.modulated_contribution
                * normalization_factor,
                primary_angle=contrib.primary_angle,
                connection_strength=contrib.connection_strength,
                applying_bonus_applied=contrib.applying_bonus_applied,
                modifiers_applied=contrib.modifiers_applied,
            )
        total_activation *= normalization_factor

    # ========================================================================
    # PHASE 2: Apply Moon phase modulation (Φ factor)
    # ========================================================================

    moon_contrib = planet_contributions.get("moon")
    if moon_contrib:
        # Apply phase multiplier to Moon term only
        phase_multiplier = sky_state.phase_multiplier
        original_moon = moon_contrib.modulated_contribution
        phase_modulated_moon = original_moon * phase_multiplier

        # Update Moon contribution
        planet_contributions["moon"] = PlanetContribution(
            planet_id=moon_contrib.planet_id,
            planet_name=moon_contrib.planet_name,
            base_contribution=moon_contrib.base_contribution,
            modulated_contribution=phase_modulated_moon,
            primary_angle=moon_contrib.primary_angle,
            connection_strength=moon_contrib.connection_strength,
            applying_bonus_applied=moon_contrib.applying_bonus_applied,
            modifiers_applied=moon_contrib.modifiers_applied + ["phase_modulation"],
        )

        # Update total
        total_activation = total_activation - original_moon + phase_modulated_moon
        all_modifiers.append("phase_modulation")
    else:
        phase_multiplier = 1.0

    # ========================================================================
    # PHASE 3: Apply Sun cap (S_cap) - Sun influence without additive term
    # ========================================================================

    sun_cap = _compute_sun_cap_factor(sky_state, access)
    sun_capped_activation = total_activation * sun_cap

    # ========================================================================
    # PHASE 4: Final bounds and scaling
    # ========================================================================

    # Enforce final bounds before scaling
    final_bounded = _enforce_bounds(
        sun_capped_activation, ACTIVATION_MIN, ACTIVATION_MAX
    )

    # Scale to 0-100 range
    scaled_result = final_bounded * ACTIVATION_SCALE_FACTOR

    # ========================================================================
    # PHASE 5: Generate metadata and drivers
    # ========================================================================

    # Find primary drivers
    primary_drivers = _find_primary_drivers(planet_contributions)

    # Generate flags for API
    flags = {
        "eclipse_corridor": sky_state.eclipse_exact_corridor
        or sky_state.eclipse_warning_corridor,
        "voc": get_moon_void_of_course_status(sky_state).get("is_voc", False),
        "retro": any(
            get_planet_state(sky_state, pid).retrograde
            for pid in [2, 3, 4, 5, 6, 7, 8, 9]
            if get_planet_state(sky_state, pid) is not None
        ),
        "station": sky_state.any_planet_stationary,
        "gandanta_axis": access.gandanta_axis,
        "gandanta_planet": False,  # Planet gandanta detection (future enhancement)
        "combustion": sky_state.any_planet_combust,
    }

    # Mathematical validation
    bounds_valid = all(
        PLANET_CONTRIB_MIN <= contrib.modulated_contribution <= PLANET_CONTRIB_MAX
        for contrib in planet_contributions.values()
    )

    # Sun additive check (PM requirement)
    sun_additive_check = (
        "sun" not in planet_contributions
    )  # Sun should NEVER be in contributions

    # ========================================================================
    # PHASE 6: Format contributions with deterministic ordering
    # ========================================================================

    # Sort contributions by BREAKDOWN_KEY_ORDER for deterministic JSON
    ordered_contributions = {}
    for planet_key in BREAKDOWN_KEY_ORDER:
        if planet_key in planet_contributions:
            ordered_contributions[planet_key] = planet_contributions[planet_key]

    return ActivationResult(
        total_activation=round(total_activation, NUMERIC_PRECISION_DP),
        sun_capped_activation=round(final_bounded, NUMERIC_PRECISION_DP),
        scaled_activation=round(scaled_result, NUMERIC_PRECISION_DP),
        planet_contributions=ordered_contributions,
        phase_multiplier=round(phase_multiplier, NUMERIC_PRECISION_DP),
        sun_cap_factor=round(sun_cap, NUMERIC_PRECISION_DP),
        primary_drivers=primary_drivers,
        active_modifiers=list(set(all_modifiers)),  # Remove duplicates
        flags=flags,
        bounds_valid=bounds_valid,
        sun_additive_check=sun_additive_check,
    )


def validate_activation_result(result: ActivationResult) -> dict[str, bool]:
    """Validate activation result against mathematical invariants.

    Args:
        result: ActivationResult to validate

    Returns:
        Dictionary of validation results
    """
    validations = {
        "bounds_valid": result.bounds_valid,
        "sun_additive_forbidden": result.sun_additive_check,
        "phase_multiplier_reasonable": 0.5 <= result.phase_multiplier <= 1.5,
        "sun_cap_in_bounds": SUN_CAP_MIN <= result.sun_cap_factor <= SUN_CAP_MAX,
        "contributions_ordered": list(result.planet_contributions.keys())
        == [k for k in BREAKDOWN_KEY_ORDER if k in result.planet_contributions],
        "no_nan_values": not any(
            math.isnan(contrib.modulated_contribution)
            for contrib in result.planet_contributions.values()
        ),
        "scaled_in_range": 0.0 <= result.scaled_activation <= 100.0,
    }

    return validations


# Export main interface
__all__ = [
    "ActivationDrivers",
    "ActivationResult",
    "PlanetContribution",
    "compute_activation",
    "validate_activation_result",
]
