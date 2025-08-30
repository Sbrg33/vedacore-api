#!/usr/bin/env python3
"""
Transit Dasha Synchronizer - Dasha Period Alignment Scoring
Checks alignment between current dasha periods and transit events
"""

import logging

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .constants import PLANET_NAMES
from .dasha import VimshottariDashaEngine

logger = logging.getLogger(__name__)


# Map planet names to IDs
PLANET_NAME_TO_ID = {
    "SUN": 1,
    "MOON": 2,
    "JUPITER": 3,
    "RAHU": 4,
    "MERCURY": 5,
    "VENUS": 6,
    "KETU": 7,
    "SATURN": 8,
    "MARS": 9,
}

# Planet friendships (simplified KP relationships)
PLANET_FRIENDSHIPS = {
    1: [3, 9, 2],  # Sun: friends with Jupiter, Mars, Moon
    2: [1, 5],  # Moon: friends with Sun, Mercury
    3: [1, 2, 9],  # Jupiter: friends with Sun, Moon, Mars
    4: [5, 6, 8],  # Rahu: friends with Mercury, Venus, Saturn
    5: [1, 6],  # Mercury: friends with Sun, Venus
    6: [5, 8],  # Venus: friends with Mercury, Saturn
    7: [9, 6],  # Ketu: friends with Mars, Venus
    8: [5, 6],  # Saturn: friends with Mercury, Venus
    9: [1, 2, 3],  # Mars: friends with Sun, Moon, Jupiter
}


@dataclass
class DashaSyncResult:
    """Result of dasha synchronization check"""

    current_dasha: str
    current_antardasha: str
    current_pratyantara: str | None
    target_planet: int
    sync_score: float  # 0-1
    sync_level: str  # 'direct', 'friendly', 'neutral', 'hostile'
    reasons: list[str]

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "dasha": self.current_dasha,
            "antardasha": self.current_antardasha,
            "pratyantara": self.current_pratyantara,
            "target_planet": self.target_planet,
            "target_name": PLANET_NAMES.get(
                self.target_planet, str(self.target_planet)
            ),
            "sync_score": round(self.sync_score, 2),
            "sync_level": self.sync_level,
            "reasons": self.reasons,
        }


class TransitDashaSync:
    """
    Synchronize transit events with Vimshottari Dasha periods.
    Higher scores indicate better alignment for event manifestation.
    """

    def __init__(self, dasha_engine: VimshottariDashaEngine | None = None):
        """
        Initialize dasha synchronizer.

        Args:
            dasha_engine: Vimshottari dasha calculator (creates if None)
        """
        self.dasha_engine = dasha_engine or VimshottariDashaEngine()
        logger.info("TransitDashaSync initialized")

    def get_dasha_score(
        self,
        target_planet: int,
        active_dasha: dict | None = None,
        current_time: datetime | None = None,
        birth_time: datetime | None = None,
        moon_longitude: float | None = None,
        dispositor_map: dict[int, int] | None = None,
    ) -> float:
        """
        Get dasha alignment score for target planet.

        Args:
            target_planet: Target planet ID (1-9)
            active_dasha: Pre-calculated active dasha dict
            current_time: Current UTC time
            birth_time: Birth time for dasha calculation
            moon_longitude: Birth moon longitude
            dispositor_map: Planet dispositor mapping

        Returns:
            Dasha score (0-1)
        """
        # Get active dasha if not provided
        if active_dasha is None:
            if birth_time and moon_longitude is not None:
                active_dasha = self._get_active_dasha_dict(
                    birth_time, moon_longitude, current_time
                )
            else:
                logger.warning("No dasha data available")
                return 0.4  # Default neutral score

        # Extract dasha lords
        maha_lord = self._name_to_id(active_dasha.get("mahadasha", ""))
        antar_lord = self._name_to_id(active_dasha.get("antardasha", ""))
        pratyantar_lord = self._name_to_id(active_dasha.get("pratyantara", ""))

        # Check direct match (strongest)
        if target_planet in [maha_lord, antar_lord, pratyantar_lord]:
            return 1.0

        # Check dispositor match
        if dispositor_map:
            if target_planet in dispositor_map:
                target_disp = dispositor_map[target_planet]
                if target_disp in [maha_lord, antar_lord]:
                    return 0.8

            # Check reverse - if dasha lord's dispositor is target
            for lord in [maha_lord, antar_lord]:
                if lord and lord in dispositor_map:
                    if dispositor_map[lord] == target_planet:
                        return 0.7

        # Check friendship
        friendship_score = self._calculate_friendship_score(
            target_planet, [maha_lord, antar_lord, pratyantar_lord]
        )
        if friendship_score > 0.5:
            return 0.6

        # Default neutral score
        return 0.4

    def check_dasha_sync(
        self,
        target_planet: int,
        birth_time: datetime,
        moon_longitude: float,
        current_time: datetime | None = None,
        dispositor_map: dict[int, int] | None = None,
    ) -> DashaSyncResult:
        """
        Comprehensive dasha synchronization check.

        Args:
            target_planet: Target planet ID
            birth_time: Birth time for dasha calculation
            moon_longitude: Birth moon longitude
            current_time: Current time (None = now)
            dispositor_map: Planet dispositor mapping

        Returns:
            DashaSyncResult with detailed analysis
        """
        if current_time is None:
            current_time = datetime.now(UTC)

        # Get current dasha periods
        current_periods = self.dasha_engine.get_current_dasha_periods(
            birth_time, moon_longitude, current_time, levels=3
        )

        if not current_periods:
            return DashaSyncResult(
                current_dasha="Unknown",
                current_antardasha="Unknown",
                current_pratyantara=None,
                target_planet=target_planet,
                sync_score=0.4,
                sync_level="neutral",
                reasons=["No dasha data available"],
            )

        # Extract period names
        maha = current_periods[0].planet if current_periods else "Unknown"
        antar = current_periods[1].planet if len(current_periods) > 1 else "Unknown"
        pratyantar = current_periods[2].planet if len(current_periods) > 2 else None

        # Convert to IDs
        maha_id = self._name_to_id(maha)
        antar_id = self._name_to_id(antar)
        pratyantar_id = self._name_to_id(pratyantar) if pratyantar else None

        # Analyze synchronization
        sync_score = 0.0
        sync_level = "neutral"
        reasons = []

        # Direct match check
        if target_planet == maha_id:
            sync_score = 1.0
            sync_level = "direct"
            reasons.append("Target is Mahadasha lord")
        elif target_planet == antar_id:
            sync_score = 0.95
            sync_level = "direct"
            reasons.append("Target is Antardasha lord")
        elif target_planet == pratyantar_id:
            sync_score = 0.85
            sync_level = "direct"
            reasons.append("Target is Pratyantara lord")

        # Dispositor check
        elif dispositor_map:
            disp_score, disp_reason = self._check_dispositor_sync(
                target_planet, [maha_id, antar_id], dispositor_map
            )
            if disp_score > 0.5:
                sync_score = disp_score
                sync_level = "friendly"
                reasons.append(disp_reason)

        # Friendship check
        if sync_score < 0.5:
            friend_score = self._calculate_friendship_score(
                target_planet, [maha_id, antar_id, pratyantar_id]
            )
            if friend_score > 0.5:
                sync_score = 0.6
                sync_level = "friendly"
                reasons.append("Friendly with dasha lords")
            elif friend_score < -0.5:
                sync_score = 0.2
                sync_level = "hostile"
                reasons.append("Hostile to dasha lords")
            else:
                sync_score = 0.4
                sync_level = "neutral"
                reasons.append("Neutral relationship")

        return DashaSyncResult(
            current_dasha=maha,
            current_antardasha=antar,
            current_pratyantara=pratyantar,
            target_planet=target_planet,
            sync_score=sync_score,
            sync_level=sync_level,
            reasons=reasons,
        )

    def get_best_transit_times(
        self,
        target_planet: int,
        birth_time: datetime,
        moon_longitude: float,
        days_ahead: int = 30,
    ) -> list[tuple[datetime, float]]:
        """
        Find best times for transit events based on dasha periods.

        Args:
            target_planet: Target planet ID
            birth_time: Birth time
            moon_longitude: Birth moon longitude
            days_ahead: How many days to look ahead

        Returns:
            List of (datetime, score) tuples for best times
        """
        best_times = []
        current_time = datetime.now(UTC)

        # Check dasha changes in the period
        for days in range(days_ahead):
            check_time = current_time + timedelta(days=days)

            # Get dasha at this time
            periods = self.dasha_engine.get_current_dasha_periods(
                birth_time, moon_longitude, check_time, levels=3
            )

            if periods:
                # Check if target planet rules any period
                for period in periods:
                    lord_id = self._name_to_id(period.planet)
                    if lord_id == target_planet:
                        # Higher score for higher level periods
                        if period.level == "mahadasha":
                            score = 1.0
                        elif period.level == "antardasha":
                            score = 0.9
                        else:
                            score = 0.8

                        best_times.append((check_time, score))
                        break

        # Sort by score
        best_times.sort(key=lambda x: x[1], reverse=True)

        return best_times[:10]  # Return top 10

    def _get_active_dasha_dict(
        self,
        birth_time: datetime,
        moon_longitude: float,
        current_time: datetime | None = None,
    ) -> dict:
        """
        Get active dasha as dictionary.

        Args:
            birth_time: Birth time
            moon_longitude: Birth moon longitude
            current_time: Current time

        Returns:
            Dict with dasha period names
        """
        if current_time is None:
            current_time = datetime.now(UTC)

        periods = self.dasha_engine.get_current_dasha_periods(
            birth_time, moon_longitude, current_time, levels=3
        )

        result = {}
        if periods:
            result["mahadasha"] = periods[0].planet
            if len(periods) > 1:
                result["antardasha"] = periods[1].planet
            if len(periods) > 2:
                result["pratyantara"] = periods[2].planet

        return result

    def _name_to_id(self, planet_name: str) -> int | None:
        """
        Convert planet name to ID.

        Args:
            planet_name: Planet name string

        Returns:
            Planet ID or None
        """
        if not planet_name:
            return None

        # Try direct lookup
        planet_id = PLANET_NAME_TO_ID.get(planet_name.upper())
        if planet_id:
            return planet_id

        # Try reverse lookup from constants
        for pid, pname in PLANET_NAMES.items():
            if pname.upper() == planet_name.upper():
                return pid

        return None

    def _calculate_friendship_score(
        self, target: int, dasha_lords: list[int | None]
    ) -> float:
        """
        Calculate friendship score between target and dasha lords.

        Args:
            target: Target planet ID
            dasha_lords: List of dasha lord IDs

        Returns:
            Friendship score (-1 to +1)
        """
        score = 0.0
        count = 0

        for lord in dasha_lords:
            if lord is None:
                continue

            # Check if friends
            if lord in PLANET_FRIENDSHIPS.get(target, []):
                score += 1.0
                count += 1
            elif target in PLANET_FRIENDSHIPS.get(lord, []):
                score += 1.0
                count += 1
            # Check if enemies (simplified - opposite of friends)
            elif lord in [4, 7] and target in [1, 2]:  # Nodes vs luminaries
                score -= 1.0
                count += 1
            else:
                # Neutral
                count += 1

        if count == 0:
            return 0.0

        return score / count

    def _check_dispositor_sync(
        self,
        target: int,
        dasha_lords: list[int | None],
        dispositor_map: dict[int, int],
    ) -> tuple[float, str]:
        """
        Check dispositor-based synchronization.

        Args:
            target: Target planet
            dasha_lords: Dasha lord IDs
            dispositor_map: Dispositor mapping

        Returns:
            Tuple of (score, reason)
        """
        # Check if target disposits dasha lords
        for lord in dasha_lords:
            if lord and lord in dispositor_map:
                if dispositor_map[lord] == target:
                    return (0.8, "Target disposits dasha lord")

        # Check if dasha lords disposit target
        if target in dispositor_map:
            target_disp = dispositor_map[target]
            if target_disp in dasha_lords:
                return (0.7, "Dasha lord disposits target")

        return (0.0, "")

    def explain_sync(self, result: DashaSyncResult) -> str:
        """
        Generate human-readable explanation of dasha sync.

        Args:
            result: DashaSyncResult to explain

        Returns:
            Explanation string
        """
        planet_name = PLANET_NAMES.get(result.target_planet, str(result.target_planet))

        if result.sync_level == "direct":
            return f"{planet_name} directly rules current {result.reasons[0].split()[-2]} period"
        elif result.sync_level == "friendly":
            return f"{planet_name} is friendly with {result.current_dasha}/{result.current_antardasha}"
        elif result.sync_level == "hostile":
            return f"{planet_name} is hostile to current dasha lords"
        else:
            return f"{planet_name} has neutral relationship with dasha"


# Quick scoring function for API use
def quick_dasha_score(
    target_planet: int, dasha_lord_name: str, antardasha_lord_name: str | None = None
) -> float:
    """
    Quick dasha score without full calculation.

    Args:
        target_planet: Target planet ID
        dasha_lord_name: Current mahadasha lord name
        antardasha_lord_name: Current antardasha lord name

    Returns:
        Dasha alignment score (0-1)
    """
    # Convert names to IDs
    dasha_id = PLANET_NAME_TO_ID.get(dasha_lord_name.upper())
    antar_id = (
        PLANET_NAME_TO_ID.get(antardasha_lord_name.upper())
        if antardasha_lord_name
        else None
    )

    # Direct match
    if target_planet == dasha_id:
        return 1.0
    if target_planet == antar_id:
        return 0.9

    # Friendship check
    if dasha_id and target_planet in PLANET_FRIENDSHIPS.get(dasha_id, []):
        return 0.7

    # Default
    return 0.4
