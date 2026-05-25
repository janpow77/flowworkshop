#!/bin/sh
# Container-Entrypoint: Datenbankmigrationen anwenden, dann uvicorn starten.
#
# Drei Faelle werden automatisch behandelt:
#   1. Frische DB (keine alembic_version, keine Kerntabelle)
#        -> alembic upgrade head  (legt alle Tabellen via Baseline an)
#   2. Bestehende, noch nicht versionierte DB (keine alembic_version, aber
#      Kerntabelle vorhanden) — z.B. die CCX23-Prod-DB beim ersten Deploy
#        -> alembic stamp head    (uebernimmt Baseline ohne Neuanlage)
#        -> alembic upgrade head  (no-op bzw. spaetere Migrationen)
#   3. Bereits versionierte DB (alembic_version vorhanden)
#        -> alembic upgrade head  (wendet neue Migrationen an)
set -e
cd /app

# DB-Erreichbarkeit abwarten und Zustand erkennen.
# Exit-Code 10 => bestehende, un-gestampte DB (Fall 2).
set +e
python3 - <<'PY'
import sys, time
from sqlalchemy import create_engine, inspect, text
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] DB noch nicht bereit ({attempt + 1}/30): {exc}", file=sys.stderr)
        time.sleep(2)
else:
    print("[entrypoint] DB nicht erreichbar — Abbruch", file=sys.stderr)
    sys.exit(1)

tables = set(inspect(engine).get_table_names())
has_alembic = "alembic_version" in tables
has_core = "workshop_registrations" in tables
sys.exit(10 if (not has_alembic and has_core) else 0)
PY
RC=$?
set -e

if [ "$RC" = "1" ]; then
    echo "[entrypoint] Datenbank nicht erreichbar — beende."
    exit 1
fi

if [ "$RC" = "10" ]; then
    echo "[entrypoint] Bestehende, nicht versionierte DB erkannt -> alembic stamp head"
    alembic stamp head
fi

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

echo "[entrypoint] Starte uvicorn"
exec uvicorn main:app --host 0.0.0.0 --port 8000
