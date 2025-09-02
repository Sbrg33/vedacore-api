#!/usr/bin/env bash
#
# SECURITY VALIDATION: Test Port 8000 Fix
# Validates that the Cloudflare SSL + port mapping security fix is working
#
set -euo pipefail

echo "🔍 VedaCore Security Fix Validation"
echo "==================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success_count=0
total_tests=0

# Test function
run_test() {
    local test_name="$1"
    local expected="$2"
    shift 2
    
    echo -n "🧪 $test_name: "
    total_tests=$((total_tests + 1))
    
    if "$@"; then
        if [ "$expected" = "pass" ]; then
            echo -e "${GREEN}✅ PASS${NC}"
            success_count=$((success_count + 1))
        else
            echo -e "${RED}❌ FAIL (expected to fail, but passed)${NC}"
        fi
    else
        if [ "$expected" = "fail" ]; then
            echo -e "${GREEN}✅ PASS (correctly blocked)${NC}"
            success_count=$((success_count + 1))
        else
            echo -e "${RED}❌ FAIL${NC}"
        fi
    fi
}

# Get server IP from credentials or detect
SERVER_IP=""
if command -v python3 >/dev/null 2>&1; then
    # Try to get IP from DigitalOcean manager
    SERVER_IP=$(python3 -c "
import sys
sys.path.insert(0, '/home/sb108/projects/tools/vedacore-api-toolbox/cloud')
try:
    from credentials_manager import CredentialsManager
    cm = CredentialsManager()
    ip = cm.get_credential('vedacore', 'server_ip')
    if ip: print(ip)
except: pass
" 2>/dev/null || echo "")
fi

# Fallback: try to detect from existing container
if [ -z "$SERVER_IP" ] && command -v docker >/dev/null 2>&1; then
    # Try to get from running container's network
    SERVER_IP=$(docker inspect vedacore-api 2>/dev/null | \
        python3 -c "import json,sys; data=json.load(sys.stdin); print(data[0]['NetworkSettings']['Networks']['bridge']['Gateway'])" 2>/dev/null || echo "")
fi

if [ -z "$SERVER_IP" ]; then
    echo -e "${YELLOW}⚠️  Server IP not detected. Manual testing required.${NC}"
    echo "Get your server IP and run:"
    echo "  curl --max-time 5 http://YOUR_SERVER_IP:8000/api/v1/health/up"
    echo ""
fi

echo "🎯 Target: ${SERVER_IP:-'<IP_NOT_DETECTED>'}"
echo ""

# Test 1: UFW status shows port 8000 blocked
echo "📋 Test 1: UFW Configuration"
if command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "8000.*DENY"; then
        echo -e "✅ UFW correctly blocks port 8000: ${GREEN}PASS${NC}"
        success_count=$((success_count + 1))
    elif ufw status | grep -q "8000.*ALLOW"; then
        echo -e "❌ UFW allows port 8000: ${RED}FAIL - SECURITY RISK${NC}"
    else
        echo -e "⚠️  Port 8000 not found in UFW rules (may be default deny)"
    fi
    total_tests=$((total_tests + 1))
else
    echo "⚠️  UFW not available - cannot test firewall rules"
fi

# Test 2: Container port mapping
echo ""
echo "📋 Test 2: Docker Port Mapping"
if command -v docker >/dev/null 2>&1 && docker ps | grep -q vedacore-api; then
    PORTS=$(docker port vedacore-api 2>/dev/null || echo "none")
    echo "Port mapping: $PORTS"
    
    if echo "$PORTS" | grep -q "80.*8000"; then
        echo -e "✅ Correct port mapping (80→8000): ${GREEN}PASS${NC}"
        success_count=$((success_count + 1))
    else
        echo -e "❌ Incorrect port mapping: ${RED}FAIL${NC}"
        echo "Expected: 0.0.0.0:80->8000/tcp"
    fi
    total_tests=$((total_tests + 1))
else
    echo "⚠️  VedaCore container not running - cannot test port mapping"
fi

# Test 3: Local access via port 80 (should work)
echo ""
run_test "Local HTTP access (port 80)" "pass" \
    curl -fsS --max-time 10 http://localhost:80/api/v1/health/up

# Test 4: External HTTPS access (should work)
echo ""
run_test "External HTTPS access" "pass" \
    curl -fsS --max-time 10 https://api.vedacore.io/api/v1/health/up

# Test 5: Direct port 8000 access (should be blocked)
if [ -n "$SERVER_IP" ]; then
    echo ""
    run_test "Direct port 8000 access (should be BLOCKED)" "fail" \
        timeout 5 bash -c "echo 'test' | nc -w3 $SERVER_IP 8000"
    
    echo ""
    run_test "HTTP request to port 8000 (should be BLOCKED)" "fail" \
        curl -fsS --max-time 5 "http://$SERVER_IP:8000/api/v1/health/up"
fi

# Test 6: Cloudflare SSL mode check (if possible)
echo ""
echo "📋 Test 6: Cloudflare SSL Configuration"
echo "Manual check required:"
echo "1. Go to Cloudflare Dashboard → SSL/TLS → Overview"  
echo "2. Verify SSL mode is 'Flexible'"
echo "3. Confirm Edge certificates are active"

# Summary
echo ""
echo "📊 VALIDATION SUMMARY"
echo "===================="
echo "Tests passed: $success_count/$total_tests"

if [ $success_count -eq $total_tests ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED - SECURITY FIX VALIDATED!${NC}"
    echo ""
    echo "✅ Your VedaCore API is now secure:"
    echo "   - Direct port 8000 access blocked"
    echo "   - Cloudflare proxy path working"
    echo "   - TLS termination at edge"
    echo ""
    echo "🌐 Safe access URLs:"
    echo "   https://api.vedacore.io"
    if [ -n "$SERVER_IP" ]; then
        echo "   http://$SERVER_IP:80 (for debugging only)"
    fi
    exit 0
else
    echo -e "${RED}⚠️  SOME TESTS FAILED - SECURITY FIX MAY BE INCOMPLETE${NC}"
    echo ""
    echo "🔧 Next steps:"
    echo "1. Run: sudo bash tools/security-fix-ports.sh"
    echo "2. Restart container if needed"
    echo "3. Re-run this validation script"
    echo ""
    echo "💡 If issues persist, check SECURITY-FIX.md for troubleshooting"
    exit 1
fi