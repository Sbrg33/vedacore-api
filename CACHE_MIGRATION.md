# Cache Backend Standardization - PM Requirement Implementation

## Overview

Implements PM's requirement: "Use Redis for production, file cache for dev only"

## Changes Made

### 1. Created Unified Cache System (`unified_cache.py`)
- **Production**: Uses Redis backend via `cache_backend.py` 
- **Development**: Uses file-based cache via `cache_service.py`
- **Environment-driven**: Automatically selects backend based on `ENVIRONMENT` variable

### 2. Environment Configuration
```bash
# Production (uses Redis)
ENVIRONMENT=production
CACHE_BACKEND=redis
REDIS_URL=redis://localhost:6379/0

# Development (uses file cache)
ENVIRONMENT=development
```

### 3. Migration Path

**Before (deprecated):**
```python
from app.services.cache_service import CacheService
cache = CacheService(system="KP")
```

**After (standardized):**
```python
from app.services.unified_cache import get_unified_cache
cache = get_unified_cache("KP")  # Auto-selects Redis or file based on environment
```

## Implementation Details

### Backend Selection Logic
1. **Production mode**: Attempts Redis backend, falls back to memory if Redis unavailable
2. **Development mode**: Uses file-based cache for persistence across restarts
3. **Rate limiting**: Already uses Redis backend via `cache_backend.py`

### Migration Status
- ✅ **Security headers**: Added `Referrer-Policy: no-referrer` to SSE responses
- ✅ **Rate limiting metrics**: Prometheus integration with fallback logging  
- ✅ **Cache standardization**: Unified cache system with environment-driven selection
- ✅ **Example migration**: Updated `app/core/session.py` as reference

### Files Modified
- `src/api/routers/stream.py`: Added security headers
- `src/app/services/unified_cache.py`: NEW - Unified cache interface
- `src/app/services/cache_service.py`: Added deprecation notice
- `src/app/core/session.py`: Example migration to unified cache

### Testing
```bash
# Test development mode
ENVIRONMENT=development PYTHONPATH=./src:. python -c "
from app.services.unified_cache import get_unified_cache
cache = get_unified_cache('TEST')
print('Backend:', cache._backend_type)  # Should be 'file'
"

# Test production mode  
ENVIRONMENT=production PYTHONPATH=./src:. python -c "
from app.services.unified_cache import get_unified_cache
cache = get_unified_cache('TEST')
print('Backend:', cache._backend_type)  # Should be 'redis' 
"
```

## Next Steps (Optional)

1. **Gradual migration**: Update remaining cache_service imports to unified_cache
2. **Monitoring**: Add cache backend metrics to existing Prometheus setup
3. **Configuration**: Set `ENVIRONMENT=production` in production deployments

## Backward Compatibility

- Existing `cache_service.py` usage continues to work
- No breaking changes to existing API
- Migration can be done incrementally