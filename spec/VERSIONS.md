# Versions and Pinning

- Ephemeris dataset version: swe-2.10.3
- ΔT model: norm-const-69s (UTC→TT +69.0 seconds)
- Normalization ruleset: norm-2025-09-01.1
- API version: 1.1.2
- Algorithm version: algo-1.0.0

Notes:
- ΔT is pinned for determinism. If the ΔT model changes, bump the normalization
  ruleset and update cache keys accordingly.
- Any change to ephemeris dataset or normalization requires prewarming the cache
  and may trigger version migration headers.

