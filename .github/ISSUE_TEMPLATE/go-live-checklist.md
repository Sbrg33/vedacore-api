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
  - `curl -fsS http://127.0.0.1:8123/api/v1/health/ready`
  - `docker logs vedacore-api` (if not ready)

- [ ] Public smoke
  - `GET <PUBLIC_URL>/api/v1/health/ready` returns 200
  - `GET <PUBLIC_URL>/api/docs` returns 200/308
  - `GET <PUBLIC_URL>/metrics` returns 200

- [ ] Observability
  - `PROMETHEUS_MULTIPROC_DIR` is writable
  - `WORKERS` set as desired

Notes

- Deploy workflow sets: `ENVIRONMENT=production`, `VC_ENV=remote`
- Use immutable tags (`sha-<commit>`) for rollbacks
- CORS must list explicit origins with protocol; wildcard is rejected in prod

