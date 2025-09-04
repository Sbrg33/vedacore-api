#!/bin/bash
# ATS Regression Protection Verification Script
# Run this before any major deployment to ensure ATS fixes are intact

set -euo pipefail

echo "🛡️  ATS Regression Protection Verification"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_passed=0
check_failed=0

check_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ PASS${NC}: $2"
        ((check_passed++))
    else
        echo -e "${RED}❌ FAIL${NC}: $2"
        ((check_failed++))
    fi
}

echo -e "\n📁 Checking Critical Files..."

# 1. Check if try/catch exists in adapter
if grep -q "try:" src/interfaces/ats_system_adapter.py && grep -q "_ATS_CORE_AVAILABLE = False" src/interfaces/ats_system_adapter.py; then
    check_result 0 "ATS adapter contains try/catch fallback"
else
    check_result 1 "ATS adapter missing try/catch protection"
fi

# 2. Check lazy import in router
if grep -q "_get_service()" src/api/routers/ats.py && grep -q "from app.services.ats_service import ATSService" src/api/routers/ats.py; then
    check_result 0 "ATS router has lazy import protection"
else
    check_result 1 "ATS router missing lazy import"
fi

# 3. Check git status
if [ -z "$(git status --porcelain)" ]; then
    check_result 0 "Repository clean, no uncommitted ATS changes"
else
    echo -e "${YELLOW}⚠️  WARN${NC}: Uncommitted changes detected:"
    git status --porcelain | head -5
fi

# 4. Check commit presence
if git log --oneline -10 | grep -q "8d0ce56.*ats.*prevent startup crash"; then
    check_result 0 "ATS fix commit 8d0ce56 present in history"
else
    check_result 1 "ATS fix commit not found - possible regression risk"
fi

# 5. Test import without crash (if Python available)
if command -v python3 &> /dev/null; then
    if python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from interfaces.ats_system_adapter import ATSSystemAdapter
    print('Import successful')
    exit(0)
except Exception as e:
    print(f'Import failed: {e}')
    exit(1)
" 2>/dev/null; then
        check_result 0 "ATS adapter imports without crash"
    else
        check_result 1 "ATS adapter import test failed"
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC}: Python not available for import test"
fi

echo -e "\n📊 Summary:"
echo -e "  ${GREEN}Passed: $check_passed${NC}"
echo -e "  ${RED}Failed: $check_failed${NC}"

if [ $check_failed -eq 0 ]; then
    echo -e "\n🎉 ${GREEN}ALL CHECKS PASSED${NC} - ATS protection is intact!"
    exit 0
else
    echo -e "\n🚨 ${RED}CHECKS FAILED${NC} - ATS regression risk detected!"
    echo ""
    echo "🛠️  Recovery steps:"
    echo "   1. git checkout 8d0ce565cec4697bd7d9450ac2c733449e2bc134"
    echo "   2. Review changes to ATS files"
    echo "   3. Ensure try/catch and lazy imports are preserved"
    exit 1
fi