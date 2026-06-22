"""Unit-Tests (SQLite) fuer das Checklisten-Paket: nativer Round-Trip,
audit_designer-Adapter (Cross-Repo) und Validierung/Existenz."""

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.ext.compiler import compiles


@compiles(pg.JSONB, "sqlite")
def _jsonb_sqlite(t, c, **kw):  # pragma: no cover
    return "TEXT"


from database import Base  # noqa: E402
from models.checklist_template import (  # noqa: E402
    ChecklistAnswerOption,
    ChecklistAnswerSet,
    ChecklistMember,
    ChecklistNodeComment,
    ChecklistQuestionCategory,
    ChecklistTemplate,
    ChecklistTemplateNode,
)
from services.checklist_package_service import ChecklistPackageService  # noqa: E402

eng = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=eng)


def nid():
    return str(uuid.uuid4())


@pytest.fixture
def db():
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_native(db, title="Muster A"):
    tpl = ChecklistTemplate(
        id=nid(), title=title, status="draft", current_version="1.0"
    )
    db.add(tpl)
    db.flush()
    aset = ChecklistAnswerSet(
        id=nid(), template_id=tpl.id, name="Bewertung", sort_order=0
    )
    db.add(aset)
    db.flush()
    for i, n in enumerate(["Konform", "Teilweise", "Nicht konform"]):
        db.add(
            ChecklistAnswerOption(id=nid(), answer_set_id=aset.id, name=n, sort_order=i)
        )
    cat = ChecklistQuestionCategory(
        id=nid(), template_id=tpl.id, name="Allgemein", sort_order=0
    )
    db.add(cat)
    db.flush()
    h = ChecklistTemplateNode(
        id=nid(),
        template_id=tpl.id,
        node_type="HEADING",
        sort_order=0,
        title="1. Kapitel",
    )
    db.add(h)
    db.flush()
    q = ChecklistTemplateNode(
        id=nid(),
        template_id=tpl.id,
        parent_id=h.id,
        node_type="QUESTION",
        sort_order=0,
        title="1.1 Frage",
        answer_type="BOOLEAN_JN",
        category_id=cat.id,
    )
    d = ChecklistTemplateNode(
        id=nid(),
        template_id=tpl.id,
        parent_id=h.id,
        node_type="DECISION",
        sort_order=1,
        title="1.2 Einnahmen?",
        ja_label="Ja-Text",
        nein_label="Nein-Text",
    )
    db.add(q)
    db.add(d)
    db.flush()
    ja = ChecklistTemplateNode(
        id=nid(),
        template_id=tpl.id,
        parent_id=d.id,
        decision_parent_id=d.id,
        node_type="QUESTION",
        branch="JA",
        sort_order=0,
        title="1.2.1 Hoehe",
        answer_type="CURRENCY",
    )
    qr = ChecklistTemplateNode(
        id=nid(),
        template_id=tpl.id,
        parent_id=h.id,
        node_type="QUESTION",
        sort_order=2,
        title="1.3 Risiko",
        answer_type="CUSTOM_ENUM",
        answer_set_id=aset.id,
        remark_snippets_json={"Nicht konform": "<p>Feststellung</p>"},
    )
    db.add(ja)
    db.add(qr)
    db.flush()
    db.add(
        ChecklistNodeComment(
            id=nid(),
            template_id=tpl.id,
            node_id=q.id,
            author_id=None,
            message="Bitte pruefen",
        )
    )
    db.commit()
    return tpl


def _rt(pkg):
    return json.loads(json.dumps(pkg, default=str))


def test_native_round_trip(db):
    tpl = _seed_native(db)
    pkg = _rt(ChecklistPackageService.build_package(db, tpl))
    res = ChecklistPackageService.import_package(
        db, pkg, current_user_id="u-owner", title_override="Muster A (Kopie)"
    )
    assert res["created"] is True
    new_id = res["template_id"]
    # Ersteller wird OWNER-Mitglied (sonst kein Zugriff/Loeschen)
    owner = (
        db.query(ChecklistMember)
        .filter(
            ChecklistMember.template_id == new_id,
            ChecklistMember.user_id == "u-owner",
        )
        .first()
    )
    assert owner is not None and owner.role == "owner"
    nodes = db.query(ChecklistTemplateNode).filter_by(template_id=new_id).all()
    assert len(nodes) == 5
    roots = [n for n in nodes if not n.parent_id]
    assert len(roots) == 1
    assert sorted({n.branch for n in nodes if n.branch}) == ["JA"]
    assert any(n.decision_parent_id for n in nodes)
    assert any(n.remark_snippets_json for n in nodes)
    sets = db.query(ChecklistAnswerSet).filter_by(template_id=new_id).all()
    assert any(s.name == "Bewertung" for s in sets)
    bew = next(s for s in sets if s.name == "Bewertung")
    assert db.query(ChecklistAnswerOption).filter_by(answer_set_id=bew.id).count() == 3
    assert db.query(ChecklistNodeComment).filter_by(template_id=new_id).count() == 1
    assert res["answer_sets_created"] >= 1


def test_audit_designer_adapter(db):
    ad = {
        "format": "audit-designer-checklist-package",
        "format_version": 1,
        "project": {"name": "AD Import", "current_version": "1.0"},
        "categories": {
            "5": {
                "name": "Projektart",
                "items": [
                    {"value": "Bau", "sort_order": 0},
                    {"value": "FuE", "sort_order": 1},
                ],
            }
        },
        "qchess_answer_sets": {
            "qid1": {
                "name": "J/N",
                "options": [
                    {"reviewantwort_id": "a", "name": "Ja", "sort": 0},
                    {"reviewantwort_id": "b", "name": "Nein", "sort": 1},
                ],
            }
        },
        "versions": [
            {
                "version_number": "1.0",
                "tree_data": {
                    "root_id": "r",
                    "nodes": {
                        "r": {
                            "id": "r",
                            "node_type": "HEADING",
                            "parent_id": None,
                            "branch": None,
                            "sort_order": 0,
                            "content": {"title": "1. K"},
                            "children": ["q1", "d1"],
                        },
                        "q1": {
                            "id": "q1",
                            "node_type": "QUESTION",
                            "parent_id": None,
                            "branch": None,
                            "sort_order": 0,
                            "content": {
                                "title": "1.1",
                                "answer_type": "CUSTOM_ENUM",
                                "category_id": 5,
                            },
                            "children": [],
                        },
                        "d1": {
                            "id": "d1",
                            "node_type": "DECISION",
                            "parent_id": None,
                            "sort_order": 1,
                            "content": {
                                "title": "1.2",
                                "qchess_ja_label": "JaT",
                                "qchess_nein_label": "NeinT",
                            },
                            "children": ["c1"],
                        },
                        "c1": {
                            "id": "c1",
                            "node_type": "QUESTION",
                            "parent_id": None,
                            "branch": "JA",
                            "sort_order": 0,
                            "content": {
                                "title": "1.2.1",
                                "answer_type": "CUSTOM_ENUM",
                                "qchess_antwortset_id": "qid1",
                            },
                            "internal": {
                                "team_notes": [
                                    {"username": "zink", "message": "Art. 73?"}
                                ]
                            },
                            "children": [],
                        },
                    },
                },
            }
        ],
    }
    res = ChecklistPackageService.import_package(db, _rt(ad), current_user_id=None)
    assert res["created"] is True
    new_id = res["template_id"]
    nodes = db.query(ChecklistTemplateNode).filter_by(template_id=new_id).all()
    assert len(nodes) == 4
    assert (
        len([n for n in nodes if not n.parent_id]) == 1
    )  # children-walk baute den Baum
    ja = [n for n in nodes if n.branch == "JA"]
    assert len(ja) == 1 and ja[0].decision_parent_id
    assert ja[0].nein_label is None and any(n.ja_label == "JaT" for n in nodes)
    sets = {
        s.name for s in db.query(ChecklistAnswerSet).filter_by(template_id=new_id).all()
    }
    assert "Projektart" in sets and "J/N" in sets
    # q1 -> Projektart, c1 -> J/N
    q1 = next(n for n in nodes if n.title == "1.1")
    assert q1.answer_set_id is not None
    assert db.query(ChecklistNodeComment).filter_by(template_id=new_id).count() == 1


def test_validate_detects_existing_identical(db):
    tpl = _seed_native(db)
    pkg = _rt(ChecklistPackageService.build_package(db, tpl))
    prev = ChecklistPackageService.validate_package(db, pkg, fallback_title="x")
    assert prev["valid"] is True
    assert prev["exists"]["by_name"]
    assert prev["exists"]["identical"] is True
    assert prev["counts"]["nodes"] == 5


def test_rejects_garbage(db):
    prev = ChecklistPackageService.validate_package(db, {"foo": 1})
    assert prev["valid"] is False
