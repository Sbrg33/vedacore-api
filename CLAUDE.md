# VedaCore Signals API

High-performance FastAPI service providing Krishnamurti Paddhati (KP) astrology calculations and financial timing signals.

## Quick Start

```bash
# Install and run locally
make install && make run
# API available at: http://127.0.0.1:8000

# Docker deployment
docker build -t vedacore-api . && docker run -p 8000:8000 vedacore-api
```

## Core Architecture

- **FastAPI** web framework with automatic OpenAPI documentation
- **KP Engine** (`src/refactor/`) - Core astrological calculations using PySwissEph
- **Health System** - Comprehensive monitoring at `/api/v1/health/*`
- **Authentication** - JWT-based with HS256 or JWKS support
- **Streaming** - WebSocket and SSE endpoints for real-time data

## Environment Configuration

### Required for Production
```bash
ENVIRONMENT=production
AUTH_JWT_SECRET="your-32-char-secret"
CORS_ALLOWED_ORIGINS="https://your-app.com"
```

### Optional
```bash
VC_ENV=local|remote          # Database configuration
REDIS_URL="redis://..."      # Caching (recommended for production)
```

## Key Endpoints

- **Health**: `/api/v1/health/ready` - Service readiness
- **Docs**: `/api/docs` - Interactive API documentation  
- **KP Calculations**: `/api/v1/kp/*` - Ruling planets, horary, positions
- **Streaming**: `/ws` (WebSocket) and `/stream` (SSE)

## Development Commands

```bash
make test           # Run tests
make check-health   # Verify API health
make docker-smoke   # Docker integration test
```

## Production Deployment

- **Registry**: `ghcr.io/sbrg33/vedacore-api`
- **Tags**: `sha-<commit>` for deterministic deployments
- **Auto-scaling**: Optimized worker count based on available memory
- **Monitoring**: Prometheus metrics at `/metrics`

## Project Structure

```
src/
├── api/           # FastAPI routes and middleware
├── refactor/      # KP astrology engine
└── apps/          # Application configuration

.github/workflows/ # CI/CD automation
config/           # ATS scoring and system configurations
tests/           # Test suites
```

Ready for production use with comprehensive health monitoring and deterministic deployments.