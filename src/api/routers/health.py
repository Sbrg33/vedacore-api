#!/usr/bin/env python3
"""
Health check endpoints for monitoring and readiness
"""

import os
import sys

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from refactor.monitoring import get_metrics

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """
    Kubernetes liveness probe endpoint.

    Returns 200 OK if the application process is alive and responsive.
    This should only fail if the process is completely dead.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "process_id": os.getpid(),
    }


async def _check_core_dependencies() -> dict[str, Any]:
    """Check core system dependencies for readiness."""
    checks = {}

    # 1. Test KP facade calculation
    try:
        from refactor import facade

        now = datetime.now(UTC)
        pos = facade.get_positions(now)
        checks["kp_facade"] = {
            "status": "ok",
            "moon_position": round(pos.position, 2) if pos else None,
        }
    except Exception as e:
        checks["kp_facade"] = {"status": "error", "error": str(e)}

    # 2. Check cache directory access
    cache_dir = "data/cache/KP"
    try:
        cache_writable = (
            os.access(cache_dir, os.W_OK) if os.path.exists(cache_dir) else False
        )
        cache_readable = (
            os.access(cache_dir, os.R_OK) if os.path.exists(cache_dir) else False
        )
        checks["cache_storage"] = {
            "status": "ok" if (cache_writable and cache_readable) else "warning",
            "directory": cache_dir,
            "writable": cache_writable,
            "readable": cache_readable,
            "exists": os.path.exists(cache_dir),
        }
    except Exception as e:
        checks["cache_storage"] = {"status": "error", "error": str(e)}

    # 3. Check authentication system
    try:
        from api.services.auth import _from_env

        verifier = _from_env()
        auth_mode = "jwks" if verifier.jwks_url else "hs256"
        checks["authentication"] = {
            "status": "ok",
            "mode": auth_mode,
            "configured": True,
        }
    except Exception as e:
        checks["authentication"] = {"status": "error", "error": str(e)}

    # 4. Check system adapters
    try:
        # Import from interfaces package where registry is exposed
        from interfaces.registry import get_registry

        registered_systems = get_registry().list_systems()
        checks["system_adapters"] = {
            "status": "ok" if registered_systems else "warning",
            "registered_count": len(registered_systems),
            "systems": registered_systems,
        }
    except Exception as e:
        checks["system_adapters"] = {"status": "error", "error": str(e)}

    return checks


@router.get(
    "/health/ready",
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"},
    },
)
async def readiness_check():
    """
    Kubernetes readiness probe endpoint.

    Returns 200 OK if all critical dependencies are functional.
    Returns 503 Service Unavailable if any critical systems are failing.

    This endpoint validates:
    - KP calculation engine functionality
    - Cache storage accessibility
    - Authentication system configuration
    - System adapter registry
    """
    timestamp = datetime.now(UTC).isoformat()

    # Run all dependency checks
    dependency_checks = await _check_core_dependencies()

    # Determine overall readiness
    critical_failures = []
    warnings = []

    for check_name, check_result in dependency_checks.items():
        if check_result.get("status") == "error":
            critical_failures.append(
                f"{check_name}: {check_result.get('error', 'unknown error')}"
            )
        elif check_result.get("status") == "warning":
            warnings.append(f"{check_name}: degraded functionality")

    # Build response
    response_data = {
        "status": "ready" if not critical_failures else "not_ready",
        "timestamp": timestamp,
        "checks": dependency_checks,
        "summary": {
            "total_checks": len(dependency_checks),
            "passing": len(
                [c for c in dependency_checks.values() if c.get("status") == "ok"]
            ),
            "warnings": len(
                [c for c in dependency_checks.values() if c.get("status") == "warning"]
            ),
            "failures": len(critical_failures),
        },
    }

    # Add failure details if any
    if critical_failures:
        response_data["errors"] = critical_failures
    if warnings:
        response_data["warnings"] = warnings

    # Return appropriate status code
    if critical_failures:
        return JSONResponse(
            content=response_data, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    else:
        return JSONResponse(content=response_data, status_code=status.HTTP_200_OK)


@router.get("/health/metrics")
async def metrics_endpoint() -> dict[str, Any]:
    """
    Get current metrics snapshot for monitoring.

    Returns internal metrics and performance indicators.
    """
    try:
        metrics = get_metrics()
        return {
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
            "metrics": metrics,
        }
    except Exception as e:
        # Don't fail the endpoint - return what we can
        return {
            "status": "partial",
            "timestamp": datetime.now(UTC).isoformat(),
            "error": f"Metrics collection failed: {e!s}",
            "metrics": {},
        }


@router.get("/health/version")
async def version_info() -> dict[str, Any]:
    """
    Get version and environment information.

    Useful for deployment verification and debugging.
    """
    try:
        from refactor.facade import get_version_info

        facade_version = get_version_info()
    except Exception:
        facade_version = "unavailable"

    return {
        "api_version": "1.0.0",
        "facade_version": facade_version,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "platform": {
            "system": os.uname().sysname if hasattr(os, "uname") else "unknown",
            "machine": os.uname().machine if hasattr(os, "uname") else "unknown",
        },
        "process": {
            "pid": os.getpid(),
            "working_directory": os.getcwd(),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get(
    "/health/startup",
    responses={
        200: {"description": "Startup checks passed"},
        503: {"description": "Startup checks failed"},
    },
)
async def startup_check():
    """
    Comprehensive startup health check.

    This endpoint runs detailed validation of all system components
    and should be called after deployment to verify everything is working.
    More comprehensive than /ready endpoint.
    """
    timestamp = datetime.now(UTC).isoformat()

    # Get basic dependency checks
    basic_checks = await _check_core_dependencies()

    # Additional startup-specific checks
    startup_checks = {}

    # 5. Check streaming services
    try:
        from api.services.stream_manager import stream_manager

        stream_stats = stream_manager.stats()
        startup_checks["streaming"] = {
            "status": "ok",
            "active_streams": stream_stats.get("active_streams", 0),
            "total_messages": stream_stats.get("total_messages", 0),
        }
    except Exception as e:
        startup_checks["streaming"] = {"status": "error", "error": str(e)}

    # 6. Check WebSocket manager
    try:
        from api.services.ws_manager import ws_manager

        ws_stats = ws_manager.get_stats()
        startup_checks["websockets"] = {
            "status": "ok",
            "active_connections": ws_stats.get("active_connections", 0),
            "total_connections": ws_stats.get("total_connections", 0),
        }
    except Exception as e:
        startup_checks["websockets"] = {"status": "error", "error": str(e)}

    # 7. Test actual KP calculation with timing
    try:
        import time

        from refactor import facade

        start_time = time.time()
        now = datetime.now(UTC)

        # Test multiple calculations
        positions = facade.get_positions(now)
        houses = facade.get_houses_from_positions(
            positions, (13.0878, 80.2785)
        )  # Chennai

        calc_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        startup_checks["kp_performance"] = {
            "status": "ok" if calc_time < 100 else "warning",  # Warn if > 100ms
            "calculation_time_ms": round(calc_time, 2),
            "moon_position": round(positions.position, 2) if positions else None,
            "houses_calculated": len(houses.as_dict()) if houses else 0,
        }
    except Exception as e:
        startup_checks["kp_performance"] = {"status": "error", "error": str(e)}

    # 8. Check environment configuration
    try:
        env = os.getenv("ENVIRONMENT", "development")
        auth_configured = bool(
            os.getenv("AUTH_JWT_SECRET") or os.getenv("AUTH_JWKS_URL")
        )
        cors_configured = bool(os.getenv("CORS_ALLOWED_ORIGINS"))

        config_status = "ok"
        if env == "production" and (not auth_configured or not cors_configured):
            config_status = "error"
        elif env in ("staging", "test") and not auth_configured:
            config_status = "warning"

        startup_checks["configuration"] = {
            "status": config_status,
            "environment": env,
            "auth_configured": auth_configured,
            "cors_configured": cors_configured,
            "required_for_production": env == "production",
        }
    except Exception as e:
        startup_checks["configuration"] = {"status": "error", "error": str(e)}

    # Combine all checks
    all_checks = {**basic_checks, **startup_checks}

    # Analyze results
    total_checks = len(all_checks)
    passing = len([c for c in all_checks.values() if c.get("status") == "ok"])
    warnings = len([c for c in all_checks.values() if c.get("status") == "warning"])
    failures = len([c for c in all_checks.values() if c.get("status") == "error"])

    critical_failures = [
        f"{name}: {check.get('error', 'unknown error')}"
        for name, check in all_checks.items()
        if check.get("status") == "error"
    ]

    warning_list = [
        f"{name}: degraded functionality"
        for name, check in all_checks.items()
        if check.get("status") == "warning"
    ]

    # Build response
    response_data = {
        "status": "ready" if not critical_failures else "not_ready",
        "timestamp": timestamp,
        "startup_validation": "complete",
        "checks": all_checks,
        "summary": {
            "total_checks": total_checks,
            "passing": passing,
            "warnings": warnings,
            "failures": failures,
            "success_rate": (
                round((passing / total_checks) * 100, 1) if total_checks > 0 else 0
            ),
        },
    }

    if critical_failures:
        response_data["errors"] = critical_failures
    if warning_list:
        response_data["warnings"] = warning_list

    # Return with appropriate status
    status_code = (
        status.HTTP_200_OK
        if not critical_failures
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(content=response_data, status_code=status_code)
