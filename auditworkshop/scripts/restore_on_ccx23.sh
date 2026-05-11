#!/usr/bin/env bash
# restore_on_ccx23.sh — Stufe 8.3 (Daten-Restore auf CCX23).
#
# Wird auf dem CCX23 ausgeführt, nachdem snapshot_for_hetzner.sh die
# Dateien per scp ins Verzeichnis CCX23_DEST gelegt hat.
#
# Was passiert:
#   1. Hash der Snapshot-Dateien verifizieren.
#   2. Falls Schema/Rolle noch nicht existieren, freundlich abbrechen
#      mit Hinweis auf Tracker-Tresor — destruktive Aktionen (DROP,
#      TRUNCATE) führt das Skript nie ohne expliziten ALLOW_DESTRUCTIVE=1.
#   3. pg_restore in das Schema workshop. Quell-Dump nutzt Schema
#      'workshop' (am Quell-Host bereits so konfiguriert) — wir mappen
#      nicht.
#   4. REINDEX SCHEMA workshop.
#   5. Tarball nach /var/lib/auditworkshop/data entpacken.
#   6. Eigentümer auf 1000:1000 setzen (Container-User).
#
# Idempotent — bei zweitem Lauf prüft das Skript, ob die DB-Inhalte
# bereits da sind, und überspringt das Restore (es sei denn,
# FORCE_RESTORE=1 ist gesetzt).

set -euo pipefail

# ── Konfiguration ─────────────────────────────────────────
SNAPSHOT_DIR="${SNAPSHOT_DIR:-/var/tmp/workshop-migration}"
TS="${TS:-}"                              # Pflicht, oder neueste Datei finden
DB_HOST="${DB_HOST:-cockpit-postgres}"
DB_NAME="${DB_NAME:-cockpit}"
DB_SCHEMA="${DB_SCHEMA:-workshop}"
DB_OWNER="${DB_OWNER:-workshop_app}"
DATA_DIR="${DATA_DIR:-/var/lib/auditworkshop/data}"
DATA_OWNER="${DATA_OWNER:-1000:1000}"
PSQL_CONTAINER="${PSQL_CONTAINER:-cockpit-postgres}"
ALLOW_DESTRUCTIVE="${ALLOW_DESTRUCTIVE:-0}"
FORCE_RESTORE="${FORCE_RESTORE:-0}"

log()  { printf '[restore] %s\n' "$*"; }
fail() { printf '[restore] FEHLER: %s\n' "$*" >&2; exit 1; }

# ── Vorbedingungen ────────────────────────────────────────
[[ -d "$SNAPSHOT_DIR" ]] || fail "$SNAPSHOT_DIR existiert nicht"
command -v docker >/dev/null 2>&1 || fail "docker nicht gefunden"
docker ps --format '{{.Names}}' | grep -qx "$PSQL_CONTAINER" \
  || fail "Postgres-Container '$PSQL_CONTAINER' läuft nicht"

# ── Snapshot-Auswahl ──────────────────────────────────────
if [[ -z "$TS" ]]; then
  # neueste Snapshot-Tripletts ermitteln
  HASH_FILE=$(ls -t "$SNAPSHOT_DIR"/workshop-snapshot-*.sha256 2>/dev/null | head -1) \
    || fail "Keine workshop-snapshot-*.sha256 in $SNAPSHOT_DIR"
  [[ -n "$HASH_FILE" ]] || fail "Keine workshop-snapshot-*.sha256 in $SNAPSHOT_DIR"
  TS=$(basename "$HASH_FILE" | sed -E 's/workshop-snapshot-(.+)\.sha256/\1/')
fi
DUMP_FILE="$SNAPSHOT_DIR/workshop-dump-${TS}.dump"
DATA_FILE="$SNAPSHOT_DIR/workshop-data-${TS}.tar.gz"
HASH_FILE="$SNAPSHOT_DIR/workshop-snapshot-${TS}.sha256"

[[ -f "$DUMP_FILE" ]] || fail "$DUMP_FILE fehlt"
[[ -f "$DATA_FILE" ]] || fail "$DATA_FILE fehlt"
[[ -f "$HASH_FILE" ]] || fail "$HASH_FILE fehlt"

log "Snapshot TS=$TS ausgewählt"

# ── 1. Hash-Verifikation ──────────────────────────────────
log "sha256 prüfen"
( cd "$SNAPSHOT_DIR" && sha256sum -c "$(basename "$HASH_FILE")" ) \
  || fail "Hash-Verifikation fehlgeschlagen"

# ── 2. Schema/Rolle prüfen ────────────────────────────────
log "Schema/Rolle in Postgres prüfen"
ROLE_EXISTS=$(docker exec "$PSQL_CONTAINER" psql -U postgres -tAc \
  "SELECT 1 FROM pg_roles WHERE rolname='${DB_OWNER}'" || true)
SCHEMA_EXISTS=$(docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" -tAc \
  "SELECT 1 FROM information_schema.schemata WHERE schema_name='${DB_SCHEMA}'" || true)

if [[ "$ROLE_EXISTS" != "1" ]]; then
  fail "Rolle '$DB_OWNER' fehlt — bitte via Tracker-Tresor das Passwort holen und manuell anlegen: CREATE ROLE $DB_OWNER LOGIN PASSWORD '<aus Tresor>';"
fi
if [[ "$SCHEMA_EXISTS" != "1" ]]; then
  log "Schema '$DB_SCHEMA' fehlt — wird angelegt"
  docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" \
    -c "CREATE SCHEMA $DB_SCHEMA AUTHORIZATION $DB_OWNER;"
fi

# pgvector-Extension prüfen
PGVECTOR_OK=$(docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" -tAc \
  "SELECT 1 FROM pg_extension WHERE extname='vector'" || true)
if [[ "$PGVECTOR_OK" != "1" ]]; then
  log "pgvector-Extension fehlt — wird angelegt"
  docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;"
fi

# ── 3. Restore-Vorbedingung: Schema leer oder FORCE_RESTORE? ──
TABLE_COUNT=$(docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${DB_SCHEMA}'" || true)
TABLE_COUNT="${TABLE_COUNT:-0}"
if [[ "$TABLE_COUNT" -gt 0 ]]; then
  if [[ "$FORCE_RESTORE" -ne 1 ]]; then
    log "Schema $DB_SCHEMA enthält bereits $TABLE_COUNT Tabelle(n)."
    log "Mit FORCE_RESTORE=1 wird das Schema geleert (TRUNCATE) und neu importiert."
    log "Andernfalls überspringe Restore. (Datenpfad-Restore läuft trotzdem unten.)"
  else
    if [[ "$ALLOW_DESTRUCTIVE" -ne 1 ]]; then
      fail "FORCE_RESTORE=1 verlangt zusätzlich ALLOW_DESTRUCTIVE=1 für TRUNCATE/DROP-Operationen."
    fi
    log "FORCE_RESTORE+ALLOW_DESTRUCTIVE: TRUNCATE aller Tabellen im Schema $DB_SCHEMA"
    docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" \
      -c "DO \$\$ DECLARE r record; BEGIN FOR r IN (SELECT schemaname, tablename FROM pg_tables WHERE schemaname='${DB_SCHEMA}') LOOP EXECUTE 'TRUNCATE TABLE '||quote_ident(r.schemaname)||'.'||quote_ident(r.tablename)||' CASCADE'; END LOOP; END \$\$;"
  fi
fi

# ── 4. pg_restore ─────────────────────────────────────────
if [[ "$TABLE_COUNT" -eq 0 || "$FORCE_RESTORE" -eq 1 ]]; then
  log "pg_restore -> $DB_NAME / Schema $DB_SCHEMA"
  # Dump per stdin in den Postgres-Container streamen, damit wir keine
  # Bind-Mount-Konstruktion bauen müssen.
  docker exec -i "$PSQL_CONTAINER" pg_restore --no-owner --role="$DB_OWNER" \
       -d "$DB_NAME" \
       --schema="$DB_SCHEMA" \
       --no-acl \
       < "$DUMP_FILE" \
    || fail "pg_restore fehlgeschlagen"

  log "REINDEX SCHEMA $DB_SCHEMA"
  docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" \
    -c "REINDEX SCHEMA $DB_SCHEMA;"
fi

# ── 5. Datenpfad-Restore ──────────────────────────────────
log "Tarball auspacken nach $DATA_DIR"
sudo mkdir -p "$DATA_DIR"
# strip-components=1, weil im Tarball '<DATA_PATH>/...' enthalten ist.
sudo tar -xzf "$DATA_FILE" -C "$DATA_DIR" --strip-components=1
sudo chown -R "$DATA_OWNER" "$DATA_DIR"

# ── 6. Verifikation ───────────────────────────────────────
log "Verifikation der wichtigsten Marker"
# Geocode-Cache muss vorhanden sein (Workshop-Constraint, 5.200+ Einträge).
if [[ -f "$DATA_DIR/geocode_cache.json" ]]; then
  ENTRIES=$(python3 -c "import json,sys; print(len(json.load(open('$DATA_DIR/geocode_cache.json'))))" 2>/dev/null || echo "?")
  log "  geocode_cache.json: $ENTRIES Einträge"
else
  log "  WARN: $DATA_DIR/geocode_cache.json fehlt"
fi

log "IVFFlat-Index im Schema $DB_SCHEMA prüfen"
docker exec "$PSQL_CONTAINER" psql -U postgres -d "$DB_NAME" -tAc \
  "SELECT indexrelid::regclass FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='${DB_SCHEMA}' AND indexrelid::regclass::text LIKE '%ivfflat%' OR EXISTS (SELECT 1 FROM pg_am am WHERE am.oid=c.relam AND am.amname='ivfflat');" \
  | head || true

log "Restore abgeschlossen — TS=$TS"
