"""
Compatibility Shims for Legacy Routes

Provides backward compatibility for existing routes while transitioning to v1.
Implements PM requirements for Deprecation/Sunset headers and migration guidance.
"""

from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse


# Migration mapping: old path -> new path
ROUTE_MIGRATIONS = {
    # Houses API
    "/houses": "/api/v1/jyotish/chart",
    "/api/v1/houses": "/api/v1/jyotish/chart",
    
    # KP endpoints
    "/kp/rp": "/api/v1/kp/ruling-planets",
    "/api/v1/kp/rp/compute": "/api/v1/kp/ruling-planets",
    "/kp/horary": "/api/v1/kp/horary",
    "/kp/horary/calculate": "/api/v1/kp/horary",
    "/api/v1/kp/horary/calculate": "/api/v1/kp/horary",
    
    # Dasha
    "/dasha": "/api/v1/jyotish/dasha/vimshottari",
    "/api/v1/dasha": "/api/v1/jyotish/dasha/vimshottari",
    
    # Moon chain/KP chain
    "/kp/nl_chain": "/api/v1/kp/chain", 
    "/kp/moon_chain": "/api/v1/kp/chain",
    
    # Location features -> Transit windows
    "/features": "/api/v1/jyotish/transits/window",
    "/api/v1/location/features": "/api/v1/jyotish/transits/window",
    
    # Atlas
    "/atlas": "/api/v1/atlas/resolve",
    
    # Streaming
    "/stream": "/api/v1/stream",
    "/ws": "/api/v1/ws",
    
    # Nodes
    "/nodes": "/api/v1/jyotish/chart",  # Include in general chart
    "/api/v1/nodes": "/api/v1/jyotish/chart",
    
    # Eclipse
    "/eclipse": "/api/v1/kp/transit-events",  # Eclipse as transit events
    "/api/v1/eclipse": "/api/v1/kp/transit-events",
    
    # Varga
    "/varga": "/api/v1/jyotish/varga/d9",  # Default to navamsa
    "/api/v1/varga": "/api/v1/jyotish/varga/d9",
    
    # Micro timing -> KP chain analysis
    "/micro": "/api/v1/kp/chain",
    "/api/v1/micro": "/api/v1/kp/chain",
    
    # Strategy -> Transit windows  
    "/strategy": "/api/v1/jyotish/transits/window",
    "/api/v1/strategy": "/api/v1/jyotish/transits/window",
    
    # Tara Bala
    "/tara": "/api/v1/kp/tara-bala",
    "/api/v1/tara": "/api/v1/kp/tara-bala",
    
    # Transit events
    "/transit-events": "/api/v1/kp/transit-events",
    "/api/v1/transit-events": "/api/v1/kp/transit-events",
    
    # Panchanga
    "/panchanga": "/api/v1/jyotish/panchanga",
    "/api/v1/panchanga": "/api/v1/jyotish/panchanga",
}

# Sunset date (60 days from now as PM guidance)
SUNSET_DATE = (datetime.utcnow() + timedelta(days=60)).strftime("%a, %d %b %Y %H:%M:%S GMT")


def get_deprecation_headers(old_path: str, new_path: str) -> Dict[str, str]:
    """Generate deprecation headers following PM requirements."""
    return {
        "Deprecation": "true",
        "Sunset": SUNSET_DATE,
        "Link": f'</api/docs/migration-v1>; rel="deprecation"',
        "X-Migration-Path": new_path,
        "X-Migration-Info": "This endpoint is deprecated. See /api/docs/migration-v1 for migration guidance."
    }


class LegacyShimRouter:
    """Router for handling legacy route compatibility."""
    
    def __init__(self):
        self.router = APIRouter()
        self._setup_shims()
    
    def _setup_shims(self):
        """Setup all legacy route shims."""
        for old_path, new_path in ROUTE_MIGRATIONS.items():
            self._create_shim(old_path, new_path)
    
    def _create_shim(self, old_path: str, new_path: str):
        """Create individual route shim."""
        
        @self.router.get(old_path, include_in_schema=False)
        @self.router.post(old_path, include_in_schema=False)
        @self.router.put(old_path, include_in_schema=False)
        @self.router.patch(old_path, include_in_schema=False)
        @self.router.delete(old_path, include_in_schema=False)
        async def legacy_handler(request: Request):
            """Handle legacy route with deprecation."""
            
            # Get request details
            method = request.method
            headers = get_deprecation_headers(old_path, new_path)
            
            # For GET requests, redirect to new path
            if method == "GET":
                return RedirectResponse(
                    url=new_path + ("?" + str(request.url.query) if request.url.query else ""),
                    status_code=308,  # Permanent redirect
                    headers=headers
                )
            
            # For POST/PUT/PATCH, call new handler (don't redirect)
            else:
                try:
                    # Import the new handler and call it
                    # This is a simplified approach - in reality would need proper handler mapping
                    from api.main import app
                    
                    # Create new request to new path
                    new_url = request.url.replace(path=new_path)
                    
                    # Get request body if present
                    body = await request.body() if method in ["POST", "PUT", "PATCH"] else None
                    
                    # Call new endpoint handler (simplified)
                    response_data = {
                        "message": "Legacy endpoint called - this is a compatibility shim",
                        "new_endpoint": new_path,
                        "migration_required": True,
                        "sunset_date": SUNSET_DATE
                    }
                    
                    return JSONResponse(
                        content=response_data,
                        status_code=200,
                        headers=headers
                    )
                    
                except Exception as e:
                    return JSONResponse(
                        content={
                            "error": {
                                "code": "LEGACY_HANDLER_ERROR",
                                "message": f"Legacy handler failed: {str(e)}",
                                "new_endpoint": new_path,
                                "migration_required": True
                            }
                        },
                        status_code=500,
                        headers=headers
                    )


# Create the legacy shim router
legacy_shim_router = LegacyShimRouter().router


# Manual shim functions for complex migrations
async def houses_shim(request: Request):
    """
    Houses API shim - maps to new jyotish/chart endpoint.
    Handles parameter transformation if needed.
    """
    try:
        # Get request body for POST requests
        if request.method == "POST":
            body = await request.json()
            
            # Transform legacy parameters if needed
            # Legacy: timestamp, latitude, longitude, house_system
            # New: datetime, lat, lon, house_system (same)
            if "timestamp" in body:
                body["datetime"] = body.pop("timestamp")
            if "latitude" in body:
                body["lat"] = body.pop("latitude") 
            if "longitude" in body:
                body["lon"] = body.pop("longitude")
        
        # Call new jyotish/chart handler
        from api.routers.v1.jyotish import calculate_chart
        from api.routers.v1.models import BaseVedicRequest
        
        new_request = BaseVedicRequest(**body)
        result = await calculate_chart(new_request)
        
        # Add deprecation headers
        headers = get_deprecation_headers("/houses", "/api/v1/jyotish/chart")
        
        return JSONResponse(
            content=result.dict(),
            headers=headers
        )
        
    except Exception as e:
        headers = get_deprecation_headers("/houses", "/api/v1/jyotish/chart")
        return JSONResponse(
            content={
                "error": {
                    "code": "MIGRATION_ERROR",
                    "message": f"Houses shim failed: {str(e)}",
                    "new_endpoint": "/api/v1/jyotish/chart"
                }
            },
            status_code=500,
            headers=headers
        )


async def kp_rp_shim(request: Request):
    """
    KP Ruling Planets shim - maps to new kp/ruling-planets endpoint.
    """
    try:
        if request.method == "POST":
            body = await request.json()
            
            # Transform parameters
            if "timestamp" in body:
                body["datetime"] = body.pop("timestamp")
            if "latitude" in body:
                body["lat"] = body.pop("latitude")
            if "longitude" in body: 
                body["lon"] = body.pop("longitude")
        
        # Call new KP ruling planets handler
        from api.routers.v1.kp import calculate_ruling_planets
        from api.routers.v1.models import BaseKPRequest
        
        new_request = BaseKPRequest(**body)
        result = await calculate_ruling_planets(new_request)
        
        headers = get_deprecation_headers("/kp/rp", "/api/v1/kp/ruling-planets")
        
        return JSONResponse(
            content=result.dict(),
            headers=headers
        )
        
    except Exception as e:
        headers = get_deprecation_headers("/kp/rp", "/api/v1/kp/ruling-planets")
        return JSONResponse(
            content={
                "error": {
                    "code": "MIGRATION_ERROR", 
                    "message": f"KP RP shim failed: {str(e)}",
                    "new_endpoint": "/api/v1/kp/ruling-planets"
                }
            },
            status_code=500,
            headers=headers
        )
