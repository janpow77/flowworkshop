"""
flowworkshop · dataframe_service.py
Speichert XLSX/CSV als echte SQL-Tabellen in PostgreSQL.
Ermoeglicht SQL-Abfragen und Statistik-Aggregationen durch das LLM.

Tabellen werden als workshop_df_{source_name} gespeichert.
"""
from __future__ import annotations
import io
import logging
import re
from typing import Any

import pandas as pd
from sqlalchemy import text

from database import engine

log = logging.getLogger(__name__)

_LEGAL_SUFFIXES = [
    r"gmbh\s*&\s*co\.?\s*kgaa",
    r"gmbh\s*&\s*co\.?\s*kg",
    r"gmbh\s*&\s*co\.?\s*ohg",
    r"ag\s*&\s*co\.?\s*kg",
    r"ag\s*&\s*co\.?\s*kgaa",
    r"ug\s*\(haftungsbeschr[aä]nkt\)",
    r"ggmbh",
    r"gmbh",
    r"kgaa",
    r"kg",
    r"ohg",
    r"ug",
    r"ag",
    r"se",
    r"gbr",
    r"mbh",
    r"e\.?\s*v\.?",
    r"e\.?\s*g\.?",
    r"inc\.?",
    r"ltd\.?",
    r"s\.?a\.?",
]

_LEGAL_RE = re.compile(r"\b(?:" + "|".join(_LEGAL_SUFFIXES) + r")\s*$", re.IGNORECASE)

_SEARCH_STOP_WORDS = frozenset({
    "und", "der", "die", "das", "fuer", "für", "von", "den", "dem", "des",
    "am", "im", "an", "zu", "zur", "zum", "bei", "mit", "the", "and", "for",
    "gmbh", "ggmbh", "mbh", "ltd", "inc", "kgaa",
})

_REFERENCE_PROFILE_PATTERNS: dict[str, dict[str, list[str]]] = {
    "sanctions": {
        "name": [
            r"^name$", r"entity_?name", r"subject_?name", r"full_?name",
            r"organisation_?name", r"organization_?name", r"company_?name",
            r"person_?name", r"designation",
        ],
        "alias": [r"aliases?", r"also_?known", r"\baka\b", r"other_?names?"],
        "projekt": [r"sanction_?program", r"sanction_?programme", r"program", r"programme", r"list_?name", r"regime"],
        "beschreibung": [r"sanction_?reasons?", r"reasons?", r"grounds?", r"remarks?", r"comment", r"description", r"title"],
        "aktenzeichen": [r"list_?id", r"entity_?id", r"subject_?id", r"reference", r"regulation", r"decision", r"listing_?id", r"^id$"],
        "standort": [r"address", r"city", r"town", r"place_?of_?birth", r"birth_?place", r"jurisdiction"],
        "country": [r"country", r"citizenship", r"nationality", r"jurisdiction_?country"],
        "status": [r"listing_?status", r"sanction_?status", r"status", r"active", r"state"],
        "date": [r"listing_?date", r"date_?listed", r"effective_?date", r"start_?date", r"date"],
    },
    "tam": {
        "name": [
            r"beneficiary_?name", r"name_?of_?the_?beneficiary", r"undertaking",
            r"recipient_?name", r"company_?name", r"^beneficiary$",
        ],
        "projekt": [r"aid_?measure_?title", r"measure_?title", r"scheme_?title", r"aid_?scheme", r"title", r"measure", r"scheme"],
        "beschreibung": [r"objectives?", r"aid_?instrument", r"instrument", r"sector(_?nace)?", r"economic_?activity", r"beneficiary_?type", r"entrusted_?entity", r"remarks?"],
        "aktenzeichen": [r"sa_?number", r"ref_?no", r"reference_?number", r"national_?id", r"case_?number", r"measure_?id"],
        "standort": [r"region", r"city", r"address", r"postal", r"postcode", r"zip", r"location"],
        "country": [r"member_?state", r"country"],
        "status": [r"is_?late", r"late_?publication", r"delay", r"publication_?status", r"status"],
        "authority": [r"granting_?authority", r"awarding_?authority", r"authority", r"provider"],
        "amount": [r"aid_?element", r"nominal_?amount", r"gross_?grant", r"grant_?equivalent", r"amount", r"value"],
        "programme": [r"program(me)?", r"regime", r"objective"],
        "date": [r"date_?granted", r"grant_?date", r"published_?date", r"publication_?date", r"award_?date", r"date"],
    },
    "state_aid": {
        "name": [r"beneficiary_?name", r"recipient_?name", r"undertaking", r"company_?name", r"^beneficiary$", r"^name$"],
        "projekt": [r"aid_?measure_?title", r"measure_?title", r"scheme_?title", r"measure_?name", r"title", r"scheme"],
        "beschreibung": [r"objectives?", r"objective", r"aid_?instrument", r"instrument", r"legal_?basis", r"sector", r"activity", r"description", r"summary"],
        "aktenzeichen": [r"sa_?number", r"case_?number", r"measure_?id", r"reference_?number", r"notification_?number", r"^id$"],
        "standort": [r"region", r"city", r"address", r"postal", r"postcode", r"zip", r"location"],
        "country": [r"member_?state", r"country"],
        "status": [r"status", r"phase", r"decision"],
        "authority": [r"granting_?authority", r"awarding_?authority", r"authority", r"managing_?authority", r"provider"],
        "amount": [r"aid_?element", r"nominal_?amount", r"gross_?grant", r"amount", r"value", r"budget"],
        "programme": [r"program(me)?", r"fund", r"objective", r"priority"],
        "date": [r"date_?granted", r"grant_?date", r"published_?date", r"decision_?date", r"approval_?date", r"date"],
    },
    "cohesio": {
        "name": [r"beneficiary", r"final_?recipient", r"recipient_?name", r"company_?name", r"organisation", r"organization", r"undertaking", r"^name$"],
        "projekt": [r"operation_?name", r"operation_?title", r"project_?title", r"project_?name", r"title", r"operation"],
        "beschreibung": [r"program(me)?", r"fund", r"policy_?objective", r"intervention_?field", r"description", r"summary", r"theme", r"category"],
        "aktenzeichen": [r"operation_?id", r"project_?id", r"reference", r"cci", r"code", r"^id$"],
        "standort": [r"region", r"city", r"municipality", r"nuts", r"location"],
        "country": [r"country", r"member_?state"],
        "status": [r"implementation_?status", r"status", r"phase"],
        "amount": [r"eu_?contribution", r"union_?contribution", r"total_?budget", r"budget", r"total_?cost", r"amount"],
        "programme": [r"program(me)?", r"fund", r"priority", r"objective"],
        "date": [r"start_?date", r"end_?date", r"approval_?date", r"completion_?date", r"date"],
    },
}

_REFERENCE_CONTEXT_LABELS = {
    "alias": "Alias",
    "authority": "Stelle",
    "amount": "Volumen",
    "programme": "Programm",
    "beschreibung": "Kontext",
    "date": "Datum",
}

_REFERENCE_CONTEXT_ORDER = {
    "sanctions": ["alias", "beschreibung", "date"],
    "tam": ["amount", "authority", "programme", "beschreibung", "date"],
    "state_aid": ["amount", "authority", "programme", "beschreibung", "date"],
    "cohesio": ["programme", "amount", "beschreibung", "date"],
    "other": ["beschreibung", "programme", "amount", "authority", "date"],
}


def _safe_table_name(source: str) -> str:
    """Erzeugt einen sicheren SQL-Tabellennamen aus dem Source-Label."""
    name = re.sub(r"[^a-zA-Z0-9_]", "_", source.lower()).strip("_")
    return f"workshop_df_{name}"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _parse_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text_value = str(value).strip()
    if not text_value:
        return None
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
        return None


def _format_eur(value: float | None) -> str:
    if value is None:
        return "k.A."
    return f"{value:,.0f}".replace(",", ".") + " €"


def _normalize_search_text(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    text_value = re.sub(r"\s+", " ", text_value)
    return text_value


def _compact_search_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalize_search_text(value))


def _strip_legal_suffix(value: Any) -> str:
    normalized = _normalize_search_text(value)
    if not normalized:
        return ""
    cleaned = _LEGAL_RE.sub("", normalized).strip()
    cleaned = re.sub(r"\s*&\s*(co\.?)?\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned.rstrip(",;. ")


def _tokenize_search_text(value: Any) -> list[str]:
    normalized = _strip_legal_suffix(value) or _normalize_search_text(value)
    tokens = re.split(r"[\s/|,;()\\-]+", normalized)
    return [token for token in tokens if len(token) >= 3 and token not in _SEARCH_STOP_WORDS]


def _search_word_present(token: str, text_value: str) -> bool:
    if re.search(r"\b" + re.escape(token) + r"\b", text_value, re.IGNORECASE):
        return True
    if len(token) >= 6 and re.search(r"\b" + re.escape(token[:6]), text_value, re.IGNORECASE):
        return True
    return False


def _score_search_value(value: Any, query: str) -> int:
    normalized = _normalize_search_text(value)
    if not normalized or not query:
        return 0

    stripped_normalized = _strip_legal_suffix(normalized)
    stripped_query = _strip_legal_suffix(query)
    query_tokens = _tokenize_search_text(query)

    if normalized == query:
        return 140
    if stripped_query and stripped_normalized == stripped_query:
        return 132
    if normalized.startswith(query):
        return 115
    if stripped_query and stripped_normalized.startswith(stripped_query):
        return 109
    if query_tokens and all(_search_word_present(token, normalized) for token in query_tokens):
        return 104
    if all(part in normalized for part in query.split()):
        return 92
    if stripped_query and stripped_query in stripped_normalized:
        return 88
    if query in normalized:
        return 78

    compact_query = _compact_search_text(query)
    compact_value = _compact_search_text(normalized)
    if compact_query and compact_query in compact_value:
        return 68
    return 0


def ingest_dataframe(
    file_bytes: bytes,
    filename: str,
    source: str,
    sheet_name: str | int | None = 0,
    dataset_group: str = "generic",
    registry_type: str | None = None,
) -> dict:
    """
    Liest eine XLSX/XLS/CSV-Datei als DataFrame ein und speichert sie
    als SQL-Tabelle. Bestehende Tabelle wird ersetzt.

    Returns:
        {"table_name": str, "rows": int, "columns": list[str], "source": str}
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("xlsx", "xls", "xlsm"):
        # Immer smart header detection (EFRE-Tabellen haben oft Titelzeilen)
        df = _read_excel_smart(file_bytes, ext, sheet_name)
    elif ext == "csv":
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"DataFrame-Ingest nur fuer XLSX/XLS/CSV, nicht '{ext}'")

    # Spalten bereinigen
    df.columns = [_clean_column_name(str(c)) for c in df.columns]

    # Leere Zeilen/Spalten entfernen
    df = df.dropna(how="all").dropna(axis=1, how="all")

    # Unnamed-Spalten entfernen
    df = df[[c for c in df.columns if not c.startswith("unnamed")]]

    if df.empty:
        return {"table_name": "", "rows": 0, "columns": [], "source": source}

    table_name = _safe_table_name(source)

    # Metadaten aus Titelzeilen extrahieren (Bundesland, Fonds, Periode)
    metadata = {}
    if ext in ("xlsx", "xls", "xlsm"):
        metadata = _detect_metadata(file_bytes, ext, sheet_name, source=filename)

    # In PostgreSQL speichern (replace = DROP + CREATE)
    df.to_sql(table_name, engine, if_exists="replace", index=False)

    # Metadaten in separater Tabelle speichern
    _save_metadata(
        table_name,
        source,
        metadata,
        dataset_group=dataset_group,
        registry_type=registry_type,
        filename=filename,
    )

    log.info("DataFrame %s: %d Zeilen, %d Spalten → %s (%s)",
             source, len(df), len(df.columns), table_name, metadata)

    return {
        "table_name": table_name,
        "rows": len(df),
        "columns": list(df.columns),
        "source": source,
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "metadata": metadata,
        "dataset_group": dataset_group,
        "registry_type": registry_type,
    }


def _read_excel_smart(file_bytes: bytes, ext: str, sheet_name: str | int | None = 0) -> pd.DataFrame:
    """
    Versucht die Header-Zeile automatisch zu finden.
    Typisch bei EFRE-Transparenzlisten: 3-6 leere/Titel-Zeilen vor dem Header.
    Heuristik: Erste Zeile mit >= 3 nicht-leeren Zellen UND mindestens eine
    Zelle die wie ein Spaltenname aussieht (kurz, alphabetisch).
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    # Richtiges Blatt auswaehlen
    if isinstance(sheet_name, str) and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    elif isinstance(sheet_name, int) and sheet_name < len(wb.worksheets):
        ws = wb.worksheets[sheet_name]
    else:
        ws = wb.worksheets[0]

    best_row = 0
    candidates = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i > 30:
            break
        cells = [c for c in row if c is not None]
        non_empty = [str(c).strip() for c in cells if str(c).strip()]

        if len(non_empty) < 2:
            continue

        # Header-Heuristik: Zellen mit Buchstaben zaehlen
        text_cells = sum(1 for c in non_empty if any(ch.isalpha() for ch in str(c)))
        # Reine Zahlen-Zellen (typisch fuer Datenzeilen)
        pure_numbers = sum(1 for c in non_empty if _is_number(c))

        # Header hat typischerweise mehr Text als Zahlen
        # Datenzeilen haben viele Zahlen
        text_ratio = text_cells / max(len(non_empty), 1)

        candidates.append((i, len(non_empty), text_ratio, text_cells, pure_numbers))

    if candidates:
        # Sortiere: Bevorzuge Zeilen mit hoher Text-Ratio und vielen Zellen
        # Erster Kandidat mit text_ratio > 0.5 und >= 3 Zellen
        for row_idx, count, ratio, texts, nums in candidates:
            if count >= 3 and ratio >= 0.4:
                best_row = row_idx
                break
        else:
            # Fallback: Zeile mit den meisten Zellen
            best_row = max(candidates, key=lambda x: (x[2], x[1]))[0]

    wb.close()

    df = pd.read_excel(
        io.BytesIO(file_bytes),
        header=best_row,
        sheet_name=sheet_name,
        engine="openpyxl",
    )
    return df


def _clean_column_name(name: str) -> str:
    """Bereinigt Spaltennamen fuer SQL. Nimmt bei zweisprachigen Headern den deutschen Teil."""
    name = name.strip()
    # Zweisprachige Header (DE\n\nEN) → nur deutschen Teil nehmen
    if "\n" in name:
        name = name.split("\n")[0].strip()
    name = name.lower()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-zA-Z0-9_äöüß]", "", name)
    name = name.strip("_")
    if not name or name[0].isdigit():
        name = "col_" + name
    return name[:63]  # PostgreSQL Limit


def _is_number(s: str) -> bool:
    """Prüft ob ein String eine Zahl ist."""
    try:
        float(str(s).replace(",", ".").replace(" ", ""))
        return True
    except (ValueError, TypeError):
        return False


# ── Metadaten-Erkennung ──────────────────────────────────────────────────────

BUNDESLAENDER = [
    "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen",
    "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen",
    "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen",
    "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
    # Varianten
    "Freistaat Sachsen", "Freistaat Bayern", "Freistaat Thüringen",
    "NRW",
]

FONDS = ["EFRE", "ESF", "ESF+", "ELER", "EMFAF", "ERDF", "JTF", "AMIF", "ISF", "REACT-EU"]

PERIODEN = ["2014-2020", "2021-2027", "2014–2020", "2021–2027",
            "21-27", "14-20", "2028-2034"]


def _detect_metadata(
    file_bytes: bytes,
    ext: str,
    sheet_name: str | int | None = 0,
    source: str | None = None,
) -> dict:
    """
    Erkennt Bundesland, Fonds und Foerderperiode aus den Titelzeilen einer XLSX.
    Liest die ersten 15 Zeilen VOR dem Daten-Header.
    Falls nichts erkannt wird, wird der Dateiname (source) als Fallback herangezogen.
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)

    if isinstance(sheet_name, str) and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    elif isinstance(sheet_name, int) and sheet_name < len(wb.worksheets):
        ws = wb.worksheets[sheet_name]
    else:
        ws = wb.worksheets[0]

    # Alle Texte aus den ersten 15 Zeilen sammeln
    title_text = ""
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i > 15:
            break
        for c in row:
            if c is not None:
                title_text += " " + str(c)
    wb.close()

    # Auch Dateinamen durchsuchen
    title_text_lower = title_text.lower()

    result = {"bundesland": None, "fonds": None, "periode": None}

    # Bundesland erkennen
    for bl in BUNDESLAENDER:
        if bl.lower() in title_text_lower:
            # Normalisieren (Freistaat X → X)
            clean = bl.replace("Freistaat ", "")
            result["bundesland"] = clean
            break

    # Fonds erkennen
    for f in FONDS:
        if f.lower() in title_text_lower or f in title_text:
            result["fonds"] = f.upper()
            break

    # Periode erkennen
    for p in PERIODEN:
        if p in title_text:
            # Normalisieren
            result["periode"] = p.replace("–", "-")
            if len(result["periode"]) <= 5:
                result["periode"] = "20" + result["periode"]
            break

    # Fallback: aus Spaltenwerten (Fonds-Spalte)
    if not result["fonds"]:
        # Suche nach EFRE/ESF in den Daten
        for f in FONDS:
            if f.lower() in title_text_lower:
                result["fonds"] = f
                break

    # Fallback: Bundesland und Fonds aus Dateinamen erkennen
    # Greift z.B. bei "transparenzliste_sachsen_efre.xlsx" oder "Begünstigte_NRW_2021-2027.xlsx"
    if source:
        source_lower = source.lower()
        if not result["bundesland"]:
            for bl in BUNDESLAENDER:
                if bl.lower().replace("-", "_").replace(" ", "_") in source_lower.replace("-", "_"):
                    clean = bl.replace("Freistaat ", "")
                    result["bundesland"] = clean
                    break
        if not result["fonds"]:
            for f in FONDS:
                if f.lower() in source_lower:
                    result["fonds"] = f.upper()
                    break
        if not result["periode"]:
            for p in PERIODEN:
                p_normalized = p.replace("–", "-")
                if p_normalized in source or p_normalized.replace("-", "_") in source_lower:
                    result["periode"] = p_normalized
                    if len(result["periode"]) <= 5:
                        result["periode"] = "20" + result["periode"]
                    break

    return result


def _ensure_metadata_table():
    """Erstellt die Metadaten-Tabelle falls nicht vorhanden."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workshop_df_metadata (
                table_name TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                bundesland TEXT,
                fonds TEXT,
                periode TEXT,
                row_count INT DEFAULT 0,
                is_beneficiary BOOLEAN DEFAULT FALSE,
                dataset_group TEXT DEFAULT 'generic',
                registry_type TEXT,
                filename TEXT
            )
        """))
        conn.execute(text("""
            ALTER TABLE workshop_df_metadata
            ADD COLUMN IF NOT EXISTS dataset_group TEXT DEFAULT 'generic'
        """))
        conn.execute(text("""
            ALTER TABLE workshop_df_metadata
            ADD COLUMN IF NOT EXISTS registry_type TEXT
        """))
        conn.execute(text("""
            ALTER TABLE workshop_df_metadata
            ADD COLUMN IF NOT EXISTS filename TEXT
        """))
        conn.commit()


def _save_metadata(
    table_name: str,
    source: str,
    metadata: dict,
    dataset_group: str = "generic",
    registry_type: str | None = None,
    filename: str | None = None,
):
    """Speichert Metadaten zu einer DataFrame-Tabelle."""
    _ensure_metadata_table()

    # Ist es ein Beguenstigtenverzeichnis? (Hat Standort/Ort/PLZ-Spalte)
    from services.geocoding_service import detect_columns
    try:
        cols = detect_columns(source)
        is_beneficiary = bool(cols.get("standort") or cols.get("ort") or cols.get("plz"))
    except Exception:
        is_beneficiary = False
    if dataset_group == "beneficiary":
        is_beneficiary = True

    with engine.connect() as conn:
        # Zeilenanzahl
        try:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        except Exception:
            count = 0

        conn.execute(text("""
            INSERT INTO workshop_df_metadata (
                table_name, source, bundesland, fonds, periode, row_count,
                is_beneficiary, dataset_group, registry_type, filename
            )
            VALUES (:t, :s, :bl, :f, :p, :c, :b, :g, :rt, :fn)
            ON CONFLICT (table_name) DO UPDATE SET
                source = :s, bundesland = :bl, fonds = :f, periode = :p,
                row_count = :c, is_beneficiary = :b,
                dataset_group = :g, registry_type = :rt, filename = :fn
        """), {
            "t": table_name, "s": source,
            "bl": metadata.get("bundesland"),
            "f": metadata.get("fonds"),
            "p": metadata.get("periode"),
            "c": count,
            "b": is_beneficiary,
            "g": dataset_group,
            "rt": registry_type,
            "fn": filename,
        })
        conn.commit()


def get_beneficiary_sources() -> list[dict]:
    """Gibt alle DataFrame-Tabellen zurueck die Beguenstigtenverzeichnisse sind."""
    _ensure_metadata_table()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT table_name, source, bundesland, fonds, periode, row_count, dataset_group, registry_type, filename
            FROM workshop_df_metadata
            WHERE dataset_group = 'beneficiary'
               OR (is_beneficiary = TRUE AND COALESCE(dataset_group, 'generic') IN ('generic', 'beneficiary'))
            ORDER BY bundesland, source
        """)).fetchall()
    return [
        {"table_name": r[0], "source": r[1], "bundesland": r[2],
         "fonds": r[3], "periode": r[4], "row_count": r[5],
         "dataset_group": r[6], "registry_type": r[7], "filename": r[8]}
        for r in rows
    ]


def list_reference_registry_sources() -> list[dict]:
    """Gibt importierte Referenzregister fuer Unternehmensabgleiche zurueck."""
    _ensure_metadata_table()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT table_name, source, row_count, dataset_group, registry_type, filename
            FROM workshop_df_metadata
            WHERE dataset_group = 'reference_registry'
               OR registry_type IS NOT NULL
            ORDER BY registry_type, source
        """)).fetchall()
    return [
        {
            "table_name": r[0],
            "source": r[1],
            "row_count": r[2],
            "dataset_group": r[3],
            "registry_type": r[4],
            "filename": r[5],
        }
        for r in rows
    ]


def query_dataframe(source: str, sql_query: str) -> list[dict]:
    """
    Fuehrt eine SQL-Abfrage auf einer DataFrame-Tabelle aus.
    SICHERHEIT: Nur SELECT auf die spezifische Tabelle, kein DML/DDL.
    """
    cleaned = sql_query.strip()
    upper = cleaned.upper()

    if not upper.startswith("SELECT"):
        raise ValueError("Nur SELECT-Abfragen erlaubt.")

    # Blockliste fuer gefaehrliche SQL-Keywords
    blocked = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
               "GRANT", "REVOKE", "EXEC", "EXECUTE", "INTO", "COPY", ";"]
    for keyword in blocked:
        # Pruefe ob das Keyword als eigenstaendiges Wort vorkommt (nicht in Spaltennamen)
        import re
        if keyword == ";":
            if ";" in cleaned:
                raise ValueError("Mehrere Statements (;) sind nicht erlaubt.")
        elif re.search(rf"\b{keyword}\b", upper):
            raise ValueError(f"'{keyword}' ist in Abfragen nicht erlaubt.")

    table_name = _safe_table_name(source)

    # Tabelle pruefen
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
            {"t": table_name},
        )
        if not result.scalar():
            raise ValueError(f"Tabelle '{table_name}' nicht gefunden. Erst Daten einlesen.")

    # Nur {table} durch den sicheren Tabellennamen ersetzen
    safe_sql = cleaned.replace("{table}", f'"{table_name}"')

    # Maximal 1000 Zeilen zurueckgeben
    if "LIMIT" not in upper:
        safe_sql += " LIMIT 1000"

    with engine.connect() as conn:
        result = conn.execute(text(safe_sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    return rows


def get_table_info(source: str) -> dict:
    """Gibt Schema-Info und Statistiken einer DataFrame-Tabelle zurueck."""
    table_name = _safe_table_name(source)

    with engine.connect() as conn:
        # Pruefen ob Tabelle existiert
        result = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
            {"t": table_name},
        )
        if not result.scalar():
            return {"exists": False, "table_name": table_name}

        # Spalten
        cols = conn.execute(
            text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = :t
                ORDER BY ordinal_position
            """),
            {"t": table_name},
        )
        columns = [{"name": r[0], "type": r[1]} for r in cols]

        # Zeilenanzahl
        count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

    return {
        "exists": True,
        "table_name": table_name,
        "row_count": count,
        "columns": columns,
    }


def get_summary_stats(source: str) -> str:
    """
    Erzeugt eine menschenlesbare Zusammenfassung einer DataFrame-Tabelle.
    Wird als Kontext an das LLM uebergeben.
    """
    table_name = _safe_table_name(source)
    info = get_table_info(source)
    if not info.get("exists"):
        return f"Tabelle '{source}' nicht gefunden."

    lines = [
        f"Datenquelle: {source}",
        f"Tabelle: {table_name}",
        f"Zeilen: {info['row_count']}",
        f"Spalten: {', '.join(c['name'] for c in info['columns'])}",
        "",
    ]

    # Numerische Spalten: Min/Max/Avg/Sum
    numeric_cols = [c["name"] for c in info["columns"]
                    if c["type"] in ("integer", "bigint", "numeric", "double precision", "real")]

    if numeric_cols:
        lines.append("Numerische Statistiken:")
        with engine.connect() as conn:
            for col in numeric_cols[:10]:  # Max 10 Spalten
                try:
                    row = conn.execute(text(
                        f'SELECT MIN("{col}"), MAX("{col}"), AVG("{col}")::numeric(20,2), '
                        f'SUM("{col}")::numeric(20,2), COUNT("{col}") '
                        f'FROM "{table_name}" WHERE "{col}" IS NOT NULL'
                    )).fetchone()
                    if row and row[4] > 0:
                        lines.append(
                            f"  {col}: Min={row[0]}, Max={row[1]}, "
                            f"Avg={row[2]}, Summe={row[3]}, Anzahl={row[4]}"
                        )
                except Exception:
                    pass

    # Top 5 Zeilen als Beispiel
    lines.append("\nBeispieldaten (erste 5 Zeilen):")
    with engine.connect() as conn:
        rows = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT 5')).fetchall()
        col_names = [c["name"] for c in info["columns"]]
        for row in rows:
            fields = [f"{col_names[i]}: {row[i]}" for i in range(len(row))
                      if row[i] is not None and str(row[i]).strip()]
            lines.append("  " + " | ".join(fields[:6]))

    return "\n".join(lines)


def get_beneficiary_llm_context(max_entries_per_source: int = 8) -> str:
    from services.geocoding_service import detect_columns

    sources = get_beneficiary_sources()
    if not sources:
        return ""

    parts = [
        "Aktuell geladene Beguenstigtenverzeichnisse.",
        f"Anzahl Quellen: {len(sources)}",
        "",
    ]

    total_rows = 0
    total_cost = 0.0
    combined_top: list[dict[str, Any]] = []

    for source_info in sources:
        source = source_info["source"]
        table_name = _safe_table_name(source)
        columns = detect_columns(source)

        name_col = columns.get("name")
        project_col = columns.get("projekt")
        cost_col = columns.get("kosten")
        location_col = columns.get("standort") or columns.get("ort") or columns.get("landkreis")
        category_col = columns.get("sz")

        selected_cols: list[tuple[str, str]] = []
        for alias, col in (
            ("name", name_col),
            ("projekt", project_col),
            ("kosten", cost_col),
            ("standort", location_col),
            ("kategorie", category_col),
        ):
            if col:
                selected_cols.append((alias, col))

        if not selected_cols:
            continue

        sql = ", ".join(f"{_quote_ident(col)} AS {alias}" for alias, col in selected_cols)
        with engine.connect() as conn:
            rows = conn.execute(text(f'SELECT {sql} FROM "{table_name}"')).fetchall()

        parsed_rows: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row._mapping)
            entry["kosten_num"] = _parse_numeric(entry.get("kosten"))
            parsed_rows.append(entry)

        row_count = len(parsed_rows)
        total_rows += row_count
        cost_rows = [r for r in parsed_rows if r.get("kosten_num") is not None]
        source_total = sum(r["kosten_num"] for r in cost_rows)
        total_cost += source_total

        top_rows = sorted(cost_rows, key=lambda item: item["kosten_num"], reverse=True)[:max_entries_per_source]
        combined_top.extend(
            {
                "source": source,
                "bundesland": source_info.get("bundesland") or source,
                "name": row.get("name") or "Unbekannt",
                "projekt": row.get("projekt") or "",
                "standort": row.get("standort") or "",
                "kosten_num": row["kosten_num"],
            }
            for row in top_rows
        )

        parts.extend([
            f"Quelle: {source}",
            f"- Bundesland: {source_info.get('bundesland') or 'k.A.'}",
            f"- Fonds: {source_info.get('fonds') or 'k.A.'}",
            f"- Foerderperiode: {source_info.get('periode') or 'k.A.'}",
            f"- Datensaetze: {row_count}",
            f"- Datensaetze mit Kosten: {len(cost_rows)}",
            f"- Summe Gesamtkosten: {_format_eur(source_total)}",
        ])

        if top_rows:
            parts.append("- Hoechste Foerdersummen / Gesamtkosten:")
            for idx, row in enumerate(top_rows, start=1):
                details = [
                    f"{idx}. {row.get('name') or 'Unbekannt'}",
                    _format_eur(row.get("kosten_num")),
                ]
                if row.get("standort"):
                    details.append(str(row["standort"]))
                if row.get("projekt"):
                    details.append(str(row["projekt"])[:120])
                parts.append("  " + " | ".join(details))

        category_counts: dict[str, int] = {}
        for row in parsed_rows:
            category = str(row.get("kategorie") or "").strip()
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
        if category_counts:
            parts.append("- Haeufigste Kategorien:")
            for label, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)[:5]:
                parts.append(f"  {label}: {count}")

        location_totals: dict[str, float] = {}
        for row in cost_rows:
            location = str(row.get("standort") or "").strip()
            if not location:
                continue
            location_totals[location] = location_totals.get(location, 0.0) + float(row["kosten_num"])
        if location_totals:
            parts.append("- Top-Standorte nach aggregierten Kosten:")
            for label, amount in sorted(location_totals.items(), key=lambda item: item[1], reverse=True)[:5]:
                parts.append(f"  {label}: {_format_eur(amount)}")

        parts.append("")

    parts.extend([
        "Quellenuebergreifende Kennzahlen:",
        f"- Gesamtzahl Datensaetze: {total_rows}",
        f"- Gesamtvolumen: {_format_eur(total_cost)}",
    ])

    if combined_top:
        parts.append("- Hoechste Einzelvorhaben ueber alle Quellen:")
        for idx, row in enumerate(sorted(combined_top, key=lambda item: item["kosten_num"], reverse=True)[:12], start=1):
            parts.append(
                "  "
                + " | ".join(filter(None, [
                    f"{idx}. {row['name']}",
                    _format_eur(row["kosten_num"]),
                    row.get("bundesland"),
                    row.get("standort"),
                    str(row.get("projekt", ""))[:120],
                ]))
            )

    return "\n".join(parts).strip()


def _get_text_columns(source: str) -> list[str]:
    info = get_table_info(source)
    if not info.get("exists"):
        return []
    text_types = {"text", "character varying", "character"}
    return [c["name"] for c in info["columns"] if c["type"] in text_types]


def _pick_fallback_column(text_columns: list[str], used_columns: set[str]) -> str | None:
    for column in text_columns:
        if column not in used_columns:
            return column
    return None


def _get_column_names(source: str) -> list[str]:
    info = get_table_info(source)
    if not info.get("exists"):
        return []
    return [c["name"] for c in info["columns"]]


def _find_pattern_column(
    columns: list[str],
    patterns: list[str],
    used_columns: set[str] | None = None,
) -> str | None:
    blocked = used_columns or set()
    for pattern in patterns:
        for column in columns:
            if column in blocked:
                continue
            if re.search(pattern, column, re.IGNORECASE):
                return column
    return None


def _clean_display_text(value: Any) -> str:
    if value is None:
        return ""
    text_value = str(value).strip()
    if not text_value or text_value.lower() in {"nan", "none", "null"}:
        return ""
    return re.sub(r"\s+", " ", text_value)


def _format_reference_value(field_name: str, value: Any) -> str:
    if field_name == "amount":
        amount = _parse_numeric(value)
        if amount is not None:
            return _format_eur(amount)
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    return _clean_display_text(value)


def _join_unique_values(*values: Any, limit: int = 280) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        text_value = _clean_display_text(value)
        if not text_value:
            continue
        key = text_value.casefold()
        if key in seen:
            continue
        seen.add(key)
        parts.append(text_value)
    combined = " | ".join(parts)
    if len(combined) > limit:
        return combined[: limit - 1].rstrip() + "…"
    return combined


def _resolve_reference_registry_columns(source: str, registry_type: str | None) -> dict[str, str | None]:
    from services.geocoding_service import detect_columns

    columns = _get_column_names(source)
    text_columns = _get_text_columns(source)
    generic = detect_columns(source)
    profile_patterns = _REFERENCE_PROFILE_PATTERNS.get(registry_type or "", {})

    mapping = {
        "name": _find_pattern_column(columns, profile_patterns.get("name", [])) or generic.get("name"),
        "alias": _find_pattern_column(columns, profile_patterns.get("alias", [])),
        "projekt": _find_pattern_column(columns, profile_patterns.get("projekt", [])) or generic.get("projekt"),
        "beschreibung": _find_pattern_column(columns, profile_patterns.get("beschreibung", [])) or generic.get("beschreibung"),
        "aktenzeichen": _find_pattern_column(columns, profile_patterns.get("aktenzeichen", [])) or generic.get("aktenzeichen"),
        "standort": _find_pattern_column(columns, profile_patterns.get("standort", []))
        or generic.get("standort")
        or generic.get("ort")
        or generic.get("landkreis"),
        "country": _find_pattern_column(columns, profile_patterns.get("country", [])) or generic.get("country"),
        "status": _find_pattern_column(columns, profile_patterns.get("status", [])) or generic.get("status"),
        "authority": _find_pattern_column(columns, profile_patterns.get("authority", [])),
        "amount": _find_pattern_column(columns, profile_patterns.get("amount", [])),
        "programme": _find_pattern_column(columns, profile_patterns.get("programme", [])),
        "date": _find_pattern_column(columns, profile_patterns.get("date", [])),
    }

    used_for_fallback = {value for value in mapping.values() if value}
    if not mapping["name"]:
        mapping["name"] = _pick_fallback_column(text_columns, used_for_fallback)
        if mapping["name"]:
            used_for_fallback.add(mapping["name"])
    if not mapping["projekt"]:
        mapping["projekt"] = _pick_fallback_column(text_columns, used_for_fallback)
        if mapping["projekt"]:
            used_for_fallback.add(mapping["projekt"])
    if not mapping["beschreibung"]:
        mapping["beschreibung"] = _pick_fallback_column(text_columns, used_for_fallback)

    return mapping


def _build_reference_search_vectors(entry: dict[str, Any]) -> dict[str, str]:
    amount_value = _format_reference_value("amount", entry.get("amount"))
    return {
        "name": _join_unique_values(entry.get("name"), entry.get("alias")),
        "projekt": _join_unique_values(entry.get("projekt"), entry.get("programme")),
        "beschreibung": _join_unique_values(
            entry.get("beschreibung"),
            entry.get("authority"),
            amount_value,
            entry.get("date"),
        ),
        "aktenzeichen": _clean_display_text(entry.get("aktenzeichen")),
        "standort": _clean_display_text(entry.get("standort")),
        "country": _clean_display_text(entry.get("country")),
        "status": _join_unique_values(entry.get("status"), entry.get("date")),
    }


def _build_reference_project_name(entry: dict[str, Any], registry_type: str | None) -> str:
    fallback_order = {
        "sanctions": [entry.get("projekt"), entry.get("programme")],
        "tam": [entry.get("projekt"), entry.get("programme")],
        "state_aid": [entry.get("projekt"), entry.get("programme")],
        "cohesio": [entry.get("projekt"), entry.get("programme")],
    }
    return _join_unique_values(*(fallback_order.get(registry_type or "", [entry.get("projekt"), entry.get("programme")])), limit=180)


def _build_reference_description(entry: dict[str, Any], registry_type: str | None) -> str:
    ordered_fields = _REFERENCE_CONTEXT_ORDER.get(registry_type or "", _REFERENCE_CONTEXT_ORDER["other"])
    parts: list[str] = []
    for field_name in ordered_fields:
        formatted_value = _format_reference_value(field_name, entry.get(field_name))
        if not formatted_value:
            continue
        label = _REFERENCE_CONTEXT_LABELS.get(field_name)
        parts.append(f"{label}: {formatted_value}" if label else formatted_value)
    if not parts:
        return _clean_display_text(entry.get("beschreibung"))
    return _join_unique_values(*parts, limit=320)


def search_beneficiary_records(
    query: str = "",
    scope: str = "all",
    bundesland: str | None = None,
    fonds: str | None = None,
    source: str | None = None,
    min_cost: float | None = None,
    limit: int = 60,
    company_limit: int = 14,
) -> dict:
    from services.geocoding_service import detect_columns

    scope_fields = {
        "all": ["name", "projekt", "aktenzeichen", "standort", "beschreibung"],
        "company": ["name"],
        "project": ["projekt"],
        "aktenzeichen": ["aktenzeichen"],
        "location": ["standort"],
    }
    if scope not in scope_fields:
        raise ValueError(f"Unbekannter Scope '{scope}'.")

    normalized_query = _normalize_search_text(query)
    beneficiary_sources = [
        item for item in get_beneficiary_sources()
        if (not bundesland or (item.get("bundesland") or "") == bundesland)
        and (not fonds or (item.get("fonds") or "") == fonds)
        and (not source or item.get("source") == source)
    ]

    scanned_records = 0
    flat_results: list[dict[str, Any]] = []

    for source_info in beneficiary_sources:
        current_source = source_info["source"]
        table_name = _safe_table_name(current_source)
        columns = detect_columns(current_source)

        name_col = columns.get("name")
        project_col = columns.get("projekt")
        cost_col = columns.get("kosten")
        location_col = columns.get("standort") or columns.get("ort") or columns.get("landkreis")
        category_col = columns.get("sz")
        description_col = columns.get("beschreibung")
        aktenzeichen_col = columns.get("aktenzeichen")

        selected_cols: list[tuple[str, str]] = []
        for alias, col in (
            ("name", name_col),
            ("projekt", project_col),
            ("kosten", cost_col),
            ("standort", location_col),
            ("kategorie", category_col),
            ("beschreibung", description_col),
            ("aktenzeichen", aktenzeichen_col),
        ):
            if col:
                selected_cols.append((alias, col))

        if not selected_cols:
            continue

        sql = ", ".join(f"{_quote_ident(col)} AS {alias}" for alias, col in selected_cols)
        with engine.connect() as conn:
            rows = conn.execute(text(f'SELECT {sql} FROM "{table_name}"')).fetchall()

        scanned_records += len(rows)
        for row in rows:
            entry = dict(row._mapping)
            cost_value = _parse_numeric(entry.get("kosten"))
            if min_cost is not None and (cost_value is None or cost_value < min_cost):
                continue

            field_values = {
                "name": entry.get("name"),
                "projekt": entry.get("projekt"),
                "aktenzeichen": entry.get("aktenzeichen"),
                "standort": entry.get("standort"),
                "beschreibung": entry.get("beschreibung"),
            }

            matched_fields: list[str] = []
            match_score = 0
            if normalized_query:
                for field_name in scope_fields[scope]:
                    field_score = _score_search_value(field_values.get(field_name), normalized_query)
                    if field_score > 0:
                        matched_fields.append(field_name)
                        match_score = max(match_score, field_score)
                if match_score == 0:
                    continue
            else:
                match_score = 1

            flat_results.append({
                "company_name": str(entry.get("name") or "").strip() or "Unbekannt",
                "project_name": str(entry.get("projekt") or "").strip() or "",
                "aktenzeichen": str(entry.get("aktenzeichen") or "").strip() or "",
                "location": str(entry.get("standort") or "").strip() or "",
                "category": str(entry.get("kategorie") or "").strip() or "",
                "description": str(entry.get("beschreibung") or "").strip() or "",
                "kosten": cost_value,
                "kosten_label": _format_eur(cost_value),
                "source": current_source,
                "bundesland": source_info.get("bundesland"),
                "fonds": source_info.get("fonds"),
                "periode": source_info.get("periode"),
                "matched_fields": matched_fields,
                "match_score": match_score,
            })

    def _record_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        if normalized_query:
            return (
                -int(item.get("match_score") or 0),
                -float(item.get("kosten") or 0.0),
                item.get("company_name") or "",
                item.get("project_name") or "",
            )
        return (
            -float(item.get("kosten") or 0.0),
            item.get("company_name") or "",
            item.get("project_name") or "",
        )

    sorted_records = sorted(flat_results, key=_record_sort_key)

    companies: dict[str, dict[str, Any]] = {}
    for item in sorted_records:
        company_key = _normalize_search_text(item["company_name"]) or _normalize_search_text(item["project_name"])
        if not company_key:
            company_key = f"{item['source']}::{len(companies)}"
        company = companies.setdefault(company_key, {
            "company_name": item["company_name"],
            "total_kosten": 0.0,
            "project_count": 0,
            "match_score": 0,
            "sources": set(),
            "bundeslaender": set(),
            "fonds": set(),
            "standorte": set(),
            "aktenzeichen": set(),
            "matched_fields": set(),
            "projects": [],
        })

        if item.get("kosten") is not None:
            company["total_kosten"] += float(item["kosten"])
        company["project_count"] += 1
        company["match_score"] = max(company["match_score"], int(item.get("match_score") or 0))
        if item.get("source"):
            company["sources"].add(item["source"])
        if item.get("bundesland"):
            company["bundeslaender"].add(item["bundesland"])
        if item.get("fonds"):
            company["fonds"].add(item["fonds"])
        if item.get("location"):
            company["standorte"].add(item["location"])
        if item.get("aktenzeichen"):
            company["aktenzeichen"].add(item["aktenzeichen"])
        for field_name in item.get("matched_fields") or []:
            company["matched_fields"].add(field_name)
        if len(company["projects"]) < 8:
            company["projects"].append({
                "project_name": item["project_name"],
                "aktenzeichen": item["aktenzeichen"],
                "location": item["location"],
                "category": item["category"],
                "kosten": item["kosten"],
                "kosten_label": item["kosten_label"],
                "source": item["source"],
                "bundesland": item["bundesland"],
                "fonds": item["fonds"],
                "periode": item["periode"],
                "matched_fields": item["matched_fields"],
                "match_score": item["match_score"],
            })

    company_results = []
    for company in companies.values():
        company_results.append({
            "company_name": company["company_name"],
            "total_kosten": company["total_kosten"],
            "total_kosten_label": _format_eur(company["total_kosten"] or None),
            "project_count": company["project_count"],
            "match_score": company["match_score"],
            "sources": sorted(company["sources"]),
            "bundeslaender": sorted(company["bundeslaender"]),
            "fonds": sorted(company["fonds"]),
            "standorte": sorted(company["standorte"])[:6],
            "aktenzeichen": sorted(company["aktenzeichen"])[:6],
            "matched_fields": sorted(company["matched_fields"]),
            "projects": company["projects"],
        })

    def _company_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        if normalized_query:
            return (
                -int(item.get("match_score") or 0),
                -float(item.get("total_kosten") or 0.0),
                -int(item.get("project_count") or 0),
                item.get("company_name") or "",
            )
        return (
            -float(item.get("total_kosten") or 0.0),
            -int(item.get("project_count") or 0),
            item.get("company_name") or "",
        )

    company_results = sorted(company_results, key=_company_sort_key)
    limited_records = sorted_records[:max(1, min(limit, 200))]
    limited_companies = company_results[:max(1, min(company_limit, 50))]

    return {
        "query": query,
        "scope": scope,
        "summary": {
            "sources_considered": len(beneficiary_sources),
            "records_scanned": scanned_records,
            "matches": len(sorted_records),
            "companies": len(company_results),
            "total_match_volume": sum(float(item["kosten"]) for item in sorted_records if item.get("kosten") is not None),
        },
        "companies": limited_companies,
        "records": limited_records,
    }


def search_reference_registry_records(
    query: str,
    registry_type: str | None = None,
    source: str | None = None,
    limit: int = 30,
) -> dict:
    normalized_query = _normalize_search_text(query)
    registry_sources = [
        item for item in list_reference_registry_sources()
        if (not registry_type or item.get("registry_type") == registry_type)
        and (not source or item.get("source") == source)
    ]

    if not normalized_query:
        return {
            "query": query,
            "summary": {
                "sources_considered": len(registry_sources),
                "matches": 0,
            },
            "hits": [],
        }

    hits: list[dict[str, Any]] = []

    for source_info in registry_sources:
        current_source = source_info["source"]
        table_name = _safe_table_name(current_source)
        current_registry_type = source_info.get("registry_type") or "other"
        columns = _resolve_reference_registry_columns(current_source, current_registry_type)

        selected_cols: list[tuple[str, str]] = []
        for alias, col in (
            ("name", columns.get("name")),
            ("alias", columns.get("alias")),
            ("projekt", columns.get("projekt")),
            ("beschreibung", columns.get("beschreibung")),
            ("aktenzeichen", columns.get("aktenzeichen")),
            ("standort", columns.get("standort")),
            ("country", columns.get("country")),
            ("status", columns.get("status")),
            ("authority", columns.get("authority")),
            ("amount", columns.get("amount")),
            ("programme", columns.get("programme")),
            ("date", columns.get("date")),
        ):
            if col:
                selected_cols.append((alias, col))

        if not selected_cols:
            continue

        sql = ", ".join(f"{_quote_ident(col)} AS {alias}" for alias, col in selected_cols)
        with engine.connect() as conn:
            rows = conn.execute(text(f'SELECT {sql} FROM "{table_name}" LIMIT 5000')).fetchall()

        for row in rows:
            entry = dict(row._mapping)
            field_values = _build_reference_search_vectors(entry)

            match_score = 0
            matched_fields: list[str] = []
            for field_name in ("name", "projekt", "beschreibung", "aktenzeichen", "standort", "country", "status"):
                field_score = _score_search_value(field_values.get(field_name), normalized_query)
                if field_score > 0:
                    matched_fields.append(field_name)
                    match_score = max(match_score, field_score)

            if match_score == 0:
                continue

            hits.append({
                "company_name": _join_unique_values(entry.get("name"), entry.get("alias"), limit=160) or _build_reference_project_name(entry, current_registry_type) or "Unbekannt",
                "project_name": _build_reference_project_name(entry, current_registry_type),
                "description": _build_reference_description(entry, current_registry_type),
                "aktenzeichen": _clean_display_text(entry.get("aktenzeichen")),
                "location": _clean_display_text(entry.get("standort")),
                "country": _clean_display_text(entry.get("country")),
                "status": _clean_display_text(entry.get("status")),
                "source": current_source,
                "registry_type": current_registry_type,
                "filename": source_info.get("filename"),
                "matched_fields": matched_fields,
                "match_score": match_score,
            })

    total_matches = len(hits)
    hits = sorted(
        hits,
        key=lambda item: (
            -int(item.get("match_score") or 0),
            item.get("registry_type") or "",
            item.get("company_name") or "",
            item.get("project_name") or "",
        ),
    )[:max(1, min(limit, 100))]

    return {
        "query": query,
        "summary": {
            "sources_considered": len(registry_sources),
            "matches": total_matches,
        },
        "hits": hits,
    }


def list_dataframe_tables() -> list[dict]:
    """Listet alle workshop_df_* Tabellen."""
    _ensure_metadata_table()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                t.table_name,
                m.dataset_group,
                m.registry_type
            FROM information_schema.tables t
            LEFT JOIN workshop_df_metadata m ON m.table_name = t.table_name
            WHERE t.table_schema = 'public' AND t.table_name LIKE 'workshop_df_%'
            ORDER BY t.table_name
        """))
        tables = []
        for name, dataset_group, registry_type in result:
            source = name.replace("workshop_df_", "")
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            tables.append({
                "table_name": name,
                "source": source,
                "rows": count,
                "dataset_group": dataset_group,
                "registry_type": registry_type,
            })
    return tables


def delete_dataframe_table(source: str) -> bool:
    """Loescht eine DataFrame-Tabelle und ihre Metadaten."""
    table_name = _safe_table_name(source)
    with engine.connect() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        conn.execute(text("DELETE FROM workshop_df_metadata WHERE table_name = :t OR source = :s"),
                     {"t": table_name, "s": source})
        conn.commit()
    log.info("DataFrame-Tabelle %s + Metadaten geloescht.", table_name)
    return True
