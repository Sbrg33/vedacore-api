#!/usr/bin/env python3
"""
Shared OpenAPI helpers and reusable response docs.
"""

from __future__ import annotations

from typing import Any, Dict


# Reusable default error responses for routers. These are documentation-only
# (the global exception handler already returns RFC7807 Problem JSON).
DEFAULT_ERROR_RESPONSES: Dict[int, Dict[str, Any]] = {
    401: {
        "description": "Unauthorized",
        "headers": {"WWW-Authenticate": {"schema": {"type": "string"}}},
    },
    403: {"description": "Forbidden"},
    404: {"description": "Not Found"},
    409: {"description": "Conflict"},
    422: {"description": "Validation Error"},  # FastAPI default
    429: {
        "description": "Too Many Requests",
        "headers": {
            "X-RateLimit-Limit": {"schema": {"type": "integer"}},
            "X-RateLimit-Remaining": {"schema": {"type": "integer"}},
            "Retry-After": {
                "schema": {"type": "integer", "description": "Seconds"}
            },
        },
    },
    500: {"description": "Server Error"},
}

