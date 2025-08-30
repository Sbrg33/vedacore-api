#!/usr/bin/env python3
"""
Initialize and register all system adapters
This module is called during API startup to register available systems
"""

import logging

from datetime import UTC

from .kp_adapter import KPSystemAdapter
from .kp_houses_adapter import KPHousesAdapter
from .kp_micro_adapter import KPMicroAdapter
from .kp_strategy_adapter import KPStrategyAdapter
from .registry import get_registry, set_default_system

logger = logging.getLogger(__name__)


def initialize_systems() -> dict[str, bool]:
    """
    Initialize and register all available system adapters

    Returns:
        Dict of system name to registration status
    """
    registry = get_registry()
    results = {}

    # Register KP System (always available)
    try:
        kp_adapter = KPSystemAdapter()
        registry.register(kp_adapter)
        results["KP"] = True
        logger.info("KP system adapter registered successfully")
    except Exception as e:
        logger.error(f"Failed to register KP adapter: {e}")
        results["KP"] = False

    # Register KP Houses adapter
    try:
        kp_houses_adapter = KPHousesAdapter()
        registry.register(kp_houses_adapter)
        results["KP_HOUSES"] = True
        logger.info("KP Houses adapter registered successfully")
    except Exception as e:
        logger.error(f"Failed to register KP Houses adapter: {e}")
        results["KP_HOUSES"] = False

    # Register KP Micro-Timing adapter (Phase 8)
    try:
        kp_micro_adapter = KPMicroAdapter()
        registry.register(kp_micro_adapter)
        results["KP_MICRO"] = True
        logger.info("KP Micro-Timing adapter registered successfully")
    except Exception as e:
        logger.error(f"Failed to register KP Micro adapter: {e}")
        results["KP_MICRO"] = False

    # Register KP Strategy adapter (Phase 9)
    try:
        kp_strategy_adapter = KPStrategyAdapter()
        registry.register(kp_strategy_adapter)
        results["KP_STRATEGY"] = True
        logger.info("KP Strategy adapter registered successfully")
    except Exception as e:
        logger.error(f"Failed to register KP Strategy adapter: {e}")
        results["KP_STRATEGY"] = False

    # Future: Register Chinese Astrology adapter
    # try:
    #     from .chinese_adapter import ChineseSystemAdapter
    #     chinese_adapter = ChineseSystemAdapter()
    #     registry.register(chinese_adapter)
    #     results["Chinese"] = True
    # except ImportError:
    #     logger.info("Chinese system adapter not available")
    #     results["Chinese"] = False

    # Future: Register Chaldean Numerology adapter
    # try:
    #     from .chaldean_adapter import ChaldeanSystemAdapter
    #     chaldean_adapter = ChaldeanSystemAdapter()
    #     registry.register(chaldean_adapter)
    #     results["Chaldean"] = True
    # except ImportError:
    #     logger.info("Chaldean system adapter not available")
    #     results["Chaldean"] = False

    # Future: Register Sound/Vibrational adapter
    # try:
    #     from .sound_adapter import SoundSystemAdapter
    #     sound_adapter = SoundSystemAdapter()
    #     registry.register(sound_adapter)
    #     results["Sound"] = True
    # except ImportError:
    #     logger.info("Sound system adapter not available")
    #     results["Sound"] = False

    # Set KP as default system
    if results.get("KP"):
        set_default_system("KP")
        logger.info("Set KP as default system")

    # Log summary
    registered = [k for k, v in results.items() if v]
    logger.info(f"System initialization complete. Registered: {registered}")

    return results


def get_system_status() -> dict:
    """
    Get status of all registered systems

    Returns:
        Dict with system information
    """
    registry = get_registry()
    systems = registry.list_systems()

    status = {
        "registered_systems": systems,
        "default_system": "KP",
        "total_systems": len(systems),
        "metadata": {},
    }

    # Get metadata for each system
    for system in systems:
        try:
            metadata = registry.get_metadata(system)
            status["metadata"][system] = metadata
        except Exception as e:
            logger.error(f"Error getting metadata for {system}: {e}")
            status["metadata"][system] = {"error": str(e)}

    return status


def validate_system_health() -> dict[str, bool]:
    """
    Validate health of all registered systems

    Returns:
        Dict of system name to health status
    """
    registry = get_registry()
    health = {}

    for system in registry.list_systems():
        try:
            adapter = registry.get(system)
            # Try a simple calculation to verify system works
            from datetime import datetime

            now = datetime.now(UTC)

            # Attempt to get a snapshot
            snapshot = adapter.snapshot(now)
            health[system] = snapshot is not None

        except Exception as e:
            logger.error(f"Health check failed for {system}: {e}")
            health[system] = False

    return health
