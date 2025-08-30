#!/usr/bin/env python3
"""
KP Dasha System Adapter - Vimshottari Dasha calculations via SystemAdapter interface.
Provides snapshot and changes methods for dasha periods.
"""

import logging

from datetime import date, datetime
from typing import Any

from refactor.dasha import VimshottariDashaEngine
from refactor.time_utils import validate_utc_datetime

logger = logging.getLogger(__name__)


class KPDashaAdapter:
    """
    Adapter for Vimshottari Dasha calculations following SystemAdapter protocol.
    """

    def __init__(self, ephe_path: str = "./swisseph/ephe"):
        """
        Initialize KP Dasha adapter.

        Args:
            ephe_path: Path to Swiss Ephemeris data files
        """
        self.system = "KP_DASHA"
        self.engine = VimshottariDashaEngine(ephe_path)
        self._birth_charts = {}  # Cache for birth data
        logger.info(f"KPDashaAdapter initialized for {self.system}")

    def set_birth_data(
        self,
        chart_id: str,
        birth_time: datetime,
        moon_longitude: float | None = None,
    ):
        """
        Set birth data for a chart (required for dasha calculations).

        Args:
            chart_id: Unique identifier for the chart
            birth_time: Birth UTC timestamp
            moon_longitude: Pre-calculated Moon longitude (optional)
        """
        birth_time = validate_utc_datetime(birth_time)

        # Calculate moon longitude if not provided
        if moon_longitude is None:
            moon_longitude = self.engine.get_moon_longitude(birth_time)

        self._birth_charts[chart_id] = {
            "birth_time": birth_time,
            "moon_longitude": moon_longitude,
        }

        logger.debug(f"Birth data set for chart {chart_id}: {birth_time.isoformat()}")

    def snapshot(
        self,
        ts_utc: datetime,
        chart_id: str | None = None,
        birth_time: datetime | None = None,
        moon_longitude: float | None = None,
        levels: int = 3,
    ) -> dict[str, Any]:
        """
        Get current active dasha chain at timestamp.

        Args:
            ts_utc: Reference timestamp
            chart_id: Chart ID if birth data was pre-set
            birth_time: Birth time if not using chart_id
            moon_longitude: Moon longitude at birth (optional)
            levels: Number of dasha levels to return (1-5)

        Returns:
            Dict with current dasha periods and metadata
        """
        ts_utc = validate_utc_datetime(ts_utc)

        # Get birth data
        if chart_id and chart_id in self._birth_charts:
            birth_data = self._birth_charts[chart_id]
            birth_time = birth_data["birth_time"]
            moon_longitude = birth_data["moon_longitude"]
        elif birth_time:
            birth_time = validate_utc_datetime(birth_time)
            if moon_longitude is None:
                moon_longitude = self.engine.get_moon_longitude(birth_time)
        else:
            raise ValueError("Either chart_id or birth_time must be provided")

        # Get current dashas
        current_dashas = self.engine.get_current_dashas(
            birth_time=birth_time,
            reference_time=ts_utc,
            levels=levels,
            moon_longitude=moon_longitude,
        )

        # Format response
        result = {
            "system": self.system,
            "timestamp": ts_utc.isoformat(),
            "birth_time": birth_time.isoformat(),
            "moon_longitude": moon_longitude,
            "levels": levels,
        }

        # Add each level if present
        if "mahadasha" in current_dashas:
            maha = current_dashas["mahadasha"]
            result["mahadasha"] = {
                "planet": maha.planet,
                "start": maha.start_date.isoformat(),
                "end": maha.end_date.isoformat(),
                "duration_days": float(maha.duration_days),
            }

        if "antardasha" in current_dashas:
            antar = current_dashas["antardasha"]
            result["antardasha"] = {
                "planet": antar.planet,
                "start": antar.start_date.isoformat(),
                "end": antar.end_date.isoformat(),
                "duration_days": float(antar.duration_days),
            }

        if "pratyantardasha" in current_dashas:
            pratyantar = current_dashas["pratyantardasha"]
            result["pratyantardasha"] = {
                "planet": pratyantar.planet,
                "start": pratyantar.start_date.isoformat(),
                "end": pratyantar.end_date.isoformat(),
                "duration_days": float(pratyantar.duration_days),
            }

        if "sookshma" in current_dashas:
            sookshma = current_dashas["sookshma"]
            result["sookshma"] = {
                "planet": sookshma.planet,
                "start": sookshma.start_date.isoformat(),
                "end": sookshma.end_date.isoformat(),
                "duration_days": float(sookshma.duration_days),
            }

        if "prana" in current_dashas:
            prana = current_dashas["prana"]
            result["prana"] = {
                "planet": prana.planet,
                "start": prana.start_date.isoformat(),
                "end": prana.end_date.isoformat(),
                "duration_days": float(prana.duration_days),
            }

        # Add metadata
        result["meta"] = {
            "adapter": self.system,
            "version": "1.0.0",
            "ayanamsa": "Krishnamurti",
            "chart_id": chart_id,
            "nakshatra": self.engine.get_nakshatra_from_longitude(moon_longitude)[0],
        }

        return result

    def changes(
        self,
        day_utc: date,
        chart_id: str | None = None,
        birth_time: datetime | None = None,
        moon_longitude: float | None = None,
        levels: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Get all dasha transitions on a given day.

        Args:
            day_utc: Date to check for changes
            chart_id: Chart ID if birth data was pre-set
            birth_time: Birth time if not using chart_id
            moon_longitude: Moon longitude at birth (optional)
            levels: Number of dasha levels to check (1-5)

        Returns:
            List of dasha change events
        """
        # Convert date to datetime
        date_dt = datetime(day_utc.year, day_utc.month, day_utc.day, 0, 0, 0)

        # Get birth data
        if chart_id and chart_id in self._birth_charts:
            birth_data = self._birth_charts[chart_id]
            birth_time = birth_data["birth_time"]
            moon_longitude = birth_data["moon_longitude"]
        elif birth_time:
            birth_time = validate_utc_datetime(birth_time)
            if moon_longitude is None:
                moon_longitude = self.engine.get_moon_longitude(birth_time)
        else:
            raise ValueError("Either chart_id or birth_time must be provided")

        # Get dasha changes
        changes = self.engine.get_dasha_changes(
            date_utc=date_dt,
            birth_time=birth_time,
            moon_longitude=moon_longitude,
            levels=levels,
        )

        # Add system and metadata to each change
        for change in changes:
            change["system"] = self.system
            change["date"] = day_utc.isoformat()
            if chart_id:
                change["chart_id"] = chart_id

        return changes

    def get_full_cycle(
        self,
        chart_id: str | None = None,
        birth_time: datetime | None = None,
        moon_longitude: float | None = None,
        levels: int = 3,
    ) -> dict[str, Any]:
        """
        Get full 120-year Vimshottari cycle with nested periods.

        Args:
            chart_id: Chart ID if birth data was pre-set
            birth_time: Birth time if not using chart_id
            moon_longitude: Moon longitude at birth (optional)
            levels: Depth of nesting (1-5)

        Returns:
            Full cycle structure as dictionary
        """
        # Get birth data
        if chart_id and chart_id in self._birth_charts:
            birth_data = self._birth_charts[chart_id]
            birth_time = birth_data["birth_time"]
            moon_longitude = birth_data["moon_longitude"]
        elif birth_time:
            birth_time = validate_utc_datetime(birth_time)
            if moon_longitude is None:
                moon_longitude = self.engine.get_moon_longitude(birth_time)
        else:
            raise ValueError("Either chart_id or birth_time must be provided")

        # Calculate full cycle
        full_cycle = self.engine.calculate_full_cycle(
            birth_time=birth_time, moon_longitude=moon_longitude, levels=levels
        )

        # Convert to dictionary and add metadata
        result = full_cycle.to_dict()
        result["system"] = self.system
        result["birth_time"] = birth_time.isoformat()
        result["moon_longitude"] = moon_longitude
        result["meta"] = {
            "adapter": self.system,
            "version": "1.0.0",
            "ayanamsa": "Krishnamurti",
            "chart_id": chart_id,
            "levels": levels,
        }

        return result

    def get_birth_balance(
        self, birth_time: datetime, moon_longitude: float | None = None
    ) -> dict[str, Any]:
        """
        Get birth balance dasha information.

        Args:
            birth_time: Birth UTC timestamp
            moon_longitude: Moon longitude at birth (optional)

        Returns:
            Birth balance details
        """
        birth_time = validate_utc_datetime(birth_time)

        if moon_longitude is None:
            moon_longitude = self.engine.get_moon_longitude(birth_time)

        # Get birth balance
        lord, elapsed_days, remaining_days = self.engine.calculate_birth_balance(
            birth_time, moon_longitude
        )

        # Get nakshatra info
        nakshatra, _, elapsed_portion = self.engine.get_nakshatra_from_longitude(
            moon_longitude
        )

        return {
            "system": self.system,
            "birth_time": birth_time.isoformat(),
            "moon_longitude": moon_longitude,
            "nakshatra": nakshatra,
            "birth_lord": lord,
            "elapsed_days": float(elapsed_days),
            "remaining_days": float(remaining_days),
            "elapsed_portion": elapsed_portion,
            "remaining_portion": 1.0 - elapsed_portion,
        }


# Module-level instance
_adapter = None


def get_kp_dasha_adapter(ephe_path: str = "./swisseph/ephe") -> KPDashaAdapter:
    """Get or create singleton KP Dasha adapter instance"""
    global _adapter
    if _adapter is None:
        _adapter = KPDashaAdapter(ephe_path)
    return _adapter
