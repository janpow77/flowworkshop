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

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from auditcore_funding_sources import workshop as _funding
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
# Hash-Felder, Grenzen für namenlose Zeilen, kanonische Aliase und
# Fonds-Spalten stehen im Profil flowworkshop.beneficiaries von
# auditcore_funding_sources. Die Namen bleiben für Skripte erhalten.
_PROFIL = _funding.profile()

# Reihenfolge ist deterministisch — Änderungen invalidieren bestehende IDs.
_HASH_FIELDS: tuple[str, ...] = tuple(_PROFIL["hash_fields"])

# Zeilen ohne Begünstigtennamen: bis zu diesem Anteil gelten sie als
# Leer-, Summen- oder Fußnotenzeilen und werden übersprungen. Darüber deutet
# es auf eine falsche Kopfzeile hin — dann wird der Snapshot abgewiesen.
NAMENLOS_MAX_ANTEIL = _PROFIL["nameless"]["max_share"]
NAMENLOS_TOLERANZ = _PROFIL["nameless"]["tolerance"]
# Unabhängig von der Stückzahl: mehr als die Hälfte ohne Namen wird nie
# akzeptiert — dann stimmt die Kopfzeile mit Sicherheit nicht.
NAMENLOS_HARTE_GRENZE = _PROFIL["nameless"]["hard_limit"]

# Kanonische Aliase, die der Parser im Spalten-Mapping erwartet.
_CANONICAL_ALIASES: tuple[str, ...] = tuple(_PROFIL["canonical_aliases"])

# Spaltennamen, unter denen die Länder den Fonds führen.
_FONDS_SPALTEN: tuple[str, ...] = tuple(_PROFIL["fund_columns"])


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


# Hash, Normalisierung, Spaltenerkennung und Parser stammen aus
# auditcore_funding_sources (Profil flowworkshop.beneficiaries). Die Namen
# bleiben als Kompatibilitätsschicht erhalten; das Verhalten ist durch die
# Charakterisierung des Originals (a05bb21) belegt.


def _normalize_for_hash(value: Any) -> str:
    """Lowercase + Whitespace-Kompaktor für den Hash-Input."""
    return _funding.normalize_for_hash(value)


def compute_record_hash(row: dict[str, Any], source_key: str) -> str:
    """Stabile, deterministische ID einer Beneficiary-Zeile (SHA-256, 32 Hex)."""
    return _funding.compute_record_hash(row, source_key)


def _normalize_company_name_simple(value: Any) -> str:
    """Suchform für ``beneficiary_name_normalized`` (ohne Rechtsform-Strip)."""
    return _funding.normalize_company_name_simple(value)


def _detect_canonical_columns(
    headers: list[str], explicit_mapping: dict[str, str] | None,
) -> dict[str, str]:
    """Mappt Spalten-Header auf kanonische Aliase (``{alias: original_header}``)."""
    return _funding.detect_canonical_columns(headers, explicit_mapping)


def parse_xlsx_or_csv(
    content: bytes,
    *,
    file_name: str,
    sheet: str | int | None = None,
    header_row: int = 0,
    field_mapping: dict[str, str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Parser für XLSX/CSV/PDF. Pro Zeile ein Dict mit ``raw_row``, ``mapping``,
    kanonischen Feldern und ``_row_number``; namenlose Zeilen tragen
    ``_skip_reason='no_name'``.

    XLSX und CSV liest auditcore_funding_sources ohne pandas mit der
    Typinferenz des bisherigen Parsers (``typing="legacy"``). Das PDF des
    Saarlands bleibt beim anwendungseigenen Leser.
    """
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""
    if ext == "pdf":
        # Das Saarland veröffentlicht seine Liste nur als PDF. Die Datei
        # enthält echten Text, die Tabelle lässt sich also direkt auslesen.
        from services.pdf_vorhabenliste import lies_vorhabenliste
        df = lies_vorhabenliste(content)
        rows = _funding.map_rows(
            list(df.columns), df.itertuples(index=False, name=None), field_mapping,
        )
    elif ext in ("xlsx", "xls", "xlsm", "csv"):
        rows = _funding.parse_file(
            content, file_name, sheet=sheet, header_row=header_row,
            field_mapping=field_mapping,
        )
    else:
        raise ValueError(
            f"Beneficiary-Harvest nur fuer XLSX/XLS/CSV/PDF, nicht '{ext}' "
            f"(file_name={file_name})"
        )
    yield from rows


def _stringify(value: Any) -> str | None:
    """Liefert den Original-Wert als getrimmten String oder None."""
    return _funding.stringify(value)


def _stringify_plz(value: Any) -> str | None:
    """PLZ als String — 12345.0 wird '12345'."""
    return _funding.stringify_plz(value)


def validate_beneficiary_rows(rows: list[dict[str, Any]], params: BeneficiaryHarvestParams) -> list[str]:
    """Fachliche Vorvalidierung eines Quellensnapshots.

    Harte Fehler verhindern den Austausch des bisherigen Bestands; die
    Grenzen für namenlose Zeilen stehen im Profil der Bibliothek.
    """
    context = _funding.SnapshotContext(
        source_key=params.source_key,
        bundesland=params.bundesland,
        fonds=params.fonds,
        periode=params.periode,
        country_code=params.country_code,
    )
    return _funding.validate_rows(rows, context)


def _coerce_float(value: Any) -> float | None:
    return _funding.coerce_float(value)


def filtere_nach_fonds(rows: list[dict[str, Any]], fonds: str | None) -> tuple[list[dict[str, Any]], int]:
    """Behält bei einer fondsübergreifenden Liste nur den eigenen Fonds.

    Liefert (verbleibende Zeilen, Anzahl entfernter Zeilen).
    """
    return _funding.filter_by_fund(rows, fonds)


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
    parsed_rows, fremder_fonds = filtere_nach_fonds(parsed_rows, params.fonds)
    if fremder_fonds:
        log.info(
            "Beneficiary-Harvest %s: %d Zeilen anderer Fonds übersprungen "
            "(Quelle ist %s).", params.source_key, fremder_fonds, params.fonds,
        )

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
                    # Mehrere Länder führen in den Orts- und Kreisspalten reine
                    # Zahlen (Sachsen z.B. einen Gemeindeschlüssel). Ohne die
                    # Wandlung nach Text bricht PostgreSQL den Insert ab und
                    # reisst mit ihm die ganze Transaktion.
                    "location": _stringify(parsed.get("location")),
                    "landkreis": _stringify(parsed.get("landkreis")),
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
                else:
                    # snapshot/force: die Quelle wurde nach der Validierung
                    # geleert, es ist also ein reiner Insert. Trotzdem
                    # Konflikte abfangen: manche Länder führen Vor- und
                    # Nachname in getrennten Spalten, wodurch zwei echte
                    # Zeilen denselben Datensatz-Hash ergeben. Ohne diese
                    # Klausel bricht die erste Kollision den gesamten Import.
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["source_key", "source_record_id"],
                    )

                # Jede Zeile in einem eigenen Savepoint: eine fehlerhafte Zeile
                # darf die Transaktion nicht vergiften. Vorher scheiterten nach
                # dem ersten Fehler sämtliche Folgezeilen mit
                # "current transaction is aborted".
                with db.begin_nested():
                    result = db.execute(stmt)
                rc = result.rowcount or 0
                if rc > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning(
                    "Beneficiary-Upsert fehlgeschlagen (row=%s): %s",
                    parsed.get("_row_number"), exc,
                )

        # Commit am Ende — XLSX sind klein genug fuer eine Transaktion.
        db.commit()

        lauf_status = "ok" if failed == 0 else "partial"
        run.status = lauf_status
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("Beneficiary-Harvest fehlgeschlagen")
        lauf_status = "failed"
        run.status = lauf_status
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
            if lauf_status == "failed":
                db.add(run)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()

    return {
        "run_id": run_id,
        # Bewusst die lokale Variable statt run.status: nach einem Rollback ist
        # die Zeile fort, und ein Zugriff auf das ORM-Objekt wuerde mit
        # ObjectDeletedError die eigentliche Fehlerursache verdecken.
        "status": lauf_status,
        "mode": mode,
        "source_key": params.source_key,
        "records_seen": seen,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "records_failed": failed,
        "error": error_msg,
    }
