"""
Layer A — Tests fuer den Embedding-Layer (bge-m3).

Pure-Python-Tests:
  - build_embedding_text fuer jedes Modul (richtige Konkatenation)
  - search_semantic mit Mock-Embedding (kein Gateway-Call)
  - upsert idempotent
  - rebuild_module_embeddings mit batch + skip_existing

KEINE Live-Gateway-Tests — die wuerden den Workshop-LLM blockieren. Das
Gateway wird ueber Monkeypatch ersetzt.

Lauf: pytest backend/tests/test_entity_embeddings.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Backend-Verzeichnis in den Pfad legen
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Pure Helpers ──────────────────────────────────────────────────────────────


def test_build_embedding_text_state_aid_dict():
    """state_aid: name | objective | authority."""
    from services.entity_embeddings import build_embedding_text
    record = {
        "beneficiary_name": "Beispiel GmbH",
        "aid_objective": "Forschung und Entwicklung im Bereich Photovoltaik",
        "granting_authority": "BMWK",
    }
    text_input = build_embedding_text(module="state_aid", record=record)
    assert "Beispiel GmbH" in text_input
    assert "Photovoltaik" in text_input
    assert "BMWK" in text_input
    assert " | " in text_input


def test_build_embedding_text_state_aid_skips_empty():
    """Leere Felder werden nicht als '|' ausgegeben."""
    from services.entity_embeddings import build_embedding_text
    record = {
        "beneficiary_name": "Solo GmbH",
        "aid_objective": None,
        "granting_authority": "",
    }
    text_input = build_embedding_text(module="state_aid", record=record)
    assert text_input == "Solo GmbH"


def test_build_embedding_text_beneficiary():
    """beneficiary: name | project_name | description."""
    from services.entity_embeddings import build_embedding_text
    record = {
        "beneficiary_name": "Bauer KG",
        "project_name": "Solarpark Niederbayern",
        "project_description": "Errichtung einer 5 MW PV-Anlage",
    }
    text_input = build_embedding_text(module="beneficiary", record=record)
    assert "Bauer KG" in text_input
    assert "Solarpark Niederbayern" in text_input
    assert "PV-Anlage" in text_input


def test_build_embedding_text_sanctions_with_aliases_list():
    """sanctions: name | aliases (list joined) | program."""
    from services.entity_embeddings import build_embedding_text
    record = {
        "name": "Subject A",
        "aliases": ["A. Subject", "Mr. A"],
        "sanctions_program": "EU FSF Russia",
    }
    text_input = build_embedding_text(module="sanctions", record=record)
    assert "Subject A" in text_input
    assert "A. Subject" in text_input
    assert "EU FSF Russia" in text_input


def test_build_embedding_text_sanctions_with_aliases_string():
    """sanctions: aliases als String wird auch akzeptiert."""
    from services.entity_embeddings import build_embedding_text
    record = {
        "name": "Subject B",
        "aliases": "B. Subject; Mr. B",
        "sanctions_program": None,
    }
    text_input = build_embedding_text(module="sanctions", record=record)
    assert "Subject B" in text_input
    assert "B. Subject" in text_input


def test_build_embedding_text_company_entity_with_address():
    """company_entity: canonical_name | first city."""
    from services.entity_embeddings import build_embedding_text
    record = {
        "canonical_name": "Siemens AG",
        "addresses": [
            {"city": "München", "postal_code": "80333", "country": "DEU"},
            {"city": "Berlin"},
        ],
    }
    text_input = build_embedding_text(module="company_entity", record=record)
    assert "Siemens AG" in text_input
    assert "München" in text_input
    # Nur ERSTE Adresse, nicht alle
    assert "Berlin" not in text_input


def test_build_embedding_text_company_entity_no_address():
    """company_entity: ohne Adressen nur Name."""
    from services.entity_embeddings import build_embedding_text
    record = {
        "canonical_name": "Beispiel AG",
        "addresses": None,
    }
    text_input = build_embedding_text(module="company_entity", record=record)
    assert text_input == "Beispiel AG"


def test_build_embedding_text_unknown_module_raises():
    """Unbekanntes Modul -> ValueError."""
    from services.entity_embeddings import build_embedding_text
    with pytest.raises(ValueError):
        build_embedding_text(module="bogus", record={"name": "x"})


def test_build_embedding_text_works_with_orm_objects():
    """Funktioniert auch mit Objekten (getattr-Pfad), nicht nur dicts."""
    from services.entity_embeddings import build_embedding_text

    class _Fake:
        def __init__(self):
            self.beneficiary_name = "Mock GmbH"
            self.aid_objective = "Forschung"
            self.granting_authority = None

    text_input = build_embedding_text(module="state_aid", record=_Fake())
    assert "Mock GmbH" in text_input
    assert "Forschung" in text_input


def test_valid_modules_constant():
    """Vier Module sind unterstuetzt."""
    from services.entity_embeddings import VALID_MODULES
    assert "state_aid" in VALID_MODULES
    assert "beneficiary" in VALID_MODULES
    assert "sanctions" in VALID_MODULES
    assert "company_entity" in VALID_MODULES


# ── upsert_embedding ──────────────────────────────────────────────────────────


def test_upsert_embedding_validates_module():
    """Unbekanntes Modul wirft ValueError, ohne DB-Zugriff."""
    from services.entity_embeddings import upsert_embedding
    with pytest.raises(ValueError):
        upsert_embedding(
            db=None,  # type: ignore[arg-type]
            module="bogus",
            record_id="1",
            text_input="x",
            embedding=[0.0],
        )


def test_upsert_embedding_validates_record_id():
    """Leere record_id wirft ValueError."""
    from services.entity_embeddings import upsert_embedding
    with pytest.raises(ValueError):
        upsert_embedding(
            db=None,  # type: ignore[arg-type]
            module="state_aid",
            record_id="",
            text_input="x",
            embedding=[0.0] * 1024,
        )


def test_upsert_embedding_skips_empty_text():
    """Leerer text_input liefert None — kein DB-Zugriff."""
    from services.entity_embeddings import upsert_embedding
    out = upsert_embedding(
        db=None,  # type: ignore[arg-type]
        module="state_aid",
        record_id="1",
        text_input="   ",
        embedding=[0.0] * 1024,
    )
    assert out is None


def test_upsert_embedding_validates_dim():
    """Falsche Dim wirft ValueError, kein DB-Zugriff."""
    from services.entity_embeddings import upsert_embedding
    with pytest.raises(ValueError):
        upsert_embedding(
            db=None,  # type: ignore[arg-type]
            module="state_aid",
            record_id="1",
            text_input="some text",
            embedding=[0.0, 1.0, 2.0],  # Dim != 1024
        )


# ── DB-Integration-Tests ──────────────────────────────────────────────────────


@pytest.fixture
def db_session():
    """Liefert eine SessionLocal — Test-spezifische Embeddings werden in
    teardown wieder geloescht.
    """
    try:
        from database import SessionLocal  # noqa: WPS433
        from models.entity_embeddings import EntityEmbedding  # noqa: F401
    except Exception:  # noqa: BLE001
        pytest.skip("DB nicht erreichbar (Test laeuft ohne Container).")
    db = SessionLocal()

    # Sicherstellen, dass die Tabelle existiert. Wenn nicht (z.B. weil das
    # Backend nicht hochgefahren ist), skip.
    try:
        from sqlalchemy import inspect
        ins = inspect(db.bind)
        if not ins.has_table("workshop_entity_embeddings"):
            db.close()
            pytest.skip("workshop_entity_embeddings existiert nicht.")
    except Exception:  # noqa: BLE001
        db.close()
        pytest.skip("DB-Inspektion fehlgeschlagen.")

    test_record_ids: list[str] = []

    def _track(rid: str) -> None:
        test_record_ids.append(rid)

    db.test_track_embedding = _track  # type: ignore[attr-defined]

    try:
        yield db
    finally:
        try:
            from models.entity_embeddings import EntityEmbedding as _E
            if test_record_ids:
                db.query(_E).filter(
                    _E.source_module == "state_aid",
                    _E.source_record_id.in_(test_record_ids),
                ).delete(synchronize_session=False)
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        finally:
            db.close()


def test_upsert_embedding_idempotent(db_session, monkeypatch):
    """Zweiter Upsert mit gleichem (module, record_id) erzeugt KEIN Duplikat,
    sondern aktualisiert das bestehende Embedding.
    """
    from models.entity_embeddings import EntityEmbedding
    from services.entity_embeddings import upsert_embedding

    rid = "test-uniq-emb-1"
    vec1 = [0.1] * 1024
    vec2 = [0.2] * 1024

    out1 = upsert_embedding(
        db_session,
        module="state_aid",
        record_id=rid,
        text_input="text v1",
        embedding=vec1,
    )
    db_session.commit()
    assert out1 is not None
    db_session.test_track_embedding(rid)

    out2 = upsert_embedding(
        db_session,
        module="state_aid",
        record_id=rid,
        text_input="text v2",
        embedding=vec2,
    )
    db_session.commit()
    assert out2 is not None

    # Es darf nur einen Eintrag fuer (state_aid, rid) geben.
    rows = (
        db_session.query(EntityEmbedding)
        .filter(
            EntityEmbedding.source_module == "state_aid",
            EntityEmbedding.source_record_id == rid,
        )
        .all()
    )
    assert len(rows) == 1
    # Update muss text_input neu gesetzt haben.
    assert rows[0].text_input == "text v2"


def test_search_semantic_with_mocked_embedding(db_session, monkeypatch):
    """search_semantic ohne Gateway-Call. Das Embedding wird als bekannter
    Vektor gemockt; wir legen einen zweiten, dazu passenden Embedding-Eintrag
    an und pruefen, dass er gefunden wird.
    """
    from services import entity_embeddings as ee
    from services.entity_embeddings import search_semantic, upsert_embedding

    rid = "test-search-uniq-1"
    fixed_vec = [0.0] * 1024
    fixed_vec[0] = 1.0  # ausgepraegter Anker — Cosine zu anderen 0.0-Vektoren = 0.0

    # Patch des Gateway-Aufrufs
    monkeypatch.setattr(ee, "get_embedding", lambda text_value: fixed_vec)

    upsert_embedding(
        db_session,
        module="state_aid",
        record_id=rid,
        text_input="Mock-Suchziel",
        embedding=fixed_vec,
    )
    db_session.commit()
    db_session.test_track_embedding(rid)

    results = search_semantic(
        db_session, "irgendeine Frage",
        module="state_aid",
        limit=5,
        min_similarity=0.5,
    )
    # Mindestens unser Test-Eintrag muss dabei sein und cos_sim ~1.0
    found = [r for r in results if r["source_record_id"] == rid]
    assert found, f"Erwartet rid={rid} unter den Ergebnissen, bekam {results}"
    assert found[0]["cosine_similarity"] >= 0.99
    assert found[0]["text_input"] == "Mock-Suchziel"


def test_search_semantic_returns_empty_when_gateway_fails(monkeypatch):
    """Wenn das Gateway None liefert, kommt eine leere Liste zurueck — keine
    Exception."""
    from services import entity_embeddings as ee
    from services.entity_embeddings import search_semantic

    monkeypatch.setattr(ee, "get_embedding", lambda text_value: None)

    out = search_semantic(
        db=None,  # type: ignore[arg-type]
        query="irgendeine Frage",
        module="state_aid",
        limit=5,
    )
    assert out == []


def test_search_semantic_validates_module():
    """Unbekanntes module -> ValueError, ohne DB-Zugriff."""
    from services.entity_embeddings import search_semantic
    with pytest.raises(ValueError):
        search_semantic(
            db=None,  # type: ignore[arg-type]
            query="test",
            module="bogus",
            limit=5,
        )


def test_rebuild_module_embeddings_dry_run(db_session):
    """Dry-Run laeuft ohne Schreibvorgang durch und liefert Stats-Dict."""
    from services.entity_embeddings import rebuild_module_embeddings

    stats = rebuild_module_embeddings(
        db_session, "state_aid",
        batch_size=10, skip_existing=True, dry=True, limit=5,
    )
    assert "processed" in stats
    assert "inserted" in stats
    assert "updated" in stats
    assert "skipped" in stats
    assert "failed" in stats


def test_rebuild_module_embeddings_unknown_module():
    """Unbekanntes Modul wirft ValueError direkt."""
    from services.entity_embeddings import rebuild_module_embeddings
    with pytest.raises(ValueError):
        rebuild_module_embeddings(
            db=None,  # type: ignore[arg-type]
            module="bogus",
            batch_size=10, dry=True,
        )


def test_rebuild_module_embeddings_skip_existing_with_mock(
    db_session, monkeypatch,
):
    """Mit skip_existing=True wird ein bereits eingebetteter Record nicht
    nochmal embeddet — Counter ``skipped`` zaehlt ihn.

    Wir koennen das nicht garantieren, weil es Test-Daten in der DB braucht;
    aber wir koennen verifizieren, dass die Funktion fuer einen vorhandenen
    Eintrag den skipped-Counter erhoeht. Dazu legen wir einen Embedding-
    Eintrag an, dessen source_record_id der ID eines bestehenden state_aid-
    Awards entspricht (sofern die DB welche enthaelt).
    """
    from sqlalchemy import text as _text
    from services.entity_embeddings import (
        rebuild_module_embeddings, upsert_embedding,
    )

    # Pruefen ob es ueberhaupt state_aid-Awards in der DB gibt.
    row = db_session.execute(_text(
        "SELECT id FROM workshop_state_aid_awards LIMIT 1"
    )).first()
    if row is None:
        pytest.skip("Keine state_aid-Awards in der DB — Test braucht Daten.")

    award_id_str = str(row[0])
    fixed_vec = [0.0] * 1024
    fixed_vec[0] = 1.0
    upsert_embedding(
        db_session,
        module="state_aid",
        record_id=award_id_str,
        text_input="precomputed",
        embedding=fixed_vec,
    )
    db_session.commit()
    db_session.test_track_embedding(award_id_str)

    # Patch Gateway-Embed (sollte nicht aufgerufen werden, weil der Eintrag
    # geskippt wird).
    from services import entity_embeddings as ee

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError(
            "Gateway sollte nicht aufgerufen werden (skip_existing=True)",
        )

    monkeypatch.setattr(ee, "_batch_embed", _should_not_be_called)

    stats = rebuild_module_embeddings(
        db_session, "state_aid",
        batch_size=5, skip_existing=True, dry=False, limit=1,
    )
    # Der eine Record, der bereits ein Embedding hat, MUSS skipped werden.
    assert stats["skipped"] >= 1
    # Nicht-Embeddable Records (z.B. ohne Namen) duerften die Bilanz nicht
    # umkehren — aber wir verifizieren wenigstens, dass wir nichts inserted
    # haben (Gateway war ja gepatcht).
    assert stats["inserted"] == 0
