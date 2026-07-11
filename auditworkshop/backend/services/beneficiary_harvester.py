"""
flowworkshop · services/beneficiary_harvester.py

Phase 6a — Smart-Mode-Harvest fuer Beneficiaries.

Idempotent, additiv. Bei XLSX-/CSV-Upload wird nur das ergaenzt, was neu ist.
Alte Records bleiben unangetastet (smart-Mode mit ON CONFLICT DO NOTHING).
Drei Modi analog ``services.state_aid_harvester``:

  - smart        — neue Records einfuegen, Konflikte als skipped zaehlen.
  - full-refresh — bei Konflikt UPDATE (Korrekturen aus Quelle uebernehmen).
  - force        — Pre-Delete der Quelle, dann reiner Insert.

Originalwerte werden in den ``*_raw``-Spalten gespeichert. Parsed-Helper
(cost_total, *_at-Datums) koennen NULL sein, wenn parse_amount/parse_date
am Original-String scheitern. Die ganze Original-Zeile landet zusaetzlich
in ``raw_payload`` (JSONB) — 100 % Rueckverfolgbarkeit zur Quell-Zeile.
"""
from __future__ import annotations

import hashlib
import io
import logging
import math
import re
import unicodedata
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models.beneficiary_records import BeneficiaryHarvestRun, BeneficiaryRecord
from services.state_aid_service import parse_amount, parse_date

log = logging.getLogger(__name__)


# Vier Modi (siehe Modul-Docstring).
# ``snapshot`` ist der fachlich sichere Standard fuer regelmaessige
# Transparenzlisten: die Quelle ist nach dem Lauf exakt der gelesene
# Quellensnapshot, nicht die historisch aufaddierte Menge.
HarvestMode = Literal["smart", "full-refresh", "force", "snapshot"]


# Fields, die in compute_record_hash einfliessen — bewusst stabil, ueber
# Workshop-Updates hinweg. Aenderungen an dieser Liste machen alle Hashes
# alt und erzeugen Duplikate beim naechsten Smart-Lauf.
_HASH_FIELDS: tuple[str, ...] = (
    "beneficiary_name",
    "project_name",
    "project_aktenzeichen",
    "bundesland",
    "periode",
    "fonds",
    "funded_at_raw",
    "cost_total_raw",
)


# Kanonische Aliase, die der Parser im Spalten-Mapping erwartet. Sie spiegeln
# die Rollen aus services.geocoding_service.COLUMN_PATTERNS wider, damit das
# Backfill-Skript dieselbe Logik wiederverwenden kann.
_CANONICAL_ALIASES: tuple[str, ...] = (
    "name", "projekt", "aktenzeichen", "beschreibung",
    "kosten", "kosten_eu", "currency",
    "standort", "ort", "plz", "landkreis", "nuts", "latitude", "longitude",
    "beginn", "ende", "funded_at",
)


# ── Datenklassen ──────────────────────────────────────────────────────────────


@dataclass
class BeneficiaryHarvestParams:
    """Eingabe-Parameter eines Harvest-Laufs.

    ``source_key`` ist Pflicht — jeder Lauf gehoert zu genau einer Quelle.
    Datei-Inhalt kommt entweder als ``file_content`` (Bytes, im Speicher)
    oder wird in einer Phase-6b-Ausbaustufe per URL-Connector geladen.
    """

    source_key: str
    bundesland: str | None = None
    fonds: str | None = None
    periode: str | None = None
    country_code: str | None = None
    file_content: bytes | None = None
    file_name: str | None = None
    field_mapping: dict[str, str] | None = None
    sheet_name: str | int | None = None
    header_row: int = 0
    mode: HarvestMode = "snapshot"
    triggered_by: str = "cli"


# ── Helper: Hash + Normalize ─────────────────────────────────────────────────


_ACCENT_TABLE = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})


def _normalize_for_hash(value: Any) -> str:
    """Lowercase + Whitespace-Kompaktor fuer den Hash-Input.

    Bewusst NICHT die volle ``normalize_company_name``-Logik: der Hash darf
    keine Rechtsform-Suffixe entfernen, sonst kollidieren ``Beispiel GmbH``
    und ``Beispiel KG`` zur selben ID. Stabilitaet vor Cleverness.
    """
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    s = str(value).strip()
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"\s+", " ", s)
    return s


def compute_record_hash(row: dict[str, Any], source_key: str) -> str:
    """Stabile, deterministische ID einer Beneficiary-Zeile.

    Kombiniert die Felder in ``_HASH_FIELDS`` plus den Source-Key zu einem
    SHA-256, gekuerzt auf 32 Hex-Zeichen (= 128 Bit, kollisionsarm fuer
    typische Volumina von <1 Mio. Records pro Quelle).

    Reihenfolge der Felder ist deterministisch — Aenderungen an der Liste
    invalidieren bestehende IDs (das ist gewollt, Smart-Mode meldet dann
    alle Records als neu).
    """
    parts: list[str] = [source_key]
    for field in _HASH_FIELDS:
        parts.append(_normalize_for_hash(row.get(field)))
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def _normalize_company_name_simple(value: Any) -> str:
    """Akzent-/Umlaute-Kompaktor + Whitespace-Trim fuer das Search-Helper-
    Feld ``beneficiary_name_normalized``.

    Hier KEIN Strip von Rechtsform-Suffixen — Suche nutzt rapidfuzz, das
    Tokens unabhaengig vom Suffix matcht. Der Index profitiert dafuer von
    der vollen Token-Information.
    """
    if value is None:
        return ""
    s = str(value).translate(_ACCENT_TABLE).casefold()
    s = re.sub(r"[^\w\s\-]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ── Header- / Spalten-Detection ──────────────────────────────────────────────


def _detect_canonical_columns(
    headers: list[str], explicit_mapping: dict[str, str] | None,
) -> dict[str, str]:
    """Mapped Spalten-Header der XLSX/CSV auf kanonische Aliase.

    Wenn ein expliziter ``field_mapping`` mitgegeben wird, gilt der mit
    Vorrang — Felder, die dort nicht enthalten sind, werden ueber die
    Patterns aus ``services.geocoding_service.COLUMN_PATTERNS`` ergaenzt.

    Rueckgabe: ``{alias: original_header}``. Aliase ohne Treffer fehlen
    schlicht im Dict (Aufrufer muss ``.get()`` benutzen).
    """
    from services.geocoding_service import COLUMN_PATTERNS

    mapping: dict[str, str] = {}
    if explicit_mapping:
        for alias, header in explicit_mapping.items():
            if alias not in _CANONICAL_ALIASES:
                continue
            if header and header in headers:
                mapping[alias] = header

    # Pattern-basierter Fallback: nur fuer Aliase, die noch nicht gesetzt sind.
    role_to_alias = {
        "name": "name",
        "projekt": "projekt",
        "aktenzeichen": "aktenzeichen",
        "beschreibung": "beschreibung",
        "kosten": "kosten",
        "kosten_eu": "kosten_eu",
        "standort": "standort",
        "ort": "ort",
        "plz": "plz",
        "landkreis": "landkreis",
        "latitude": "latitude",
        "longitude": "longitude",
        "beginn": "beginn",
        "ende": "ende",
    }
    for role, alias in role_to_alias.items():
        if alias in mapping:
            continue
        patterns = COLUMN_PATTERNS.get(role, [])
        for pattern in patterns:
            candidates = [h for h in headers if re.search(pattern, h, re.IGNORECASE)]
            if candidates:
                # Kuerzeste Spalte = spezifischster Match (analog _find_column).
                mapping[alias] = min(candidates, key=len)
                break
    return mapping


# ── Parser: XLSX / CSV ────────────────────────────────────────────────────────


def parse_xlsx_or_csv(
    content: bytes,
    *,
    file_name: str,
    sheet: str | int | None = None,
    header_row: int = 0,
    field_mapping: dict[str, str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Lazy parser fuer XLSX/CSV. Pro Zeile ein Dict mit:

      - ``raw_row``    : ``dict[orig_header → value]`` (volle Original-Zeile).
      - ``mapping``    : ``dict[alias → orig_header]`` (kanonisches Mapping).
      - kanonische Aliase als Top-Level-Keys (``beneficiary_name`` etc.).
      - ``_row_number``: 1-basiert, fuer Audit-Spur.

    Bei XLSX wird wenn moeglich auf ``services.dataframe_service._read_excel_smart``
    zurueckgegriffen, das eine Header-Zeile erkennt — fuer CSV reicht ein
    direkter ``pandas.read_csv``.
    """
    import pandas as pd

    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""

    if ext in ("xlsx", "xls", "xlsm"):
        from services.dataframe_service import _read_excel_smart
        if header_row and header_row > 0:
            df = pd.read_excel(
                io.BytesIO(content),
                header=header_row,
                sheet_name=sheet if sheet is not None else 0,
                engine="openpyxl",
            )
        else:
            df = _read_excel_smart(content, ext, sheet if sheet is not None else 0)
    elif ext == "csv":
        from services.dataframe_service import _read_csv_smart
        df = _read_csv_smart(content)
    else:
        raise ValueError(
            f"Beneficiary-Harvest nur fuer XLSX/XLS/CSV, nicht '{ext}' "
            f"(file_name={file_name})"
        )

    # Spaltennamen sauber als String — pandas liefert manchmal int/np.* Header.
    headers = [str(c).strip() for c in df.columns]
    df.columns = headers

    mapping = _detect_canonical_columns(headers, field_mapping)

    # Datums-/Datums-of-Funding-Heuristik: wenn `funded_at` nicht explizit
    # gesetzt ist, nehmen wir `beginn` (Projektstart) als Naeherung — analog
    # zur bisherigen UI-Anzeige in Szenario 6.
    if "funded_at" not in mapping and "beginn" in mapping:
        mapping["funded_at"] = mapping["beginn"]

    for idx, row in df.iterrows():
        raw_row: dict[str, Any] = {}
        for header in headers:
            value = row.get(header)
            if isinstance(value, float) and math.isnan(value):
                value = None
            elif hasattr(value, "isoformat"):
                # pandas.Timestamp / datetime / date → ISO-String, damit JSONB
                # serialisierbar bleibt.
                try:
                    value = value.isoformat()
                except Exception:
                    value = str(value)
            raw_row[header] = value

        # Kanonische Felder extrahieren.
        canonical: dict[str, Any] = {}
        for alias, header in mapping.items():
            canonical[alias] = raw_row.get(header)

        # Pflichtfeld: Name. Wer keinen Namen liefert, wird aussortiert.
        name = (canonical.get("name") or "").strip() if canonical.get("name") else ""
        if not name:
            yield {
                "_row_number": int(idx) + 1,
                "_skip_reason": "no_name",
                "raw_row": raw_row,
                "mapping": mapping,
            }
            continue

        yield {
            "_row_number": int(idx) + 1,
            "raw_row": raw_row,
            "mapping": mapping,
            "beneficiary_name": name,
            "project_name": (canonical.get("projekt") or "").strip() or None,
            "project_aktenzeichen": (canonical.get("aktenzeichen") or "").strip() or None,
            "project_description": (canonical.get("beschreibung") or "").strip() or None,
            "cost_total_raw": _stringify(canonical.get("kosten")),
            "cost_eu_funding_raw": _stringify(canonical.get("kosten_eu")),
            "currency": (canonical.get("currency") or "").strip() or None,
            "location": (canonical.get("standort") or canonical.get("ort") or "") or None,
            "landkreis": (canonical.get("landkreis") or "").strip() or None,
            "plz": _stringify_plz(canonical.get("plz")),
            "nuts_code": (canonical.get("nuts") or "").strip() or None,
            "latitude": _coerce_float(canonical.get("latitude")),
            "longitude": _coerce_float(canonical.get("longitude")),
            "project_start_raw": _stringify(canonical.get("beginn")),
            "project_end_raw": _stringify(canonical.get("ende")),
            "funded_at_raw": _stringify(canonical.get("funded_at")),
        }


def _stringify(value: Any) -> str | None:
    """Liefert den Original-Wert als getrimmten String oder None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    return s or None


def _stringify_plz(value: Any) -> str | None:
    """PLZ als String — pandas liest 5-stellige PLZ oft als float (12345.0)."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return str(int(value))
    s = str(value).strip()
    return s or None


def validate_beneficiary_rows(rows: list[dict[str, Any]], params: BeneficiaryHarvestParams) -> list[str]:
    """Fachliche Vorvalidierung eines Quellensnapshots.

    Harte Fehler verhindern den Austausch des bisherigen Bestands. Fehlende
    optionale Angaben bleiben dagegen eine sichtbar auswertbare Qualitätslücke.
    """
    errors: list[str] = []
    if not params.fonds or not params.periode or not params.country_code:
        errors.append("Quellenkontext Fonds, Förderperiode oder Land fehlt.")
    for row in rows:
        if row.get("_skip_reason"):
            errors.append(f"Zeile {row.get('_row_number')}: Begünstigtenname fehlt.")
            continue
        nr = row.get("_row_number")
        total = parse_amount(row.get("cost_total_raw"))
        eu = parse_amount(row.get("cost_eu_funding_raw"))
        if total is not None and total < 0:
            errors.append(f"Zeile {nr}: Gesamtkosten dürfen nicht negativ sein.")
        if eu is not None and eu < 0:
            errors.append(f"Zeile {nr}: EU-Anteil darf nicht negativ sein.")
        if total is not None and eu is not None and eu > total:
            errors.append(f"Zeile {nr}: EU-Anteil ist größer als Gesamtkosten.")
        start, end = parse_date(row.get("project_start_raw")), parse_date(row.get("project_end_raw"))
        if start and end and start > end:
            errors.append(f"Zeile {nr}: Projektbeginn liegt nach Projektende.")
        lat, lon = row.get("latitude"), row.get("longitude")
        if lat is not None and not -90 <= float(lat) <= 90:
            errors.append(f"Zeile {nr}: Breitengrad außerhalb des gültigen Bereichs.")
        if lon is not None and not -180 <= float(lon) <= 180:
            errors.append(f"Zeile {nr}: Längengrad außerhalb des gültigen Bereichs.")
    return errors


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isnan(f):
            return None
        return f
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


# ── Hauptfunktion ─────────────────────────────────────────────────────────────


def run_beneficiary_harvest(
    db: Session, params: BeneficiaryHarvestParams,
) -> dict[str, Any]:
    """Phase 6a §3 — Smart-Mode-Harvest in die zentrale Tabelle.

    Ablauf:
      1. ``BeneficiaryHarvestRun`` mit status=running anlegen.
      2. Bei mode=force: alle Records der Quelle vorab loeschen.
      3. Zeilen aus der Datei iterieren, kanonisch + raw mappen.
      4. Pro Zeile Insert-Statement bauen — modusabhaengig:
           smart        → ON CONFLICT DO NOTHING
           full-refresh → ON CONFLICT DO UPDATE
           force        → reiner Insert (Pre-Delete hat geleert)
      5. Bei rowcount > 0 → inserted, sonst skipped.
      6. Run finalisieren mit records_seen / inserted / skipped / failed.
    """
    if not params.source_key:
        raise ValueError("source_key ist Pflicht.")

    mode: HarvestMode = params.mode or "snapshot"
    triggered_by = params.triggered_by or "cli"

    if mode not in ("smart", "full-refresh", "force", "snapshot"):
        raise ValueError("mode muss smart|full-refresh|force|snapshot sein.")

    # Die gesamte Datei vor jedem destruktiven Schritt parsen. So kann eine
    # kaputte/anders strukturierte Download-Datei nie den letzten guten Stand
    # einer Quelle leeren.
    if not params.file_content:
        raise ValueError("file_content ist Pflicht.")
    parsed_rows = list(parse_xlsx_or_csv(
        params.file_content, file_name=params.file_name or "upload.xlsx",
        sheet=params.sheet_name, header_row=params.header_row,
        field_mapping=params.field_mapping,
    ))
    valid_rows = [row for row in parsed_rows if not row.get("_skip_reason")]
    if not valid_rows:
        raise ValueError("Keine valide Begünstigtenzeile bzw. keine Namensspalte erkannt.")
    validation_errors = validate_beneficiary_rows(parsed_rows, params)
    if validation_errors:
        preview = " ".join(validation_errors[:8])
        suffix = " …" if len(validation_errors) > 8 else ""
        raise ValueError(f"Snapshot abgewiesen: {preview}{suffix}")

    # ── Snapshot/force: erst nach erfolgreichem Parse löschen ──
    force_deleted_count = 0
    if mode in ("force", "snapshot"):
        force_deleted_count = (
            db.query(BeneficiaryRecord)
            .filter(BeneficiaryRecord.source_key == params.source_key)
            .delete(synchronize_session=False)
        )
        # Noch nicht committen: Snapshot-Loeschung und neue Records sind eine
        # Transaktion. Bei einem Fehler bleibt der vorherige Quellenstand intakt.
        db.flush()
        log.warning(
            "Beneficiary-Harvest mode=%s: %d bestehende Records aus '%s' geloescht.",
            mode, force_deleted_count, params.source_key,
        )

    # ── Run-Eintrag (status=running) ──
    run_id = str(uuid.uuid4())
    run = BeneficiaryHarvestRun(
        id=run_id,
        source_key=params.source_key,
        triggered_by=triggered_by,
        status="running",
        parameters={
            "mode": mode,
            "bundesland": params.bundesland,
            "fonds": params.fonds,
            "periode": params.periode,
            "country_code": params.country_code,
            "file_name": params.file_name,
            "sheet_name": (
                str(params.sheet_name) if params.sheet_name is not None else None
            ),
            "header_row": params.header_row,
            "field_mapping": params.field_mapping or {},
            "force_deleted_before": force_deleted_count if mode == "force" else None,
        },
    )
    db.add(run)
    db.flush()

    seen = inserted = skipped = failed = 0
    error_msg: str | None = None
    if mode == "force" and force_deleted_count:
        error_msg = (
            f"force-mode: {force_deleted_count} bestehende Records vorab geloescht."
        )

    try:
        for parsed in parsed_rows:
            seen += 1

            if parsed.get("_skip_reason"):
                # Zeilen ohne Begünstigtenname werden gezaehlt aber als
                # failed gewertet — sind keine valide Beneficiary-Zeile.
                failed += 1
                continue

            try:
                record_hash = compute_record_hash(parsed, params.source_key)
                cost_total = parse_amount(parsed.get("cost_total_raw"))
                cost_eu = parse_amount(parsed.get("cost_eu_funding_raw"))
                project_start = parse_date(parsed.get("project_start_raw"))
                project_end = parse_date(parsed.get("project_end_raw"))
                funded_at = parse_date(parsed.get("funded_at_raw"))

                values = {
                    "source_key": params.source_key,
                    "source_record_id": record_hash,
                    "upload_run_id": run_id,
                    "source_filename": params.file_name,
                    "source_sheet": (
                        str(params.sheet_name)
                        if params.sheet_name is not None else None
                    ),
                    "source_row_number": parsed.get("_row_number"),
                    "beneficiary_name": parsed["beneficiary_name"],
                    "beneficiary_name_normalized": _normalize_company_name_simple(
                        parsed["beneficiary_name"]
                    ),
                    "project_name": parsed.get("project_name"),
                    "project_aktenzeichen": parsed.get("project_aktenzeichen"),
                    "project_description": parsed.get("project_description"),
                    "bundesland": params.bundesland,
                    "fonds": params.fonds,
                    "periode": params.periode,
                    "country_code": params.country_code,
                    "location": parsed.get("location"),
                    "landkreis": parsed.get("landkreis"),
                    "plz": parsed.get("plz"),
                    "nuts_code": parsed.get("nuts_code"),
                    "latitude": parsed.get("latitude"),
                    "longitude": parsed.get("longitude"),
                    "cost_total_raw": parsed.get("cost_total_raw"),
                    "cost_total": cost_total,
                    "cost_eu_funding_raw": parsed.get("cost_eu_funding_raw"),
                    "cost_eu_funding": cost_eu,
                    "currency": parsed.get("currency"),
                    "project_start_raw": parsed.get("project_start_raw"),
                    "project_start": project_start,
                    "project_end_raw": parsed.get("project_end_raw"),
                    "project_end": project_end,
                    "funded_at_raw": parsed.get("funded_at_raw"),
                    "funded_at": funded_at,
                    "raw_payload": parsed.get("raw_row") or {},
                }

                stmt = pg_insert(BeneficiaryRecord).values(**values)
                if mode == "smart":
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["source_key", "source_record_id"],
                    )
                elif mode == "full-refresh":
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["source_key", "source_record_id"],
                        set_={
                            k: getattr(stmt.excluded, k) for k in (
                                "upload_run_id", "source_filename", "source_sheet",
                                "source_row_number",
                                "beneficiary_name", "beneficiary_name_normalized",
                                "project_name", "project_aktenzeichen",
                                "project_description",
                                "bundesland", "fonds", "periode", "country_code",
                                "location", "landkreis", "plz", "nuts_code",
                                "latitude", "longitude",
                                "cost_total_raw", "cost_total",
                                "cost_eu_funding_raw", "cost_eu_funding",
                                "currency",
                                "project_start_raw", "project_start",
                                "project_end_raw", "project_end",
                                "funded_at_raw", "funded_at",
                                "raw_payload",
                            )
                        },
                    )
                # snapshot/force: reiner Insert (Quelle wurde nach Validierung geleert).
                result = db.execute(stmt)
                rc = result.rowcount or 0
                if mode == "smart":
                    if rc > 0:
                        inserted += 1
                    else:
                        skipped += 1
                else:
                    if rc > 0:
                        inserted += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning(
                    "Beneficiary-Upsert fehlgeschlagen (row=%s): %s",
                    parsed.get("_row_number"), exc,
                )

        # Commit am Ende — XLSX sind klein genug fuer eine Transaktion.
        db.commit()

        run.status = "ok" if failed == 0 else "partial"
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("Beneficiary-Harvest fehlgeschlagen")
        run.status = "failed"
        error_msg = str(exc)
    finally:
        run.records_seen = seen
        run.records_inserted = inserted
        run.records_skipped = skipped
        run.records_failed = failed
        run.error_message = error_msg
        run.finished_at = datetime.now(timezone.utc)
        try:
            # Nach Rollback ist der Run nicht mehr in der Session; ihn erneut
            # anhaengen, damit der fehlgeschlagene Lauf trotzdem auditierbar ist.
            if run.status == "failed":
                db.add(run)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()

    return {
        "run_id": run_id,
        "status": run.status,
        "mode": mode,
        "source_key": params.source_key,
        "records_seen": seen,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "records_failed": failed,
        "error": error_msg,
    }
