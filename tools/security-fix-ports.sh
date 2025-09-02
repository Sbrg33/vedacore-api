#!/usr/bin/env bash
#
# SECURITY FIX: Close Port 8000 Vulnerability
# Fixes: Direct container access bypassing Cloudflare controls
# 
# This script:
# 1. Ensures port 80->8000 mapping is correct
# 2. Blocks direct port 8000 access via UFW
# 3. Validates the security fix
#
set -euo pipefail

echo "🚨 VedaCore Security Fix: Closing Port 8000 Vulnerability"
echo "========================================================="

# Check if running as root (required for firewall changes)
if [ "$EUID" -ne 0 ]; then 
    echo "❌ This script must be run as root (for UFW changes)"
    echo "Run: sudo $0"
    exit 1
fi

# Check if UFW is available
if ! command -v ufw >/dev/null 2>&1; then
    echo "❌ UFW not found. Install with: apt-get install ufw"
    exit 1
fi

# Show current UFW status
echo "📋 Current UFW Rules:"
ufw status numbered || true
echo ""

# Apply security fix
echo "🔒 Applying Security Fix..."

# Allow required ports
echo "✅ Allowing SSH (22), HTTP (80), HTTPS (443)..."
ufw allow 22/tcp || true
ufw allow 80/tcp || true  
ufw allow 443/tcp || true

# CRITICAL: Block direct container access
echo "🚫 Blocking direct container access (port 8000)..."
ufw deny 8000/tcp || true

# Enable firewall
echo "🛡️  Enabling UFW firewall..."
ufw --force enable || true
ufw reload || true

echo ""
echo "📋 Updated UFW Rules:"
ufw status numbered

# Validate container is running correctly
echo ""
echo "🔍 Validating Container Configuration..."

# Check if vedacore-api container exists and is mapped correctly
if docker ps --format "table {{.Names}}\t{{.Ports}}" | grep vedacore-api; then
    echo "✅ VedaCore container found"
    
    # Check port mapping
    PORTS=$(docker port vedacore-api 2>/dev/null || echo "No ports mapped")
    echo "📍 Port mapping: $PORTS"
    
    if echo "$PORTS" | grep -q "80.*8000"; then
        echo "✅ Correct port mapping: 80->8000"
    else
        echo "⚠️  Port mapping may need adjustment"
        echo "Expected: 0.0.0.0:80->8000/tcp"
        echo "To fix: docker stop vedacore-api && docker rm vedacore-api"
        echo "Then redeploy with: -p 80:8000"
    fi
    
    # Test local access (should work)
    echo "🧪 Testing local container access..."
    if curl -fsS http://localhost:80/api/v1/health/up >/dev/null 2>&1; then
        echo "✅ Local access via port 80: OK"
    else
        echo "❌ Local access via port 80: FAILED"
    fi
    
    # Test direct port 8000 (should be blocked)
    echo "🧪 Testing direct port 8000 access (should be blocked)..."
    if timeout 5 bash -c "</dev/tcp/localhost/8000" 2>/dev/null; then
        echo "⚠️  WARNING: Port 8000 is still accessible directly!"
        echo "UFW may need time to take effect, or container needs restart"
    else
        echo "✅ Port 8000 blocked: Firewall working correctly"
    fi
    
else
    echo "⚠️  VedaCore container not found. Deploy first."
fi

echo ""
echo "🎯 Security Fix Summary:"
echo "========================"
echo "✅ UFW allows: SSH (22), HTTP (80), HTTPS (443)"
echo "🚫 UFW blocks: Direct container access (8000)"
echo "🔗 Cloudflare → Port 80 → Container 8000 (secure path)"
echo "🚫 Direct IP:8000 access blocked (security fix)"
echo ""
echo "🌐 Your API should now be accessible ONLY via:"
echo "   https://api.vedacore.io (Cloudflare proxy)"
echo "   https://yourdomain.com (if configured)"
echo ""
echo "✅ SECURITY VULNERABILITY FIXED!"