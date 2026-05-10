#!/usr/bin/env bash
# migrate.sh — DB-Schema-Migrationen anwenden. Idempotent.
#
# Aktuelle Lage: Workshop nutzt SQLAlchemy `Base.metadata.create_all`
# beim Lifespan-Start (siehe backend/main.py). Echte Schema-Migrationen
# laufen als Inline-`ALTER TABLE`-Anweisungen ebenfalls dort.
# Folge: dieser Hook ist aktuell ein No-Op und dokumentiert nur den
# Status. Sobald Alembic eingeführt wird, wird hier `alembic upgrade
# head` aufgerufen.

set -euo pipefail

log() { printf '[migrate] %s\n' "$*"; }

log "Workshop migriert sein Schema beim Container-Start (Base.metadata.create_all"
log "+ Inline-ALTER-TABLE in backend/main.py). Kein expliziter Hook nötig."
log "Sobald Alembic vorhanden ist, hier 'alembic upgrade head' einfügen."
