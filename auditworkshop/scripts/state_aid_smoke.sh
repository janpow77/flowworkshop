#!/usr/bin/env bash
# state_aid_smoke.sh — End-to-End-Smoke fuer das State-Aid-Modul.
#
# Prueft die wichtigsten public Endpoints + 1 Validator-Endpoint und macht
# Inhalts-Asserts (z.B. "Siemens" liefert >=3 Treffer). Bei Fehler exit 1
# mit klarer Diagnose.
#
# Usage:
#   bash auditworkshop/scripts/state_aid_smoke.sh
#   BACKEND_BASE=http://localhost:8006 bash auditworkshop/scripts/state_aid_smoke.sh
set -euo pipefail

BACKEND_BASE="${BACKEND_BASE:-http://localhost:8000}"

pass=0
fail=0
warn=0
failures=()

# ── Hilfen ────────────────────────────────────────────────────────────────────

http_status() {
  curl -s -o /dev/null -w '%{http_code}' "$@"
}

check_status() {
  # check_status <label> <url> <expected_status>
  local label="$1"; local url="$2"; local expected="$3"
  local code
  code=$(http_status "$url" || true)
  if [[ "$code" == "$expected" ]]; then
    printf 'PASS  [%s] %s\n' "$code" "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL  [%s != %s] %s\n' "$code" "$expected" "$label"
    fail=$((fail + 1))
    failures+=("$label (got $code, expected $expected)")
  fi
}

assert_json_min_count() {
  # assert_json_min_count <label> <url> <jq-path> <min>
  local label="$1"; local url="$2"; local path="$3"; local min="$4"
  local body
  body=$(curl -s -m 30 "$url" || true)
  if [[ -z "$body" ]]; then
    printf 'FAIL  [empty body] %s\n' "$label"
    fail=$((fail + 1))
    failures+=("$label (empty response)")
    return
  fi
  local count
  count=$(printf '%s' "$body" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    path = '$path'
    cur = data
    for part in path.split('.'):
        if part.isdigit():
            cur = cur[int(part)]
        else:
            cur = cur.get(part)
        if cur is None:
            break
    if isinstance(cur, list):
        print(len(cur))
    elif isinstance(cur, int):
        print(cur)
    else:
        print(0)
except Exception as e:
    print('ERR:', e, file=sys.stderr)
    print(-1)
" 2>&1) || true
  if [[ "$count" =~ ^-?[0-9]+$ ]] && [[ "$count" -ge "$min" ]]; then
    printf 'PASS  [%s>=%s] %s\n' "$count" "$min" "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL  [%s<%s] %s\n' "$count" "$min" "$label"
    fail=$((fail + 1))
    failures+=("$label (got $count, expected >=$min)")
  fi
}

assert_json_field() {
  # assert_json_field <label> <url> <jq-path> <expected_substring>
  local label="$1"; local url="$2"; local path="$3"; local expected="$4"
  local body
  body=$(curl -s -m 30 "$url" || true)
  local val
  val=$(printf '%s' "$body" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    cur = data
    for part in '$path'.split('.'):
        if part.isdigit():
            cur = cur[int(part)]
        else:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            break
    print(cur if cur is not None else '')
except Exception as e:
    print('ERR:', e, file=sys.stderr)
    print('')
" 2>&1) || true
  if [[ "$val" == *"$expected"* ]]; then
    printf 'PASS  [%s] %s\n' "$val" "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL  [%s != *%s*] %s\n' "$val" "$expected" "$label"
    fail=$((fail + 1))
    failures+=("$label (got '$val', expected to contain '$expected')")
  fi
}

# ── Header ────────────────────────────────────────────────────────────────────

printf '=== State-Aid Smoke ===\n'
printf 'Backend: %s\n\n' "$BACKEND_BASE"

# ── 1. Status / Sources ───────────────────────────────────────────────────────

check_status 'GET /api/state-aid/status'                  "$BACKEND_BASE/api/state-aid/status"  200
check_status 'GET /api/state-aid/sources'                 "$BACKEND_BASE/api/state-aid/sources" 200

assert_json_min_count 'status: total_awards >= 1000'      "$BACKEND_BASE/api/state-aid/status"  total_awards 1000
assert_json_min_count 'sources: count >= 4'               "$BACKEND_BASE/api/state-aid/sources" sources      4

# ── 2. Suche (Volltext-Fuzzy) ─────────────────────────────────────────────────

check_status 'GET /search?q=Fraunhofer'                   "$BACKEND_BASE/api/state-aid/search?q=Fraunhofer&country_code=DE&limit=20" 200

# Inhalt: 5 fixe Smoke-Queries muessen je >=3 Treffer liefern
for q in Siemens Trumpf Volkswagen Fraunhofer Bosch; do
  assert_json_min_count "search '$q' (>=3 Treffer)" \
    "$BACKEND_BASE/api/state-aid/search?q=$q&limit=20" total_hits 3
done

# ── 3. Karte ─────────────────────────────────────────────────────────────────

check_status 'GET /map?level=1 (DE)'                      "$BACKEND_BASE/api/state-aid/map?country_code=DE&level=1" 200
assert_json_min_count 'map level=1 (DE) Punkte >= 5'      "$BACKEND_BASE/api/state-aid/map?country_code=DE&level=1" points 5

# ── 4. Award-Detail ─────────────────────────────────────────────────────────

# Erst mal eine ID via Suche holen, dann den Detail-Endpoint pruefen.
AWARD_ID=$(
  curl -s -m 15 "$BACKEND_BASE/api/state-aid/search?q=Fraunhofer&limit=1" \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    hits = d.get('hits') or []
    if hits:
        # Hits sind Award-Dicts inkl. Score; das DB-Primary ist 'id', das
        # Match-Feld 'award_id'. Wir wollen den DB-Primary fuer den
        # /award/{id}-Endpoint, also bevorzugt 'id'.
        h = hits[0]
        print(h.get('id') or h.get('award_id') or '')
except Exception:
    pass
" 2>/dev/null || true
)
if [[ -n "$AWARD_ID" ]]; then
  check_status "GET /award/{id} — $AWARD_ID"             "$BACKEND_BASE/api/state-aid/award/$AWARD_ID" 200
else
  printf 'WARN  [no award id] /award/{id} smoke uebersprungen\n'
  warn=$((warn + 1))
fi

# ── 5. Stats ────────────────────────────────────────────────────────────────

check_status 'GET /stats?country_code=DE'                 "$BACKEND_BASE/api/state-aid/stats?country_code=DE&limit=5" 200

# ── 6. Validator ─────────────────────────────────────────────────────────────

check_status 'GET /validation/last'                       "$BACKEND_BASE/api/state-aid/validation/last" 200

# ── Zusammenfassung ──────────────────────────────────────────────────────────

printf '\n--- State-Aid Smoke ---\n'
printf 'Passed: %d\nFailed: %d\nWarnings: %d\n' "$pass" "$fail" "$warn"
if [[ "${#failures[@]}" -gt 0 ]]; then
  printf '\nFehlgeschlagen:\n'
  for f in "${failures[@]}"; do
    printf '  · %s\n' "$f"
  done
fi
[[ "$fail" -eq 0 ]]
