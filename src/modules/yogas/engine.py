"""
Yoga detection engine with DSL support.
Evaluates planetary combinations based on YAML rule definitions.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from config.feature_flags import require_feature


@dataclass
class YogaResult:
    """Result of a yoga evaluation."""

    name: str
    category: str
    strength: float  # 0-100
    active: bool
    planets_involved: list[int]
    houses_involved: list[int]
    description: str
    effects: list[str]
    cancellation: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "category": self.category,
            "strength": round(self.strength, 2),
            "active": self.active,
            "planets": self.planets_involved,
            "houses": self.houses_involved,
            "description": self.description,
            "effects": self.effects,
            "cancellation": self.cancellation,
        }


class YogaRule:
    """Represents a single yoga rule."""

    def __init__(self, rule_dict: dict):
        """Initialize from rule dictionary."""
        self.name = rule_dict.get("name", "Unknown")
        self.category = rule_dict.get("category", "general")
        self.conditions = rule_dict.get("conditions", [])
        self.strength_factors = rule_dict.get("strength_factors", [])
        self.cancellations = rule_dict.get("cancellations", [])
        self.description = rule_dict.get("description", "")
        self.effects = rule_dict.get("effects", [])
        self.priority = rule_dict.get("priority", 50)

    def evaluate(self, context: dict) -> YogaResult | None:
        """Evaluate if this yoga is present.

        Args:
            context: Chart context with planets, houses, aspects

        Returns:
            YogaResult if yoga is present, None otherwise
        """
        # Check all conditions
        planets_involved = set()
        houses_involved = set()

        for condition in self.conditions:
            result, planets, houses = self._evaluate_condition(condition, context)
            if not result:
                return None
            planets_involved.update(planets)
            houses_involved.update(houses)

        # All conditions met - yoga is present
        strength = self._calculate_strength(context)

        # Check for cancellation
        cancellation = self._check_cancellation(context)

        return YogaResult(
            name=self.name,
            category=self.category,
            strength=strength,
            active=(strength >= 25 and not cancellation),
            planets_involved=list(planets_involved),
            houses_involved=list(houses_involved),
            description=self.description,
            effects=self.effects,
            cancellation=cancellation,
        )

    def _evaluate_condition(
        self, condition: dict, context: dict
    ) -> tuple[bool, set[int], set[int]]:
        """Evaluate a single condition.

        Returns:
            Tuple of (result, planets_involved, houses_involved)
        """
        cond_type = condition.get("type")
        planets = set()
        houses = set()

        if cond_type == "planet_in_house":
            planet = condition.get("planet")
            house = condition.get("house")
            if self._check_planet_in_house(planet, house, context):
                planets.add(planet)
                houses.add(house)
                return True, planets, houses

        elif cond_type == "planet_in_sign":
            planet = condition.get("planet")
            sign = condition.get("sign")
            if self._check_planet_in_sign(planet, sign, context):
                planets.add(planet)
                return True, planets, houses

        elif cond_type == "planets_in_kendras":
            required_planets = condition.get("planets", [])
            if self._check_planets_in_kendras(required_planets, context):
                planets.update(required_planets)
                houses.update([1, 4, 7, 10])
                return True, planets, houses

        elif cond_type == "planets_conjunct":
            planet1 = condition.get("planet1")
            planet2 = condition.get("planet2")
            orb = condition.get("orb", 10)
            if self._check_conjunction(planet1, planet2, orb, context):
                planets.update([planet1, planet2])
                return True, planets, houses

        elif cond_type == "planet_exalted":
            planet = condition.get("planet")
            if self._check_exaltation(planet, context):
                planets.add(planet)
                return True, planets, houses

        elif cond_type == "exchange":
            planet1 = condition.get("planet1")
            planet2 = condition.get("planet2")
            if self._check_exchange(planet1, planet2, context):
                planets.update([planet1, planet2])
                return True, planets, houses

        elif cond_type == "aspect":
            from_planet = condition.get("from")
            to_planet = condition.get("to")
            if self._check_aspect(from_planet, to_planet, context):
                planets.update([from_planet, to_planet])
                return True, planets, houses

        elif cond_type == "lordship":
            planet = condition.get("planet")
            houses_ruled = condition.get("rules_houses", [])
            if self._check_lordship(planet, houses_ruled, context):
                planets.add(planet)
                houses.update(houses_ruled)
                return True, planets, houses

        return False, planets, houses

    def _check_planet_in_house(self, planet: int, house: int, context: dict) -> bool:
        """Check if planet is in specified house."""
        planet_data = context.get("planets", {}).get(planet)
        if planet_data:
            return planet_data.get("house") == house
        return False

    def _check_planet_in_sign(self, planet: int, sign: int, context: dict) -> bool:
        """Check if planet is in specified sign."""
        planet_data = context.get("planets", {}).get(planet)
        if planet_data:
            return planet_data.get("sign") == sign
        return False

    def _check_planets_in_kendras(
        self, required_planets: list[int], context: dict
    ) -> bool:
        """Check if all required planets are in kendras (1,4,7,10)."""
        kendras = {1, 4, 7, 10}
        for planet in required_planets:
            planet_data = context.get("planets", {}).get(planet)
            if not planet_data or planet_data.get("house") not in kendras:
                return False
        return True

    def _check_conjunction(
        self, planet1: int, planet2: int, orb: float, context: dict
    ) -> bool:
        """Check if two planets are conjunct within orb."""
        p1_data = context.get("planets", {}).get(planet1)
        p2_data = context.get("planets", {}).get(planet2)

        if p1_data and p2_data:
            # Check if in same house
            if p1_data.get("house") != p2_data.get("house"):
                return False

            # Check orb
            diff = abs(p1_data.get("longitude", 0) - p2_data.get("longitude", 0))
            if diff > 180:
                diff = 360 - diff
            return diff <= orb

        return False

    def _check_exaltation(self, planet: int, context: dict) -> bool:
        """Check if planet is exalted."""
        from constants.relationships import EXALTATION_SIGNS

        planet_data = context.get("planets", {}).get(planet)
        if planet_data:
            return planet_data.get("sign") == EXALTATION_SIGNS.get(planet)
        return False

    def _check_exchange(self, planet1: int, planet2: int, context: dict) -> bool:
        """Check if two planets are in mutual exchange (Parivartana)."""
        from constants.relationships import SIGN_LORDS

        p1_data = context.get("planets", {}).get(planet1)
        p2_data = context.get("planets", {}).get(planet2)

        if p1_data and p2_data:
            # Check if planet1 is in sign ruled by planet2
            # and planet2 is in sign ruled by planet1
            p1_sign = p1_data.get("sign")
            p2_sign = p2_data.get("sign")

            # Get signs ruled by each planet
            p1_rules = [s for s, lord in SIGN_LORDS.items() if lord == planet1]
            p2_rules = [s for s, lord in SIGN_LORDS.items() if lord == planet2]

            return (p1_sign in p2_rules) and (p2_sign in p1_rules)

        return False

    def _check_aspect(self, from_planet: int, to_planet: int, context: dict) -> bool:
        """Check if one planet aspects another."""
        aspects = context.get("aspects", {})
        planet_aspects = aspects.get(from_planet, {})
        return to_planet in planet_aspects

    def _check_lordship(self, planet: int, houses: list[int], context: dict) -> bool:
        """Check if planet rules specified houses."""
        # This would need house cusps and sign calculations
        # Simplified version
        from constants.relationships import SIGN_LORDS

        for house in houses:
            house_sign = context.get("houses", {}).get(house, {}).get("sign")
            if house_sign and SIGN_LORDS.get(house_sign) != planet:
                return False
        return True

    def _calculate_strength(self, context: dict) -> float:
        """Calculate yoga strength based on factors."""
        strength = 50.0  # Base strength

        for factor in self.strength_factors:
            factor_type = factor.get("type")
            weight = factor.get("weight", 10)

            if factor_type == "planet_strength":
                planet = factor.get("planet")
                # Would use Shadbala or other strength measure
                planet_data = context.get("planets", {}).get(planet, {})
                if planet_data.get("exalted"):
                    strength += weight
                elif planet_data.get("debilitated"):
                    strength -= weight

            elif factor_type == "house_strength":
                house = factor.get("house")
                # Would use house strength measures
                if house in [1, 4, 7, 10]:  # Kendras
                    strength += weight * 0.5

            elif factor_type == "aspect_quality":
                # Check benefic vs malefic aspects
                pass

        return max(0, min(100, strength))

    def _check_cancellation(self, context: dict) -> str | None:
        """Check if yoga is cancelled."""
        for cancellation in self.cancellations:
            cond_type = cancellation.get("type")

            if cond_type == "debilitated_planet":
                planet = cancellation.get("planet")
                if self._check_debilitation(planet, context):
                    return f"Cancelled: {self._get_planet_name(planet)} is debilitated"

            elif cond_type == "combust_planet":
                planet = cancellation.get("planet")
                if self._check_combustion(planet, context):
                    return f"Cancelled: {self._get_planet_name(planet)} is combust"

            elif cond_type == "malefic_aspect":
                planet = cancellation.get("planet")
                if self._check_malefic_aspects(planet, context):
                    return f"Cancelled: {self._get_planet_name(planet)} under malefic aspect"

        return None

    def _check_debilitation(self, planet: int, context: dict) -> bool:
        """Check if planet is debilitated."""
        from constants.relationships import DEBILITATION_SIGNS

        planet_data = context.get("planets", {}).get(planet)
        if planet_data:
            return planet_data.get("sign") == DEBILITATION_SIGNS.get(planet)
        return False

    def _check_combustion(self, planet: int, context: dict) -> bool:
        """Check if planet is combust."""
        planet_data = context.get("planets", {}).get(planet)
        return planet_data.get("combust", False) if planet_data else False

    def _check_malefic_aspects(self, planet: int, context: dict) -> bool:
        """Check if planet receives malefic aspects."""
        malefics = {1, 4, 7, 8, 9}  # Sun, Rahu, Ketu, Saturn, Mars
        aspects = context.get("aspects", {})

        for malefic in malefics:
            if planet in aspects.get(malefic, {}):
                return True
        return False

    def _get_planet_name(self, planet: int) -> str:
        """Get planet name from ID."""
        names = {
            1: "Sun",
            2: "Moon",
            3: "Jupiter",
            4: "Rahu",
            5: "Mercury",
            6: "Venus",
            7: "Ketu",
            8: "Saturn",
            9: "Mars",
        }
        return names.get(planet, f"Planet_{planet}")


class YogaEngine:
    """Main yoga detection engine."""

    def __init__(self):
        """Initialize yoga engine."""
        self.rules = []
        self.rules_by_category = {}
        self._load_rules()

    def _load_rules(self):
        """Load yoga rules from YAML files."""
        rules_dir = Path(__file__).parent / "rules"

        # Load each YAML file in rules directory
        for yaml_file in rules_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    rules_data = yaml.safe_load(f)

                    if rules_data and "yogas" in rules_data:
                        for rule_dict in rules_data["yogas"]:
                            rule = YogaRule(rule_dict)
                            self.rules.append(rule)

                            # Organize by category
                            category = rule.category
                            if category not in self.rules_by_category:
                                self.rules_by_category[category] = []
                            self.rules_by_category[category].append(rule)

            except Exception as e:
                # Log error but continue loading other files
                print(f"Error loading {yaml_file}: {e}")

        # Sort rules by priority
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    @require_feature("yoga_engine")
    def detect_yogas(self, context: dict) -> dict[str, Any]:
        """Detect all yogas in the chart.

        Args:
            context: Chart context with planets, houses, aspects

        Returns:
            Dictionary with detected yogas
        """
        detected = []
        by_category = {}
        statistics = {
            "total_evaluated": len(self.rules),
            "total_detected": 0,
            "active": 0,
            "cancelled": 0,
            "by_category": {},
        }

        # Evaluate each rule
        for rule in self.rules:
            result = rule.evaluate(context)
            if result:
                detected.append(result)

                # Organize by category
                if result.category not in by_category:
                    by_category[result.category] = []
                by_category[result.category].append(result)

                # Update statistics
                statistics["total_detected"] += 1
                if result.active:
                    statistics["active"] += 1
                if result.cancellation:
                    statistics["cancelled"] += 1

                cat_stats = statistics["by_category"].get(
                    result.category, {"count": 0, "active": 0}
                )
                cat_stats["count"] = cat_stats.get("count", 0) + 1
                if result.active:
                    cat_stats["active"] = cat_stats.get("active", 0) + 1
                statistics["by_category"][result.category] = cat_stats

        # Sort by strength
        detected.sort(key=lambda y: y.strength, reverse=True)

        return {
            "yogas": [y.to_dict() for y in detected],
            "by_category": {
                cat: [y.to_dict() for y in yogas] for cat, yogas in by_category.items()
            },
            "statistics": statistics,
            "strongest": detected[0].to_dict() if detected else None,
        }


# Global engine instance
_yoga_engine = None


def get_yoga_engine() -> YogaEngine:
    """Get singleton yoga engine instance."""
    global _yoga_engine
    if _yoga_engine is None:
        _yoga_engine = YogaEngine()
    return _yoga_engine


@require_feature("yoga_engine")
def detect_all_yogas(ctx: dict) -> dict[str, Any]:
    """Convenience function to detect all yogas.

    Args:
        ctx: Chart context

    Returns:
        Yoga detection results
    """
    engine = get_yoga_engine()
    return engine.detect_yogas(ctx)
