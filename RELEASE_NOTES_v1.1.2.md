VedaCore API v1.1.2 — Release Notes

Highlights
- Security: Top-level HTTP Bearer in OpenAPI; REST requires JWT (docs & runtime aligned).
- Streaming: SSE 200 responses now text/event-stream only; token query documented across stream endpoints.
- Contracts: Added response models for root, version, systems, Moon strength/config, ATS health, KP RP health/explain.
- Spec hygiene: Legacy shims hidden; normalized to OpenAPI 3.0.3; prod server exported.
- SDKs: TypeScript client regenerated; Python client bumped to 1.1.2.

SDKs
- TypeScript: @vedacore/api@1.1.2
- Python: veda_core_signals_api_client==1.1.2

Operational
- Spec: openapi.json frozen at 1.1.2 with global HTTPBearer + bearerAuth (legacy) and servers[0]=prod.
- SSE: Sanitized OpenAPI content to advertise only text/event-stream for SSE endpoints.
- Runtime: REST endpoints guarded by JWT; SSE/WS accept ?token= for browser compatibility.

Upgrade Guide
- Update clients to @vedacore/api@1.1.2 or veda_core_signals_api_client==1.1.2.
- Validate CORS in production: set CORS_ALLOWED_ORIGINS to explicit protocol-prefixed domains.
- Prefer AUTH_JWKS_URL for managed IdPs; otherwise set strong AUTH_JWT_SECRET (>=32 chars).

Verification Commands
- curl -fsS https://api.vedacore.io/api/v1/health/up
- curl -fsS https://api.vedacore.io/api/docs >/dev/null && echo OK
- curl -s https://api.vedacore.io/api/v1/version | jq .

