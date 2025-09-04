# VedaCore API (Minimal Export)

[![npm](https://img.shields.io/npm/v/%40vedacore%2Fapi.svg)](https://www.npmjs.com/package/@vedacore/api)
[![PyPI](https://img.shields.io/pypi/v/vedacore-api.svg)](https://pypi.org/project/vedacore-api/)
[![OpenAPI](https://img.shields.io/badge/OpenAPI-1.1.2-blue.svg)](./openapi.json)

[![npm next](https://img.shields.io/npm/v/%40vedacore%2Fapi/next.svg?label=npm%40next)](https://www.npmjs.com/package/@vedacore/api?activeTab=versions)
[![PyPI pre](https://img.shields.io/pypi/v/vedacore-api.svg?label=pypi%20pre&include_prereleases)](https://pypi.org/project/vedacore-api/#history)

Production-ready FastAPI service for high-precision KP astrology calculations.

- Entrypoint: `apps.api.main:app`
- Health: `GET /api/v1/health/live` | Ready: `/api/v1/health/ready` | Docs: `/api/docs` | Metrics: `/metrics`
- Notes: Ephemeris data under `./swisseph/ephe`; atlas data under `src/data/atlas`
- CI: Minimal workflow runs pytest smoke with `PYTHONPATH=./src:.`

SDK quickstart: see `SDK.md` for TypeScript/Python client usage and versioning aligned with `openapi.json`.

## Local Dev Quickstart

- Requires Python 3.11
- Install: `make install`
- Run API (reload): `make run` (uvicorn on `http://127.0.0.1:8000`)
- Tests: `make test` (or `PYTHONPATH=./src:. pytest -v`)
- Smoke: `make smoke-local` (start → readiness gate → stop)

Direct commands:
```bash
pip install -r requirements.txt
export PYTHONPATH=./src:.
uvicorn apps.api.main:app --reload --port 8000
```

## Environment Model

Two toggles with different purposes:
- `ENVIRONMENT`: enables production hardening (security gates, strict CORS). Use `production` in real deployments.
- `VC_ENV`: selects configuration mode (DB/streaming); `local` vs `remote` (Supabase/cloud).

Templates:
- `.env.production.example` (prod switches and security headers)
- `.env.remote.template` (Supabase Cloud)
- Optional: generate local templates via script:
  - `PYTHONPATH=./src:. python src/app/core/environment.py create-templates`

Key vars:
- Auth: `AUTH_JWKS_URL=...` (recommended) or `AUTH_JWT_SECRET=<32+ chars>`
- CORS: `CORS_ALLOWED_ORIGINS=https://app.example,https://admin.example` (no wildcard in prod)
- Workers/metrics: Auto-detects RAM and scales workers (≤1GB→1, ≤2GB→2, >2GB→4). Override: `WORKERS=N`. Metrics: `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus`
- Feature flags: `FEATURE_V1_ROUTING=true`, `ACTIVATION_ENABLED=false`
- Optional routing toggles: `ENABLE_ATS=true|false` (ATS endpoints return 403 when disabled)

## Production Quickstart (Docker)

```bash
docker build -t vedacore-api .
docker run -d --name vedacore-api --restart unless-stopped -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e VC_ENV=remote \
  -e AUTH_JWT_SECRET='your-long-secret' \
  -e CORS_ALLOWED_ORIGINS='https://your-frontend.example' \
  vedacore-api
```

### DigitalOcean (Blue/Green with Compose + Caddy)

Files under `deploy/` provide a simple, SSE‑friendly blue/green rollout on a single droplet.

- Compose/Caddy: `deploy/docker-compose.yml`, `deploy/Caddyfile`
- Env template: `deploy/.env.example` (copy to `.env` and set secrets)
- Flip script: `deploy/deploy_green.sh` (switches proxy to green, then stops blue)

Steps (once):
- Set immutable image digests in `deploy/docker-compose.yml` (`api_blue` and `api_green`).
- `cd deploy && cp .env.example .env && edit .env`.
- `docker compose up -d caddy api_blue`.

Deploy a new version (zero‑downtime):
- Edit `api_green.image` to the new digest in `deploy/docker-compose.yml`.
- `cd deploy && ./deploy_green.sh`.
- Rollback: switch `Caddyfile` back to `api_blue` and `docker compose up -d api_blue`.

Health gate:
```bash
curl -fsS http://localhost:8000/api/v1/health/ready || docker logs --tail 200 vedacore-api
```

Plaintext liveness (for external monitors):
```bash
curl -fsS http://localhost:8000/api/v1/health/up
```

Auth options:
- JWKS: set `AUTH_JWKS_URL` (add `AUTH_AUDIENCE`/`AUTH_ISSUER` as needed)
- HS256: set `AUTH_JWT_SECRET` (min 32 chars)

All REST endpoints require authentication. Use `Authorization: Bearer <jwt>` for REST.
For SSE/WS, use `?token=<jwt>` as query parameter (browser-compatible). Non-browser clients may send `Authorization: Bearer <jwt>` instead.

CORS rules:
- In production, origins must be explicit and include protocol; startup fails on misconfig.

## CI/CD Deploy (SSH)

- Workflow: `.github/workflows/deploy.yml`
- Required secrets: `DO_HOST`, `DO_USER`, `DO_SSH_KEY`, `GHCR_USERNAME`, `GHCR_TOKEN`, `AUTH_JWT_SECRET`, `CORS_ALLOWED_ORIGINS`, optional `REDIS_URL`
- Environment-specific secrets:
  - Production environment: define `REDIS_URL`
  - Staging environment: define `REDIS_URL` (preferred) or `STAGING_REDIS_URL` (fallback)
- Auto‑deploy: when "Build & Push Image (GHCR)" succeeds on `main`, the deploy workflow auto‑runs and deploys the exact image tagged `sha-<long-commit>`
- Concurrency: deploys are serialized (`deploy-vedacore-api` group) to prevent overlap
- Environments: deploy job uses GitHub Environments (production by default; staging available via manual input)
- Manual deploy (override or rollback):
  - GitHub UI: Actions → Deploy (SSH via GHCR) → Run workflow
  - Inputs:
    - `environment`: `production` (default) or `staging`
    - `tag`: image tag (e.g., `sha-<long-commit>` or `latest`)
    - `public_url`: optional override (defaults per environment)
  - CLI example (deploy specific image to staging):
    - `gh workflow run "Deploy (SSH via GHCR)" -F environment=staging -F tag=sha-<long-commit>`
  - Rollback: re‑deploy a previous known good SHA with the same command

## GHCR Deploy

Images are published to GHCR via CI:
- Registry: `ghcr.io/$OWNER/vedacore-api`
- Tags: `sha-<commit>` (short and long), `latest` on `main`, plus release tags as created

Auto‑deploy uses the long SHA tag for deterministic server updates.

Run on a server:
```bash
export OWNER=<your_github_org_or_user>
docker login ghcr.io -u <GHCR_USERNAME> -p <GHCR_TOKEN>
docker pull ghcr.io/$OWNER/vedacore-api:latest

docker rm -f vedacore-api || true
docker run -d --name vedacore-api --restart unless-stopped -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e VC_ENV=remote \
  -e AUTH_JWT_SECRET='<32+ char random>' \
  -e CORS_ALLOWED_ORIGINS='https://your-frontend.example' \
  ghcr.io/$OWNER/vedacore-api:latest

curl -fsS http://127.0.0.1:8000/api/v1/health/ready
```

Notes:
- Prefer immutable tags (e.g., `sha-<commit>`) for rollbacks.

## Production Checklist

- Auth & Env: set `ENVIRONMENT=production`, `VC_ENV=remote`; configure either `AUTH_JWKS_URL` (preferred) or a strong `AUTH_JWT_SECRET` (≥32 chars). Set `API_KEY_V1_CUTOFF_DATE` to enable API key routing middleware.
- CORS: define `CORS_ALLOWED_ORIGINS` with explicit, protocol‑prefixed domains (no wildcards in production).
- Image Tag: deploy pinned GHCR tag `sha-<long-commit>`; avoid `latest`. Validate with `GET /api/v1/version`.
- Ports & Health: expose `-p 80:8000` (or set `PORT`); ensure port 80 is free (stop nginx/apache if not used). Use `--restart unless-stopped` for reboot persistence. Monitors should hit `/api/v1/health/up`; readiness gate at `/api/v1/health/ready`.
- Metrics & Workers: set `PROMETHEUS_MULTIPROC_DIR` (writable) and `WORKERS` as desired; confirm `/metrics` responds.
- Optional Redis: set `REDIS_URL` for backpressure and token auditing; service runs without it but with reduced hardening.
- ATS (optional): enable via `ENABLE_ATS=true`; symbol policy is strict (3‑letter) and integers 1–9 are accepted.
- Quick verify: `make check-health BASE=https://api.vedacore.io`, `curl -fsS <PUBLIC_URL>/api/docs >/dev/null && echo OK`, `curl -s <PUBLIC_URL>/api/v1/version`.

## Observability

- `/api/v1/health/up`: plaintext "ok" for liveness probes.
- `/api/v1/health/ready`: JSON readiness gate validating subsystems.
- `/api/v1/health/live`: JSON liveness (includes `process_id` as string).
- `/metrics` exposes Prometheus metrics.
- Multi-worker metrics use `PROMETHEUS_MULTIPROC_DIR` (default `/tmp/prometheus`).
- Internal metrics helpers are wired via `refactor.monitoring`.

Streaming metrics of interest:
- `vc_sse_handshake_total{method, outcome}`: header/query mix and outcomes (success, invalid_token, missing_token, rate_limited).
- `vc_sse_handshake_latency_seconds{method, outcome}`: handshake latency distribution.
- `vc_sse_reset_total{topic}`: resets due to resume gaps.
- `vc_sse_resume_replayed_total{topic}`: events replayed during resume.
- `vc_stream_connections{tenant,topic,protocol}` and `vc_messages_per_connection{tenant,topic,protocol}`: live connections and throughput.

Quick checks:
```bash
# Health (preferred for monitors)
curl -fsS http://127.0.0.1:8000/api/v1/health/up

# Readiness (used in CI)
curl -fsS http://127.0.0.1:8000/api/v1/health/ready

# Docs (OpenAPI UI)
curl -fsS http://127.0.0.1:8000/api/docs >/dev/null && echo OK

# Metrics endpoint
curl -fsS http://127.0.0.1:8000/metrics | head -n 10

# Portable health checker (prefers /health/up, fallback /health/ready)
make check-health BASE=http://127.0.0.1:8000
```

## Release channels

| Channel | Purpose | Install |
|---|---|---|
| **Stable** | Frozen to committed `openapi.json` (diff‑gated) | `npm i @vedacore/api` • `pip install vedacore-api` |
| **Next** | Nightly preview from live spec | `npm i @vedacore/api@next` • `pip install vedacore-api --pre` |

**Versioning & gates**
- SDK version equals `.info.version` in `openapi.json`.
- Patch/minor releases are blocked by an OpenAPI breaking‑change guard.
- Major versions allow breaking changes.

**Spec source of truth**
- Authoritative contracts live under `spec/` (`openapi-3.1.yaml`, `asyncapi.yaml`, `VERSIONS.md`).
- Export the 3.0.x JSON used by SDKs from the running app:
  - `PYTHONPATH=./src:. python tools/export_openapi.py`
  - CI validates `spec/` via Spectral + AsyncAPI and diffs `openapi.json`.

**Base URL & auth**
- Default server (prod): `https://api.vedacore.io` (override with `OPENAPI_PUBLIC_URL`).
- REST: send `Authorization: Bearer <jwt>`.
- Streaming: obtain short‑lived token via `/api/v1/auth/stream-token`; browsers pass `?token=<jwt>`, non‑browsers may use the header.

**Security caution (SSE tokens)**
- Query tokens in URLs can leak via Referer or logs. Prefer `Authorization: Bearer` for non‑browsers. Query tokens are short‑lived and may be deprecated in the future.
- Examples:
  - curl (header): `curl -H "Accept: text/event-stream" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/stream?topic=kp.moon.chain"`
  - EventSource (browser): `new EventSource(`${BASE}/api/v1/stream?topic=kp.moon.chain&token=${token}`);`
  - Also set `Referrer-Policy: no-referrer` on the hosting page to avoid leaking query tokens in Referer headers on navigation.

Add this to static HTML pages:
```
<meta name="referrer" content="no-referrer">
```

Minimal EventSource client handling reset events:
```
const url = `${BASE}/api/v1/stream?topic=${encodeURIComponent(topic)}&token=${token}`;
const es = new EventSource(url);
es.addEventListener('reset', () => {
  console.warn('Server requested full resync; reconnecting');
  es.close();
  const es2 = new EventSource(`${BASE}/api/v1/stream?topic=${encodeURIComponent(topic)}&token=${token}`);
});
```

Resume buffer: server retains a bounded window in memory and/or Redis. If your Last-Event-ID falls behind the minimum retained sequence, the server emits `event: reset` and closes; reconnect without Last-Event-ID.

Browser security headers:
- Add `Content-Security-Policy: connect-src https://api.vedacore.io;` so browsers can open EventSource to the API origin.

Sizing your client buffer:
- Debug endpoints expose resume windows:
  - `/stream/_resume?topic=...` → `redis: {size,min_seq,max_seq}`, `memory: {size,min_seq,max_seq}`
  - `/stream/_topics?include_resume=true` lists resume stats per topic
- Choose a local buffer (number of events) that exceeds your expected offline duration multiplied by average event rate.

## Testing

- Run: `make test` or `PYTHONPATH=./src:. pytest -v`
- Minimal suite validates docs, readiness, and metrics.

## Contracts Governance

- Source of truth: `spec/openapi-3.1.yaml` and `spec/asyncapi.yaml`.
- Export live JSON: `PYTHONPATH=./src:. python tools/export_openapi.py`.
- CI gates: Spectral (OpenAPI), AsyncAPI validate, oasdiff (vs previous and vs 3.1), Schemathesis smoke, drift guard.
- Pre-commit guard: blocks new direct `swisseph/pyswisseph` imports outside approved modules. Enable via `pip install pre-commit && pre-commit install`.

## Tools

- `tools/check_api_health.py`: portable API health checker (no deps). Examples:
  - `python tools/check_api_health.py --base http://127.0.0.1:8000`
  - `python tools/check_api_health.py --base https://api.vedacore.io --json`

## KP Ruling Planets Weights

- API override: POST `/api/v1/kp/ruling-planets` accepts optional `weights`:
```json
{
  "datetime": "2025-09-01T14:00:00Z",
  "lat": 40.7128,
  "lon": -74.0060,
  "include_day_lord": true,
  "weights": {
    "day_lord": 2.0,
    "asc_nl": 3.0,
    "asc_sl": 1.5,
    "asc_ssl": 0.5,
    "moon_nl": 2.0,
    "moon_sl": 1.0,
    "moon_ssl": 0.5,
    "exalt": 0.75,
    "own": 0.5,
    "normalize": true,
    "top_k_primary": 5
  }
}
```

- Quick curl (replace token/lat/lon/time):
```bash
TOKEN='<your_jwt>'
curl -sS -X POST http://127.0.0.1:8000/api/v1/kp/ruling-planets \
  -H 'content-type: application/json' -H "Authorization: Bearer $TOKEN" \
  -d '{
        "datetime": "2025-09-01T14:00:00Z",
        "lat": 40.7128,
        "lon": -74.0060,
        "include_day_lord": true,
        "weights": {"asc_nl": 3.0, "moon_nl": 2.0}
      }'
```

- Env defaults (server-wide): set before starting the container
  - `RP_W_DAY_LORD`, `RP_W_ASC_NL`, `RP_W_ASC_SL`, `RP_W_ASC_SSL`
  - `RP_W_MOON_NL`, `RP_W_MOON_SL`, `RP_W_MOON_SSL`
  - `RP_W_EXALT`, `RP_W_OWN`, `RP_NORMALIZE`, `RP_TOP_K_PRIMARY`
  - Example:
```bash
export RP_W_DAY_LORD=2.0 RP_W_ASC_NL=3.0 RP_W_MOON_NL=1.5 \
       RP_W_EXALT=1.0 RP_W_OWN=0.25 RP_NORMALIZE=true RP_TOP_K_PRIMARY=5
```

## Troubleshooting

- Readiness 503 in production: missing `AUTH_JWT_SECRET`/`AUTH_JWKS_URL` or `CORS_ALLOWED_ORIGINS`.
- 401 on REST: missing or invalid `Authorization: Bearer <jwt>`; verify `AUTH_AUDIENCE`/`AUTH_ISSUER` when using JWKS.
- 401 on streaming: request `/api/v1/auth/stream-token` and pass `?token=` (browser) or `Authorization` (non‑browser).
- Metrics with multiple workers: set writable `PROMETHEUS_MULTIPROC_DIR` (e.g., `/tmp/prometheus`).
- Port conflicts: free port 80 or change `PORT` mapping in `docker run`.
- Deploy version mismatch: deploy immutable GHCR tag (long SHA) and verify `/api/v1/health/version`.
## ATS Endpoints (Feature-Flagged)

- Feature flag: set `ENABLE_ATS=true` to enable ATS routes (default: true unless overridden). When disabled, endpoints return 403.
- Enable in Docker run:
```bash
docker run -d --rm --name vedacore-api -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e VC_ENV=remote \
  -e ENABLE_ATS=true \
  -e AUTH_JWT_SECRET='your-long-secret' \
  -e CORS_ALLOWED_ORIGINS='https://your-frontend.example' \
  ghcr.io/$OWNER/vedacore-api:latest
```

Notes:
- In production, set `API_KEY_V1_CUTOFF_DATE` to enable API key routing middleware.
- Health check inside the container targets `/api/v1/health/ready` and honors `PORT`.

- Quick curl examples (replace timestamp if desired):
```bash
# Status (returns healthy + context when enabled; 403 when disabled)
curl -sS http://127.0.0.1:8000/api/v1/ats/status | jq .

# Transit scores (neutral zeros with minimal ATS layer)
curl -sS -X POST http://127.0.0.1:8000/api/v1/ats/transit \
  -H 'content-type: application/json' -d '{}'

# Config dump
curl -sS http://127.0.0.1:8000/api/v1/ats/config | jq .
```

### ATS Scoring Model & Tuning

- Aspects considered: conjunction (0°), opposition (180°), trine (120°), square (90°), sextile (60°)
- Default orbs/weights (base): 8/1.0, 7/0.8, 6/0.7, 6/0.6, 4/0.5
- Condition factor: retrograde sources are scaled by 0.9
- KP emphasis: edges into Moon’s NL/SL/SSL can be up-weighted

Accepted target symbols (API): strictly one of
`SUN, MOO, JUP, RAH, MER, VEN, KET, SAT, MAR` (or integer IDs 1–9).

Configure via env:
```bash
# Orbs
export ATS_ORB_CONJ=8 ATS_ORB_OPP=7 ATS_ORB_TRI=6 ATS_ORB_SQR=6 ATS_ORB_SEX=4
# Base weights
export ATS_W_CONJ=1.0 ATS_W_OPP=0.8 ATS_W_TRI=0.7 ATS_W_SQR=0.6 ATS_W_SEX=0.5
# KP emphasis multipliers (destination planets)
export ATS_KP_NL=1.2 ATS_KP_SL=1.1 ATS_KP_SSL=1.05
```

Or via ATS context YAML (loaded from `config/ats/ats_market.yaml`):
```yaml
aspects:
  conj: { orb: 8.0, weight: 1.0 }
  opp:  { orb: 7.0, weight: 0.8 }
  tri:  { orb: 6.0, weight: 0.7 }
  sqr:  { orb: 6.0, weight: 0.6 }
  sex:  { orb: 4.0, weight: 0.5 }
kp_emphasis:
  nl: 1.2
  sl: 1.1
  ssl: 1.05
```

Defaults are provided in `config/ats/ats_market.yaml` with conservative KP emphasis values (`nl: 1.10`, `sl: 1.05`, `ssl: 1.02`) and standard aspect orbs/weights. Adjust these to tune scoring for your environment.

- Readiness 503: missing auth (`AUTH_JWT_SECRET`/`AUTH_JWKS_URL`) or CORS misconfig in prod.
- CORS errors: ensure comma-separated origins with `http(s)://` prefix; no wildcard in prod.
- 401 on streaming: validate token and `AUTH_AUDIENCE`/`AUTH_ISSUER`.

## Runbooks

- Extended deployment/runbook docs live in the monorepo: `Sbrg33/vedacore` under `vedacore/docs/feedback/8302025/`.

## Redis/Upstash for Streaming Resume

- Enable Redis-backed SSE resume for multi-worker deployments (Upstash compatible):
  - `REDIS_URL=rediss://<UPSTASH_USER>:<UPSTASH_PASS>@<host>:<port>`
  - Optional tuning:
    - `STREAM_RESUME_BACKEND=redis` (auto-enabled when `REDIS_URL` set)
    - `STREAM_RESUME_TTL_SECONDS=3600`
    - `STREAM_RESUME_MAX_ITEMS=5000`
    - `STREAM_RESUME_REDIS_PREFIX=sse:resume:`
    - `STREAM_SEQ_REDIS_PREFIX=sse:seq:`
  - Behavior: each published event is stored in a sorted set per topic; reconnects with `Last-Event-ID` fetch missed events via `ZRANGEBYSCORE`. Global event ids use per-topic `INCR` ensuring monotonic ordering across workers.

## Security Notes (Admin/Debug Endpoints)

- The following internal/debug endpoints require either an admin role or the `stream:debug` scope:
  - `GET /stream/_resume?topic=...` — returns Redis + memory resume stats for a topic
  - `GET /stream/_topics?include_resume=true` — returns topics with subscriber counts and optional resume stats
- Access control:
  - Role claim (preferred): `role` in JWT must be `admin` or `owner`
  - Scope claim (alternative): `scope` must include `stream:debug`
- Failures return RFC 7807 Problem JSON with status 403 and code `FORBIDDEN_DEBUG`.
