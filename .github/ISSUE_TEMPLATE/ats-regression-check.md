---
name: ATS Regression Prevention Checklist  
about: Ensure ATS fixes remain intact before major releases
title: "ATS Module Regression Check"
labels: ["bug-prevention", "ats", "production"]
---

# ATS Module Regression Prevention Checklist

Before any major deployment or when touching ATS-related code:

## 🔍 **Pre-Deployment Verification**
- [ ] Verify `src/interfaces/ats_system_adapter.py` contains try/except block
- [ ] Verify `src/api/routers/ats.py` has lazy import (`_get_service()`)
- [ ] Test container startup without `ats` package: `docker run -p 8000:8000 <image>`
- [ ] Confirm health endpoints work: `curl http://localhost:8000/api/v1/health/up`
- [ ] ATS endpoints return neutral/403 instead of crash

## 🧪 **Critical Test Commands**
```bash
# Test graceful fallback
docker run --rm -e ENVIRONMENT=development vedacore-api:latest python -c "
from interfaces.ats_system_adapter import ATSSystemAdapter
print('✅ ATS adapter loads without crash')
"

# Test API startup
timeout 30 docker run --rm -p 8001:8000 vedacore-api:latest &
sleep 20 && curl -f http://localhost:8001/api/v1/health/up
```

## 🚨 **Regression Indicators**
- Container restart loops on startup
- Import errors mentioning "ats.vedacore_ats"
- 521 errors from Cloudflare
- Health endpoints returning connection refused

## 📝 **Fix Reference**
- **Fixed Commit**: `8d0ce565cec4697bd7d9450ac2c733449e2bc134`
- **Key Files**: `ats_system_adapter.py`, `ats.py` router
- **Strategy**: Try/catch fallback + lazy imports