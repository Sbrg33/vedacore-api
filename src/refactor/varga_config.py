"""
Configuration for Varga (Divisional Charts) system.

Frozen dataclass configuration ensuring immutability and thread-safety
for varga calculations in production environments.
"""

import os

from dataclasses import dataclass, field

__all__ = ["VargaConfig", "get_varga_config"]


@dataclass(frozen=True)
class VargaConfig:
    """Immutable configuration for varga system."""

    # Performance settings
    enable_jit: bool = True
    enable_caching: bool = True
    cache_ttl_seconds: int = 300
    batch_size_limit: int = 10000

    # Range limits
    min_divisor: int = 2
    max_divisor: int = 300  # Allow research beyond D60

    # Data paths
    definitions_path: str = field(
        default_factory=lambda: os.environ.get(
            "VEDACORE_VARGA_DEFINITIONS", "data/varga_definitions/"
        )
    )

    # Classical scheme mappings
    # Maps divisor -> preferred classical scheme name
    classical_schemes: dict[int, str] = field(
        default_factory=lambda: {
            2: "hora_classical",  # Sun/Moon hora (implemented)
            3: "drekkana_classical",  # Trinal distribution (implemented)
            7: "saptamsa_classical",  # Children/progeny (implemented)
            9: "navamsa_classical",  # Spouse/dharma (implemented)
            10: "dasamsa_classical",  # Career/profession (implemented)
            12: "dwadasamsa_classical",  # Parents (implemented)
            16: "linear",  # Vehicles/comforts (use linear for now)
            20: "linear",  # Spiritual progress (use linear for now)
            24: "linear",  # Education/knowledge (use linear for now)
            27: "linear",  # Strengths/weaknesses (use linear for now)
            30: "trimsamsa_classical",  # Misfortunes (implemented as piecewise)
            40: "linear",  # Maternal lineage (use linear for now)
            45: "linear",  # Paternal lineage (use linear for now)
            60: "linear",  # Past karma (use linear for now)
        }
    )

    # Vimshopaka Bala weight sets
    # Different classical systems for strength calculation
    vimshopaka_sets: dict[str, dict[int, float]] = field(
        default_factory=lambda: {
            # Shadvarga (6 divisions)
            "shadvarga": {
                1: 6.0,  # D1 Rasi
                2: 2.0,  # D2 Hora
                3: 4.0,  # D3 Drekkana
                9: 5.0,  # D9 Navamsa
                12: 2.0,  # D12 Dwadasamsa
                30: 1.0,  # D30 Trimsamsa
            },
            # Saptavarga (7 divisions)
            "saptavarga": {
                1: 5.0,  # D1 Rasi
                2: 2.0,  # D2 Hora
                3: 3.0,  # D3 Drekkana
                7: 2.5,  # D7 Saptamsa
                9: 4.5,  # D9 Navamsa
                12: 2.0,  # D12 Dwadasamsa
                30: 1.0,  # D30 Trimsamsa
            },
            # Dashavarga (10 divisions) - BPHS weights (Total = 20.0)
            "dashavarga": {
                1: 3.0,  # D1 Rasi - 3 Rupas
                2: 1.5,  # D2 Hora - 1.5 Rupas
                3: 1.5,  # D3 Drekkana - 1.5 Rupas
                7: 1.5,  # D7 Saptamsa - 1.5 Rupas
                9: 3.0,  # D9 Navamsa - 3 Rupas
                10: 1.5,  # D10 Dasamsa - 1.5 Rupas
                12: 1.5,  # D12 Dwadasamsa - 1.5 Rupas
                16: 1.5,  # D16 Shodasamsa - 1.5 Rupas
                30: 1.0,  # D30 Trimsamsa - 1 Rupa (corrected from 1.5)
                60: 4.0,  # D60 Shashtyamsa - 4 Rupas (corrected from 5.0)
            },
            # Shodasavarga (16 divisions) - BPHS weights (Total = 20.0)
            "shodasavarga": {
                1: 3.5,  # D1 Rasi - 3.5 Kalas
                2: 1.0,  # D2 Hora - 1 Kala
                3: 1.0,  # D3 Drekkana - 1 Kala
                4: 0.5,  # D4 Chaturthamsa - 0.5 Kala
                7: 1.0,  # D7 Saptamsa - 1 Kala
                9: 3.0,  # D9 Navamsa - 3 Kalas
                10: 1.0,  # D10 Dasamsa - 1 Kala
                12: 1.0,  # D12 Dwadasamsa - 1 Kala
                16: 2.0,  # D16 Shodasamsa - 2 Kalas
                20: 0.5,  # D20 Vimsamsa - 0.5 Kala
                24: 0.5,  # D24 Chaturvimsamsa - 0.5 Kala
                27: 1.0,  # D27 Nakshatramsa - 1 Kala
                30: 1.0,  # D30 Trimsamsa - 1 Kala
                40: 0.5,  # D40 Khavedamsa - 0.5 Kala
                45: 0.5,  # D45 Akshavedamsa - 0.5 Kala
                60: 2.0,  # D60 Shashtyamsa - 2 Kalas (corrected from 4.0)
            },
        }
    )

    # Vargottama settings
    vargottama_check_vargas: list[int] = field(
        default_factory=lambda: [9, 10, 12, 30]  # Default vargas to check
    )
    vargottama_strength_bonus: float = 25.0  # Bonus strength for vargottama

    # Custom scheme limits
    max_custom_schemes: int = 100
    custom_scheme_name_pattern: str = r"^[a-zA-Z0-9_-]{3,50}$"

    # Research mode settings
    allow_experimental_vargas: bool = field(
        default_factory=lambda: os.environ.get(
            "VEDACORE_VARGA_EXPERIMENTAL", "false"
        ).lower()
        == "true"
    )

    # Logging and debugging
    log_unknown_schemes: bool = True
    trace_calculations: bool = False

    def get_scheme_for_divisor(self, divisor: int) -> str:
        """Get the preferred scheme for a given divisor.

        Args:
            divisor: Number of divisions

        Returns:
            Scheme name, defaults to "linear" if not specified
        """
        return self.classical_schemes.get(divisor, "linear")

    def get_vimshopaka_weights(self, set_name: str = "shadvarga") -> dict[int, float]:
        """Get Vimshopaka Bala weights for a specific set.

        Args:
            set_name: Name of the weight set

        Returns:
            Dictionary of divisor -> weight
        """
        return self.vimshopaka_sets.get(set_name, self.vimshopaka_sets["shadvarga"])

    def validate_divisor(self, divisor: int) -> bool:
        """Check if a divisor is within valid range.

        Args:
            divisor: Number to validate

        Returns:
            True if valid
        """
        return self.min_divisor <= divisor <= self.max_divisor

    def get_standard_vargas(self) -> list[int]:
        """Get list of standard divisional chart numbers.

        Returns:
            List of commonly used divisors
        """
        return sorted(self.classical_schemes.keys())

    def get_shodasavarga_divisors(self) -> list[int]:
        """Get the 16 divisors for Shodasavarga.

        Returns:
            List of 16 standard divisors
        """
        return [1, 2, 3, 4, 7, 9, 10, 12, 16, 20, 24, 27, 30, 40, 45, 60]


# Singleton instance
_config_instance: VargaConfig | None = None


def get_varga_config() -> VargaConfig:
    """Get singleton varga configuration instance.

    Returns:
        Frozen VargaConfig instance
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = VargaConfig()

    return _config_instance


def reset_config():
    """Reset configuration (for testing only)."""
    global _config_instance
    _config_instance = None
