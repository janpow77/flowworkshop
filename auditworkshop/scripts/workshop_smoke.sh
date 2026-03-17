#!/usr/bin/env bash
set -euo pipefail

BACKEND_BASE="${BACKEND_BASE:-http://localhost:8000}"
FRONTEND_BASE="${FRONTEND_BASE:-http://localhost:3000}"

pass=0
fail=0

check() {
  local label="$1"
  local url="$2"
  local expected="$3"

  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)

  if [[ "$code" == "$expected" ]]; then
    printf 'PASS  [%s] %s\n' "$code" "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL  [%s != %s] %s\n' "$code" "$expected" "$label"
    fail=$((fail + 1))
  fi
}

printf '=== FlowWorkshop Smoke ===\n'
printf 'Frontend: %s\n' "$FRONTEND_BASE"
printf 'Backend:  %s\n\n' "$BACKEND_BASE"

check 'Frontend root' "$FRONTEND_BASE" 200
check 'Backend health' "$BACKEND_BASE/health" 200
check 'Knowledge stats' "$BACKEND_BASE/api/knowledge/stats" 200
check 'System profile' "$BACKEND_BASE/api/system/profile" 200
check 'Supported formats' "$BACKEND_BASE/api/workshop/supported-formats" 200
check 'Project list' "$BACKEND_BASE/api/projects/" 200
check 'Beneficiary search API' "$BACKEND_BASE/api/beneficiaries/search" 200
check 'Reference data sources API' "$BACKEND_BASE/api/reference-data/sources" 200

printf '\nPassed: %d\nFailed: %d\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
