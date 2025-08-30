#!/usr/bin/env python3
"""
System Registry for managing multiple astrological/numerological systems
Provides registration, discovery, and routing for system adapters
"""

import logging
import threading

from .system_adapter import SystemAdapter

logger = logging.getLogger(__name__)


class SystemRegistry:
    """
    Thread-safe registry for system adapters
    Manages registration and retrieval of different calculation systems
    """

    def __init__(self):
        self._adapters: dict[str, SystemAdapter] = {}
        self._lock = threading.Lock()
        self._default_system = "KP"
        self._initialization_order: list[str] = []

    def register(self, adapter: SystemAdapter, force: bool = False) -> bool:
        """
        Register a system adapter

        Args:
            adapter: SystemAdapter implementation
            force: If True, overwrite existing adapter

        Returns:
            True if registered successfully

        Raises:
            ValueError: If adapter already exists and force=False
        """
        with self._lock:
            system_name = adapter.system

            if system_name in self._adapters and not force:
                raise ValueError(
                    f"System '{system_name}' already registered. Use force=True to override."
                )

            # Validate adapter implements protocol
            if not hasattr(adapter, "snapshot") or not hasattr(adapter, "changes"):
                raise TypeError(
                    f"Adapter for '{system_name}' does not implement SystemAdapter protocol"
                )

            self._adapters[system_name] = adapter
            if system_name not in self._initialization_order:
                self._initialization_order.append(system_name)

            logger.info(f"Registered system adapter: {system_name} v{adapter.version}")

            # Record metrics
            try:
                from refactor.monitoring import set_feature_flag

                set_feature_flag(f"system_{system_name.lower()}_enabled", True)
            except ImportError:
                pass

            return True

    def unregister(self, system: str) -> bool:
        """
        Unregister a system adapter

        Args:
            system: System name to unregister

        Returns:
            True if unregistered successfully, False if not found
        """
        with self._lock:
            if system in self._adapters:
                del self._adapters[system]
                if system in self._initialization_order:
                    self._initialization_order.remove(system)
                logger.info(f"Unregistered system adapter: {system}")
                return True
            return False

    def get(self, system: str) -> SystemAdapter | None:
        """
        Get a registered system adapter

        Args:
            system: System name

        Returns:
            SystemAdapter if found, None otherwise
        """
        with self._lock:
            return self._adapters.get(system)

    def get_or_default(self, system: str | None = None) -> SystemAdapter:
        """
        Get a system adapter or return the default

        Args:
            system: Optional system name

        Returns:
            SystemAdapter for the requested system or default

        Raises:
            ValueError: If system not found and no default registered
        """
        if system is None:
            system = self._default_system

        adapter = self.get(system)
        if adapter is None:
            # Try default
            adapter = self.get(self._default_system)
            if adapter is None:
                raise ValueError(
                    f"System '{system}' not found and no default system registered"
                )

        return adapter

    def list_systems(self) -> list[str]:
        """
        List all registered systems

        Returns:
            List of system names
        """
        with self._lock:
            return list(self._adapters.keys())

    def get_all(self) -> dict[str, SystemAdapter]:
        """
        Get all registered adapters

        Returns:
            Dictionary of system name to adapter
        """
        with self._lock:
            return self._adapters.copy()

    def set_default(self, system: str):
        """
        Set the default system

        Args:
            system: System name to use as default

        Raises:
            ValueError: If system not registered
        """
        if system not in self._adapters:
            raise ValueError(f"Cannot set default to unregistered system '{system}'")
        self._default_system = system
        logger.info(f"Set default system to: {system}")

    def get_metadata(self, system: str) -> dict:
        """
        Get metadata for a specific system

        Args:
            system: System name

        Returns:
            System metadata dictionary

        Raises:
            ValueError: If system not found
        """
        adapter = self.get(system)
        if adapter is None:
            raise ValueError(f"System '{system}' not found")
        return adapter.get_metadata()

    def get_all_metadata(self) -> dict[str, dict]:
        """
        Get metadata for all registered systems

        Returns:
            Dictionary of system name to metadata
        """
        with self._lock:
            return {
                name: adapter.get_metadata() for name, adapter in self._adapters.items()
            }

    def validate_system(self, system: str) -> bool:
        """
        Check if a system is registered

        Args:
            system: System name to check

        Returns:
            True if registered, False otherwise
        """
        return system in self._adapters

    def clear(self):
        """Clear all registered adapters (use with caution)"""
        with self._lock:
            self._adapters.clear()
            self._initialization_order.clear()
            logger.warning("Cleared all system adapters from registry")


# Global registry instance
_registry = SystemRegistry()


# Convenience functions for module-level access
def register_system(adapter: SystemAdapter, force: bool = False) -> bool:
    """Register a system adapter in the global registry"""
    return _registry.register(adapter, force)


def get_system(system: str) -> SystemAdapter | None:
    """Get a system adapter from the global registry"""
    return _registry.get(system)


def get_system_or_default(system: str | None = None) -> SystemAdapter:
    """Get a system adapter or the default from the global registry"""
    return _registry.get_or_default(system)


def list_systems() -> list[str]:
    """List all registered systems in the global registry"""
    return _registry.list_systems()


def set_default_system(system: str):
    """Set the default system in the global registry"""
    _registry.set_default(system)


def validate_system(system: str) -> bool:
    """Check if a system is registered in the global registry"""
    return _registry.validate_system(system)


def get_registry() -> SystemRegistry:
    """Get the global registry instance"""
    return _registry
