"""Constants for VedaCore Location Features.
All values are centralized here to avoid policy drift across modules.
Adjust cautiously and keep changes documented in docs/technical/LOCATION_FEATURES_API.md.
"""

from __future__ import annotations

# Proximity threshold (degrees) for angular distance to Asc/MC/Desc/IC.
ANGLE_PROX_THRESHOLD_DEG: float = 30.0

# Penalty window for distance to nearest cusp (degrees). Within this window,
# scores are linearly penalized up to CUSP_PENALTY_WEIGHT.
CUSP_PENALTY_WINDOW_DEG: float = 3.0
CUSP_PENALTY_WEIGHT: float = 0.40  # 40% max penalty when right on the cusp

# House class weights. Do not rename keys; logic depends on these literals.
HOUSE_WEIGHTS = {
    "angular": 1.00,    # Houses 1,4,7,10
    "succedent": 0.65,  # Houses 2,5,8,11
    "cadent": 0.35,     # Houses 3,6,9,12
}

# Classical aspects used for angle relationships.
ASPECT_ANGLES_DEG = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "opposition": 180.0,
}

# Maximum orbs (degrees) for each aspect type.
ASPECT_ORBS_DEG = {
    "conjunction": 5.0,
    "opposition": 5.0,
    "square": 4.0,
    "trine": 4.0,
    "sextile": 3.0,
}

# Bonus factor for applying aspects vs separating.
APPLYING_ASPECT_BONUS: float = 1.10

# PM6 production hardening
MAX_LOCATIONS_PER_REQUEST: int = 200

# LST segment labels (8-segment scheme)
LST_SEGMENTS = [
    "midnight",
    "pre-dawn", 
    "dawn",
    "forenoon",
    "noon-peak",
    "afternoon", 
    "dusk",
    "evening"
]