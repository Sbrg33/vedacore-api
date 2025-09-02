"""
Response models for OpenAPI specification and contract stability.

PM requirement: Ensure every route declares response models for:
- SDK generation
- Contract stability  
- Type safety
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# =======================
# Health & Monitoring
# =======================

class HealthStatus(BaseModel):
    """Basic health status response."""
    status: str = Field(..., description="Health status: ok, warning, error")
    timestamp: datetime = Field(..., description="Check timestamp")
    process_id: str = Field(..., description="Process ID as string")


class DependencyCheck(BaseModel):
    """Individual dependency check result."""
    status: str = Field(..., description="Check status: ok, warning, error") 
    error: Optional[str] = Field(None, description="Error message if failed")


class KPFacadeCheck(DependencyCheck):
    """KP facade calculation check."""
    moon_position: Optional[float] = Field(None, description="Moon position if successful")


class CacheStorageCheck(DependencyCheck):
    """Cache storage accessibility check."""
    directory: str = Field(..., description="Cache directory path")
    writable: bool = Field(..., description="Directory is writable")
    readable: bool = Field(..., description="Directory is readable")
    exists: bool = Field(..., description="Directory exists")


class AuthenticationCheck(DependencyCheck):
    """Authentication system check."""
    mode: str = Field(..., description="Auth mode: jwks or hs256")
    configured: bool = Field(..., description="Authentication is configured")


class SystemAdaptersCheck(DependencyCheck):
    """System adapters registry check."""
    registered_count: int = Field(..., description="Number of registered systems")
    systems: List[str] = Field(..., description="List of registered system names")


class StreamingCheck(DependencyCheck):
    """Streaming service check."""
    active_streams: int = Field(..., description="Number of active streams")
    total_messages: int = Field(..., description="Total messages sent")


class WebSocketCheck(DependencyCheck):
    """WebSocket manager check."""
    active_connections: int = Field(..., description="Active WebSocket connections")
    total_connections: int = Field(..., description="Total WebSocket connections")


class KPPerformanceCheck(DependencyCheck):
    """KP calculation performance check."""
    calculation_time_ms: float = Field(..., description="Calculation time in milliseconds")
    moon_position: Optional[float] = Field(None, description="Moon position calculated")
    houses_calculated: int = Field(..., description="Number of houses calculated")


class ConfigurationCheck(DependencyCheck):
    """Environment configuration check."""
    environment: str = Field(..., description="Current environment")
    auth_configured: bool = Field(..., description="Authentication configured")
    cors_configured: bool = Field(..., description="CORS configured")
    required_for_production: bool = Field(..., description="Running in production mode")


class HealthSummary(BaseModel):
    """Health check summary statistics."""
    total_checks: int = Field(..., description="Total number of checks")
    passing: int = Field(..., description="Number of passing checks")
    warnings: int = Field(..., description="Number of warnings")
    failures: int = Field(..., description="Number of failures")
    success_rate: Optional[float] = Field(None, description="Success rate percentage")


class ReadinessResponse(BaseModel):
    """Readiness probe response."""
    status: str = Field(..., description="Overall status: ready or not_ready")
    timestamp: datetime = Field(..., description="Check timestamp")
    checks: Dict[str, DependencyCheck] = Field(..., description="Individual dependency checks")
    summary: HealthSummary = Field(..., description="Check summary")
    errors: Optional[List[str]] = Field(None, description="Critical error messages")
    warnings: Optional[List[str]] = Field(None, description="Warning messages")


class StartupResponse(ReadinessResponse):
    """Startup validation response (extends readiness)."""
    startup_validation: str = Field(..., description="Validation completion status")


class MetricsResponse(BaseModel):
    """Metrics endpoint response."""
    status: str = Field(..., description="Metrics collection status")
    timestamp: datetime = Field(..., description="Metrics timestamp")
    metrics: Dict[str, Any] = Field(..., description="Current metrics data")
    error: Optional[str] = Field(None, description="Error if metrics collection failed")


class PlatformInfo(BaseModel):
    """Platform information."""
    system: str = Field(..., description="Operating system")
    machine: str = Field(..., description="Machine architecture")


class ProcessInfo(BaseModel):
    """Process information."""
    pid: int = Field(..., description="Process ID")
    working_directory: str = Field(..., description="Current working directory")


class VersionResponse(BaseModel):
    """Version and environment information."""
    api_version: str = Field(..., description="API version")
    facade_version: str = Field(..., description="KP facade version")
    python_version: str = Field(..., description="Python version")
    environment: str = Field(..., description="Runtime environment")
    build_sha: str = Field(..., description="Git build SHA")
    platform: PlatformInfo = Field(..., description="Platform information")
    process: ProcessInfo = Field(..., description="Process information")
    timestamp: datetime = Field(..., description="Response timestamp")


# =======================
# Streaming & WebSocket  
# =======================

class StreamStatsResponse(BaseModel):
    """Stream statistics response."""
    stream_manager: Dict[str, Any] = Field(..., description="Stream manager statistics")
    rate_limiter: Dict[str, Any] = Field(..., description="Rate limiter metrics")
    tenant_status: Dict[str, Any] = Field(..., description="Tenant-specific status")
    moon_publisher: Dict[str, Any] = Field(..., description="Moon publisher statistics")
    timestamp: float = Field(..., description="Statistics timestamp")
    request_id: str = Field(..., description="Request correlation ID")


class StreamHealthResponse(BaseModel):
    """Streaming service health check."""
    status: str = Field(..., description="Health status: healthy or unhealthy")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    stats: Dict[str, int] = Field(..., description="Health statistics")
    timestamp: float = Field(..., description="Health check timestamp")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


class PublishResponse(BaseModel):
    """Message publish response."""
    ok: bool = Field(..., description="Publish success status")
    topic: str = Field(..., description="Topic published to")
    payload_size: int = Field(..., description="Payload size in bytes")
    subscribers: int = Field(..., description="Number of current subscribers")
    publisher: str = Field(..., description="Publisher type")
    tenant_id: Optional[str] = Field(None, description="Tenant ID for JWT publish")
    request_id: Optional[str] = Field(None, description="Request correlation ID")
    timestamp: float = Field(..., description="Publish timestamp")


class WebSocketStatsResponse(BaseModel):
    """WebSocket service statistics."""
    websocket_manager: Dict[str, Any] = Field(..., description="WebSocket manager stats")
    rate_limiter: Dict[str, Any] = Field(..., description="Rate limiter stats")
    service_info: Dict[str, str] = Field(..., description="Service information")


class WebSocketHealthResponse(BaseModel):
    """WebSocket service health check."""
    status: str = Field(..., description="Health status: healthy or unhealthy")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    stats: Dict[str, int] = Field(..., description="Health statistics")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


# =======================
# Cache & Configuration
# =======================

class CacheStatsResponse(BaseModel):
    """Cache statistics response."""
    backend_type: str = Field(..., description="Cache backend type")
    environment: str = Field(..., description="Environment mode")
    status: Optional[str] = Field(None, description="Backend status")
    note: Optional[str] = Field(None, description="Additional information")
    error: Optional[str] = Field(None, description="Error message if failed")


# =======================
# Error Responses
# =======================

class ErrorDetail(BaseModel):
    """Error detail information."""
    type: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


class ErrorResponse(BaseModel):
    """Standard error response."""
    ok: bool = Field(False, description="Success status")
    error: str = Field(..., description="Error type identifier")
    detail: str = Field(..., description="Human readable error message")
    timestamp: Optional[datetime] = Field(None, description="Error timestamp")


class ValidationErrorResponse(ErrorResponse):
    """Validation error response."""
    errors: List[ErrorDetail] = Field(..., description="Validation error details")


class RateLimitErrorResponse(ErrorResponse):
    """Rate limit error response."""
    retry_after: int = Field(..., description="Retry after seconds")
    limit_type: str = Field(..., description="Type of limit exceeded")


# =======================
# Advisory Responses
# =======================

class AdvisorySnapshotResponse(BaseModel):
    """Advisory snapshot response."""
    timestamp: datetime = Field(..., description="Calculation timestamp")
    latitude: float = Field(..., description="Location latitude")
    longitude: float = Field(..., description="Location longitude")
    advisory_layers: Dict[str, Any] = Field(..., description="Enabled advisory calculations")
    timing: Optional[Dict[str, Any]] = Field(None, description="Timing metrics if requested")


class AdvisoryRangeResponse(BaseModel):
    """Advisory range response."""
    start: str = Field(..., description="Start time ISO format")
    end: str = Field(..., description="End time ISO format")
    interval_minutes: int = Field(..., description="Sampling interval")
    count: int = Field(..., description="Number of snapshots")
    snapshots: List[Dict[str, Any]] = Field(..., description="Advisory snapshots")


class FeatureStatusResponse(BaseModel):
    """Feature flag status response."""
    enabled: List[str] = Field(..., description="Enabled feature modules")
    available: List[str] = Field(..., description="Available feature modules")
    configuration: Dict[str, Any] = Field(..., description="Feature configuration")


class RulingPlanetsResponse(BaseModel):
    """KP Ruling Planets calculation response."""
    ascendant_lords: Dict[str, str] = Field(..., description="Ascendant sign, star, and sub lords")
    moon_lords: Dict[str, str] = Field(..., description="Moon sign, star, and sub lords")
    day_lord: str = Field(..., description="Day lord (Vara)")
    hora_lord: Optional[str] = Field(None, description="Hora lord (planetary hour)")
    calculation_time: datetime = Field(..., description="Calculation timestamp")


class ShadbalaResponse(BaseModel):
    """Shadbala strength calculation response."""
    planets: Dict[str, Dict[str, float]] = Field(..., description="Planetary strength components")
    total_strength: Dict[str, float] = Field(..., description="Total strength by planet")
    strongest_planet: str = Field(..., description="Strongest planet")
    calculation_details: Dict[str, Any] = Field(..., description="Calculation breakdown")


class AdvisoryHealthResponse(BaseModel):
    """Advisory service health response."""
    status: str = Field(..., description="Health status")
    enabled_count: int = Field(..., description="Number of enabled features")
    available_count: int = Field(..., description="Number of available features")
    features: List[str] = Field(..., description="Enabled feature list")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


# =======================
# ATS Responses
# =======================

class ATSBatchResponse(BaseModel):
    """ATS batch calculation response."""
    results: List[Dict[str, Any]] = Field(..., description="ATS calculation results")
    count: int = Field(..., description="Number of results")


class ATSConfigResponse(BaseModel):
    """ATS configuration response."""
    context: Dict[str, Any] = Field(..., description="ATS context configuration")


class ATSValidationResponse(BaseModel):
    """ATS validation response."""
    valid: bool = Field(..., description="Validation result")
    scores: Dict[str, float] = Field(..., description="Validated scores")
    computation_time_ms: float = Field(..., description="Computation time in milliseconds")
    timestamp: datetime = Field(..., description="Validation timestamp")


class ATSStatusResponse(BaseModel):
    """ATS system status response."""
    status: str = Field(..., description="System status: healthy or unhealthy")
    adapter_version: str = Field(..., description="Adapter version")
    context_file: str = Field(..., description="Context configuration file")
    cache_ttl: int = Field(..., description="Cache TTL in seconds")
    test_calculation: Dict[str, Any] = Field(..., description="Test calculation result")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


class ATSContextsResponse(BaseModel):
    """ATS contexts list response."""
    contexts: List[Dict[str, str]] = Field(..., description="Available ATS contexts")
    current: str = Field(..., description="Current context file")


# =======================
# Micro-timing Responses
# =======================

class MicroVolatilityWindow(BaseModel):
    """Individual volatility window."""
    start_time: datetime = Field(..., description="Window start time")
    end_time: datetime = Field(..., description="Window end time")
    strength: str = Field(..., description="Window strength: high, medium, low")
    score: float = Field(..., description="Volatility score")
    factors: Dict[str, Any] = Field(..., description="Contributing factors")


class MicroDayResponse(BaseModel):
    """Micro-timing day response."""
    date: str = Field(..., description="Date in ISO format")
    system: str = Field(..., description="System used for calculation")
    windows: List[MicroVolatilityWindow] = Field(..., description="Volatility windows")
    summary: Dict[str, Any] = Field(..., description="Daily summary statistics")
    computation_time_ms: float = Field(..., description="Computation time in milliseconds")


class MicroRangeResponse(BaseModel):
    """Micro-timing range response."""
    start_date: str = Field(..., description="Start date in ISO format")
    end_date: str = Field(..., description="End date in ISO format")
    system: str = Field(..., description="System used for calculation")
    daily_windows: List[Dict[str, Any]] = Field(..., description="Daily windows by date")
    total_windows: int = Field(..., description="Total number of windows")
    summary: Dict[str, Any] = Field(..., description="Range summary statistics")


class MicroNextResponse(BaseModel):
    """Next volatility window response."""
    next_window: Optional[MicroVolatilityWindow] = Field(None, description="Next volatility window")
    time_until_minutes: Optional[float] = Field(None, description="Minutes until next window")
    current_status: str = Field(..., description="Current volatility status")
    system: str = Field(..., description="System used for calculation")


class MicroInstantResponse(BaseModel):
    """Instantaneous volatility response."""
    timestamp: datetime = Field(..., description="Query timestamp")
    volatility_score: float = Field(..., description="Current volatility score")
    strength: str = Field(..., description="Current strength level")
    factors: Dict[str, Any] = Field(..., description="Contributing factors")
    system: str = Field(..., description="System used for calculation")


class MicroConfigResponse(BaseModel):
    """Micro-timing configuration response."""
    system: str = Field(..., description="System name")
    weights: Optional[Dict[str, float]] = Field(None, description="System weights")
    thresholds: Optional[Dict[str, float]] = Field(None, description="Volatility thresholds")
    window_sizes: Optional[Dict[str, int]] = Field(None, description="Window size configuration")
    feature_flags: Optional[Dict[str, bool]] = Field(None, description="Feature flags")
    metadata: Dict[str, Any] = Field(..., description="Additional configuration metadata")


# =======================
# Panchanga Responses
# =======================

class PanchangaHealthResponse(BaseModel):
    """Panchanga adapter health response."""
    adapter_id: str = Field(..., description="Adapter ID")
    version: str = Field(..., description="Adapter version")
    health: Dict[str, Any] = Field(..., description="Health check result")
    registry_status: str = Field(..., description="Registry status")


class PanchangaSchemaResponse(BaseModel):
    """Panchanga adapter schema response."""
    adapter_id: str = Field(..., description="Adapter ID")
    version: str = Field(..., description="Adapter version")
    schema: Dict[str, Any] = Field(..., description="Input/output schema")


class PanchangaExplanationResponse(BaseModel):
    """Panchanga explanation response."""
    status: str = Field(..., description="Request status")
    result: Dict[str, Any] = Field(..., description="Panchanga calculation result")
    explanation: Dict[str, Any] = Field(..., description="Result explanation")
    adapter_info: Dict[str, str] = Field(..., description="Adapter information")


# =======================
# Signals Responses
# =======================

class SignalsHealthResponse(BaseModel):
    """Signals service health response."""
    status: str = Field(..., description="Service health status")
    service: str = Field(..., description="Service name")


# =======================
# Strategy Responses
# =======================

class StrategyDayResponse(BaseModel):
    """Daily confidence timeline response."""
    date: str = Field(..., description="Date in ISO format")
    ticker: str = Field(..., description="Ticker symbol")
    timeline: List[Dict[str, Any]] = Field(..., description="Confidence timeline")
    summary: Dict[str, Any] = Field(..., description="Daily summary statistics")
    computation_time_ms: float = Field(..., description="Computation time in milliseconds")


class StrategyWindowResponse(BaseModel):
    """Window confidence aggregation response."""
    ticker: str = Field(..., description="Ticker symbol")
    window_start: datetime = Field(..., description="Window start time")
    window_end: datetime = Field(..., description="Window end time")
    confidence_aggregate: Dict[str, Any] = Field(..., description="Aggregated confidence metrics")
    rules_applied: List[str] = Field(..., description="Applied confidence rules")


class StrategyConfigResponse(BaseModel):
    """Strategy configuration response."""
    ticker: str = Field(..., description="Ticker symbol")
    config: Dict[str, Any] = Field(..., description="Strategy configuration")
    metadata: Dict[str, Any] = Field(..., description="Configuration metadata")


class StrategyDryRunResponse(BaseModel):
    """Configuration dry run response."""
    valid: bool = Field(..., description="Configuration validity")
    test_results: Dict[str, Any] = Field(..., description="Test results")
    errors: Optional[List[str]] = Field(None, description="Validation errors")
    warnings: Optional[List[str]] = Field(None, description="Validation warnings")


class StrategyHealthResponse(BaseModel):
    """Strategy system health response."""
    status: str = Field(..., description="System health status")
    active_systems: List[str] = Field(..., description="Active strategy systems")
    performance_metrics: Dict[str, Any] = Field(..., description="Performance metrics")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


# =======================
# Transit Events Responses
# =======================

class TransitGatesResponse(BaseModel):
    """Transit gates calculation response."""
    timestamp: str = Field(..., description="ISO timestamp of calculation")
    moon_chain: Dict[str, Any] = Field(..., description="Current Moon KP chain")
    gates: List[Dict[str, Any]] = Field(..., description="Gate calculations")
    strongest: Optional[Dict[str, Any]] = Field(
        None, description="Strongest gate if any"
    )


class TransitPromiseCheckResponse(BaseModel):
    """Transit promise checking response."""
    promise_results: List[Dict[str, Any]] = Field(
        ..., description="Promise check results for themes"
    )
    planet_themes: Optional[List[str]] = Field(
        None, description="All themes for specific planet"
    )


class TransitConfigResponse(BaseModel):
    """Transit event configuration response."""
    features: Dict[str, bool] = Field(..., description="Feature flag status")
    thresholds: Dict[str, int] = Field(..., description="Scoring thresholds")
    weights: Dict[str, float] = Field(..., description="Component weights")


class TransitHealthResponse(BaseModel):
    """Transit event system health response."""
    status: str = Field(..., description="System health status")
    moon_chain: Optional[str] = Field(None, description="Current Moon chain signature")
    cache_stats: Optional[Dict[str, Any]] = Field(
        None, description="Cache statistics"
    )
    error: Optional[str] = Field(None, description="Error message if unhealthy")


# =======================
# WebSocket Responses
# =======================

class WebSocketHealthResponse(BaseModel):
    """WebSocket service health response."""
    status: str = Field(..., description="Service health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    stats: Dict[str, int] = Field(..., description="Connection and message statistics")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


class WebSocketStatsResponse(BaseModel):
    """WebSocket detailed statistics response."""
    websocket_manager: Dict[str, Any] = Field(..., description="WebSocket manager statistics")
    rate_limiter: Dict[str, Any] = Field(..., description="Rate limiter metrics")
    service_info: Dict[str, str] = Field(..., description="Service information")


# =======================
# Generic Responses
# =======================

class SuccessResponse(BaseModel):
    """Generic success response."""
    ok: bool = Field(True, description="Success status")
    message: str = Field(..., description="Success message")
    timestamp: Optional[datetime] = Field(None, description="Response timestamp")


class StatusResponse(BaseModel):
    """Generic status response."""
    status: str = Field(..., description="Operation status")
    message: Optional[str] = Field(None, description="Status message")
    timestamp: datetime = Field(..., description="Status timestamp")