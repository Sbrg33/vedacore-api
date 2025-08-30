#!/usr/bin/env python3
"""
System Adapter Protocol for multi-system support
Defines the interface all astrological/numerological systems must implement
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Protocol


class SystemType(Enum):
    """Supported system types"""

    KP = "KP"  # Krishnamurti Paddhati
    CHINESE = "Chinese"  # Chinese Astrology
    CHALDEAN = "Chaldean"  # Chaldean Numerology
    SOUND = "Sound"  # Sound/Vibrational System
    VEDIC = "Vedic"  # Traditional Vedic (future)
    WESTERN = "Western"  # Western Astrology (future)
    PYTHAGOREAN = "Pythagorean"  # Pythagorean Numerology (future)


@dataclass
class SystemSnapshot:
    """Complete system state at a point in time"""

    system: str
    timestamp: datetime
    data: dict[str, Any]
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "system": self.system,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata or {},
        }


@dataclass
class SystemChange:
    """Represents a change in system state"""

    system: str
    timestamp: datetime
    change_type: str
    from_value: Any
    to_value: Any
    entity: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "system": self.system,
            "timestamp": self.timestamp.isoformat(),
            "change_type": self.change_type,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "entity": self.entity,
            "metadata": self.metadata or {},
        }


class SystemAdapter(Protocol):
    """
    Protocol that all system adapters must implement
    This ensures consistent interface across all astrological/numerological systems
    """

    @property
    def system(self) -> str:
        """System identifier (e.g., 'KP', 'Chinese', 'Chaldean', 'Sound')"""
        ...

    @property
    def version(self) -> str:
        """Adapter version"""
        ...

    @property
    def description(self) -> str:
        """Human-readable system description"""
        ...

    def snapshot(self, ts_utc: datetime) -> SystemSnapshot:
        """
        Get complete system state at a specific timestamp

        Args:
            ts_utc: UTC timestamp for calculation

        Returns:
            SystemSnapshot containing all system data at the timestamp
        """
        ...

    def changes(self, day_utc: date) -> list[SystemChange]:
        """
        Get all changes for a given day

        Args:
            day_utc: UTC date for which to find changes

        Returns:
            List of SystemChange objects for the day
        """
        ...

    def calculate(self, ts_utc: datetime, entity: str, **kwargs) -> dict[str, Any]:
        """
        Perform system-specific calculation

        Args:
            ts_utc: UTC timestamp for calculation
            entity: Entity to calculate for (e.g., planet_id, name, number)
            **kwargs: System-specific parameters

        Returns:
            Dictionary with calculation results
        """
        ...

    def validate_input(self, entity: str, **kwargs) -> bool:
        """
        Validate input parameters for the system

        Args:
            entity: Entity to validate
            **kwargs: Additional parameters to validate

        Returns:
            True if valid, raises ValueError if invalid
        """
        ...

    def get_metadata(self) -> dict[str, Any]:
        """
        Get system metadata and configuration

        Returns:
            Dictionary with system metadata
        """
        ...


class BaseSystemAdapter(ABC):
    """
    Base implementation of SystemAdapter with common functionality
    Concrete adapters should inherit from this class
    """

    def __init__(self, system: str, version: str = "1.0.0"):
        self._system = system
        self._version = version
        self._cache_enabled = True
        self._metrics_enabled = True

    @property
    def system(self) -> str:
        return self._system

    @property
    def version(self) -> str:
        return self._version

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    def snapshot(self, ts_utc: datetime) -> SystemSnapshot:
        pass

    @abstractmethod
    def changes(self, day_utc: date) -> list[SystemChange]:
        pass

    @abstractmethod
    def calculate(self, ts_utc: datetime, entity: str, **kwargs) -> dict[str, Any]:
        pass

    def validate_input(self, entity: str, **kwargs) -> bool:
        """Default validation - override in subclasses"""
        if not entity:
            raise ValueError("Entity cannot be empty")
        return True

    def get_metadata(self) -> dict[str, Any]:
        """Default metadata - override in subclasses"""
        return {
            "system": self.system,
            "version": self.version,
            "description": self.description,
            "cache_enabled": self._cache_enabled,
            "metrics_enabled": self._metrics_enabled,
        }

    def enable_cache(self, enabled: bool = True):
        """Enable or disable caching for this adapter"""
        self._cache_enabled = enabled

    def enable_metrics(self, enabled: bool = True):
        """Enable or disable metrics for this adapter"""
        self._metrics_enabled = enabled
