# Multi-stage build for KP Ephemeris API
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
       gcc \
       g++ \
    && apt-get clean \
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

# Build-time metadata (git SHA)
ARG VC_BUILD_SHA=unknown
ENV VC_BUILD_SHA=${VC_BUILD_SHA}

# Install runtime dependencies
RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
       curl \
    && apt-get clean \
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
ENV PYTHONPATH="/app/src:/app"
# Default service port (can be overridden)
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER ephemeris

# Runtime env (Prometheus multiprocess + sensible defaults)
ENV PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus"
ENV LOG_LEVEL="INFO"
ENV ACTIVATION_ENABLED="false"

# Worker scaling: Auto-detects system memory and sets optimal worker count
# ≤1GB: 1 worker (memory-optimized for small droplets)
# ≤2GB: 2 workers (balanced performance)  
# >2GB: 4 workers (high-performance)
# Override with: -e WORKERS=N (manual control)

# Health check configuration for Docker
# Uses readiness endpoint which validates all critical dependencies
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["sh","-c","curl -fsS http://localhost:${PORT}/api/v1/health/ready -H 'Accept: application/json' | grep -q '\"status\":\"ready\"'"]

# Expose port
# Expose default app port; host mapping handled at runtime (-p 80:8000 for prod)
EXPOSE 8000
# Optionally expose 80 for documentation; container still listens on $PORT
EXPOSE 80

# Entrypoint ensures runtime dirs exist, then launches uvicorn
COPY --chown=ephemeris:ephemeris tools/docker-entrypoint.sh /app/tools/docker-entrypoint.sh
RUN chmod +x /app/tools/docker-entrypoint.sh

# Run application via entrypoint
CMD ["/app/tools/docker-entrypoint.sh"]
