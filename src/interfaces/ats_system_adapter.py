#!/usr/bin/env python3
"""
ATS System Adapter - Wraps existing ATS without modifying core
Maintains all critical logic: 307s offset, True Node handling, Ketu derivation
"""

import logging
import os

from datetime import UTC, date, datetime
from typing import Any

import yaml

# Import ATS core WITHOUT any modifications
from ats.vedacore_ats import (
    PLANETS,
    KPState,
    build_edges_transit,
    context_from_dict,
    normalize_scores,
    score_targets,
)

# Import existing facade provider - it has correct 307s offset and node logic
from ats.vedacore_facade_provider import VedaCoreFacadeProvider

from .system_adapter import BaseSystemAdapter, SystemChange, SystemSnapshot

logger = logging.getLogger(__name__)

# ID mapping at adapter boundary ONLY - core remains unchanged
ID_TO_ATS = {
    1: "SUN",
    2: "MOON",
    3: "JUP",
    4: "RAH",
    5: "MERC",
    6: "VEN",
    7: "KET",
    8: "SAT",
    9: "MAR",
}

ATS_TO_ID = {v: k for k, v in ID_TO_ATS.items()}


class ATSSystemAdapter(BaseSystemAdapter):
    """
    ATS System Adapter - bridges VedaCore to ATS scoring engine

    Key features:
    - Preserves ATS core string IDs internally
    - Maps numeric IDs at boundaries only
    - Maintains 307s finance offset via facade
    - Single True Node lookup with Ketu derivation
    - Caches context for performance
    """

    def __init__(self, context_yaml: str | None = None):
        """
        Initialize ATS adapter

        Args:
            context_yaml: Path to context YAML file (defaults to ats_market.yaml)
        """
        super().__init__(system="ATS", version="1.0.0")

        # Use existing facade provider - maintains 307s offset and node logic
        self.facade = VedaCoreFacadeProvider(apply_finance_offset=True)

        # Load context configuration
        if context_yaml is None:
            # Try multiple paths for context file
            possible_paths = [
                "config/ats/ats_market.yaml",
                "ats/configs/ats_market.yaml",
                os.path.join(
                    os.path.dirname(__file__), "..", "ats", "configs", "ats_market.yaml"
                ),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    context_yaml = path
                    break
            else:
                # Fail fast if no context file found
                raise FileNotFoundError(
                    f"ATS context file not found. Searched paths: {possible_paths}"
                )

        self.context_yaml = context_yaml
        self.ref_norm = 1.5  # Reference for 0-100 scaling
        self.default_targets = ("VEN", "MER")  # Default scoring targets

        # Cache loaded context
        self._context_cache = None
        self._load_context()

    def _load_context(self):
        """Load and cache context from YAML"""
        try:
            if not os.path.exists(self.context_yaml):
                raise FileNotFoundError(
                    f"Context file does not exist: {self.context_yaml}"
                )

            with open(self.context_yaml) as f:
                ctx_cfg = yaml.safe_load(f)
                self._context_cache = context_from_dict(ctx_cfg)
                logger.info(f"Loaded ATS context from {self.context_yaml}")
        except Exception as e:
            logger.error(f"Failed to load context from {self.context_yaml}: {e}")
            # Fail fast instead of silent fallback
            raise RuntimeError(f"ATS context loading failed: {e}") from e

    @property
    def description(self) -> str:
        return "ATS (Aspect-Transfer Scoring) - Transit-to-transit scoring with KP integration"

    def calculate(
        self, ts_utc: datetime, entity: str = None, **kwargs
    ) -> dict[str, Any]:
        """
        Calculate ATS scores for given timestamp

        Args:
            ts_utc: UTC timestamp for calculation
            entity: Not used (kept for interface compatibility)
            **kwargs:
                targets: List of target planets (numeric IDs or ATS strings)
                context_yaml: Override context file path

        Returns:
            Dictionary with scores_raw, scores_norm, by_source, paths, timestamp
        """
        # Ensure UTC
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=UTC)

        # Get targets (can be numeric IDs or string names)
        targets = kwargs.get("targets", self.default_targets)

        # Convert numeric IDs to ATS strings if needed
        if targets and isinstance(targets[0], int):
            targets = tuple(ID_TO_ATS.get(t, f"UNKNOWN_{t}") for t in targets)
        elif targets and isinstance(targets[0], str):
            # Ensure uppercase for consistency
            targets = tuple(t.upper() for t in targets)

        # Override context if specified
        if "context_yaml" in kwargs:
            with open(kwargs["context_yaml"]) as f:
                ctx = context_from_dict(yaml.safe_load(f))
        else:
            ctx = self._context_cache

        try:
            # Get ephemeris data via facade (applies 307s offset internally)
            longs = self.facade.get_transit_longs(ts_utc)  # Returns {'SUN': deg, ...}
            dign = self.facade.get_dignities(ts_utc)  # Returns {'SUN': 'NEU', ...}
            raw_conds = self.facade.get_conditions(
                ts_utc
            )  # Returns {'SUN': {'retro': ...}, ...}

            # Map condition keys to ATS core format (retro -> is_retro, etc)
            conds = {}
            for planet, planet_conds in raw_conds.items():
                conds[planet] = {
                    "is_retro": planet_conds.get("retro", False),
                    "is_station": planet_conds.get("station", False),
                    "is_combust": planet_conds.get("combust", False),
                    "is_cazimi": planet_conds.get("cazimi", False),
                }

            # Get KP Moon chain
            nl, sl, ssl = self.facade.get_moon_chain(
                ts_utc
            )  # Returns ('JUP', 'VEN', 'MER')

            # Optional: get planet chains for all planets
            planet_chains = (
                self.facade.get_planet_chains(ts_utc)
                if hasattr(self.facade, "get_planet_chains")
                else {}
            )

            # Build KP state
            kp = KPState(
                moon_nl=nl, moon_sl=sl, moon_ssl=ssl, planet_chain=planet_chains
            )

            # Calculate ATS scores using original core functions
            edges = build_edges_transit(PLANETS, longs, dign, conds, kp=kp, ctx=ctx or {}) or []
            totals, by_src, pathlog = score_targets(targets, PLANETS, edges, ctx=ctx or {})
            totals = totals or {t: 0.0 for t in targets}
            by_src = by_src or {t: {} for t in targets}
            pathlog = pathlog or []
            scores = normalize_scores(totals, ref=self.ref_norm) or {t: 0.0 for t in targets}

            # Convert source planets back to numeric IDs for output
            by_src_id = {}
            for target, sources in by_src.items():
                target_id = ATS_TO_ID.get(target, target)
                by_src_id[target_id] = {
                    ATS_TO_ID.get(src, src): val for src, val in sources.items()
                }

            # Convert target scores to use numeric IDs
            scores_raw_id = {ATS_TO_ID.get(k, k): v for k, v in totals.items()}
            scores_norm_id = {ATS_TO_ID.get(k, k): v for k, v in scores.items()}

            return {
                "timestamp": ts_utc.isoformat(),
                "scores_raw": scores_raw_id,
                "scores_norm": scores_norm_id,
                "by_source": by_src_id,
                "paths": pathlog,
                "targets": [ATS_TO_ID.get(t, t) for t in targets],
                "context": os.path.basename(self.context_yaml),
            }

        except Exception as e:
            logger.error(f"ATS calculation failed: {e}")
            raise

    def snapshot(self, ts_utc: datetime) -> SystemSnapshot:
        """
        Get complete ATS state at a timestamp

        Args:
            ts_utc: UTC timestamp for snapshot

        Returns:
            SystemSnapshot with ATS scores and metadata
        """
        result = self.calculate(ts_utc)

        return SystemSnapshot(
            system=self.system,
            timestamp=ts_utc,
            data={
                "scores": result["scores_norm"],
                "raw_scores": result["scores_raw"],
                "by_source": result["by_source"],
                "context": result["context"],
            },
            metadata={
                "targets": result["targets"],
                "ref_norm": self.ref_norm,
                "path_count": len(result.get("paths", [])),
            },
        )

    def changes(self, day_utc: date) -> list[SystemChange]:
        """
        Get ATS score changes throughout the day

        Args:
            day_utc: UTC date for which to find changes

        Returns:
            List of SystemChange objects showing score evolution
        """
        changes = []

        # Sample every 15 minutes to detect significant changes
        from datetime import timedelta

        start_ts = datetime.combine(day_utc, datetime.min.time(), tzinfo=UTC)
        prev_scores = None

        for minutes in range(0, 1440, 15):  # Every 15 minutes
            ts = start_ts + timedelta(minutes=minutes)

            try:
                result = self.calculate(ts)
                current_scores = result["scores_norm"]

                if prev_scores:
                    # Check for significant changes (>10% difference)
                    for planet_id, score in current_scores.items():
                        prev_score = prev_scores.get(planet_id, 0)
                        if (
                            abs(score - prev_score) > 10
                        ):  # 10-point change on 0-100 scale
                            changes.append(
                                SystemChange(
                                    system=self.system,
                                    timestamp=ts,
                                    change_type="score_change",
                                    from_value=prev_score,
                                    to_value=score,
                                    entity=str(planet_id),
                                    metadata={"magnitude": abs(score - prev_score)},
                                )
                            )

                prev_scores = current_scores

            except Exception as e:
                logger.warning(f"Could not calculate ATS for {ts}: {e}")
                continue

        return changes

    def get_metadata(self) -> dict[str, Any]:
        """Get ATS metadata and configuration"""
        return {
            "system": self.system,
            "version": self.version,
            "description": self.description,
            "context_file": self.context_yaml,
            "ref_norm": self.ref_norm,
            "default_targets": self.default_targets,
            "planets": list(ID_TO_ATS.values()),
            "cache_enabled": self._cache_enabled,
            "metrics_enabled": self._metrics_enabled,
            "facade_offset": "307s finance offset applied",
            "node_handling": "True Node (SWE 11), Ketu = Rahu + 180°",
        }
