#!/usr/bin/env python3
"""
House calculation configuration with initialization guards
Ensures topocentric and sidereal modes are set once at startup
"""

import os
import threading

import swisseph as swe

# Thread lock for configuration
_config_lock = threading.Lock()

# Configuration state
_config_initialized = False
_topocentric_enabled = False
_topocentric_params: tuple[float, float, float] | None = None

# Environment-based configuration
HOUSE_TOPO_ENABLED = os.environ.get("HOUSE_TOPO_ENABLED", "false").lower() == "true"
HOUSE_TOPO_LON = float(os.environ.get("HOUSE_TOPO_LON", "0.0"))
HOUSE_TOPO_LAT = float(os.environ.get("HOUSE_TOPO_LAT", "0.0"))
HOUSE_TOPO_ELEV = float(os.environ.get("HOUSE_TOPO_ELEV", "0.0"))


def initialize_house_config() -> None:
    """
    Initialize house calculation configuration.
    This should be called once at process startup.
    Sets topocentric mode if enabled via environment variables.
    """
    global _config_initialized, _topocentric_enabled, _topocentric_params

    with _config_lock:
        if _config_initialized:
            return  # Already initialized

        # Set topocentric mode if enabled
        if HOUSE_TOPO_ENABLED:
            swe.set_topo(HOUSE_TOPO_LON, HOUSE_TOPO_LAT, HOUSE_TOPO_ELEV)
            _topocentric_enabled = True
            _topocentric_params = (HOUSE_TOPO_LON, HOUSE_TOPO_LAT, HOUSE_TOPO_ELEV)
            print(
                f"House calculations: Topocentric mode enabled at "
                f"lon={HOUSE_TOPO_LON}, lat={HOUSE_TOPO_LAT}, elev={HOUSE_TOPO_ELEV}m"
            )
        else:
            _topocentric_enabled = False
            _topocentric_params = None
            print("House calculations: Geocentric mode (default)")

        _config_initialized = True


def is_topocentric_enabled() -> bool:
    """Check if topocentric mode is enabled"""
    return _topocentric_enabled


def get_topocentric_params() -> tuple[float, float, float] | None:
    """Get topocentric parameters if enabled"""
    return _topocentric_params


def ensure_config_initialized() -> None:
    """
    Ensure configuration is initialized.
    Raises RuntimeError if attempting to use before initialization.
    """
    if not _config_initialized:
        raise RuntimeError(
            "House configuration not initialized. "
            "Call initialize_house_config() at process startup."
        )


def prevent_runtime_change() -> None:
    """
    Guard against runtime configuration changes.
    This should be called before any operation that might change global state.
    """
    if _config_initialized:
        raise RuntimeError(
            "Cannot change house configuration after initialization. "
            "Topocentric and sidereal modes must be set once at startup."
        )
