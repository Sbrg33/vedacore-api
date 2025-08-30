#!/usr/bin/env python3
"""
Transit Moon Engine - KP Chain Tracking
Tracks Moon's NL/SL/SSL changes per minute with caching for real-time event detection
"""

import logging

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .constants import PLANET_NAMES
from .facade import get_positions

MOON_ID = 2  # Moon planet ID

logger = logging.getLogger(__name__)


@dataclass
class MoonChainData:
    """Moon's KP chain at a specific time"""

    timestamp: datetime
    longitude: float
    speed: float
    sign: int
    nakshatra: int
    pada: int
    nl: int  # Nakshatra Lord
    sl: int  # Sub Lord
    ssl: int  # Sub-Sub Lord (SL2)
    s3: int | None = None  # S3 if needed

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "longitude": round(self.longitude, 4),
            "speed": round(self.speed, 4),
            "sign": self.sign,
            "nakshatra": self.nakshatra,
            "pada": self.pada,
            "nl": self.nl,
            "nl_name": PLANET_NAMES.get(self.nl, str(self.nl)),
            "sl": self.sl,
            "sl_name": PLANET_NAMES.get(self.sl, str(self.sl)),
            "ssl": self.ssl,
            "ssl_name": PLANET_NAMES.get(self.ssl, str(self.ssl)),
            "s3": self.s3,
            "s3_name": PLANET_NAMES.get(self.s3, str(self.s3)) if self.s3 else None,
        }

    def get_signature(self) -> str:
        """Create hashable signature for deduplication"""
        sig = f"MOON_{self.nl}_{self.sl}_{self.ssl}"
        if self.s3:
            sig += f"_{self.s3}"
        return sig

    def get_chain_dict(self) -> dict[str, int]:
        """Get chain as simple dict for gate calculations"""
        chain = {"NL": self.nl, "SL": self.sl, "SSL": self.ssl}
        if self.s3:
            chain["S3"] = self.s3
        return chain


class MoonTransitEngine:
    """
    Track Moon's KP chain changes per minute with caching.
    Performance target: < 3ms for cached, < 10ms for fresh calculation.
    """

    def __init__(self, cache_ttl_seconds: int = 60, enable_s3: bool = False):
        """
        Initialize Moon transit engine.

        Args:
            cache_ttl_seconds: Cache TTL (default 60s = 1 minute)
            enable_s3: Whether to calculate S3 level (deeper subdivision)
        """
        self.cache_ttl = cache_ttl_seconds
        self.enable_s3 = enable_s3

        # Minute-based cache
        self._cache: dict[int, MoonChainData] = {}  # minute_bucket -> data
        self._last_chain: MoonChainData | None = None
        self._change_history: list[tuple[datetime, str, str]] = (
            []
        )  # (time, old_sig, new_sig)

        logger.info(
            f"MoonTransitEngine initialized: cache_ttl={cache_ttl_seconds}s, s3={enable_s3}"
        )

    def get_moon_chain(self, ts: datetime) -> MoonChainData:
        """
        Get Moon's KP chain at given timestamp.

        Args:
            ts: UTC timestamp

        Returns:
            MoonChainData with all KP levels
        """
        # Ensure UTC
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        # Check cache (minute bucket)
        minute_bucket = int(ts.timestamp() / 60)

        if minute_bucket in self._cache:
            logger.debug(f"Cache hit for minute {minute_bucket}")
            return self._cache[minute_bucket]

        # Calculate fresh
        logger.debug(f"Calculating fresh Moon chain for {ts}")

        # Get Moon position with KP lords already calculated
        moon_data = get_positions(ts, planet_id=MOON_ID, apply_kp_offset=False)

        # Create chain data
        chain_data = MoonChainData(
            timestamp=ts,
            longitude=moon_data.position,
            speed=moon_data.speed,
            sign=moon_data.sign,
            nakshatra=moon_data.nakshatra,
            pada=moon_data.pada,
            nl=moon_data.nl,  # Nakshatra Lord
            sl=moon_data.sl,  # Sub Lord
            ssl=moon_data.sl2,  # Sub-Sub Lord (sl2 in PlanetData)
        )

        # Calculate S3 if enabled (would need deeper subdivision logic)
        if self.enable_s3:
            # S3 calculation would go here - using simplified approach for now
            # In production, this would use Vimshottari subdivision to S3 level
            chain_data.s3 = self._calculate_s3(moon_data.position)

        # Update cache
        self._cache[minute_bucket] = chain_data

        # Clean old cache entries
        self._clean_cache(minute_bucket)

        # Track changes
        self._track_change(chain_data)

        return chain_data

    def get_moon_signature(self, ts: datetime) -> str:
        """
        Get Moon chain signature for deduplication.

        Args:
            ts: UTC timestamp

        Returns:
            Hashable signature string
        """
        chain = self.get_moon_chain(ts)
        return chain.get_signature()

    def detect_chain_change(self, ts: datetime) -> tuple[str, str] | None:
        """
        Detect if Moon's KP chain has changed since last check.

        Args:
            ts: UTC timestamp

        Returns:
            Tuple of (old_signature, new_signature) if changed, None otherwise
        """
        current = self.get_moon_chain(ts)

        if self._last_chain is None:
            self._last_chain = current
            return None

        old_sig = self._last_chain.get_signature()
        new_sig = current.get_signature()

        if old_sig != new_sig:
            self._last_chain = current
            return (old_sig, new_sig)

        return None

    def get_next_change_estimate(self, ts: datetime) -> datetime | None:
        """
        Estimate when next KP lord change will occur.

        Args:
            ts: Current UTC timestamp

        Returns:
            Estimated timestamp of next change, or None if stationary
        """
        chain = self.get_moon_chain(ts)

        if abs(chain.speed) < 0.001:  # Nearly stationary
            return None

        # Moon moves ~13.2° per day on average
        # Each nakshatra is 13.333° (360/27)
        # Each sub-lord division is approximately 0.888° to 3.333° (unequal)

        # Simplified estimate: check every 20 minutes for SL changes
        # In production, would calculate exact boundary distance
        avg_minutes_per_sl = 20 if chain.speed > 12 else 25

        return ts + timedelta(minutes=avg_minutes_per_sl)

    def get_recent_changes(self, hours: int = 24) -> list[dict]:
        """
        Get recent Moon chain changes.

        Args:
            hours: How many hours back to look

        Returns:
            List of change events
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        recent = []
        for ts, old_sig, new_sig in self._change_history:
            if ts > cutoff:
                recent.append(
                    {
                        "timestamp": ts.isoformat(),
                        "old_signature": old_sig,
                        "new_signature": new_sig,
                    }
                )

        return recent

    def _calculate_s3(self, longitude: float) -> int:
        """
        Calculate S3 (deeper sub-lord) for Moon.
        Simplified implementation - would need full Vimshottari logic.

        Args:
            longitude: Moon's longitude

        Returns:
            S3 lord planet ID
        """
        # This is a placeholder - actual S3 calculation requires
        # recursive Vimshottari subdivision to 4th level
        # For now, return a deterministic value based on position

        # Rough approximation: 249 sub-divisions in zodiac
        # Each is 360/249 = 1.446 degrees
        sub_index = int(longitude / 1.446) % 9

        # Map to planet IDs in Vimshottari sequence
        vimshottari_sequence = [7, 6, 1, 2, 9, 4, 3, 8, 5]  # Ketu starts
        return vimshottari_sequence[sub_index]

    def _track_change(self, chain_data: MoonChainData) -> None:
        """Track chain changes for history"""
        if (
            self._last_chain
            and chain_data.get_signature() != self._last_chain.get_signature()
        ):
            self._change_history.append(
                (
                    chain_data.timestamp,
                    self._last_chain.get_signature(),
                    chain_data.get_signature(),
                )
            )

            # Keep only last 100 changes
            if len(self._change_history) > 100:
                self._change_history = self._change_history[-100:]

    def _clean_cache(self, current_bucket: int) -> None:
        """Clean old cache entries"""
        # Keep last 5 minutes
        cutoff_bucket = current_bucket - 5

        keys_to_remove = [k for k in self._cache if k < cutoff_bucket]
        for k in keys_to_remove:
            del self._cache[k]

    def clear_cache(self) -> None:
        """Clear all cached data"""
        self._cache.clear()
        self._last_chain = None
        logger.info("Moon transit cache cleared")

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring"""
        return {
            "cache_entries": len(self._cache),
            "change_history_count": len(self._change_history),
            "last_chain": self._last_chain.to_dict() if self._last_chain else None,
        }


# Module-level singleton for efficiency
_moon_engine: MoonTransitEngine | None = None


def get_moon_engine() -> MoonTransitEngine:
    """Get or create singleton Moon engine"""
    global _moon_engine
    if _moon_engine is None:
        _moon_engine = MoonTransitEngine()
    return _moon_engine


def get_current_moon_chain() -> MoonChainData:
    """Convenience function to get current Moon chain"""
    engine = get_moon_engine()
    return engine.get_moon_chain(datetime.now(UTC))
