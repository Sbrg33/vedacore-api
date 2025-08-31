#!/usr/bin/env bash
set -euo pipefail

# Ensure Prometheus multiprocess dir exists (needed for multi-worker metrics)
mkdir -p "${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"

# Default workers/port if not provided
UVICORN_WORKERS="${WORKERS:-4}"
APP_PORT="${PORT:-8000}"

# Honor reverse proxy headers (Cloudflare) for client IPs
exec uvicorn apps.api.main:app \
  --host 0.0.0.0 \
  --port "${APP_PORT}" \
  --workers "${UVICORN_WORKERS}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
