#!/usr/bin/env python3
"""
Transit Promise Checker - Birth Chart Promise Validation
Checks if planetary positions promise specific events or themes
"""

import logging

from dataclasses import dataclass

from .constants import PLANET_NAMES
from .kp_house_groups import HOUSE_GROUPS
from .kp_significators import get_house_significators, get_planet_significations

logger = logging.getLogger(__name__)


@dataclass
class PromiseResult:
    """Result of promise checking for a theme"""

    theme: str
    promising_planets: list[int]
    strength: float  # 0-1 indicating promise strength
    details: dict[int, list[str]]  # planet -> reasons

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "theme": self.theme,
            "promising_planets": self.promising_planets,
            "planet_names": [
                PLANET_NAMES.get(p, str(p)) for p in self.promising_planets
            ],
            "strength": round(self.strength, 2),
            "details": self.details,
        }


class TransitPromiseChecker:
    """
    Check if natal chart promises specific events or themes.
    Based on KP significator theory and house groupings.
    """

    # Financial/Trading themes and their house groups
    TRADING_THEMES = {
        "GAINS": [2, 5, 9, 11],  # Wealth, speculation, fortune, gains
        "LOSSES": [6, 8, 12],  # Debts, obstacles, losses
        "SPECULATION": [5, 8, 11],  # Speculation, sudden gains
        "INVESTMENT": [2, 4, 11],  # Assets, property, gains
        "VOLATILITY": [8, 12],  # Sudden events, uncertainty
        "STABILITY": [2, 4, 10],  # Wealth, assets, career
        "PARTNERSHIP": [7, 11],  # Business partnerships
        "COMPETITION": [6, 7],  # Enemies, competitors
    }

    # General life themes
    LIFE_THEMES = {
        "CAREER": HOUSE_GROUPS.get("career", [1, 10]),
        "FINANCE": HOUSE_GROUPS.get("wealth", [2, 11]),
        "HEALTH": HOUSE_GROUPS.get("health", [1, 6]),
        "RELATIONSHIP": HOUSE_GROUPS.get("marriage", [7]),
        "EDUCATION": HOUSE_GROUPS.get("education", [4, 9]),
        "TRAVEL": HOUSE_GROUPS.get("travel", [3, 9, 12]),
        "SPIRITUALITY": HOUSE_GROUPS.get("moksha", [4, 8, 12]),
        "CREATIVITY": [3, 5],
    }

    def __init__(self, natal_data: dict | None = None):
        """
        Initialize promise checker.

        Args:
            natal_data: Birth chart data with planet positions and houses
        """
        self.natal_data = natal_data
        self.planet_significations: dict[int, list[int]] = {}
        self.house_significators: dict[int, list[tuple[int, str, float]]] = {}

        if natal_data:
            self._analyze_natal_chart()

        logger.info("TransitPromiseChecker initialized")

    def check_promise(
        self,
        theme: str,
        planet_id: int | None = None,
        natal_data: dict | None = None,
    ) -> PromiseResult:
        """
        Check if chart promises a specific theme.

        Args:
            theme: Theme to check (e.g., 'GAINS', 'CAREER')
            planet_id: Specific planet to check (None = all planets)
            natal_data: Override natal data

        Returns:
            PromiseResult with details
        """
        if natal_data:
            self.natal_data = natal_data
            self._analyze_natal_chart()

        if not self.natal_data:
            logger.warning("No natal data available for promise checking")
            return PromiseResult(
                theme=theme, promising_planets=[], strength=0.3, details={}
            )

        # Get relevant houses for theme
        theme_houses = self._get_theme_houses(theme)
        if not theme_houses:
            return PromiseResult(
                theme=theme, promising_planets=[], strength=0.0, details={}
            )

        promising_planets = []
        details = {}

        if planet_id:
            # Check specific planet
            score, reasons = self._check_planet_promise(planet_id, theme_houses)
            if score > 0.3:
                promising_planets.append(planet_id)
                details[planet_id] = reasons
        else:
            # Check all planets
            for pid in range(1, 10):  # Planets 1-9
                score, reasons = self._check_planet_promise(pid, theme_houses)
                if score > 0.3:
                    promising_planets.append(pid)
                    details[pid] = reasons

        # Calculate overall strength
        strength = self._calculate_promise_strength(promising_planets, theme_houses)

        return PromiseResult(
            theme=theme,
            promising_planets=promising_planets,
            strength=strength,
            details=details,
        )

    def get_planet_promise_score(self, planet_id: int, theme: str = "FINANCE") -> float:
        """
        Get promise score for a specific planet and theme.

        Args:
            planet_id: Planet to check
            theme: Theme to evaluate

        Returns:
            Promise score (0-1)
        """
        result = self.check_promise(theme, planet_id)

        if planet_id in result.promising_planets:
            return 1.0  # Strong promise

        # Check if planet is connected via dispositor
        theme_houses = self._get_theme_houses(theme)
        if self._has_indirect_connection(planet_id, theme_houses):
            return 0.6  # Moderate promise

        return 0.3  # Weak/no promise

    def get_all_themes_for_planet(self, planet_id: int) -> list[str]:
        """
        Get all themes a planet promises.

        Args:
            planet_id: Planet to analyze

        Returns:
            List of theme names
        """
        promised_themes = []

        # Check trading themes
        for theme in self.TRADING_THEMES:
            result = self.check_promise(theme, planet_id)
            if planet_id in result.promising_planets:
                promised_themes.append(theme)

        # Check life themes
        for theme in self.LIFE_THEMES:
            result = self.check_promise(theme, planet_id)
            if planet_id in result.promising_planets:
                promised_themes.append(theme)

        return promised_themes

    def _analyze_natal_chart(self) -> None:
        """Analyze natal chart and cache significators"""
        if not self.natal_data:
            return

        planet_positions = self.natal_data.get("planets", {})
        house_cusps = self.natal_data.get("houses", [])

        if not planet_positions or not house_cusps:
            logger.warning("Incomplete natal data for analysis")
            return

        # Calculate planet significations
        for planet_id in range(1, 10):
            if planet_id in planet_positions:
                self.planet_significations[planet_id] = get_planet_significations(
                    planet_id, planet_positions, house_cusps
                )

        # Calculate house significators
        for house in range(1, 13):
            self.house_significators[house] = get_house_significators(
                house, planet_positions, house_cusps
            )

    def _get_theme_houses(self, theme: str) -> list[int]:
        """
        Get houses relevant to a theme.

        Args:
            theme: Theme name

        Returns:
            List of house numbers
        """
        # Check trading themes first
        if theme in self.TRADING_THEMES:
            return self.TRADING_THEMES[theme]

        # Check life themes
        if theme in self.LIFE_THEMES:
            return self.LIFE_THEMES[theme]

        # Check standard house groups
        if theme.lower() in HOUSE_GROUPS:
            return HOUSE_GROUPS[theme.lower()]

        # Default to empty
        return []

    def _check_planet_promise(
        self, planet_id: int, theme_houses: list[int]
    ) -> tuple[float, list[str]]:
        """
        Check if planet promises theme houses.

        Args:
            planet_id: Planet to check
            theme_houses: Houses representing the theme

        Returns:
            Tuple of (score, reasons)
        """
        score = 0.0
        reasons = []

        # Get planet's significations
        signified_houses = self.planet_significations.get(planet_id, [])

        # Check direct signification
        common_houses = set(signified_houses) & set(theme_houses)
        if common_houses:
            score += 0.5 * len(common_houses) / len(theme_houses)
            reasons.append(f"Signifies houses {common_houses}")

        # Check if planet is significator of theme houses
        for house in theme_houses:
            significators = self.house_significators.get(house, [])
            for sig_planet, level, strength in significators:
                if sig_planet == planet_id:
                    score += strength / 100.0 * 0.5
                    reasons.append(f"{level} of house {house}")
                    break

        # Normalize score to [0, 1]
        score = min(1.0, score)

        return score, reasons

    def _has_indirect_connection(self, planet_id: int, theme_houses: list[int]) -> bool:
        """
        Check if planet has indirect connection to theme houses.

        Args:
            planet_id: Planet to check
            theme_houses: Theme house numbers

        Returns:
            True if indirect connection exists
        """
        # Check if planet aspects or is aspected by significators
        for house in theme_houses:
            significators = self.house_significators.get(house, [])
            for sig_planet, _, _ in significators[:3]:  # Top 3 significators
                # In KP, planets in same nakshatra are connected
                # This is simplified - would need nakshatra data
                if abs(sig_planet - planet_id) in [3, 6]:  # Trine positions
                    return True

        return False

    def _calculate_promise_strength(
        self, promising_planets: list[int], theme_houses: list[int]
    ) -> float:
        """
        Calculate overall promise strength.

        Args:
            promising_planets: List of planets that promise theme
            theme_houses: Houses for the theme

        Returns:
            Strength score (0-1)
        """
        if not promising_planets:
            return 0.0

        # More planets = stronger promise
        planet_factor = min(1.0, len(promising_planets) / 3.0)

        # Check if key significators are involved
        key_factor = 0.0
        for house in theme_houses:
            significators = self.house_significators.get(house, [])
            if significators:
                top_sig = significators[0][0]  # Strongest significator
                if top_sig in promising_planets:
                    key_factor += 1.0 / len(theme_houses)

        # Combine factors
        strength = 0.6 * planet_factor + 0.4 * key_factor

        return min(1.0, strength)

    def explain_promise(self, result: PromiseResult) -> str:
        """
        Generate human-readable explanation of promise.

        Args:
            result: PromiseResult to explain

        Returns:
            Explanation string
        """
        if not result.promising_planets:
            return f"No strong promise for {result.theme}"

        planet_names = [PLANET_NAMES.get(p, str(p)) for p in result.promising_planets]

        explanation = f"{result.theme} promised by {', '.join(planet_names)}"

        if result.strength > 0.7:
            explanation += " (strong indication)"
        elif result.strength > 0.5:
            explanation += " (moderate indication)"
        else:
            explanation += " (weak indication)"

        return explanation


# Simplified promise checker for quick scoring
def quick_promise_score(planet_id: int, theme: str = "FINANCE") -> float:
    """
    Quick promise score without full natal analysis.
    Based on natural significations.

    Args:
        planet_id: Planet to check
        theme: Theme to evaluate

    Returns:
        Promise score (0-1)
    """
    # Natural significations (simplified)
    natural_promises = {
        "GAINS": [3, 6],  # Jupiter, Venus - natural benefics
        "LOSSES": [8, 9, 4],  # Saturn, Mars, Rahu - natural malefics
        "SPECULATION": [5, 4],  # Mercury, Rahu - quick changes
        "STABILITY": [3, 8],  # Jupiter, Saturn - slow planets
        "FINANCE": [2, 6, 3],  # Moon (wealth), Venus (luxury), Jupiter (fortune)
        "CAREER": [1, 8, 10],  # Sun (authority), Saturn (work), MC ruler
    }

    theme_planets = natural_promises.get(theme, [])

    if planet_id in theme_planets:
        return 1.0
    elif planet_id in [3, 6]:  # Natural benefics
        return 0.6
    else:
        return 0.3
