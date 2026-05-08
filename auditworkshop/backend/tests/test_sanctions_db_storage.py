"""
Phase 6c — Tests fuer die DB-Persistenz der Sanctions-Eintraege.

Getestet wird der gesamte CSV → DB → In-Memory-Index-Flow gegen die
echte Postgres-Datenbank des Backends (im Container ueber
``/app/data/...`` und ``DATABASE_URL``). Pro Test wird eine kuenstliche
``source_key``-Praeefix-Reihe verwendet (``test_phase6c_<run-id>_<key>``),
sodass Produktivdaten nicht beeinflusst werden — die Cleanup-Fixture
loescht alle so eingefuegten Zeilen am Ende.

Wenn die Tests ausserhalb des Containers laufen (kein DB-Zugriff), werden
sie via ``pytest.skip`` uebersprungen.
"""
from __future__ import annotations

import csv
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

# Backend-Verzeichnis importierbar machen
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Fixtures ─────────────────────────────────────────────────────────────────


_CSV_HEADERS = [
    "id", "schema", "name", "aliases", "birth_date", "countries",
    "addresses", "identifiers", "sanctions", "phones", "emails",
    "program_ids", "dataset", "first_seen", "last_seen", "last_change",
]


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            full = {h: "" for h in _CSV_HEADERS}
            full.update(row)
            writer.writerow(full)


@pytest.fixture(scope="module")
def db_session_or_skip():
    """SQLAlchemy-Session aus ``database.SessionLocal``. Skippt, wenn die
    DB nicht erreichbar ist (z.B. lokale Test-Runs ausserhalb Docker).
    """
    try:
        from database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        # Connectivity-Check
        db.execute(text("SELECT 1")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB nicht erreichbar: {exc}")

    # Sicherstellen, dass das Modell registriert ist und die Tabelle existiert
    try:
        from database import Base, engine
        from models.sanctions_entries import SanctionsEntry  # noqa: F401
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"Tabelle workshop_sanctions_entries nicht anlegbar: {exc}")

    yield db
    db.close()


@pytest.fixture
def test_source_key(db_session_or_skip):
    """Erzeugt einen einmaligen Source-Key pro Test und raeumt am Ende auf."""
    key = f"test_phase6c_{uuid.uuid4().hex[:12]}"
    yield key
    # Cleanup
    from sqlalchemy import text
    db_session_or_skip.execute(
        text(
            "DELETE FROM workshop_sanctions_entries WHERE source_key = :k"
        ),
        {"k": key},
    )
    db_session_or_skip.commit()


@pytest.fixture
def mini_csv(tmp_path):
    """Erzeugt eine Mini-CSV mit drei Eintraegen (zwei Personen, eine Org)."""
    csv_path = tmp_path / "mini_sanctions.csv"
    _write_csv(csv_path, [
        {
            "id": "T-001",
            "schema": "Person",
            "name": "Vladimir Vladimirovich Putin",
            "aliases": "Wladimir Putin;Путин Владимир",
            "birth_date": "1952-10-07",
            "countries": "ru",
            "sanctions": "Test EU UKR-2022/336",
            "first_seen": "2022-02-25T00:00:00",
            "last_seen": "2026-05-08T00:00:00",
        },
        {
            "id": "T-002",
            "schema": "Person",
            "name": "Kim Jong Un",
            "aliases": "Kim Jung-eun",
            "countries": "kp",
            "sanctions": "Test UN DPRK",
        },
        {
            "id": "T-003",
            "schema": "Organization",
            "name": "Acme Defense GmbH",
            "aliases": "Acme Defense Ltd",
            "countries": "de",
            "sanctions": "Test EU UKR-2024/100",
        },
    ])
    return csv_path


# ── Test 1: CSV → DB Upsert ─────────────────────────────────────────────────


def test_load_from_csv_to_db_inserts_rows(db_session_or_skip, mini_csv, test_source_key):
    """``load_from_csv_to_db`` schreibt alle CSV-Zeilen idempotent in die DB."""
    from services.sanctions_service import load_from_csv_to_db
    from models.sanctions_entries import SanctionsEntry

    summary = load_from_csv_to_db(
        db_session_or_skip, test_source_key, str(mini_csv),
    )
    assert summary["records_seen"] == 3
    assert summary["records_skipped"] == 0
    assert summary["records_upserted"] >= 1

    rows = (
        db_session_or_skip.query(SanctionsEntry)
        .filter(SanctionsEntry.source_key == test_source_key)
        .order_by(SanctionsEntry.entry_id.asc())
        .all()
    )
    assert len(rows) == 3
    ids = [r.entry_id for r in rows]
    assert ids == ["T-001", "T-002", "T-003"]

    # Originalwert verbatim erhalten
    putin = next(r for r in rows if r.entry_id == "T-001")
    assert putin.name == "Vladimir Vladimirovich Putin"
    # Aliases als JSONB-Liste
    assert isinstance(putin.aliases, list)
    assert "Wladimir Putin" in putin.aliases
    # Normalisierter Helper-String
    assert "putin" in putin.name_normalized.lower()
    # raw_payload enthaelt die ganze Zeile
    assert putin.raw_payload.get("birth_date") == "1952-10-07"
    assert putin.raw_payload.get("sanctions") == "Test EU UKR-2022/336"


# ── Test 2: DB → In-Memory-Index Rebuild ────────────────────────────────────


def test_load_index_from_db_rebuilds_records(db_session_or_skip, mini_csv, test_source_key):
    """``load_index_from_db`` rekonstruiert den In-Memory-Index aus DB-Rows."""
    from services.sanctions_service import (
        load_from_csv_to_db, load_index_from_db, SanctionsSource,
    )

    load_from_csv_to_db(db_session_or_skip, test_source_key, str(mini_csv))

    src = SanctionsSource(
        key=test_source_key,
        display_name="Test-Quelle",
        issuer="—",
        download_url="file:///dev/null",
        csv_path=str(mini_csv),
        license="Test",
    )
    src.csv_path = str(mini_csv)  # ENV-Override neutralisieren

    idx = load_index_from_db(db_session_or_skip, src)
    assert idx.is_loaded()
    stats = idx.stats()
    assert stats["source_key"] == test_source_key
    assert stats["total_entries"] == 3
    assert stats["persons"] == 2
    assert stats["organizations"] == 1


# ── Test 3: Search-Konsistenz CSV vs DB ─────────────────────────────────────


def test_search_consistency_csv_vs_db(db_session_or_skip, mini_csv, test_source_key):
    """Die Suche auf einem DB-aufgebauten Index liefert dieselben Treffer
    wie auf einem CSV-aufgebauten Index (gleiche Quelle, gleicher Inhalt).
    """
    from services.sanctions_service import (
        SanctionsListIndex, SanctionsSource,
        load_from_csv_to_db, load_index_from_db,
    )

    src_csv = SanctionsSource(
        key=test_source_key,
        display_name="Test-Quelle (CSV-Source)",
        issuer="—",
        download_url="file:///dev/null",
        csv_path=str(mini_csv),
        license="Test",
    )
    src_csv.csv_path = str(mini_csv)
    csv_idx = SanctionsListIndex(src_csv)
    csv_idx.load(str(mini_csv))

    load_from_csv_to_db(db_session_or_skip, test_source_key, str(mini_csv))
    db_idx = load_index_from_db(db_session_or_skip, src_csv)

    # Dieselbe Query auf beiden Indizes
    csv_hits = csv_idx.search("Putin", limit=10, min_score=70.0)
    db_hits = db_idx.search("Putin", limit=10, min_score=70.0)

    assert len(csv_hits) == len(db_hits) >= 1
    # Top-Treffer haben identisches Name + Score (bis auf Reihenfolge)
    csv_top = sorted([(h.name, h.score) for h in csv_hits])
    db_top = sorted([(h.name, h.score) for h in db_hits])
    assert csv_top == db_top


# ── Test 4: refresh_run_id wird auf SanctionsEntry gesetzt ──────────────────


def test_refresh_run_id_propagates_to_entry(db_session_or_skip, mini_csv, test_source_key):
    """Wenn beim Upsert ein ``refresh_run_id`` gesetzt wird, landet er als
    FK auf jeder neuen oder aktualisierten Zeile.
    """
    from sqlalchemy import text
    from services.sanctions_service import load_from_csv_to_db
    from models.sanctions_entries import SanctionsEntry

    # Wir erzeugen einen Refresh-Run-Datensatz, dessen id als FK genommen wird.
    insert_run = text(
        "INSERT INTO workshop_sanctions_refresh "
        "(started_at, triggered_by, status) "
        "VALUES (now(), 'test:phase6c', 'running') RETURNING id"
    )
    refresh_run_id = int(db_session_or_skip.execute(insert_run).scalar())
    db_session_or_skip.commit()
    try:
        load_from_csv_to_db(
            db_session_or_skip, test_source_key, str(mini_csv),
            refresh_run_id=refresh_run_id,
        )
        rows = (
            db_session_or_skip.query(SanctionsEntry)
            .filter(SanctionsEntry.source_key == test_source_key)
            .all()
        )
        assert len(rows) == 3
        assert all(r.refresh_run_id == refresh_run_id for r in rows)
    finally:
        # Run aufraeumen
        db_session_or_skip.execute(
            text(
                "DELETE FROM workshop_sanctions_refresh WHERE id = :i"
            ),
            {"i": refresh_run_id},
        )
        db_session_or_skip.commit()


# ── Test 5: Idempotenz — zweiter Refresh, 0 neue Zeilen ─────────────────────


def test_smart_idempotency_second_run_no_new_rows(
    db_session_or_skip, mini_csv, test_source_key,
):
    """Wird derselbe Backfill zweimal ausgefuehrt, fuegt der zweite Lauf
    keine neuen Zeilen ein. Smart-Mode heisst hier: ON CONFLICT DO UPDATE
    fuer die bestehenden Eintraege, kein Wachstum der Tabelle.
    """
    from services.sanctions_service import load_from_csv_to_db
    from models.sanctions_entries import SanctionsEntry

    # 1. Run
    summary_1 = load_from_csv_to_db(
        db_session_or_skip, test_source_key, str(mini_csv),
    )
    count_after_first = (
        db_session_or_skip.query(SanctionsEntry)
        .filter(SanctionsEntry.source_key == test_source_key)
        .count()
    )
    assert count_after_first == 3
    assert summary_1["records_seen"] == 3

    # 2. Run — gleiche CSV
    summary_2 = load_from_csv_to_db(
        db_session_or_skip, test_source_key, str(mini_csv),
    )
    count_after_second = (
        db_session_or_skip.query(SanctionsEntry)
        .filter(SanctionsEntry.source_key == test_source_key)
        .count()
    )
    assert count_after_second == count_after_first
    assert summary_2["records_seen"] == 3


# ── Test 6: Backfill-Skript-Funktion (idempotent, ON CONFLICT DO NOTHING) ───


def test_backfill_source_idempotent(db_session_or_skip, mini_csv, test_source_key):
    """``backfill_sanctions_entries.backfill_source`` ist idempotent:
    zweiter Lauf liefert ``records_inserted == 0`` und ``records_skipped == 3``.
    """
    from scripts.backfill_sanctions_entries import backfill_source
    from services.sanctions_service import SanctionsSource

    src = SanctionsSource(
        key=test_source_key,
        display_name="Test",
        issuer="—",
        download_url="file:///dev/null",
        csv_path=str(mini_csv),
        license="Test",
    )
    src.csv_path = str(mini_csv)

    first = backfill_source(src)
    assert first["status"] == "ok"
    assert first["records_seen"] == 3
    assert first["records_inserted"] == 3
    assert first["records_skipped"] == 0

    second = backfill_source(src)
    assert second["status"] == "ok"
    assert second["records_seen"] == 3
    assert second["records_inserted"] == 0
    assert second["records_skipped"] == 3


# ── Test 7: Skipped Zeilen ohne id/name ─────────────────────────────────────


def test_load_from_csv_to_db_skips_invalid_rows(
    db_session_or_skip, tmp_path, test_source_key,
):
    """Zeilen ohne ``id`` oder ``name`` werden als ``records_skipped`` gezaehlt."""
    from services.sanctions_service import load_from_csv_to_db

    csv_path = tmp_path / "broken.csv"
    _write_csv(csv_path, [
        {"id": "OK-1", "schema": "Person", "name": "Valid Name"},
        {"id": "", "schema": "Person", "name": "No ID Person"},  # skip
        {"id": "OK-2", "schema": "Person", "name": ""},  # skip
        {"id": "OK-3", "schema": "Organization", "name": "Valid Org"},
    ])

    summary = load_from_csv_to_db(
        db_session_or_skip, test_source_key, str(csv_path),
    )
    assert summary["records_seen"] == 4
    assert summary["records_skipped"] == 2
    # Inserted = 2 (OK-1 + OK-3)
    from models.sanctions_entries import SanctionsEntry
    rows = (
        db_session_or_skip.query(SanctionsEntry)
        .filter(SanctionsEntry.source_key == test_source_key)
        .all()
    )
    assert len(rows) == 2
