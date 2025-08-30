#!/usr/bin/env python3
"""
API request models using Pydantic V2.

All request models follow standardized patterns with consistent field names.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Import base models for consistency
from .base import (
    BaseRequest,
    BatchRequestMixin,
    CacheableMixin,
    Latitude,
    LocationRequest,
    Longitude,
    PlanetId,
    PlanetRequest,
    TimeRangeRequest,
    UTCDateTime,
)


class IntradayRequest(BaseModel, CacheableMixin):
    """Request for intraday signal data"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "date": "2025-08-20",
                "interval": "5s",
                "session_filter": ["REGULAR"],
                "include_off_hours": False,
                "system": "KP",
            }
        },
    )

    date: str = Field(..., description="Date in YYYY-MM-DD format (NY time)")
    interval: Literal["2s", "5s", "15s", "30s", "1m", "5m", "15m", "30m", "1h"] = Field(
        default="5s", description="Time interval for slicing"
    )
    session_filter: list[Literal["PRE_MARKET", "REGULAR", "AFTER_HOURS"]] = Field(
        default=["REGULAR"], description="Trading sessions to include"
    )
    include_off_hours: bool = Field(default=False, description="Include off-hours data")
    system: str = Field(
        default="KP", description="Calculation system (KP only supported currently)"
    )

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format"""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")

    @field_validator("system")
    @classmethod
    def validate_system(cls, v: str) -> str:
        """Validate system is supported"""
        if v != "KP":
            # Only KP is currently supported
            return "KP"
        return v


class PositionRequest(PlanetRequest, CacheableMixin):
    """Request for planetary position at specific time"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "timestamp": "2025-08-20T14:30:00Z",
                "planet_id": 2,
                "apply_offset": True,
                "system": "KP",
            }
        },
    )

    apply_offset: bool = Field(default=True, description="Apply 307s finance offset")
    system: str = Field(
        default="KP", description="Calculation system (KP only supported currently)"
    )

    @field_validator("system")
    @classmethod
    def validate_system(cls, v: str) -> str:
        """Validate system is supported"""
        if v != "KP":
            return "KP"
        return v


class ChangesRequest(TimeRangeRequest, CacheableMixin):
    """Request for lord change detection"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "start_time": "2025-08-20T00:00:00Z",
                "end_time": "2025-08-20T23:59:59Z",
                "planet_id": 2,
                "apply_offset": True,
                "levels": ["nl", "sl", "sl2"],
            }
        },
    )

    planet_id: PlanetId = Field(
        default=2, description="Planet ID (1-9, default 2 for Moon)"
    )
    apply_offset: bool = Field(default=True, description="Apply 307s finance offset")
    levels: list[Literal["nl", "sl", "sl2"]] = Field(
        default=["nl", "sl", "sl2"], description="KP levels to track"
    )


class HouseRequest(LocationRequest, CacheableMixin):
    """Request for house calculations"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "timestamp": "2025-08-20T14:30:00Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "house_system": "PLACIDUS",
            }
        },
    )

    house_system: Literal["PLACIDUS", "KOCH", "EQUAL", "BHAVA"] = Field(
        default="PLACIDUS", description="House system to use"
    )


class DashaRequest(BaseRequest, CacheableMixin):
    """Request for Vimshottari Dasha calculations"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "timestamp": "1990-05-15T10:30:00Z",
                "moon_longitude": 150.0,
                "current_time": "2025-08-20T14:30:00Z",
                "level": 3,
            }
        },
    )

    moon_longitude: float = Field(
        ..., ge=0, lt=360, description="Moon's longitude at birth in degrees"
    )
    current_time: UTCDateTime | None = Field(
        default=None, description="Current time for dasha period (defaults to now)"
    )
    level: int = Field(default=3, ge=1, le=5, description="Dasha level depth (1-5)")

    @field_validator("current_time")
    @classmethod
    def set_current_time(cls, v: datetime | None) -> datetime:
        """Set current time to now if not provided"""
        if v is None:
            return datetime.now(UTC)
        return v


class BatchPositionRequest(BaseModel, BatchRequestMixin, CacheableMixin):
    """Request for batch position calculations"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "timestamps": ["2025-08-20T00:00:00Z", "2025-08-20T12:00:00Z"],
                "planet_ids": [1, 2, 3],
                "apply_offset": True,
            }
        },
    )

    timestamps: list[UTCDateTime] = Field(
        ..., min_length=1, max_length=1000, description="List of timestamps"
    )
    planet_ids: list[PlanetId] = Field(
        default=[2], min_length=1, max_length=9, description="List of planet IDs"
    )
    apply_offset: bool = Field(default=True, description="Apply 307s finance offset")


class TransitRequest(LocationRequest):
    """Request for transit calculations"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "timestamp": "2025-08-20T14:30:00Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "natal_positions": {"1": 120.5, "2": 150.3},
                "orb": 1.0,
            }
        },
    )

    natal_positions: dict[str, float] = Field(
        ..., description="Natal planet positions (planet_id: longitude)"
    )
    orb: float = Field(
        default=1.0, ge=0.1, le=10.0, description="Aspect orb in degrees"
    )
    aspect_types: list[str] = Field(
        default=["conjunction", "opposition", "trine", "square", "sextile"],
        description="Types of aspects to calculate",
    )


class EclipseRequest(TimeRangeRequest, CacheableMixin):
    """Request for eclipse calculations"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-12-31T23:59:59Z",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "eclipse_type": "BOTH",
            }
        },
    )

    latitude: Latitude | None = Field(
        default=None, description="Observer latitude for visibility"
    )
    longitude: Longitude | None = Field(
        default=None, description="Observer longitude for visibility"
    )
    eclipse_type: Literal["SOLAR", "LUNAR", "BOTH"] = Field(
        default="BOTH", description="Type of eclipses to find"
    )


class VargaRequest(PlanetRequest):
    """Request for Varga (divisional chart) calculations"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "timestamp": "2025-08-20T14:30:00Z",
                "varga_type": "D9",
                "planet_id": 1,
            }
        },
    )

    varga_type: str = Field(default="D9", description="Varga chart type (D1-D300)")

    @field_validator("varga_type")
    @classmethod
    def validate_varga_type(cls, v: str) -> str:
        """Validate varga type format"""
        if not v.startswith("D"):
            v = f"D{v}"

        try:
            num = int(v[1:])
            if not 1 <= num <= 300:
                raise ValueError("Varga number must be between 1 and 300")
        except (ValueError, IndexError):
            raise ValueError(f"Invalid varga type: {v}")

        return v


class EnhancedSignalsRequest(BaseModel, CacheableMixin):
    """Request for enhanced KP timing signals with multi-timeframe analysis"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "date": "2025-08-20",
                "timeframes": ["1m", "5m", "15m", "1h"],
                "planet_ids": [2, 3],
                "include_confluence": True,
                "use_cache": True,
                "streaming_enabled": False,
            }
        },
    )

    date: str = Field(..., description="Date in YYYY-MM-DD format (NY time)")
    timeframes: list[Literal["1m", "5m", "15m", "1h", "4h", "1d"]] = Field(
        default=["1m", "5m", "15m", "1h"], 
        description="Timeframes for multi-timeframe analysis"
    )
    planet_ids: list[PlanetId] = Field(
        default=[2], 
        min_length=1, 
        max_length=9, 
        description="Planet IDs to analyze (1-9)"
    )
    include_confluence: bool = Field(
        default=True, 
        description="Include confluence detection across timeframes and planets"
    )
    use_cache: bool = Field(
        default=True, 
        description="Use Redis/cache for faster responses"
    )
    streaming_enabled: bool = Field(
        default=False,
        description="Enable real-time streaming of signal updates"
    )

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format"""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, v: list[str]) -> list[str]:
        """Validate timeframes"""
        valid_timeframes = {"1m", "5m", "15m", "1h", "4h", "1d"}
        invalid = set(v) - valid_timeframes
        if invalid:
            raise ValueError(f"Invalid timeframes: {invalid}. Valid: {valid_timeframes}")
        return v


class SignalStreamRequest(BaseModel):
    """Request for real-time signal streaming"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "topics": ["kp.signals.enhanced", "kp.confluence.alerts"],
                "timeframes": ["1m", "5m"],
                "planet_ids": [2],
                "confluence_threshold": 3,
            }
        },
    )

    topics: list[str] = Field(
        default=["kp.signals.enhanced"], 
        description="Signal topics to stream"
    )
    timeframes: list[Literal["1m", "5m", "15m", "1h", "4h", "1d"]] = Field(
        default=["1m", "5m"], 
        description="Timeframes to monitor"
    )
    planet_ids: list[PlanetId] = Field(
        default=[2], 
        description="Planets to monitor"
    )
    confluence_threshold: int = Field(
        default=3, 
        ge=2, 
        le=10,
        description="Minimum signals required for confluence alert"
    )


# Export all request models
__all__ = [
    "BatchPositionRequest",
    "ChangesRequest",
    "DashaRequest",
    "EclipseRequest",
    "EnhancedSignalsRequest",
    "HouseRequest",
    "IntradayRequest",
    "PositionRequest",
    "SignalStreamRequest",
    "TransitRequest",
    "VargaRequest",
]
