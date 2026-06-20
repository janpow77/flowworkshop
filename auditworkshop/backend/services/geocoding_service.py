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
from services.country_profiles import (
    get_country_name,
    get_country_profile,
)

log = logging.getLogger(__name__)

_cache: dict[str, dict | None] = {}
_last_request_time = 0.0

# ── NUTS-3 Zuordnung ─────────────────────────────────────────────────────────

_nuts_data: dict | None = None


def _format_date_string(value: object) -> str:
    """Normalisiert Datumswerte aus XLSX/CSV auf 'YYYY-MM-DD' (oder Original
    bei nicht-parsbarem Format). Leere/None-Werte werden zu ''.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "null", "n/a"):
        return ""
    # Bereits ISO-Datum: nur den Datumsteil
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if iso_match:
        return iso_match.group(1)
    # Deutsches Datum DD.MM.YYYY
    de_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if de_match:
        d, m, y = de_match.groups()
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    # YYYY-MM (ohne Tag)
    ym_match = re.match(r"^(\d{4})-(\d{2})$", s)
    if ym_match:
        return f"{s}-01"
    # YYYY (nur Jahr)
    if re.match(r"^\d{4}$", s):
        return f"{s}-01-01"
    # Sonst: Roh-String, max 30 Zeichen
    return s[:30]


def _parse_cost_value(value: object) -> float:
    """Normalisiert Kostenwerte aus XLSX/CSV fuer Kartenantworten."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text_value = str(value).strip()
    if not text_value:
        return 0.0

    cleaned = text_value.replace("\xa0", " ").replace("EUR", "").replace("€", "")
    cleaned = cleaned.replace(" ", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


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
        # ISF/AMIF: "Org_Rechtliche Bezeichnung" ist die echte Begünstigten-Spalte
        r"^org_rechtliche", r"rechtliche.*bezeichnung", r"^leistungsempf",
        # "beneficiary" als Wort, NICHT "beneficiary_type" (= Typ-Spalte)
        r"^beneficiary$", r"beneficiary_name", r"beneficiar.*name",
        r"contractor", r"zuwendungsempf", r"antragsteller", r"beguenstig",
        r"unternehmen", r"company", r"entity", r"organisation", r"organization",
        r"recipient", r"undertaking", r"subject.*name",
        r"entity.*name", r"company.*name", r"name$",
        r"förderempf", r"empf.*name", r"firma", r"name.*firma",
        # Baden-Württemberg EFRE: PostgreSQL-Spalten-Limit (63 chars) hat
        # den langen englischen Header
        # „In the case of legal entities, the beneficiary's name; …"
        # auf "in_the_case_of_legal_entities_the_beneficiarys_and_in_the_case_"
        # gekürzt — keines der bisherigen Patterns trifft. Daher gezielt:
        r"^in_the_case_of_legal_entities", r"beneficiarys",
    ],
    "projekt": [
        r"^op_?name$",
        r"^projektname$",  # ISF/AMIF
        r"bezeichnung$", r"bezeichnung.*vorhaben", r"operation.*name",
        r"projekt", r"vorhaben", r"massnahme", r"maßnahme", r"title",
        r"subject", r"measure", r"operation", r"project", r"scheme",
        r"aid.*measure", r"programme?", r"program",
    ],
    # Gesamt-/Projektkosten (förderfähige Gesamtausgaben). Die EU-Anteils-
    # Patterns (eu.*beteiligung/eu.*beitrag/union.*support) wurden bewusst
    # in die separate Rolle `kosten_eu` ausgelagert — sonst summierte
    # dieselbe Auswertung je nach Header-Schreibweise mal die Gesamtkosten,
    # mal nur den EU-Kofinanzierungsanteil (typ. 40–60 % der Gesamtkosten).
    # `kosten` bleibt als generischer Fallback-Name erhalten und hat
    # Priorität auf die Gesamtgröße.
    "kosten": [
        r"^op_?total_?cost$",
        r"kofinanziert.*projekt.*kosten",
        r"co.?financed.*project.*cost",
        r"förderf.*gesamt.*kosten",
        r"projekt.*kosten", r"gesamtkosten", r"gesamtausgaben", r"total.*cost",
        r"total.*eligible", r"eligible.*cost", r"förderf.*kosten",
        r"fördersumme", r"zuwendung.*betrag", r"bruttobetrag",
        r"betrag", r"summe", r"zuschuss",
        r"amount", r"grant",
        r"funding(?!.*rate)(?!.*satz)(?!quote)",
        r"public.*support",
    ],
    # EU-Kofinanzierungsanteil (Unionsbeteiligung) — getrennt von den
    # Gesamtkosten geführt, damit Aggregate eine eindeutige semantische
    # Größe summieren. Wird in der zentralen Tabelle nach cost_eu_funding
    # geschrieben.
    "kosten_eu": [
        r"eu.*beteiligung", r"eu.*beitrag", r"union.*support",
        r"eu.*kofinanz", r"unionsbeteiligung", r"eu.*funding",
        # Generische (Ko-)Finanzierungsspalten bezeichnen i.d.R. den
        # Kofinanzierungsanteil, nicht die Gesamtkosten.
        r"kofinanzierung", r"co.*finanz",
    ],
    "standort": [
        r"^op_?geo_?location$",
        r"standortindikator", r"standort.*plz", r"standort.*ort",  # Spezifischste zuerst
        r"investitionsort",
        r"ort.*begünstig", r"ort.*vorhaben",
        r"location.*indicator", r"geolocation",
        r"standort", r"location", r"adresse", r"plz.*ort", r"anschrift", r"sitz",
        r"address", r"city", r"municipality",
        r"einsatzort", r"betriebsst", r"verwaltungssitz", r"firmensitz",
        r"hauptsitz", r"werk.*ort", r"street|straße|strasse", r"postanschrift",
        r"^coordinates?$",  # Bremen ESF: text-Adresse statt Lat/Lon
        r"oper_loc_geo",
        r"nuts",  # NUTS-Spalte als letzter Fallback
    ],
    # Separate PLZ- und Ort-Spalten (werden bei Bedarf kombiniert)
    "plz": [
        r"^plz\b", r"postleitzahl", r"postal.*code", r"zip", r"postcode",
        r"_plz_|_plz$", r"^geolokalisierung$",  # MV ESF: 5-stellige PLZ
    ],
    "ort": [
        r"^ort$", r"^stadt$", r"^gemeinde$", r"^kommune$",
        r"_ort_|_ort$", r"projekt.*ort", r"projektstandort_ort",
        r"ortschaft", r"wohnort", r"sitz.*ort", r"ort.*stadt",
        r"town", r"city", r"municipality", r"gemeindename",
    ],
    "landkreis": [
        r"landkreis", r"kreis", r"^region$",
        r"bezirk", r"verwaltungsbezirk", r"distrikt", r"district",
        r"kreis.*frei", r"regierungsbezirk", r"gebiet",
    ],
    "sz": [
        r"wirtschaftst", r"wirtschaftszweig", r"wirtschaftsbereich",
        r"branche", r"sektor", r"nace",
        r"art.*der.*intervention", r"interventionskategorie",
        r"interventions.*bereich", r"intervention.*field",
        r"spezifisches.*ziel", r"specific.*objective", r"priorit",
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
    "beginn": [
        r"datum.*beginn", r"datum.*beginns", r"beginn.*vorhabens",
        r"^beginn$", r"start.*date", r"^start$", r"datum.*start",
        r"projekt.*beginn", r"vorhaben.*beginn",
        r"^projekt_?von$",  # ISF/AMIF
    ],
    "ende": [
        r"datum.*abschluss", r"datum.*endes", r"datum.*ende",
        r"abschluss.*vorhabens", r"ende.*vorhabens",
        r"end.*date.*operation", r"completion.*date",
        r"^ende$", r"^abschluss$", r"^end_date$", r"^end$",
        r"^projekt_?bis$",  # ISF/AMIF
        r"end_date", r"end.*date",
        r"voraussichtlich.*abschluss", r"voraussichtlich.*ende",
        r"projekt.*ende", r"projekt.*abschluss",
    ],
    "latitude": [r"^lat$", r"^latitude$", r"^breitengrad$", r"breitengrad", r"^y_?coord", r"y_?wgs"],
    "longitude": [r"^lon$", r"^lng$", r"^longitude$", r"^laengengrad$", r"^längengrad$", r"laengengrad", r"längengrad", r"^x_?coord", r"x_?wgs"],
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


def _matches_role_label(value: object, role: str) -> bool:
    text_value = str(value or "").strip()
    if not text_value or len(text_value) > 140:
        return False
    if role == "kosten" and re.search(r"(instrument|rate|satz|quote|percent|proz|%)", text_value, re.IGNORECASE):
        return False
    return any(re.search(pattern, text_value, re.IGNORECASE) for pattern in COLUMN_PATTERNS.get(role, []))


HEADER_LABEL_PATTERNS: dict[str, list[str]] = {
    "name": [
        r"^name$", r"name.*begünstig", r"^beneficiary$", r"beneficiar.*name", r"zuwendungsempf",
    ],
    "projekt": [
        r"operation.*name", r"bezeichnung.*vorhaben", r"projektname", r"^operation$",
    ],
    "kosten": [
        r"total.*cost", r"gesamtkosten", r"förderfähige.*kosten", r"project.*cost",
    ],
    "standort": [
        r"standortindikator", r"location[\s\S]*indicator", r"geoloc", r"investitionsort",
    ],
    "plz": [
        r"postleitzahl", r"postcode", r"postal.*code", r"^plz$",
    ],
    "ort": [
        r"^ort$", r"location$", r"project.*location",
    ],
    "landkreis": [
        r"bezirk", r"district", r"landkreis",
    ],
    "sz": [
        r"intervention.*field", r"interven.?tion.*type", r"interventionsbereich", r"art.*intervention",
    ],
    "beschreibung": [
        r"purpose", r"achievement", r"zweck", r"errungenschaft", r"summary",
    ],
    "aktenzeichen": [
        r"operation.*id", r"projektnummer", r"aktenzeichen",
    ],
    "country": [
        r"^country$", r"^land$",
    ],
    "beginn": [
        r"start.*date", r"datum.*beginn", r"projektbeginn",
    ],
    "ende": [
        r"end.*date", r"datum.*ende", r"datum.*abschluss", r"projektende",
    ],
}


def _header_label_matches_role(value: object, role: str) -> bool:
    text_value = str(value or "").strip()
    if not text_value or len(text_value) > 90:
        return False
    if re.search(r"\d{4}-\d{2}-\d{2}|\d+[,.]\d+", text_value):
        return False
    return any(re.search(pattern, text_value, re.IGNORECASE) for pattern in HEADER_LABEL_PATTERNS.get(role, []))


def _infer_columns_from_embedded_header_rows(table_name: str, columns: list[str]) -> dict[str, str]:
    """Erkennt Dateien, bei denen die eigentlichen Header als erste Datenzeile
    importiert wurden. Das passiert bei einigen Transparenzlisten mit
    mehrzeiligen Titelbloecken vor der eigentlichen Tabellenkopfzeile.
    """
    inferred: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT 5')).fetchall()
    except Exception:
        return inferred

    for row in rows:
        row_dict = dict(row._mapping)
        label_hits = sum(
            1
            for value in row_dict.values()
            if any(_header_label_matches_role(value, role) for role in HEADER_LABEL_PATTERNS)
        )
        if label_hits < 2:
            continue
        for col in columns:
            value = row_dict.get(col)
            for role in HEADER_LABEL_PATTERNS:
                if role in inferred:
                    continue
                if _header_label_matches_role(value, role):
                    inferred[role] = col
    return inferred


def _is_likely_rate_column(column_name: str | None) -> bool:
    if not column_name:
        return False
    return bool(re.search(r"(satz|rate|quote|percent|proz|%)", column_name, re.IGNORECASE))


def _looks_like_embedded_header_row(row_dict: dict) -> bool:
    label_hits = 0
    for value in row_dict.values():
        if any(_header_label_matches_role(value, role) for role in HEADER_LABEL_PATTERNS):
            label_hits += 1
    return label_hits >= 2


def detect_columns(source: str) -> dict[str, str | None]:
    """
    Erkennt automatisch welche Spalten Name, Standort, Kosten etc. enthalten.
    Returns: {"name": "spaltenname", "standort": "spaltenname", ...}

    Wenn Spaltennamen-Patterns versagen (z. B. Brandenburg ESF mit
    verstümmelten Headern), wird zusätzlich der INHALT der Spalten
    auf NUTS-3-Codes, PLZ und Stadtnamen geprüft.
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

    embedded_header_mapping = _infer_columns_from_embedded_header_rows(table_name, columns)
    for role, col in embedded_header_mapping.items():
        if not col:
            continue
        if not mapping.get(role):
            mapping[role] = col
        elif role == "kosten" and _is_likely_rate_column(mapping.get(role)):
            mapping[role] = col

    # Inhalts-basierter Fallback: wenn KEINE Standort-Information per
    # Spaltennamen erkannt wurde (Brandenburg ESF, NRW ESF mit verstümmelten
    # Spalten-Headern), scanne ALLE Text-Spalten und versuche, die Rolle
    # aus dem Inhalt zu erschliessen. Bestehende Zuordnungen zu schwachen
    # Rollen (projekt, beschreibung) duerfen ueberschrieben werden, wenn
    # die Inhaltsanalyse eindeutig Standort-Pattern findet.
    has_location = any(mapping.get(k) for k in ("standort", "ort", "plz", "landkreis", "latitude"))
    if not has_location:
        critical_used = {
            mapping.get(k) for k in ("name", "kosten", "latitude", "longitude")
            if mapping.get(k)
        }
        candidates = [c for c in columns if c not in critical_used]
        if candidates:
            inferred = _infer_location_columns_by_content(table_name, candidates)
            for role, col in inferred.items():
                if not mapping.get(role):
                    mapping[role] = col
                # Overwrite weak roles, falls dieselbe Spalte dort steht
                for weak in ("projekt", "beschreibung", "sz", "aktenzeichen"):
                    if mapping.get(weak) == col:
                        mapping[weak] = None

    return mapping


def _infer_location_columns_by_content(
    table_name: str, candidates: list[str],
) -> dict[str, str]:
    """Prüft den Inhalt der Spalten und ordnet sie heuristisch
    Standort-Rollen zu (nuts→standort, plz, ort)."""
    result: dict[str, str] = {}
    nuts_re = re.compile(r"^DE[A-Z0-9]{1,3}$")
    plz_re = re.compile(r"^\d{4,5}$")
    _build_city_index("de")  # lazy load
    cities = _CITY_INDEX.get("de", {})
    try:
        with engine.connect() as conn:
            for col in candidates:
                rows = conn.execute(
                    text(f'SELECT DISTINCT "{col}" FROM "{table_name}" '
                         f'WHERE "{col}" IS NOT NULL LIMIT 30')
                ).fetchall()
                values = [str(r[0]).strip() for r in rows if r[0]]
                values = [v for v in values if v and len(v) < 80]
                if not values:
                    continue
                nuts_hits = sum(1 for v in values if nuts_re.match(v.upper()))
                plz_hits = sum(1 for v in values if plz_re.match(v))
                city_hits = sum(1 for v in values if v.casefold() in cities)
                total = len(values)
                # Mehrheits-Schwelle: ≥ 50 % der Werte passen
                if nuts_hits / total >= 0.5 and "standort" not in result:
                    result["standort"] = col
                elif plz_hits / total >= 0.5 and "plz" not in result:
                    result["plz"] = col
                elif city_hits / total >= 0.3 and "ort" not in result:
                    result["ort"] = col
    except Exception:
        log.exception("Inhalts-basierte Spaltenerkennung fehlgeschlagen")
    return result


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


# ── Offline PLZ-Datenbank (DE/AT) ────────────────────────────────────────────
# Quelle: GeoNames postal codes (CC-BY 4.0). Pro PLZ Hauptort + Koordinaten.
_PLZ_DB: dict[str, dict[str, dict]] = {}


def _load_plz_db() -> None:
    if _PLZ_DB:
        return
    import os
    base = Path(os.environ.get("PLZ_DB_DIR", "/app/data"))
    for cc, fname in (("de", "plz_de.json"), ("at", "plz_at.json")):
        path = base / fname
        try:
            if path.exists():
                _PLZ_DB[cc] = json.loads(path.read_text(encoding="utf-8"))
                log.info("PLZ-DB %s geladen: %d Eintraege", cc.upper(), len(_PLZ_DB[cc]))
        except Exception as e:
            log.warning("PLZ-DB %s nicht ladbar: %s", cc, e)
            _PLZ_DB[cc] = {}


def lookup_plz(plz: str, country_code: str | None = None) -> dict | None:
    """Sucht PLZ in der offline GeoNames-DB. Gibt {ort, bundesland, lat, lon}
    zurueck oder None.

    Akzeptiert auch zusaetzliche Schreibweisen: "01067 Dresden" → 01067,
    "1010" (AT, 4-stellig), "7310" (DE, fuehrende Null in Excel verloren) → 07310.
    """
    if not plz:
        return None
    _load_plz_db()
    cc = (country_code or "DE").lower()
    db = _PLZ_DB.get(cc, {})
    plz_str = str(plz).strip()
    if plz_str in db:
        return db[plz_str]
    # DE-PLZ sind 5-stellig. Excel/CSV schneidet fuehrende Nullen oft ab
    # ("07310" → "7310"). Pad auf 5 Stellen wenn nur 4 Stellen vorliegen.
    if cc == "de" and plz_str.isdigit() and len(plz_str) == 4:
        padded = "0" + plz_str
        if padded in db:
            return db[padded]
    # AT-PLZ haben fuehrende Null nicht — z. B. "1010" → key "1010"
    plz_str_no_pad = plz_str.lstrip("0")
    if plz_str_no_pad in db:
        return db[plz_str_no_pad]
    return None


# Invertierter Index: Stadt-Name → erste passende PLZ-Eintrag (lazy)
_CITY_INDEX: dict[str, dict[str, dict]] = {}


def _build_city_index(country_code: str) -> dict[str, dict]:
    cc = country_code.lower()
    if cc in _CITY_INDEX:
        return _CITY_INDEX[cc]
    _load_plz_db()
    db = _PLZ_DB.get(cc, {})
    idx: dict[str, dict] = {}
    for plz, entry in db.items():
        ort = (entry.get("ort") or "").strip()
        if not ort:
            continue
        key = ort.casefold()
        if key not in idx:
            idx[key] = {**entry, "plz": plz}
    _CITY_INDEX[cc] = idx
    return idx


def lookup_city(name: str, country_code: str | None = None) -> dict | None:
    """Sucht einen Stadt-/Ortsnamen in der PLZ-DB."""
    if not name:
        return None
    cc = (country_code or "DE").lower()
    idx = _build_city_index(cc)
    key = name.strip().casefold()
    if key in idx:
        return idx[key]
    # Heuristik: laeufige Suffixe entfernen ("am Main", ", Kreisfreie Stadt", ...)
    cleaned = re.sub(r",.*$", "", key).strip()
    cleaned = re.sub(r"\s+(am main|am rhein|kreisfreie stadt|stadt|landkreis)\s*$", "", cleaned).strip()
    if cleaned in idx:
        return idx[cleaned]
    return None


def _extract_plz(standort: str) -> str | None:
    """Extrahiert die erste 4-5-stellige PLZ aus dem Standort-String."""
    if not standort:
        return None
    m = re.search(r"\b(\d{4,5})\b", standort)
    return m.group(1) if m else None


# ── NUTS-3-Lookup (DE) ───────────────────────────────────────────────────────
# nuts_de.json ist eine vorhandene Datei mit NUTS-3-Codes (z. B. DE40B,
# DE803) → {name, type, bundesland, lat, lon}.
def _load_nuts_db() -> dict:
    global _nuts_data
    if _nuts_data is not None:
        return _nuts_data
    import os
    base = Path(os.environ.get("NUTS_DB_DIR", "/app/data"))
    path = base / "nuts_de.json"
    try:
        if path.exists():
            _nuts_data = json.loads(path.read_text(encoding="utf-8"))
            log.info("NUTS-DB geladen: %d Eintraege", len(_nuts_data))
        else:
            _nuts_data = {}
    except Exception as e:
        log.warning("NUTS-DB nicht ladbar: %s", e)
        _nuts_data = {}
    return _nuts_data


def lookup_nuts_code(code: str) -> dict | None:
    """Sucht einen NUTS-3-Code in nuts_de.json. Akzeptiert auch NUTS-2 mit
    Fallback auf den ersten passenden NUTS-3-Eintrag (Bundesland-Mitte).
    """
    if not code:
        return None
    db = _load_nuts_db()
    code = code.strip().upper()
    # Direkter Treffer
    if code in db:
        e = db[code]
        return {"lat": e["lat"], "lon": e["lon"], "ort": e.get("name") or code,
                "bundesland": e.get("bundesland", "")}
    # NUTS-2-Code (z. B. DE40 = Brandenburg) → ersten Sub-Eintrag nehmen
    if len(code) == 4:
        children = [v for k, v in db.items() if k.startswith(code) and len(k) > 4]
        if children:
            # Mittelwert aus allen Sub-Regionen
            lat = sum(c["lat"] for c in children) / len(children)
            lon = sum(c["lon"] for c in children) / len(children)
            bl = children[0].get("bundesland", "")
            return {"lat": round(lat, 4), "lon": round(lon, 4),
                    "ort": f"{bl} (NUTS-2 {code})", "bundesland": bl}
    return None


_NUTS_PATTERN = re.compile(r"^DE[A-Z0-9]{1,3}$")


def _extract_nuts(standort: str) -> str | None:
    """Erkennt NUTS-3-Codes (DE-Präfix + 1-3 alphanumerische Zeichen)."""
    if not standort:
        return None
    s = standort.strip().upper()
    if _NUTS_PATTERN.match(s):
        return s
    # Auch in Klartext-Listen wie "DEB11 : DE - Rheinland-Pfalz - Koblenz - ..."
    m = re.match(r"^(DE[A-Z0-9]{1,3})\b", s)
    return m.group(1) if m else None


def _extract_city_candidates(standort: str) -> list[str]:
    """Extrahiert potenzielle Stadt-Namen aus dem Standort-String.

    Heuristisch: alle Wort-Sequenzen mit Großbuchstabe-Anfang, getrennt
    durch Komma/Leerzeichen. Funktioniert für "Legienstraße 40, Kiel"
    sowie "DEB11 : DE - Rheinland-Pfalz - Koblenz - Koblenz, Kreisfreie Stadt".
    """
    if not standort:
        return []
    # Sammle alle ", X" und "- X" Komponenten plus letzte Komponente
    parts = re.split(r"[,;\-/|]", standort)
    candidates: list[str] = []
    for part in parts:
        token = part.strip()
        if not token or len(token) < 3:
            continue
        # Erste Großbuchstaben-Sequenz herausnehmen
        m = re.search(r"\b([A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\-]{2,})\b", token)
        if m:
            candidates.append(m.group(1))
    return candidates


def _save_cache():
    try:
        Path(GEOCODE_CACHE).write_text(
            json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning("Geocode-Cache nicht speicherbar: %s", e)


# ── Geocoding ─────────────────────────────────────────────────────────────────

def _parse_location(standort: str, country_code: str | None = None) -> tuple[str, str]:
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
      - '1010 Wien' / 'Wien, Österreich' (mit country_code='AT')
    """
    cc = (country_code or "DE").upper()
    country_label = get_country_name(cc) or "Deutschland"
    profile = get_country_profile(cc)
    region_aliases = []
    if profile:
        for region in profile.get("regions", []):
            region_aliases.append(region)
            region_aliases.append(region.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue"))
        region_aliases.extend(profile.get("aliases", []))

    standort = standort.strip()
    if not standort:
        return ("", "")

    # Landkreis/Kreis-Prefix entfernen (DE/AT-relevante Begriffe)
    standort_clean = re.sub(
        r'^(?:Landkreis|LK|Kreis|Bezirk|Verwaltungsbezirk|Regierungsbezirk|Stadtkreis|SK|Politischer Bezirk)\s+',
        '', standort, flags=re.IGNORECASE
    ).strip()

    # PLZ + Ort extrahieren (DE: 5-stellig, AT: 4-stellig)
    m = re.match(r"(\d{4,5})\s*[-–]?\s*(.+)", standort_clean)
    if m:
        plz = m.group(1)
        rest = m.group(2).lstrip("- –").strip()
        ort = re.split(r"\s*/\s*|\s*,\s*", rest)[0].strip()
        if ort:
            return (f"{plz} {ort}", country_label)

    # DE-NUTS-Code nur fuer DE entfernen
    if cc == "DE":
        nuts_match = re.match(r'^DE[0-9A-G][0-9A-Z]{1,2}\s*(.*)', standort_clean)
        if nuts_match and nuts_match.group(1):
            standort_clean = nuts_match.group(1).strip()
    elif cc == "AT":
        # AT-NUTS-Codes (AT11..AT34) am Anfang entfernen
        nuts_match = re.match(r'^AT[0-9]{1,3}\s*(.*)', standort_clean)
        if nuts_match and nuts_match.group(1):
            standort_clean = nuts_match.group(1).strip()

    # Bundesland-/Land-Suffix nach Komma entfernen
    suffix_alternatives = [re.escape(alias) for alias in region_aliases if alias]
    suffix_alternatives.extend([re.escape(country_label), re.escape(cc)])
    suffix_pattern = (
        r"\s*/\s*|\s*,\s*(?:" + "|".join(suffix_alternatives) + r")\s*$"
        if suffix_alternatives
        else r"\s*/\s*"
    )
    ort = re.split(suffix_pattern, standort_clean, flags=re.IGNORECASE)[0].strip()

    if not ort:
        ort = standort_clean

    return (ort, country_label)


def geocode_single(standort: str, country_code: str | None = None) -> dict | None:
    """
    Geocodiert einen einzelnen Standort.
    Gibt {lat, lon, display_name} oder None zurueck.
    """
    global _last_request_time

    if not _cache:
        _load_cache()

    cc = (country_code or "DE").upper()
    profile = get_country_profile(cc)
    nominatim_country = (profile or {}).get("nominatim_countrycode", "de")

    base_key = standort.strip().lower()
    cache_key = f"{cc.lower()}::{base_key}"

    # Cache: zuerst landesspezifisch, dann legacy ohne Praefix
    if cache_key in _cache and _cache[cache_key]:
        return _cache[cache_key]
    if cc == "DE" and base_key in _cache and _cache[base_key]:
        return _cache[base_key]

    search_term, country = _parse_location(standort, country_code=cc)
    if not search_term:
        return None

    # Fallback: Wenn "PLZ Ort" nicht im Cache, versuche nur "Ort"
    search_lower = search_term.strip().lower()
    fallback_key = f"{cc.lower()}::{search_lower}"
    if fallback_key in _cache and _cache[fallback_key]:
        _cache[cache_key] = _cache[fallback_key]
        return _cache[cache_key]
    ort_only = re.sub(r'^\d{4,5}\s*', '', search_lower).strip()
    ort_key = f"{cc.lower()}::{ort_only}" if ort_only else None
    if ort_key and ort_key in _cache and _cache[ort_key]:
        _cache[cache_key] = _cache[ort_key]
        return _cache[cache_key]

    # NUTS-3-Lookup (DE-spezifisch) — fuer Quellen, die nur den NUTS-Code
    # statt PLZ liefern (z. B. Brandenburg ESF "DE40B", Thueringen ESF "DEG0F").
    if cc == "DE":
        nuts_code = _extract_nuts(standort)
        if nuts_code:
            nuts_hit = lookup_nuts_code(nuts_code)
            if nuts_hit:
                geo = {
                    "lat": nuts_hit["lat"],
                    "lon": nuts_hit["lon"],
                    "display_name": (
                        f"{nuts_hit['ort']}, {nuts_hit['bundesland']}, "
                        f"{get_country_name('DE') or 'Deutschland'}"
                    ),
                    "source": "nuts-db",
                }
                _cache[cache_key] = geo
                return geo

    # Offline PLZ-Lookup als Fallback (greift auch ohne Internet)
    plz = _extract_plz(standort)
    if plz:
        plz_hit = lookup_plz(plz, country_code=cc)
        if plz_hit:
            geo = {
                "lat": plz_hit["lat"],
                "lon": plz_hit["lon"],
                "display_name": (
                    f"{plz} {plz_hit['ort']}, {plz_hit['bundesland']}, "
                    f"{get_country_name(cc) or country}"
                ),
                "source": "plz-db",
            }
            _cache[cache_key] = geo
            return geo

    # Stadt-/Ortsname-Lookup als zweiter Fallback (z. B. "..., Kiel" oder
    # "DEB11 : DE - Rheinland-Pfalz - Koblenz - Koblenz, Kreisfreie Stadt")
    for candidate in _extract_city_candidates(standort):
        city_hit = lookup_city(candidate, country_code=cc)
        if city_hit:
            geo = {
                "lat": city_hit["lat"],
                "lon": city_hit["lon"],
                "display_name": (
                    f"{city_hit.get('plz', '')} {city_hit['ort']}, "
                    f"{city_hit['bundesland']}, {get_country_name(cc) or country}"
                ).strip(),
                "source": "city-db",
            }
            _cache[cache_key] = geo
            return geo

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
                "countrycodes": nominatim_country,
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
        log.warning("Geocoding fehlgeschlagen fuer '%s' (cc=%s): %s", standort, cc, e)

    _cache[cache_key] = None
    _save_cache()
    return None


# ── Karten-Daten ──────────────────────────────────────────────────────────────

def get_beneficiary_map_data(source: str, country_code: str | None = None) -> dict:
    """
    Liest Beguenstigte aus einer beliebigen DataFrame-Tabelle,
    erkennt Spalten automatisch und geocodiert die Standorte.

    Wenn die Tabelle latitude/longitude-Spalten enthaelt, werden diese
    direkt genutzt und es wird nicht erneut geocodiert. country_code
    steuert das Nominatim-Verhalten (DE/AT) und schaltet die NUTS-3
    Zuordnung (nur DE).
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
    # Priorität: Gesamtkosten (kosten) vor EU-Anteil (kosten_eu) — sonst
    # weist die Karte je nach Header-Schreibweise mal die Gesamtkosten,
    # mal nur den Unionsanteil als „kosten" aus.
    kosten_col = col_map.get("kosten")
    kosten_metric = "Gesamtkosten" if kosten_col else None
    if not kosten_col:
        kosten_col = col_map.get("kosten_eu")
        if kosten_col:
            kosten_metric = "EU-Anteil"
    projekt_col = col_map.get("projekt")
    sz_col = col_map.get("sz")
    plz_col = col_map.get("plz")
    ort_col = col_map.get("ort")
    landkreis_col = col_map.get("landkreis")
    lat_col = col_map.get("latitude")
    lon_col = col_map.get("longitude")
    beginn_col = col_map.get("beginn")
    ende_col = col_map.get("ende")
    has_coordinates = bool(lat_col and lon_col)

    # Wenn die Standort-Spalte effektiv nur die PLZ ist (z.B. AT-EFRE
    # `projektstandort_plz`) und es eine separate Ort-Spalte gibt, verwenden
    # wir lieber den kombinierten "PLZ Ort"-Pfad — Nominatim braucht den Ort.
    if standort_col and standort_col == plz_col and ort_col:
        standort_col = None

    # Wenn die Standort-Spalte nur NUTS-Codes enthält (z.B. "DE300", "DEB11")
    # ODER nur sehr wenige unterschiedliche Werte hat (= ganzes Bundesland
    # statt konkretem Standort), ignorieren wenn PLZ verfuegbar ist.
    if standort_col and (plz_col or ort_col):
        try:
            with engine.connect() as conn:
                samples = conn.execute(
                    text(f'SELECT DISTINCT "{standort_col}" FROM "{table_name}" '
                         f'WHERE "{standort_col}" IS NOT NULL LIMIT 20')
                ).fetchall()
            sample_values = [str(r[0]).strip() for r in samples if r[0]]
            unique_count = len(set(v.casefold() for v in sample_values))
            looks_like_nuts = bool(sample_values) and all(
                re.fullmatch(r"[A-Z]{2}[A-Z0-9]{1,3}", v) for v in sample_values
            )
            if unique_count <= 2 or looks_like_nuts:
                standort_col = None  # PLZ-Pfad bevorzugen
        except Exception:
            pass

    # Standort-Spalte: direkt, oder PLZ+Ort kombiniert, oder nur Ort/Landkreis
    has_location = standort_col or ort_col or plz_col or landkreis_col or has_coordinates
    if not has_location:
        return {
            "count": 0, "beneficiaries": [],
            "columns_detected": col_map, "source": source,
            "error": "Keine Standort-/Ort-/PLZ-Spalte erkannt. Verfügbare Spalten: " +
                     ", ".join(_get_columns(table_name)),
        }

    # SQL dynamisch zusammenbauen
    select_parts: list[str] = []
    if standort_col:
        select_parts.append(f'"{standort_col}" AS standort')
        where_clauses = [f'"{standort_col}" IS NOT NULL']
    elif plz_col and ort_col:
        # PLZ + Ort kombinieren → "PLZ Ort"
        select_parts.append(f'CONCAT("{plz_col}", \' \', "{ort_col}") AS standort')
        where_clauses = [f'"{ort_col}" IS NOT NULL']
    elif ort_col:
        select_parts.append(f'"{ort_col}" AS standort')
        where_clauses = [f'"{ort_col}" IS NOT NULL']
    elif plz_col:
        select_parts.append(f'"{plz_col}" AS standort')
        where_clauses = [f'"{plz_col}" IS NOT NULL']
    elif landkreis_col:
        select_parts.append(f'"{landkreis_col}" AS standort')
        where_clauses = [f'"{landkreis_col}" IS NOT NULL']
    else:
        # Nur lat/lon vorhanden -> Standort als Fallback aus Koordinaten zusammensetzen
        select_parts.append("'' AS standort")
        where_clauses = []

    if has_coordinates:
        select_parts.append(f'"{lat_col}" AS _lat')
        select_parts.append(f'"{lon_col}" AS _lon')
        where_clauses.append(f'"{lat_col}" IS NOT NULL AND "{lon_col}" IS NOT NULL')
    if name_col:
        select_parts.append(f'"{name_col}" AS name')
    if projekt_col:
        select_parts.append(f'"{projekt_col}" AS projekt')
    if kosten_col:
        select_parts.append(f'"{kosten_col}" AS kosten')
    if sz_col:
        select_parts.append(f'"{sz_col}" AS kategorie')
    if beginn_col:
        select_parts.append(f'"{beginn_col}"::text AS beginn')
    if ende_col:
        select_parts.append(f'"{ende_col}"::text AS ende')

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    sql = f'SELECT {", ".join(select_parts)} FROM "{table_name}" WHERE {where_sql}'

    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()

    if not _cache:
        _load_cache()

    cc = (country_code or "DE").upper()
    results = []
    for row in rows:
        row_dict = dict(row._mapping)
        if _looks_like_embedded_header_row(row_dict):
            continue
        standort = str(row_dict.get("standort", "") or "").strip()

        geo: dict | None = None
        if has_coordinates:
            try:
                lat_val = float(row_dict.get("_lat"))
                lon_val = float(row_dict.get("_lon"))
                geo = {"lat": lat_val, "lon": lon_val, "display_name": standort}
                if not standort:
                    standort = f"{lat_val:.4f}, {lon_val:.4f}"
            except (TypeError, ValueError):
                geo = None

        if geo is None:
            if not standort:
                continue
            geo = geocode_single(standort, country_code=cc)

        if geo:
            beginn_raw = row_dict.get("beginn")
            ende_raw = row_dict.get("ende")
            entry = {
                "standort": standort,
                "lat": geo["lat"],
                "lon": geo["lon"],
                "name": str(row_dict.get("name", "Unbekannt"))[:200],
                "projekt": str(row_dict.get("projekt", ""))[:300],
                "kosten": _parse_cost_value(row_dict.get("kosten")),
                "kategorie": str(row_dict.get("kategorie", ""))[:50],
                "beginn": _format_date_string(beginn_raw),
                "ende": _format_date_string(ende_raw),
            }
            # NUTS-3 Zuordnung nur fuer Deutschland (Datei nuts_de.json)
            if cc == "DE":
                nuts_info = lookup_nuts(geo["lat"], geo["lon"])
                if nuts_info:
                    entry["nuts3"] = nuts_info["nuts3"]
                    entry["region"] = nuts_info["region"]
            results.append(entry)

    return {
        "count": len(results),
        "beneficiaries": results,
        "columns_detected": col_map,
        "cost_metric_label": kosten_metric,
        "source": source,
        "country_code": cc,
        "country_name": get_country_name(cc),
    }


def _get_columns(table_name: str) -> list[str]:
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :t ORDER BY ordinal_position
        """), {"t": table_name})
        return [r[0] for r in result]
