#!/usr/bin/env python3
"""
Minimal ATS compatibility package.

Provides the interfaces expected by ATSSystemAdapter so the API can
start even when the full ATS engine is not vendored.

Modules:
- ats.vedacore_ats: PLANETS, KPState, context_from_dict, build_edges_transit,
  score_targets, normalize_scores
- ats.vedacore_facade_provider: VedaCoreFacadeProvider

Note: This is a minimal implementation that returns neutral/zero scores.
It is intended to unblock application startup and allow wiring tests.
Replace with the full ATS engine when available.
"""

