#!/usr/bin/env bash
# stop.sh — Stack anhalten ohne Datenverlust. Idempotent.
# Bewusst kein `down` und kein `down -v`, damit weder Container-Konfiguration
# noch Volumes verloren gehen.

set -euo pipefail

SLUG="auditworkshop"
STACK_DIR="/opt/${SLUG}"

log() { printf '[stop] %s\n' "$*"; }

cd "${STACK_DIR}"
log "docker compose stop"
docker compose stop
log "Stack angehalten"
