# Changelog

All notable changes to this project will be documented in this file.

## [1.1.2] — 2025-09-03

Status: Stable (non‑breaking); contract‑first verified via CI.

- Streaming/SSE:
  - Dual auth: Authorization: Bearer preferred over `?token=`; short‑TTL query tokens with ±30s skew.
  - Resume semantics: Last-Event-ID with reset control event on buffer gap.
  - Security headers: Cache-Control: no-store, Referrer-Policy: no-referrer, Vary: Authorization, Accept.
  - Deprecation nudges: query tokens emit Warning: 299 and Sunset (HTTP-date) when used.
- Security/Errors:
  - 401 with WWW-Authenticate and remediation hint.
  - Soft 429 with Problem JSON including retry_after_seconds.
- Contracts/Governance:
  - OpenAPI 3.1 op-level OR security for /api/v1/stream; AsyncAPI documents header precedence + reset.
  - Live export only; CI: Spectral, AsyncAPI validate, oasdiff (non‑breaking), Schemathesis smoke, SwissEph boundary guard.
- Observability:
  - Standardized tracing attributes across stream, enhanced_signals, dasha, nodes, houses; Redis spans.
- Logging:
  - Redacts token, Authorization, and Referer in logs.

Upgrade notes:
- No breaking changes. Browser clients can continue `?token=` (short‑TTL); server clients should use Bearer.
- Handle `event: reset` by clearing local buffers and reconnecting without Last-Event-ID.

