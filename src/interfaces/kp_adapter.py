#!/usr/bin/env python3
"""
KP System Adapter - Wraps existing KP facade for plugin architecture
Maintains 100% backward compatibility while enabling multi-system support
"""

import logging

from datetime import UTC, date, datetime, timedelta
from typing import Any

from refactor import facade
from refactor.constants import FINANCE_LATENCY_SECONDS
from refactor.monitoring import timed

from .system_adapter import BaseSystemAdapter, SystemChange, SystemSnapshot

logger = logging.getLogger(__name__)


class KPSystemAdapter(BaseSystemAdapter):
    """
    Adapter for Krishnamurti Paddhati (KP) astrological system
    Wraps the existing refactor.facade module to maintain compatibility
    """

    def __init__(self):
        super().__init__(system="KP", version="1.0.0")
        # Use planet IDs from constants.py - NEVER hardcode!
        from refactor.constants import PLANET_NAMES

        self._planets = PLANET_NAMES  # Maps 1-9 to correct names

    @property
    def description(self) -> str:
        return "Krishnamurti Paddhati - Sub-lord based astrological system"

    @timed("kp_adapter.snapshot")
    def snapshot(self, ts_utc: datetime) -> SystemSnapshot:
        """
        Get complete KP system state at a timestamp

        Args:
            ts_utc: UTC timestamp for calculation

        Returns:
            SystemSnapshot with all planetary positions and KP lords
        """
        # Ensure UTC
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=UTC)

        snapshot_data = {}

        # Get positions for all planets
        for planet_id, planet_name in self._planets.items():
            try:
                # Skip unsupported planets
                if planet_id not in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
                    continue

                position_data = facade.get_positions(ts_utc, planet_id)

                # Extract KP chain data from PlanetData object
                kp_data = {
                    "longitude": position_data.position,  # position field holds longitude
                    "latitude": position_data.dec,  # declination
                    "speed": position_data.speed,
                    "sign": position_data.sign,
                    "nakshatra": position_data.nakshatra,
                    "pada": position_data.pada,
                    "NL": position_data.nl,  # lowercase fields
                    "SL": position_data.sl,
                    "SL2": position_data.sl2,
                }

                snapshot_data[planet_name] = kp_data

            except Exception as e:
                logger.error(f"Error getting position for {planet_name}: {e}")
                snapshot_data[planet_name] = {"error": str(e)}

        # Add metadata
        metadata = {
            "ayanamsa": "KRISHNAMURTI",
            "node_type": "TRUE_NODE",
            "finance_offset": FINANCE_LATENCY_SECONDS,
            "calculation_time": datetime.now(UTC).isoformat(),
        }

        return SystemSnapshot(
            system="KP", timestamp=ts_utc, data=snapshot_data, metadata=metadata
        )

    @timed("kp_adapter.changes")
    def changes(self, day_utc: date) -> list[SystemChange]:
        """
        Get all KP lord changes for a given day

        Args:
            day_utc: UTC date for which to find changes

        Returns:
            List of SystemChange objects for lord changes
        """
        # Convert date to datetime range
        start_time = datetime.combine(day_utc, datetime.min.time()).replace(tzinfo=UTC)
        end_time = start_time + timedelta(days=1)

        changes_list = []

        # Get changes for each planet
        for planet_id, planet_name in self._planets.items():
            try:
                # Use facade to get lord changes
                planet_changes = facade.get_kp_lord_changes(
                    start_time, end_time, planet_id=planet_id
                )

                # Convert to SystemChange objects
                for change in planet_changes:
                    system_change = SystemChange(
                        system="KP",
                        timestamp=change["timestamp"],
                        change_type=change["change_type"],
                        from_value=change["from_lord"],
                        to_value=change["to_lord"],
                        entity=planet_name,
                        metadata={
                            "planet_id": planet_id,
                            "longitude": change.get("longitude"),
                            "level": change.get("level", "NL"),
                        },
                    )
                    changes_list.append(system_change)

            except Exception as e:
                logger.error(f"Error getting changes for {planet_name}: {e}")

        # Sort by timestamp
        changes_list.sort(key=lambda x: x.timestamp)

        return changes_list

    @timed("kp_adapter.calculate")
    def calculate(self, ts_utc: datetime, entity: str, **kwargs) -> dict[str, Any]:
        """
        Perform KP-specific calculation

        Args:
            ts_utc: UTC timestamp for calculation
            entity: Planet name or ID
            **kwargs: Additional parameters (apply_offset, levels, etc.)

        Returns:
            Dictionary with calculation results
        """
        # Map entity to planet_id
        planet_id = None
        if isinstance(entity, int):
            planet_id = entity
        elif isinstance(entity, str):
            # Reverse lookup
            for pid, pname in self._planets.items():
                if pname.lower() == entity.lower():
                    planet_id = pid
                    break

        if planet_id is None:
            raise ValueError(f"Unknown entity: {entity}")

        # Get apply_offset flag
        apply_offset = kwargs.get("apply_offset", False)

        # Calculate using facade
        position_data = facade.get_positions(ts_utc, planet_id, apply_offset)

        # Convert PlanetData to dictionary
        result = {
            "longitude": position_data.position,
            "latitude": position_data.dec,
            "speed": position_data.speed,
            "sign": position_data.sign,
            "nakshatra": position_data.nakshatra,
            "pada": position_data.pada,
            "NL": position_data.nl,
            "SL": position_data.sl,
            "SL2": position_data.sl2,
        }

        # Add any additional calculations requested
        if kwargs.get("include_houses"):
            # Future: Add house calculations
            pass

        if kwargs.get("include_aspects"):
            # Future: Add aspect calculations
            pass

        return result

    def validate_input(self, entity: str, **kwargs) -> bool:
        """
        Validate KP system input parameters

        Args:
            entity: Planet name or ID to validate
            **kwargs: Additional parameters to validate

        Returns:
            True if valid

        Raises:
            ValueError: If invalid
        """
        # Check entity
        valid_entity = False
        if isinstance(entity, int):
            valid_entity = entity in self._planets
        elif isinstance(entity, str):
            valid_entity = any(
                p.lower() == entity.lower() for p in self._planets.values()
            )

        if not valid_entity:
            raise ValueError(f"Invalid entity for KP system: {entity}")

        # Validate timestamp if provided
        if "timestamp" in kwargs:
            ts = kwargs["timestamp"]
            if not isinstance(ts, datetime):
                raise ValueError("Timestamp must be a datetime object")

            # Check reasonable date range
            min_date = datetime(1900, 1, 1, tzinfo=UTC)
            max_date = datetime(2100, 1, 1, tzinfo=UTC)
            if ts < min_date or ts > max_date:
                raise ValueError(f"Timestamp out of range: {ts}")

        return True

    def get_metadata(self) -> dict[str, Any]:
        """
        Get KP system metadata

        Returns:
            Dictionary with system configuration and capabilities
        """
        base_metadata = super().get_metadata()

        kp_metadata = {
            "ayanamsa": "KRISHNAMURTI",
            "ayanamsa_id": 5,
            "node_type": "TRUE_NODE",
            "node_id": 11,
            "planets": self._planets,
            "nakshatras": 27,
            "sub_lords": 249,
            "sub_sub_lords": 2193,
            "finance_offset_seconds": FINANCE_LATENCY_SECONDS,
            "supported_calculations": [
                "positions",
                "kp_lords",
                "lord_changes",
                "snapshot",
            ],
            "future_capabilities": ["houses", "aspects", "dashas", "transits"],
        }

        return {**base_metadata, **kp_metadata}


# Auto-register KP adapter when module is imported
def register_kp_adapter():
    """Register the KP adapter with the global registry"""
    try:
        from .registry import register_system

        adapter = KPSystemAdapter()
        register_system(adapter)
        logger.info("KP system adapter registered successfully")
        return adapter
    except Exception as e:
        logger.error(f"Failed to register KP adapter: {e}")
        return None
