#!/bin/bash
#
# Tägliches Backup des Workshop-Bestands auf CCX23.
#
# Gesichert wird:
#   1. PostgreSQL-Datenbank `workshop` (nativ auf dem Host, ~7 GB)
#   2. /var/lib/auditworkshop/data  — Bind-Mount des Backends: geocode_cache.json
#      (3.177 Einträge, nicht reproduzierbar ohne 3.177 Nominatim-Requests),
#      Transparenzlisten, Demo-Dokumente, Referenzdaten
#   3. /etc/auditworkshop           — Konfiguration inkl. Secrets
#
# Der Dump wird direkt in `age` gestreamt — auf der Platte entsteht nie ein
# unverschlüsselter Dump. Parallel prüft `pg_restore --list` im selben Stream,
# dass das Archiv lesbar ist und die Kerntabellen enthält; ohne diesen Nachweis
# bricht der Lauf ab, bevor rotiert wird.
#
# Cron (deploy):
#   45 2 * * * /bin/bash -lc 'set -a; . /opt/auditworkshop/backup.env; set +a; \
#       /opt/auditworkshop/scripts/backup-auditworkshop-daily.sh' \
#       >> /opt/auditworkshop/backups/backup-daily.log 2>&1
#
# Ablage:
#   lokal (SSD):  /opt/auditworkshop/backups/                     (2 Stück)
#   HC-Volume:    /mnt/HC_Volume_106223615/auditworkshop-backups/ (7 Stück)
#
# Wiederherstellung: siehe restore-auditworkshop-backup.sh

set -euo pipefail

TS=$(date +%Y%m%d_%H%M%S)
DB=workshop
LOCAL_DIR=/opt/auditworkshop/backups
VOLUME_DIR=/mnt/HC_Volume_106223615/auditworkshop-backups
DB_FILE=daily_workshop_${TS}.dump.age
FS_FILE=daily_workshop_files_${TS}.tar.gz.age

# Der komprimierte Dump einer ~7-GB-Datenbank liegt weit über 50 MB. Ein
# kleineres Ergebnis bedeutet abgebrochener Dump — dann nicht rotieren.
MIN_DB_BYTES=$((50 * 1024 * 1024))
MIN_FS_BYTES=$((10 * 1024))

# Tabellen, die im Archiv-Inhaltsverzeichnis auftauchen MÜSSEN. Fehlt eine,
# war der Dump unvollständig.
REQUIRED_TABLES=(
    workshop_beneficiary_records
    workshop_state_aid_awards
    workshop_registrations
    workshop_sanctions_entries
)

RETAIN_LOCAL=2
RETAIN_VOLUME=7

: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT (age1...) muss gesetzt sein}"

log() { echo "[$(date '+%F %T')] $*"; }

TOC=$(mktemp /tmp/workshop-toc.XXXXXX)
cleanup() {
    rm -f "$TOC" "$LOCAL_DIR/$DB_FILE.part" "$VOLUME_DIR/$DB_FILE.part" \
          "$LOCAL_DIR/$FS_FILE.part" "$VOLUME_DIR/$FS_FILE.part"
}
trap cleanup EXIT

log "=== Daily-Backup auditworkshop startet ==="

command -v age >/dev/null 2>&1 || { log "FEHLER: age ist nicht installiert."; exit 1; }
mkdir -p "$LOCAL_DIR" "$VOLUME_DIR"

# ── 1. Datenbank ─────────────────────────────────────────────────────────────
# tee spaltet den Stream: eine Kopie wird verschlüsselt weggeschrieben, die
# andere sofort auf Lesbarkeit geprüft. Klartext berührt nie die Platte.
# Wichtig: `pg_restore --list` liest nur den Archivkopf und beendet sich dann.
# Ohne das nachgeschaltete `cat > /dev/null` bekäme `tee` SIGPIPE und der Dump
# bräche nach wenigen hundert Kilobyte ab. Der Prüfzweig muss den Strom also
# bis zum Ende leerlaufen lassen.
log "Dumpe Datenbank '$DB' …"
sudo -u postgres nice -n 19 pg_dump -Fc "$DB" \
    | tee >( { pg_restore --list > "$TOC" 2>/dev/null || true; cat > /dev/null; } ) \
    | age --recipient "$BACKUP_AGE_RECIPIENT" --output "$LOCAL_DIR/$DB_FILE.part"

# Die Prozess-Substitution läuft nebenläufig — kurz auf das Inhaltsverzeichnis
# warten, bevor es ausgewertet wird.
for _ in $(seq 1 30); do
    grep -q "TOC Entries" "$TOC" 2>/dev/null && break
    sleep 1
done

SIZE=$(stat -c%s "$LOCAL_DIR/$DB_FILE.part")
if [ "$SIZE" -lt "$MIN_DB_BYTES" ]; then
    log "FEHLER: Dump verdächtig klein ($(numfmt --to=iec "$SIZE")) — Abbruch ohne Rotation."
    exit 1
fi

if ! grep -q "TOC Entries" "$TOC"; then
    log "FEHLER: Archiv-Inhaltsverzeichnis nicht lesbar — Abbruch ohne Rotation."
    exit 1
fi
for tbl in "${REQUIRED_TABLES[@]}"; do
    if ! grep -q "TABLE DATA .* $tbl " "$TOC"; then
        log "FEHLER: Tabelle '$tbl' fehlt im Dump — Abbruch ohne Rotation."
        exit 1
    fi
done
TOC_ENTRIES=$(grep -c "^[0-9]" "$TOC" || true)
log "Dump verifiziert: $TOC_ENTRIES Archiv-Einträge, alle Kerntabellen vorhanden."

mv "$LOCAL_DIR/$DB_FILE.part" "$LOCAL_DIR/$DB_FILE"
log "Verschlüsselter Dump OK: $DB_FILE ($(numfmt --to=iec "$SIZE"))"

# ── 2. Dateien und Konfiguration ─────────────────────────────────────────────
log "Sichere Datenverzeichnis und Konfiguration …"
sudo tar -czf - \
    -C / var/lib/auditworkshop/data etc/auditworkshop \
    2>/dev/null \
    | age --recipient "$BACKUP_AGE_RECIPIENT" --output "$LOCAL_DIR/$FS_FILE.part"

FS_SIZE=$(stat -c%s "$LOCAL_DIR/$FS_FILE.part")
if [ "$FS_SIZE" -lt "$MIN_FS_BYTES" ]; then
    log "FEHLER: Datei-Archiv verdächtig klein ($FS_SIZE Bytes) — Abbruch ohne Rotation."
    exit 1
fi
mv "$LOCAL_DIR/$FS_FILE.part" "$LOCAL_DIR/$FS_FILE"
log "Verschlüsseltes Datei-Archiv OK: $FS_FILE ($(numfmt --to=iec "$FS_SIZE"))"

# ── 3. Kopie auf das HC-Volume ───────────────────────────────────────────────
for f in "$DB_FILE" "$FS_FILE"; do
    cp "$LOCAL_DIR/$f" "$VOLUME_DIR/$f.part"
    mv "$VOLUME_DIR/$f.part" "$VOLUME_DIR/$f"
done
log "Kopie auf HC-Volume OK"

# ── 4. Rotation ──────────────────────────────────────────────────────────────
# Nur daily_*-Dateien rotieren; manuell abgelegte pre-*-Dumps bleiben liegen.
rotate() {
    local dir=$1 muster=$2 behalten=$3
    find "$dir" -maxdepth 1 -name "$muster" -printf '%T@ %p\n' \
        | sort -rn | tail -n "+$((behalten + 1))" | cut -d' ' -f2- | xargs -r rm -v
}
rotate "$LOCAL_DIR"  'daily_workshop_20*.dump.age'        "$RETAIN_LOCAL"
rotate "$LOCAL_DIR"  'daily_workshop_files_*.tar.gz.age'  "$RETAIN_LOCAL"
rotate "$VOLUME_DIR" 'daily_workshop_20*.dump.age'        "$RETAIN_VOLUME"
rotate "$VOLUME_DIR" 'daily_workshop_files_*.tar.gz.age'  "$RETAIN_VOLUME"

log "=== Daily-Backup auditworkshop fertig ==="
