#!/usr/bin/env python3
"""
Adapter between FastAPI and the refactored facade
Handles data transformation and error handling
"""

import logging
import sys

from datetime import datetime, timedelta
from pathlib import Path

# Add refactor directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "refactor"))

from app.core.config import NY_TZ
from app.models.responses import ChangeEvent, PositionResponse
from refactor.constants import PLANET_NAMES
from refactor.facade import get_kp_lord_changes, get_positions
from refactor.monitoring import Timer

logger = logging.getLogger(__name__)


class FacadeAdapter:
    """
    Adapter between FastAPI models and refactored facade

    Responsibilities:
    - Convert between API models and core types
    - Handle timezone conversions
    - Apply business logic transformations
    - Error handling and logging
    """

    def __init__(self):
        self.planet_names = PLANET_NAMES
        logger.info("FacadeAdapter initialized")

    async def get_position(
        self, timestamp: datetime, planet_id: int = 2, apply_offset: bool = True
    ) -> PositionResponse:
        """
        Get planetary position at a specific time

        Args:
            timestamp: UTC timestamp
            planet_id: Planet ID (1-9)
            apply_offset: Whether to apply 307s finance offset

        Returns:
            PositionResponse with all calculated fields
        """
        with Timer("facade_get_position"):
            try:
                # Call facade function
                planet_data = get_positions(
                    ts=timestamp, planet_id=planet_id, apply_kp_offset=apply_offset
                )

                # Determine motion state
                if abs(planet_data.speed) < 0.01:
                    state = "stationary"
                elif planet_data.speed < 0:
                    state = "retrograde"
                else:
                    state = "direct"

                # Build response
                response = PositionResponse(
                    timestamp=timestamp,
                    planet_id=planet_id,
                    planet_name=self.planet_names.get(planet_id, f"Planet{planet_id}"),
                    position=planet_data.position,
                    speed=planet_data.speed,
                    nl=planet_data.nl,
                    sl=planet_data.sl,
                    sl2=planet_data.sl2,
                    sign=planet_data.sign,
                    nakshatra=planet_data.nakshatra,
                    pada=planet_data.pada,
                    state=state,
                    offset_applied=apply_offset,
                )

                return response

            except Exception as e:
                logger.error(f"Error getting position: {e}")
                raise

    async def get_changes_for_day(
        self, date: datetime, planet_id: int = 2, levels: list[str] | None = None
    ) -> list[ChangeEvent]:
        """
        Get all lord changes for a specific day

        Args:
            date: Date (NY timezone aware)
            planet_id: Planet ID
            levels: Lord levels to include (nl, sl, sl2, sign)

        Returns:
            List of ChangeEvent objects
        """
        with Timer("facade_get_changes"):
            try:
                if levels is None:
                    levels = ["nl", "sl", "sl2"]

                # Convert NY date to UTC range
                ny_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                ny_end = ny_start + timedelta(days=1)

                utc_start = ny_start.astimezone(NY_TZ).replace(tzinfo=None)
                utc_end = ny_end.astimezone(NY_TZ).replace(tzinfo=None)

                # Find changes using facade
                changes = get_kp_lord_changes(
                    start_ts=utc_start,
                    end_ts=utc_end,
                    planet_id=planet_id,
                    apply_kp_offset=True,
                    check_interval_seconds=1,  # High precision for intraday
                )

                # Convert to API models
                events = []
                for change in changes:
                    # Filter by level
                    if change.level not in levels:
                        continue

                    # Convert UTC to NY time
                    ny_time = NY_TZ.localize(change.timestamp.replace(tzinfo=None))

                    event = ChangeEvent(
                        timestamp_utc=change.timestamp,
                        timestamp_ny=ny_time,
                        planet_id=planet_id,
                        level=change.level,
                        old_lord=change.old_lord,
                        new_lord=change.new_lord,
                        position=change.position,
                    )
                    events.append(event)

                return events

            except Exception as e:
                logger.error(f"Error getting changes: {e}")
                raise

    async def get_changes_range(
        self,
        start_date: str,
        end_date: str,
        planet_id: int = 2,
        levels: list[str] | None = None,
    ) -> dict:
        """
        Get lord changes for a date range

        Args:
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)
            planet_id: Planet ID
            levels: Lord levels to include

        Returns:
            Dictionary with change statistics and events
        """
        with Timer("facade_get_changes_range"):
            try:
                if levels is None:
                    levels = ["nl", "sl", "sl2"]

                # Parse dates
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(end_date, "%Y-%m-%d")

                # Convert to NY timezone
                ny_start = NY_TZ.localize(start.replace(hour=0, minute=0, second=0))
                ny_end = NY_TZ.localize(end.replace(hour=23, minute=59, second=59))

                # Convert to UTC
                utc_start = ny_start.astimezone(NY_TZ).replace(tzinfo=None)
                utc_end = ny_end.astimezone(NY_TZ).replace(tzinfo=None)

                # Find changes
                changes = get_kp_lord_changes(
                    start_ts=utc_start,
                    end_ts=utc_end,
                    planet_id=planet_id,
                    apply_kp_offset=True,
                    check_interval_seconds=60,  # Lower precision for longer ranges
                )

                # Convert and filter
                events = []
                level_counts = {level: 0 for level in levels}

                for change in changes:
                    if change.level not in levels:
                        continue

                    ny_time = NY_TZ.localize(change.timestamp.replace(tzinfo=None))

                    event = ChangeEvent(
                        timestamp_utc=change.timestamp,
                        timestamp_ny=ny_time,
                        planet_id=planet_id,
                        level=change.level,
                        old_lord=change.old_lord,
                        new_lord=change.new_lord,
                        position=change.position,
                    )
                    events.append(event)
                    level_counts[change.level] += 1

                return {
                    "start_date": start_date,
                    "end_date": end_date,
                    "planet_id": planet_id,
                    "planet_name": self.planet_names.get(
                        planet_id, f"Planet{planet_id}"
                    ),
                    "total_changes": len(events),
                    "changes": events,
                    "by_level": level_counts,
                }

            except Exception as e:
                logger.error(f"Error getting change range: {e}")
                raise

    async def validate_offset_consistency(
        self, timestamp: datetime, planet_id: int = 2
    ) -> dict:
        """
        Validate that offset is applied consistently

        Args:
            timestamp: UTC timestamp
            planet_id: Planet ID

        Returns:
            Validation results comparing with/without offset
        """
        try:
            # Get positions with and without offset
            with_offset = get_positions(timestamp, planet_id, apply_kp_offset=True)
            without_offset = get_positions(timestamp, planet_id, apply_kp_offset=False)

            # Calculate expected difference (307 seconds)
            expected_diff = 307 / 86400 * 360  # degrees
            actual_diff = abs(with_offset.position - without_offset.position)

            # Check if lords are different
            lord_changes = {
                "nl": with_offset.nl != without_offset.nl,
                "sl": with_offset.sl != without_offset.sl,
                "sl2": with_offset.sl2 != without_offset.sl2,
            }

            return {
                "timestamp": timestamp.isoformat(),
                "planet_id": planet_id,
                "with_offset": {
                    "position": with_offset.position,
                    "nl": with_offset.nl,
                    "sl": with_offset.sl,
                    "sl2": with_offset.sl2,
                },
                "without_offset": {
                    "position": without_offset.position,
                    "nl": without_offset.nl,
                    "sl": without_offset.sl,
                    "sl2": without_offset.sl2,
                },
                "position_diff_degrees": actual_diff,
                "expected_diff_degrees": expected_diff,
                "lord_changes": lord_changes,
                "any_lord_changed": any(lord_changes.values()),
            }

        except Exception as e:
            logger.error(f"Error validating offset: {e}")
            raise
