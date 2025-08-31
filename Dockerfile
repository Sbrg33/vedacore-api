# Multi-stage build for KP Ephemeris API
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements
WORKDIR /app
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -U pip wheel && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 ephemeris && \
    mkdir -p /app/cache && \
    chown -R ephemeris:ephemeris /app

WORKDIR /app

# Copy application code
COPY --chown=ephemeris:ephemeris . .

# Set Python path for target monorepo structure
ENV PYTHONPATH="/app/src:/app:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER ephemeris

# Runtime env (Prometheus multiprocess + sensible defaults)
ENV PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus"
ENV LOG_LEVEL="INFO"
ENV ACTIVATION_ENABLED="false"

# Health check configuration for Docker
# Uses readiness endpoint which validates all critical dependencies
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/ready -H "Accept: application/json" | \
        grep -q '"status":"ready"' || exit 1

# Expose port
EXPOSE 8000

# Entrypoint ensures runtime dirs exist, then launches uvicorn
COPY --chown=ephemeris:ephemeris tools/docker-entrypoint.sh /app/tools/docker-entrypoint.sh
RUN chmod +x /app/tools/docker-entrypoint.sh

# Run application via entrypoint
CMD ["/app/tools/docker-entrypoint.sh"]
