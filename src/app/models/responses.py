#!/usr/bin/env python3
"""
API response models using Pydantic V2.

All response models follow standardized patterns with consistent structure.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Import base models
from .base import (
    ErrorResponse,
)


class ChangeRef(BaseModel):
    """Reference to a nearby lord change event"""

    type: Literal["NL", "SL", "SL2", "SIGN"] = Field(..., description="Type of change")
    timestamp: str = Field(..., description="Timestamp of change (NY time ISO)")
    delta_seconds: int = Field(..., description="Seconds from current slice to change")
    from_lord: int = Field(..., description="Previous lord ID")
    to_lord: int = Field(..., description="New lord ID")


class IntradaySlice(BaseModel):
    """Single time slice of intraday data"""

    start: str = Field(..., description="Slice start time (NY ISO)")
    end: str = Field(..., description="Slice end time (NY ISO)")
    nl: int = Field(..., description="Nakshatra lord ID")
    sl: int = Field(..., description="Sub lord ID")
    sl2: int = Field(..., description="2nd sub lord ID")
    amd_phase: (
        Literal[
            "volatility_build", "pre_change", "critical_change", "confirmation", "none"
        ]
        | None
    ) = Field(default="none", description="AMD phase relative to nearest change")
    change_ref: ChangeRef | None = Field(
        default=None, description="Nearest change reference"
    )
    session: str = Field(..., description="Trading session")
    position: float = Field(..., description="Planet longitude in degrees")
    speed: float = Field(..., description="Planet speed in degrees/day")


class PositionResponse(BaseModel):
    """Planetary position response"""

    timestamp: datetime = Field(..., description="Calculation timestamp (UTC)")
    planet_id: int = Field(..., description="Planet ID")
    planet_name: str = Field(..., description="Planet name")
    position: float = Field(..., description="Longitude in degrees")
    speed: float = Field(..., description="Speed in degrees/day")
    nl: int = Field(..., description="Nakshatra lord")
    sl: int = Field(..., description="Sub lord")
    sl2: int = Field(..., description="2nd sub lord")
    sign: int = Field(..., description="Zodiac sign (1-12)")
    nakshatra: int = Field(..., description="Nakshatra number (1-27)")
    pada: int = Field(..., description="Pada number (1-4)")
    state: Literal["direct", "retrograde", "stationary"] = Field(
        ..., description="Motion state"
    )
    offset_applied: bool = Field(..., description="Whether 307s offset was applied")


class ChangeEvent(BaseModel):
    """Lord change event"""

    timestamp_utc: datetime = Field(..., description="Change time (UTC)")
    timestamp_ny: datetime = Field(..., description="Change time (NY)")
    planet_id: int = Field(..., description="Planet ID")
    level: str = Field(..., description="Change level (nl/sl/sl2/sign)")
    old_lord: int = Field(..., description="Previous lord/sign")
    new_lord: int = Field(..., description="New lord/sign")
    position: float = Field(..., description="Planet position at change")


class ChangesResponse(BaseModel):
    """Response containing change events"""

    start_date: str = Field(..., description="Start date")
    end_date: str = Field(..., description="End date")
    planet_id: int = Field(..., description="Planet ID")
    planet_name: str = Field(..., description="Planet name")
    total_changes: int = Field(..., description="Total number of changes")
    changes: list[ChangeEvent] = Field(..., description="List of change events")
    by_level: dict[str, int] = Field(..., description="Count by level")


class MetricsResponse(BaseModel):
    """Performance metrics response"""

    uptime_seconds: float
    cache_hit_rate: float
    total_requests: int
    avg_response_time_ms: float
    feature_flags: dict[str, bool]
    metrics: dict[str, Any]


class ErrorResponse(BaseModel):
    """Error response"""

    error: str = Field(..., description="Error message")
    detail: str | None = Field(default=None, description="Detailed error information")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Error timestamp"
    )
    request_id: str | None = Field(default=None, description="Request ID for tracking")


class EnhancedSignal(BaseModel):
    """Enhanced KP timing signal with multi-timeframe context"""

    timestamp: str = Field(..., description="Signal timestamp (NY ISO)")
    timeframe: str = Field(..., description="Signal timeframe (1m, 5m, etc.)")
    planet_id: int = Field(..., description="Planet ID")
    planet_name: str = Field(..., description="Planet name")
    position: float = Field(..., description="Planet longitude in degrees")
    speed: float = Field(..., description="Planet speed in degrees/day")
    nl: int = Field(..., description="Nakshatra lord ID")
    sl: int = Field(..., description="Sub lord ID")
    sl2: int = Field(..., description="2nd sub lord ID")
    signal_type: str = Field(..., description="Signal type (immediate, near_term, etc.)")
    strength: float = Field(..., description="Signal strength (0-100)")
    level: str = Field(..., description="Primary KP level change (nl, sl, sl2)")
    direction: str = Field(..., description="Signal direction (bullish, bearish, neutral)")
    volume_profile: str = Field(..., description="Volume profile classification")


class ConfluenceEvent(BaseModel):
    """Confluence event across multiple timeframes and planets"""

    timestamp: str = Field(..., description="Confluence timestamp (UTC ISO)")
    type: str = Field(..., description="Confluence type")
    strength: float = Field(..., description="Confluence strength score (0-100)")
    signal_count: int = Field(..., description="Number of contributing signals")
    timeframes: list[str] = Field(..., description="Contributing timeframes")
    planets: list[int] = Field(..., description="Contributing planet IDs")
    levels: list[str] = Field(..., description="Contributing KP levels")
    direction: str = Field(..., description="Overall confluence direction")
    signals: list[EnhancedSignal] = Field(..., description="Contributing signals")


class TimeframeAnalysis(BaseModel):
    """Analysis results for a specific timeframe"""

    interval_seconds: int = Field(..., description="Timeframe interval in seconds")
    signals: list[EnhancedSignal] = Field(..., description="Signals for this timeframe")
    signal_count: int = Field(..., description="Total signal count")
    last_update: str | None = Field(default=None, description="Last update timestamp")


class PlanetSignalAnalysis(BaseModel):
    """Signal analysis for a specific planet"""

    planet_id: int = Field(..., description="Planet ID")
    signals: list[EnhancedSignal] = Field(..., description="All signals for this planet")
    signal_count: int = Field(..., description="Total signal count")


class ConfluenceAnalysis(BaseModel):
    """Confluence analysis results"""

    enabled: bool = Field(..., description="Whether confluence analysis was enabled")
    events: list[ConfluenceEvent] = Field(..., description="Detected confluence events")
    event_count: int = Field(..., description="Total confluence event count")


class EnhancedSignalsMetadata(BaseModel):
    """Metadata for enhanced signals response"""

    generated_at: str = Field(..., description="Response generation timestamp")
    cache_key: str = Field(..., description="Cache key used")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    performance_stats: dict[str, Any] | None = Field(
        default=None, description="Performance statistics"
    )


class EnhancedSignalsResponse(BaseModel):
    """Enhanced KP timing signals response with multi-timeframe analysis"""

    date: str = Field(..., description="Analysis date")
    timeframes: dict[str, TimeframeAnalysis] = Field(
        ..., description="Analysis by timeframe"
    )
    planets: dict[str, PlanetSignalAnalysis] = Field(
        ..., description="Analysis by planet"
    )
    confluence: ConfluenceAnalysis = Field(..., description="Confluence analysis")
    metadata: EnhancedSignalsMetadata = Field(..., description="Response metadata")


class SignalStreamUpdate(BaseModel):
    """Real-time signal stream update"""

    event_id: str = Field(..., description="Unique event ID for SSE resumption")
    event_type: str = Field(..., description="Event type (signal, confluence, heartbeat)")
    timestamp: str = Field(..., description="Event timestamp")
    topic: str = Field(..., description="Stream topic")
    data: dict[str, Any] = Field(..., description="Event payload")
    sequence: int | None = Field(default=None, description="Event sequence number")


class PerformanceStatsResponse(BaseModel):
    """Performance statistics for enhanced signals service"""

    total_requests: int = Field(..., description="Total requests processed")
    cache_hits: int = Field(..., description="Cache hit count")
    cache_misses: int = Field(..., description="Cache miss count")
    cache_hit_rate: float = Field(..., description="Cache hit rate percentage")
    avg_response_time_ms: float = Field(..., description="Average response time")
    p95_response_time_ms: float = Field(..., description="95th percentile response time")
    redis_available: bool = Field(..., description="Whether Redis is available")
    service_health: str = Field(..., description="Overall service health")
