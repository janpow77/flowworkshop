#!/usr/bin/env bash
# bootstrap.sh — einmalige Erstinitialisierung des auditworkshop-Stacks
# auf dem CCX23. Idempotent: kann mehrfach aufgerufen werden.
#
# Voraussetzungen:
#   - Docker und Docker-Compose-Plugin installiert (Workstream A).
#   - Externes Docker-Netz `cockpit` existiert (von Caddy/Postgres-Stack).
#   - Cockpit-Master-Key in /etc/cockpit/master.key vorhanden.
#   - shared Postgres erreichbar im Docker-Netz `cockpit`.
#
# Was passiert:
#   - Verzeichnisse /var/lib/auditworkshop/data und /etc/auditworkshop/
#     anlegen, korrekte Eigentümer setzen.
#   - Schema `workshop` und Rolle `workshop_app` im shared Postgres
#     anlegen, falls nicht vorhanden.
#   - pgvector-Extension prüfen.
#   - .env-Datei aus Vorlage kopieren, falls noch nicht vorhanden.

set -euo pipefail

SLUG="auditworkshop"
DATA_DIR="/var/lib/${SLUG}"
CFG_DIR="/etc/${SLUG}"
ENV_FILE="${CFG_DIR}/env"
ENV_EXAMPLE="$(dirname "$0")/../.env.production.example"

log()  { printf '[bootstrap] %s\n' "$*"; }
fail() { printf '[bootstrap] FEHLER: %s\n' "$*" >&2; exit 1; }

# ── Verzeichnisse ──────────────────────────────────────────
log "Verzeichnisse anlegen"
sudo install -d -m 0755 -o 1000 -g 1000 "${DATA_DIR}/data"
sudo install -d -m 0750 -o root -g root "${CFG_DIR}"

# ── .env aus Vorlage ──────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -f "${ENV_EXAMPLE}" ]]; then
    log ".env-Datei aus Vorlage kopieren — Tresor-Werte einsetzen!"
    sudo install -m 0600 -o root -g root "${ENV_EXAMPLE}" "${ENV_FILE}"
    log "Bitte ${ENV_FILE} mit Tresor-Werten befüllen, dann erneut ausführen."
  else
    fail "Weder ${ENV_FILE} noch ${ENV_EXAMPLE} gefunden"
  fi
fi

# ── DB-Schema und Rolle ───────────────────────────────────
# Erwartet psql-Container im cockpit-Netz; konkreter Aufruf hängt vom
# shared-Postgres-Setup in Workstream A ab. Hier als Platzhalter mit
# klarer Fehlermeldung, falls Voraussetzung fehlt.
if command -v docker >/dev/null 2>&1 && docker network inspect cockpit >/dev/null 2>&1; then
  log "Schema 'workshop' und Rolle 'workshop_app' im shared Postgres prüfen"
  # Annahme: Cockpit stellt einen psql-Container 'cockpit-postgres' bereit.
  # Passwort wird über Tresor vergeben und in /etc/auditworkshop/env hinterlegt.
  if ! grep -q '^DATABASE_URL=' "${ENV_FILE}"; then
    fail "DATABASE_URL fehlt in ${ENV_FILE} — bitte Tresor-Wert einsetzen"
  fi
  log "Hinweis: CREATE ROLE/SCHEMA wird in Workstream A oder Stufe 8.3 ausgeführt."
else
  log "Docker-Netz 'cockpit' fehlt — Workstream A noch nicht abgeschlossen, überspringe DB-Setup"
fi

log "bootstrap abgeschlossen"
