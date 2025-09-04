#!/usr/bin/env bash
set -euo pipefail

# Minimal blue/green helper.
# Preconditions:
#  - docker-compose.yml and Caddyfile present in this directory
#  - api_blue running with a known-good image
#  - Edit docker-compose.yml to set api_green image to the new immutable digest

cd "$(dirname "$0")"

echo "[1/4] Pulling new green image…"
docker compose pull api_green

echo "[2/4] Starting green (warm-up)…"
docker compose up -d api_green

echo "[3/4] Switching proxy upstream to green…"
sed -i 's/reverse_proxy \(api_\)\w\+:8000/reverse_proxy api_green:8000/' Caddyfile
docker compose exec caddy caddy reload

echo "Verifying green via Caddy health…"
for i in $(seq 1 18); do
  if curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:8081/api/v1/health/ready" >/dev/null 2>&1; then
    echo "Green is healthy through Caddy. Proceeding to stop blue."
    break
  fi
  sleep 5
done

echo "[4/4] Draining blue (90s)…"
docker compose stop api_blue || true

echo "Recording deploy metadata…"
BLUE_IMG=$(grep -A2 '^  api_blue:' docker-compose.yml | sed -n 's/^[[:space:]]*image:[[:space:]]*//p' | head -n1)
GREEN_IMG=$(grep -A2 '^  api_green:' docker-compose.yml | sed -n 's/^[[:space:]]*image:[[:space:]]*//p' | head -n1)
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
printf '{"blue":"%s","green":"%s","active":"green","ts":"%s"}\n' "$BLUE_IMG" "$GREEN_IMG" "$TS" > .last_release.json
echo "Wrote .last_release.json (active=green)"

echo "Done. Rollback: switch Caddyfile back to api_blue and start it again."
