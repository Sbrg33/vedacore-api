#!/usr/bin/env bash
set -euo pipefail

# Ensure Prometheus multiprocess dir exists (needed for multi-worker metrics)
mkdir -p "${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"

# Default workers if not provided
UVICORN_WORKERS="${WORKERS:-4}"

exec uvicorn apps.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${UVICORN_WORKERS}"

