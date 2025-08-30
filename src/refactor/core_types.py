#!/usr/bin/env python3
"""
Core data types for Master Ephemeris refactoring
Matches production data structures from master_ephe
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# ============================================================================
# PLANET DATA
# ============================================================================


@dataclass
class PlanetData:
    """Planet data with KP lords and serialization support

    Matches master_ephe/core/master_ephemeris.py:1156
    """

    position: float  # Sidereal longitude in degrees
    speed: float  # Speed in degrees/day
    state: int  # 0=direct, 1=retrograde, 2=stationary
    nl: int  # Nakshatra lord (planet ID)
    sl: int  # Sub lord (planet ID)
    sl2: int  # 2nd Sub lord (planet ID)
    sl3: int = 0  # 3rd Sub lord (disabled for v1)
    sign: int = 0  # Zodiac sign (1-12)
    nakshatra: int = 0  # Nakshatra number (1-27)
    pada: int = 0  # Pada number (1-4)
    dms: str = ""  # Degrees-minutes-seconds format
    dec: float = 0.0  # Declination
    distance: float = 0.0  # Distance in AU
    speed_percentage: float = 0.0  # Speed as percentage of average
    ra: float = 0.0  # Right ascension
    phase_angle: float | None = None
    magnitude: float | None = None
    acceleration: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def longitude(self) -> float:
        """Alias for position to maintain backward compatibility.

        Some modules expect .longitude while others use .position.
        This property ensures both work seamlessly.
        """
        return self.position

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Remove None values for cleaner JSON
        return {k: v for k, v in data.items() if v is not None}

    def get_kp_chain(self, levels: int = 3) -> list[int]:
        """Get KP chain up to specified level"""
        chain = [self.nl]
        if levels >= 2 and self.sl:
            chain.append(self.sl)
        if levels >= 3 and self.sl2:
            chain.append(self.sl2)
        if levels >= 4 and self.sl3:
            chain.append(self.sl3)
        return chain[:levels]


# ============================================================================
# KP LORD CHANGE EVENT
# ============================================================================


@dataclass
class KPLordChange:
    """KP lord change event with serialization

    Also used for sign ingresses with level='sign' where old_lord/new_lord
    represent old_sign/new_sign (1-12).

    Matches master_ephe/core/master_ephemeris.py:1205
    """

    timestamp_utc: datetime
    julian_day: float
    planet_id: int
    level: str  # 'nl', 'sl', 'sl2', 'sl3', or 'sign' for ingresses
    old_lord: int  # For sign ingresses, this is old_sign (1-12)
    new_lord: int  # For sign ingresses, this is new_sign (1-12)
    position: float  # Planet position at change
    timestamp_ny: datetime | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "julian_day": self.julian_day,
            "planet_id": self.planet_id,
            "level": self.level,
            "old_lord": self.old_lord,
            "new_lord": self.new_lord,
            "position": self.position,
            "timestamp_ny": (
                self.timestamp_ny.isoformat() if self.timestamp_ny else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KPLordChange":
        """Create from dictionary"""
        data = data.copy()
        data["timestamp_utc"] = datetime.fromisoformat(data["timestamp_utc"])
        if data.get("timestamp_ny"):
            data["timestamp_ny"] = datetime.fromisoformat(data["timestamp_ny"])
        return cls(**data)


# ============================================================================
# CALCULATION PROFILE
# ============================================================================


@dataclass
class CalcProfile:
    """Calculation profile for ephemeris settings

    Simplified from master_ephe for v1 refactoring
    """

    ayanamsa_id: int  # e.g., swe.SIDM_KRISHNAMURTI
    node_model: str = "true"  # "true" | "mean" (always true for v1)
    use_true_positions: bool = True
    topocentric_planets: bool = False
    house_system: bytes = b"P"  # Placidus (not used in v1)

    # House edge policy for planets exactly on cusps
    house_edge_policy: str = "entering"  # "entering" | "preceding"

    # Apply empirical adjustments (always False in production)
    apply_adjustments: bool = False

    # Finance latency configuration
    finance_latency_enabled: bool = True
    finance_latency_seconds: int = 307

    # KP timing offset configuration
    kp_timing_offset_minutes: int = 5
    kp_timing_offset_enabled: bool = True
    kp_timing_offset_label: str = "KP_OFFSET_ACTIVE"

    # Cache TTL configuration (seconds)
    planet_ttl: dict[int, int] = field(
        default_factory=lambda: {
            1: 3600,  # Sun: 1 hour
            2: 300,  # Moon: 5 minutes
            3: 3600,  # Jupiter: 1 hour
            4: 600,  # Rahu: 10 minutes
            5: 1800,  # Mercury: 30 minutes
            6: 1800,  # Venus: 30 minutes
            7: 600,  # Ketu: 10 minutes
            8: 3600,  # Saturn: 1 hour
            9: 1800,  # Mars: 30 minutes
        }
    )


# ============================================================================
# BATCH CALCULATION RESULTS
# ============================================================================


@dataclass
class BatchPositionResult:
    """Result of batch position calculation"""

    timestamp: datetime
    positions: dict[int, PlanetData]  # planet_id -> PlanetData

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "positions": {
                str(pid): pdata.to_dict() for pid, pdata in self.positions.items()
            },
        }


# ============================================================================
# EVENT SCHEMA (Future-proofing for multiple systems)
# ============================================================================


@dataclass
class AstrologyEvent:
    """Standard event schema for all astrology systems

    Future-proofing for KP, Chinese, Chaldean, etc.
    """

    ts_utc: datetime
    system: str  # "KP", "Chinese", "Chaldean", etc.
    entity: str  # Planet name or entity
    level: str  # Type of change/event
    value: Any  # Current value
    change: dict | None = None  # Change details (old/new)
    meta: dict[str, Any] = field(default_factory=dict)  # Additional metadata

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "ts_utc": self.ts_utc.isoformat(),
            "system": self.system,
            "entity": self.entity,
            "level": self.level,
            "value": self.value,
            "change": self.change,
            "meta": self.meta,
        }
