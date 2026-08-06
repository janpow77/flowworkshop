#!/bin/bash
# Entschlüsselt ein age-Backup der Workshop-Datenbank und spielt es zurück.
#
# Die private age-Identität liegt bewusst NICHT auf dem Server — sie muss beim
# Restore mitgebracht werden.
#
#   ./restore-auditworkshop-backup.sh BACKUP.dump.age /sicherer/pfad/backup-key.txt
#
# Zum reinen Prüfen eines Backups (ohne etwas zu überschreiben):
#   PRUEFEN=1 ./restore-auditworkshop-backup.sh BACKUP.dump.age key.txt

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Aufruf: $0 BACKUP.dump.age /sicherer/pfad/backup-key.txt" >&2
    exit 2
fi

BACKUP=$1
IDENTITY=$2
DB=${RESTORE_DB:-workshop}

command -v age >/dev/null 2>&1 || { echo "age fehlt." >&2; exit 1; }
[ -r "$BACKUP" ]   || { echo "Backup nicht lesbar: $BACKUP" >&2; exit 1; }
[ -r "$IDENTITY" ] || { echo "Private age-Identität nicht lesbar." >&2; exit 1; }

# Erst Integrität und Format prüfen, ohne etwas zu schreiben.
echo "Prüfe Archiv …"
age --decrypt --identity "$IDENTITY" "$BACKUP" | pg_restore --list | head -20
echo "Archiv lesbar."

if [ "${PRUEFEN:-0}" = "1" ]; then
    echo "PRUEFEN=1 gesetzt — es wurde nichts verändert."
    exit 0
fi

echo
echo "ACHTUNG: Die Datenbank '$DB' wird mit --clean überschrieben."
read -r -p "Zum Fortfahren exakt RESTORE eingeben: " CONFIRM
[ "$CONFIRM" = "RESTORE" ] || { echo "Abgebrochen."; exit 1; }

age --decrypt --identity "$IDENTITY" "$BACKUP" \
    | sudo -u postgres pg_restore --clean --if-exists --no-owner -d "$DB"

echo "Restore abgeschlossen. Anwendung und Smoke-Tests jetzt prüfen."
