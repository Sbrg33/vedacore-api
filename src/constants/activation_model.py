#!/usr/bin/env python3
"""
Global Locality Research - Activation Model Constants
Single source of truth for all model parameters, profiles, and specifications.

Model Version: GLA-1.0.0
PM-approved implementation following all four specification documents.

CHANGELOG:
- GLA-1.0.0 (2025-08-26): Initial release with default and research-1 profiles
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any

# ============================================================================
# MODEL VERSIONING
# ============================================================================
MODEL_VERSION = "GLA-1.0.0"
MODEL_DESCRIPTION = "Global Locality Research - Planetary Activation Field Mapping"

# Valid model profiles (sealed set for reproducibility)
VALID_PROFILES = {"default", "research-1"}

# ============================================================================
# MODEL PROFILES (PM-SEALED CONFIGURATIONS)
# ============================================================================
MODEL_PROFILES: Dict[str, Dict[str, Any]] = {
    "default": {
        # Mercury retrograde penalty (applied only to Mercury in D_p)
        "mercury_retro_penalty": -10,  # -10% when Mercury retrograde
        
        # Mutual reception bonus (OFF in default, research only)
        "mutual_reception_bonus": None,  # Disabled
        
        # Station window bonus (±24h from ephemeris events)
        "station_window_bonus": 20,  # +20% when within ±24h of station
        
        # Void of Course penalty (major aspects only to angles)
        "voc_penalty": -30,  # -30% when Moon void of course
        
        # Eclipse corridor modulation
        "eclipse_modulation": True,
        
        # Gandānta boundary handling
        "gandanta_handling": True,
        
        # Seasonal nakshatra modulation (experimental)
        "seasonal_modulation": False,  # Disabled by default
        
        # Latitude-scaled orbs (high latitude compensation)
        "latitude_scaled_orbs": False,  # Disabled by default
    },
    
    "research-1": {
        # Same as default but with research features enabled
        "mercury_retro_penalty": -10,
        "mutual_reception_bonus": 8,  # +8% when mutual reception detected
        "station_window_bonus": 20,
        "voc_penalty": -30,
        "eclipse_modulation": True,
        "gandanta_handling": True,
        "seasonal_modulation": True,  # ±5% seasonal variation
        "latitude_scaled_orbs": True,  # Scale orbs by sqrt(R_lat) for >60°
    }
}

# ============================================================================
# CORE ASTRONOMICAL SPECIFICATIONS (PM-LOCKED)
# ============================================================================

# VoC definition: LOCKED to major aspects only (PM requirement)
MAJOR_ASPECTS_DEG: List[float] = [0.0, 60.0, 90.0, 120.0, 180.0]

# Node calculation policy (align with positions adapter)  
TRUE_NODE_POLICY: bool = True  # Use True Node for Rahu/Ketu

# Combustion radii per planet (frozen exact thresholds)
COMBUSTION_RADII_DEG: Dict[int, float] = {
    1: 8.0,   # Sun (self-reference, not used but included for completeness)
    2: 12.0,  # Moon
    3: 8.0,   # Jupiter  
    4: 8.0,   # Rahu
    5: 8.0,   # Mercury
    6: 8.0,   # Venus
    7: 8.0,   # Ketu
    8: 9.0,   # Saturn
    9: 8.0,   # Mars
}

# Station detection window (PM specification)
STATION_WINDOW_HOURS: int = 24  # ±24h UTC from ephemeris events

# Gatekeeper (axis-lord condition) score bounds  
GATEKEEPER_BOUNDS: tuple[float, float] = (0.85, 1.15)

# Nakshatra boundary handling rule
NAKSHATRA_BOUNDARY_RULE: str = "left_closed_right_open"

# ============================================================================
# ASPECT & PROXIMITY PARAMETERS
# ============================================================================

# Aspect orbs for activation calculations (degrees)
ASPECT_ORBS_DEG: Dict[str, float] = {
    "conjunction": 5.0,
    "sextile": 3.0, 
    "square": 4.0,
    "trine": 4.0,
    "opposition": 5.0,
}

# Angular proximity threshold (distance to ASC/MC/DESC/IC)
ANGLE_PROXIMITY_THRESHOLD_DEG: float = 30.0

# Applying aspect bonus multiplier
APPLYING_ASPECT_BONUS: float = 1.10

# ============================================================================
# ECLIPSE & NODE PARAMETERS  
# ============================================================================

# Eclipse corridor definitions (PM specification)
ECLIPSE_WARNING_CORRIDOR_DEG: float = 12.0  # Warning zone around nodes
ECLIPSE_EXACT_CORRIDOR_DEG: float = 1.0     # Exact eclipse zone

# Node proximity effects
NODE_PROXIMITY_STRONG_DEG: float = 3.0      # Strong node influence
NODE_PROXIMITY_MODERATE_DEG: float = 8.0    # Moderate node influence

# ============================================================================
# SUN MODULATION PARAMETERS
# ============================================================================

# Sun cap bounds (S_cap in formula) 
SUN_CAP_MIN: float = 0.70  # Minimum Sun influence
SUN_CAP_MAX: float = 1.30  # Maximum Sun influence

# Day/night modulation factors
DAY_BIRTH_MULTIPLIER: float = 1.10   # +10% for day birth
NIGHT_BIRTH_MULTIPLIER: float = 0.90 # -10% for night birth

# ============================================================================
# PHASE & TIMING PARAMETERS
# ============================================================================

# Sun-Moon phase influence on Moon term (Φ in formula)
PHASE_INFLUENCE_WEIGHT: float = 0.15  # How much phase affects Moon term

# Time-to-exact weighting for immediacy
IMMEDIACY_WEIGHT: float = 0.20  # Weight for applying vs separating

# ============================================================================
# LATITUDE & RELIABILITY PARAMETERS
# ============================================================================

# Latitude reliability bands for confidence scoring
LATITUDE_HIGH_RELIABILITY_MAX: float = 60.0   # High confidence below 60°
LATITUDE_MED_RELIABILITY_MAX: float = 66.5    # Medium confidence 60-66.5°
LATITUDE_POLAR_HARD_LIMIT: float = 66.5       # Hard limit for 422 response

# Latitude orb scaling factor (for research profile)
LATITUDE_ORB_SCALING_THRESHOLD: float = 60.0  # Apply scaling above 60°

# ============================================================================
# OUTPUT FORMATTING & DETERMINISM
# ============================================================================

# Breakdown key ordering (alphabetical for deterministic JSON)
BREAKDOWN_KEY_ORDER: List[str] = [
    "jupiter", "mars", "mercury", "moon", 
    "rahu", "saturn", "venus", "ketu"
]

# Numeric precision for deterministic output
NUMERIC_PRECISION_DP: int = 4  # 4 decimal places

# Activation score scaling (0-1 to 0-100)
ACTIVATION_SCALE_FACTOR: int = 100

# ============================================================================
# GANDĀNTA PARAMETERS
# ============================================================================

# Gandānta junction boundaries (transition zones between water/fire signs)
GANDANTA_BOUNDARIES_DEG: List[tuple[float, float]] = [
    (356.6667, 360.0),    # Revati-Ashwini (Pisces-Aries) 
    (0.0, 3.3333),        # Ashwini continuation
    (116.6667, 120.0),    # Ashlesha-Magha (Cancer-Leo)
    (236.6667, 240.0),    # Jyeshtha-Moola (Scorpio-Sagittarius)
]

# Gandānta orb (degrees on either side of exact boundary)
GANDANTA_ORB_DEG: float = 1.0

# ============================================================================
# CACHE & PERFORMANCE PARAMETERS
# ============================================================================

# Cache TTL for different components (seconds)
CACHE_TTL_SKY_STATE: int = 60      # 1 minute for global sky state
CACHE_TTL_ACCESS: int = 300        # 5 minutes for access geometry
CACHE_TTL_BASELINE: int = 3600     # 1 hour for novelty baselines

# Performance targets (for validation)
TARGET_LATENCY_P50_MS: float = 2.0   # p50 latency target per location
TARGET_LATENCY_P99_MS: float = 10.0  # p99 latency target per location
TARGET_CACHE_HIT_RATIO: float = 0.80 # 80% cache hit target

# ============================================================================
# VALIDATION & BOUNDS
# ============================================================================

# Planet contribution bounds (before Sun cap application)
PLANET_CONTRIB_MIN: float = 0.0  # Minimum individual planet contribution
PLANET_CONTRIB_MAX: float = 1.0  # Maximum individual planet contribution

# Total activation bounds (before scaling to 0-100)
ACTIVATION_MIN: float = 0.0  # Minimum total activation
ACTIVATION_MAX: float = 1.0  # Maximum total activation (before Sun cap)

# ============================================================================
# FEATURE FLAGS & TOGGLES
# ============================================================================

# Default feature states (can be overridden by profile)
DEFAULT_FEATURE_FLAGS: Dict[str, bool] = {
    "mercury_retro_enabled": True,
    "voc_penalty_enabled": True, 
    "station_bonus_enabled": True,
    "eclipse_modulation_enabled": True,
    "gandanta_handling_enabled": True,
    "combustion_penalty_enabled": True,
    "applying_bonus_enabled": True,
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_profile_config(profile: str) -> Dict[str, Any]:
    """Get configuration for specified profile.
    
    Args:
        profile: Profile name (must be in VALID_PROFILES)
        
    Returns:
        Profile configuration dictionary
        
    Raises:
        ValueError: If profile is not recognized
    """
    if profile not in VALID_PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Valid profiles: {VALID_PROFILES}")
    
    return MODEL_PROFILES[profile].copy()


def get_model_fingerprint(profile: str) -> str:
    """Generate fingerprint for caching.
    
    Args:
        profile: Profile name
        
    Returns:
        Unique fingerprint string for cache keys
    """
    return f"{MODEL_VERSION}:{profile}"


def validate_profile_params(profile_config: Dict[str, Any]) -> bool:
    """Validate profile configuration parameters.
    
    Args:
        profile_config: Profile configuration to validate
        
    Returns:
        True if valid, False otherwise
    """
    required_keys = {
        "mercury_retro_penalty", "station_window_bonus", "voc_penalty",
        "eclipse_modulation", "gandanta_handling"
    }
    
    return all(key in profile_config for key in required_keys)


def get_combustion_radius(planet_id: int) -> float:
    """Get combustion radius for planet.
    
    Args:
        planet_id: Planet ID (1-9)
        
    Returns:
        Combustion radius in degrees
    """
    return COMBUSTION_RADII_DEG.get(planet_id, 8.0)  # Default 8° if not found


def is_major_aspect(aspect_deg: float, orb_tolerance: float = 0.1) -> bool:
    """Check if degree separation is a major aspect.
    
    Args:
        aspect_deg: Angular separation in degrees
        orb_tolerance: Tolerance for exact match
        
    Returns:
        True if within orb of major aspect
    """
    for major_aspect in MAJOR_ASPECTS_DEG:
        if abs(aspect_deg - major_aspect) <= orb_tolerance:
            return True
    return False


def get_latitude_reliability(latitude: float) -> str:
    """Get reliability rating for latitude.
    
    Args:
        latitude: Latitude in degrees
        
    Returns:
        Reliability rating: "high", "med", or "low"
    """
    abs_lat = abs(latitude)
    if abs_lat < LATITUDE_HIGH_RELIABILITY_MAX:
        return "high"
    elif abs_lat < LATITUDE_MED_RELIABILITY_MAX:
        return "med"
    else:
        return "low"


def should_apply_polar_hard_limit(latitude: float) -> bool:
    """Check if latitude exceeds polar hard limit.
    
    Args:
        latitude: Latitude in degrees
        
    Returns:
        True if should return 422 error
    """
    return abs(latitude) >= LATITUDE_POLAR_HARD_LIMIT


# ============================================================================
# MODEL METADATA
# ============================================================================

__all__ = [
    # Core constants
    "MODEL_VERSION", "MODEL_DESCRIPTION", "VALID_PROFILES", "MODEL_PROFILES",
    
    # Astronomical specifications
    "MAJOR_ASPECTS_DEG", "TRUE_NODE_POLICY", "COMBUSTION_RADII_DEG", 
    "STATION_WINDOW_HOURS", "GATEKEEPER_BOUNDS", "NAKSHATRA_BOUNDARY_RULE",
    
    # Parameters
    "ASPECT_ORBS_DEG", "ANGLE_PROXIMITY_THRESHOLD_DEG", "APPLYING_ASPECT_BONUS",
    "ECLIPSE_WARNING_CORRIDOR_DEG", "ECLIPSE_EXACT_CORRIDOR_DEG", 
    "SUN_CAP_MIN", "SUN_CAP_MAX", "DAY_BIRTH_MULTIPLIER", "NIGHT_BIRTH_MULTIPLIER",
    
    # Formatting & validation
    "BREAKDOWN_KEY_ORDER", "NUMERIC_PRECISION_DP", "ACTIVATION_SCALE_FACTOR",
    
    # Helper functions
    "get_profile_config", "get_model_fingerprint", "validate_profile_params",
    "get_combustion_radius", "is_major_aspect", "get_latitude_reliability",
    "should_apply_polar_hard_limit"
]