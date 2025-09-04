"""
Request ID Middleware

Ensures every response has an `X-Request-ID` header for correlation.
Stores the value in `request.state.request_id` for downstream use.
"""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        req_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        try:
            request.state.request_id = req_id
        except Exception:
            pass
        response = await call_next(request)
        try:
            response.headers.setdefault(self.header_name, req_id)
        except Exception:
            pass
        return response

