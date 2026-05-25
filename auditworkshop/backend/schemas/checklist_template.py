"""
flowworkshop · schemas/checklist_template.py

Pydantic-Schemas fuer das KOM-Checklisten-Template-Subsystem (Designer).
Deckt Template, Knoten (rekursiver Baum), Antwortsets + Optionen, Kategorien
sowie Mitglieder und Einladungen ab. Bewusst getrennt von schemas/checklist.py
(projektgebundene Workshop-Checklisten).

Hinweis: Einladungs-/Notification-Flow, Locks, Export und Uebersetzung sind
spaeteren Phasen vorbehalten — hier nur die Lese-Schemas (Out) fuer Member/
Invite, damit die Mitglieder eines Templates ausgegeben werden koennen.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from models.checklist_template import (
    NodeType,
    NodeBranch,
    TemplateAnswerType,
    TemplateStatus,
    MemberRole,
)

# Obergrenzen fuer Freitext-/Text-Felder (Text-Spalten ohne DB-Limit). Verhindern
# unbeschraenkten Speicherverbrauch (Storage-DoS) durch ueberlange Eingaben; die
# Werte sind fuer fachliche Checklisten-Inhalte grosszuegig bemessen.
_MAX_TITLE_LEN = 4_000
_MAX_TEXT_LEN = 20_000


# ── Antwortoptionen ───────────────────────────────────────────────────────────

class AnswerOptionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    sort_order: int = 0
    is_standard: bool = False
    is_entfaellt: bool = False
    value_number: float | None = None
    threshold: float | None = None
    bemerkung: str | None = None


class AnswerOptionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    sort_order: int | None = None
    is_standard: bool | None = None
    is_entfaellt: bool | None = None
    value_number: float | None = None
    threshold: float | None = None
    bemerkung: str | None = None


class AnswerOptionOut(BaseModel):
    id: str
    answer_set_id: str
    name: str
    sort_order: int = 0
    is_standard: bool = False
    is_entfaellt: bool = False
    value_number: float | None = None
    threshold: float | None = None
    bemerkung: str | None = None

    model_config = {"from_attributes": True}


# ── Antwortsets ───────────────────────────────────────────────────────────────

class AnswerSetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    sort_order: int = 0
    options: list[AnswerOptionCreate] | None = None


class AnswerSetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    sort_order: int | None = None


class AnswerSetOut(BaseModel):
    id: str
    template_id: str | None = None  # NULL = globale Bibliothek
    name: str
    description: str | None = None
    sort_order: int = 0
    created_at: datetime | None = None
    options: list[AnswerOptionOut] = []

    model_config = {"from_attributes": True}


# ── Kategorien ────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    sort_order: int | None = None


class CategoryOut(BaseModel):
    id: str
    template_id: str
    name: str
    sort_order: int = 0
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Knoten ────────────────────────────────────────────────────────────────────

class NodeCreate(BaseModel):
    parent_id: str | None = Field(default=None, max_length=36)
    node_type: NodeType = NodeType.QUESTION
    branch: NodeBranch | None = None
    ja_label: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    nein_label: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    decision_parent_id: str | None = Field(default=None, max_length=36)
    sort_order: int = 0

    title: str | None = Field(default=None, max_length=_MAX_TITLE_LEN)
    public_remark: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    remark_snippets_json: Any | None = None

    eingabetyp: int | None = None  # 0=Auswahl,1=Freitext,2=Betrag,4=Datum
    answer_type: TemplateAnswerType | None = None
    answer_set_id: str | None = Field(default=None, max_length=36)
    category_id: str | None = Field(default=None, max_length=36)

    legal_reference: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    relevant_documents_json: Any | None = None
    is_header_field: bool = False


class NodeUpdate(BaseModel):
    parent_id: str | None = Field(default=None, max_length=36)
    node_type: NodeType | None = None
    branch: NodeBranch | None = None
    ja_label: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    nein_label: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    decision_parent_id: str | None = Field(default=None, max_length=36)
    sort_order: int | None = None

    title: str | None = Field(default=None, max_length=_MAX_TITLE_LEN)
    public_remark: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    remark_snippets_json: Any | None = None

    eingabetyp: int | None = None
    answer_type: TemplateAnswerType | None = None
    answer_set_id: str | None = Field(default=None, max_length=36)
    category_id: str | None = Field(default=None, max_length=36)

    legal_reference: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    relevant_documents_json: Any | None = None
    is_header_field: bool | None = None


class NodeMove(BaseModel):
    """Reparent + Reorder eines Knotens."""
    parent_id: str | None = None
    sort_order: int = 0


class NodeOut(BaseModel):
    id: str
    template_id: str
    parent_id: str | None = None
    node_type: str
    branch: str | None = None
    ja_label: str | None = None
    nein_label: str | None = None
    decision_parent_id: str | None = None
    sort_order: int = 0

    title: str | None = None
    public_remark: str | None = None
    remark_snippets_json: Any | None = None

    eingabetyp: int | None = None
    answer_type: str | None = None
    answer_set_id: str | None = None
    category_id: str | None = None

    legal_reference: str | None = None
    relevant_documents_json: Any | None = None
    is_header_field: bool = False

    # Team-Workflow-Status des Knotens (pending/in_progress/resolved)
    status: str | None = None

    # Uebersetzungsfelder (nur Lese-Ausgabe; Pflege erfolgt in Phase 9)
    source_text_en: str | None = None
    translated_text_de: str | None = None
    review_text_de: str | None = None
    translation_status: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class NodeTreeOut(NodeOut):
    """Knoten mit verschachtelten Kindknoten fuer die Baum-Ausgabe."""
    children: list["NodeTreeOut"] = []


# ── Mitglieder & Einladungen ──────────────────────────────────────────────────

class MemberOut(BaseModel):
    """Mitgliedschaft eines Nutzers an einem Template, angereichert um die
    Nutzer-Stammdaten aus workshop_registrations (Name, Organisation,
    Bundesland, Funktion) fuer die Bund-Laender-Arbeitskreis-Anzeige."""
    id: str
    template_id: str
    user_id: str
    role: str
    invited_by_id: str | None = None
    created_at: datetime | None = None

    # Angereicherte Nutzer-Infos (aus Registration; nicht aus dem Member-Modell)
    user_name: str | None = None
    user_email: str | None = None
    organization: str | None = None
    bundesland: str | None = None
    function_role: str | None = None

    model_config = {"from_attributes": True}


class InviteOut(BaseModel):
    """Einladung zur Mitarbeit, angereichert um die Stammdaten des
    eingeladenen Nutzers."""
    id: str
    template_id: str
    invited_user_id: str
    invited_by_id: str | None = None
    role: str
    status: str
    created_at: datetime | None = None
    responded_at: datetime | None = None

    # Angereicherte Infos zum eingeladenen Nutzer
    invited_user_name: str | None = None
    invited_user_email: str | None = None
    organization: str | None = None
    bundesland: str | None = None
    function_role: str | None = None
    # Name des Einladenden (Komfort fuer das Frontend)
    invited_by_name: str | None = None

    model_config = {"from_attributes": True}


# ── Einladungs-/Rollen-Flow (Eingabe) ─────────────────────────────────────────

class InviteCreate(BaseModel):
    """Anlage einer Einladung durch den Owner. Die Owner-Rolle kann nicht
    vergeben werden (nur Eigentuemerschaft via Template-Erstellung)."""
    user_id: str = Field(..., min_length=1, max_length=36)
    role: MemberRole = MemberRole.VIEWER


class MemberRoleUpdate(BaseModel):
    """Aenderung der Rolle eines bestehenden Mitglieds durch den Owner."""
    role: MemberRole


# ── Template ──────────────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    source_language: str = Field("en", max_length=8)
    target_language: str = Field("de", max_length=8)
    source_document_name: str | None = Field(None, max_length=255)
    properties_json: Any | None = None
    status: TemplateStatus = TemplateStatus.DRAFT


class TemplateUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    source_language: str | None = Field(None, max_length=8)
    target_language: str | None = Field(None, max_length=8)
    source_document_name: str | None = Field(None, max_length=255)
    properties_json: Any | None = None
    statistics_json: Any | None = None
    status: TemplateStatus | None = None


class TemplateOut(BaseModel):
    id: str
    owner_id: str | None = None
    title: str
    description: str | None = None
    source_language: str
    target_language: str
    source_document_name: str | None = None
    properties_json: Any | None = None
    statistics_json: Any | None = None
    status: str
    node_count: int = 0
    my_role: str | None = None  # Rolle des anfragenden Nutzers
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TemplateDetailOut(TemplateOut):
    members: list[MemberOut] = []
    categories: list[CategoryOut] = []
    answer_sets: list[AnswerSetOut] = []
