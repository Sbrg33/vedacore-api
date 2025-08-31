---
name: Go-Live Sign-off Checklist
about: Verify production readiness and deploy the latest image
title: "Go-Live: vedacore-api @ sha-<commit>"
labels: release, go-live
assignees: ''
---

Checklist

- [ ] Build image for latest commit (push to main or manual dispatch)
  - Workflow: Build & Push Image (GHCR)
  - Expect tags: `sha-<commit>`; `latest` (if main)

- [ ] Prepare deploy inputs
  - Tag to deploy: `sha-<commit>`
  - Public URL (default): `https://api.vedacore.io`

- [ ] Verify repo secrets set (Org/Repo → Settings → Secrets and variables → Actions)
  - `DO_HOST`, `DO_USER`, `DO_SSH_KEY` (and optional `DO_PORT`)
  - `GHCR_USERNAME`, `GHCR_TOKEN` (read:packages)
  - `AUTH_JWT_SECRET`
  - `CORS_ALLOWED_ORIGINS`

- [ ] Deploy via workflow
  - Workflow: Deploy (SSH via GHCR)
  - Input `tag`: `sha-<commit>`

- [ ] Server readiness
  - `curl -fsS http://127.0.0.1:8000/api/v1/health/ready`
  - `docker logs vedacore-api` (if not ready)
  - Docs (local origin): `curl -fsS http://127.0.0.1:8000/api/docs >/dev/null && echo OK`
  - Metrics (local origin): `curl -fsS http://127.0.0.1:8000/metrics | head -n 10`

- [ ] Public smoke
  - `GET <PUBLIC_URL>/api/v1/health/ready` returns 200
  - `GET <PUBLIC_URL>/api/v1/health/up` returns "ok"
  - `GET <PUBLIC_URL>/api/docs` returns 200/308
  - `GET <PUBLIC_URL>/metrics` returns 200
  - ATS public endpoint: `curl -sS <PUBLIC_URL>/api/v1/ats/status | jq .status`

- [ ] Deployment version verification
  - `curl -fsS <PUBLIC_URL>/api/v1/version | jq -r .build_sha` matches deployed `sha-<commit>`
  - Alt: `curl -fsS <PUBLIC_URL>/api/v1/health/version | jq .`
  - Optional: `make check-health BASE=<PUBLIC_URL>` (prefers /health/up)

- [ ] CI gates green for target SHA
  - Minimal CI succeeded (unit + docker-smoke)
  - ATS symbol contract tests executed and passed
  - GHCR Build & Push succeeded for `sha-<commit>`

- [ ] Observability
  - `PROMETHEUS_MULTIPROC_DIR` is writable
  - `WORKERS` set as desired

- [ ] ATS endpoints (if ENABLE_ATS=true)
  - Status: `curl -sS http://127.0.0.1:8000/api/v1/ats/status | jq .`
  - Transit (defaults): `curl -sS -X POST http://127.0.0.1:8000/api/v1/ats/transit -H 'content-type: application/json' -d '{}'`
  - Transit (3-letter symbols): `curl -sS -X POST http://127.0.0.1:8000/api/v1/ats/transit -H 'content-type: application/json' -d '{"targets":["VEN","MER"]}'`
  - Transit (integers): `curl -sS -X POST http://127.0.0.1:8000/api/v1/ats/transit -H 'content-type: application/json' -d '{"targets":[6,5]}'`
  - Symbol validation (should 422): `curl -sS -X POST http://127.0.0.1:8000/api/v1/ats/transit -H 'content-type: application/json' -d '{"targets":["MERC","MOON"]}'`
  - Config: `curl -sS http://127.0.0.1:8000/api/v1/ats/config | jq .`

- [ ] KP Ruling Planets (KP v1)
  - RP (defaults):
    `curl -sS -X POST http://127.0.0.1:8000/api/v1/kp/ruling-planets -H 'content-type: application/json' -d '{"datetime":"2025-09-01T14:00:00Z","lat":40.7128,"lon":-74.0060}' | jq .`
  - RP (custom weights):
    `curl -sS -X POST http://127.0.0.1:8000/api/v1/kp/ruling-planets -H 'content-type: application/json' -d '{"datetime":"2025-09-01T14:00:00Z","lat":40.7128,"lon":-74.0060,"include_day_lord":true,"weights":{"asc_nl":3.0,"moon_nl":2.0}}' | jq .`

Notes

- Deploy workflow sets: `ENVIRONMENT=production`, `VC_ENV=remote`
- Use immutable tags (`sha-<commit>`) for rollbacks
- CORS must list explicit origins with protocol; wildcard is rejected in prod
- ATS symbol standard: 3-letter tokens (SUN,MOO,JUP,RAH,MER,VEN,KET,SAT,MAR) or integers (1-9)
- Auto-deploy: Triggers on successful GHCR build for main branch with deterministic SHA tags
