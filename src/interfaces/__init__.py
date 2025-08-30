#!/usr/bin/env python3
"""
Multi-system plugin architecture for VedaCore
Provides extensible interfaces for different astrological and numerological systems
"""

from .registry import SystemRegistry, get_system, register_system
from .system_adapter import SystemAdapter, SystemChange, SystemSnapshot

__all__ = [
    "SystemAdapter",
    "SystemChange",
    "SystemRegistry",
    "SystemSnapshot",
    "get_system",
    "register_system",
]
