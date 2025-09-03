"""
Response models for OpenAPI specification and contract stability.

PM requirement: Ensure every route declares response models for:
- SDK generation
- Contract stability  
- Type safety
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


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
# Location Features Responses
# =======================

class Coordinates(BaseModel):
    """Geographic coordinates for a location."""
    lat: float = Field(..., description="Latitude in degrees")
    lon: float = Field(..., description="Longitude in degrees")
    elevation: float | None = Field(None, description="Elevation in meters if available")


class Angles(BaseModel):
    """Primary angles for a location."""
    asc: float = Field(..., description="Ascendant ecliptic longitude")
    mc: float = Field(..., description="Midheaven ecliptic longitude")
    desc: float = Field(..., description="Descendant ecliptic longitude")
    ic: float = Field(..., description="Imum Coeli ecliptic longitude")


class LSTSegment(BaseModel):
    """Local Sidereal Time segment descriptor."""
    num: int = Field(..., description="Segment index 0-7")
    label: str = Field(..., description="Human-friendly label for the segment")


class DistToAngles(BaseModel):
    """Great-circle distances to angles (degrees)."""
    asc: float
    mc: float
    desc: float
    ic: float


class AspectToAngle(BaseModel):
    """Aspect between planet and an angle (ASC/MC)."""
    angle: str = Field(..., description="Target angle: asc|mc")
    type: str = Field(..., description="Aspect type e.g. conj, opp, tri, sqr, sex")
    orb: float = Field(..., description="Orb distance in degrees")
    applying: bool = Field(..., description="Whether aspect is applying")


class DeclinationInfo(BaseModel):
    """Declination analysis information."""
    mode: str = Field(..., description="Calculation mode: topo|geo")
    dec_strength: float = Field(..., description="Declination strength [0,1]")
    circumpolar: bool = Field(..., description="Circumpolar visibility flag")


class TopoAltAz(BaseModel):
    """Topocentric altitude/azimuth if computed."""
    alt: float
    az: float


class PlanetFeature(BaseModel):
    """Per-planet features at a location."""
    model_config = ConfigDict(extra="allow")
    house: int = Field(..., ge=1, le=12)
    ecl_lon: float
    ra: float
    dec: float
    dist_to_angles: DistToAngles
    cusp_dist_deg: float
    topo: TopoAltAz | None = None
    above_horizon: bool | None = None
    aspect_to_angles: list[AspectToAngle] = Field(default_factory=list)
    declination: DeclinationInfo


class DerivedIndices(BaseModel):
    """Bounded indices summarizing local emphasis."""
    angular_load: float
    house_emphasis: dict[str, float]
    aspect_to_angle_load: float
    declinational_emphasis: float


class LocationDerived(BaseModel):
    aspect_to_angles: list[AspectToAngle] = Field(default_factory=list)
    indices: DerivedIndices
    declination: DeclinationInfo


class LocationFeature(BaseModel):
    """Full feature payload for a single location."""
    model_config = ConfigDict(extra="allow")
    id: str
    name: str | None = None
    coords: Coordinates
    angles: Angles
    houses: list[float]
    lst_segment: LSTSegment
    planets: dict[str, PlanetFeature]
    derived: LocationDerived


class LocationFeaturesResponse(BaseModel):
    """Top-level container for location features computation."""
    timestamp: str
    locations: list[LocationFeature]


# =======================
# Activation Responses
# =======================

class ActivationDrivers(BaseModel):
    planet: str | None = None
    angle: str | None = None
    kind: str | None = None
    applying: bool | None = None


class ActivationConfidence(BaseModel):
    reliability_lat: float | None = None


class ActivationStrength(BaseModel):
    absolute: float
    delta: float | None = None
    exposure_weighted: float | None = None


class ActivationLocation(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str | None = None
    lat: float
    lon: float
    activation: ActivationStrength
    breakdown: Dict[str, float]
    sun_cap: float | None = None
    phase_multiplier: float | None = None
    drivers: ActivationDrivers | Dict[str, Any]
    flags: Dict[str, Any] | list[str] | None = None
    confidence: ActivationConfidence | Dict[str, Any] | None = None


class ActivationSky(BaseModel):
    model_config = ConfigDict(extra="allow")
    moon: Dict[str, Any] | None = None
    sun: Dict[str, Any] | None = None


class ActivationResponse(BaseModel):
    timestamp: str
    model_version: str
    model_profile: str
    locations: list[ActivationLocation]
    sky: ActivationSky | None = None


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


# RFC 7807 Problem Details (global error model)
class Problem(BaseModel):
    """Problem Details per RFC 7807 for error responses."""
    type: Optional[str] = Field(
        None, description="URI reference that identifies the problem type"
    )
    title: str = Field(..., description="Short, human-readable summary of the problem")
    status: int = Field(..., description="HTTP status code")
    detail: Optional[str] = Field(None, description="Human-readable explanation")
    instance: Optional[str] = Field(
        None, description="URI reference that identifies the specific occurrence"
    )
    code: Optional[str] = Field(None, description="Application-specific error code")


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


# =======================
# Varga (Divisional) Responses
# =======================

class VargaCalculateDirectResponse(BaseModel):
    """Direct varga calculation response."""
    divisor: int = Field(..., ge=2, le=300, description="Divisional chart number")
    scheme: str = Field(..., description="Calculation scheme")
    positions: Dict[int, int] = Field(
        ..., description="Planet ID to varga sign (1-12)"
    )
    note: str = Field(..., description="Human-readable clarification notes")


class VargaCalculateResponse(BaseModel):
    """Timestamp-based varga calculation response."""
    timestamp: str = Field(..., description="UTC timestamp (ISO8601)")
    divisor: int = Field(..., ge=2, le=300, description="Divisional chart number")
    scheme: str = Field(..., description="Calculation scheme")
    positions: Dict[str, int] = Field(
        ..., description="Planet ID (string) to varga sign (1-12)"
    )
    note: str = Field(..., description="Human-readable clarification notes")


class VargottamaStatusResponse(BaseModel):
    """Vargottama detection response."""
    timestamp: str = Field(..., description="UTC timestamp (ISO8601)")
    vargottama_status: Dict[str, Dict[str, bool]] = Field(
        ..., description="Planet name to {varga_name: is_vargottama}"
    )
    checked_vargas: List[int] = Field(..., description="Checked varga divisors")


class ShodasavargaResponse(BaseModel):
    """All 16 divisional charts response."""
    timestamp: str = Field(..., description="UTC timestamp (ISO8601)")
    planet_id: Optional[int] = Field(
        None, description="Specific planet ID if filtered"
    )
    shodasavarga: Dict[str, Dict[str, int]] = Field(
        ..., description="Map of Dn -> {planet_id: sign(1-12)}"
    )
    note: str = Field(..., description="Human-readable clarification notes")


class VargaStrengthResponse(BaseModel):
    """Vimshopaka Bala strength response."""
    timestamp: str = Field(..., description="UTC timestamp (ISO8601)")
    planet: str = Field(..., description="Planet name")
    varga_set: str = Field(..., description="Weight set used")
    strength: float = Field(..., ge=0, le=100, description="Strength score 0-100")
    scale: str = Field(..., description="Scale description (e.g., 0-100)")
    interpretation: str = Field(..., description="Human-readable strength band")


class CustomVargaRegisterResponse(BaseModel):
    """Custom varga scheme registration response."""
    status: str = Field(..., description="Operation status")
    name: str = Field(..., description="Registered scheme name")
    divisor: int = Field(..., ge=2, le=300, description="Scheme divisor")
    message: str = Field(..., description="Additional status message")


class VargaSchemesCategories(BaseModel):
    classical: List[str] = Field(..., description="Classical schemes")
    custom: List[str] = Field(..., description="Custom schemes")
    other: List[str] = Field(..., description="Other schemes")


class VargaSchemesResponse(BaseModel):
    """Available varga schemes response."""
    schemes: List[str] = Field(..., description="All scheme identifiers")
    count: int = Field(..., description="Total schemes")
    categories: VargaSchemesCategories = Field(..., description="Categorized lists")


class VargaConfigResponse(BaseModel):
    """Varga system configuration response."""
    features: Dict[str, Any] = Field(..., description="Feature flags and values")
    limits: Dict[str, int] = Field(..., description="System limits")
    classical_schemes: Dict[str, Any] = Field(
        ..., description="Classical scheme definitions"
    )
    vimshopaka_sets: List[str] = Field(..., description="Available weight sets")
    standard_vargas: List[int] = Field(..., description="Standard varga divisors")
    shodasavarga: List[int] = Field(..., description="Shodasavarga divisors")


# =======================
# KP Horary Responses
# =======================

class HorarySignificatorsResponse(BaseModel):
    """KP horary significators response.

    Simplified structure exposing horary mapping and interpretation fields.
    """
    horary_number: int = Field(..., ge=1, le=249, description="Horary number (1-249)")
    sign: int = Field(..., ge=1, le=12, description="Zodiac sign (1-12)")
    sign_lord: str = Field(..., description="Sign lord planet")
    star: int = Field(..., ge=1, le=9, description="Nakshatra ordinal (1-9)")
    star_lord: str = Field(..., description="Nakshatra lord")
    sub: int = Field(..., ge=1, le=3, description="Sub division (1-3)")
    interpretation: str = Field(..., description="Guidance for use in KP")


class ServiceHealthResponse(BaseModel):
    service: str
    status: str
    registry_available: bool | None = None
    timestamp: str
    adapter_registered: bool | None = None
    adapter_version: str | None = None


# =======================
# KP Analysis & Config Responses
# =======================

class KPAnalysisResponse(BaseModel):
    """Top-level KP analysis response container (allows extra keys)."""
    model_config = ConfigDict(extra="allow")
    houses: Optional[Dict[str, Any]] = Field(None, description="House analysis components")
    planets: Optional[Dict[str, Any]] = Field(None, description="Planet analysis components")
    matters: Optional[Dict[str, Any]] = Field(None, description="Life matters analysis")
    timing: Optional[Dict[str, Any]] = Field(None, description="Timing analysis (dasha/transits)")
    context: Optional[Dict[str, Any]] = Field(None, description="Calculation context")
    summary: Optional[Dict[str, Any]] = Field(None, description="Summary and highlights")


# =======================
# KP RP & Small Utilities
# =======================

class WeekdayInfoResponse(BaseModel):
    weekday_idx: int
    weekday_name: str
    day_lord: str
    day_lord_name: str


class AdapterSchemaResponse(BaseModel):
    """Arbitrary adapter schema payload (permits extra fields)."""
    model_config = ConfigDict(extra="allow")


class KPHousePromisesResponse(BaseModel):
    """House promise analysis response (allows extra keys)."""
    model_config = ConfigDict(extra="allow")
    house: Optional[int] = Field(None, description="Analyzed house number")
    promises: Optional[Dict[str, Any]] = Field(None, description="Promise breakdown and rationale")


class KPPlanetSignificationsResponse(BaseModel):
    """Planet significations response (allows extra keys)."""
    model_config = ConfigDict(extra="allow")
    planet_id: Optional[int] = Field(None, description="Planet ID")
    signifies: Optional[List[str]] = Field(None, description="Houses/significations list")


class KPCuspalSublordsResponse(BaseModel):
    """Cuspal sub-lords analysis response (allows extra keys)."""
    model_config = ConfigDict(extra="allow")
    cuspal_sublords: Optional[Dict[int, Dict[str, Any]]] = Field(
        None, description="Per-house sign/star/sub details"
    )


class KPSignificatorsResponse(BaseModel):
    """KP significator hierarchy response (allows extra keys)."""
    model_config = ConfigDict(extra="allow")
    house: Optional[int] = Field(None, description="House focused view")
    planet: Optional[int] = Field(None, description="Planet focused view")
    significators: Optional[List[Dict[str, Any]]] = Field(
        None, description="Significator hierarchy entries"
    )
    primary: Optional[List[Dict[str, Any]]] = Field(
        None, description="Primary significators (strongest)"
    )
    signifies: Optional[List[str]] = Field(
        None, description="For planet-focused: houses signified by planet"
    )


class KPConfigRetrograde(BaseModel):
    reverses_sublord: bool
    strength_factor: float
    rahu_ketu_always_retrograde: bool


class KPConfigResponse(BaseModel):
    """KP configuration response with typed top-level sections."""
    retrograde: KPConfigRetrograde
    orbs: Dict[str, Dict[str, float]]
    significators: Dict[str, Any]
    defaults: Dict[str, Any]
    performance: Dict[str, Any]


# =======================
# Fortuna (Arabic Parts) Responses
# =======================

class FortunaPointPosition(BaseModel):
    longitude: float = Field(..., description="Longitude in degrees")
    sign: int = Field(..., ge=1, le=12, description="Zodiac sign (1-12)")
    house: int = Field(..., ge=1, le=12, description="House position (1-12)")
    nakshatra: int = Field(..., ge=1, le=27, description="Nakshatra (1-27)")
    sub_lord: str = Field(..., description="KP sub-lord planet name")


class FortunaPointMovement(BaseModel):
    daily_motion: float = Field(..., description="Degrees per day")
    retrograde: bool = Field(..., description="Retrograde flag")


class FortunaPointInfo(BaseModel):
    name: str = Field(..., description="Display name")
    formula: str = Field(..., description="Formula used")
    signification: str = Field(..., description="Point signification")
    position: FortunaPointPosition
    movement: FortunaPointMovement
    strength: float = Field(..., ge=0, le=100, description="Strength score")
    afflicted: bool = Field(..., description="Affliction flag")


class FortunaAspect(BaseModel):
    planet: str
    aspect: str
    angle: float
    orb: float
    applying: bool


class FortunaTransitEvent(BaseModel):
    house: int = Field(..., ge=1, le=12)
    cusp_degree: float
    hours_until: int
    type: str


class PartOfFortuneData(BaseModel):
    longitude: float
    sign: int
    house: int
    nakshatra: int
    is_day_birth: bool
    aspects: Optional[List[FortunaAspect]] = None
    next_transits: Optional[List[FortunaTransitEvent]] = None


class FortunaCalculateResponse(BaseModel):
    timestamp: str
    location: Dict[str, float]
    fortuna_points: Dict[str, FortunaPointInfo]
    count: int


class PartOfFortuneResponse(BaseModel):
    timestamp: str
    location: Dict[str, float]
    part_of_fortune: PartOfFortuneData


class FortunaMovementStats(BaseModel):
    total_movement: float
    average_speed: float
    min_longitude: float
    max_longitude: float


class FortunaMovementResponse(BaseModel):
    date: str
    location: Dict[str, float]
    interval_hours: int
    movement: Dict[str, Any]
    statistics: Dict[str, FortunaMovementStats]


class FortunaRangeSample(BaseModel):
    timestamp: str
    longitude: float


class FortunaRangeSignChange(BaseModel):
    timestamp: str
    from_sign: int
    to_sign: int


class FortunaRangeResponse(BaseModel):
    start: str
    end: str
    point: str
    samples: List[Dict[str, Any]]
    sign_changes: List[FortunaRangeSignChange]
    total_samples: int


class FortunaAvailablePoint(BaseModel):
    name: str
    display_name: str
    formula: str
    description: str
    category: str


class FortunaHelpResponse(BaseModel):
    description: str
    key_concepts: Dict[str, str]
    primary_points: Dict[str, str]
    usage: Dict[str, str]
    timing_tips: List[str]


# =======================
# Tara Bala Responses
# =======================

class TaraPersonalResponse(BaseModel):
    timestamp: str
    birth_moon_longitude: float
    tara_analysis: Dict[str, Any]


class MuhurtaTaraResponse(BaseModel):
    event_timestamp: str
    participants: int
    muhurta_analysis: Dict[str, Any]


class TaraDaySummary(BaseModel):
    favorable_hours: int | None
    unfavorable_hours: int | None
    best_time: Dict[str, Any]
    worst_time: Dict[str, Any]


class TaraDayScanResponse(BaseModel):
    date: str
    birth_moon_longitude: float
    summary: TaraDaySummary
    hourly_data: List[Dict[str, Any]] | None
    key_points: List[Dict[str, Any]] | None


class UniversalTaraInfo(BaseModel):
    tara_number: int
    tara_name: str
    description: str
    general_quality: str


class UniversalTaraResponse(BaseModel):
    timestamp: str
    current_nakshatra: int
    reference_nakshatra: int
    universal_tara: UniversalTaraInfo


class TaraTypeInfo(BaseModel):
    number: int
    name: str
    description: str
    quality: str


class TaraHelpResponse(BaseModel):
    description: str
    usage: Dict[str, str]
    tara_cycle: List[Dict[str, Any]]
    best_taras: List[int]
    worst_taras: List[int]
    neutral_taras: List[int]


# =======================
# Dasha Responses
# =======================

class DashaPeriod(BaseModel):
    planet: str | int
    start: str
    end: str
    duration_days: float


class DashaSnapshotResponse(BaseModel):
    system: str
    timestamp: str
    birth_time: str
    moon_longitude: float
    levels: int
    mahadasha: DashaPeriod | None = None
    antardasha: DashaPeriod | None = None
    pratyantardasha: DashaPeriod | None = None
    sookshma: DashaPeriod | None = None
    prana: DashaPeriod | None = None
    meta: Dict[str, Any]


class DashaChangeEvent(BaseModel):
    level: str | int | None = None
    type: str | None = None
    planet: str | int | None = None
    timestamp: str | None = None
    meta: Dict[str, Any] | None = None
    system: str | None = None
    date: str | None = None
    chart_id: str | None = None


class DashaCycleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    system: str
    birth_time: str
    moon_longitude: float
    meta: Dict[str, Any]


class DashaBirthBalanceResponse(BaseModel):
    system: str
    birth_time: str
    moon_longitude: float
    nakshatra: int | str
    birth_lord: str
    elapsed_days: float
    remaining_days: float
    elapsed_portion: float
    remaining_portion: float
    compute_time_ms: float | None = None


class DashaSystemInfo(BaseModel):
    id: str
    name: str
    description: str
    levels: List[str]
    planets: List[str]


class DashaSystemsResponse(BaseModel):
    systems: List[Dict[str, Any]] | List[DashaSystemInfo]


# =======================
# Nodes Responses
# =======================

class NodeEvent(BaseModel):
    type: str = Field(..., description="Event type")
    timestamp: str = Field(..., description="Event timestamp (ISO)")
    speed: Optional[float] = Field(None, description="Node speed at event time")
    metadata: Dict[str, Any] | None = Field(None, description="Additional event metadata")
    meta: Dict[str, Any] | None = Field(None, description="Computation metadata")


class NodeNextEventResponse(BaseModel):
    found: bool
    event: Optional[NodeEvent] = None
    days_until: Optional[int] = None
    search_start: Optional[str] = None
    search_days: Optional[int] = None
    compute_time_ms: Optional[float] = None


class NodeSpeedStats(BaseModel):
    min: float
    max: float
    avg: float


class NodeStatisticsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    event_counts: Dict[str, int] | None = None
    speed_stats: NodeSpeedStats | None = None
    configuration: Dict[str, Any] | None = None
    compute_time_ms: Optional[float] = None


class NodeConfigResponse(BaseModel):
    system: str
    configuration: Dict[str, Any]
    features: Dict[str, Any]
    thresholds: Dict[str, Any]
    performance: Dict[str, Any]
    cache: Dict[str, Any]


class NodeSystemsEndpoint(BaseModel):
    path: str
    method: str
    description: str


class NodeSystemsResponse(BaseModel):
    systems: List[Dict[str, Any]]
    endpoints: List[NodeSystemsEndpoint]


# =======================
# Enhanced Signals Responses (additional)
# =======================

class EnhancedInvalidateResponse(BaseModel):
    status: str
    tenant_id: str
    timestamp: str
    invalidated: Optional[str] = None
    message: Optional[str] = None
    date: Optional[str] = None


class EnhancedSignalsHealthResponse(BaseModel):
    status: str
    service: str
    version: str | None = None
    redis_available: bool | None = None
    metrics: Dict[str, Any] | None = None
    error: Optional[str] = None
    timestamp: str


# =======================
# Eclipse Config Response
# =======================

class EclipseConfigMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    system: str | None = None
    version: str | None = None
    description: str | None = None
    config: Dict[str, Any] | None = None
    capabilities: Dict[str, Any] | None = None
    performance: Dict[str, Any] | None = None
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
