#!/usr/bin/env bash
#
# Smoke-Test fuer Auditworkshop. Standardziel: NUC-Dev (localhost:8000/:3000).
# Funktioniert via BACKEND_BASE/FRONTEND_BASE-ENV auch gegen die Hetzner-
# Deployment-URLs.
#
# Beispiele:
#   # NUC (Default)
#   bash scripts/workshop_smoke.sh
#
#   # CCX23 via Tailscale (intern)
#   BACKEND_BASE=https://cockpit-nbg1-1.tailec75b1.ts.net \
#   FRONTEND_BASE=https://cockpit-nbg1-1.tailec75b1.ts.net \
#     bash scripts/workshop_smoke.sh
#
#   # CCX23 oeffentlich (nach DNS-Flip auf 178.105.58.231)
#   BACKEND_BASE=https://workshop.flowaudit.de \
#   FRONTEND_BASE=https://workshop.flowaudit.de \
#     bash scripts/workshop_smoke.sh
#
#   # Anderer Login-User
#   SMOKE_EMAIL=anderer@host.de  bash scripts/workshop_smoke.sh
#
# Erwartete Ausgabe: 9 Workshop-Checks + 15 State-Aid-Checks (siehe
# state_aid_smoke.sh) — alle PASS. Nicht-Null Exit bei einem FAIL.
set -euo pipefail

BACKEND_BASE="${BACKEND_BASE:-http://localhost:8000}"
FRONTEND_BASE="${FRONTEND_BASE:-http://localhost:3000}"
SMOKE_EMAIL="${SMOKE_EMAIL:-jan.riener@wirtschaft.hessen.de}"

pass=0
fail=0

check() {
  local label="$1"
  local url="$2"
  local expected="$3"
  local auth_header="${4:-}"

  local code
  if [[ -n "$auth_header" ]]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "$auth_header" "$url" || true)
  else
    code=$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)
  fi

  if [[ "$code" == "$expected" ]]; then
    printf 'PASS  [%s] %s\n' "$code" "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL  [%s != %s] %s\n' "$code" "$expected" "$label"
    fail=$((fail + 1))
  fi
}

printf '=== AuditWorkshop Smoke ===\n'
printf 'Frontend: %s\n' "$FRONTEND_BASE"
printf 'Backend:  %s\n' "$BACKEND_BASE"
printf 'Login:    %s\n\n' "$SMOKE_EMAIL"

# Geschuetzte Endpunkte brauchen einen Token. Holen wir uns den vorab.
TOKEN=$(
  curl -s -X POST "$BACKEND_BASE/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$SMOKE_EMAIL\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" \
    2>/dev/null || true
)
AUTH=""
if [[ -n "$TOKEN" ]]; then
  AUTH="Authorization: Bearer $TOKEN"
fi

# Oeffentliche Endpunkte (kein Token notwendig)
check 'Frontend root'                "$FRONTEND_BASE"                                200
check 'Backend health'               "$BACKEND_BASE/health"                          200
check 'System profile (public)'      "$BACKEND_BASE/api/system/profile"              200

# Geschuetzte Endpunkte: ohne Token muss 401 kommen, mit Token 200
check 'Knowledge stats (no auth)'    "$BACKEND_BASE/api/knowledge/stats"             401
check 'Knowledge stats (auth)'       "$BACKEND_BASE/api/knowledge/stats"             200 "$AUTH"
check 'Project list (auth)'          "$BACKEND_BASE/api/projects/"                   200 "$AUTH"
check 'Supported formats (auth)'     "$BACKEND_BASE/api/workshop/supported-formats"  200 "$AUTH"
check 'Beneficiary search (auth)'    "$BACKEND_BASE/api/beneficiaries/search"        200 "$AUTH"
check 'Reference data (auth)'        "$BACKEND_BASE/api/reference-data/sources"      200 "$AUTH"

printf '\nPassed: %d\nFailed: %d\n' "$pass" "$fail"

# State-Aid-Smoke (12 zusaetzliche Checks). Eigene Datei haelt das Hauptskript
# klein und erlaubt isoliertes Ausfuehren bei Demo-Vorbereitung.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$SCRIPT_DIR/state_aid_smoke.sh" ]]; then
  printf '\n=== Running State-Aid Smoke ===\n'
  if BACKEND_BASE="$BACKEND_BASE" bash "$SCRIPT_DIR/state_aid_smoke.sh"; then
    printf '\nState-Aid Smoke OK.\n'
  else
    printf '\nState-Aid Smoke FAIL.\n'
    fail=$((fail + 1))
  fi
else
  printf '\nWARN: %s nicht gefunden — uebersprungen.\n' "$SCRIPT_DIR/state_aid_smoke.sh"
fi

printf '\n=== Total ===\nPassed: %d\nFailed: %d\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
