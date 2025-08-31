# VedaCore API (Minimal Export)

Production-ready FastAPI service for high-precision KP astrology calculations.

- Entrypoint: `apps.api.main:app`
- Health: `GET /api/v1/health/live` | Ready: `/api/v1/health/ready` | Docs: `/api/docs` | Metrics: `/metrics`
- Notes: Ephemeris data under `./swisseph/ephe`; atlas data under `src/data/atlas`
- CI: Minimal workflow runs pytest smoke with `PYTHONPATH=./src:.`

## Local Dev Quickstart

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
- Workers/metrics: `WORKERS=4`, `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus`
- Feature flags: `FEATURE_V1_ROUTING=true`, `ACTIVATION_ENABLED=false`
- Optional routing toggles: `ENABLE_ATS=true|false` (ATS endpoints return 403 when disabled)

## Production Quickstart (Docker)

```bash
docker build -t vedacore-api .
docker run -d --rm --name vedacore-api -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e VC_ENV=remote \
  -e AUTH_JWT_SECRET='your-long-secret' \
  -e CORS_ALLOWED_ORIGINS='https://your-frontend.example' \
  vedacore-api
```

Health gate:
```bash
curl -fsS http://localhost:8000/api/v1/health/ready || docker logs --tail 200 vedacore-api
```

Auth options:
- JWKS: set `AUTH_JWKS_URL` (add `AUTH_AUDIENCE`/`AUTH_ISSUER` as needed)
- HS256: set `AUTH_JWT_SECRET` (min 32 chars)

CORS rules:
- In production, origins must be explicit and include protocol; startup fails on misconfig.

## CI/CD Deploy (SSH)

- Workflow: `.github/workflows/deploy.yml`
- Required secrets: `DO_HOST`, `DO_USER`, `DO_SSH_KEY`, `GHCR_USERNAME`, `GHCR_TOKEN`, `AUTH_JWT_SECRET`, `CORS_ALLOWED_ORIGINS`
- Trigger: GitHub → Actions → Deploy (SSH via GHCR) → Run workflow

## GHCR Deploy

Images are published to GHCR via CI:
- Registry: `ghcr.io/$OWNER/vedacore-api`
- Tags: `sha-<commit>`; `latest` only on main; release tags as created

Run on a server:
```bash
export OWNER=<your_github_org_or_user>
docker login ghcr.io -u <GHCR_USERNAME> -p <GHCR_TOKEN>
docker pull ghcr.io/$OWNER/vedacore-api:latest

docker rm -f vedacore-api || true
docker run -d --rm --name vedacore-api -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e VC_ENV=remote \
  -e AUTH_JWT_SECRET='<32+ char random>' \
  -e CORS_ALLOWED_ORIGINS='https://your-frontend.example' \
  ghcr.io/$OWNER/vedacore-api:latest

curl -fsS http://127.0.0.1:8000/api/v1/health/ready
```

Notes:
- Prefer immutable tags (e.g., `sha-<commit>`) for rollbacks.

## Observability

- `/metrics` exposes Prometheus metrics.
- Multi-worker metrics use `PROMETHEUS_MULTIPROC_DIR` (default `/tmp/prometheus`).
- Internal metrics helpers are wired via `refactor.monitoring`.

Quick checks:
```bash
# Readiness (used in CI)
curl -fsS http://127.0.0.1:8000/api/v1/health/ready

# Docs (OpenAPI UI)
curl -fsS http://127.0.0.1:8000/api/docs >/dev/null && echo OK

# Metrics endpoint
curl -fsS http://127.0.0.1:8000/metrics | head -n 10
```

## Testing

- Run: `make test` or `PYTHONPATH=./src:. pytest -v`
- Minimal suite validates docs, readiness, and metrics.

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

- Quick curl (replace lat/lon/time):
```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/kp/ruling-planets \
  -H 'content-type: application/json' \
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

- Readiness 503: missing auth (`AUTH_JWT_SECRET`/`AUTH_JWKS_URL`) or CORS misconfig in prod.
- CORS errors: ensure comma-separated origins with `http(s)://` prefix; no wildcard in prod.
- 401 on streaming: validate token and `AUTH_AUDIENCE`/`AUTH_ISSUER`.

## Runbooks

- Extended deployment/runbook docs live in the monorepo: `Sbrg33/vedacore` under `vedacore/docs/feedback/8302025/`.
