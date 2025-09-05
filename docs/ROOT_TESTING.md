# Testing (Repo Root Shortcuts)

This monorepo hosts the VedaCore API in `vedacore-api/`. Use these shortcuts from the repo root to run tests efficiently. They mirror the instructions in `vedacore-api/README.md`.

- Fast test run (skips heavy warmup/JIT):
  - `make -C vedacore-api test`
- Very fast loop (unit + contracts, fail fast):
  - `make -C vedacore-api test-fast`
- Contracts only (runs in chunks to avoid local timeouts):
  - `make -C vedacore-api test-contracts`
- Parallel run (requires `pytest-xdist`; falls back to sequential):
  - `make -C vedacore-api test-parallel`

Notes
- Default markers exclude `slow` and `integration`; include them explicitly when needed:
  - `PYTHONPATH=./vedacore-api/src:. pytest -m "slow or integration" -q`
- Tests reuse a session‑scoped TestClient and OpenAPI spec for speed.
- Fast targets set `VC_SKIP_WARMUP=1` and `NUMBA_DISABLE_JIT=1`.

For full details and additional commands, see `vedacore-api/README.md`.
