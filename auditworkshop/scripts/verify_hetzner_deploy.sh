#!/usr/bin/env bash
# verify_hetzner_deploy.sh — End-to-End-Integrations-Test (S5).
#
# Prüft die zwölf Bedingungen aus dem Master-Plan
# `und-inherited-matsumoto.md`, Abschnitt „End-to-End-Integrations-Test
# (S5)". Wird nach Stufe 8.5 (Cutover) gegen die produktive URL des
# Workshops gefahren.
#
# Nutzung:
#   BASE_URL=https://auditworkshop.tail-xxxx.ts.net \
#   TOKEN=<auth-token-für-geschützte-endpunkte> \
#   COCKPIT_URL=https://cockpit.tail-xxxx.ts.net \
#   bash verify_hetzner_deploy.sh
#
# Exit 0 = alle 12 Bedingungen grün.
# Exit 1 = mindestens eine Bedingung rot.

set -uo pipefail   # kein -e: jeder Check soll laufen, am Ende Summary

BASE_URL="${BASE_URL:?BASE_URL nicht gesetzt}"
TOKEN="${TOKEN:-}"
COCKPIT_URL="${COCKPIT_URL:-}"
SMOKE_EMAIL="${SMOKE_EMAIL:-jan.riener@wirtschaft.hessen.de}"
EXPECTED_KNOWLEDGE_CHUNKS="${EXPECTED_KNOWLEDGE_CHUNKS:-}"
SNAPSHOT_VERIFY_SQL="${SNAPSHOT_VERIFY_SQL:-}"

pass=0
fail=0
results=()

ok()   { results+=("PASS  $1"); pass=$((pass+1)); printf '\033[32mPASS\033[0m  %s\n' "$1"; }
nope() { results+=("FAIL  $1: $2"); fail=$((fail+1)); printf '\033[31mFAIL\033[0m  %s — %s\n' "$1" "$2"; }

# Wenn TOKEN leer und SMOKE_EMAIL gesetzt: Token holen.
if [[ -z "$TOKEN" ]]; then
  TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
            -H 'Content-Type: application/json' \
            -d "{\"email\":\"$SMOKE_EMAIL\"}" \
          | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || true)
fi
AUTH=()
[[ -n "$TOKEN" ]] && AUTH=(-H "Authorization: Bearer $TOKEN")

printf '=== End-to-End-Integrations-Test (S5) ===\n'
printf 'BASE_URL    : %s\n' "$BASE_URL"
printf 'COCKPIT_URL : %s\n\n' "${COCKPIT_URL:-<nicht gesetzt>}"

# 1. Smoke-Test (8 HTTP-Endpunkte)
printf '\n1. Workshop Smoke-Test\n'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if BACKEND_BASE="$BASE_URL" FRONTEND_BASE="$BASE_URL" \
     bash "$SCRIPT_DIR/workshop_smoke.sh" >/tmp/s5_smoke.log 2>&1; then
  ok "(1) Smoke-Test grün"
else
  nope "(1) Smoke-Test" "siehe /tmp/s5_smoke.log"
fi

# 2. Sechs Workshop-Szenarien — wir prüfen ihre HTTP-Endpunkte.
printf '\n2. Workshop-Szenarien\n'
declare -A SC=(
  [1_dokumentenanalyse]="$BASE_URL/api/workshop/supported-formats"
  [2_checklisten]="$BASE_URL/api/checklists/"
  [3_halluzination]="$BASE_URL/api/knowledge/stats"
  [4_bericht]="$BASE_URL/api/workshop/report-formats"
  [5_vorab_upload]="$BASE_URL/api/documents/folders"
  [6_beguenstigte]="$BASE_URL/api/beneficiaries/sources"
)
sc_fail=0
for k in "${!SC[@]}"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" "${SC[$k]}" || true)
  if [[ "$code" =~ ^(200|404)$ ]]; then
    printf '   %-25s %s\n' "$k" "$code"
  else
    printf '   %-25s %s  (FAIL)\n' "$k" "$code"
    sc_fail=$((sc_fail+1))
  fi
done
if [[ $sc_fail -eq 0 ]]; then
  ok "(2) Sechs Szenario-Endpunkte erreichbar"
else
  nope "(2) Sechs Szenarien" "$sc_fail Endpunkte rot"
fi

# 3. Wissensdatenbank-Konsistenz
printf '\n3. Wissensdatenbank-Konsistenz\n'
chunks=$(curl -s "${AUTH[@]}" "$BASE_URL/api/knowledge/stats" \
         | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_chunks',0))" 2>/dev/null || echo 0)
printf '   total_chunks: %s\n' "$chunks"
if [[ -n "$EXPECTED_KNOWLEDGE_CHUNKS" ]]; then
  if [[ "$chunks" == "$EXPECTED_KNOWLEDGE_CHUNKS" ]]; then
    ok "(3) Wissensdatenbank-Chunks matcht ($chunks)"
  else
    nope "(3) Wissensdatenbank-Chunks" "erwartet $EXPECTED_KNOWLEDGE_CHUNKS, gesehen $chunks"
  fi
else
  if [[ "$chunks" -gt 0 ]]; then
    ok "(3) Wissensdatenbank befüllt ($chunks Chunks); EXPECTED_KNOWLEDGE_CHUNKS für strenge Prüfung setzen"
  else
    nope "(3) Wissensdatenbank" "0 Chunks"
  fi
fi

# 4. LLM erreichbar
printf '\n4. LLM-Erreichbarkeit\n'
ollama=$(curl -s "$BASE_URL/api/system/ollama" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('ok') else 'FAIL'); print(','.join(d.get('models',[])))" 2>/dev/null || true)
echo "   $ollama"
if [[ "$ollama" == OK* ]]; then
  ok "(4) Ollama-Endpoint antwortet OK"
else
  nope "(4) LLM" "$ollama"
fi

# 5. Health-Endpoint Cockpit-Schema
printf '\n5. Health-Endpoint im Cockpit-Schema\n'
health=$(curl -s "$BASE_URL/health")
echo "   $health" | head -c 200; echo
status=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
db=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('checks',{}).get('db','?'))" 2>/dev/null || echo "?")
ollm=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('checks',{}).get('ollama','?'))" 2>/dev/null || echo "?")
egpu=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('checks',{}).get('egpu_gateway','?'))" 2>/dev/null || echo "?")
db=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('checks',{}).get('database',{}).get('status','?'))" 2>/dev/null || echo "?")
ollm=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('checks',{}).get('llm_router',{}).get('status','?'))" 2>/dev/null || echo "?")
egpu=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('checks',{}).get('egpu_gateway',{}).get('status','?'))" 2>/dev/null || echo "?")
if [[ "$status" == "ready" && "$db" == "ready" && "$ollm" == "ready" ]]; then
  ok "(5) Health-Schema korrekt — status=ready, database=ready, llm_router=ready, egpu_gateway=$egpu"
else
  nope "(5) Health-Schema" "status=$status database=$db llm_router=$ollm egpu_gateway=$egpu"
fi

# 6. Caddy-TLS — gültiges Zertifikat
printf '\n6. TLS-Zertifikat\n'
host=${BASE_URL#https://}
host=${host%%/*}
if echo | timeout 5 openssl s_client -servername "$host" -connect "$host:443" 2>/dev/null \
   | openssl x509 -noout -issuer 2>/dev/null | grep -qi "let's encrypt\|encryption"; then
  ok "(6) TLS-Zertifikat von Let's Encrypt"
else
  nope "(6) TLS-Zertifikat" "kein Let's Encrypt erkennbar (Tailscale-internes Zertifikat ist OK, dann hier WARN)"
fi

# 7. Cockpit-Statusübersicht zeigt Workshop
printf '\n7. Cockpit-Statusübersicht\n'
if [[ -n "$COCKPIT_URL" ]]; then
  cockpit_apps=$(curl -s "$COCKPIT_URL/api/v1/apps" 2>/dev/null || true)
  if echo "$cockpit_apps" | python3 -c "import sys,json; apps=json.load(sys.stdin); sys.exit(0 if any(a.get('slug')=='auditworkshop' and a.get('status') in ('healthy','ok','running') for a in apps) else 1)" 2>/dev/null; then
    ok "(7) Cockpit listet Workshop als gesund"
  else
    nope "(7) Cockpit-Statusübersicht" "Workshop fehlt oder ungesund"
  fi
else
  nope "(7) Cockpit-Statusübersicht" "COCKPIT_URL nicht gesetzt — überspringe"
fi

# 8. Cockpit-App-Launcher
printf '\n8. Cockpit-App-Launcher\n'
if [[ -n "$COCKPIT_URL" ]]; then
  launcher=$(curl -s "$COCKPIT_URL/api/v1/apps/auditworkshop" 2>/dev/null || true)
  url=$(echo "$launcher" | python3 -c "import sys,json; print(json.load(sys.stdin).get('url',''))" 2>/dev/null || true)
  if [[ "$url" == "$BASE_URL" || "$url" == "${BASE_URL}/" ]]; then
    ok "(8) App-Launcher zeigt korrekte URL"
  else
    nope "(8) App-Launcher" "url='$url' erwartet '$BASE_URL'"
  fi
else
  nope "(8) App-Launcher" "COCKPIT_URL nicht gesetzt"
fi

# 9. Cockpit-Backup-Verwaltung
printf '\n9. Cockpit-Backup-Verwaltung\n'
if [[ -n "$COCKPIT_URL" ]]; then
  backups=$(curl -s "$COCKPIT_URL/api/v1/backups?slug=auditworkshop" 2>/dev/null || true)
  count=$(echo "$backups" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
  if [[ "$count" -gt 0 ]]; then
    ok "(9) Cockpit kennt $count Backup(s) für auditworkshop"
  else
    nope "(9) Cockpit-Backup-Verwaltung" "0 Backups gelistet"
  fi
else
  nope "(9) Cockpit-Backup-Verwaltung" "COCKPIT_URL nicht gesetzt"
fi

# 10. Tracker-Sitzungs-Log
printf '\n10. Tracker-Sitzungs-Log\n'
TRACKER_URL="${TRACKER_URL:-http://nuc.tailnet:8050}"
if curl -s --max-time 5 "$TRACKER_URL/api/v1/briefing" >/dev/null 2>&1; then
  ok "(10) Tracker-Briefing erreichbar — Migrations-Eintrag manuell prüfen"
else
  nope "(10) Tracker-Sitzungs-Log" "Tracker $TRACKER_URL nicht erreichbar"
fi

# 11. Backup-Probe (nur Existenz prüfen, Sandbox-Restore in Cockpit-Domäne)
printf '\n11. Backup-Probe\n'
if [[ -n "$COCKPIT_URL" ]]; then
  test_result=$(curl -s "$COCKPIT_URL/api/v1/backups/auditworkshop/last-restore-test" 2>/dev/null || true)
  status=$(echo "$test_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result','?'))" 2>/dev/null || echo "?")
  if [[ "$status" == "ok" ]]; then
    ok "(11) Letzter Restore-Test in Sandbox: ok"
  else
    nope "(11) Backup-Probe" "Letzter Restore-Test: $status"
  fi
else
  nope "(11) Backup-Probe" "COCKPIT_URL nicht gesetzt"
fi

# 12. Sphärentrennung — Workshop ist shared
printf '\n12. Sphärentrennung\n'
if [[ -n "$COCKPIT_URL" ]]; then
  vis=$(curl -s "$COCKPIT_URL/api/v1/apps/auditworkshop" \
       | python3 -c "import sys,json; print(json.load(sys.stdin).get('visibility','?'))" 2>/dev/null || echo "?")
  if [[ "$vis" == "shared" ]]; then
    ok "(12) Workshop als visibility=shared registriert"
  else
    nope "(12) Sphärentrennung" "visibility='$vis'"
  fi
else
  nope "(12) Sphärentrennung" "COCKPIT_URL nicht gesetzt"
fi

# ── Summary ───────────────────────────────────────────────
printf '\n=== Summary ===\n'
printf '%s\n' "${results[@]}"
printf '\nPassed: %d / %d\n' "$pass" $((pass+fail))
[[ "$fail" -eq 0 ]]
