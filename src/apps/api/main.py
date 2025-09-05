#!/usr/bin/env python3
"""
VedaCore Signals API - Main Application
FastAPI application for KP ephemeris-based trading signals
"""

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse

try:
    from fastapi.responses import ORJSONResponse

    ORJSON_AVAILABLE = True
except ImportError:
    ORJSON_AVAILABLE = False
import asyncio
import uuid
import os

from contextlib import asynccontextmanager
from pathlib import Path

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.routers.advisory import router as advisory_router
from api.routers.atlas import router as atlas_router
from api.routers.ats import router as ats_router
from api.routers.dasha import router as dasha_router
from api.routers.eclipse import router as eclipse_router
from api.routers.fortuna import router as fortuna_router
from api.routers.health import router as health_router
from api.routers.houses import router as houses_router
from api.routers.kp_horary import router as kp_horary_router
from api.routers.kp_ruling_planets import router as kp_ruling_planets_router
from api.routers.location import router as location_router
from api.routers.location_stream import router as location_stream_router
from api.routers.micro import router as micro_router
from api.routers.moon import router as moon_router
from api.routers.nodes import router as nodes_router
from api.routers.panchanga import router as panchanga_router
from api.routers.signals import router as signals_router
from api.routers.enhanced_signals import router as enhanced_signals_router
from api.routers.strategy import router as strategy_router
from api.routers.stream import router as stream_router
from api.routers.tara import router as tara_router
from api.routers.transit_events import router as transit_events_router
from api.routers.ws import router as ws_router
from app.core.logging import get_api_logger, setup_logging
from app.core.environment import get_complete_config
from refactor.monitoring import set_feature_flag, setup_prometheus_metrics
from config.feature_flags import get_feature_flags
from api.models.responses import Problem
from api.services.auth import require_jwt_header_or_query, AuthContext, optional_jwt, optional_jwt_query
from api.services.rate_limiter import check_qps_limit
from fastapi.openapi.utils import get_openapi
from shared.otel import init_tracing as _otel_init_tracing

# Test/CI detection and warmup controls
IN_TEST = (
    os.getenv("VC_TEST_MODE", "false").lower() == "true"
    or ("PYTEST_CURRENT_TEST" in os.environ)
)
SKIP_WARMUP = os.getenv("VC_SKIP_WARMUP", "false").lower() in ("true", "1")

# Initialize structured logging EARLY (before any logger usage)
setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format_json=os.getenv("LOG_FORMAT", "json").lower() == "json",
)
logger = get_api_logger("main")

# OTEL tracing is initialized after app creation below

# REST QPS guard: enforce per-tenant request rate limits on REST endpoints
async def rest_qps_guard(
    auth_header: AuthContext | None = Depends(optional_jwt),
    auth_query: AuthContext | None = Depends(optional_jwt_query),
):
    """Rate limiting guard; auth optional in local/test environments.

    If no auth is present, uses a public tenant bucket to keep tests simple.
    """
    auth = auth_header or auth_query
    tenant = auth.tenant_id if auth and auth.tenant_id else "public"
    await check_qps_limit(tenant)

# Guard: warn if environment points to obsolete monorepo paths
try:
    import sys
    _pp = os.getenv("PYTHONPATH", "")
    if "/home/sb108/projects/vedacore" in _pp or any(
        "/home/sb108/projects/vedacore" in p for p in sys.path
    ):
        logger.warning(
            "⚠️ Detected legacy PYTHONPATH entry for /home/sb108/projects/vedacore. "
            "This monorepo is deprecated; remove it to avoid accidental cross-imports."
        )
except Exception:
    pass

# V1 API routers (conditional based on feature flag)
try:
    from api.routers.v1 import (
        jyotish_router,
        kp_router, 
        ref_router,
        atlas_router as atlas_v1_router,
        auth_router,
        stream_router as stream_v1_router
    )
    from api.routers.v1.shims import legacy_shim_router
    V1_ROUTERS_AVAILABLE = True
    logger.info("V1 API routers loaded successfully")
except ImportError as e:
    logger.warning(f"V1 routers not available: {e}")
    V1_ROUTERS_AVAILABLE = False

# Import production hardening middleware
try:
    from api.middleware.ephemeris_headers import EphemerisHeadersMiddleware
    from api.middleware.log_redaction import LogRedactionMiddleware
    from api.middleware.usage_metering import UsageMeteringMiddleware
    from api.middleware.idempotency import IdempotencyMiddleware
    from api.middleware.request_id import RequestIDMiddleware
    from api.middleware.api_key_routing import install_api_key_routing_middleware
    from api.middleware.deprecation_headers import install_deprecation_headers_middleware
    from api.services.redis_config import get_redis, close_redis
    from api.services.stream_backpressure import get_backpressure_manager, shutdown_backpressure_manager
    PRODUCTION_HARDENING_AVAILABLE = True
    logger.info("🔧 Production hardening middleware loaded")
except ImportError as e:
    logger.warning(f"Production hardening not available: {e}")
    PRODUCTION_HARDENING_AVAILABLE = False

# Global Locality Research - Activation API (feature flagged)
ACTIVATION_ENABLED = os.getenv("ACTIVATION_ENABLED", "false").lower() == "true"
if ACTIVATION_ENABLED:
    try:
        from api.routers.activation import router as activation_router

        logger.info("Activation API enabled - Global Locality Research system loaded")
    except ImportError as e:
        logger.warning(f"Activation API import failed: {e}")
        ACTIVATION_ENABLED = False

# Ensure cache directory exists
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "KP"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def validate_production_security():
    """Validate production security configuration."""
    env = os.getenv("ENVIRONMENT", "development").lower()

    if env == "production":
        logger.info("🔒 Validating production security configuration...")

        # Check authentication
        auth_jwks = os.getenv("AUTH_JWKS_URL")
        auth_secret = os.getenv("AUTH_JWT_SECRET")

        if not auth_jwks and not auth_secret:
            raise RuntimeError(
                "PRODUCTION STARTUP ERROR: No authentication configured. "
                "Set AUTH_JWKS_URL or AUTH_JWT_SECRET."
            )

        # CORS validation is now handled by configure_cors_security()
        # It will raise RuntimeError if CORS is misconfigured in production
        logger.info("🔒 CORS security validation handled by configure_cors_security()")

        # Validate other critical settings
        required_prod_settings = {
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
            "LOG_FORMAT": os.getenv("LOG_FORMAT", "json"),
        }

        for setting, value in required_prod_settings.items():
            logger.info(f"🔧 {setting}: {value}")

        # Require production hardening components to be available
        if not PRODUCTION_HARDENING_AVAILABLE:
            raise RuntimeError(
                "PRODUCTION STARTUP ERROR: Required production hardening middleware not available"
            )

        logger.info("✅ Production security validation complete")


async def initialize_configurations():
    """Initialize all system configurations."""
    configs = [
        ("house_config", "initialize_house_config", "House configuration"),
        ("nodes_config", "initialize_node_config", "Node configuration"),
        ("eclipse_config", "initialize_eclipse_config", "Eclipse configuration"),
        ("moon_config", "initialize_moon_config", "Moon configuration"),
        ("micro_config", "initialize_micro_config", "Micro-timing configuration"),
        ("strategy_config", "initialize_strategy_config", "Strategy configuration"),
        ("direction_config", "initialize_direction_config", "Direction configuration"),
    ]

    for module_name, func_name, desc in configs:
        try:
            module = __import__(f"refactor.{module_name}", fromlist=[func_name])
            init_func = getattr(module, func_name)
            init_func()
            logger.info(f"{desc} initialized")
        except Exception as e:
            logger.warning(f"{desc} initialization failed: {e}")


async def initialize_systems():
    """Initialize system adapters."""
    try:
        from interfaces.initialize import get_system_status
        from interfaces.initialize import initialize_systems as init_systems

        systems = init_systems()
        logger.info(f"Initialized systems: {systems}")

        status = get_system_status()
        logger.info(f"System registry status: {status['registered_systems']}")
    except Exception as e:
        logger.warning(f"System initialization failed: {e}")


async def initialize_warmup():
    """Perform JIT compilation and cache warmup."""
    try:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        from refactor import facade
        from refactor.kp_chain import warmup_kp_calculations

        warmup_kp_calculations()

        now = datetime.now(ZoneInfo("UTC"))
        _ = facade.get_kp_lord_changes(
            now - timedelta(hours=1), now, planet_id=2, levels=("nl", "sl", "sl2")
        )

        logger.info("Warming up KP JIT compilation...")
        from refactor.kp_horary import HoraryConfig, compute_horary

        cfg = HoraryConfig(mode="unix_mod")
        for t in (1, 1000, 86_400, 123456789):
            compute_horary(t, cfg, moon_chain_planets=("MO", "MO", "MO"))

        logger.info("KP JIT warmup completed")
    except Exception as e:
        logger.warning(f"Warmup partially failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting VedaCore API...")

    background_tasks = []
    try:
        await _startup_initialization()
        background_tasks = await _initialize_background_services()
        _set_startup_feature_flags()
        yield
    finally:
        await _graceful_shutdown(app, background_tasks)


async def _startup_initialization():
    """Initialize core application components."""
    await validate_production_security()
    await initialize_configurations()
    await initialize_systems()
    await _initialize_advisory_adapters()
    # Skip production hardening and JIT warmup during tests/CI or when explicitly disabled
    if not IN_TEST:
        await _initialize_production_hardening()
    if not (IN_TEST or SKIP_WARMUP):
        await initialize_warmup()


async def _initialize_advisory_adapters():
    """Initialize advisory adapters for KP endpoints."""
    try:
        from interfaces.advisory_adapter_protocol import advisory_registry

        registered_adapters = advisory_registry.list_adapters()
        logger.info(f"Advisory adapters registered: {registered_adapters}")
    except Exception as e:
        logger.warning(f"Advisory adapter initialization failed: {e}")


async def _initialize_production_hardening():
    """Initialize production hardening systems (PM requirements)."""
    if not PRODUCTION_HARDENING_AVAILABLE:
        logger.info("⏭️  Production hardening not available, skipping initialization")
        return
    
    try:
        # Initialize Redis with production durability settings
        redis_mgr = await get_redis()
        redis_health = await redis_mgr.health_check()
        
        if redis_health.get("status") == "healthy":
            logger.info("✅ Redis initialized with production durability settings")
            logger.info(f"   Memory usage: {redis_health.get('memory_usage', {}).get('usage_ratio', 0):.1%}")
        else:
            logger.error(f"❌ Redis health check failed: {redis_health}")
            raise RuntimeError("Redis initialization failed")
        
        # Initialize stream backpressure manager
        backpressure_mgr = await get_backpressure_manager()
        backpressure_health = await backpressure_mgr.health_check()
        
        if backpressure_health.get("status") in ("healthy", "idle"):
            logger.info("✅ Stream backpressure manager initialized")
            logger.info(f"   Global subscriber limit: {backpressure_mgr.max_total_subscribers}")
            logger.info(f"   Per-tenant limit: {backpressure_mgr.max_subscribers_per_tenant}")
        else:
            logger.error(f"❌ Backpressure manager health check failed: {backpressure_health}")
            raise RuntimeError("Backpressure manager initialization failed")
        
        logger.info("🔧 Production hardening systems initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Production hardening initialization failed: {e}")
        # Don't fail startup, but log the issue
        logger.warning("⚠️  Continuing without full production hardening")


async def _initialize_background_services():
    """Initialize background services and return task list."""
    # Keep background services light under tests/CI to avoid port conflicts and latency
    if not IN_TEST:
        _setup_prometheus_metrics()
        _initialize_streaming_services()
        await _start_moon_publisher()
    return []  # Return empty task list for now


def _setup_prometheus_metrics():
    """Setup Prometheus monitoring."""
    if setup_prometheus_metrics(port=9090):
        logger.info("Prometheus metrics available on port 9090")
        try:
            from refactor.monitoring import setup_eclipse_metrics

            if setup_eclipse_metrics():
                logger.info("Eclipse metrics initialized")
        except Exception as e:
            logger.warning(f"Eclipse metrics setup failed: {e}")


def _initialize_streaming_services():
    """Initialize streaming metrics services."""
    try:
        from api.services.metrics import initialize_streaming_metrics

        initialize_streaming_metrics()
        logger.info("Streaming metrics initialized")
    except Exception as e:
        logger.warning(f"Streaming metrics initialization failed: {e}")


async def _start_moon_publisher():
    """Start Moon publisher service."""
    try:
        from api.services.moon_publisher import moon_publisher

        if await moon_publisher.start():
            logger.info("Moon publisher started successfully")
        else:
            logger.info("Moon publisher disabled (MOON_PUBLISHER_ENABLED=false)")
    except Exception as e:
        logger.warning(f"Moon publisher initialization failed: {e}")


def _set_startup_feature_flags():
    """Set initial feature flags after startup."""
    set_feature_flag("api_enabled", True)
    set_feature_flag("cache_enabled", True)


async def _graceful_shutdown(app: FastAPI, background_tasks):
    """Handle graceful application shutdown."""
    logger.info("Initiating graceful shutdown...")
    try:
        set_feature_flag("api_enabled", False)
        app.state.accepting_connections = False
        logger.info("Stopped accepting new connections")

        await _cancel_background_tasks(background_tasks)
        # Shorter grace period for non-production for faster local dev
        sleep_sec = 5 if os.getenv("ENVIRONMENT", "development").lower() == "production" else 0.5
        await asyncio.sleep(sleep_sec)
        await _stop_moon_publisher()
        await _shutdown_production_hardening()
        logger.info("Graceful shutdown completed successfully")
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")

    logger.info("VedaCore API shutdown complete")


async def _cancel_background_tasks(background_tasks):
    """Cancel and wait for background tasks to complete."""
    for task in background_tasks:
        if not task.done():
            task.cancel()
    logger.info("Cancelled background publisher tasks")

    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)


async def _stop_moon_publisher():
    """Stop Moon publisher service."""
    try:
        from api.services.moon_publisher import moon_publisher

        await moon_publisher.stop()
        publisher_stats = moon_publisher.get_stats()
        logger.info(f"Moon publisher stopped: {publisher_stats}")
    except Exception as e:
        logger.warning(f"Error stopping Moon publisher: {e}")


async def _shutdown_production_hardening():
    """Shutdown production hardening systems (PM requirements)."""
    if not PRODUCTION_HARDENING_AVAILABLE:
        return
    
    try:
        # Shutdown stream backpressure manager
        logger.info("🔧 Shutting down stream backpressure manager...")
        await shutdown_backpressure_manager()
        logger.info("✅ Stream backpressure manager shutdown complete")
        
        # Close Redis connections
        logger.info("🔧 Closing Redis connections...")
        await close_redis()
        logger.info("✅ Redis connections closed")
        
        logger.info("🔧 Production hardening shutdown complete")
        
    except Exception as e:
        logger.error(f"❌ Production hardening shutdown failed: {e}")


# Create FastAPI app with ORJSON optimization if available
app_kwargs = {
    "title": "VedaCore Signals API",
    "description": "High-precision KP ephemeris calculations for trading signals",
    "version": "1.0.0",
    "lifespan": lifespan,
    "docs_url": "/api/docs",
    "redoc_url": "/api/redoc",
}

if ORJSON_AVAILABLE:
    app_kwargs["default_response_class"] = ORJSONResponse

app = FastAPI(**app_kwargs)

# Optional OpenTelemetry tracing (no-op if disabled or deps missing)
if _otel_init_tracing(app):
    logger.info("📡 OpenTelemetry tracing initialized")


def configure_cors_security():
    """Configure CORS with production-grade security controls."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()

    if cors_origins_env:
        allowed_origins = _validate_cors_origins_from_env(cors_origins_env, env)
    else:
        allowed_origins = []

    return _handle_cors_fallback(allowed_origins, env)


def _validate_cors_origins_from_env(cors_origins_env, env):
    """Parse and validate CORS origins from environment variable."""
    raw_origins = [
        origin.strip() for origin in cors_origins_env.split(",") if origin.strip()
    ]
    allowed_origins = []

    for origin in raw_origins:
        if origin == "*":
            _validate_wildcard_origin(env)
            allowed_origins.append(origin)
        elif origin.startswith(("http://", "https://")):
            _validate_url_origin(origin, env)
            allowed_origins.append(origin)
        else:
            _handle_invalid_origin_protocol(origin, env)

    return allowed_origins


def _validate_wildcard_origin(env):
    """Validate wildcard origin based on environment."""
    if env == "production":
        logger.error(
            "🚨 SECURITY ERROR: Wildcard CORS origin (*) not allowed in production"
        )
        raise RuntimeError(
            "CORS Security Error: Wildcard origins prohibited in production"
        )
    else:
        logger.warning("⚠️  SECURITY WARNING: Wildcard CORS origin should not be used")


def _validate_url_origin(origin, env):
    """Validate URL format origin."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(origin)
        if parsed.netloc:
            logger.info(f"✅ CORS origin allowed: {origin}")
        else:
            logger.error(f"❌ Invalid CORS origin format: {origin}")
            if env == "production":
                raise RuntimeError(
                    f"CORS Security Error: Invalid origin format: {origin}"
                )
    except Exception as e:
        logger.error(f"❌ CORS origin validation failed for {origin}: {e}")
        if env == "production":
            raise RuntimeError(
                f"CORS Security Error: Origin validation failed: {origin}"
            ) from e


def _handle_invalid_origin_protocol(origin, env):
    """Handle invalid origin protocol."""
    logger.error(f"❌ CORS origin must start with http:// or https://: {origin}")
    if env == "production":
        raise RuntimeError(
            f"CORS Security Error: Origin must include protocol: {origin}"
        )


def _handle_cors_fallback(allowed_origins, env):
    """Handle CORS origin fallback based on environment."""
    if not allowed_origins:
        if env == "production":
            logger.error(
                "🚨 PRODUCTION CORS ERROR: CORS_ALLOWED_ORIGINS must be configured"
            )
            logger.error(
                "   Example: export CORS_ALLOWED_ORIGINS='https://your-app.com,https://your-admin.com'"
            )
            raise RuntimeError(
                "CORS Security Error: CORS_ALLOWED_ORIGINS required for production. "
                "Set specific domains, never use wildcard (*) in production."
            )
        elif env in ("staging", "test"):
            logger.warning(
                f"⚠️  {env.upper()} CORS WARNING: No origins configured, API will reject browser requests"
            )
            allowed_origins = []
        else:  # development
            allowed_origins = [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://localhost:8000",
                "http://localhost:8080",
                "http://localhost:8083",
                "http://localhost:8000",
            ]
            logger.warning("🔧 DEVELOPMENT: Using default localhost CORS origins")
            logger.warning("   Set CORS_ALLOWED_ORIGINS for production deployment")

    return _build_cors_config(allowed_origins, env)


def _build_cors_config(allowed_origins, env):
    """Build CORS configuration dictionary."""
    allowed_headers = [
        "accept",
        "accept-encoding",
        "authorization",
        "content-type",
        "dnt",
        "origin",
        "user-agent",
        "x-csrftoken",
        "x-requested-with",
        "x-api-key",
        "x-request-id",
        "cache-control",
        "last-event-id",
    ]

    allowed_methods = ["GET", "POST", "OPTIONS"]

    if os.getenv("CORS_ALLOW_PUT", "false").lower() == "true":
        allowed_methods.append("PUT")
        logger.info("✅ CORS: PUT method enabled")

    if os.getenv("CORS_ALLOW_DELETE", "false").lower() == "true":
        allowed_methods.append("DELETE")
        logger.warning("⚠️  CORS: DELETE method enabled - ensure proper authorization")

    logger.info("🔒 CORS Configuration Summary:")
    logger.info(f"   Environment: {env}")
    logger.info(f"   Allowed Origins: {len(allowed_origins)} configured")
    logger.info(f"   Allowed Methods: {allowed_methods}")
    logger.info("   Credentials: True")

    return {
        "allow_origins": allowed_origins,
        "allow_credentials": True,
        "allow_methods": allowed_methods,
        "allow_headers": allowed_headers,
        "expose_headers": ["x-request-id", "x-ratelimit-remaining"],
        "max_age": 86400,  # 24 hours preflight cache
    }


# Configure CORS with security validation
cors_config = configure_cors_security()
app.add_middleware(CORSMiddleware, **cors_config)

# Check environment config for feature flags
config = get_complete_config()

# Add security and monitoring middleware (PM requirements)
if config.feature_v1_routing and PRODUCTION_HARDENING_AVAILABLE:
    # Install API key routing middleware first (PM5.txt Day 3 requirement)
    if install_api_key_routing_middleware(app):
        logger.info("🔄 API key routing middleware installed")
    
    # Install deprecation headers middleware (PM Final: RFC 8594 compliance)
    if install_deprecation_headers_middleware(app):
        logger.info("⚠️ Deprecation headers middleware installed")
    
    # Request ID middleware (correlation id)
    app.add_middleware(RequestIDMiddleware)
    logger.info("🆔 Request ID middleware installed")

    # Install idempotency middleware (PM requirement: honor Idempotency-Key)
    app.add_middleware(IdempotencyMiddleware)
    logger.info("🔄 Idempotency middleware installed")
    
    # Install usage metering (PM requirement: track all requests)
    app.add_middleware(UsageMeteringMiddleware, enable_metering=True)
    logger.info("📊 Usage metering middleware installed")
    
    # Install log redaction (PM requirement: mask tokens in all logs)
    from api.middleware.log_redaction import install_global_log_redaction
    install_global_log_redaction()
    app.add_middleware(LogRedactionMiddleware)
    logger.info("🔒 Token redaction middleware installed")
    
    # Install ephemeris headers (PM requirement: numerical reproducibility)
    app.add_middleware(EphemerisHeadersMiddleware)
    logger.info("🔢 Ephemeris headers middleware installed")
elif config.feature_v1_routing:
    logger.warning("🚨 Production hardening middleware not available - running without full security")

# Include V1 routers if feature flag is enabled and routers are available
if config.feature_v1_routing and V1_ROUTERS_AVAILABLE:
    logger.info("🚀 Mounting V1 API routes")
    app.include_router(jyotish_router, dependencies=[Depends(rest_qps_guard)])  # V1: Core Vedic calculations
    app.include_router(kp_router, dependencies=[Depends(rest_qps_guard)])  # V1: KP-specific calculations  
    app.include_router(ref_router, dependencies=[Depends(rest_qps_guard)])  # V1: Reference data
    app.include_router(atlas_v1_router, dependencies=[Depends(rest_qps_guard)])  # V1: Geographic resolution
    app.include_router(auth_router)  # V1: Authentication (streaming tokens)
    app.include_router(stream_v1_router)  # V1: Unified streaming
    app.include_router(legacy_shim_router)  # Legacy route compatibility
    logger.info("✅ V1 API routes mounted successfully")
else:
    logger.info("📡 Mounting legacy API routes")

# (removed duplicate strict rest_qps_guard; see earlier optional version)

# Include legacy routers (always available for backward compatibility)
app.include_router(health_router, prefix="/api/v1")
app.include_router(
    signals_router, prefix="/api/v1", dependencies=[Depends(rest_qps_guard)]
)
app.include_router(
    enhanced_signals_router, prefix="/api/v1", dependencies=[Depends(rest_qps_guard)]
)  # Enhanced KP timing signals
app.include_router(
    houses_router, prefix="/api/v1", dependencies=[Depends(rest_qps_guard)]
)
app.include_router(
    location_router, prefix="/api/v1/location", dependencies=[Depends(rest_qps_guard)]
)
app.include_router(dasha_router, dependencies=[Depends(rest_qps_guard)])
app.include_router(nodes_router, dependencies=[Depends(rest_qps_guard)])
app.include_router(eclipse_router, dependencies=[Depends(rest_qps_guard)])
app.include_router(moon_router, dependencies=[Depends(rest_qps_guard)])
app.include_router(micro_router, dependencies=[Depends(rest_qps_guard)])  # Phase 8: Micro-timing
app.include_router(strategy_router, dependencies=[Depends(rest_qps_guard)])  # Phase 9: Strategy
app.include_router(advisory_router, dependencies=[Depends(rest_qps_guard)])  # Phase 11: Advisory layers
app.include_router(tara_router, dependencies=[Depends(rest_qps_guard)])  # KP: Tara Bala
app.include_router(fortuna_router, dependencies=[Depends(rest_qps_guard)])  # KP: Fortuna Points
app.include_router(transit_events_router, dependencies=[Depends(rest_qps_guard)])  # Transit Event System
# Always include ATS router; endpoints gated by feature flag to return 403 when disabled
app.include_router(ats_router, dependencies=[Depends(rest_qps_guard)])  # ATS: Aspect-Transfer Scoring
app.include_router(panchanga_router, dependencies=[Depends(rest_qps_guard)])  # Panchanga: SystemAdapter registry demo
app.include_router(kp_horary_router, dependencies=[Depends(rest_qps_guard)])  # KP: Horary Numbers (1-249)
app.include_router(kp_ruling_planets_router, dependencies=[Depends(rest_qps_guard)])  # KP: Ruling Planets System
app.include_router(stream_router)  # Streaming: SSE endpoints
app.include_router(ws_router)  # Streaming: WebSocket endpoints
app.include_router(atlas_router, dependencies=[Depends(require_jwt_header_or_query)])  # Atlas: City search/resolution
app.include_router(location_stream_router)  # Location features SSE stream

# Global Locality Research - Activation API (if enabled)
if ACTIVATION_ENABLED:
    app.include_router(
        activation_router, prefix="/api/v1/location", dependencies=[Depends(rest_qps_guard)]
    )  # GLR: Activation field mapping
    logger.info("Activation router mounted at /api/v1/location/activation")


## Root endpoint moved below response model definitions


# Prometheus metrics endpoint
@app.get("/metrics", response_class=PlainTextResponse, tags=["health"])
async def metrics():
    """Prometheus metrics endpoint"""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


from pydantic import BaseModel, Field


class VersionShortResponse(BaseModel):
    build_sha: str = Field(..., description="Build commit SHA")
    symbol_policy: str = Field(..., description="Symbol policy identifier")


# Build/version endpoint for deployment verification
@app.get("/api/v1/version", response_model=VersionShortResponse, tags=["health"])
async def version() -> VersionShortResponse:
    """Expose build metadata (git SHA) and symbol policy"""
    return {
        "build_sha": os.getenv("VC_BUILD_SHA", "unknown"),
        "symbol_policy": "ats-3-letter-strict",
    }


# Schemas for typed root + systems responses
class StreamingInfo(BaseModel):
    sse: str = Field(..., description="SSE endpoint template")
    websocket: str = Field(..., description="WebSocket endpoint path")
    authentication: str = Field(..., description="Authentication method for streams")


class ActivationInfo(BaseModel):
    endpoint: str
    stream: str
    model_version: str
    profiles: list[str]
    description: str


class RootInfoResponse(BaseModel):
    name: str
    version: str
    status: str
    docs: str
    streaming: StreamingInfo
    activation: ActivationInfo | None = Field(default=None, description="Activation API info if enabled")


class SystemsResponse(BaseModel):
    systems: list[str]
    default: str
    capabilities: dict[str, list[str]]
    health: dict[str, object]
    metadata: dict[str, object]


# System status endpoint
@app.get("/api/v1/systems", response_model=SystemsResponse, tags=["reference"])
async def get_systems() -> dict[str, object]:
    """Get registered calculation systems with capabilities"""
    from interfaces.initialize import get_system_status, validate_system_health

    status = get_system_status()
    health = validate_system_health()

    # Define capabilities for each system
    capabilities = {
        "KP": ["SIGNALS", "LORD_CHANGES", "POSITIONS"],
        "KP_HOUSES": ["HOUSES", "PLACIDUS", "BHAVA"],
        "KP_MICRO": ["VOLATILITY_WINDOWS", "MICRO_TIMING", "INSTANT_SCORE"],
        "KP_STRATEGY": ["CONFIDENCE_TIMELINE", "RULE_COMBINATORS", "FEATURE_LOGGING"],
    }

    return {
        "systems": status["registered_systems"],
        "default": status["default_system"],
        "capabilities": capabilities,
        "health": health,
        "metadata": status["metadata"],
    }

# Root endpoint (after models are defined)
@app.get("/", response_model=RootInfoResponse, tags=["health"])
async def root() -> dict[str, object]:
    base_response = {
        "name": "VedaCore Signals API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/api/docs",
        "streaming": {
            "sse": "/stream/{topic}?token=jwt_token",
            "websocket": "/ws?token=jwt_token",
            "authentication": "jwt_query_parameter",
        },
    }

    if ACTIVATION_ENABLED:
        base_response["activation"] = {
            "endpoint": "/api/v1/location/activation",
            "stream": "/api/v1/location/activation/stream",
            "model_version": "GLA-1.0.0",
            "profiles": ["default", "research-1"],
            "description": "Global Locality Research - Planetary activation field mapping",
        }

    return base_response
# Global HTTPException handler emitting RFC7807 Problem Details
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Correlate with request id and trace id
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    trace_id = None
    try:
        from opentelemetry import trace  # type: ignore
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        if ctx and getattr(ctx, "trace_id", 0):
            trace_id = f"{ctx.trace_id:032x}"
    except Exception:
        pass
    # Reasonable defaults for title/detail
    detail = None
    title = "HTTP error"
    if isinstance(exc.detail, dict):
        title = exc.detail.get("title") or title
        detail = exc.detail.get("detail") or detail
    elif isinstance(exc.detail, str):
        title = exc.detail
    # Enrich problem with retry_after_seconds if available
    retry_after_seconds = None
    try:
        ra = None
        if exc.headers and isinstance(exc.headers, dict):
            ra = exc.headers.get("Retry-After")
        if ra is not None:
            retry_after_seconds = int(str(ra))
    except Exception:
        retry_after_seconds = None

    problem = Problem(
        title=title,
        status=exc.status_code,
        detail=detail,
        instance=str(request.url),
        trace_id=trace_id,
        # Include retry hint when present
        **({"retry_after_seconds": retry_after_seconds} if retry_after_seconds is not None else {}),
    )
    return JSONResponse(status_code=exc.status_code, content=problem.model_dump(), headers={"X-Request-ID": req_id})

# Fallback handler for uncaught exceptions
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    trace_id = None
    try:
        from opentelemetry import trace  # type: ignore
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        if ctx and getattr(ctx, "trace_id", 0):
            trace_id = f"{ctx.trace_id:032x}"
    except Exception:
        pass
    problem = Problem(title="Internal Server Error", status=500, detail=str(exc)[:200], instance=str(request.url), code="INTERNAL_ERROR", trace_id=trace_id)
    return JSONResponse(status_code=500, content=problem.model_dump(), headers={"X-Request-ID": req_id})
# Custom OpenAPI schema with metadata (servers/contact/license)
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=os.getenv("OPENAPI_VERSION", "1.0.0"),
        description=app.description,
        routes=app.routes,
    )
    # Servers: prefer explicit override; else fallback by environment
    env = os.getenv("ENVIRONMENT", "development").lower()
    public_url_env = os.getenv("OPENAPI_PUBLIC_URL") or os.getenv("VEDACORE_URL")
    if not public_url_env:
        public_url_fallback = "https://api.vedacore.io" if env == "production" else "/"
    else:
        public_url_fallback = public_url_env
    schema["servers"] = [{"url": public_url_fallback}]
    # Contact and license
    schema.setdefault("info", {}).setdefault("contact", {})
    schema["info"]["contact"].update(
        {"name": "VedaCore Support", "email": os.getenv("SUPPORT_EMAIL", "support@vedacore.io")}
    )
    schema["info"]["license"] = {"name": "Proprietary", "url": os.getenv("LICENSE_URL", "https://vedacore.io/license")}
    # Surface build SHA
    schema["info"].setdefault("x-build", {})
    schema["info"]["x-build"]["sha"] = os.getenv("VC_BUILD_SHA", "unknown")
    # Security schemes: add both HTTPBearer (canonical) and bearerAuth (legacy), plus queryApiKey for SSE
    components = schema.setdefault("components", {})
    sec = components.setdefault("securitySchemes", {})
    sec["HTTPBearer"] = {"type": "http", "scheme": "bearer"}
    sec.setdefault("bearerAuth", {"type": "http", "scheme": "bearer"})
    sec.setdefault("queryApiKey", {"type": "apiKey", "in": "query", "name": "token"})
    schema["security"] = [{"HTTPBearer": []}]
    # Security & permissions notes for admin/scope-gated endpoints
    notes = {
        "adminEndpoints": ["/stream/_resume", "/stream/_topics"],
        "requirements": "role=admin|owner OR scope includes 'stream:debug'",
        "problem": {"status": 403, "code": "FORBIDDEN_DEBUG", "title": "Forbidden"},
    }
    schema.setdefault("info", {}).setdefault("x-security", notes)
    try:
        desc = schema["info"].get("description") or ""
        extra = "\n\nSecurity: Admin/Debug endpoints require role admin|owner or scope 'stream:debug'."
        if extra not in desc:
            schema["info"]["description"] = (desc + extra).strip()
    except Exception:
        pass

    # Sanitize SSE responses: remove stray application/json alongside text/event-stream
    paths = schema.get("paths", {})
    for p, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for m, op in methods.items():
            if not isinstance(op, dict):
                continue
            responses = op.get("responses", {})
            r200 = responses.get("200") or responses.get(200)
            if not isinstance(r200, dict):
                continue
            content = r200.get("content", {})
            if "text/event-stream" in content:
                # ensure schema for event-stream
                ces = content["text/event-stream"]
                if isinstance(ces, dict):
                    ces.setdefault("schema", {"type": "string"})
                # drop empty JSON content entry
                if "application/json" in content:
                    content.pop("application/json", None)
            # For SSE op, ensure op-level OR security for header OR query token
            if p == "/api/v1/stream" and m == "get":
                try:
                    op.setdefault("security", [{"HTTPBearer": []}, {"queryApiKey": []}])
                    # Optional: document key response headers for SSE 200 responses
                    # to improve parity with 3.1 authoring docs and make SDKs aware.
                    r200_headers = r200.setdefault("headers", {})
                    r200_headers.setdefault(
                        "Cache-Control",
                        {"schema": {"type": "string"}, "description": "no-store"},
                    )
                    r200_headers.setdefault(
                        "Referrer-Policy",
                        {"schema": {"type": "string"}, "description": "no-referrer"},
                    )
                    r200_headers.setdefault(
                        "Vary",
                        {
                            "schema": {"type": "string"},
                            "description": "Authorization, Accept",
                        },
                    )
                except Exception:
                    pass
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi
