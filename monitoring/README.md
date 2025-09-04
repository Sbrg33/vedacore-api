# VedaCore API Monitoring

Comprehensive monitoring setup for the VedaCore API deployment.

## Components

### 1. GitHub Actions Health Monitor
- **File**: `.github/workflows/health-monitor.yml`
- **Schedule**: Every 5 minutes during business hours, hourly otherwise
- **Features**:
  - Automated health checks
  - Issue creation on failures
  - Production monitoring

### 2. Uptime Check Script
- **File**: `monitoring/uptime-check.sh`
- **Usage**: Can be run locally or via cron
- **Features**:
  - Multiple endpoint testing
  - Retry logic
  - Webhook alerts
  - Logging

## Quick Start

### Test Local Deployment
```bash
# Test against local development server
API_HOST=localhost:8000 ./monitoring/uptime-check.sh
```

### Test Production Deployment
```bash
# Test against production (replace with your DO host)
API_HOST=your-do-host.com ./monitoring/uptime-check.sh
```

### Set Up Continuous Monitoring
```bash
# Add to crontab for every 5 minutes
*/5 * * * * /path/to/monitoring/uptime-check.sh

# Or with custom settings
*/5 * * * * API_HOST=your-host LOG_FILE=/var/log/vedacore.log /path/to/uptime-check.sh
```

## Configuration

### Environment Variables
- `API_HOST`: Target host (default: localhost:8000)
- `LOG_FILE`: Log file path (default: /var/log/vedacore-uptime.log)
- `ALERT_WEBHOOK`: Slack/Discord webhook URL for alerts

### GitHub Secrets Required
- `DO_HOST`: DigitalOcean droplet hostname/IP
- Other secrets already configured for deployment

## Monitoring Endpoints

The monitoring system checks these critical endpoints:
- `/api/v1/health/up` - Basic service availability
- `/api/v1/health/ready` - Service readiness (dependencies)
- `/api/v1/health/version` - Build information

## Alert Types

### GitHub Actions
- Creates GitHub issues on health check failures
- Includes timestamp, workflow run, and debugging steps

### Script Alerts
- Logs all events with timestamps
- Optional webhook notifications
- Retry logic with exponential backoff

## Troubleshooting

### Common Issues
1. **Connection refused**: Service not running or firewall blocking
2. **Timeout**: Service under high load or network issues
3. **503/502 errors**: Service starting up or misconfigured

### Debug Commands
```bash
# Check container status
docker ps | grep vedacore

# View container logs
docker logs vedacore-api

# Check service health directly
curl -v http://your-host/api/v1/health/ready

# Restart container if needed
docker restart vedacore-api
```

## Production Recommendations

1. **Set up external monitoring**: Use services like UptimeRobot, Pingdom, or DataDog
2. **Configure alerts**: Set up email/SMS notifications
3. **Log aggregation**: Forward logs to centralized logging system
4. **Metrics collection**: Integrate with Prometheus/Grafana
5. **Performance monitoring**: Track response times and error rates