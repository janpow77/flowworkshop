#!/usr/bin/env python3
"""
Harvest oeffentliche EFRE/ESF/JTF-Transparenzlisten aller Bundeslaender.

Liest die URL-Registry aus data/transparenzlisten_urls.json,
laedt XLSX-Dateien herunter und verarbeitet sie ueber die Backend-API.
Dadurch wird der Geocoding-Cache fuer den Workshop vorgebaut.

WICHTIG: Alle Daten sind oeffentlich zugaenglich gemaess Art. 49 VO (EU) 2021/1060.

Aufruf:
    # Voller Harvest (Download + Upload + Geocode)
    python3 scripts/harvest_transparenzlisten.py

    # Nur pruefen ob URLs noch erreichbar sind (HEAD-Request)
    python3 scripts/harvest_transparenzlisten.py --check

    # Alle ok-Quellen erneut laden (auch bereits geladene)
    python3 scripts/harvest_transparenzlisten.py --force

Voraussetzungen:
    - Backend laeuft auf http://localhost:8006 (docker-compose)
    - ALLOW_REMOTE_GEOCODING=true in der Backend-Konfiguration
"""
import argparse
import io
import json
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import requests

# --- Konstanten ---

BACKEND_DEFAULT = "http://localhost:8006"
HEADERS = {"User-Agent": "Auditworkshop-EFRE-Demo/1.0 (Workshop-Vorbereitung)"}
TIMEOUT_DOWNLOAD = 60
TIMEOUT_UPLOAD = 300
TIMEOUT_GEOCODE = 600

# Pfad zur URL-Registry
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "transparenzlisten_urls.json"


# --- Registry-I/O ---

def load_registry() -> dict:
    """Laedt die URL-Registry aus der JSON-Datei."""
    if not REGISTRY_PATH.exists():
        print(f"FEHLER: Registry nicht gefunden: {REGISTRY_PATH}")
        sys.exit(1)
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FEHLER: Registry-JSON ungueltig: {e}")
        sys.exit(1)


def save_registry(registry: dict) -> None:
    """Schreibt die Registry zurueck in die JSON-Datei."""
    registry["_updated"] = date.today().isoformat()
    text = json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
    REGISTRY_PATH.write_text(text, encoding="utf-8")
    print(f"\nRegistry aktualisiert: {REGISTRY_PATH}")


def make_label(source: dict) -> str:
    """Erzeugt ein kompaktes Label aus Bundesland, Fonds und Periode."""
    bl = source["bundesland"].replace(" ", "_").replace("-", "_")
    fonds = source["fonds"]
    periode = source["periode"]
    return f"{bl}_{fonds}_{periode}"


# --- Download / Upload / Geocoding ---

def download(label: str, url: str) -> bytes | None:
    """Laedt eine Datei herunter. Behandelt Redirects und ZIP-Archive."""
    print(f"  Download {label} ...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_DOWNLOAD, allow_redirects=True)
        r.raise_for_status()
        content = r.content
        size_kb = len(content) / 1024
        print(f"    {size_kb:.0f} KB heruntergeladen")

        # ZIP-Archiv? Erste XLSX extrahieren.
        # HINWEIS: XLSX-Dateien sind intern ebenfalls ZIP-Archive (PK-Header),
        # daher nur bei expliziter .zip-URL extrahieren.
        if url.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    xlsx_files = [
                        n for n in zf.namelist()
                        if n.lower().endswith((".xlsx", ".xls"))
                    ]
                    if xlsx_files:
                        print(f"    ZIP enthaelt: {xlsx_files[0]}")
                        content = zf.read(xlsx_files[0])
                    else:
                        print("    WARNUNG: Kein XLSX in ZIP gefunden")
                        return None
            except zipfile.BadZipFile:
                print("    WARNUNG: URL endet auf .zip, aber Datei ist kein gueltiges ZIP")
                return None

        return content
    except requests.exceptions.HTTPError as e:
        print(f"    FEHLER: HTTP {e.response.status_code} -- {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"    FEHLER: Verbindung fehlgeschlagen -- {e}")
        return None
    except requests.exceptions.Timeout:
        print(f"    FEHLER: Timeout nach {TIMEOUT_DOWNLOAD}s")
        return None
    except Exception as e:
        print(f"    FEHLER: Download fehlgeschlagen -- {e}")
        return None


def upload(label: str, content: bytes, backend: str) -> dict | None:
    """Laedt XLSX ueber die Backend-API hoch."""
    print(f"  Upload {label} ...")
    try:
        filename = f"{label}.xlsx"
        files = {
            "file": (
                filename,
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        r = requests.post(
            f"{backend}/api/beneficiaries/upload",
            files=files,
            timeout=TIMEOUT_UPLOAD,
        )
        if r.ok:
            data = r.json()
            meta = data.get("metadata", {})
            bundesland = meta.get("bundesland", "?")
            fonds = meta.get("fonds", "?")
            rows = data.get("rows", 0)
            print(f"    OK: {bundesland} {fonds} -- {rows} Vorhaben")
            return data
        else:
            print(f"    FEHLER: HTTP {r.status_code} -- {r.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        print(f"    FEHLER: Upload-Timeout ({TIMEOUT_UPLOAD}s)")
        return None
    except Exception as e:
        print(f"    FEHLER: Upload fehlgeschlagen -- {e}")
        return None


def trigger_geocoding(backend: str) -> int:
    """
    Ruft die Karten-API auf, um Geocoding fuer alle Quellen auszuloesen.
    Der /api/beneficiaries/map-Endpunkt geocodiert automatisch alle Standorte.
    Gibt die Anzahl geocodierter Eintraege zurueck.
    """
    print(f"  Geocoding ausloesen ...")
    try:
        r = requests.get(f"{backend}/api/beneficiaries/map", timeout=TIMEOUT_GEOCODE)
        if r.ok:
            data = r.json()
            count = data.get("count", 0)
            print(f"    {count} Standorte mit Koordinaten")
            return count
        else:
            print(f"    WARNUNG: Map-API HTTP {r.status_code}")
            return 0
    except Exception as e:
        print(f"    WARNUNG: Geocoding-Aufruf fehlgeschlagen -- {e}")
        return 0


def check_url(url: str) -> tuple[bool, int | None]:
    """
    Prueft per HEAD-Request ob eine URL erreichbar ist.
    Gibt (erreichbar, status_code) zurueck.
    """
    try:
        r = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        return r.ok, r.status_code
    except requests.exceptions.RequestException:
        # Manche Server lehnen HEAD ab, Fallback auf GET mit Range
        try:
            r = requests.get(
                url,
                headers={**HEADERS, "Range": "bytes=0-0"},
                timeout=15,
                allow_redirects=True,
            )
            # 200 oder 206 (Partial Content) sind beide ok
            ok = r.status_code in (200, 206)
            return ok, r.status_code
        except requests.exceptions.RequestException:
            return False, None


def print_cache_stats():
    """Gibt Statistiken zum Geocode-Cache aus."""
    try:
        cache_path = Path(__file__).resolve().parent.parent / "data" / "geocode_cache.json"
        if cache_path.exists():
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            with_coords = len([k for k, v in cache.items() if v is not None])
            without_coords = len(cache) - with_coords
            print(f"\n  Geocode-Cache: {len(cache)} Eintraege gesamt")
            print(f"    Mit Koordinaten:  {with_coords}")
            print(f"    Ohne Koordinaten: {without_coords}")
        else:
            print("\n  Geocode-Cache: Datei nicht gefunden")
    except Exception as e:
        print(f"\n  Geocode-Cache: Lesefehler -- {e}")


# --- Befehle ---

def cmd_check(registry: dict) -> None:
    """Prueft alle URLs per HEAD-Request auf Erreichbarkeit."""
    print("\nURL-Verfuegbarkeitspruefung (HEAD-Requests)")
    print("-" * 60)

    changed = False
    sources = registry["sources"]
    checked = 0
    ok_count = 0
    fail_count = 0
    skip_count = 0

    for src in sources:
        label = make_label(src)
        url = src.get("url")

        if not url:
            status = src.get("status", "?")
            print(f"  {label:40s}  SKIP (keine URL, status={status})")
            skip_count += 1
            continue

        reachable, status_code = check_url(url)
        checked += 1

        if reachable:
            print(f"  {label:40s}  OK   (HTTP {status_code})")
            ok_count += 1
            # Falls vorher 404 war, Status aktualisieren
            if src.get("status") == "404":
                src["status"] = "ok"
                changed = True
        else:
            code_str = str(status_code) if status_code else "keine Antwort"
            print(f"  {label:40s}  FAIL (HTTP {code_str})")
            fail_count += 1
            # Status auf 404 setzen falls vorher ok
            if src.get("status") == "ok":
                src["status"] = "404"
                src["notes"] = f"URL lieferte {code_str} am {date.today().isoformat()}, Portal pruefen fuer aktualisierten Link"
                changed = True

        # Nominatim-freundliche Pause (fuer den Fall dass Redirects geocoden)
        time.sleep(0.5)

    print(f"\nErgebnis: {ok_count} erreichbar, {fail_count} fehlgeschlagen, {skip_count} uebersprungen")

    if changed:
        save_registry(registry)
    else:
        print("Keine Status-Aenderungen.")


def cmd_harvest(registry: dict, backend: str, force: bool) -> None:
    """Voller Harvest: Download + Upload + Geocoding fuer alle ok-Quellen."""

    # Backend pruefen
    try:
        r = requests.get(f"{backend}/health", timeout=5)
        r.raise_for_status()
        print(f"Backend erreichbar ({backend})")
    except Exception:
        print(f"FEHLER: Backend nicht erreichbar ({backend})")
        print("Ist der Docker-Stack gestartet? (docker compose up -d)")
        sys.exit(1)

    sources = registry["sources"]
    results = {"success": [], "failed": [], "skipped": []}
    changed = False

    for src in sources:
        label = make_label(src)
        status = src.get("status", "todo")
        url = src.get("url")

        # Nur Quellen mit status "ok" verarbeiten
        if status != "ok":
            reason = {
                "todo": "noch keine URL bekannt",
                "404": "URL nicht erreichbar",
                "manual_download": "nur manueller Download",
                "preloaded": "bereits vorgeladen",
            }.get(status, f"status={status}")
            print(f"\n--- {label} --- SKIP ({reason})")
            results["skipped"].append((label, reason))
            continue

        if not url:
            print(f"\n--- {label} --- SKIP (keine URL trotz status=ok)")
            results["skipped"].append((label, "keine URL"))
            continue

        print(f"\n--- {label} ---")

        # Herunterladen
        content = download(label, url)
        if content is None:
            results["failed"].append((label, "Download"))
            # URL-Status aktualisieren
            src["status"] = "404"
            src["notes"] = f"Download fehlgeschlagen am {date.today().isoformat()}"
            changed = True
            continue

        # Hochladen
        data = upload(label, content, backend)
        if data is None:
            results["failed"].append((label, "Upload"))
            continue

        # Ergebnis in Registry speichern
        rows = data.get("rows", 0)
        if rows and rows != src.get("rows"):
            src["rows"] = rows
            changed = True

        results["success"].append(label)

        # Kurze Pause zwischen Uploads
        time.sleep(1)

    # Geocoding fuer alle Quellen ausloesen
    geocoded = 0
    if results["success"]:
        print(f"\n--- Geocoding ---")
        print("Rufe /api/beneficiaries/map auf (loest Geocoding aus)...")
        print("Das kann mehrere Minuten dauern (1 Request/s Nominatim-Limit).")
        geocoded = trigger_geocoding(backend)

    # Registry aktualisieren
    if changed:
        save_registry(registry)

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("ERGEBNIS")
    print(f"  Erfolgreich:    {len(results['success'])}")
    for s in results["success"]:
        print(f"    + {s}")
    if results["failed"]:
        print(f"  Fehlgeschlagen: {len(results['failed'])}")
        for label, phase in results["failed"]:
            print(f"    ! {label} ({phase})")
    if results["skipped"]:
        print(f"  Uebersprungen:  {len(results['skipped'])}")
        for label, reason in results["skipped"]:
            print(f"    - {label} ({reason})")
    if geocoded:
        print(f"  Geocodierte Standorte: {geocoded}")

    print_cache_stats()
    print("=" * 60)

    # Exit-Code: 0 wenn mindestens eine Quelle erfolgreich oder alle uebersprungen
    sys.exit(0 if results["success"] or not results["failed"] else 1)


# --- CLI ---

def parse_args() -> argparse.Namespace:
    """Kommandozeilen-Argumente parsen."""
    parser = argparse.ArgumentParser(
        description=(
            "Harvest oeffentliche EFRE/ESF/JTF-Transparenzlisten aller Bundeslaender. "
            "Liest URLs aus data/transparenzlisten_urls.json und verarbeitet sie ueber die Backend-API."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python3 scripts/harvest_transparenzlisten.py           # Voller Harvest\n"
            "  python3 scripts/harvest_transparenzlisten.py --check   # Nur URL-Pruefung\n"
            "  python3 scripts/harvest_transparenzlisten.py --force   # Erneut laden\n"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Nur pruefen ob URLs noch erreichbar sind (HEAD-Request), kein Download",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Alle ok-Quellen erneut laden, auch wenn bereits verarbeitet",
    )
    parser.add_argument(
        "--backend",
        default=BACKEND_DEFAULT,
        help=f"Backend-URL (Standard: {BACKEND_DEFAULT})",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("EFRE/ESF/JTF Transparenzlisten-Harvester")
    print("Oeffentliche Daten gemaess Art. 49 VO (EU) 2021/1060")
    print(f"Registry: {REGISTRY_PATH}")
    print("=" * 60)

    registry = load_registry()
    sources = registry.get("sources", [])

    # Statistik-Ueberblick
    status_counts: dict[str, int] = {}
    for src in sources:
        s = src.get("status", "?")
        status_counts[s] = status_counts.get(s, 0) + 1
    print(f"\n{len(sources)} Quellen geladen:")
    for s, c in sorted(status_counts.items()):
        print(f"  {s:20s} {c}")

    if args.check:
        cmd_check(registry)
    else:
        cmd_harvest(registry, args.backend, args.force)


if __name__ == "__main__":
    main()
