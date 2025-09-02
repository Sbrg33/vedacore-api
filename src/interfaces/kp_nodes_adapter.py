#!/usr/bin/env python3
"""
KP Nodes System Adapter - Node perturbation and stationary detection via SystemAdapter interface.
Provides events and state queries for Rahu/Ketu (True Nodes).
"""

import logging

from datetime import UTC, date, datetime, timedelta
from typing import Any

from refactor.nodes import NodePerturbationCalculator
from refactor.nodes_config import get_node_config
from refactor.time_utils import validate_utc_datetime

logger = logging.getLogger(__name__)


class KPNodesAdapter:
    """
    Adapter for KP Nodes calculations following SystemAdapter protocol.
    Provides node events (stationary, direction changes) and current state.
    """

    def __init__(self, ephe_path: str = "./swisseph/ephe"):
        """
        Initialize KP Nodes adapter.

        Args:
            ephe_path: Path to Swiss Ephemeris data files
        """
        self.system = "KP_NODES"
        self.calculator = NodePerturbationCalculator(ephe_path)
        self.config = get_node_config()
        logger.info(f"KPNodesAdapter initialized for {self.system}")

    def snapshot(self, ts_utc: datetime) -> dict[str, Any]:
        """
        Get current node state at timestamp.

        Args:
            ts_utc: Reference timestamp (UTC)

        Returns:
            Dict with current node state and metadata
        """
        ts_utc = validate_utc_datetime(ts_utc)

        # Get current state
        state = self.calculator.get_node_state(ts_utc)

        # Format response
        result = {
            "system": self.system,
            "timestamp": state.timestamp.isoformat(),
            "longitude": state.longitude,
            "speed": state.speed,
            "direction": state.direction,
            "stationary": state.is_stationary,
            "meta": {
                "adapter": self.system,
                "version": "1.0.0",
                "ayanamsa": "Krishnamurti",
                "node": "True Node (Rahu)",
                "speed_threshold": self.config.speed_threshold,
                "hysteresis_enabled": self.config.enable_hysteresis,
            },
        }

        # Add optional diagnostics
        if state.solar_elongation is not None:
            result["solar_elongation"] = state.solar_elongation
            result["meta"]["diagnostics_enabled"] = True

        # Add Ketu position (180° opposite)
        result["ketu_longitude"] = (state.longitude + 180.0) % 360.0

        return result

    def changes(self, day_utc: date) -> list[dict[str, Any]]:
        """
        Get all node events on a given day.

        Args:
            day_utc: Date to check for events (UTC)

        Returns:
            List of node event dictionaries
        """
        # Convert date to datetime range
        start_time = datetime(
            day_utc.year, day_utc.month, day_utc.day, 0, 0, 0, tzinfo=UTC
        )
        end_time = start_time + timedelta(days=1)

        # Get events for the day
        events = self.calculator.detect_events(start_time, end_time)

        # Convert to dictionaries
        result = []
        for event in events:
            event_dict = event.to_dict()
            event_dict["system"] = self.system
            event_dict["date"] = day_utc.isoformat()
            result.append(event_dict)

        return result

    def get_events(
        self, start_time: datetime, end_time: datetime
    ) -> list[dict[str, Any]]:
        """
        Get all node events in a time range.

        Args:
            start_time: Start of search period (UTC)
            end_time: End of search period (UTC)

        Returns:
            List of node event dictionaries
        """
        start_time = validate_utc_datetime(start_time)
        end_time = validate_utc_datetime(end_time)

        # Get events
        events = self.calculator.detect_events(start_time, end_time)

        # Convert to dictionaries
        result = []
        for event in events:
            event_dict = event.to_dict()
            event_dict["system"] = self.system
            result.append(event_dict)

        return result

    def get_current_state(self, ts_utc: datetime | None = None) -> dict[str, Any]:
        """
        Get current node state (live calculation).

        Args:
            ts_utc: Timestamp (default: now)

        Returns:
            Current state dictionary
        """
        if ts_utc is None:
            ts_utc = datetime.now(UTC)
        else:
            ts_utc = validate_utc_datetime(ts_utc)

        state = self.calculator.get_node_state(ts_utc)

        return {
            "timestamp": state.timestamp.isoformat(),
            "speed": state.speed,
            "direction": state.direction,
            "stationary": state.is_stationary,
            "longitude": state.longitude,
            "ketu_longitude": (state.longitude + 180.0) % 360.0,
            "solar_elongation": state.solar_elongation,
            "meta": {"ayanamsa": "Krishnamurti", "system": self.system},
        }

    def find_next_event(
        self,
        from_time: datetime | None = None,
        event_type: str | None = None,
        max_days: int = 30,
    ) -> dict[str, Any] | None:
        """
        Find the next node event.

        Args:
            from_time: Start searching from this time (default: now)
            event_type: Specific event type to find (optional)
            max_days: Maximum days to search forward

        Returns:
            Next event dictionary or None
        """
        if from_time is None:
            from_time = datetime.now(UTC)
        else:
            from_time = validate_utc_datetime(from_time)

        event = self.calculator.find_next_event(from_time, event_type, max_days)

        if event:
            event_dict = event.to_dict()
            event_dict["system"] = self.system
            return event_dict

        return None

    def get_statistics(
        self, start_time: datetime, end_time: datetime
    ) -> dict[str, Any]:
        """
        Get statistics about node events in a period.

        Args:
            start_time: Start of analysis period
            end_time: End of analysis period

        Returns:
            Statistics dictionary
        """
        start_time = validate_utc_datetime(start_time)
        end_time = validate_utc_datetime(end_time)

        events = self.calculator.detect_events(start_time, end_time)

        # Count events by type
        event_counts = {}
        for event in events:
            event_type = event.event_type
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        # Calculate average speeds
        speeds = [abs(e.speed) for e in events]
        avg_speed = sum(speeds) / len(speeds) if speeds else 0

        # Find min/max speeds
        min_speed = min(speeds) if speeds else 0
        max_speed = max(speeds) if speeds else 0

        return {
            "system": self.system,
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "days": (end_time - start_time).days,
            },
            "event_counts": event_counts,
            "total_events": len(events),
            "speed_stats": {
                "average": round(avg_speed, 6),
                "minimum": round(min_speed, 6),
                "maximum": round(max_speed, 6),
            },
            "config": {
                "speed_threshold": self.config.speed_threshold,
                "hysteresis": self.config.enable_hysteresis,
                "wobble_detection": self.config.enable_wobble_detection,
                "diagnostics": self.config.enable_diagnostics,
            },
        }


# Module-level instance
_adapter = None


def get_kp_nodes_adapter(ephe_path: str = "./swisseph/ephe") -> KPNodesAdapter:
    """Get or create singleton KP Nodes adapter instance"""
    global _adapter
    if _adapter is None:
        _adapter = KPNodesAdapter(ephe_path)
    return _adapter
