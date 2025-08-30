#!/usr/bin/env python3
"""
Advanced node calculations for Rahu/Ketu (True Nodes).
Detects stationary windows, direction changes, and perturbations.
Research-grade, production-safe implementation.
"""

import logging

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import swisseph as swe

from refactor.nodes_config import get_node_config
from refactor.time_utils import validate_utc_datetime

logger = logging.getLogger(__name__)

# Swiss Ephemeris True Node ID
TRUE_NODE_ID = 11  # Rahu (True North Node)
# Ketu = Rahu + 180°


@dataclass
class NodeEvent:
    """Represents a node event (stationary, direction change, etc.)"""

    event_type: (
        str  # 'stationary_start', 'stationary_end', 'direction_change', 'wobble_peak'
    )
    timestamp: datetime
    speed: float  # Degrees per day at event time
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "speed": round(self.speed, 6),
        }
        # Add relevant metadata
        if self.event_type == "direction_change":
            result["from"] = self.metadata.get("from_direction")
            result["to"] = self.metadata.get("to_direction")
        elif self.event_type == "wobble_peak":
            result["amplitude"] = self.metadata.get("amplitude", abs(self.speed))
        elif self.event_type in ["stationary_start", "stationary_end"]:
            result["threshold"] = self.metadata.get("threshold")

        # Add optional diagnostics if enabled
        if "solar_elongation" in self.metadata:
            result["solar_elongation"] = self.metadata["solar_elongation"]
        if "proximity_bands" in self.metadata:
            result["proximity_bands"] = self.metadata["proximity_bands"]

        return result


@dataclass
class NodeState:
    """Current state of the nodes"""

    timestamp: datetime
    longitude: float  # Rahu longitude in degrees
    speed: float  # Degrees per day
    direction: str  # 'direct' or 'retro'
    is_stationary: bool
    solar_elongation: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "longitude": round(self.longitude, 6),
            "speed": round(self.speed, 6),
            "direction": self.direction,
            "stationary": self.is_stationary,
            "solar_elongation": (
                round(self.solar_elongation, 2) if self.solar_elongation else None
            ),
        }


class NodePerturbationCalculator:
    """
    Production-grade calculator for lunar node events.
    Detects stationary windows, direction changes, and perturbations.
    """

    def __init__(self, ephe_path: str = "./swisseph/ephe"):
        """
        Initialize node calculator.

        Args:
            ephe_path: Path to Swiss Ephemeris data files
        """
        swe.set_ephe_path(ephe_path)
        swe.set_sid_mode(5)  # KP ayanamsa for consistency
        self.config = get_node_config()
        logger.info(
            f"NodePerturbationCalculator initialized with config: {self.config.to_dict()}"
        )

    def _get_node_position(self, ts_utc: datetime) -> tuple[float, float]:
        """
        Get True Node position and speed at given time.

        Args:
            ts_utc: UTC timestamp

        Returns:
            Tuple of (longitude, speed) in degrees and degrees/day
        """
        ts_utc = validate_utc_datetime(ts_utc)

        # Convert to Julian day
        jd = swe.julday(
            ts_utc.year,
            ts_utc.month,
            ts_utc.day,
            ts_utc.hour + ts_utc.minute / 60.0 + ts_utc.second / 3600.0,
        )

        # Get True Node position (sidereal)
        result = swe.calc_ut(jd, TRUE_NODE_ID, swe.FLG_SIDEREAL | swe.FLG_SPEED)

        longitude = result[0][0]  # Sidereal longitude
        speed = result[0][3]  # Speed in degrees/day

        return longitude, speed

    def _get_sun_position(self, ts_utc: datetime) -> float:
        """Get Sun's sidereal longitude for elongation calculation"""
        ts_utc = validate_utc_datetime(ts_utc)

        jd = swe.julday(
            ts_utc.year,
            ts_utc.month,
            ts_utc.day,
            ts_utc.hour + ts_utc.minute / 60.0 + ts_utc.second / 3600.0,
        )

        # Sun ID = 0 in Swiss Ephemeris
        result = swe.calc_ut(jd, 0, swe.FLG_SIDEREAL)
        return result[0][0]

    def _calculate_solar_elongation(self, node_lon: float, sun_lon: float) -> float:
        """Calculate angular separation between node and Sun"""
        diff = abs(node_lon - sun_lon)
        if diff > 180:
            diff = 360 - diff
        return diff

    def _bisect_event(
        self,
        start_time: datetime,
        end_time: datetime,
        condition_func,
        max_iters: int | None = None,
    ) -> datetime:
        """
        Bisection search to refine event time.

        Args:
            start_time: Start of search interval
            end_time: End of search interval
            condition_func: Function that returns True/False for the condition
            max_iters: Maximum iterations (default from config)

        Returns:
            Refined timestamp of event
        """
        if max_iters is None:
            max_iters = self.config.bisection_max_iters

        tolerance = timedelta(seconds=self.config.bisection_tolerance_seconds)

        for _ in range(max_iters):
            if end_time - start_time <= tolerance:
                break

            mid_time = start_time + (end_time - start_time) / 2

            if condition_func(mid_time):
                end_time = mid_time
            else:
                start_time = mid_time

        return start_time + (end_time - start_time) / 2

    def get_node_state(self, ts_utc: datetime) -> NodeState:
        """
        Get current state of the nodes.

        Args:
            ts_utc: UTC timestamp

        Returns:
            NodeState with current position, speed, and flags
        """
        ts_utc = validate_utc_datetime(ts_utc)

        # Get node position and speed
        longitude, speed = self._get_node_position(ts_utc)

        # Determine direction
        direction = "direct" if speed >= 0 else "retro"

        # Check if stationary
        is_stationary = abs(speed) < self.config.speed_threshold

        # Calculate solar elongation if diagnostics enabled
        solar_elongation = None
        if self.config.enable_diagnostics:
            sun_lon = self._get_sun_position(ts_utc)
            solar_elongation = self._calculate_solar_elongation(longitude, sun_lon)

        return NodeState(
            timestamp=ts_utc,
            longitude=longitude,
            speed=speed,
            direction=direction,
            is_stationary=is_stationary,
            solar_elongation=solar_elongation,
        )

    def detect_events(
        self, start_time: datetime, end_time: datetime
    ) -> list[NodeEvent]:
        """
        Detect node events in a time range.

        Args:
            start_time: Start of search period (UTC)
            end_time: End of search period (UTC)

        Returns:
            List of NodeEvent objects sorted by time
        """
        start_time = validate_utc_datetime(start_time)
        end_time = validate_utc_datetime(end_time)

        events = []

        # Coarse scan with configured step
        scan_step = timedelta(seconds=self.config.scan_step_seconds)
        current_time = start_time

        # Track state
        prev_state = self.get_node_state(current_time)
        was_stationary = prev_state.is_stationary

        while current_time < end_time:
            next_time = min(current_time + scan_step, end_time)
            current_state = self.get_node_state(next_time)

            # Check for direction change
            if prev_state.direction != current_state.direction:
                # Refine with bisection
                def direction_condition(t):
                    _, speed = self._get_node_position(t)
                    return (speed >= 0) == (current_state.direction == "direct")

                event_time = self._bisect_event(
                    current_time, next_time, direction_condition
                )

                _, event_speed = self._get_node_position(event_time)

                event = NodeEvent(
                    event_type="direction_change",
                    timestamp=event_time,
                    speed=event_speed,
                    metadata={
                        "from_direction": prev_state.direction,
                        "to_direction": current_state.direction,
                    },
                )

                # Add diagnostics if enabled
                if self.config.enable_diagnostics:
                    sun_lon = self._get_sun_position(event_time)
                    node_lon, _ = self._get_node_position(event_time)
                    event.metadata["solar_elongation"] = (
                        self._calculate_solar_elongation(node_lon, sun_lon)
                    )

                events.append(event)

            # Check for stationary start/end
            is_stationary = current_state.is_stationary

            # Use hysteresis for exit if enabled
            if self.config.enable_hysteresis and was_stationary:
                exit_threshold = self.config.get_exit_threshold()
                is_stationary = abs(current_state.speed) < exit_threshold

            if was_stationary != is_stationary:
                # Refine with bisection
                if is_stationary:
                    # Entering stationary
                    def stationary_condition(t):
                        _, speed = self._get_node_position(t)
                        return abs(speed) < self.config.speed_threshold

                    event_type = "stationary_start"
                    threshold = self.config.speed_threshold
                else:
                    # Exiting stationary
                    exit_thresh = self.config.get_exit_threshold()

                    def stationary_condition(t):
                        _, speed = self._get_node_position(t)
                        return abs(speed) >= exit_thresh

                    event_type = "stationary_end"
                    threshold = exit_thresh

                event_time = self._bisect_event(
                    current_time, next_time, stationary_condition
                )

                _, event_speed = self._get_node_position(event_time)

                event = NodeEvent(
                    event_type=event_type,
                    timestamp=event_time,
                    speed=event_speed,
                    metadata={"threshold": threshold},
                )

                events.append(event)
                was_stationary = is_stationary

            # Move to next step
            prev_state = current_state
            current_time = next_time

        # Detect wobble peaks if enabled
        if self.config.enable_wobble_detection:
            wobble_events = self._detect_wobble_peaks(events, start_time, end_time)
            events.extend(wobble_events)

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)

        return events

    def _detect_wobble_peaks(
        self, existing_events: list[NodeEvent], start_time: datetime, end_time: datetime
    ) -> list[NodeEvent]:
        """
        Detect wobble/perturbation peaks around existing events.

        Args:
            existing_events: Already detected events
            start_time: Search start boundary
            end_time: Search end boundary

        Returns:
            List of wobble peak events
        """
        wobble_events = []
        window = timedelta(hours=self.config.wobble_window_hours)

        for event in existing_events:
            if event.event_type not in ["direction_change", "stationary_start"]:
                continue

            # Search window around event
            search_start = max(event.timestamp - window, start_time)
            search_end = min(event.timestamp + window, end_time)

            # Find local speed extrema
            max_speed = 0
            max_time = None

            scan_step = timedelta(minutes=5)  # Finer scan for wobbles
            current = search_start

            while current <= search_end:
                _, speed = self._get_node_position(current)
                if abs(speed) > max_speed:
                    max_speed = abs(speed)
                    max_time = current
                current += scan_step

            # Report if significant amplitude
            if max_time and max_speed >= self.config.wobble_min_amplitude:
                _, actual_speed = self._get_node_position(max_time)

                wobble = NodeEvent(
                    event_type="wobble_peak",
                    timestamp=max_time,
                    speed=actual_speed,
                    metadata={"amplitude": max_speed},
                )
                wobble_events.append(wobble)

        return wobble_events

    def find_next_event(
        self, from_time: datetime, event_type: str | None = None, max_days: int = 30
    ) -> NodeEvent | None:
        """
        Find the next node event after a given time.

        Args:
            from_time: Start searching from this time
            event_type: Specific event type to find (optional)
            max_days: Maximum days to search forward

        Returns:
            Next NodeEvent or None if not found
        """
        from_time = validate_utc_datetime(from_time)
        end_time = from_time + timedelta(days=max_days)

        events = self.detect_events(from_time, end_time)

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return events[0] if events else None


# Module-level instance for convenience
_calculator = None


def get_node_calculator(
    ephe_path: str = "./swisseph/ephe",
) -> NodePerturbationCalculator:
    """Get or create singleton node calculator instance"""
    global _calculator
    if _calculator is None:
        _calculator = NodePerturbationCalculator(ephe_path)
    return _calculator
