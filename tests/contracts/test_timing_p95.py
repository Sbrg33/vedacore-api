from __future__ import annotations

import time
from fastapi.testclient import TestClient
from apps.api.main import app


client = TestClient(app)


def test_ats_transit_p95_under_budget_and_deterministic():
    payload = {"targets": [6, 5]}  # VEN, MER (strict symbols also accepted)

    durations = []
    results = []
    for _ in range(10):
        t0 = time.perf_counter()
        r = client.post("/api/v1/ats/transit", json=payload)
        dt = time.perf_counter() - t0
        assert r.status_code == 200, r.text
        results.append(r.json())
        durations.append(dt)

    # Determinism on targets/scores
    base = results[0]
    for j in results[1:]:
        assert j.get("targets") == base.get("targets")
        # Compare normalized scores with small tolerance
        for k, v in base.get("scores_norm", {}).items():
            assert abs(j["scores_norm"][k] - v) < 1e-6

    # Simple P95 check (10 samples → index 9)
    durations.sort()
    p95 = durations[9]
    # Keep generous budget to avoid flakiness in CI
    assert p95 < 0.5  # seconds

