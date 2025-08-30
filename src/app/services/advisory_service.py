"""
Advisory service for Vedic/KP/Jaimini enhancement layers.
Collects and aggregates advisory calculations based on feature flags.
"""

import logging
import time

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.feature_flags import get_feature_flags

# Lazy imports to avoid numpy dependency when not needed
try:
    from refactor.facade import get_house_cusps, get_positions
    from refactor.moon_factors import get_lunar_panchanga

    FACADE_AVAILABLE = True
except ImportError:
    FACADE_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class AdvisoryContext:
    """Context for advisory calculations."""

    timestamp: datetime
    latitude: float = 40.7128  # Default NYC
    longitude: float = -74.0060
    planets: dict[int, dict] = None
    houses: dict[int, float] = None
    ascendant: float = None
    moon_longitude: float = None
    sunrise: datetime = None
    sunset: datetime = None
    aspects: dict = None

    def __post_init__(self):
        """Initialize context with astronomical data."""
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)

        if self.planets is None:
            self.planets = self._load_planets()

        if self.houses is None:
            self._load_houses()

        if self.moon_longitude is None:
            moon_data = self.planets.get(2, {})
            self.moon_longitude = moon_data.get("longitude", 0.0)

    def _load_planets(self) -> dict[int, dict]:
        """Load planetary positions."""
        planets = {}

        if not FACADE_AVAILABLE:
            # Return mock data if facade not available
            for planet_id in range(1, 10):
                planets[planet_id] = {
                    "longitude": planet_id * 30.0,
                    "latitude": 0.0,
                    "speed": 1.0,
                    "retrograde": False,
                    "sign": planet_id,
                    "nakshatra": planet_id,
                    "house": planet_id,
                    "nl": planet_id,
                    "sl": planet_id,
                    "sl2": planet_id,
                }
            return planets

        for planet_id in range(1, 10):
            try:
                pos = get_positions(self.timestamp, planet_id)
                if pos:
                    planets[planet_id] = {
                        "longitude": pos.longitude,
                        "latitude": pos.latitude,
                        "speed": pos.speed,
                        "retrograde": pos.speed < 0,
                        "sign": int(pos.longitude / 30) + 1,
                        "nakshatra": int(pos.longitude * 27 / 360) + 1,
                        "nl": pos.nl,
                        "sl": pos.sl,
                        "sl2": pos.sl2,
                    }
            except Exception as e:
                logger.debug(f"Could not load planet {planet_id}: {e}")
        return planets

    def _load_houses(self):
        """Load house cusps and ascendant."""
        if not FACADE_AVAILABLE:
            # Return mock house data if facade not available
            self.houses = {i: (i - 1) * 30.0 for i in range(1, 13)}
            self.ascendant = 0.0
            return

        try:
            house_data = get_house_cusps(
                self.timestamp, self.latitude, self.longitude, system="P"  # Placidus
            )
            if house_data:
                self.houses = {i: house_data.houses[i - 1] for i in range(1, 13)}
                self.ascendant = house_data.ascendant

                # Assign planets to houses
                for planet_id, planet_data in self.planets.items():
                    planet_long = planet_data["longitude"]
                    # Find which house the planet is in
                    for house_num in range(1, 13):
                        house_start = self.houses[house_num]
                        house_end = self.houses[house_num % 12 + 1]

                        # Handle wrap-around at 360 degrees
                        if house_start > house_end:
                            if planet_long >= house_start or planet_long < house_end:
                                planet_data["house"] = house_num
                                break
                        else:
                            if house_start <= planet_long < house_end:
                                planet_data["house"] = house_num
                                break
        except Exception as e:
            logger.debug(f"Could not load houses: {e}")
            self.houses = {i: (i - 1) * 30.0 for i in range(1, 13)}
            self.ascendant = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "planets": self.planets,
            "houses": self.houses,
            "ascendant": self.ascendant,
            "moon_longitude": self.moon_longitude,
            "sunrise": self.sunrise.isoformat() if self.sunrise else None,
            "sunset": self.sunset.isoformat() if self.sunset else None,
        }


class AdvisoryService:
    """Service for collecting advisory layers based on feature flags."""

    def __init__(self):
        self.flags = get_feature_flags()
        self.timeout_ms = self.flags.ADVISORY_TIMEOUT_MS
        self._init_modules()

    def _init_modules(self):
        """Initialize enabled modules."""
        self.modules = {}

        # Lazy import based on feature flags
        if self.flags.ENABLE_SHADBALA:
            from modules.vedic_strength.shadbala import compute_shadbala

            self.modules["shadbala"] = compute_shadbala

        if self.flags.ENABLE_KP_RULING_PLANETS:
            from modules.transits.ruling_planets import calculate_ruling_planets

            self.modules["ruling_planets"] = calculate_ruling_planets

        if self.flags.ENABLE_AVASTHAS:
            from modules.vedic_strength.avasthas import compute_avasthas

            self.modules["avasthas"] = compute_avasthas

        if self.flags.ENABLE_ASHTAKAVARGA:
            from modules.vedic_strength.ashtakavarga import compute_bav_sav

            self.modules["ashtakavarga"] = compute_bav_sav

        if self.flags.ENABLE_VEDIC_ASPECTS:
            from modules.aspects.vedic_drsti import calculate_vedic_aspects

            self.modules["vedic_aspects"] = calculate_vedic_aspects

        if self.flags.ENABLE_PANCHANGA_FULL:
            from modules.panchanga.panchanga_full import calculate_enhanced_panchanga

            self.modules["panchanga_full"] = calculate_enhanced_panchanga

        if self.flags.ENABLE_DAILY_WINDOWS:
            from modules.panchanga.daily_windows import calculate_daily_windows

            self.modules["daily_windows"] = calculate_daily_windows

        if self.flags.ENABLE_YOGA_ENGINE:
            from modules.yogas.engine import detect_all_yogas

            self.modules["yoga_engine"] = detect_all_yogas

        # Add Varga (Divisional Charts) module
        if self.flags.ENABLE_VARGA_ADVISORY:
            self.modules["varga"] = self._calculate_varga_advisory

    def _calculate_varga_advisory(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Calculate varga advisory data.

        Args:
            ctx: Advisory context dictionary

        Returns:
            Varga positions, vargottama status, and optional strength
        """
        from datetime import datetime

        from refactor.facade import (
            get_varga_chart,
            get_varga_strength,
            get_vargottama_status,
        )

        timestamp = datetime.fromisoformat(ctx["timestamp"])
        result = {}

        # Calculate enabled vargas
        if hasattr(self.flags, "ENABLED_VARGAS"):
            varga_charts = {}
            for varga_str in self.flags.ENABLED_VARGAS:
                try:
                    divisor = int(
                        varga_str[1:]
                    )  # Extract number from "D9", "D10", etc.
                    chart = get_varga_chart(timestamp, divisor)
                    # Convert 0-11 to 1-12 for display
                    varga_charts[varga_str] = {
                        str(pid): sign + 1 for pid, sign in chart.items()
                    }
                except Exception as e:
                    logger.debug(f"Error calculating {varga_str}: {e}")

            if varga_charts:
                result["charts"] = varga_charts

        # Check vargottama if enabled
        if self.flags.ENABLE_VARGOTTAMA:
            try:
                # Check for commonly important vargas
                check_vargas = (
                    [9, 10, 12]
                    if not hasattr(self.flags, "ENABLED_VARGAS")
                    else [
                        int(v[1:])
                        for v in self.flags.ENABLED_VARGAS
                        if v.startswith("D")
                    ]
                )
                vargottama = get_vargottama_status(timestamp, check_vargas)
                result["vargottama"] = vargottama
            except Exception as e:
                logger.debug(f"Error calculating vargottama: {e}")

        # Calculate Vimshopaka Bala if enabled
        if self.flags.ENABLE_VIMSHOPAKA_BALA:
            try:
                strengths = {}
                for planet_id in range(1, 10):  # All 9 planets
                    strength = get_varga_strength(timestamp, planet_id, "shadvarga")
                    strengths[str(planet_id)] = round(strength, 2)
                result["vimshopaka_bala"] = strengths
            except Exception as e:
                logger.debug(f"Error calculating Vimshopaka Bala: {e}")

        return result if result else None

    def collect_advisory_layers(
        self,
        timestamp: datetime,
        latitude: float = 40.7128,
        longitude: float = -74.0060,
        include_timing: bool = False,
    ) -> dict[str, Any]:
        """Collect all enabled advisory layers.

        Args:
            timestamp: Time for calculations
            latitude: Location latitude
            longitude: Location longitude
            include_timing: Include timing metrics

        Returns:
            Dictionary with advisory data from enabled modules
        """
        # Create context
        ctx = AdvisoryContext(
            timestamp=timestamp, latitude=latitude, longitude=longitude
        )

        result = {
            "timestamp": timestamp.isoformat(),
            "enabled_features": self.flags.enabled_features(),
            "advisory": {},
        }

        if include_timing:
            result["timing"] = {}

        # Collect from each enabled module
        for module_name, module_func in self.modules.items():
            try:
                start_time = time.time()

                # Call module with timeout protection
                module_result = self._call_with_timeout(
                    module_func, ctx.to_dict(), self.timeout_ms / 1000.0
                )

                if module_result:
                    result["advisory"][module_name] = module_result

                if include_timing:
                    elapsed_ms = (time.time() - start_time) * 1000
                    result["timing"][module_name] = round(elapsed_ms, 2)

            except Exception as e:
                logger.error(f"Error in {module_name}: {e}")
                result["advisory"][module_name] = {"error": str(e)}

        # Add core Panchanga if available (already implemented)
        if self.flags.ENABLE_PANCHANGA_FULL and FACADE_AVAILABLE:
            try:
                panchanga = get_lunar_panchanga(timestamp)
                if panchanga:
                    result["advisory"]["panchanga"] = {
                        "tithi": panchanga["tithi"],
                        "nakshatra": panchanga["nakshatra"],
                        "yoga": panchanga["yoga"],
                        "karana": panchanga["karana"],
                        "vara": panchanga["vara"],
                    }
            except Exception as e:
                logger.debug(f"Panchanga not available: {e}")

        return result

    def _call_with_timeout(self, func, args, timeout_seconds):
        """Call function with timeout (simplified version)."""
        # In production, use threading or asyncio for proper timeout
        # For now, just call directly
        return func(args)

    def get_advisory_for_range(
        self,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 60,
        latitude: float = 40.7128,
        longitude: float = -74.0060,
    ) -> list[dict]:
        """Get advisory data for a time range.

        Args:
            start_time: Start of range
            end_time: End of range
            interval_minutes: Sampling interval
            latitude: Location latitude
            longitude: Location longitude

        Returns:
            List of advisory snapshots
        """
        snapshots = []
        current = start_time

        while current <= end_time:
            snapshot = self.collect_advisory_layers(
                current, latitude, longitude, include_timing=False
            )
            snapshots.append(snapshot)

            # Move to next interval
            from datetime import timedelta

            current += timedelta(minutes=interval_minutes)

        return snapshots

    def get_feature_status(self) -> dict[str, Any]:
        """Get current feature flag status.

        Returns:
            Dictionary with feature status
        """
        return {
            "enabled": self.flags.enabled_features(),
            "available": [
                "shadbala",
                "avasthas",
                "ashtakavarga",
                "panchanga_full",
                "hora_windows",
                "daily_windows",
                "tara_bala",
                "planet_friendships",
                "vedic_aspects",
                "eclipse_detector",
                "graha_yuddha",
                "badhaka_maraka",
                "kp_ruling_planets",
                "transit_dasha_confluence",
                "yoga_engine",
                "jaimini",
                "declination_lat_flags",
            ],
            "flags": self.flags.to_dict(),
        }


# Singleton instance
_advisory_service = None


def get_advisory_service() -> AdvisoryService:
    """Get singleton advisory service instance."""
    global _advisory_service
    if _advisory_service is None:
        _advisory_service = AdvisoryService()
    return _advisory_service
