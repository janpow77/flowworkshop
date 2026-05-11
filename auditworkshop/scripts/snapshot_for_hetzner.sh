#!/usr/bin/env bash
# snapshot_for_hetzner.sh — Stufe 8.2 (Daten-Snapshot am Quell-Host).
#
# Wird auf dem Heim-Host ausgeführt, der den Quell-Stack betreibt
# (NUC oder Desktop). Erzeugt:
#   - workshop-dump-<TS>.dump        (pg_dump -Fc des Schemas workshop)
#   - workshop-data-<TS>.tar.gz      (Tarball des Bind-Mount /backend/data)
#   - workshop-snapshot-<TS>.sha256  (sha256-Summen beider Dateien)
#
# Standardvorgehen:
#   1. Backend + cloudflared anhalten (DB läuft weiter — Dump bleibt
#      konsistent ohne Schreibvorgänge des Backends).
#   2. pg_dump und tar erzeugen.
#   3. sha256 berechnen.
#   4. Backend + cloudflared wieder starten.
#   5. Optional: Dateien per scp auf CCX23 hochladen (Variable
#      CCX23_HOST), dort Hash verifizieren.
#
# Idempotent — kann mehrfach ausgeführt werden, jeder Lauf hat eigene
# Zeitstempel-Dateien.

set -euo pipefail

# ── Konfiguration (per Env überschreibbar) ────────────────
COMPOSE_DIR="${COMPOSE_DIR:-$(pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_CONTAINER="${DB_CONTAINER:-auditworkshop-db}"
DB_USER="${DB_USER:-workshop}"
DB_NAME="${DB_NAME:-workshop}"
DATA_PATH="${DATA_PATH:-backend/data}"
OUT_DIR="${OUT_DIR:-/var/tmp/workshop-snapshot}"
CCX23_HOST="${CCX23_HOST:-}"            # leer = kein scp
CCX23_USER="${CCX23_USER:-deploy}"
CCX23_DEST="${CCX23_DEST:-/var/tmp/workshop-migration}"
SKIP_STOP="${SKIP_STOP:-0}"             # 1 = Backend nicht anhalten (z.B. Test)

TS=$(date +%Y%m%d-%H%M%S)
DUMP_FILE="workshop-dump-${TS}.dump"
DATA_FILE="workshop-data-${TS}.tar.gz"
HASH_FILE="workshop-snapshot-${TS}.sha256"

log()  { printf '[snapshot] %s\n' "$*"; }
fail() { printf '[snapshot] FEHLER: %s\n' "$*" >&2; exit 1; }

# ── Vorbedingungen ────────────────────────────────────────
[[ -d "$COMPOSE_DIR" ]] || fail "COMPOSE_DIR=$COMPOSE_DIR existiert nicht"
[[ -f "$COMPOSE_DIR/$COMPOSE_FILE" ]] || fail "$COMPOSE_DIR/$COMPOSE_FILE fehlt"
command -v docker >/dev/null 2>&1 || fail "docker nicht gefunden"

mkdir -p "$OUT_DIR"

cd "$COMPOSE_DIR"

# ── 1. Backend + cloudflared anhalten ─────────────────────
if [[ "$SKIP_STOP" -ne 1 ]]; then
  log "Backend + cloudflared anhalten (DB läuft weiter)"
  docker compose -f "$COMPOSE_FILE" stop backend cloudflared 2>/dev/null || \
    log "WARN: backend/cloudflared nicht laufend oder unbekannt — überspringe"
fi

# ── 2. DB-Dump ────────────────────────────────────────────
log "pg_dump -> $OUT_DIR/$DUMP_FILE"
docker exec "$DB_CONTAINER" pg_dump -Fc -U "$DB_USER" "$DB_NAME" \
  > "$OUT_DIR/$DUMP_FILE" \
  || fail "pg_dump fehlgeschlagen"

# ── 3. Bind-Mount-Tarball ─────────────────────────────────
[[ -d "$COMPOSE_DIR/$DATA_PATH" ]] \
  || fail "$COMPOSE_DIR/$DATA_PATH existiert nicht — DATA_PATH prüfen"
log "tar -> $OUT_DIR/$DATA_FILE (Quelle: $DATA_PATH)"
tar -czf "$OUT_DIR/$DATA_FILE" -C "$COMPOSE_DIR" "$DATA_PATH"

# ── 4. sha256-Summen ──────────────────────────────────────
log "sha256 -> $OUT_DIR/$HASH_FILE"
( cd "$OUT_DIR" && sha256sum "$DUMP_FILE" "$DATA_FILE" > "$HASH_FILE" )
log "Inhalt:"
sed 's/^/    /' "$OUT_DIR/$HASH_FILE"

# ── 5. Backend + cloudflared wieder starten ───────────────
if [[ "$SKIP_STOP" -ne 1 ]]; then
  log "Backend + cloudflared wieder starten"
  docker compose -f "$COMPOSE_FILE" start backend cloudflared 2>/dev/null || \
    log "WARN: docker compose start fehlgeschlagen"
fi

# ── 6. Optional: scp + Verifikation ───────────────────────
if [[ -n "$CCX23_HOST" ]]; then
  log "Dateien per scp auf $CCX23_USER@$CCX23_HOST:$CCX23_DEST/ kopieren"
  ssh "$CCX23_USER@$CCX23_HOST" "mkdir -p '$CCX23_DEST'"
  scp "$OUT_DIR/$DUMP_FILE" "$OUT_DIR/$DATA_FILE" "$OUT_DIR/$HASH_FILE" \
      "$CCX23_USER@$CCX23_HOST:$CCX23_DEST/"
  log "Hash auf Zielseite verifizieren"
  ssh "$CCX23_USER@$CCX23_HOST" \
      "cd '$CCX23_DEST' && sha256sum -c '$HASH_FILE'" \
    || fail "Hash-Verifikation auf $CCX23_HOST fehlgeschlagen"
  log "Snapshot $TS auf CCX23 angekommen und verifiziert."
else
  log "CCX23_HOST leer — kein scp. Dateien liegen unter $OUT_DIR."
fi

log "Fertig."
echo "TS=$TS"
echo "DUMP=$OUT_DIR/$DUMP_FILE"
echo "DATA=$OUT_DIR/$DATA_FILE"
echo "HASH=$OUT_DIR/$HASH_FILE"
