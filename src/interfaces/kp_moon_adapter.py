#!/usr/bin/env python3
"""
KP Moon Factors System Adapter - Phase 7
Provides moon factors and anomaly detection through SystemAdapter interface
"""

import logging

from datetime import date, datetime, timedelta
from typing import Any

from app.services.cache_service import CacheService
from interfaces.system_adapter import BaseSystemAdapter, SystemChange, SystemSnapshot
from refactor.monitoring import track_computation
from refactor.moon_config import MoonConfig
from refactor.moon_factors_enhanced import (
    EnhancedMoonCalculator,
)

logger = logging.getLogger(__name__)


class KPMoonAdapter(BaseSystemAdapter):
    """
    KP Moon factors adapter implementation
    """

    def __init__(self, cache_service: CacheService | None = None):
        super().__init__("KP_MOON", "1.0.0")
        self.cache_service = cache_service
        self.config = MoonConfig()
        self.calculator = EnhancedMoonCalculator(self.config)
        logger.info(f"KPMoonAdapter initialized with config: {self.config}")

    @property
    def description(self) -> str:
        return "KP Moon Factors System with Phase 7 enhancements"

    def snapshot(self, ts_utc: datetime) -> SystemSnapshot:
        """
        Get moon factor state at a specific timestamp
        """
        with track_computation("moon_snapshot"):
            profile = self.calculator.calculate_profile(ts_utc)

            data = {
                "timestamp": ts_utc.isoformat(),
                "profile": profile.to_dict(),
                "basic_factors": {
                    "longitude": profile.basic_factors.longitude,
                    "latitude": profile.basic_factors.latitude,
                    "speed": profile.basic_factors.speed,
                    "distance": profile.basic_factors.distance,
                    "declination": profile.basic_factors.declination,
                },
            }

            return SystemSnapshot(
                system=self.system,
                timestamp=ts_utc,
                data=data,
                metadata={
                    "config": {
                        "mean_speed": self.config.mean_speed,
                        "max_latitude": self.config.max_latitude,
                    }
                },
            )

    def changes(self, day_utc: date) -> list[SystemChange]:
        """
        Get moon events for a given day
        """
        from zoneinfo import ZoneInfo

        UTC = ZoneInfo("UTC")
        start = datetime.combine(day_utc, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)

        changes = []

        with track_computation("moon_changes"):
            # Find events
            events = self.calculator.find_events(start, end)

            for event in events:
                changes.append(
                    SystemChange(
                        system=self.system,
                        timestamp=event.timestamp,
                        change_type=event.event_type,
                        from_value=None,
                        to_value=event.value,
                        entity="Moon",
                        metadata=event.metadata,
                    )
                )

            # Add tithi changes
            changes.extend(self._find_tithi_changes(start, end))

            # Add nakshatra changes
            changes.extend(self._find_nakshatra_changes(start, end))

        return sorted(changes, key=lambda x: x.timestamp)

    def calculate(self, ts_utc: datetime, entity: str, **kwargs) -> dict[str, Any]:
        """
        Perform moon-specific calculations

        Entities:
        - 'profile': Full moon profile with indices
        - 'events': Find events in range
        - 'strength': Calculate strength at time
        - 'panchanga': Get panchanga elements
        """
        if entity == "profile":
            return self._calculate_profile(ts_utc, **kwargs)
        elif entity == "events":
            return self._calculate_events(ts_utc, **kwargs)
        elif entity == "strength":
            return self._calculate_strength(ts_utc, **kwargs)
        elif entity == "panchanga":
            return self._calculate_panchanga(ts_utc, **kwargs)
        else:
            raise ValueError(f"Unknown entity: {entity}")

    def _calculate_profile(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """Calculate full moon profile"""
        with track_computation("moon_profile"):
            profile = self.calculator.calculate_profile(ts_utc)
            return profile.to_dict()

    def _calculate_events(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """Find moon events in range"""
        end_utc = kwargs.get("end_utc", ts_utc + timedelta(days=30))
        event_types = kwargs.get("event_types", ["perigee", "apogee", "standstill"])

        with track_computation("moon_events"):
            events = self.calculator.find_events(ts_utc, end_utc, event_types)

            return {
                "start": ts_utc.isoformat(),
                "end": end_utc.isoformat(),
                "events": [
                    {
                        "type": e.event_type,
                        "timestamp": e.timestamp.isoformat(),
                        "value": e.value,
                        "metadata": e.metadata,
                    }
                    for e in events
                ],
            }

    def _calculate_strength(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """Calculate moon strength"""
        with track_computation("moon_strength"):
            profile = self.calculator.calculate_profile(ts_utc)

            return {
                "timestamp": ts_utc.isoformat(),
                "strength": profile.strength,
                "strength_score": profile.strength_score,
                "velocity_index": profile.velocity_index,
                "latitude_index": profile.latitude_index,
                "distance_index": profile.distance_index,
                "anomalies": {
                    "is_perigee": profile.is_perigee,
                    "is_apogee": profile.is_apogee,
                    "is_standstill": profile.is_standstill,
                    "is_fast_moon": profile.is_fast_moon,
                    "is_slow_moon": profile.is_slow_moon,
                },
            }

    def _calculate_panchanga(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """Get panchanga elements"""
        with track_computation("moon_panchanga"):
            profile = self.calculator.calculate_profile(ts_utc)
            basic = profile.basic_factors

            return {
                "timestamp": ts_utc.isoformat(),
                "tithi": basic.tithi,
                "tithi_num": basic.tithi_num,
                "tithi_percent": basic.tithi_percent,
                "paksha": "Shukla" if basic.is_waxing else "Krishna",
                "nakshatra": basic.nakshatra,
                "nakshatra_num": basic.nakshatra_num,
                "pada": basic.pada,
                "yoga": basic.yoga,
                "yoga_num": basic.yoga_num,
                "karana": basic.karana,
                "karana_num": basic.karana_num,
            }

    def _find_tithi_changes(self, start: datetime, end: datetime) -> list[SystemChange]:
        """Find tithi changes in range"""
        changes = []
        current = start
        step = timedelta(hours=1)
        prev_tithi = None

        while current <= end:
            profile = self.calculator.calculate_profile(current)
            tithi = profile.basic_factors.tithi_num

            if prev_tithi is not None and tithi != prev_tithi:
                changes.append(
                    SystemChange(
                        system=self.system,
                        timestamp=current,
                        change_type="tithi_change",
                        from_value=prev_tithi,
                        to_value=tithi,
                        entity="Tithi",
                        metadata={"tithi_name": profile.basic_factors.tithi},
                    )
                )

            prev_tithi = tithi
            current += step

        return changes

    def _find_nakshatra_changes(
        self, start: datetime, end: datetime
    ) -> list[SystemChange]:
        """Find nakshatra changes in range"""
        changes = []
        current = start
        step = timedelta(hours=1)
        prev_nakshatra = None

        while current <= end:
            profile = self.calculator.calculate_profile(current)
            nakshatra = profile.basic_factors.nakshatra_num

            if prev_nakshatra is not None and nakshatra != prev_nakshatra:
                changes.append(
                    SystemChange(
                        system=self.system,
                        timestamp=current,
                        change_type="nakshatra_change",
                        from_value=prev_nakshatra,
                        to_value=nakshatra,
                        entity="Nakshatra",
                        metadata={"nakshatra_name": profile.basic_factors.nakshatra},
                    )
                )

            prev_nakshatra = nakshatra
            current += step

        return changes

    def get_metadata(self) -> dict[str, Any]:
        """Get adapter metadata and configuration"""
        meta = super().get_metadata()
        meta.update(
            {
                "config": {
                    "mean_speed": self.config.mean_speed,
                    "max_latitude": self.config.max_latitude,
                    "perigee_threshold": self.config.perigee_threshold,
                    "apogee_threshold": self.config.apogee_threshold,
                    "search_step_hours": self.config.event_search_step_hours,
                },
                "capabilities": {
                    "moon_profile": True,
                    "velocity_index": True,
                    "latitude_index": True,
                    "distance_index": True,
                    "perigee_apogee": True,
                    "standstill_detection": True,
                    "panchanga": True,
                    "tithi_tracking": True,
                    "nakshatra_tracking": True,
                },
                "performance": {
                    "profile_calculation": "<10ms",
                    "event_search_year": "<200ms",
                    "cache_ttl_days": self.config.cache_ttl_profile_days,
                },
            }
        )
        return meta


# Register adapter
def register_moon_adapter(cache_service: CacheService | None = None):
    """
    Register KP Moon adapter with system registry
    """
    from interfaces import system_registry

    adapter = KPMoonAdapter(cache_service)
    system_registry.register_adapter(adapter)
    logger.info(f"Registered {adapter.system} adapter")
    return adapter
