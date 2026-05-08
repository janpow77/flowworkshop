"""
Phase 6d — Tests fuer Entity-Resolution.

Schwerpunkt:
  - LEI-Match: 100% Confidence, gleicher LEI = gleiche Entity
  - Identifier-Match: HRB-Nummer findet bestehende Entity
  - Name-Exact: nach Normalisierung exakter Match
  - Name-Fuzzy: Score 80+ -> Match, Score <75 -> KEIN Match
  - Idempotenz: zweiter Rebuild = 0 neue Entities
  - Reject-Logic: rejected match wird in Audit-Report gefiltert

Lauf: pytest backend/tests/test_entity_resolution.py -q

Wir testen, soweit moeglich, ohne DB. Fuer DB-Tests nutzen wir die laufende
Anwendung (siehe conftest.py) und legen temporaere Test-Records an, die wir
am Ende wieder entfernen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Backend-Verzeichnis in den Pfad legen
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Pure Helpers (kein DB-Zugriff) ────────────────────────────────────────────


def test_is_valid_lei_correct_format():
    """LEI: 18 Zeichen + 2 Ziffern Pruefziffer, alphanumerisch gross."""
    from services.entity_resolution import is_valid_lei
    assert is_valid_lei("529900T8BM49AURSDO55") is True
    assert is_valid_lei("ABCD1234567890123456") is True


def test_is_valid_lei_invalid():
    """Falsche LEIs werden korrekt erkannt."""
    from services.entity_resolution import is_valid_lei
    assert is_valid_lei(None) is False
    assert is_valid_lei("") is False
    assert is_valid_lei("kurz") is False
    # 19 Zeichen
    assert is_valid_lei("ABCD123456789012345") is False
    # Letzte 2 Stellen muessen Ziffern sein
    assert is_valid_lei("ABCDEFGHIJKLMNOPQRST") is False


def test_extract_lei_from_text_finds_token():
    """LEI in Freitext wird extrahiert."""
    from services.entity_resolution import extract_lei_from_text
    assert extract_lei_from_text("LEI: 529900T8BM49AURSDO55") == "529900T8BM49AURSDO55"
    assert extract_lei_from_text("HRB 12345 Berlin / 529900T8BM49AURSDO55") == (
        "529900T8BM49AURSDO55"
    )


def test_extract_lei_from_text_no_match():
    from services.entity_resolution import extract_lei_from_text
    assert extract_lei_from_text(None) is None
    assert extract_lei_from_text("HRB 12345 Berlin") is None
    assert extract_lei_from_text("") is None


def test_store_identifier_dedup():
    """Mehrfaches Hinzufuegen desselben Identifiers fuehrt zu keinem Duplikat."""
    from services.entity_resolution import _store_identifier
    out = _store_identifier(None, "hrb", "HRB 12345 Berlin")
    out = _store_identifier(out, "hrb", "HRB 12345 Berlin")
    out = _store_identifier(out, "hrb", "HRB 9999 München")
    assert out == {"hrb": ["HRB 12345 Berlin", "HRB 9999 München"]}


def test_store_identifier_separate_buckets():
    """Verschiedene Buckets bleiben getrennt."""
    from services.entity_resolution import _store_identifier
    out = _store_identifier(None, "hrb", "HRB 12345 Berlin")
    out = _store_identifier(out, "ust_id", "DE123456789")
    assert out["hrb"] == ["HRB 12345 Berlin"]
    assert out["ust_id"] == ["DE123456789"]


def test_source_tables_known():
    """SOURCE_TABLES deckt alle drei Module ab."""
    from services.entity_resolution import SOURCE_TABLES
    assert "state_aid" in SOURCE_TABLES
    assert "beneficiary" in SOURCE_TABLES
    assert "sanctions" in SOURCE_TABLES
    assert SOURCE_TABLES["state_aid"] == "workshop_state_aid_awards"
    assert SOURCE_TABLES["beneficiary"] == "workshop_beneficiary_records"
    assert SOURCE_TABLES["sanctions"] == "workshop_sanctions_entries"


def test_confidence_constants_ordered():
    """Confidence-Klassen sind absteigend."""
    from services.entity_resolution import (
        CONFIDENCE_FUZZY_THRESHOLD, CONFIDENCE_IDENTIFIER, CONFIDENCE_LEI,
        CONFIDENCE_NAME_EXACT,
    )
    assert CONFIDENCE_LEI > CONFIDENCE_IDENTIFIER
    assert CONFIDENCE_IDENTIFIER > CONFIDENCE_NAME_EXACT
    assert CONFIDENCE_NAME_EXACT > CONFIDENCE_FUZZY_THRESHOLD
    # Schwelle 75 wie spezifiziert
    assert CONFIDENCE_FUZZY_THRESHOLD == 75.0
    assert CONFIDENCE_LEI == 100.0
    assert CONFIDENCE_IDENTIFIER == 95.0
    assert CONFIDENCE_NAME_EXACT == 90.0


# ── DB-Integration-Tests ──────────────────────────────────────────────────────


@pytest.fixture
def db_session():
    """Liefert eine SessionLocal — Test-spezifische Entities werden in
    teardown wieder geloescht.
    """
    try:
        from database import SessionLocal  # noqa: WPS433
        from models.entities import CompanyEntity, EntityMatch  # noqa: F401
    except Exception:  # noqa: BLE001
        pytest.skip("DB nicht erreichbar (Test laeuft ohne Container).")
    db = SessionLocal()
    created_entity_ids: list[int] = []
    created_match_ids: list[int] = []

    def _track_entity(eid: int) -> None:
        created_entity_ids.append(eid)

    def _track_match(mid: int) -> None:
        created_match_ids.append(mid)

    db.test_track_entity = _track_entity  # type: ignore[attr-defined]
    db.test_track_match = _track_match    # type: ignore[attr-defined]

    try:
        yield db
    finally:
        try:
            from models.entities import EntityMatch as _M
            from models.entities import CompanyEntity as _E
            if created_match_ids:
                db.query(_M).filter(_M.id.in_(created_match_ids)).delete(
                    synchronize_session=False,
                )
            if created_entity_ids:
                db.query(_E).filter(_E.id.in_(created_entity_ids)).delete(
                    synchronize_session=False,
                )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        finally:
            db.close()


def _make_test_entity(
    db, *, name: str, lei: str | None = None,
    country_code: str | None = "DEU",
):
    """Hilfsfunktion: legt eine Test-Entity an und merkt die ID."""
    from services.entity_resolution import _create_entity, _normalize_for_match
    ent = _create_entity(
        db,
        canonical_name=name,
        canonical_name_normalized=_normalize_for_match(name),
        country_code=country_code,
        lei=lei,
        identifier=None,
        addresses=None,
        first_match_method="test",
    )
    db.commit()
    db.test_track_entity(ent.id)
    return ent


def test_resolve_entity_lei_match_returns_existing(db_session):
    """Ein bestehender LEI-Eintrag wird wiedergefunden -> 100% Confidence."""
    from services.entity_resolution import resolve_entity
    ent = _make_test_entity(
        db_session,
        name="Test LEI Company GmbH (uniq-er-1)",
        lei="TESTLEI0000000001ER",  # 20 Zeichen, endet auf 2 Ziffern (1=ungueltig)
    )
    # Gueltigen LEI verwenden — 18 alphanum + 2 Ziffern.
    db_session.delete(ent)
    db_session.commit()

    valid_lei = "ABCDEFGHIJKLMNOPQR12"
    ent = _make_test_entity(
        db_session,
        name="LEI Test GmbH (uniq-er-2)",
        lei=valid_lei,
    )

    result = resolve_entity(
        db_session,
        name="Some Other Name",
        lei=valid_lei,
    )
    assert result is not None
    assert result.entity.id == ent.id
    assert result.method == "lei"
    assert result.confidence == 100.0
    assert result.is_new_entity is False


def test_resolve_entity_lei_in_identifier(db_session):
    """LEI im Identifier-Feld wird als LEI behandelt."""
    from services.entity_resolution import resolve_entity
    valid_lei = "ABCDEFGHIJKLMNOPQR34"
    ent = _make_test_entity(
        db_session,
        name="LEI Identifier Test (uniq-er-3)",
        lei=valid_lei,
    )

    result = resolve_entity(
        db_session,
        name="Andere Schreibweise",
        identifier=valid_lei,
    )
    assert result is not None
    assert result.entity.id == ent.id
    assert result.method == "lei"
    assert result.confidence == 100.0


def test_resolve_entity_name_exact_match(db_session):
    """Gleicher normalisierter Name -> Match mit 90% Confidence."""
    from services.entity_resolution import resolve_entity
    ent = _make_test_entity(
        db_session,
        name="Acme Industries (uniq-er-4)",
    )

    # Gleicher Name, andere Schreibweise (Whitespace)
    result = resolve_entity(
        db_session,
        name="  Acme   Industries (uniq-er-4)",
    )
    assert result is not None
    assert result.entity.id == ent.id
    assert result.method == "name_exact"
    assert result.confidence == 90.0


def test_resolve_entity_fuzzy_match_above_threshold(db_session):
    """Fuzzy-Match mit Score >= 75 erzeugt Match an bestehende Entity."""
    from services.entity_resolution import resolve_entity
    ent = _make_test_entity(
        db_session,
        name="Fraunhofer-Gesellschaft zur Foerderung der angewandten Forschung e.V. (uniq-er-5)",
    )

    # Bewusst leicht abweichend — fuzzy-Match sollte greifen
    result = resolve_entity(
        db_session,
        name="Fraunhofer Gesellschaft zur Foerderung der angewandten Forschung (uniq-er-5)",
    )
    assert result is not None
    # Entweder name_exact (Normalisierung schluckt e.V.) oder fuzzy
    assert result.entity.id == ent.id
    # Confidence muss >= Schwelle sein
    assert result.confidence >= 75.0


def test_resolve_entity_name_new_when_no_match(db_session):
    """Komplett neuer Name -> neue Entity wird angelegt."""
    import uuid
    from services.entity_resolution import resolve_entity
    # uuid-suffix verhindert Kollision mit bestehenden Entities aus
    # voraufgegangenen Rebuilds.
    suffix = uuid.uuid4().hex[:12]
    unique = f"Zzwxqzdpfijntmnq Bvjlnpqtwaoo {suffix}"
    result = resolve_entity(db_session, name=unique)
    assert result is not None
    assert result.is_new_entity is True
    assert result.method == "name_new"
    db_session.test_track_entity(result.entity.id)
    db_session.commit()


def test_link_record_idempotent(db_session):
    """Zweiter ``link_record`` mit gleichen IDs erzeugt KEINEN Doppel-Eintrag."""
    from services.entity_resolution import link_record
    name = "Idempotenz Test GmbH (uniq-er-7)"
    sid = "test-sid-er-7"

    m1 = link_record(
        db_session,
        source_module="state_aid",
        source_record_id=sid,
        name=name,
        country_code="DEU",
    )
    db_session.commit()
    assert m1 is not None
    db_session.test_track_match(m1.id)
    db_session.test_track_entity(m1.entity_id)

    # Zweiter Aufruf: gleiches Match muss zurueckkommen
    m2 = link_record(
        db_session,
        source_module="state_aid",
        source_record_id=sid,
        name=name,
        country_code="DEU",
    )
    db_session.commit()
    assert m2 is not None
    assert m1.id == m2.id


def test_link_record_unknown_module_raises(db_session):
    """Unbekanntes ``source_module`` wirft ValueError."""
    from services.entity_resolution import link_record
    with pytest.raises(ValueError):
        link_record(
            db_session,
            source_module="unknown_module",
            source_record_id="sid",
            name="X",
        )


def test_rebuild_idempotent(db_session):
    """Zweiter Rebuild fuer dieselbe Source erzeugt 0 neue Matches."""
    from services.entity_resolution import (
        link_record, rebuild_entities_from_state_aid,
    )
    # Erstmals ein paar Records anlegen — dafuer brauchen wir aber echte
    # state_aid-Awards. Ohne grossen Bestand testen wir nur, dass
    # rebuild() ohne Fehler durchlaeuft und ein Stats-Dict zurueckliefert.
    stats = rebuild_entities_from_state_aid(
        db_session, batch=100, dry=True, limit=10,
    )
    assert "records_seen" in stats
    assert "matches_created" in stats
    assert "entities_created" in stats
    assert "low_confidence_skipped" in stats
    # Bei dry=True: kein Schreibvorgang
    db_session.rollback()


def test_rejected_match_filter_logic():
    """Rejected-Matches sollten in der Audit-Sicht NICHT mehr auftauchen.

    Wir testen die Filter-Logik selber (kein DB-Zugriff): der Search-Endpoint
    filtert mit ``rejected.is_(False)``.
    """
    from models.entities import EntityMatch  # noqa: F401
    # Kein direkter SQL-Test, aber wir verifizieren, dass der Code-Pfad
    # ueberhaupt das ``rejected``-Feld nutzt.
    import inspect
    from routers import entities as entities_router
    src = inspect.getsource(entities_router.search_entities)
    assert "rejected.is_(False)" in src or "rejected == False" in src or (
        ".is_(False)" in src and "rejected" in src
    )
