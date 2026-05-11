#!/usr/bin/env bash
# lifecycle/_common.sh — wiederverwendbare Bash-Bibliothek für alle
# Cockpit-Apps. Wird von bootstrap.sh, migrate.sh, start.sh, stop.sh
# über `source` eingebunden. Identische Datei in jedem App-Repo
# (auditworkshop, cockpit, audit_designer …) — sie bleibt beim
# Repo-Layout fest und ändert sich nur in einer zentralen Sitzung.
#
# Bereitstellt:
#   verify_slsa_or_die       SLSA-Build-Provenance prüfen, sonst Abbruch
#   wait_for_health_or_rollback  5-Min-Health-Polling mit Rollback-Hook
#   pg_schema_assert         Schema im shared Postgres muss existieren
#   ensure_dir               idempotentes mkdir mit Eigentümer-Kontrolle
#   require_env              Pflicht-Env-Variablen prüfen
#   log/fail/warn            einheitliches Logging mit Slug-Präfix
#
# Erwartet vor dem Source-Aufruf:
#   COMMON_SLUG     — Slug der App (z.B. "auditworkshop")
#   STACK_DIR       — typischerweise /opt/${COMMON_SLUG}
#   ENV_FILE        — typischerweise /etc/${COMMON_SLUG}/env
#
# set -euo pipefail wird vom aufrufenden Skript gesetzt.

: "${COMMON_SLUG:?COMMON_SLUG nicht gesetzt}"

# ── Logging ────────────────────────────────────────────────
log()  { printf '[%s:%s] %s\n' "$(basename "${BASH_SOURCE[1]:-?}" .sh)" "$COMMON_SLUG" "$*"; }
warn() { printf '[%s:%s] WARN: %s\n' "$(basename "${BASH_SOURCE[1]:-?}" .sh)" "$COMMON_SLUG" "$*" >&2; }
fail() { printf '[%s:%s] FEHLER: %s\n' "$(basename "${BASH_SOURCE[1]:-?}" .sh)" "$COMMON_SLUG" "$*" >&2; exit 1; }

# ── Utility: Pflicht-Env prüfen ────────────────────────────
require_env() {
  local var
  for var in "$@"; do
    if [[ -z "${!var:-}" ]]; then
      fail "Pflicht-Env-Variable '${var}' nicht gesetzt"
    fi
  done
}

# ── Utility: Verzeichnis idempotent anlegen ────────────────
# Args: <pfad> <mode> <user> <group>
ensure_dir() {
  local path="$1" mode="$2" user="$3" group="$4"
  sudo install -d -m "$mode" -o "$user" -g "$group" "$path"
}

# ── SLSA-Verify (MIG-04) ───────────────────────────────────
# Prüft die Build-Provenance-Attestation eines Image-Tags. Bricht
# hart ab, wenn `gh attestation verify` fehlschlägt; bei fehlendem
# `gh` warnt der Hook nur (nicht jeder Host hat gh, dann muss cosign
# her).
#
# Args:
#   $1  voller Image-Pfad inkl. Tag, z.B. ghcr.io/janpow77/auditworkshop-backend:sha-abc1234
#   $2  GitHub-Owner für --owner-Flag (z.B. janpow77)
#
# ENV-Override:
#   COMMON_SKIP_SLSA=1  -> Verify bewusst überspringen (Notfall, im migration-log eintragen!)
verify_slsa_or_die() {
  local image="$1" owner="$2"
  if [[ "${COMMON_SKIP_SLSA:-0}" -eq 1 ]]; then
    warn "SLSA-Verify übersprungen (COMMON_SKIP_SLSA=1) — Eintrag im migration-log!"
    return 0
  fi
  if command -v gh >/dev/null 2>&1; then
    log "gh attestation verify oci://${image} --owner ${owner}"
    if ! gh attestation verify "oci://${image}" --owner "$owner" >/dev/null 2>&1; then
      fail "SLSA-Provenance-Verifikation fehlgeschlagen für ${image}. \
Migration/Deploy abgebrochen (MIG-04). Image manuell prüfen oder mit \
COMMON_SKIP_SLSA=1 überspringen (im migration-log dokumentieren)."
    fi
    return 0
  fi
  if command -v cosign >/dev/null 2>&1; then
    log "cosign verify-attestation --type=slsaprovenance ${image}"
    if ! cosign verify-attestation --type=slsaprovenance "$image" >/dev/null 2>&1; then
      fail "SLSA-Provenance-Verifikation per cosign fehlgeschlagen für ${image}."
    fi
    return 0
  fi
  fail "Weder gh noch cosign installiert — SLSA-Verify nicht möglich. \
gh CLI auf dem CCX23 nachinstallieren (apt-get install gh)."
}

# ── Postgres-Schema-Assertion ──────────────────────────────
# Args: <psql-container> <db> <schema>
pg_schema_assert() {
  local container="$1" db="$2" schema="$3"
  local exists
  exists=$(docker exec "$container" psql -U postgres -d "$db" -tAc \
    "SELECT 1 FROM information_schema.schemata WHERE schema_name='${schema}'" \
    2>/dev/null || true)
  if [[ "$exists" != "1" ]]; then
    fail "Schema '${schema}' fehlt in Datenbank '${db}'. \
bootstrap.sh zuerst ausführen (legt Schema und Rolle an)."
  fi
}

# ── Health-Polling mit Rollback (MIG-07) ───────────────────
# Pollt einen Health-Endpoint im 2-Sekunden-Takt für maximal 5 Minuten
# (150 Versuche). Bei Erfolg (status=ready) Rückgabe 0; bei Timeout
# Aufruf der Rollback-Funktion und Rückgabe 1.
#
# Args:
#   $1  Health-URL (z.B. http://localhost:8000/health)
#   $2  Rollback-Funktion-Name (optional, leer = kein Rollback)
#
# ENV-Override:
#   COMMON_HEALTH_TIMEOUT_SECONDS  Default 300 (5 Minuten, MIG-07)
#   COMMON_HEALTH_INTERVAL_SECONDS Default 2
wait_for_health_or_rollback() {
  local url="$1" rollback_fn="${2:-}"
  local timeout="${COMMON_HEALTH_TIMEOUT_SECONDS:-300}"
  local interval="${COMMON_HEALTH_INTERVAL_SECONDS:-2}"
  local deadline=$(( $(date +%s) + timeout ))
  local attempt=0
  log "Health-Polling startet auf ${url} (Timeout ${timeout}s, Intervall ${interval}s)"
  while [[ $(date +%s) -lt $deadline ]]; do
    attempt=$(( attempt + 1 ))
    local body status
    body=$(curl -fsS --max-time 4 "$url" 2>/dev/null || true)
    if [[ -n "$body" ]]; then
      status=$(printf '%s' "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
      if [[ "$status" == "ready" ]]; then
        log "Health=ready nach ${attempt} Versuchen"
        return 0
      fi
      log "Health=${status} (warte weiter)"
    fi
    sleep "$interval"
  done
  warn "Health-Polling Timeout nach ${timeout}s ohne 'ready'"
  if [[ -n "$rollback_fn" ]] && declare -F "$rollback_fn" >/dev/null; then
    warn "Rollback-Funktion '${rollback_fn}' wird aufgerufen"
    "$rollback_fn"
  fi
  return 1
}
