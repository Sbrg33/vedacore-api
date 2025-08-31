from __future__ import annotations

from ats.vedacore_ats import KPState, build_edges_transit, score_targets


def test_ats_scoring_conjunction_boosts_target():
    planets = ("SUN", "VEN", "MAR")
    # Place SUN and VEN in conjunction; MAR elsewhere
    longs = {"SUN": 10.0, "VEN": 12.0, "MAR": 200.0}
    dign = {p: "NEU" for p in planets}
    conds = {p: {"is_retro": False} for p in planets}
    kp = KPState(moon_nl="VEN", moon_sl="SUN", moon_ssl="MAR")
    ctx = {"aspects": {"conj": {"orb": 8.0, "weight": 1.0}}}

    edges = build_edges_transit(planets, longs, dign, conds, kp=kp, ctx=ctx)
    totals, by_src, pathlog = score_targets(("VEN", "SUN"), planets, edges, ctx=ctx, kp=kp)
    assert totals["VEN"] > 0.0
    # VEN should receive more than SUN since SUN->VEN edge contributes to VEN
    assert totals["VEN"] >= totals["SUN"]

