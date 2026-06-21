#!/bin/bash
# CI Frontend Verification Script — v1.19-ci-e2e-audit-export
# Usage: bash scripts/ci_frontend_verify.sh
# Run in frontend directory with Node.js available
set -e

echo "=========================================="
echo " v1.19 CI Frontend Verification"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# ---- 1. Check Node.js ----
echo ""
echo "[1/3] Checking Node.js environment..."
node --version
npm --version
echo "PASS"

# ---- 2. Install dependencies ----
echo ""
echo "[2/3] Installing dependencies (npm ci)..."
npm ci
echo "PASS"

# ---- 3. Production build ----
echo ""
echo "[3/3] Running production build..."
npm run build
echo "Build: PASS"

echo "Checking build output..."
if [ -d "dist" ]; then
    echo "dist/ exists: PASS"
    ls -la dist/ | head -5
else
    echo "dist/ missing: FAIL"
    exit 1
fi

echo ""
echo "=========================================="
echo " v1.19 CI Frontend Verification: PASSED"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
