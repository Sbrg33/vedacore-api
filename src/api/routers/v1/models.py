"""
Common models and schemas for API v1

Implements PM requirements for uniform error schema, 
request/response patterns, and Vedic defaults.
"""

from datetime import datetime as dt
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# Common Error Schema (PM requirement)
class ErrorDetail(BaseModel):
    """Error detail for validation issues."""
    field: str = Field(..., description="Field that caused the error")
    message: str = Field(..., description="Error message for this field") 
    code: str = Field(..., description="Error code for this specific issue")


class ErrorResponse(BaseModel):
    """Uniform error response schema for all v1 endpoints."""
    error: Dict[str, Any] = Field(..., description="Error information")
    
    @classmethod
    def create(
        cls,
        code: Literal["VALIDATION_ERROR", "AUTH_ERROR", "RATE_LIMIT", "INTERNAL"],
        message: str,
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ) -> "ErrorResponse":
        """Create standardized error response."""
        return cls(
            error={
                "code": code,
                "message": message, 
                "details": details or {},
                "trace_id": trace_id or str(uuid4())
            }
        )


# Common Request Models
class BaseVedicRequest(BaseModel):
    """Base request for all Vedic calculations with enforced defaults."""
    
    datetime: dt = Field(..., description="UTC datetime in RFC3339 format")
    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees (WGS84)")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees (WGS84)")
    timezone: Optional[str] = Field(None, description="IANA timezone (if local input provided)")
    
    # Vedic defaults (PM requirement)
    zodiac: Literal["sidereal"] = Field(default="sidereal", description="Zodiac system (sidereal enforced)")
    ayanamsha: Literal["kp", "lahiri"] = Field(default="kp", description="Ayanamsha system")
    node_mode: Literal["true_node", "mean_node"] = Field(default="true_node", description="Node calculation mode")
    house_system: Literal["placidus"] = Field(default="placidus", description="House system (Placidus for KP)")
    
    @field_validator("zodiac")
    @classmethod
    def enforce_sidereal(cls, v):
        """Enforce sidereal zodiac for all Vedic calculations."""
        if v != "sidereal":
            raise ValueError("Only sidereal zodiac is supported in Vedic calculations")
        return v


class BaseKPRequest(BaseVedicRequest):
    """Base request for KP-specific calculations with stricter defaults."""
    
    ayanamsha: Literal["kp"] = Field(default="kp", description="KP Ayanamsha (enforced for KP)")
    
    @field_validator("ayanamsha")
    @classmethod
    def enforce_kp_ayanamsha(cls, v):
        """Enforce KP ayanamsha for KP calculations.""" 
        if v != "kp":
            raise ValueError("Only KP ayanamsha is supported in KP calculations")
        return v


# Response envelope for consistent structure
class BaseResponse(BaseModel):
    """Base response with consistent metadata."""
    
    data: Any = Field(..., description="Response data")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")
    
    @classmethod
    def create(cls, data: Any, **meta_kwargs) -> "BaseResponse":
        """Create response with metadata."""
        return cls(data=data, meta=meta_kwargs)


# Common field types
class PlanetPosition(BaseModel):
    """Planet position information."""
    
    planet: str = Field(..., description="Planet identifier") 
    longitude: float = Field(..., description="Longitude in degrees")
    latitude: Optional[float] = Field(None, description="Latitude in degrees")
    speed: float = Field(..., description="Speed in degrees per day")
    retrograde: bool = Field(..., description="Whether planet is retrograde")


class HousePosition(BaseModel):
    """House cusp information."""
    
    house: int = Field(..., ge=1, le=12, description="House number")
    cusp: float = Field(..., description="Cusp longitude in degrees") 
    lord: str = Field(..., description="House lord planet")


# Streaming request models
class StreamTokenRequest(BaseModel):
    """Request for streaming token."""
    
    topic: str = Field(..., description="Topic to subscribe to")
    ttl_seconds: int = Field(default=180, ge=30, le=300, description="Token TTL in seconds")


class StreamTokenResponse(BaseModel):
    """Response for streaming token."""
    
    token: str = Field(..., description="One-time streaming JWT token")
    expires_at: dt = Field(..., description="Token expiration timestamp")
    topic: str = Field(..., description="Authorized topic")


# Path template constants for metering (PM requirement)
PATH_TEMPLATES = {
    # Jyotish endpoints
    "jyotish_chart": "/api/v1/jyotish/chart",
    "jyotish_aspects": "/api/v1/jyotish/aspects", 
    "jyotish_panchanga": "/api/v1/jyotish/panchanga",
    "jyotish_transits_window": "/api/v1/jyotish/transits/window",
    "jyotish_dasha_vimshottari": "/api/v1/jyotish/dasha/vimshottari",
    "jyotish_varga": "/api/v1/jyotish/varga/{type}",
    "jyotish_strength": "/api/v1/jyotish/strength",
    
    # KP endpoints
    "kp_chart": "/api/v1/kp/chart",
    "kp_chain": "/api/v1/kp/chain", 
    "kp_ruling_planets": "/api/v1/kp/ruling-planets",
    "kp_cuspal_interlinks": "/api/v1/kp/cuspal-interlinks",
    "kp_horary": "/api/v1/kp/horary",
    "kp_tara_bala": "/api/v1/kp/tara-bala",
    "kp_transit_events": "/api/v1/kp/transit-events",
    
    # Reference endpoints
    "ref_ayanamshas": "/api/v1/ref/ayanamshas",
    "ref_varga_types": "/api/v1/ref/varga-types", 
    "ref_aspect_modes": "/api/v1/ref/aspect-modes",
    
    # Atlas endpoints
    "atlas_resolve": "/api/v1/atlas/resolve",
    
    # Streaming endpoints
    "stream": "/api/v1/stream",
    "ws": "/api/v1/ws",
    "stream_topics": "/api/v1/stream/topics",
    
    # Auth endpoints
    "auth_stream_token": "/api/v1/auth/stream-token",
}