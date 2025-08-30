#!/usr/bin/env python3
"""
KP Eclipse System Adapter
Provides eclipse prediction through SystemAdapter interface
"""

import logging

from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any

from app.services.cache_service import CacheService
from interfaces.system_adapter import BaseSystemAdapter, SystemChange, SystemSnapshot
from refactor.eclipse import (
    EclipseEvent,
    lunar_events_between,
    lunar_visibility,
    next_eclipse,
    solar_events_between,
    solar_path,
    solar_visibility,
)
from refactor.eclipse_config import EclipseConfig
from refactor.monitoring import track_computation

logger = logging.getLogger(__name__)


class KPEclipseAdapter(BaseSystemAdapter):
    """
    KP Eclipse prediction adapter implementation
    """

    def __init__(self, cache_service: CacheService | None = None):
        super().__init__("KP_ECLIPSE", "1.0.0")
        self.cache_service = cache_service
        self.config = EclipseConfig()
        logger.info(f"KPEclipseAdapter initialized with config: {self.config}")

    @property
    def description(self) -> str:
        return "KP Eclipse Prediction System (Solar & Lunar)"

    def snapshot(self, ts_utc: datetime) -> SystemSnapshot:
        """
        Get eclipse state at a specific timestamp
        Finds active or nearest eclipse events
        """
        # Find eclipses around this time (±30 days)
        start = ts_utc - timedelta(days=30)
        end = ts_utc + timedelta(days=30)

        solar_events = solar_events_between(start, end, self.config)
        lunar_events = lunar_events_between(start, end, self.config)

        # Find nearest eclipse
        all_events = solar_events + lunar_events
        nearest = None
        min_diff = float("inf")

        for event in all_events:
            diff = abs((event.peak_utc - ts_utc).total_seconds())
            if diff < min_diff:
                min_diff = diff
                nearest = event

        data = {
            "timestamp": ts_utc.isoformat(),
            "nearest_eclipse": self._event_to_dict(nearest) if nearest else None,
            "solar_count": len(solar_events),
            "lunar_count": len(lunar_events),
            "window_days": 30,
        }

        return SystemSnapshot(
            system=self.system,
            timestamp=ts_utc,
            data=data,
            metadata={"config": asdict(self.config)},
        )

    def changes(self, day_utc: date) -> list[SystemChange]:
        """
        Get eclipse events for a given day
        """
        start = datetime.combine(day_utc, datetime.min.time()).replace(tzinfo=None)
        end = start + timedelta(days=1)

        changes = []

        # Find solar eclipses
        for event in solar_events_between(start, end, self.config):
            changes.append(
                SystemChange(
                    system=self.system,
                    timestamp=event.peak_utc,
                    change_type="solar_eclipse",
                    from_value=None,
                    to_value=event.classification,
                    entity="Sun",
                    metadata=self._event_to_dict(event),
                )
            )

        # Find lunar eclipses
        for event in lunar_events_between(start, end, self.config):
            changes.append(
                SystemChange(
                    system=self.system,
                    timestamp=event.peak_utc,
                    change_type="lunar_eclipse",
                    from_value=None,
                    to_value=event.classification,
                    entity="Moon",
                    metadata=self._event_to_dict(event),
                )
            )

        return sorted(changes, key=lambda x: x.timestamp)

    def calculate(self, ts_utc: datetime, entity: str, **kwargs) -> dict[str, Any]:
        """
        Perform eclipse-specific calculations

        Entities:
        - 'events': Find eclipses in range
        - 'visibility': Check local visibility
        - 'path': Get solar eclipse path
        - 'next': Find next eclipse
        """
        if entity == "events":
            return self._calculate_events(ts_utc, **kwargs)
        elif entity == "visibility":
            return self._calculate_visibility(ts_utc, **kwargs)
        elif entity == "path":
            return self._calculate_path(ts_utc, **kwargs)
        elif entity == "next":
            return self._calculate_next(ts_utc, **kwargs)
        else:
            raise ValueError(f"Unknown entity: {entity}")

    def _calculate_events(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """
        Find eclipses in time range
        """
        end_utc = kwargs.get("end_utc", ts_utc + timedelta(days=365))
        eclipse_type = kwargs.get("eclipse_type", "both")

        result = {"start": ts_utc.isoformat(), "end": end_utc.isoformat()}

        if eclipse_type in ["solar", "both"]:
            with track_computation("eclipse_solar_search"):
                solar = solar_events_between(ts_utc, end_utc, self.config)
                result["solar"] = [self._event_to_dict(e) for e in solar]

        if eclipse_type in ["lunar", "both"]:
            with track_computation("eclipse_lunar_search"):
                lunar = lunar_events_between(ts_utc, end_utc, self.config)
                result["lunar"] = [self._event_to_dict(e) for e in lunar]

        return result

    def _calculate_visibility(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """
        Check local visibility of eclipse
        """
        lat = kwargs.get("lat")
        lon = kwargs.get("lon")
        eclipse_type = kwargs.get("eclipse_type", "solar")

        if lat is None or lon is None:
            raise ValueError("lat and lon required for visibility")

        # Find eclipse at this time
        window = timedelta(hours=6)
        events = []

        if eclipse_type == "solar":
            events = solar_events_between(ts_utc - window, ts_utc + window, self.config)
        else:
            events = lunar_events_between(ts_utc - window, ts_utc + window, self.config)

        if not events:
            return {
                "visible": False,
                "reason": f"No {eclipse_type} eclipse within ±6 hours",
            }

        # Check visibility of nearest eclipse
        event = min(events, key=lambda e: abs((e.peak_utc - ts_utc).total_seconds()))

        with track_computation("eclipse_visibility_check"):
            if eclipse_type == "solar":
                visibility = solar_visibility(event, lat, lon, self.config)
            else:
                visibility = lunar_visibility(event, lat, lon, self.config)

        return {
            "eclipse": self._event_to_dict(event),
            "visibility": asdict(visibility) if visibility else None,
            "location": {"lat": lat, "lon": lon},
        }

    def _calculate_path(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """
        Get solar eclipse path
        """
        # Find solar eclipse near this time
        window = timedelta(days=1)
        events = solar_events_between(ts_utc - window, ts_utc + window, self.config)

        if not events:
            return {"found": False, "reason": "No solar eclipse within ±1 day"}

        # Get path of nearest eclipse
        event = min(events, key=lambda e: abs((e.peak_utc - ts_utc).total_seconds()))

        # Only total/annular/hybrid have central paths
        if event.classification not in ["total", "annular", "hybrid"]:
            return {
                "found": False,
                "reason": f"{event.classification} eclipse has no central path",
                "eclipse": self._event_to_dict(event),
            }

        with track_computation("eclipse_path_calculation"):
            path = solar_path(event, self.config)

        if path:
            return {
                "found": True,
                "eclipse": self._event_to_dict(event),
                "path": {
                    "central_line": path.central_line,
                    "northern_limit": path.northern_limit,
                    "southern_limit": path.southern_limit,
                    "max_width_km": path.max_width_km,
                    "timestamps": [t.isoformat() for t in path.timestamps],
                },
            }
        else:
            return {
                "found": False,
                "reason": "Path calculation failed",
                "eclipse": self._event_to_dict(event),
            }

    def _calculate_next(self, ts_utc: datetime, **kwargs) -> dict[str, Any]:
        """
        Find next eclipse of specified type
        """
        eclipse_type = kwargs.get("eclipse_type", "any")
        classification = kwargs.get("classification")

        with track_computation("eclipse_next_search"):
            event = next_eclipse(
                ts_utc,
                eclipse_type=eclipse_type,
                classification=classification,
                cfg=self.config,
            )

        if event:
            return {
                "found": True,
                "eclipse": self._event_to_dict(event),
                "days_until": (event.peak_utc - ts_utc).days,
            }
        else:
            return {
                "found": False,
                "search_params": {
                    "eclipse_type": eclipse_type,
                    "classification": classification,
                },
            }

    def _event_to_dict(self, event: EclipseEvent) -> dict[str, Any]:
        """
        Convert EclipseEvent to dictionary
        """
        if not event:
            return None

        return {
            "kind": event.kind,
            "classification": event.classification,
            "peak_utc": event.peak_utc.isoformat(),
            "magnitude": event.magnitude,
            "saros": event.saros,
            "gamma": event.gamma,
            "duration_minutes": event.duration_minutes,
            "contacts": (
                {k: v.isoformat() for k, v in event.contacts.items()}
                if event.contacts
                else {}
            ),
            "meta": event.meta,
        }

    def get_metadata(self) -> dict[str, Any]:
        """
        Get adapter metadata and configuration
        """
        meta = super().get_metadata()
        meta.update(
            {
                "config": asdict(self.config),
                "capabilities": {
                    "solar_eclipse": True,
                    "lunar_eclipse": True,
                    "local_visibility": True,
                    "central_path": True,
                    "contact_times": True,
                    "saros_series": True,
                },
                "performance": {
                    "search_step_days": self.config.search_step_days,
                    "path_sampling_km": self.config.path_sampling_km,
                    "max_span_years": self.config.max_span_years,
                },
            }
        )
        return meta


# Register adapter
def register_eclipse_adapter(cache_service: CacheService | None = None):
    """
    Register KP Eclipse adapter with system registry
    """
    from interfaces import system_registry

    adapter = KPEclipseAdapter(cache_service)
    system_registry.register_adapter(adapter)
    logger.info(f"Registered {adapter.system} adapter")
    return adapter
