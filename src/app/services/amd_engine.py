#!/usr/bin/env python3
"""
AMD (Advanced Market Detection) phase detection engine
Identifies critical market phases around KP lord changes
"""

import logging

from datetime import datetime, timedelta
from typing import Literal

from app.models.responses import ChangeEvent

logger = logging.getLogger(__name__)

AMDPhase = Literal[
    "volatility_build", "pre_change", "critical_change", "confirmation", "none"
]


class AMDPhaseDetector:
    """
    Detects market phases relative to KP lord changes

    Phase definitions:
    - volatility_build: 30-60 minutes before significant change
    - pre_change: 5-30 minutes before change
    - critical_change: Within ±5 minutes of change
    - confirmation: 5-30 minutes after change
    - none: No significant phase detected
    """

    def __init__(self):
        # Phase timing windows (in seconds)
        self.windows = {
            "volatility_build": (-3600, -1800),  # -60 to -30 minutes
            "pre_change": (-1800, -300),  # -30 to -5 minutes
            "critical_change": (-300, 300),  # -5 to +5 minutes
            "confirmation": (300, 1800),  # +5 to +30 minutes
        }

        # Significant levels for AMD detection
        self.significant_levels = {"nl", "sl"}  # NL and SL changes most significant

    async def detect_phase(
        self, timestamp: datetime, changes: list[ChangeEvent]
    ) -> AMDPhase:
        """
        Detect AMD phase for a given timestamp

        Args:
            timestamp: Time to check (NY timezone)
            changes: List of change events for the day

        Returns:
            Detected AMD phase
        """
        try:
            # Filter for significant changes only
            significant_changes = [
                c for c in changes if c.level.lower() in self.significant_levels
            ]

            if not significant_changes:
                return "none"

            # Find nearest significant change
            nearest_change = None
            min_delta = float("inf")

            for change in significant_changes:
                # Calculate time delta in seconds
                delta = (change.timestamp_ny - timestamp).total_seconds()
                abs_delta = abs(delta)

                if abs_delta < min_delta:
                    min_delta = abs_delta
                    nearest_change = (change, delta)

            if not nearest_change:
                return "none"

            change, delta_seconds = nearest_change

            # Check which phase window the timestamp falls into
            for phase, (start, end) in self.windows.items():
                if start <= delta_seconds <= end:
                    logger.debug(
                        f"Detected {phase} at {timestamp} "
                        f"(delta: {delta_seconds}s from {change.level} change)"
                    )
                    return phase

            return "none"

        except Exception as e:
            logger.error(f"Error detecting AMD phase: {e}")
            return "none"

    def get_phase_strength(self, phase: AMDPhase) -> float:
        """
        Get relative strength/importance of a phase

        Args:
            phase: AMD phase

        Returns:
            Strength score (0.0 to 1.0)
        """
        strengths = {
            "critical_change": 1.0,
            "pre_change": 0.8,
            "confirmation": 0.6,
            "volatility_build": 0.4,
            "none": 0.0,
        }
        return strengths.get(phase, 0.0)

    def should_alert(self, phase: AMDPhase) -> bool:
        """
        Determine if a phase warrants an alert

        Args:
            phase: AMD phase

        Returns:
            True if alert should be sent
        """
        alert_phases = {"critical_change", "pre_change"}
        return phase in alert_phases

    async def analyze_day(self, date: datetime, changes: list[ChangeEvent]) -> dict:
        """
        Analyze AMD patterns for an entire day

        Args:
            date: Date to analyze (NY timezone)
            changes: Change events for the day

        Returns:
            Analysis summary with phase counts and patterns
        """
        try:
            # Count phases throughout the day
            phase_counts = {
                "volatility_build": 0,
                "pre_change": 0,
                "critical_change": 0,
                "confirmation": 0,
                "none": 0,
            }

            # Sample every 5 minutes throughout trading hours
            start = date.replace(hour=9, minute=30)
            end = date.replace(hour=16, minute=0)
            current = start

            samples = []
            while current <= end:
                phase = await self.detect_phase(current, changes)
                phase_counts[phase] += 1
                samples.append((current, phase))
                current += timedelta(minutes=5)

            # Identify phase clusters (consecutive non-none phases)
            clusters = []
            current_cluster = []

            for ts, phase in samples:
                if phase != "none":
                    current_cluster.append((ts, phase))
                elif current_cluster:
                    clusters.append(current_cluster)
                    current_cluster = []

            if current_cluster:
                clusters.append(current_cluster)

            return {
                "date": date.isoformat(),
                "phase_counts": phase_counts,
                "total_samples": len(samples),
                "active_rate": 1 - (phase_counts["none"] / len(samples)),
                "cluster_count": len(clusters),
                "longest_cluster": max(len(c) for c in clusters) if clusters else 0,
                "significant_changes": len(
                    [c for c in changes if c.level.lower() in self.significant_levels]
                ),
            }

        except Exception as e:
            logger.error(f"Error analyzing day: {e}")
            return {"date": date.isoformat(), "error": str(e)}
