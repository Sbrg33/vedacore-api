"""
Base models for VedaCore API - Pydantic V2 compliant.

These base models provide standardized request/response patterns
for all API endpoints, ensuring consistency across the system.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.functional_validators import AfterValidator

# --- Validators ---


def validate_latitude(v: float) -> float:
    """Validate latitude is within valid range"""
    if not -90 <= v <= 90:
        raise ValueError(f"Latitude must be between -90 and 90, got {v}")
    return v


def validate_longitude(v: float) -> float:
    """Validate longitude is within valid range"""
    if not -180 <= v <= 180:
        raise ValueError(f"Longitude must be between -180 and 180, got {v}")
    return v


def validate_planet_id(v: int) -> int:
    """Validate planet ID is valid (1-9 for Vedic planets)"""
    if v not in range(1, 10):
        raise ValueError(f"Planet ID must be between 1-9 (Vedic planets), got {v}")
    return v


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC timezone-aware"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    elif dt.tzinfo != UTC:
        return dt.astimezone(UTC)
    return dt


# --- Type Aliases ---

Latitude = Annotated[float, AfterValidator(validate_latitude)]
Longitude = Annotated[float, AfterValidator(validate_longitude)]
PlanetId = Annotated[int, AfterValidator(validate_planet_id)]
UTCDateTime = Annotated[datetime, AfterValidator(ensure_utc)]


# --- Base Request Models ---


class BaseRequest(BaseModel):
    """Base request model with common fields"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"example": {"timestamp": "2024-08-20T14:30:00Z"}},
    )

    timestamp: UTCDateTime = Field(..., description="UTC timestamp for calculations")


class LocationRequest(BaseRequest):
    """Request with location data"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "timestamp": "2024-08-20T14:30:00Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
            }
        },
    )

    latitude: Latitude = Field(
        ..., description="Latitude in decimal degrees (-90 to 90)"
    )
    longitude: Longitude = Field(
        ..., description="Longitude in decimal degrees (-180 to 180)"
    )


class PlanetRequest(BaseRequest):
    """Request for planet-specific calculations"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {"timestamp": "2024-08-20T14:30:00Z", "planet_id": 2}
        },
    )

    planet_id: PlanetId = Field(
        default=2,
        description="Planet ID (1-9): 1=Sun, 2=Moon, 3=Jupiter, 4=Rahu, 5=Mercury, 6=Venus, 7=Ketu, 8=Saturn, 9=Mars",
    )


class TimeRangeRequest(BaseModel):
    """Request with time range"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "start_time": "2024-08-20T00:00:00Z",
                "end_time": "2024-08-20T23:59:59Z",
            }
        },
    )

    start_time: UTCDateTime = Field(..., description="Start of time range (UTC)")
    end_time: UTCDateTime = Field(..., description="End of time range (UTC)")

    @field_validator("end_time")
    @classmethod
    def validate_time_range(cls, v: datetime, info) -> datetime:
        """Ensure end_time is after start_time"""
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


# --- Base Response Models ---


class MetaInfo(BaseModel):
    """Metadata for API responses"""

    adapter: str = Field(default="KP", description="System adapter used")
    version: str = Field(default="1.0.0", description="API version")
    cache_hit: bool = Field(default=False, description="Whether result was cached")
    compute_time_ms: float = Field(
        default=0.0, description="Computation time in milliseconds"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_id: str | None = Field(default=None, description="Request tracking ID")


class BaseResponse(BaseModel):
    """Base response model with standard structure"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "status": "success",
                "data": {},
                "meta": {
                    "adapter": "KP",
                    "version": "1.0.0",
                    "cache_hit": False,
                    "compute_time_ms": 0.42,
                },
            }
        },
    )

    status: str = Field(default="success", description="Response status")
    data: dict[str, Any] = Field(default_factory=dict, description="Response data")
    meta: MetaInfo = Field(default_factory=MetaInfo, description="Response metadata")


class ErrorResponse(BaseModel):
    """Error response model"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "status": "error",
                "error": "Invalid planet ID",
                "detail": "Planet ID must be between 1-9",
                "code": "INVALID_PLANET",
            }
        },
    )

    status: str = Field(default="error")
    error: str = Field(..., description="Error message")
    detail: str | None = Field(default=None, description="Detailed error information")
    code: str | None = Field(default=None, description="Error code")
    traceback: str | None = Field(
        default=None, description="Stack trace (debug mode only)"
    )


class PaginatedResponse(BaseResponse):
    """Response with pagination"""

    total: int = Field(..., description="Total number of items")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=100, description="Items per page")
    has_next: bool = Field(default=False, description="Whether next page exists")
    has_prev: bool = Field(default=False, description="Whether previous page exists")


# --- Specific Response Models ---


class PositionData(BaseModel):
    """Planet position data"""

    longitude: float = Field(..., description="Ecliptic longitude in degrees")
    latitude: float = Field(..., description="Ecliptic latitude in degrees")
    distance: float = Field(..., description="Distance in AU")
    speed: float = Field(..., description="Speed in degrees/day")
    retrograde: bool = Field(default=False, description="Whether planet is retrograde")
    nakshatra: int = Field(..., description="Nakshatra number (1-27)")
    pada: int = Field(..., description="Pada number (1-4)")
    sign: int = Field(..., description="Zodiac sign (1-12)")
    house: int | None = Field(default=None, description="House number (1-12)")


class KPLordData(BaseModel):
    """KP lord information"""

    nakshatra_lord: int = Field(..., description="Nakshatra lord planet ID")
    sub_lord: int = Field(..., description="Sub lord planet ID")
    sub_sub_lord: int = Field(..., description="Sub-sub lord planet ID")
    nakshatra_name: str = Field(..., description="Nakshatra name")
    degrees_in_nakshatra: float = Field(..., description="Degrees within nakshatra")


class HouseData(BaseModel):
    """House system data"""

    system: str = Field(default="PLACIDUS", description="House system used")
    ascendant: float = Field(..., description="Ascendant degree")
    midheaven: float = Field(..., description="Midheaven degree")
    cusps: list[float] = Field(..., description="12 house cusps in degrees")
    vertex: float | None = Field(default=None, description="Vertex point")

    @field_validator("cusps")
    @classmethod
    def validate_cusps(cls, v: list[float]) -> list[float]:
        """Ensure exactly 12 cusps"""
        if len(v) != 12:
            raise ValueError(f"Must have exactly 12 house cusps, got {len(v)}")
        return v


# --- Mixins for common patterns ---


class CacheableMixin:
    """Mixin for cacheable requests - do not inherit from BaseModel"""

    use_cache: bool = Field(default=True, description="Whether to use cached results")
    cache_ttl: int | None = Field(default=None, description="Cache TTL in seconds")


class BatchRequestMixin:
    """Mixin for batch requests - do not inherit from BaseModel"""

    batch_size: int = Field(default=100, ge=1, le=1000, description="Batch size")
    parallel: bool = Field(default=False, description="Process in parallel")


# Export all models
__all__ = [
    # Base models
    "BaseRequest",
    "LocationRequest",
    "PlanetRequest",
    "TimeRangeRequest",
    "BaseResponse",
    "ErrorResponse",
    "PaginatedResponse",
    # Data models
    "PositionData",
    "KPLordData",
    "HouseData",
    "MetaInfo",
    # Mixins
    "CacheableMixin",
    "BatchRequestMixin",
    # Type annotations
    "Latitude",
    "Longitude",
    "PlanetId",
    "UTCDateTime",
]
