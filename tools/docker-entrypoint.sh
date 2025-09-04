#!/usr/bin/env bash
set -euo pipefail

# Ensure Prometheus multiprocess dir exists (needed for multi-worker metrics)
mkdir -p "${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"

# Cache management: Clean up old cache files on startup (prevent disk buildup)
if [ -d "${VEDACORE_CACHE_DIR:-/app/cache}" ]; then
  find "${VEDACORE_CACHE_DIR:-/app/cache}" -type f -mtime +7 -delete 2>/dev/null || true
  echo "🧹 Cleaned up cache files older than 7 days"
fi

# Intelligent worker scaling based on available memory and environment
if [ -z "${WORKERS:-}" ]; then
  # Get total memory in MB (fallback to 1GB if detection fails)
  TOTAL_MEM_MB=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "1024")
  
  if [ "$TOTAL_MEM_MB" -le 1024 ]; then
    # 1GB or less: Single worker (optimal for small droplets)
    UVICORN_WORKERS=1
    echo "🎯 Memory-optimized: Using 1 worker for ${TOTAL_MEM_MB}MB system"
  elif [ "$TOTAL_MEM_MB" -le 2048 ]; then
    # 2GB: 2 workers
    UVICORN_WORKERS=2
    echo "⚡ Balanced: Using 2 workers for ${TOTAL_MEM_MB}MB system"
  else
    # 4GB+: 4 workers (original default)
    UVICORN_WORKERS=4
    echo "🚀 High-performance: Using 4 workers for ${TOTAL_MEM_MB}MB system"
  fi
else
  UVICORN_WORKERS="${WORKERS}"
  echo "📌 Manual override: Using ${UVICORN_WORKERS} workers (WORKERS env var)"
fi

APP_PORT="${PORT:-8000}"

# Fail fast on missing critical env in production
if [ "${ENVIRONMENT:-development}" = "production" ]; then
  if [ -z "${AUTH_JWKS_URL:-}" ] && [ -z "${AUTH_JWT_SECRET:-}" ]; then
    echo "ERROR: In production, set AUTH_JWKS_URL or AUTH_JWT_SECRET" >&2
    exit 1
  fi
  if [ -z "${CORS_ALLOWED_ORIGINS:-}" ]; then
    echo "ERROR: In production, set CORS_ALLOWED_ORIGINS (comma-separated, protocol-prefixed)" >&2
    exit 1
  fi
fi

# Graceful shutdown timeout (seconds)
UVICORN_GRACEFUL_TIMEOUT="${UVICORN_GRACEFUL_TIMEOUT:-90}"

# Honor reverse proxy headers (Cloudflare) for client IPs
exec uvicorn apps.api.main:app \
  --host 0.0.0.0 \
  --port "${APP_PORT}" \
  --workers "${UVICORN_WORKERS}" \
  --timeout-keep-alive 3600 \
  --timeout-graceful "${UVICORN_GRACEFUL_TIMEOUT}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
