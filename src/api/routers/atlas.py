#!/usr/bin/env python3
"""
api/routers/atlas.py — Atlas Search API

Lightweight endpoints to resolve cities to coordinates/timezone.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from pydantic import BaseModel

from app.services.atlas_service import get_by_id, load_atlas, search

router = APIRouter(prefix="/api/v1/atlas", tags=["atlas"], responses=DEFAULT_ERROR_RESPONSES)


class AtlasResult(BaseModel):
    id: str
    name: str
    country: str
    admin1: str | None = None
    latitude: float
    longitude: float
    timezone: str


@router.get(
    "/search",
    response_model=list[AtlasResult],
    summary="Search cities",
    operation_id="atlas_search",
)
def search_cities(
    q: str = Query(..., min_length=1, description="City name query"),
    country: str | None = Query(None, description="Country filter (exact match)"),
    admin1: str | None = Query(None, description="Admin1/State filter (exact match)"),
    limit: int = Query(10, ge=1, le=200),
):
    load_atlas()
    results = search(q, country=country, admin1=admin1, limit=limit)
    return [AtlasResult(**e.to_public()) for e in results]


@router.get(
    "/{city_id}",
    response_model=AtlasResult,
    summary="Get city by id",
    operation_id="atlas_get",
)
def get_city(city_id: str):
    load_atlas()
    entry = get_by_id(city_id)
    if not entry:
        raise HTTPException(404, detail="City not found")
    return AtlasResult(**entry.to_public())
