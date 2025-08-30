#!/usr/bin/env python3
"""
KP Analysis Module
Complete KP analysis data structures and orchestration
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .constants import PLANET_NAMES
from .houses import Houses
from .kp_context import KPContext
from .kp_cuspal import CuspalAnalysis
from .kp_house_groups import HouseGroupAnalysis
from .kp_significators import SignificatorData
from .kp_star_links import StarLinkData


class AnalysisStatus(Enum):
    """Status of analysis components"""

    PENDING = "pending"
    CALCULATING = "calculating"
    COMPLETE = "complete"
    ERROR = "error"
    CACHED = "cached"


@dataclass
class KPPlanetAnalysis:
    """Complete KP analysis for a single planet"""

    planet_id: int
    planet_name: str
    longitude: float
    latitude: float
    speed: float
    retrograde: bool

    # KP Lords
    sign_lord: int
    star_lord: int  # Nakshatra lord
    sub_lord: int
    sub_sub_lord: int

    # House position
    house_occupied: int
    house_position_type: str  # deep/middle/early/late/sandhi
    houses_owned: list[int]

    # Significations
    houses_signified: list[int]
    signification_strength: dict[int, float]  # house -> strength
    is_significator_for: list[int]  # Primary significator for these houses

    # Star connections
    planets_in_my_star: list[int]
    my_star_lord_house: int
    depositor_chain: list[int]

    # Strength factors
    overall_strength: float
    is_combust: bool
    is_in_own_sign: bool
    is_exalted: bool
    is_debilitated: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "planet": self.planet_name,
            "position": {
                "longitude": round(self.longitude, 4),
                "latitude": round(self.latitude, 4),
                "speed": round(self.speed, 4),
                "retrograde": self.retrograde,
            },
            "kp_lords": {
                "sign_lord": PLANET_NAMES.get(self.sign_lord, str(self.sign_lord)),
                "star_lord": PLANET_NAMES.get(self.star_lord, str(self.star_lord)),
                "sub_lord": PLANET_NAMES.get(self.sub_lord, str(self.sub_lord)),
                "sub_sub_lord": PLANET_NAMES.get(
                    self.sub_sub_lord, str(self.sub_sub_lord)
                ),
            },
            "house_position": {
                "occupied": self.house_occupied,
                "type": self.house_position_type,
                "owned": self.houses_owned,
            },
            "significations": {
                "houses": self.houses_signified,
                "strength": {
                    k: round(v, 2) for k, v in self.signification_strength.items()
                },
                "primary_for": self.is_significator_for,
            },
            "star_connections": {
                "planets_in_star": [
                    PLANET_NAMES.get(p, str(p)) for p in self.planets_in_my_star
                ],
                "star_lord_house": self.my_star_lord_house,
                "depositor_chain": [
                    PLANET_NAMES.get(p, str(p)) for p in self.depositor_chain
                ],
            },
            "strength": {
                "overall": round(self.overall_strength, 2),
                "combust": self.is_combust,
                "own_sign": self.is_in_own_sign,
                "exalted": self.is_exalted,
                "debilitated": self.is_debilitated,
            },
        }


@dataclass
class KPHouseAnalysis:
    """Complete KP analysis for a single house"""

    house_num: int
    cusp_degree: float

    # Cuspal lords
    sign_lord: int
    star_lord: int
    sub_lord: int

    # CSL analysis
    csl_promises: list[str]
    csl_denials: list[str]
    is_fruitful: bool

    # Occupants
    occupants: list[int]
    occupant_strength: float

    # Significators
    primary_significators: list[int]
    all_significators: list[tuple[int, str, float]]  # (planet, level, strength)

    # House combinations
    supporting_houses: list[int]
    contradicting_houses: list[int]

    # Timing
    favorable_periods: list[dict]  # From dasha analysis
    current_activation: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "house": self.house_num,
            "cusp": round(self.cusp_degree, 2),
            "lords": {
                "sign": PLANET_NAMES.get(self.sign_lord, str(self.sign_lord)),
                "star": PLANET_NAMES.get(self.star_lord, str(self.star_lord)),
                "sub": PLANET_NAMES.get(self.sub_lord, str(self.sub_lord)),
            },
            "csl_analysis": {
                "promises": self.csl_promises,
                "denials": self.csl_denials,
                "fruitful": self.is_fruitful,
            },
            "occupants": {
                "planets": [PLANET_NAMES.get(p, str(p)) for p in self.occupants],
                "strength": round(self.occupant_strength, 2),
            },
            "significators": {
                "primary": [
                    PLANET_NAMES.get(p, str(p)) for p in self.primary_significators
                ],
                "count": len(self.all_significators),
            },
            "relationships": {
                "supporting": self.supporting_houses,
                "contradicting": self.contradicting_houses,
            },
            "timing": {
                "currently_active": self.current_activation,
                "favorable_periods": len(self.favorable_periods),
            },
        }


@dataclass
class KPTimingAnalysis:
    """Timing analysis combining dasha and transits"""

    current_dasha: dict  # MD/AD/PD/SD/PAD lords
    ruling_planets: dict  # Current RP

    # Activation status
    activated_houses: list[int]
    activated_matters: list[str]
    timing_strength: float

    # Windows
    next_change: datetime | None
    favorable_windows: list[dict]  # Next favorable periods
    challenging_windows: list[dict]  # Periods to avoid

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "current": {
                "dasha": self.current_dasha,
                "ruling_planets": self.ruling_planets,
                "activated_houses": self.activated_houses,
                "activated_matters": self.activated_matters,
                "strength": round(self.timing_strength, 2),
            },
            "future": {
                "next_change": (
                    self.next_change.isoformat() if self.next_change else None
                ),
                "favorable_count": len(self.favorable_windows),
                "challenging_count": len(self.challenging_windows),
            },
        }


@dataclass
class KPAnalysis:
    """
    Complete KP astrological analysis.

    This is the main container for all KP analysis results.
    """

    # Metadata
    timestamp: datetime
    latitude: float
    longitude: float
    context: KPContext
    analysis_id: str = ""  # Unique ID for caching

    # Status tracking
    status: dict[str, AnalysisStatus] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Core components (lazy loaded)
    _houses: Houses | None = None
    _cuspal: CuspalAnalysis | None = None
    _significators: SignificatorData | None = None
    _star_links: StarLinkData | None = None

    # Planet analyses
    planet_analyses: dict[int, KPPlanetAnalysis] = field(default_factory=dict)

    # House analyses
    house_analyses: dict[int, KPHouseAnalysis] = field(default_factory=dict)

    # Life matter analyses
    matter_analyses: dict[str, HouseGroupAnalysis] = field(default_factory=dict)

    # Timing analysis
    timing: KPTimingAnalysis | None = None

    # Performance metrics
    calculation_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def houses(self) -> Houses | None:
        """Lazy-loaded house data"""
        if self._houses is None and self.status.get("houses") != AnalysisStatus.ERROR:
            self._load_houses()
        return self._houses

    @property
    def cuspal(self) -> CuspalAnalysis | None:
        """Lazy-loaded cuspal analysis"""
        if self._cuspal is None and self.status.get("cuspal") != AnalysisStatus.ERROR:
            self._load_cuspal()
        return self._cuspal

    @property
    def significators(self) -> SignificatorData | None:
        """Lazy-loaded significator data"""
        if (
            self._significators is None
            and self.status.get("significators") != AnalysisStatus.ERROR
        ):
            self._load_significators()
        return self._significators

    @property
    def star_links(self) -> StarLinkData | None:
        """Lazy-loaded star link data"""
        if (
            self._star_links is None
            and self.status.get("star_links") != AnalysisStatus.ERROR
        ):
            self._load_star_links()
        return self._star_links

    def _load_houses(self):
        """Load house data (implement in facade)"""
        self.status["houses"] = AnalysisStatus.CALCULATING
        # Implementation will be in facade
        pass

    def _load_cuspal(self):
        """Load cuspal analysis (implement in facade)"""
        self.status["cuspal"] = AnalysisStatus.CALCULATING
        # Implementation will be in facade
        pass

    def _load_significators(self):
        """Load significator data (implement in facade)"""
        self.status["significators"] = AnalysisStatus.CALCULATING
        # Implementation will be in facade
        pass

    def _load_star_links(self):
        """Load star link data (implement in facade)"""
        self.status["star_links"] = AnalysisStatus.CALCULATING
        # Implementation will be in facade
        pass

    def get_summary(self) -> dict:
        """Get analysis summary for quick overview"""
        return {
            "metadata": {
                "timestamp": self.timestamp.isoformat(),
                "location": f"{self.latitude:.4f}, {self.longitude:.4f}",
                "mode": self.context.mode,
                "analysis_id": self.analysis_id,
            },
            "status": {k: v.value for k, v in self.status.items()},
            "results": {
                "planets_analyzed": len(self.planet_analyses),
                "houses_analyzed": len(self.house_analyses),
                "matters_analyzed": len(self.matter_analyses),
                "has_timing": self.timing is not None,
            },
            "performance": {
                "calculation_time_ms": round(self.calculation_time_ms, 2),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_ratio": round(
                    (
                        self.cache_hits / (self.cache_hits + self.cache_misses)
                        if (self.cache_hits + self.cache_misses) > 0
                        else 0
                    ),
                    2,
                ),
            },
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }

    def to_dict(
        self,
        include_all: bool = False,
        include_planets: bool = True,
        include_houses: bool = True,
        include_timing: bool = True,
    ) -> dict:
        """
        Convert to dictionary for API response.

        Args:
            include_all: Include all components
            include_planets: Include planet analyses
            include_houses: Include house analyses
            include_timing: Include timing analysis

        Returns:
            Dictionary representation
        """
        result = {"summary": self.get_summary()}

        if include_all or include_planets:
            result["planets"] = {
                planet_id: analysis.to_dict()
                for planet_id, analysis in self.planet_analyses.items()
            }

        if include_all or include_houses:
            result["houses"] = {
                house_num: analysis.to_dict()
                for house_num, analysis in self.house_analyses.items()
            }

        if include_all or include_timing:
            if self.timing:
                result["timing"] = self.timing.to_dict()

        if self.matter_analyses:
            result["matters"] = {
                matter: analysis.to_dict()
                for matter, analysis in self.matter_analyses.items()
            }

        # Include errors and warnings if present
        if self.errors:
            result["errors"] = self.errors

        if self.warnings:
            result["warnings"] = self.warnings

        return result

    def get_house_promise(self, house_num: int) -> dict | None:
        """Get what a specific house promises"""
        if house_num in self.house_analyses:
            analysis = self.house_analyses[house_num]
            return {
                "house": house_num,
                "fruitful": analysis.is_fruitful,
                "promises": analysis.csl_promises,
                "denials": analysis.csl_denials,
                "primary_significators": [
                    PLANET_NAMES.get(p, str(p)) for p in analysis.primary_significators
                ],
            }
        return None

    def get_planet_significations(self, planet_id: int) -> dict | None:
        """Get what houses a planet signifies"""
        if planet_id in self.planet_analyses:
            analysis = self.planet_analyses[planet_id]
            return {
                "planet": analysis.planet_name,
                "signifies": analysis.houses_signified,
                "primary_for": analysis.is_significator_for,
                "strength": analysis.signification_strength,
            }
        return None

    def get_matter_prospects(self, matter: str) -> dict | None:
        """Get prospects for a life matter"""
        if matter in self.matter_analyses:
            analysis = self.matter_analyses[matter]
            return {
                "matter": matter,
                "strength": analysis.strength,
                "favorable": analysis.timing_favorable,
                "primary_houses": analysis.primary_houses,
                "significators": [
                    PLANET_NAMES.get(p, str(p)) for p in analysis.significators
                ],
            }
        return None
