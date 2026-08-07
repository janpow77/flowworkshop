"""
flowworkshop · services/checklist_package_service.py

Vollstaendiges Checklisten-Paket (Export/Import als eine portable Datei) fuer den
KOM-Checklisten-Designer. Gespiegelt zum audit_designer-Paket, angepasst an das
RELATIONALE Workshop-Modell (ChecklistTemplate → Nodes/AnswerSets/Categories/
Comments/History/Versions).

Kern: ein internes "kanonisches" Paket-Schema, in das sowohl das native
Workshop-Format ALS AUCH das audit_designer-Format (Cross-Repo) normalisiert
werden. Import legt alles mit konsistentem UUID-FK-Remapping neu an.

WICHTIG (Interop, verifiziert 2026-06-22):
* audit_designer kodiert die Hierarchie in ``children``-Arrays; ``parent_id`` ist
  dort IMMER NULL → der Adapter MUSS ``children`` top-down laufen.
* Workshop-AnswerSet(+Optionen) ⇆ audit_designer ``categories``(+items)/
  ``qchess_answer_sets``/CUSTOM_ENUM.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.checklist_template import (
    ChecklistAnswerOption,
    ChecklistAnswerSet,
    ChecklistMember,
    ChecklistNodeComment,
    ChecklistNodeHistory,
    ChecklistQuestionCategory,
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
    MemberRole,
)

PACKAGE_FORMAT = "workshop-checklist-package"
AUDIT_DESIGNER_FORMAT = "audit-designer-checklist-package"
FORMAT_VERSION = 1


class ChecklistPackageError(Exception):
    """Fachlicher Fehler beim Verarbeiten eines Checklisten-Pakets."""


def _nid() -> str:
    return str(uuid.uuid4())


class ChecklistPackageService:
    """Baut und liest vollstaendige Checklisten-Pakete (.checklist.json)."""

    # ============================================================= EXPORT
    @classmethod
    def build_package(
        cls,
        db: Session,
        template: ChecklistTemplate,
        *,
        include_discussions: bool = True,
        include_history: bool = False,
        include_versions: bool = False,
    ) -> dict[str, Any]:
        """Natives Workshop-Paket einer Checkliste erzeugen."""
        nodes = (
            db.query(ChecklistTemplateNode)
            .filter(ChecklistTemplateNode.template_id == template.id)
            .order_by(ChecklistTemplateNode.sort_order)
            .all()
        )
        node_ids = {n.id for n in nodes}

        # Antwortsets: template-scoped + referenzierte globale
        ref_set_ids = {n.answer_set_id for n in nodes if n.answer_set_id}
        sets = (
            db.query(ChecklistAnswerSet)
            .filter(
                (ChecklistAnswerSet.template_id == template.id)
                | (ChecklistAnswerSet.id.in_(ref_set_ids))
            )
            .all()
        )
        answer_sets = []
        for s in sets:
            opts = (
                db.query(ChecklistAnswerOption)
                .filter(ChecklistAnswerOption.answer_set_id == s.id)
                .order_by(ChecklistAnswerOption.sort_order)
                .all()
            )
            answer_sets.append(
                {
                    "old_id": s.id,
                    "scope": "template" if s.template_id else "global",
                    "name": s.name,
                    "description": s.description,
                    "sort_order": s.sort_order or 0,
                    "options": [
                        {
                            "old_id": o.id,
                            "name": o.name,
                            "sort_order": o.sort_order or 0,
                            "is_standard": bool(o.is_standard),
                            "is_entfaellt": bool(o.is_entfaellt),
                            "value_number": o.value_number,
                            "threshold": o.threshold,
                            "bemerkung": o.bemerkung,
                        }
                        for o in opts
                    ],
                }
            )

        categories = [
            {"old_id": c.id, "name": c.name, "sort_order": c.sort_order or 0}
            for c in db.query(ChecklistQuestionCategory)
            .filter(ChecklistQuestionCategory.template_id == template.id)
            .order_by(ChecklistQuestionCategory.sort_order)
            .all()
        ]

        node_payloads = [cls._node_payload(n) for n in nodes]

        discussions = []
        if include_discussions:
            for c in (
                db.query(ChecklistNodeComment)
                .filter(
                    ChecklistNodeComment.template_id == template.id,
                    ChecklistNodeComment.deleted_at.is_(None),
                )
                .order_by(ChecklistNodeComment.created_at)
                .all()
            ):
                if c.node_id in node_ids:
                    discussions.append(
                        {
                            "old_id": c.id,
                            "node_old_id": c.node_id,
                            "author_id": c.author_id,
                            "message": c.message,
                            "parent_comment_old_id": c.parent_comment_id,
                            "created_at": cls._iso(c.created_at),
                            "edited_at": cls._iso(c.edited_at),
                        }
                    )

        history = []
        if include_history:
            for h in (
                db.query(ChecklistNodeHistory)
                .filter(ChecklistNodeHistory.template_id == template.id)
                .order_by(ChecklistNodeHistory.created_at)
                .all()
            ):
                history.append(
                    {
                        "node_old_id": h.node_id,
                        "node_version": h.node_version,
                        "change_type": h.change_type,
                        "node_snapshot": h.node_snapshot,
                        "changed_fields": h.changed_fields,
                        "changed_by_id": h.changed_by_id,
                        "change_reason": h.change_reason,
                        "created_at": cls._iso(h.created_at),
                    }
                )

        versions = []
        if include_versions:
            for v in (
                db.query(ChecklistTemplateVersion)
                .filter(ChecklistTemplateVersion.template_id == template.id)
                .order_by(ChecklistTemplateVersion.created_at)
                .all()
            ):
                versions.append(
                    {
                        "version_number": v.version_number,
                        "is_frozen": bool(v.is_frozen),
                        "status": v.status,
                        "tree_snapshot": v.tree_snapshot,
                        "notes": v.notes,
                        "created_at": cls._iso(v.created_at),
                    }
                )

        template_meta = {
            "title": template.title,
            "description": template.description,
            "source_language": template.source_language,
            "target_language": template.target_language,
            "properties_json": template.properties_json,
            "status": template.status,
            "current_version": template.current_version,
        }
        checksum = cls._checksum(template_meta, answer_sets, categories, node_payloads)

        return {
            "format": PACKAGE_FORMAT,
            "format_version": FORMAT_VERSION,
            "exported_at": datetime.utcnow().isoformat(),
            "source": {"app": "auditworkshop", "template_id": template.id},
            "checksum": checksum,
            "options": {
                "discussions": include_discussions,
                "history": include_history,
                "versions": include_versions,
            },
            "template": template_meta,
            "answer_sets": answer_sets,
            "categories": categories,
            "nodes": node_payloads,
            "discussions": discussions,
            "history": history,
            "versions": versions,
        }

    @staticmethod
    def _node_payload(n: ChecklistTemplateNode) -> dict[str, Any]:
        return {
            "old_id": n.id,
            "parent_old_id": n.parent_id,
            "decision_parent_old_id": n.decision_parent_id,
            "node_type": n.node_type,
            "status": n.status,
            "branch": n.branch,
            "ja_label": n.ja_label,
            "nein_label": n.nein_label,
            "sort_order": n.sort_order or 0,
            "title": n.title,
            "public_remark": n.public_remark,
            "remark_snippets_json": n.remark_snippets_json,
            "eingabetyp": n.eingabetyp,
            "answer_type": n.answer_type,
            "answer_set_old_id": n.answer_set_id,
            "category_old_id": n.category_id,
            "legal_reference": n.legal_reference,
            "relevant_documents_json": n.relevant_documents_json,
            "is_header_field": bool(n.is_header_field),
            "source_text_en": n.source_text_en,
            "translated_text_de": n.translated_text_de,
            "review_text_de": n.review_text_de,
            "translation_status": n.translation_status,
        }

    @staticmethod
    def _iso(dt) -> str | None:
        return dt.isoformat() if dt else None

    @classmethod
    def _checksum(cls, template_meta, answer_sets, categories, nodes) -> str:
        """Stabile sha256 ueber den Strukturkern (ohne IDs/Zeitstempel)."""

        def set_core(s):
            return {
                "name": s["name"],
                "options": [
                    {
                        k: o[k]
                        for k in ("name", "sort_order", "is_standard", "is_entfaellt")
                    }
                    for o in s["options"]
                ],
            }

        # Relative Knoten-Signatur ueber old_id-Position (parent via index unabhaengig)
        node_core = sorted(
            (
                {
                    "node_type": n["node_type"],
                    "branch": n["branch"],
                    "title": n["title"],
                    "answer_type": n["answer_type"],
                    "ja_label": n["ja_label"],
                    "nein_label": n["nein_label"],
                    "remark_snippets_json": n["remark_snippets_json"],
                    "public_remark": n["public_remark"],
                }
                for n in nodes
            ),
            key=lambda x: json.dumps(
                x, sort_keys=True, ensure_ascii=False, default=str
            ),
        )
        canonical = {
            "template": {
                k: template_meta.get(k)
                for k in ("title", "description", "source_language", "target_language")
            },
            "answer_sets": sorted(
                (set_core(s) for s in answer_sets),
                key=lambda x: x["name"] or "",
            ),
            "categories": sorted((c["name"] or "") for c in categories),
            "nodes": node_core,
        }
        blob = json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, default=str
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(blob).hexdigest()

    # ============================================================ NORMALIZE
    @classmethod
    def normalize_payload(
        cls, payload: Any, fallback_title: str | None = None
    ) -> dict[str, Any]:
        """Beliebiges bekanntes Format → kanonisches Paket-Schema.

        Akzeptiert das native Workshop-Paket UND das audit_designer-Paket
        (Cross-Repo) sowie rohe audit_designer-tree_data.
        """
        if not isinstance(payload, dict):
            raise ChecklistPackageError("Datei enthaelt kein gueltiges JSON-Objekt.")

        fmt = payload.get("format")
        if fmt == PACKAGE_FORMAT or (
            isinstance(payload.get("nodes"), list) and "template" in payload
        ):
            return cls._normalize_native(payload, fallback_title)
        if fmt == AUDIT_DESIGNER_FORMAT or (
            isinstance(payload.get("versions"), list) and "project" in payload
        ):
            return cls._normalize_from_audit_designer(payload, fallback_title)
        if "root_id" in payload and "nodes" in payload:
            # rohe audit_designer-tree_data
            return cls._normalize_from_audit_designer(
                {
                    "project": {"name": fallback_title},
                    "categories": {},
                    "versions": [{"version_number": "1.0", "tree_data": payload}],
                },
                fallback_title,
            )
        raise ChecklistPackageError(
            "Unbekanntes Format: weder Workshop- noch audit_designer-Paket erkannt."
        )

    @staticmethod
    def _normalize_native(payload: dict, fallback_title: str | None) -> dict[str, Any]:
        fmtv = payload.get("format_version", FORMAT_VERSION)
        if isinstance(fmtv, int) and fmtv > FORMAT_VERSION:
            raise ChecklistPackageError(
                f"Paket-Format v{fmtv} ist neuer als unterstuetzt (v{FORMAT_VERSION})."
            )
        tpl = dict(payload.get("template") or {})
        if not tpl.get("title") and fallback_title:
            tpl["title"] = fallback_title
        return {
            "checksum": payload.get("checksum"),
            "template": tpl,
            "answer_sets": list(payload.get("answer_sets") or []),
            "categories": list(payload.get("categories") or []),
            "nodes": list(payload.get("nodes") or []),
            "discussions": list(payload.get("discussions") or []),
            "history": list(payload.get("history") or []),
            "versions": list(payload.get("versions") or []),
        }

    @classmethod
    def _normalize_from_audit_designer(
        cls, payload: dict, fallback_title: str | None
    ) -> dict[str, Any]:
        """Adapter: audit_designer-Paket → kanonisches Workshop-Schema.

        Verifiziert 2026-06-22 (443-Knoten-Round-Trip)."""
        proj = payload.get("project") or {}
        versions = payload.get("versions") or []
        if not versions:
            raise ChecklistPackageError("audit_designer-Paket ohne Versionen.")

        # AnswerSets aus categories (+items) und qchess_answer_sets
        answer_sets = []
        cat_key_to_setid = {}
        for old_id, c in (payload.get("categories") or {}).items():
            sid = f"cat:{old_id}"
            answer_sets.append(
                {
                    "old_id": sid,
                    "scope": "template",
                    "name": c.get("name") or "Antwortset",
                    "description": c.get("description"),
                    "sort_order": 0,
                    "options": [
                        {
                            "old_id": f"{sid}:o{i}",
                            "name": it.get("value", ""),
                            "sort_order": it.get("sort_order", i),
                        }
                        for i, it in enumerate(c.get("items", []))
                    ],
                }
            )
            cat_key_to_setid[str(old_id)] = sid
        qa_key_to_setid = {}
        for qid, q in (payload.get("qchess_answer_sets") or {}).items():
            sid = f"qa:{qid}"
            answer_sets.append(
                {
                    "old_id": sid,
                    "scope": "template",
                    "name": q.get("name") or "QChess-Antwortset",
                    "description": None,
                    "sort_order": 0,
                    "options": [
                        {
                            "old_id": f"{sid}:{o.get('reviewantwort_id', i)}",
                            "name": o.get("name", ""),
                            "sort_order": o.get("sort", i),
                        }
                        for i, o in enumerate(q.get("options", []))
                    ],
                }
            )
            qa_key_to_setid[str(qid)] = sid

        # Knoten: children-walk der (i.d.R. aktuellen/ersten) Version
        cur = versions[0]
        tree = cur.get("tree_data") or {}
        nodes_in = tree.get("nodes") or {}
        root = tree.get("root_id")
        out_nodes: list[dict[str, Any]] = []
        discussions: list[dict[str, Any]] = []

        def walk(node_id, parent_old, dec_anc_old):
            n = nodes_in.get(node_id)
            if not n:
                return
            co = n.get("content", {}) or {}
            asid = None
            if (
                co.get("category_id") is not None
                and str(co["category_id"]) in cat_key_to_setid
            ):
                asid = cat_key_to_setid[str(co["category_id"])]
            elif (
                co.get("qchess_antwortset_id")
                and str(co["qchess_antwortset_id"]) in qa_key_to_setid
            ):
                asid = qa_key_to_setid[str(co["qchess_antwortset_id"])]
            out_nodes.append(
                {
                    "old_id": node_id,
                    "parent_old_id": parent_old,
                    "decision_parent_old_id": dec_anc_old if n.get("branch") else None,
                    "node_type": n.get("node_type", "QUESTION"),
                    "status": "pending",
                    "branch": n.get("branch"),
                    "ja_label": co.get("qchess_ja_label"),
                    "nein_label": co.get("qchess_nein_label"),
                    "sort_order": n.get("sort_order", 0),
                    "title": co.get("title"),
                    "public_remark": co.get("public_remark"),
                    "remark_snippets_json": co.get("remark_snippets"),
                    "eingabetyp": co.get("qchess_eingabetyp"),
                    "answer_type": co.get("answer_type"),
                    "answer_set_old_id": asid,
                    "category_old_id": None,
                    "legal_reference": None,
                    "relevant_documents_json": None,
                    "is_header_field": False,
                }
            )
            for note in (n.get("internal", {}) or {}).get("team_notes", []) or []:
                discussions.append(
                    {
                        "old_id": _nid(),
                        "node_old_id": node_id,
                        "author_id": None,
                        "author_name": note.get("username") or note.get("author"),
                        "message": note.get("message") or note.get("text") or "",
                        "parent_comment_old_id": None,
                    }
                )
            new_dec = node_id if n.get("node_type") == "DECISION" else dec_anc_old
            for c in n.get("children", []) or []:
                walk(c, node_id, new_dec)

        if root:
            walk(root, None, None)

        extra_versions = [
            {
                "version_number": v.get("version_number") or f"v{i+2}",
                "is_frozen": bool(v.get("is_frozen")),
                "status": "released" if v.get("is_frozen") else "draft",
                "tree_snapshot": v.get("tree_data"),
                "notes": v.get("notes"),
            }
            for i, v in enumerate(versions[1:])
        ]

        return {
            "checksum": None,
            "template": {
                "title": (proj.get("name") or fallback_title or "").strip()
                or fallback_title,
                "description": proj.get("description"),
                "source_language": "de",
                "target_language": "de",
                "properties_json": {
                    "imported_from": "audit_designer",
                    "aktenzeichen": proj.get("aktenzeichen"),
                    "geschaeftsjahr": proj.get("geschaeftsjahr"),
                    "tags": proj.get("tags"),
                },
                "status": "draft",
                "current_version": proj.get("current_version"),
            },
            "answer_sets": answer_sets,
            "categories": [],
            "nodes": out_nodes,
            "discussions": discussions,
            "history": [],
            "versions": extra_versions,
        }

    # ============================================================ VALIDATE
    @classmethod
    def validate_package(
        cls, db: Session, payload: Any, fallback_title: str | None = None
    ) -> dict[str, Any]:
        try:
            pkg = cls.normalize_payload(payload, fallback_title)
        except ChecklistPackageError as exc:
            return {"valid": False, "errors": [str(exc)], "warnings": []}

        errors: list[str] = []
        warnings: list[str] = []
        nodes = pkg["nodes"]
        if not nodes:
            errors.append("Paket enthaelt keine Knoten.")

        ids = {n["old_id"] for n in nodes}
        roots = [n for n in nodes if not n.get("parent_old_id")]
        dangling = [
            n["old_id"]
            for n in nodes
            if n.get("parent_old_id") and n["parent_old_id"] not in ids
        ]
        if dangling:
            errors.append(f"{len(dangling)} Knoten mit unbekanntem parent.")
        if nodes and len(roots) != 1:
            warnings.append(f"{len(roots)} Wurzelknoten (erwartet: 1).")

        # Antwortset-Referenzen aufloesbar?
        set_ids = {s["old_id"] for s in pkg["answer_sets"]}
        missing_sets = sorted(
            {
                n["answer_set_old_id"]
                for n in nodes
                if n.get("answer_set_old_id") and n["answer_set_old_id"] not in set_ids
            }
        )
        if missing_sets:
            warnings.append(
                f"{len(missing_sets)} Antwortset-Referenz(en) ohne Definition im Paket."
            )

        title = (pkg["template"] or {}).get("title")
        existing = cls._find_existing(db, title)
        identical = False
        if existing and pkg.get("checksum"):
            for cand in existing:
                ct = db.get(ChecklistTemplate, cand["id"])
                if ct and cls.build_package(db, ct)["checksum"] == pkg["checksum"]:
                    identical = True
                    cand["identical"] = True

        from collections import Counter

        ct = Counter(n["node_type"] for n in nodes)
        return {
            "valid": len(errors) == 0,
            "template": {
                "title": title,
                "description": (pkg["template"] or {}).get("description"),
                "status": (pkg["template"] or {}).get("status"),
            },
            "counts": {
                "nodes": len(nodes),
                "questions": ct.get("QUESTION", 0),
                "headings": ct.get("HEADING", 0),
                "decisions": ct.get("DECISION", 0),
                "hints": ct.get("HINT", 0),
                "answer_sets": len(pkg["answer_sets"]),
                "categories": len(pkg["categories"]),
                "discussions": len(pkg["discussions"]),
                "history": len(pkg["history"]),
                "versions": len(pkg["versions"]),
            },
            "answer_sets": [
                {
                    "name": s["name"],
                    "option_count": len(s.get("options") or []),
                    "exists_by_name": bool(
                        s.get("scope") == "global"
                        and db.query(ChecklistAnswerSet.id)
                        .filter(
                            ChecklistAnswerSet.template_id.is_(None),
                            ChecklistAnswerSet.name == s["name"],
                        )
                        .first()
                    ),
                }
                for s in pkg["answer_sets"]
            ],
            "exists": {"by_name": existing, "identical": identical},
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def _find_existing(db: Session, title: str | None) -> list[dict[str, Any]]:
        if not title:
            return []
        rows = (
            db.query(ChecklistTemplate)
            .filter(ChecklistTemplate.title == title)
            .order_by(ChecklistTemplate.updated_at.desc())
            .all()
        )
        return [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                "identical": False,
            }
            for t in rows
        ]

    # ============================================================== IMPORT
    @classmethod
    def import_package(
        cls,
        db: Session,
        payload: Any,
        current_user_id: str | None,
        target_template_id: str | None = None,
        title_override: str | None = None,
        fallback_title: str | None = None,
    ) -> dict[str, Any]:
        pkg = cls.normalize_payload(payload, fallback_title)
        nodes = pkg["nodes"]
        ids = {n["old_id"] for n in nodes}
        if not nodes:
            raise ChecklistPackageError("Paket enthaelt keine Knoten.")
        dangling = [
            n["old_id"]
            for n in nodes
            if n.get("parent_old_id") and n["parent_old_id"] not in ids
        ]
        if dangling:
            raise ChecklistPackageError(
                f"{len(dangling)} Knoten mit unbekanntem parent."
            )

        # Import in BESTEHENDES Template → als Versions-Snapshot (sicher)
        if target_template_id is not None:
            tpl = db.get(ChecklistTemplate, target_template_id)
            if not tpl:
                raise ChecklistPackageError("Zielcheckliste nicht gefunden.")
            existing_v = {
                v.version_number
                for v in db.query(ChecklistTemplateVersion)
                .filter(ChecklistTemplateVersion.template_id == tpl.id)
                .all()
            }
            vnum = cls._next_version(
                existing_v, (pkg["template"] or {}).get("current_version") or "import-1"
            )
            db.add(
                ChecklistTemplateVersion(
                    id=_nid(),
                    template_id=tpl.id,
                    version_number=vnum,
                    is_frozen=True,
                    status="released",
                    tree_snapshot={"canonical": pkg},
                    created_by_id=current_user_id,
                    notes="Importiert aus Checklisten-Paket",
                )
            )
            tpl.current_version = vnum
            db.commit()
            return {
                "message": "Import erfolgreich",
                "created": False,
                "template_id": tpl.id,
                "version_number": vnum,
            }

        # Neues Template
        meta = pkg["template"] or {}
        title = title_override or meta.get("title") or fallback_title
        if not title:
            raise ChecklistPackageError("Kein Titel im Paket vorhanden.")
        tpl = ChecklistTemplate(
            id=_nid(),
            owner_id=current_user_id,
            title=title,
            description=meta.get("description"),
            source_language=meta.get("source_language") or "de",
            target_language=meta.get("target_language") or "de",
            properties_json=meta.get("properties_json"),
            status="draft",
            current_version=meta.get("current_version"),
        )
        db.add(tpl)
        db.flush()

        # Ersteller wird OWNER (Mitgliedschaft) — die Rechtepruefung ist
        # mitgliedschaftsbasiert; ohne diese Zeile koennte der Importeur seine
        # eigene Checkliste weder oeffnen noch loeschen.
        if current_user_id:
            db.add(
                ChecklistMember(
                    id=_nid(),
                    template_id=tpl.id,
                    user_id=current_user_id,
                    role=MemberRole.OWNER.value,
                    invited_by_id=current_user_id,
                )
            )

        # Antwortsets (global per Name dedupen, template-scoped neu)
        setmap: dict[str, str] = {}
        sets_created = sets_reused = 0
        for s in pkg["answer_sets"]:
            if s.get("scope") == "global":
                ex = (
                    db.query(ChecklistAnswerSet)
                    .filter(
                        ChecklistAnswerSet.template_id.is_(None),
                        ChecklistAnswerSet.name == s["name"],
                    )
                    .first()
                )
                if ex:
                    setmap[s["old_id"]] = ex.id
                    sets_reused += 1
                    continue
            new_set = ChecklistAnswerSet(
                id=_nid(),
                template_id=None if s.get("scope") == "global" else tpl.id,
                name=s["name"],
                description=s.get("description"),
                sort_order=s.get("sort_order", 0),
            )
            db.add(new_set)
            db.flush()
            for o in s.get("options", []):
                db.add(
                    ChecklistAnswerOption(
                        id=_nid(),
                        answer_set_id=new_set.id,
                        name=o.get("name", ""),
                        sort_order=o.get("sort_order", 0),
                        is_standard=bool(o.get("is_standard")),
                        is_entfaellt=bool(o.get("is_entfaellt")),
                        value_number=o.get("value_number"),
                        threshold=o.get("threshold"),
                        bemerkung=o.get("bemerkung"),
                    )
                )
            setmap[s["old_id"]] = new_set.id
            sets_created += 1

        # Kategorien
        catmap: dict[str, str] = {}
        for c in pkg["categories"]:
            nc = ChecklistQuestionCategory(
                id=_nid(),
                template_id=tpl.id,
                name=c["name"],
                sort_order=c.get("sort_order", 0),
            )
            db.add(nc)
            db.flush()
            catmap[c["old_id"]] = nc.id

        # Knoten — Pass A (anlegen), Pass B (parent/decision_parent)
        nodemap: dict[str, str] = {}
        rows: dict[str, ChecklistTemplateNode] = {}
        for n in nodes:
            r = ChecklistTemplateNode(
                id=_nid(),
                template_id=tpl.id,
                node_type=n.get("node_type", "QUESTION"),
                status=n.get("status") or "pending",
                branch=n.get("branch"),
                ja_label=n.get("ja_label"),
                nein_label=n.get("nein_label"),
                sort_order=n.get("sort_order", 0),
                title=n.get("title"),
                public_remark=n.get("public_remark"),
                remark_snippets_json=n.get("remark_snippets_json"),
                eingabetyp=n.get("eingabetyp"),
                answer_type=n.get("answer_type"),
                answer_set_id=setmap.get(n.get("answer_set_old_id")),
                category_id=catmap.get(n.get("category_old_id")),
                legal_reference=n.get("legal_reference"),
                relevant_documents_json=n.get("relevant_documents_json"),
                is_header_field=bool(n.get("is_header_field")),
                source_text_en=n.get("source_text_en"),
                translated_text_de=n.get("translated_text_de"),
                review_text_de=n.get("review_text_de"),
                translation_status=n.get("translation_status"),
            )
            db.add(r)
            nodemap[n["old_id"]] = r.id
            rows[n["old_id"]] = r
        db.flush()
        for n in nodes:
            r = rows[n["old_id"]]
            if n.get("parent_old_id") in nodemap:
                r.parent_id = nodemap[n["parent_old_id"]]
            if n.get("decision_parent_old_id") in nodemap:
                r.decision_parent_id = nodemap[n["decision_parent_old_id"]]

        # Diskussionen (2-Pass fuer Threading)
        commentmap: dict[str, str] = {}
        disc = 0
        for d in pkg["discussions"]:
            if d.get("node_old_id") not in nodemap:
                continue
            cid = _nid()
            commentmap[d.get("old_id") or cid] = cid
            msg = d.get("message") or ""
            if d.get("author_name") and not d.get("author_id"):
                msg = f"[{d['author_name']}] {msg}"
            db.add(
                ChecklistNodeComment(
                    id=cid,
                    template_id=tpl.id,
                    node_id=nodemap[d["node_old_id"]],
                    author_id=d.get("author_id"),
                    message=msg,
                )
            )
            disc += 1
        for d in pkg["discussions"]:
            pid = d.get("parent_comment_old_id")
            if pid and d.get("old_id") in commentmap and pid in commentmap:
                row = db.get(ChecklistNodeComment, commentmap[d["old_id"]])
                if row:
                    row.parent_comment_id = commentmap[pid]

        # Historie
        hist = 0
        for h in pkg["history"]:
            nodeid = nodemap.get(h.get("node_old_id"), h.get("node_old_id") or "")
            db.add(
                ChecklistNodeHistory(
                    id=_nid(),
                    template_id=tpl.id,
                    node_id=nodeid,
                    node_version=h.get("node_version", 1),
                    change_type=h.get("change_type", "updated"),
                    node_snapshot=h.get("node_snapshot"),
                    changed_fields=h.get("changed_fields"),
                    changed_by_id=None,
                    change_reason=h.get("change_reason"),
                )
            )
            hist += 1

        # Versions-Snapshots
        for v in pkg["versions"]:
            db.add(
                ChecklistTemplateVersion(
                    id=_nid(),
                    template_id=tpl.id,
                    version_number=v.get("version_number") or _nid()[:8],
                    is_frozen=bool(v.get("is_frozen")),
                    status=v.get("status") or "draft",
                    tree_snapshot=v.get("tree_snapshot"),
                    notes=v.get("notes"),
                    created_by_id=current_user_id,
                )
            )

        db.commit()
        return {
            "message": "Import erfolgreich",
            "created": True,
            "template_id": tpl.id,
            "title": tpl.title,
            "nodes_count": len(nodes),
            "answer_sets_created": sets_created,
            "answer_sets_reused": sets_reused,
            "discussions_restored": disc,
            "history_restored": hist,
        }

    @staticmethod
    def _next_version(existing: set[str], desired: str) -> str:
        if desired not in existing:
            return desired
        i = 2
        while f"{desired}-import-{i}" in existing:
            i += 1
        return f"{desired}-import-{i}"
