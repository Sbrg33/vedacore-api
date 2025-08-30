"""
Advisory SystemAdapter Protocol for Phase 11 modules

Defines the contract for advisory system adapters that wrap existing
modules/* components to bring them into compliance with CLAUDE.md architecture.
"""

from collections.abc import Mapping
from typing import Any, Protocol


class AdvisorySystemAdapter(Protocol):
    """
    Protocol for advisory system adapters

    Each adapter wraps an existing module/* component and provides
    a standardized interface for the registry system.
    """

    # Identity
    id: str  # 'panchanga', 'aspects', 'jaimini', 'vedic_strength', 'yogas', 'transits'
    version: str  # semver for traceability
    module_path: str  # original module path for reference

    def compute(self, ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Execute the advisory calculation

        Args:
            ctx: Context dictionary containing:
                - timestamp: datetime (required)
                - latitude: float (optional)
                - longitude: float (optional)
                - Additional system-specific parameters

        Returns:
            Dictionary with calculation results and metadata:
            {
                "data": {...},           # Main calculation results
                "meta": {
                    "adapter_id": str,
                    "adapter_version": str,
                    "compute_time_ms": float,
                    "cache_hit": bool
                }
            }
        """
        ...

    def explain(self, output: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Provide human-readable explanations of the output

        Args:
            output: Result from compute() method

        Returns:
            Dictionary with explanations and interpretations
        """
        ...

    def schema(self) -> Mapping[str, Any]:
        """
        Return JSON schema for inputs and outputs

        Returns:
            Dictionary with input_schema and output_schema definitions
        """
        ...

    def dependencies(self) -> list[str]:
        """
        Return list of other adapter IDs this adapter depends on

        Returns:
            List of adapter ID strings this adapter reads from
        """
        ...

    def health_check(self) -> Mapping[str, Any]:
        """
        Check adapter health and readiness

        Returns:
            Dictionary with health status and any issues
        """
        ...


class AdvisoryAdapterRegistry:
    """
    Registry for managing advisory system adapters

    Provides centralized access to all Phase 11 advisory components
    through the SystemAdapter protocol.
    """

    def __init__(self):
        self._adapters: dict[str, AdvisorySystemAdapter] = {}
        self._load_order: list[str] = []

    def register(self, adapter: AdvisorySystemAdapter) -> None:
        """
        Register an advisory adapter

        Args:
            adapter: Implementation of AdvisorySystemAdapter protocol
        """
        self._adapters[adapter.id] = adapter
        if adapter.id not in self._load_order:
            self._load_order.append(adapter.id)

    def get(self, adapter_id: str) -> AdvisorySystemAdapter:
        """
        Get adapter by ID

        Args:
            adapter_id: String ID of the adapter

        Returns:
            Adapter instance

        Raises:
            KeyError: If adapter not found
        """
        if adapter_id not in self._adapters:
            raise KeyError(
                f"Advisory adapter '{adapter_id}' not found. Available: {list(self._adapters.keys())}"
            )
        return self._adapters[adapter_id]

    def list_adapters(self) -> list[str]:
        """Return list of registered adapter IDs"""
        return list(self._adapters.keys())

    def get_dependency_order(self) -> list[str]:
        """
        Get adapters in dependency order (dependencies first)

        Returns:
            List of adapter IDs in execution order
        """
        # Simple topological sort based on dependencies
        ordered = []
        remaining = set(self._adapters.keys())

        while remaining:
            # Find adapters with no unresolved dependencies
            ready = []
            for adapter_id in remaining:
                adapter = self._adapters[adapter_id]
                deps = set(adapter.dependencies())
                if deps.issubset(set(ordered)):
                    ready.append(adapter_id)

            if not ready:
                # Circular dependency or missing dependency
                # Add remaining in registration order
                ready = sorted(remaining, key=lambda x: self._load_order.index(x))

            for adapter_id in ready:
                ordered.append(adapter_id)
                remaining.remove(adapter_id)

        return ordered

    def health_check_all(self) -> Mapping[str, Any]:
        """
        Run health check on all registered adapters

        Returns:
            Dictionary with health status for each adapter
        """
        results = {}
        for adapter_id, adapter in self._adapters.items():
            try:
                results[adapter_id] = adapter.health_check()
            except Exception as e:
                results[adapter_id] = {
                    "status": "error",
                    "error": str(e),
                    "healthy": False,
                }

        return {
            "overall_healthy": all(r.get("healthy", False) for r in results.values()),
            "adapters": results,
        }


# Global registry instance
advisory_registry = AdvisoryAdapterRegistry()
