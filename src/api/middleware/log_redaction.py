"""
Log Redaction Middleware

Implements PM security requirement to mask token values in all logs.
Prevents token leakage in request/response logs and error traces.
"""

import logging
import re
from typing import Callable, Dict, Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_api_logger

logger = get_api_logger("log_redaction")

# Token patterns to redact (PM requirement)
TOKEN_PATTERNS = [
    # Query parameter tokens
    (r'([?&])token=([^&\s]+)', r'\1token=***redacted***'),
    # Authorization Bearer tokens (first 6 chars + ...)
    (r'(Bearer\s+)([A-Za-z0-9+/=]{6})([A-Za-z0-9+/=]{6,})', r'\1\2...'),
    # JWT tokens in general (eyJ prefix)
    (r'(eyJ[A-Za-z0-9+/=]{3,})([A-Za-z0-9+/=]{6,})', r'\1...'),
    # Generic long tokens (base64-like patterns)
    (r'([A-Za-z0-9+/=]{24,})', lambda m: m.group(1)[:6] + '...' if len(m.group(1)) > 12 else '***redacted***'),
]


class LogRedactionFilter(logging.Filter):
    """
    Logging filter to redact sensitive information from log records.
    Applied to all loggers to ensure no token leakage.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record to redact sensitive tokens."""
        # Redact message
        if hasattr(record, 'msg') and record.msg:
            record.msg = self._redact_sensitive_data(str(record.msg))
        
        # Redact args if present
        if hasattr(record, 'args') and record.args:
            record.args = tuple(
                self._redact_sensitive_data(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        
        return True
    
    def _redact_sensitive_data(self, text: str) -> str:
        """Redact sensitive data from text using patterns."""
        for pattern, replacement in TOKEN_PATTERNS[:-1]:  # Skip the lambda one for now
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Handle the lambda pattern separately
        def replace_long_tokens(match):
            token = match.group(1)
            return token[:6] + '...' if len(token) > 12 else '***redacted***'
        
        text = re.sub(TOKEN_PATTERNS[-1][0], replace_long_tokens, text)
        return text


def redact_url_tokens(url: str) -> str:
    """
    Redact tokens from URL query parameters.
    Used for request URL logging.
    """
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        
        # Parse query parameters
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        
        # Redact token parameters
        for param_name in ['token', 'access_token', 'jwt', 'bearer']:
            if param_name in query_params:
                original_values = query_params[param_name]
                query_params[param_name] = [
                    value[:6] + '...' if len(value) > 12 else '***redacted***'
                    for value in original_values
                ]
        
        # Reconstruct URL
        new_query = urlencode(query_params, doseq=True)
        return urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, new_query, parsed.fragment
        ))
        
    except Exception as e:
        logger.warning(f"Failed to redact URL tokens: {e}")
        # Return original URL but log the failure
        return url


class TokenRedactionMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware to redact tokens from request/response logging.
    
    Implements PM requirements:
    - Never log full query strings containing token=
    - Mask tokens in request URLs
    - Redact tokens from error responses
    - Ensure reverse proxy logs also mask tokens
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.setup_logging_filters()
    
    def setup_logging_filters(self):
        """Setup log redaction filters on all relevant loggers."""
        # List of loggers to apply redaction to
        logger_names = [
            'vedacore',  # Our main logger
            'uvicorn',   # ASGI server
            'uvicorn.access',  # Access logs
            'fastapi',   # FastAPI logs
            'starlette', # Starlette logs
            'httpcore',  # HTTP client logs
            'httpx',     # HTTP client logs
        ]
        
        redaction_filter = LogRedactionFilter()
        
        for logger_name in logger_names:
            try:
                log = logging.getLogger(logger_name)
                log.addFilter(redaction_filter)
            except Exception as e:
                logger.warning(f"Failed to add redaction filter to {logger_name}: {e}")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with token redaction."""
        
        # Redact URL for logging (PM requirement)
        original_url = str(request.url)
        redacted_url = redact_url_tokens(original_url)
        
        # Set redacted URL in request state for other middleware/logging
        request.state.redacted_url = redacted_url
        request.state.original_url_redacted = original_url != redacted_url
        
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            # Ensure exceptions don't leak tokens (PM requirement)
            error_msg = str(e)
            redacted_error = self._redact_error_message(error_msg)
            
            # Log the redacted error
            logger.error(
                f"Request failed: {redacted_error}",
                extra={
                    "method": request.method,
                    "url": redacted_url,
                    "error_type": type(e).__name__
                }
            )
            
            # Re-raise with redacted message if it was modified
            if redacted_error != error_msg:
                raise type(e)(redacted_error) from e
            else:
                raise
    
    def _redact_error_message(self, error_msg: str) -> str:
        """Redact tokens from error messages."""
        for pattern, replacement in TOKEN_PATTERNS[:-1]:
            error_msg = re.sub(pattern, replacement, error_msg, flags=re.IGNORECASE)
        
        # Handle lambda pattern
        def replace_long_tokens(match):
            token = match.group(1)
            return token[:6] + '...' if len(token) > 12 else '***redacted***'
        
        error_msg = re.sub(TOKEN_PATTERNS[-1][0], replace_long_tokens, error_msg)
        return error_msg


# Nginx/reverse proxy log format example (PM requirement)
NGINX_LOG_FORMAT_EXAMPLE = """
# Add this to your nginx.conf to mask tokens in access logs
log_format vedacore_secure '$remote_addr - $remote_user [$time_local] '
                           '"$request_method $uri '
                           '${arg_token:+token=***redacted***&}'
                           '${args_without_token} $server_protocol" '
                           '$status $body_bytes_sent '
                           '"$http_referer" "$http_user_agent"';

# Map to remove token from args
map $args $args_without_token {
    ~^(.*)token=[^&]*&?(.*)$ $1$2;
    ~^(.*)token=[^&]*$ $1;
    default $args;
}

# Use the secure log format
access_log /var/log/nginx/vedacore.log vedacore_secure;
"""


def install_global_log_redaction():
    """
    Install log redaction filters globally.
    Called during application startup.
    """
    redaction_filter = LogRedactionFilter()
    
    # Install on root logger to catch everything
    root_logger = logging.getLogger()
    root_logger.addFilter(redaction_filter)
    
    logger.info("🔒 Global log redaction filters installed")
    logger.info("🔒 Tokens will be masked as '***redacted***' or 'token[:6]...'")
    
    # Log the nginx example for ops team
    logger.info("🔧 For reverse proxy log redaction, see TokenRedactionMiddleware.NGINX_LOG_FORMAT_EXAMPLE")

# Backward-compatible alias expected by apps.api.main
# Some environments import LogRedactionMiddleware; keep alias to avoid startup failures in production
LogRedactionMiddleware = TokenRedactionMiddleware
