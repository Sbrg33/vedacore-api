#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Switching proxy upstream to BLUE…"
sed -i 's/reverse_proxy \(api_\)\w\+:8000/reverse_proxy api_blue:8000/' Caddyfile
docker compose exec caddy caddy reload

echo "Ensuring blue is up…"
docker compose up -d api_blue

echo "Verifying blue via Caddy health…"
for i in $(seq 1 18); do
  if curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:8081/api/v1/health/ready" >/dev/null 2>&1; then
    echo "Blue is healthy through Caddy. Proceeding to stop green."
    break
  fi
  sleep 5
done

echo "Stopping green…"
docker compose stop api_green || true

echo "Rollback complete."

echo "Recording deploy metadata…"
BLUE_IMG=$(grep -A2 '^  api_blue:' docker-compose.yml | sed -n 's/^[[:space:]]*image:[[:space:]]*//p' | head -n1)
GREEN_IMG=$(grep -A2 '^  api_green:' docker-compose.yml | sed -n 's/^[[:space:]]*image:[[:space:]]*//p' | head -n1)
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
printf '{"blue":"%s","green":"%s","active":"blue","ts":"%s"}\n' "$BLUE_IMG" "$GREEN_IMG" "$TS" > .last_release.json
echo "Wrote .last_release.json (active=blue)"
