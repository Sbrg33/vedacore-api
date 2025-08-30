#!/usr/bin/env python3
"""
Centralized KP Constants and Planet ID Mappings
Production values from master_ephe - DO NOT MODIFY IDs
"""

import numpy as np

import swisseph as swe

# ============================================================================
# PLANET ID MAPPING - FROM PRODUCTION (DO NOT CHANGE)
# ============================================================================
# Source: master_ephe/core/master_ephemeris.py
PLANET_IDS = {
    1: swe.SUN,
    2: swe.MOON,
    3: swe.JUPITER,
    4: swe.TRUE_NODE,  # Rahu (always True Node)
    5: swe.MERCURY,
    6: swe.VENUS,
    7: -swe.TRUE_NODE,  # Ketu (opposite of Rahu)
    8: swe.SATURN,
    9: swe.MARS,
}

# Planet names for display
PLANET_NAMES = {
    1: "Sun",
    2: "Moon",
    3: "Jupiter",
    4: "Rahu",
    5: "Mercury",
    6: "Venus",
    7: "Ketu",
    8: "Saturn",
    9: "Mars",
}

# ============================================================================
# KP SYSTEM CONSTANTS
# ============================================================================
# Vimshottari Dasha Lords sequence (planet IDs)
VIMSHOTTARI_LORDS = [
    7,
    6,
    1,
    2,
    9,
    4,
    3,
    8,
    5,
]  # Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter, Saturn, Mercury

# Vimshottari Dasha periods in years
VIMSHOTTARI_YEARS = [7.0, 20.0, 6.0, 10.0, 7.0, 18.0, 16.0, 19.0, 17.0]

# Total years in Vimshottari cycle
VIMSHOTTARI_TOTAL_YEARS = 120.0

# Nakshatra and Pada spans
NAKSHATRA_SPAN = 13.333333333333334  # 360° / 27 nakshatras
PADA_SPAN = 3.333333333333334  # NAKSHATRA_SPAN / 4 padas

# Number of nakshatras and padas
NUM_NAKSHATRAS = 27
NUM_PADAS = 4

# ============================================================================
# NUMERICAL CONSTANTS
# ============================================================================
# Boundary epsilon for numerical stability (use consistently everywhere)
BOUNDARY_EPSILON = 0.0001

# Minimum speed threshold for calculations
MIN_SPEED_THRESHOLD = 0.001

# Time step limits for refinement
MIN_DT = 0.0001  # Minimum time step in days
MAX_DT = 0.5  # Maximum time step in days

# Convergence criteria for bisection
CONVERGENCE_EPSILON = 1e-10
MAX_ITERATIONS = 20

# ============================================================================
# ARCSECOND CONSTANTS (for precise boundary calculations)
# ============================================================================
TOT_ARCSEC = 1_296_000  # 360 * 3600 arcseconds
SIGN_ARCSEC = 108_000  # 30 * 3600 arcseconds (one zodiac sign)
NAK_ARCSEC = 48_000  # 13°20' = 13.333... * 3600 arcseconds
PADA_ARCSEC = 12_000  # 3°20' = 3.333... * 3600 arcseconds

# ============================================================================
# PRE-COMPUTED VALUES FOR PERFORMANCE
# ============================================================================
# Vimshottari proportions (fractions within any parent segment)
VIMSHOTTARI_PROP = np.array(VIMSHOTTARI_YEARS) / sum(VIMSHOTTARI_YEARS)

# Cumulative proportions (for sub-lord calculation)
VIMSHOTTARI_CUM = np.cumsum(VIMSHOTTARI_PROP)

# Lord array as numpy array for indexing
LORD_ARRAY = np.array(VIMSHOTTARI_LORDS)

# Lord index mapping (planet_id -> array index)
LORD_INDEX = {int(pid): i for i, pid in enumerate(VIMSHOTTARI_LORDS)}

# Fractional epsilon for KP chain calculations
EPS_F = (BOUNDARY_EPSILON / NAKSHATRA_SPAN) * 2.0

# ============================================================================
# MOD VALUES (for nakshatra lord calculation)
# ============================================================================
# Maps nakshatra number (1-27) to lord index (1-9)
MOD_VALUES = [
    7,
    20,
    6,
    10,
    7,
    18,
    16,
    19,
    17,  # Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter, Saturn, Mercury
    7,
    20,
    6,
    10,
    7,
    18,
    16,
    19,
    17,  # Repeat for Magha to Jyeshtha
    7,
    20,
    6,
    10,
    7,
    18,
    16,
    19,
    17,  # Repeat for Moola to Revati
]

# ============================================================================
# FINANCE CONSTANTS
# ============================================================================
# Finance latency offset in seconds (KP-specific, applied at display only)
FINANCE_LATENCY_SECONDS = 307  # 5:07 (307 seconds) - exact KP alignment
FINANCE_LATENCY_ENABLED = True

# KP timing offset configuration (to match reference sources)
KP_TIMING_OFFSET_MINUTES = 5
KP_TIMING_OFFSET_ENABLED = True
KP_TIMING_OFFSET_LABEL = "KP_OFFSET_ACTIVE"

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================
# TTL (Time To Live) in seconds for different planets
PLANET_TTL = {
    1: 3600,  # Sun: 1 hour
    2: 300,  # Moon: 5 minutes (fastest moving)
    3: 3600,  # Jupiter: 1 hour
    4: 600,  # Rahu: 10 minutes (dynamic)
    5: 1800,  # Mercury: 30 minutes
    6: 1800,  # Venus: 30 minutes
    7: 600,  # Ketu: 10 minutes (dynamic)
    8: 3600,  # Saturn: 1 hour
    9: 1800,  # Mars: 30 minutes
}

# ============================================================================
# NAKSHATRA NAMES (1-indexed)
# ============================================================================
NAKSHATRA_NAMES = {
    1: "Ashwini",
    2: "Bharani",
    3: "Krittika",
    4: "Rohini",
    5: "Mrigashira",
    6: "Ardra",
    7: "Punarvasu",
    8: "Pushya",
    9: "Ashlesha",
    10: "Magha",
    11: "Purva Phalguni",
    12: "Uttara Phalguni",
    13: "Hasta",
    14: "Chitra",
    15: "Swati",
    16: "Vishakha",
    17: "Anuradha",
    18: "Jyeshtha",
    19: "Moola",
    20: "Purva Ashadha",
    21: "Uttara Ashadha",
    22: "Shravana",
    23: "Dhanishta",
    24: "Shatabhisha",
    25: "Purva Bhadrapada",
    26: "Uttara Bhadrapada",
    27: "Revati",
}

# ============================================================================
# ZODIAC SIGNS (1-indexed)
# ============================================================================
SIGN_NAMES = {
    1: "Aries",
    2: "Taurus",
    3: "Gemini",
    4: "Cancer",
    5: "Leo",
    6: "Virgo",
    7: "Libra",
    8: "Scorpio",
    9: "Sagittarius",
    10: "Capricorn",
    11: "Aquarius",
    12: "Pisces",
}

# ============================================================================
# WARNING: NEVER IMPORT FROM constants_work_in_progress/
# ============================================================================
# The constants_work_in_progress directory contains experimental values
# and should NEVER be imported in production modules
