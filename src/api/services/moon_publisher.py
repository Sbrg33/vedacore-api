"""
Moon Chain Publisher Service - Background publisher for generic SSE topics.

Implements PM requirements:
- JWT-protected in-process publishing (no external API calls)
- Feature-flagged with MOON_PUBLISHER_ENABLED
- 2-5 second cadence for steady heartbeat
- Only publishes to allowed topics with proper ACLs
"""

import asyncio
import os
import random
import time

from datetime import timedelta
from typing import Any

from .stream_manager import stream_manager

# Configuration
MOON_PUBLISHER_ENABLED = os.getenv("MOON_PUBLISHER_ENABLED", "false").lower() == "true"
MOON_PUBLISHER_INTERVAL_MS = int(
    os.getenv("MOON_PUBLISHER_INTERVAL_MS", "2000")
)  # 2 seconds default
MOON_TOPIC = "kp.v1.moon.chain"


class MoonPublisher:
    """
    Background publisher for Moon chain data.

    Publishes real-time KP Moon calculations to generic streaming topics
    for live UI updates without requiring external publisher services.
    """

    def __init__(self):
        self.enabled = MOON_PUBLISHER_ENABLED
        self.interval_ms = MOON_PUBLISHER_INTERVAL_MS
        self.topic = MOON_TOPIC
        self.task: asyncio.Task | None = None
        self.should_stop = False
        self.sequence = 0  # For consumer dedupe (PM requirement)
        self.backoff_seconds = 0  # Exponential backoff on failures
        self.stats = {
            "published": 0,
            "errors": 0,
            "backoff_events": 0,
            "started_at": None,
            "last_publish": None,
            "last_error": None,
        }

    async def start(self) -> bool:
        """Start the background publisher if enabled."""
        if not self.enabled:
            return False

        if self.task and not self.task.done():
            return True  # Already running

        self.should_stop = False
        self.stats["started_at"] = time.time()
        self.task = asyncio.create_task(self._publisher_loop())
        return True

    async def stop(self) -> None:
        """Stop the background publisher gracefully."""
        self.should_stop = True
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def get_stats(self) -> dict[str, Any]:
        """Get publisher statistics."""
        return {
            "enabled": self.enabled,
            "running": self.task and not self.task.done() if self.task else False,
            "interval_ms": self.interval_ms,
            "topic": self.topic,
            **self.stats,
        }

    async def _publisher_loop(self) -> None:
        """Main publisher loop - runs in background."""
        import logging

        logger = logging.getLogger(__name__)

        logger.info(
            f"Moon publisher started: topic={self.topic} interval={self.interval_ms}ms"
        )

        while not self.should_stop:
            try:
                # Apply backoff if in error state (PM requirement: max 10s)
                if self.backoff_seconds > 0:
                    logger.info(
                        f"Moon publisher backing off for {self.backoff_seconds}s"
                    )
                    await asyncio.sleep(self.backoff_seconds)
                    self.stats["backoff_events"] += 1

                # Calculate current Moon position using VedaCore KP engine
                moon_data = await self._get_moon_chain_data()

                # Add sequence field for consumer dedupe (PM requirement)
                self.sequence += 1
                moon_data["seq"] = self.sequence

                # Publish to stream manager (in-process, no external calls)
                await stream_manager.publish(
                    self.topic, moon_data, event="moon_update", v=1
                )

                # Record metrics
                try:
                    from .metrics import streaming_metrics

                    streaming_metrics.record_stream_publish_event(self.topic)
                except ImportError:
                    pass  # Metrics not available

                # Update stats and reset backoff on success
                self.stats["published"] += 1
                self.stats["last_publish"] = time.time()
                self.stats["last_error"] = None
                self.backoff_seconds = 0  # Reset on success

                # Log periodic status (every 10 messages)
                if self.stats["published"] % 10 == 0:
                    logger.info(
                        f"Moon publisher: {self.stats['published']} messages published to {self.topic}"
                    )

            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                logger.error(f"Moon publisher error: {e}")

                # Exponential backoff (PM requirement: max 10s, don't replay old ticks)
                self.backoff_seconds = min(
                    10,
                    max(1, self.backoff_seconds * 2) if self.backoff_seconds > 0 else 1,
                )
                logger.warning(
                    f"Moon publisher will backoff for {self.backoff_seconds}s"
                )
                continue  # Skip sleep, go directly to backoff

            # Wait for next interval with jitter (PM requirement: ±250ms to avoid thundering herd)
            try:
                base_sleep = self.interval_ms / 1000.0
                jitter_ms = random.uniform(-250, 250) / 1000.0  # ±250ms jitter
                sleep_duration = max(0.1, base_sleep + jitter_ms)  # Minimum 100ms

                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

        logger.info("Moon publisher stopped")

    async def _get_moon_chain_data(self) -> dict[str, Any]:
        """
        Get current Moon KP chain data using VedaCore calculations.

        Returns real-time Moon degree, speed, and KP lord hierarchy.
        """
        try:
            # Import VedaCore facade for calculations
            from datetime import datetime
            from zoneinfo import ZoneInfo

            from refactor import facade

            # Get current UTC time
            now = datetime.now(ZoneInfo("UTC"))

            # Calculate Moon position and KP chain
            moon_data = facade.get_planet_position(now, planet_id=2)  # Moon = 2

            # Get KP lord changes for context
            lord_changes = facade.get_kp_lord_changes(
                now - timedelta(minutes=5),
                now + timedelta(minutes=5),
                planet_id=2,
                levels=("nl", "sl", "sl2"),
            )

            return {
                "timestamp": now.isoformat(),
                "degree": round(moon_data.get("degree", 0), 4),
                "speed": round(moon_data.get("speed", 0), 4),
                "zodiac_sign": moon_data.get("zodiac_sign", "unknown"),
                "nakshatra": moon_data.get("nakshatra", "unknown"),
                "kp_lords": {
                    "nl": moon_data.get("nl", "unknown"),
                    "sl": moon_data.get("sl", "unknown"),
                    "sl2": moon_data.get("sl2", "unknown"),
                },
                "upcoming_changes": len(lord_changes),
                "publisher": "moon_service",
                "flags": {"real_time": True, "kp_chain": True},
            }

        except Exception as e:
            # Fallback data if calculations fail
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Moon calculation failed, using fallback: {e}")

            return {
                "timestamp": datetime.now(ZoneInfo("UTC")).isoformat(),
                "degree": 0.0,
                "speed": 0.0,
                "zodiac_sign": "fallback",
                "nakshatra": "fallback",
                "kp_lords": {"nl": "fallback", "sl": "fallback", "sl2": "fallback"},
                "upcoming_changes": 0,
                "publisher": "moon_service_fallback",
                "flags": {"real_time": False, "kp_chain": False, "error": str(e)},
            }


# Singleton instance
moon_publisher = MoonPublisher()
