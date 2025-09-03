# VedaCore API – Engineering Standards (v1.1)

This document captures the concrete rules we follow to keep the API secure, deterministic, and easy to maintain. It is intentionally short and operational.

## 1) Module Boundaries

- Ephemeris owns astronomy math (positions, houses, ayanāṁśa). No domain module (KP/Horary) re‑implements observables.
- KP/Horary import only through Facade/Kernel utilities.
- Facade orchestrates Ephemeris → Kernel transforms → KP/Horary projections. No back‑edges.
- Every public function exposes `engine_version` for cache/versioning.

## 2) Caching (Determinism)

- Canonical key = sha256 of normalized JSON:
  - UTC ISO timestamp (second precision),
  - lat/lon with fixed precision (6 dp),
  - ayanāṁśa/house IDs,
  - engine/ephemeris versions,
  - options.
- T0 (process): small LRU for micro‑hot math.
- T1 (Redis via `UnifiedCache`): snapshots + projections; version‑namespaced; TTL 30–90 days.
- T2 (edge/CDN): GET only; never POST/SSE/tenant data.
- Always use `UnifiedCache`; never import `CacheService` directly.

## 3) Security & Limits

- REST requires JWT (Authorization header). SSE/WS use `?token=` query.
- Top‑level OpenAPI security: HTTP Bearer. Health/metrics stay public (no dependency attached).
- Per‑tenant QPS limiter applied to REST routes via `rest_qps_guard`.

## 4) Streaming

- SSE responses: `text/event-stream`, anti‑buffering headers, 15s ping, Last‑Event‑ID resumption.
- No edge caching for streaming.
- Document token query param; keep example curl in README.

## 5) OpenAPI & SDKs

- Stable spec commit: `openapi.json` with prod servers (`https://api.vedacore.io`) and version bump.
- Downgrade helper (3.1 → 3.0.3) maintained to improve codegen coverage; do not edit generated SDKs.
- CI gates: `oasdiff` non‑breaking; typed smokes validate 200/201 JSON have schemas; SSE spot checks.

## 6) Performance & Goldens

- Maintain a small golden set (hashes of canonicalized responses) for critical routes.
- Perf budgets (P95) per route in CI; allow ±10% variance on a fixed runner.

## 7) Deprecations

- Legacy shims respond with Deprecation/Sunset headers.
- Mark legacy shim routes `include_in_schema=false` so SDKs/docs are clean.

## 8) Ownership & Review

- Changes crossing module boundaries require codeowner ACK.
- Cache policy changes (TTL, key shape) require performance/accuracy sign‑off.

