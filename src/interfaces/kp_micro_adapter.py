"""
KP Micro-Timing SystemAdapter
Phase 8: Adapter for Market Micro-Timing volatility windows
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from refactor.micro_config import MicroConfig, get_micro_config
from refactor.micro_timing import (
    build_day_timeline,
    calculate_volatility_score,
    find_next_high_volatility,
)

logger = logging.getLogger(__name__)
UTC = UTC


@dataclass(frozen=True)
class KPMicroAdapter:
    """
    SystemAdapter implementation for Market Micro-Timing Engine.

    Provides volatility windows based on Moon, Nodes, Eclipse, and Dasha factors.
    """

    system: str = "KP_MICRO"
    version: str = "1.0.0"
    cfg: MicroConfig = None

    def __post_init__(self):
        """Initialize configuration if not provided."""
        if self.cfg is None:
            object.__setattr__(self, "cfg", get_micro_config())

    def get_metadata(self) -> dict[str, Any]:
        """Get system metadata."""
        return {
            "system": self.system,
            "version": self.version,
            "description": "Market Micro-Timing volatility window generator",
            "capabilities": [
                "day_timeline",
                "range_timeline",
                "next_volatility",
                "instant_score",
            ],
            "config": {
                "weights": {
                    "moon": self.cfg.w_moon_velocity,
                    "nodes": self.cfg.w_node_events,
                    "eclipse": self.cfg.w_eclipse,
                    "dasha": self.cfg.w_dasha,
                },
                "thresholds": {
                    "high": self.cfg.high_threshold,
                    "medium": self.cfg.med_threshold,
                },
                "windows": {
                    "moon_minutes": self.cfg.win_moon_anomaly_min,
                    "node_minutes": self.cfg.win_node_event_min,
                    "eclipse_hours": self.cfg.win_eclipse_hours,
                    "dasha_minutes": self.cfg.win_dasha_min,
                },
                "features": {
                    "moon": self.cfg.enable_moon,
                    "nodes": self.cfg.enable_nodes,
                    "eclipse": self.cfg.enable_eclipse,
                    "dasha": self.cfg.enable_dasha,
                },
            },
        }

    def day(self, day_local: date) -> dict[str, Any]:
        """
        Generate volatility windows for a single day.

        Args:
            day_local: Date to analyze

        Returns:
            Dictionary with date, windows list, and metadata
        """
        try:
            windows = build_day_timeline(day_local, cfg=self.cfg)

            return {
                "date": day_local.isoformat(),
                "windows": [w.to_dict() for w in windows],
                "summary": {
                    "total_windows": len(windows),
                    "high_volatility": sum(1 for w in windows if w.strength == "high"),
                    "medium_volatility": sum(
                        1 for w in windows if w.strength == "medium"
                    ),
                    "low_volatility": sum(1 for w in windows if w.strength == "low"),
                    "max_score": round(max((w.score for w in windows), default=0.0), 4),
                },
                "system": self.system,
                "meta": {"version": self.version},
            }
        except Exception as e:
            logger.error(f"Error generating day timeline: {e}")
            return {
                "date": day_local.isoformat(),
                "windows": [],
                "error": str(e),
                "system": self.system,
            }

    def range(self, start_day: date, end_day: date) -> dict[str, Any]:
        """
        Generate volatility windows for a date range.

        Args:
            start_day: Start date (inclusive)
            end_day: End date (inclusive)

        Returns:
            Dictionary with merged windows across all days
        """
        if end_day < start_day:
            raise ValueError("end_day must be >= start_day")

        # Check range limit
        days_diff = (end_day - start_day).days + 1
        if days_diff > self.cfg.max_days_range:
            raise ValueError(f"Range exceeds maximum of {self.cfg.max_days_range} days")

        all_windows = []
        current = start_day

        while current <= end_day:
            try:
                windows = build_day_timeline(current, cfg=self.cfg)
                all_windows.extend(windows)
            except Exception as e:
                logger.warning(f"Error processing {current}: {e}")

            current = current + timedelta(days=1)

        # Sort by start time
        all_windows.sort(key=lambda w: w.start)

        return {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "windows": [w.to_dict() for w in all_windows],
            "summary": {
                "days_analyzed": days_diff,
                "total_windows": len(all_windows),
                "high_volatility": sum(1 for w in all_windows if w.strength == "high"),
                "medium_volatility": sum(
                    1 for w in all_windows if w.strength == "medium"
                ),
                "low_volatility": sum(1 for w in all_windows if w.strength == "low"),
                "max_score": round(max((w.score for w in all_windows), default=0.0), 4),
            },
            "system": self.system,
            "meta": {"version": self.version},
        }

    def next(self, threshold: str = "high") -> dict[str, Any]:
        """
        Find next volatility window meeting threshold.

        Args:
            threshold: Minimum strength level ("low", "medium", "high")

        Returns:
            Dictionary with next window or message if not found
        """
        try:
            # Validate threshold
            if threshold not in ["low", "medium", "high"]:
                raise ValueError(f"Invalid threshold: {threshold}")

            window = find_next_high_volatility(
                threshold=threshold, max_days=self.cfg.max_days_range, cfg=self.cfg
            )

            if window:
                return {
                    "found": True,
                    "window": window.to_dict(),
                    "days_ahead": (window.start.date() - datetime.now(UTC).date()).days,
                    "system": self.system,
                    "meta": {"version": self.version},
                }
            else:
                return {
                    "found": False,
                    "message": f"No {threshold} volatility window found in next {self.cfg.max_days_range} days",
                    "system": self.system,
                    "meta": {"version": self.version},
                }

        except Exception as e:
            logger.error(f"Error finding next volatility: {e}")
            return {"found": False, "error": str(e), "system": self.system}

    def instant(self, timestamp: datetime) -> dict[str, Any]:
        """
        Calculate instantaneous volatility score at a specific time.

        Args:
            timestamp: Time to evaluate

        Returns:
            Dictionary with score and active factors
        """
        try:
            result = calculate_volatility_score(timestamp, cfg=self.cfg)
            result["system"] = self.system
            result["meta"] = {"version": self.version}
            return result
        except Exception as e:
            logger.error(f"Error calculating instant score: {e}")
            return {
                "timestamp": timestamp.isoformat(),
                "score": 0.0,
                "strength": "low",
                "factors": [],
                "error": str(e),
                "system": self.system,
            }

    # SystemAdapter protocol methods
    def snapshot(self, ts_utc: datetime) -> dict[str, Any]:
        """Get system state at a specific timestamp (instant score)."""
        return self.instant(ts_utc)

    def changes(self, day_utc: date) -> list[dict[str, Any]]:
        """Get all volatility windows for a day."""
        result = self.day(day_utc)
        return result.get("windows", [])
