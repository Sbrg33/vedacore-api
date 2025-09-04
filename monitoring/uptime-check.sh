#!/bin/bash
set -euo pipefail

# VedaCore API Uptime Monitoring Script
# Can be run via cron for continuous monitoring

API_HOST="${API_HOST:-localhost:8000}"
LOG_FILE="${LOG_FILE:-/var/log/vedacore-uptime.log}"
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_endpoint() {
    local endpoint="$1"
    local description="$2"
    local max_attempts="${3:-3}"
    
    for attempt in $(seq 1 $max_attempts); do
        if curl -fsS --connect-timeout 5 --max-time 15 "http://${API_HOST}${endpoint}" >/dev/null 2>&1; then
            log_message "✅ $description: OK (attempt $attempt)"
            return 0
        else
            log_message "⚠️  $description: Failed attempt $attempt"
            if [ $attempt -lt $max_attempts ]; then
                sleep 2
            fi
        fi
    done
    
    log_message "❌ $description: All attempts failed"
    return 1
}

send_alert() {
    local message="$1"
    log_message "🚨 ALERT: $message"
    
    if [ -n "$ALERT_WEBHOOK" ]; then
        curl -X POST "$ALERT_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"🚨 VedaCore API Alert: $message\"}" \
            >/dev/null 2>&1 || log_message "Failed to send webhook alert"
    fi
}

main() {
    log_message "🔍 Starting health check for $API_HOST"
    
    local failed_checks=0
    
    # Check critical endpoints
    if ! check_endpoint "/api/v1/health/up" "Basic Health"; then
        ((failed_checks++))
    fi
    
    if ! check_endpoint "/api/v1/health/ready" "Service Readiness"; then
        ((failed_checks++))
    fi
    
    if ! check_endpoint "/api/v1/health/version" "Version Info"; then
        ((failed_checks++))
    fi
    
    # Summary
    if [ $failed_checks -eq 0 ]; then
        log_message "✅ All health checks passed"
        exit 0
    else
        send_alert "$failed_checks health check(s) failed for $API_HOST"
        exit 1
    fi
}

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

main "$@"