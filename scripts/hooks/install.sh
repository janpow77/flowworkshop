#!/bin/bash
# Installiert die getrackten Git-Hooks aus scripts/hooks/ nach .git/hooks/.
#
# Nach jedem frischen Clone bzw. nach Aenderungen an den Hook-Quellen ausfuehren:
#   bash scripts/hooks/install.sh
#
# Bewusst KEIN `git config core.hooksPath`, damit ein evtl. vom pre-commit-
# Framework verwaltetes .git/hooks/pre-commit nicht ausgehebelt wird — es wird
# nur pro Hook-Datei kopiert.
set -eu

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
GIT_DIR="$(git rev-parse --git-dir)"
DEST="$GIT_DIR/hooks"
mkdir -p "$DEST"

for f in "$SRC_DIR"/*; do
    name="$(basename "$f")"
    case "$name" in
        install.sh|README*|*.md) continue ;;
    esac
    cp "$f" "$DEST/$name"
    chmod +x "$DEST/$name"
    echo "installiert: $name -> $DEST/$name"
done

echo "Fertig. Git-Hooks aktiv."
