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

# Honor reverse proxy headers (Cloudflare) for client IPs
exec uvicorn apps.api.main:app \
  --host 0.0.0.0 \
  --port "${APP_PORT}" \
  --workers "${UVICORN_WORKERS}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
