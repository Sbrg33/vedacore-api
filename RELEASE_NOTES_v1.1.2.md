VedaCore API v1.1.2 — Release Notes

Overview
VedaCore API v1.1.2 delivers hardened SSE streaming with dual authentication, deterministic resume, and stronger governance. The release is contract‑first and non‑breaking.

Highlights
- Dual SSE auth: header Bearer preferred; query tokens remain for browsers (short TTL, deprecation signaled).
- Deterministic resume: Last-Event-ID with explicit `event: reset` on gaps.
- Security by default: `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `Vary: Authorization, Accept`; 401/429 standardized.
- Operational clarity: richer traces across hot paths; log redaction for tokens/referrers.

Developer notes
- SSE client: implement a handler for `event: reset` to discard local state and reconnect.
- Browser: add `<meta name="referrer" content="no-referrer">` and `Content-Security-Policy: connect-src https://api.vedacore.io;`.
- Deprecation: query tokens sunset on Dec 31, 2025 (HTTP-date in Sunset header); migrate servers to Bearer.

Compatibility
No endpoint removals; OpenAPI 3.1 documents OR security, enriched headers, and 429 Problem body.

Verification
- curl -fsS https://api.vedacore.io/api/v1/health/up
- curl -fsS https://api.vedacore.io/api/docs >/dev/null && echo OK
- curl -i -H "Accept: text/event-stream" -H "Authorization: Bearer $TOKEN" "https://api.vedacore.io/api/v1/stream?topic=kp.moon.chain" | sed -n '1,10p'
