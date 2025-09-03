"""
API v1 Atlas Router

Geographic resolution and timezone services for Vedic calculations.
Supports city lookup, geocoding, and timezone resolution.
"""

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel, Field

from .models import BaseResponse, ErrorResponse, PATH_TEMPLATES

router = APIRouter(prefix="/api/v1/atlas", tags=["atlas"], responses=DEFAULT_ERROR_RESPONSES)


class GeocodeRequest(BaseModel):
    """Request for geocoding and timezone resolution."""
    query: str = Field(..., min_length=2, description="City, region, or location query")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum results to return")
    country_code: Optional[str] = Field(None, min_length=2, max_length=3, description="ISO country code filter")


class LocationResult(BaseModel):
    """Geographic location result."""
    name: str = Field(..., description="Location name")
    region: str = Field(..., description="Region/state")
    country: str = Field(..., description="Country name")
    country_code: str = Field(..., description="ISO country code")
    latitude: float = Field(..., description="Latitude in decimal degrees")
    longitude: float = Field(..., description="Longitude in decimal degrees")
    timezone: str = Field(..., description="IANA timezone identifier")
    population: Optional[int] = Field(None, description="Population if available")
    elevation: Optional[float] = Field(None, description="Elevation in meters")


class GeocodeResponse(BaseModel):
    """Response for geocoding request."""
    query: str = Field(..., description="Original search query")
    results: List[LocationResult] = Field(..., description="Matching locations")
    total_count: int = Field(..., description="Total matches found")


@router.post(
    "/resolve",
    response_model=BaseResponse,
    summary="Resolve Location",
    operation_id="v1_atlas_resolve",
)
async def resolve_location(request: GeocodeRequest) -> BaseResponse:
    """
    Resolve location query to coordinates and timezone.
    
    Searches cities, regions, and landmarks to provide accurate
    coordinates and IANA timezone identifiers for Vedic calculations.
    """
    try:
        # Import atlas service
        from app.services.atlas_service import search_locations
        
        # Search for locations matching query
        results = search_locations(
            query=request.query,
            limit=request.limit,
            country_filter=request.country_code
        )
        
        # Format results
        location_results = []
        for result in results:
            location_results.append(LocationResult(
                name=result["name"],
                region=result["region"],
                country=result["country"],
                country_code=result["country_code"],
                latitude=result["latitude"],
                longitude=result["longitude"], 
                timezone=result["timezone"],
                population=result.get("population"),
                elevation=result.get("elevation")
            ))
        
        geocode_data = GeocodeResponse(
            query=request.query,
            results=location_results,
            total_count=len(location_results)
        )
        
        return BaseResponse.create(
            data=geocode_data,
            path_template=PATH_TEMPLATES["atlas_resolve"],
            compute_units=0.1
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"Location resolution failed: {str(e)}"
            ).dict()
        )


@router.get(
    "/cities/{query}",
    response_model=BaseResponse,
    summary="Search Cities",
    operation_id="v1_atlas_cities",
)
async def search_cities(
    query: str,
    limit: int = 10,
    country: Optional[str] = None
) -> BaseResponse:
    """
    Search for cities matching query string.
    
    Fast city lookup for autocomplete and selection interfaces.
    Returns cities with coordinates and timezone information.
    """
    if len(query) < 2:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse.create(
                code="VALIDATION_ERROR",
                message="Query must be at least 2 characters",
                details={"query_length": len(query)}
            ).dict()
        )
    
    try:
        # Import atlas service
        from app.services.atlas_service import search_cities_fast
        
        cities = search_cities_fast(
            query=query,
            limit=min(limit, 20),  # Cap at 20
            country_filter=country
        )
        
        return BaseResponse.create(
            data=cities,
            path_template="/api/v1/atlas/cities/{query}",
            query=query,
            count=len(cities),
            compute_units=0.05
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse.create(
                code="INTERNAL",
                message=f"City search failed: {str(e)}"
            ).dict()
        )
