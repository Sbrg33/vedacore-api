# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Essential Development Commands
- **Install dependencies**: `make install` or `pip install -r requirements.txt`
- **Run locally (with reload)**: `make run` (starts uvicorn on http://127.0.0.1:8000)
- **Run tests**: `make test` or `PYTHONPATH=./src:. pytest -v`
- **Test single file**: `PYTHONPATH=./src:. pytest tests/test_specific.py -v`
- **Local smoke test**: `make smoke-local` (starts API, checks health, stops)
- **Docker build**: `make docker-build`
- **Docker smoke test**: `make docker-smoke`
- **Health check**: `make check-health BASE=http://127.0.0.1:8000`

### Environment Setup
Always set `PYTHONPATH=./src:.` when running Python commands directly:
```bash
export PYTHONPATH=./src:.
uvicorn apps.api.main:app --reload --port 8000
```

## Architecture Overview

### Core Structure
- **Entry point**: `apps.api.main:app` (FastAPI application in `src/apps/api/main.py`)
- **API layers**: 
  - V1 API (`src/api/routers/v1/`) - Feature-flagged modern API
  - Legacy API (`src/api/routers/`) - Backward compatibility
- **Business logic**: `src/refactor/` - Core KP astrology calculations
- **Application layer**: `src/app/` - Services, models, configuration
- **Data directories**: 
  - Ephemeris data: `./swisseph/ephe`
  - Atlas data: `src/data/atlas`
  - Cache: `data/cache/KP` (auto-created)

### Key Components
- **KP Engine**: Krishnamurti Paddhati astrology system in `src/refactor/`
- **Streaming**: WebSocket (`/ws`) and SSE (`/stream`) endpoints with JWT auth
- **Monitoring**: Prometheus metrics at `/metrics`, health checks at `/api/v1/health/*`
- **Production hardening**: Redis-backed services, rate limiting, token validation

## Environment Configuration

### Environment Variables
- **Core settings**:
  - `ENVIRONMENT`: `development|staging|production` (affects security hardening)
  - `VC_ENV`: `local|remote` (selects DB/cloud configuration)
  - `PYTHONPATH`: Always set to `./src:.`

- **Authentication** (required for production):
  - `AUTH_JWT_SECRET`: Min 32 chars for HS256 tokens
  - `AUTH_JWKS_URL`: Alternative JWKS endpoint
  - `AUTH_AUDIENCE`/`AUTH_ISSUER`: Optional JWKS validation

- **CORS** (required for production):
  - `CORS_ALLOWED_ORIGINS`: Comma-separated with protocols (no wildcard in production)

- **Feature flags**:
  - `FEATURE_V1_ROUTING=true`: Enable modern V1 API routes
  - `ENABLE_ATS=true`: Enable ATS (Aspect-Transfer Scoring) endpoints
  - `ACTIVATION_ENABLED=false`: Disable activation API by default

### Production Security
Production environment (`ENVIRONMENT=production`) enforces:
- Required authentication configuration
- Explicit CORS origins (no wildcards)
- Production hardening middleware stack
- Enhanced logging and monitoring

## Testing

### Test Structure
- Test files in `tests/` directory
- Pytest configuration in `pytest.ini`
- Test path: `testpaths = tests`

### Health Endpoints
- **Plain liveness**: `GET /api/v1/health/up` (plaintext "ok")
- **JSON liveness**: `GET /api/v1/health/live`
- **Readiness**: `GET /api/v1/health/ready` (validates all dependencies)
- **Version**: `GET /api/v1/version` (build SHA and symbol policy)

## KP Astrology Specifics

### Core KP Features
- **Ruling planets**: `/api/v1/kp/ruling-planets` with customizable weights
- **Horary calculations**: `/api/v1/kp/horary` (1-249 numbers)
- **Lord changes**: Track planetary period transitions
- **Micro-timing**: Sub-minute precision calculations
- **Transit scoring**: ATS system for aspect analysis

### KP Configuration
- **Ruling planet weights**: Configurable via API payload or environment variables (`RP_W_*`)
- **ATS scoring**: Aspect orbs and weights in `config/ats/ats_market.yaml`
- **House systems**: Placidus and KP house calculations

## Docker & Deployment

### Memory-Optimized Worker Scaling
VedaCore automatically detects system memory and optimizes worker count:
- **≤1GB RAM**: 1 worker (optimal for small droplets like DO Basic)
- **≤2GB RAM**: 2 workers (balanced performance) 
- **>2GB RAM**: 4 workers (high-performance)

Override with `WORKERS` environment variable if needed.

### Disk Space Management
Automatic disk management prevents space issues:
- **Docker log rotation**: Max 10MB per log file, 3 files retained
- **Cache cleanup**: Removes files older than 7 days on startup
- **Weekly cleanup**: Automated Docker system prune via cron
- **Disk monitoring**: Alerts at 80%, emergency cleanup at 90%

### Docker Usage
```bash
# Build production image
docker build -t vedacore-api .

# Run with production settings (auto-scales workers based on system memory)
docker run -d --name vedacore-api -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e VC_ENV=remote \
  -e AUTH_JWT_SECRET='your-secret-32-chars' \
  -e CORS_ALLOWED_ORIGINS='https://your-app.com' \
  vedacore-api

# Manual worker override (if needed)
docker run -d --name vedacore-api -p 8000:8000 \
  -e WORKERS=1 \
  -e ENVIRONMENT=production \
  vedacore-api
```

### GHCR Deployment
- Registry: `ghcr.io/$OWNER/vedacore-api`
- Tags: `sha-<commit>` (immutable), `latest` (main branch)
- Auto-deploy via GitHub Actions on main branch

## API Features

### Streaming Endpoints
- **SSE**: `GET /stream/{topic}?token=jwt_token`
- **WebSocket**: `ws://localhost:8000/ws?token=jwt_token`
- Authentication via JWT query parameter

### Key API Groups
- **Core KP**: `/api/v1/kp/*` - Ruling planets, horary, positions
- **Timing**: `/api/v1/signals/*` - Market timing signals
- **Transit**: `/api/v1/transit/*` - Planetary transit events
- **Streaming**: Real-time data feeds with backpressure management

## Development Notes

### Code Organization
- All astronomical calculations use PySwissEph (`pyswisseph==2.10.3.2`)
- NumPy/Numba for performance-critical calculations
- FastAPI with ORJSON for optimal JSON performance
- Redis for production caching and session management

### Performance Features
- JIT compilation warmup on startup
- Prometheus metrics and monitoring
- Multi-worker production deployment
- Comprehensive caching strategy

## Troubleshooting

### Common Issues
- **503 Readiness**: Check auth config (`AUTH_JWT_SECRET`) and CORS settings
- **CORS errors**: Ensure origins include `http://`/`https://` protocol
- **Import errors**: Verify `PYTHONPATH=./src:.` is set
- **Docker issues**: Check health endpoint: `curl http://localhost:8000/api/v1/health/ready`

### Debug Commands
```bash
# Check API status
curl -fsS http://127.0.0.1:8000/api/v1/health/ready

# View metrics
curl -fsS http://127.0.0.1:8000/metrics | head -n 10

# Test KP endpoint
curl -X POST http://127.0.0.1:8000/api/v1/kp/ruling-planets \
  -H 'Content-Type: application/json' \
  -d '{"datetime":"2025-09-01T14:00:00Z","lat":40.7128,"lon":-74.0060}'
```
