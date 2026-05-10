#!/usr/bin/env bash
# bootstrap.sh — einmalige Erstinitialisierung des auditworkshop-Stacks
# auf dem CCX23. Idempotent: kann mehrfach aufgerufen werden.
#
# Reihenfolge:
#   1. Verzeichnisse anlegen (/var/lib/auditworkshop, /etc/auditworkshop).
#   2. .env aus Vorlage kopieren (Tresor-Werte einsetzen, dann erneut).
#   3. SLSA-Provenance der Image-Tags verifizieren (MIG-04, harter Abbruch
#      bei Fehler, COMMON_SKIP_SLSA=1 nur im Notfall).
#   4. Schema 'workshop' und Rolle 'workshop_app' im shared Postgres
#      sicherstellen (CREATE IF NOT EXISTS).
#   5. pgvector-Extension prüfen.

set -euo pipefail

COMMON_SLUG="auditworkshop"
STACK_DIR="/opt/${COMMON_SLUG}"
DATA_DIR="/var/lib/${COMMON_SLUG}"
CFG_DIR="/etc/${COMMON_SLUG}"
ENV_FILE="${CFG_DIR}/env"
ENV_EXAMPLE="$(dirname "$0")/../.env.production.example"

# shellcheck disable=SC1091
source "$(dirname "$0")/_common.sh"

GHCR_OWNER="${GHCR_OWNER:-janpow77}"
PSQL_CONTAINER="${PSQL_CONTAINER:-cockpit-postgres}"
DB_NAME="${DB_NAME:-cockpit}"
DB_SCHEMA="${DB_SCHEMA:-workshop}"
DB_OWNER="${DB_OWNER:-workshop_app}"

# ── 1. Verzeichnisse ──────────────────────────────────────
log "Verzeichnisse anlegen"
ensure_dir "${DATA_DIR}/data" 0755 1000 1000
ensure_dir "${CFG_DIR}"        0750 root root

# ── 2. .env aus Vorlage ───────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -f "${ENV_EXAMPLE}" ]]; then
    log ".env aus Vorlage kopieren — Tresor-Werte einsetzen!"
    sudo install -m 0600 -o root -g root "${ENV_EXAMPLE}" "${ENV_FILE}"
    fail "${ENV_FILE} angelegt — bitte Tresor-Werte einsetzen, dann erneut ausführen."
  else
    fail "Weder ${ENV_FILE} noch ${ENV_EXAMPLE} gefunden"
  fi
fi

# Werte aus .env laden
# shellcheck disable=SC1090
set -a; source <(grep -E '^(DATABASE_URL|IMAGE_TAG)=' "${ENV_FILE}" || true); set +a

# ── 3. SLSA-Verify für Backend- und Frontend-Image ────────
if [[ -n "${IMAGE_TAG:-}" ]]; then
  verify_slsa_or_die "ghcr.io/${GHCR_OWNER}/auditworkshop-backend:${IMAGE_TAG}"  "${GHCR_OWNER}"
  verify_slsa_or_die "ghcr.io/${GHCR_OWNER}/auditworkshop-frontend:${IMAGE_TAG}" "${GHCR_OWNER}"
else
  warn "IMAGE_TAG nicht gesetzt — SLSA-Verify wird beim ersten Deploy nachgeholt"
fi

# ── 4. Schema/Rolle in Postgres ───────────────────────────
if docker ps --format '{{.Names}}' | grep -qx "$PSQL_CONTAINER"; then
  log "Schema/Rolle in Postgres sicherstellen"
  require_env DATABASE_URL

  ROLE_EXISTS=$(docker exec "$PSQL_CONTAINER" psql -U postgres -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname='${DB_OWNER}'" || true)
  if [[ "$ROLE_EXISTS" != "1" ]]; then
    fail "Rolle '${DB_OWNER}' fehlt — bitte Passwort aus Tracker-Tresor abrufen und manuell anlegen: CREATE ROLE ${DB_OWNER} LOGIN PASSWORD '<aus Tresor>';"
  fi

  SCHEMA_EXISTS=$(docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" -tAc \
    "SELECT 1 FROM information_schema.schemata WHERE schema_name='${DB_SCHEMA}'" || true)
  if [[ "$SCHEMA_EXISTS" != "1" ]]; then
    log "Schema '${DB_SCHEMA}' anlegen"
    docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" \
      -c "CREATE SCHEMA ${DB_SCHEMA} AUTHORIZATION ${DB_OWNER};"
  fi

  PGVECTOR_OK=$(docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" -tAc \
    "SELECT 1 FROM pg_extension WHERE extname='vector'" || true)
  if [[ "$PGVECTOR_OK" != "1" ]]; then
    log "pgvector-Extension aktivieren"
    docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" \
      -c "CREATE EXTENSION IF NOT EXISTS vector;"
  fi
else
  warn "Postgres-Container '${PSQL_CONTAINER}' läuft nicht — DB-Setup übersprungen (Workstream A noch nicht abgeschlossen)"
fi

log "bootstrap abgeschlossen"
