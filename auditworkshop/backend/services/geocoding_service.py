"""
flowworkshop · geocoding_service.py
Geocoding für Begünstigtenstandorte aus beliebigen EFRE-Verzeichnissen.

Erkennt Spalten automatisch (Name, Standort, Kosten, Projekt, etc.).
Nutzt Nominatim (OpenStreetMap) mit persistentem Cache.
Rate-Limit: max 1 Request/Sekunde (Nominatim Policy).
"""
from __future__ import annotations
import json
import logging
import re
import time
from pathlib import Path

import requests
from sqlalchemy import text

from config import GEOCODE_CACHE, ALLOW_REMOTE_GEOCODING
from database import engine

log = logging.getLogger(__name__)

_cache: dict[str, dict | None] = {}
_last_request_time = 0.0

# ── NUTS-3 Zuordnung ─────────────────────────────────────────────────────────

_nuts_data: dict | None = None


def _load_nuts() -> dict:
    """Laedt die NUTS-3 Regionsdaten aus der JSON-Datei."""
    global _nuts_data
    if _nuts_data is None:
        nuts_path = Path(__file__).parent.parent / "data" / "nuts_de.json"
        if nuts_path.exists():
            _nuts_data = json.loads(nuts_path.read_text(encoding="utf-8"))
            log.info("NUTS-Daten geladen: %d Regionen", len(_nuts_data))
        else:
            _nuts_data = {}
    return _nuts_data


def lookup_nuts(lat: float, lon: float) -> dict | None:
    """Findet die naechste NUTS-3 Region fuer gegebene Koordinaten (einfache Distanzsuche)."""
    nuts = _load_nuts()
    if not nuts:
        return None
    best_code = None
    best_dist = float('inf')
    for code, info in nuts.items():
        dlat = lat - info["lat"]
        dlon = lon - info["lon"]
        dist = dlat * dlat + dlon * dlon
        if dist < best_dist:
            best_dist = dist
            best_code = code
    if best_code and best_dist < 0.5:  # ~50km Radius
        info = nuts[best_code]
        return {"nuts3": best_code, "region": info["name"], "bundesland": info["bundesland"]}
    return None

# ── Spalten-Erkennung ─────────────────────────────────────────────────────────
# Patterns fuer automatische Zuordnung von Spalten in beliebigen Verzeichnissen

COLUMN_PATTERNS = {
    "name": [
        r"^name_des",  # Abgeschnittenes "Name des Begünstigten"
        r"^benef_?name$",
        r"name.*begünstig", r"name.*auftrag",
        r"(?:name|bezeichnung).*begünstig",  # Erfordert "name"/"bezeichnung" vor "begünstig"
        r"beneficiary",
        r"contractor", r"zuwendungsempf", r"antragsteller", r"beguenstig",
        r"unternehmen", r"company", r"entity", r"organisation", r"organization",
        r"recipient", r"beneficiar", r"undertaking", r"subject.*name",
        r"entity.*name", r"beneficiary.*name", r"company.*name", r"name$",
        r"förderempf", r"empf.*name", r"leistungsempf", r"firma", r"name.*firma",
    ],
    "projekt": [
        r"^op_?name$",
        r"bezeichnung$", r"bezeichnung.*vorhaben", r"operation.*name",
        r"projekt", r"vorhaben", r"massnahme", r"maßnahme", r"title",
        r"subject", r"measure", r"operation", r"project", r"scheme",
        r"aid.*measure", r"programme?", r"program",
    ],
    "kosten": [
        r"^op_?total_?cost$",
        r"förderf.*gesamt.*kosten", r"total.*cost", r"gesamtkosten",
        r"fördersumme", r"zuwendung.*betrag", r"bruttobetrag",
        r"betrag", r"summe", r"zuschuss", r"eu.*beteiligung", r"eu.*beitrag",
        r"amount", r"grant", r"funding", r"kofinanzierung", r"co.*finanz",
        r"total.*eligible", r"eligible.*cost", r"public.*support", r"union.*support",
    ],
    "standort": [
        r"^op_?geo_?location$",
        r"standortindikator", r"standort.*plz", r"standort.*ort",  # Spezifischste zuerst
        r"investitionsort",
        r"ort.*begünstig", r"ort.*vorhaben",
        r"location.*indicator", r"geolocation", r"geolokalisierung",
        r"standort", r"location", r"adresse", r"plz.*ort", r"anschrift", r"sitz",
        r"address", r"city", r"municipality",
        r"einsatzort", r"betriebsst", r"verwaltungssitz", r"firmensitz",
        r"hauptsitz", r"werk.*ort", r"street|straße|strasse", r"postanschrift",
        r"nuts",  # NUTS-Spalte als letzter Fallback
    ],
    # Separate PLZ- und Ort-Spalten (werden bei Bedarf kombiniert)
    "plz": [r"^plz\b", r"postleitzahl", r"postal.*code", r"zip", r"postcode"],
    "ort": [
        r"^ort$", r"^stadt$", r"^gemeinde$", r"^kommune$",
        r"ortschaft", r"wohnort", r"sitz.*ort", r"ort.*stadt",
        r"town", r"city", r"municipality", r"gemeindename",
    ],
    "landkreis": [
        r"landkreis", r"kreis", r"^region$",
        r"bezirk", r"verwaltungsbezirk", r"distrikt", r"district",
        r"kreis.*frei", r"regierungsbezirk", r"gebiet",
    ],
    "sz": [
        r"spezifisches.*ziel", r"specific.*objective", r"priorit",
        r"interventions.*bereich", r"intervention.*field",
    ],
    "beschreibung": [
        r"^op_?purp_?achi$",
        r"zweck", r"errungenschaft", r"purpose", r"achievement",
        r"beschreibung", r"description", r"reason", r"summary",
        r"remarks", r"gegenstand", r"comment", r"objective", r"instrument",
        r"sector", r"legal.*basis", r"sanction.*reason",
    ],
    "aktenzeichen": [
        r"aktenzeichen", r"förderkennzeichen", r"foerderkennzeichen",
        r"kennzeichen", r"vorgangsnummer", r"reference", r"sa.*number",
        r"case.*number", r"operation.*id", r"project.*id", r"list.*id",
        r"ref.*no", r"notification.*number",
    ],
    "country": [r"country", r"land$", r"staat", r"member.*state", r"nationality", r"citizenship"],
    "status": [r"status", r"listing.*status", r"decision", r"phase", r"late", r"active"],
}


def _find_column(columns: list[str], role: str) -> str | None:
    """Findet die passende Spalte fuer eine Rolle (name, standort, etc.).
    Patterns frueher in der Liste haben hoehere Prioritaet.
    Bei mehreren Treffern fuer dasselbe Pattern wird die kuerzeste Spalte bevorzugt."""
    patterns = COLUMN_PATTERNS.get(role, [])
    for pattern in patterns:
        candidates = [col for col in columns if re.search(pattern, col, re.IGNORECASE)]
        if candidates:
            # Bei mehreren Treffern: kuerzeste Spalte bevorzugen (= spezifischster Match)
            return min(candidates, key=len)
    return None


def detect_columns(source: str) -> dict[str, str | None]:
    """
    Erkennt automatisch welche Spalten Name, Standort, Kosten etc. enthalten.
    Returns: {"name": "spaltenname", "standort": "spaltenname", ...}
    """
    from services.dataframe_service import _safe_table_name
    table_name = _safe_table_name(source)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :t ORDER BY ordinal_position
        """), {"t": table_name})
        columns = [r[0] for r in result]

    mapping = {}
    for role in COLUMN_PATTERNS:
        mapping[role] = _find_column(columns, role)

    return mapping


# ── Cache ─────────────────────────────────────────────────────────────────────

def _load_cache():
    global _cache
    try:
        path = Path(GEOCODE_CACHE)
        if path.exists():
            _cache = json.loads(path.read_text(encoding="utf-8"))
            log.info("Geocode-Cache geladen: %d Eintraege", len(_cache))
    except Exception as e:
        log.warning("Geocode-Cache nicht ladbar: %s", e)
        _cache = {}


def _save_cache():
    try:
        Path(GEOCODE_CACHE).write_text(
            json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning("Geocode-Cache nicht speicherbar: %s", e)


# ── Geocoding ─────────────────────────────────────────────────────────────────

def _parse_location(standort: str) -> tuple[str, str]:
    """
    Parst verschiedene Standort-Formate → (suchbegriff, land).
    Unterstuetzte Formate:
      - '63477 Maintal / Am Kreuzstein 85'
      - '63477 Maintal'
      - 'Frankfurt am Main'
      - 'Kassel, Hessen'
      - 'Landkreis Fulda, Hessen'
      - 'LK Schmalkalden-Meiningen'
      - 'Kreis Offenbach'
    """
    standort = standort.strip()
    if not standort:
        return ("", "")

    # Landkreis/Kreis-Prefix entfernen
    standort_clean = re.sub(
        r'^(?:Landkreis|LK|Kreis|Bezirk|Verwaltungsbezirk|Regierungsbezirk|Stadtkreis|SK)\s+',
        '', standort, flags=re.IGNORECASE
    ).strip()

    # PLZ + Ort extrahieren (Formate: "63477 Maintal", "10625 - Berlin", "63477 Maintal / Straße")
    m = re.match(r"(\d{4,5})\s*[-–]?\s*(.+)", standort_clean)
    if m:
        plz = m.group(1)
        rest = m.group(2).lstrip("- –").strip()
        # Ort vor '/' oder ',' nehmen (Straße/Ortsteil abschneiden)
        # NICHT auf '-' splitten wenn es der Stadtname selbst ist (z.B. "Frankfurt-Höchst")
        ort = re.split(r"\s*/\s*|\s*,\s*", rest)[0].strip()
        if ort:
            return (f"{plz} {ort}", "Deutschland")

    # NUTS-Code erkennen (z.B. "DE714" → ignorieren, nur Ort suchen)
    nuts_match = re.match(r'^DE[0-9A-G][0-9A-Z]{1,2}\s*(.*)', standort_clean)
    if nuts_match and nuts_match.group(1):
        standort_clean = nuts_match.group(1).strip()

    # Kein PLZ — Ort direkt, Komma-Suffix (Bundesland) entfernen fuer Suche
    ort = re.split(
        r"\s*/\s*|\s*,\s*(?:Deutschland|Germany|Hessen|Bayern|Sachsen|Brandenburg|NRW"
        r"|Niedersachsen|Thüringen|Sachsen-Anhalt|Mecklenburg-Vorpommern"
        r"|Baden-Württemberg|Rheinland-Pfalz|Schleswig-Holstein|Saarland"
        r"|Berlin|Hamburg|Bremen)\s*$",
        standort_clean, flags=re.IGNORECASE
    )[0].strip()

    if not ort:
        ort = standort_clean

    return (ort, "Deutschland")


def geocode_single(standort: str) -> dict | None:
    """
    Geocodiert einen einzelnen Standort.
    Gibt {lat, lon, display_name} oder None zurueck.
    """
    global _last_request_time

    if not _cache:
        _load_cache()

    cache_key = standort.strip().lower()
    if cache_key in _cache:
        return _cache[cache_key]

    search_term, country = _parse_location(standort)
    if not search_term:
        return None

    # Fallback: Wenn "PLZ Ort" nicht im Cache, versuche nur "Ort"
    # z.B. "10625 Berlin" → fallback auf "berlin"
    search_lower = search_term.strip().lower()
    if search_lower != cache_key and search_lower in _cache:
        result = _cache[search_lower]
        _cache[cache_key] = result  # Cache auch unter Original-Key
        return result
    ort_only = re.sub(r'^\d{4,5}\s*', '', search_lower).strip()
    if ort_only and ort_only != search_lower and ort_only in _cache:
        result = _cache[ort_only]
        _cache[cache_key] = result  # Cache auch unter Original-Key
        return result

    if not ALLOW_REMOTE_GEOCODING:
        return None

    # Rate-Limiting
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    try:
        _last_request_time = time.time()
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": f"{search_term}, {country}",
                "format": "json",
                "limit": 1,
                "countrycodes": "de",
            },
            headers={"User-Agent": "Auditworkshop-EFRE-Demo/1.0"},
            timeout=5,
        )
        results = r.json()
        if results:
            geo = {
                "lat": float(results[0]["lat"]),
                "lon": float(results[0]["lon"]),
                "display_name": results[0].get("display_name", ""),
            }
            _cache[cache_key] = geo
            _save_cache()
            return geo
    except Exception as e:
        log.warning("Geocoding fehlgeschlagen fuer '%s': %s", standort, e)

    _cache[cache_key] = None
    _save_cache()
    return None


# ── Karten-Daten ──────────────────────────────────────────────────────────────

def get_beneficiary_map_data(source: str) -> dict:
    """
    Liest Beguenstigte aus einer beliebigen DataFrame-Tabelle,
    erkennt Spalten automatisch und geocodiert die Standorte.

    Returns:
        {
            "count": int,
            "beneficiaries": [{name, projekt, kosten, standort, kategorie, lat, lon}],
            "columns_detected": {role: column_name},
            "source": str,
        }
    """
    from services.dataframe_service import _safe_table_name

    table_name = _safe_table_name(source)

    # Pruefen ob Tabelle existiert
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
            {"t": table_name},
        ).scalar()
        if not exists:
            return {"count": 0, "beneficiaries": [], "columns_detected": {}, "source": source}

    # Spalten automatisch erkennen
    col_map = detect_columns(source)

    name_col = col_map.get("name")
    standort_col = col_map.get("standort")
    kosten_col = col_map.get("kosten")
    projekt_col = col_map.get("projekt")
    sz_col = col_map.get("sz")
    plz_col = col_map.get("plz")
    ort_col = col_map.get("ort")
    landkreis_col = col_map.get("landkreis")

    # Standort-Spalte: direkt, oder PLZ+Ort kombiniert, oder nur Ort/Landkreis
    has_location = standort_col or ort_col or plz_col or landkreis_col
    if not has_location:
        return {
            "count": 0, "beneficiaries": [],
            "columns_detected": col_map, "source": source,
            "error": "Keine Standort-/Ort-/PLZ-Spalte erkannt. Verfügbare Spalten: " +
                     ", ".join(_get_columns(table_name)),
        }

    # SQL dynamisch zusammenbauen
    if standort_col:
        select_parts = [f'"{standort_col}" AS standort']
        where_clause = f'"{standort_col}" IS NOT NULL'
    elif plz_col and ort_col:
        # PLZ + Ort kombinieren → "PLZ Ort"
        select_parts = [f'CONCAT("{plz_col}", \' \', "{ort_col}") AS standort']
        where_clause = f'"{ort_col}" IS NOT NULL'
    elif ort_col:
        select_parts = [f'"{ort_col}" AS standort']
        where_clause = f'"{ort_col}" IS NOT NULL'
    elif landkreis_col:
        select_parts = [f'"{landkreis_col}" AS standort']
        where_clause = f'"{landkreis_col}" IS NOT NULL'
    else:
        select_parts = [f'"{plz_col}" AS standort']
        where_clause = f'"{plz_col}" IS NOT NULL'

    if name_col:
        select_parts.append(f'"{name_col}" AS name')
    if projekt_col:
        select_parts.append(f'"{projekt_col}" AS projekt')
    if kosten_col:
        select_parts.append(f'"{kosten_col}" AS kosten')
    if sz_col:
        select_parts.append(f'"{sz_col}" AS kategorie')

    sql = f'SELECT {", ".join(select_parts)} FROM "{table_name}" WHERE {where_clause}'

    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
        columns = list(conn.execute(text(sql)).keys()) if not rows else None

    if not _cache:
        _load_cache()

    results = []
    for row in rows:
        row_dict = dict(row._mapping)
        standort = str(row_dict.get("standort", "")).strip()
        if not standort:
            continue

        cache_key = standort.lower()
        if cache_key in _cache and _cache[cache_key] is not None:
            geo = _cache[cache_key]
        else:
            geo = geocode_single(standort)

        if geo:
            entry = {
                "standort": standort,
                "lat": geo["lat"],
                "lon": geo["lon"],
                "name": str(row_dict.get("name", "Unbekannt"))[:200],
                "projekt": str(row_dict.get("projekt", ""))[:300],
                "kosten": float(row_dict["kosten"]) if "kosten" in row_dict and row_dict["kosten"] is not None else 0,
                "kategorie": str(row_dict.get("kategorie", ""))[:50],
            }
            # NUTS-3 Zuordnung
            nuts_info = lookup_nuts(geo["lat"], geo["lon"])
            if nuts_info:
                entry["nuts3"] = nuts_info["nuts3"]
                entry["region"] = nuts_info["region"]
            results.append(entry)

    return {
        "count": len(results),
        "beneficiaries": results,
        "columns_detected": col_map,
        "source": source,
    }


def _get_columns(table_name: str) -> list[str]:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :t ORDER BY ordinal_position
        """), {"t": table_name})
        return [r[0] for r in result]
