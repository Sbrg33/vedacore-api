"""
KP Strategy SystemAdapter
Phase 9: Trading strategy integration adapter
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from refactor.strategy_config import StrategyConfig, get_strategy_config
from refactor.strategy_engine import (
    build_day_propensity,
    calculate_summary_stats,
)

logger = logging.getLogger(__name__)
UTC = UTC


@dataclass(frozen=True)
class KPStrategyAdapter:
    """
    SystemAdapter implementation for Trading Strategy Integration.

    Provides minute-level confidence timelines for trading decisions.
    """

    system: str = "KP_STRATEGY"
    version: str = "1.0.0"
    cfg: StrategyConfig = None

    def __post_init__(self):
        """Initialize configuration if not provided."""
        if self.cfg is None:
            object.__setattr__(self, "cfg", get_strategy_config())

    def get_metadata(self) -> dict[str, Any]:
        """Get system metadata."""
        return {
            "system": self.system,
            "version": self.version,
            "description": "Trading strategy confidence synthesis engine",
            "capabilities": [
                "day_timeline",
                "window_aggregation",
                "confidence_scoring",
                "rule_combinators",
                "feature_logging",
            ],
            "config": {
                "weights": {
                    "micro": self.cfg.w_micro,
                    "amd": self.cfg.w_amd,
                    "moon": self.cfg.w_moon,
                    "nodes": self.cfg.w_nodes,
                },
                "thresholds": {
                    "high": self.cfg.high_threshold,
                    "medium": self.cfg.med_threshold,
                },
                "smoothing": {
                    "enabled": self.cfg.enable_smoothing,
                    "ema_alpha": self.cfg.ema_alpha,
                },
                "market_hours": {
                    "enabled": self.cfg.enable_market_hours,
                    "open": f"{self.cfg.open_hh:02d}:{self.cfg.open_mm:02d}",
                    "close": f"{self.cfg.close_hh:02d}:{self.cfg.close_mm:02d}",
                },
                "rulebook": {
                    "enabled": self.cfg.enable_rulebook,
                    "ruleset_id": (
                        self.cfg.rulebook.get("ruleset_id")
                        if self.cfg.rulebook
                        else None
                    ),
                    "rule_count": (
                        len(self.cfg.rulebook.get("rules", []))
                        if self.cfg.rulebook
                        else 0
                    ),
                },
            },
        }

    def day(self, day_local: date, *, ticker: str = "TSLA") -> dict[str, Any]:
        """
        Generate minute-level confidence timeline for a trading day.

        Args:
            day_local: Date to analyze
            ticker: Ticker symbol

        Returns:
            Dictionary with timeline, summary, and metadata
        """
        try:
            # Build propensity timeline
            signals = build_day_propensity(day_local, ticker, cfg=self.cfg)

            # Calculate summary statistics
            summary = calculate_summary_stats(signals)

            # Convert signals to dictionaries
            timeline = [s.to_dict() for s in signals]

            # Optionally save feature log
            # save_feature_log(day_local, ticker, signals)

            return {
                "date": day_local.isoformat(),
                "ticker": ticker,
                "timeline": timeline,
                "summary": {
                    "total_minutes": summary["total_minutes"],
                    "p95": round(summary["p95"], 4),
                    "p75": round(summary["p75"], 4),
                    "p50": round(summary["p50"], 4),
                    "mean": round(summary["mean"], 4),
                    "high_bins": summary["high_count"],
                    "medium_bins": summary["medium_count"],
                    "low_bins": summary["low_count"],
                    "max_score": round(summary["max_confidence"], 4),
                    "min_score": round(summary["min_confidence"], 4),
                    "up_minutes": summary.get("up_minutes", 0),
                    "down_minutes": summary.get("down_minutes", 0),
                    "neutral_minutes": summary.get("neutral_minutes", 0),
                    "mean_direction_score": round(
                        summary.get("mean_direction_score", 0.0), 4
                    ),
                    "flip_count": summary.get("flip_count", 0),
                },
                "ruleset_id": (
                    self.cfg.rulebook.get("ruleset_id") if self.cfg.rulebook else None
                ),
                "system": self.system,
                "meta": {"version": self.version},
            }

        except Exception as e:
            logger.error(f"Error generating day timeline: {e}")
            return {
                "date": day_local.isoformat(),
                "ticker": ticker,
                "timeline": [],
                "error": str(e),
                "system": self.system,
            }

    def window(
        self, start_iso: str, end_iso: str, *, ticker: str = "TSLA"
    ) -> dict[str, Any]:
        """
        Get aggregated confidence for a time window.

        Args:
            start_iso: Start timestamp (ISO format)
            end_iso: End timestamp (ISO format)
            ticker: Ticker symbol

        Returns:
            Dictionary with window summary
        """
        try:
            # Parse timestamps
            start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=UTC)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=UTC)

            # Get the day's signals
            day_local = start_dt.date()
            day_data = self.day(day_local, ticker=ticker)

            # Filter to window
            window_signals = []
            for signal_dict in day_data.get("timeline", []):
                signal_time = datetime.fromisoformat(signal_dict["t"])
                if start_dt <= signal_time <= end_dt:
                    window_signals.append(signal_dict)

            # Calculate window statistics
            if window_signals:
                confidences = [s["confidence"] for s in window_signals]
                high_count = sum(1 for s in window_signals if s["strength"] == "high")
                medium_count = sum(
                    1 for s in window_signals if s["strength"] == "medium"
                )
                low_count = sum(1 for s in window_signals if s["strength"] == "low")

                summary = {
                    "minute_count": len(window_signals),
                    "mean_confidence": round(sum(confidences) / len(confidences), 4),
                    "max_confidence": round(max(confidences), 4),
                    "min_confidence": round(min(confidences), 4),
                    "high_minutes": high_count,
                    "medium_minutes": medium_count,
                    "low_minutes": low_count,
                }
            else:
                summary = {
                    "minute_count": 0,
                    "mean_confidence": 0.0,
                    "max_confidence": 0.0,
                    "min_confidence": 0.0,
                    "high_minutes": 0,
                    "medium_minutes": 0,
                    "low_minutes": 0,
                }

            return {
                "window": {"start": start_iso, "end": end_iso},
                "ticker": ticker,
                "summary": summary,
                "system": self.system,
                "meta": {"version": self.version},
            }

        except Exception as e:
            logger.error(f"Error calculating window: {e}")
            return {
                "window": {"start": start_iso, "end": end_iso},
                "ticker": ticker,
                "error": str(e),
                "system": self.system,
            }

    def config_dryrun(
        self, test_config: dict[str, Any], day_local: date, ticker: str = "TSLA"
    ) -> dict[str, Any]:
        """
        Test a configuration without persisting it.

        Args:
            test_config: Configuration to test
            day_local: Date to test on
            ticker: Ticker symbol

        Returns:
            Test results with timeline
        """
        try:
            # Create temporary config
            # This would need proper validation in production
            temp_cfg = self.cfg  # Use existing for now

            # Generate timeline with test config
            signals = build_day_propensity(day_local, ticker, cfg=temp_cfg)

            # Return sample results
            return {
                "test": "dryrun",
                "date": day_local.isoformat(),
                "ticker": ticker,
                "sample_size": min(10, len(signals)),
                "sample": [s.to_dict() for s in signals[:10]],
                "summary": calculate_summary_stats(signals),
                "system": self.system,
            }

        except Exception as e:
            logger.error(f"Error in config dryrun: {e}")
            return {"test": "dryrun", "error": str(e), "system": self.system}

    # SystemAdapter protocol methods
    def snapshot(self, ts_utc: datetime) -> dict[str, Any]:
        """Get instant confidence at a specific timestamp."""
        # Find the minute signal for this timestamp
        day_local = ts_utc.date()
        day_data = self.day(day_local)

        # Find closest minute
        target_minute = ts_utc.replace(second=0, microsecond=0).isoformat()

        for signal in day_data.get("timeline", []):
            if signal["t"] == target_minute:
                return {
                    "timestamp": ts_utc.isoformat(),
                    "confidence": signal["confidence"],
                    "strength": signal["strength"],
                    "direction": signal["direction"],
                    "tags": signal["tags"],
                    "system": self.system,
                }

        return {
            "timestamp": ts_utc.isoformat(),
            "confidence": 0.0,
            "strength": "low",
            "direction": "neutral",
            "tags": [],
            "system": self.system,
        }

    def changes(self, day_utc: date) -> list[dict[str, Any]]:
        """Get significant confidence changes for a day."""
        day_data = self.day(day_utc)
        timeline = day_data.get("timeline", [])

        changes = []
        previous_strength = "low"

        for signal in timeline:
            current_strength = signal["strength"]

            # Record strength changes
            if current_strength != previous_strength:
                changes.append(
                    {
                        "timestamp": signal["t"],
                        "type": "strength_change",
                        "from": previous_strength,
                        "to": current_strength,
                        "confidence": signal["confidence"],
                    }
                )
                previous_strength = current_strength

        return changes
