# VedaCore API (Minimal Export)

Production-ready FastAPI service for high-precision KP astrology calculations.

- Entrypoint: apps.api.main:app
- Quick run (local):
  - pip install -r requirements.txt
  - export PYTHONPATH=./src:.
  - uvicorn apps.api.main:app --reload --port 8123
- Docker:
  - docker build -t vedacore-api .
  - docker run -p 8123:8123 vedacore-api

Health: GET /api/v1/health/live | Ready: /api/v1/health/ready | Docs: /api/docs

Notes:
- Ephemeris data included at ./swisseph/ephe
- Atlas data under src/data/atlas

CI: Minimal workflow runs pytest smoke + small API subset with `PYTHONPATH=./src:.`.

## Production Quickstart

Environment variables (minimal):
- `ENVIRONMENT=production`
- `AUTH_JWT_SECRET=<32+ char random>` (or set `AUTH_JWKS_URL=https://.../.well-known/jwks.json`)
- `CORS_ALLOWED_ORIGINS=https://your-frontend.example`
- Optional: `WORKERS=4`, `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus`

Run with Docker:
```bash
docker build -t vedacore-api .
docker run -d --rm --name vedacore-api -p 8123:8123 \
  -e ENVIRONMENT=production \
  -e AUTH_JWT_SECRET='your-long-secret' \
  -e CORS_ALLOWED_ORIGINS='https://your-frontend.example' \
  vedacore-api
```

Health check:
```bash
curl -fsS http://localhost:8123/api/v1/health/ready || tail -n 200 $(docker logs vedacore-api 2>&1)
```

## CI/CD Deploy (SSH)

- Workflow: `.github/workflows/deploy.yml`
- Required secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `AUTH_JWT_SECRET`, `CORS_ALLOWED_ORIGINS`
- Optional: `DEPLOY_PORT`

Trigger deployment:
- From GitHub → Actions → Deploy (SSH) → Run workflow

## GHCR Deploy

Images are published to GitHub Container Registry (GHCR) via CI:
- Registry: `ghcr.io/$OWNER/vedacore-api` (set `OWNER` to your org/user)
- Tags: `sha-<commit>`, `latest` on main, and release tags (e.g., `v1.0.0`)

Pull and run on a server:
```bash
# 0) Set OWNER (once per shell)
export OWNER=<your_github_org_or_user>

# 1) Login (PAT with read:packages)
docker login ghcr.io -u <GHCR_USERNAME> -p <GHCR_TOKEN>

# 2) Pull image
docker pull ghcr.io/$OWNER/vedacore-api:latest

# 3) Run with production env
docker rm -f vedacore-api || true
docker run -d --rm --name vedacore-api -p 8123:8123 \
  -e ENVIRONMENT=production \
  -e AUTH_JWT_SECRET='<32+ char random>' \
  -e CORS_ALLOWED_ORIGINS='https://your-frontend.example' \
  ghcr.io/$OWNER/vedacore-api:latest

# 4) Health gate
curl -fsS http://127.0.0.1:8123/api/v1/health/ready
```

Notes:
- `OWNER` should match your GitHub org/user that owns the package.
- Use an immutable tag (e.g., `sha-<commit>`) for rollbacks.
- The included `Deploy (SSH via GHCR)` workflow automates these steps over SSH.
