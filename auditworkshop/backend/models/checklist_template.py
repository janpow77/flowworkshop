"""
flowworkshop · models/checklist_template.py

Eigenstaendiges, projekt-UNGEBUNDENES Checklisten-Template-Subsystem fuer den
KOM-Musterchecklisten-Designer. Bewusst getrennt vom projektgebundenen
models/checklist.py (WorkshopChecklist → WorkshopQuestion).

Struktur 1:1 nach audit_designer (Knoten-Tree HEADING/QUESTION/DECISION/HINT,
JA/NEIN-Zweige, Decision-Trees) plus KOM-Felder (legal_reference,
relevant_documents). Antwortsets nach QChess-Modell (REVIEWANTWORTSET /
REVIEWANTWORT): definierbar als globale Bibliothek, pro Checkliste und je Frage.

Versionierung node-level (NodeChangeHistory-aequivalent), Mitglieder/Rollen,
In-App-Einladungen (kein Mail) und Node-Locks fuer die Hybrid-Kollaboration.
Hinweis: das In-App-Notification-Modell existiert bereits als
models.automation.Notification (workshop_notifications) und wird wiederverwendet.
"""
import enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base


# ── Wertebereiche (als String/Integer gespeichert; hier dokumentiert) ─────────

class NodeType(str, enum.Enum):
    HEADING = "HEADING"
    QUESTION = "QUESTION"
    DECISION = "DECISION"
    HINT = "HINT"


class NodeBranch(str, enum.Enum):
    JA = "JA"
    NEIN = "NEIN"


class TemplateAnswerType(str, enum.Enum):
    BOOLEAN = "BOOLEAN"          # Ja/Nein/Teilweise/Entfaellt
    BOOLEAN_JN = "BOOLEAN_JN"    # Ja/Nein
    CURRENCY = "CURRENCY"        # Betrag
    DATE = "DATE"
    CUSTOM_ENUM = "CUSTOM_ENUM"  # Optionen aus zugewiesenem Antwortset
    TEXT = "TEXT"                # Freitext / nur Bemerkung


# eingabetyp (QChess FRAGENTYPID): 0=Auswahl-Dropdown, 1=Freitext, 2=Betrag, 4=Datum
class EingabeTyp(int, enum.Enum):
    AUSWAHL = 0
    FREITEXT = 1
    BETRAG = 2
    DATUM = 4


class TemplateStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MemberRole(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    COMMENTER = "commenter"
    VIEWER = "viewer"


class InviteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"


class TranslationStatus(str, enum.Enum):
    UNTRANSLATED = "untranslated"
    GENERATING = "generating"
    PROPOSED = "proposed"      # KI-Entwurf liegt vor, wartet auf Admin-Review
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    ERROR = "error"


class NodeChangeType(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    MOVED = "moved"
    DUPLICATED = "duplicated"
    RESTORED = "restored"
    TRANSLATED = "translated"
    REVIEWED = "reviewed"


# ── Template (die "Kachel") ───────────────────────────────────────────────────

class ChecklistTemplate(Base):
    """KOM-Musterchecklist als eigenstaendiges Template (nicht projektgebunden)."""
    __tablename__ = "workshop_checklist_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source_language = Column(String(8), nullable=False, server_default="en")
    target_language = Column(String(8), nullable=False, server_default="de")
    # Quelldokument (PDF-Original der KOM-Checkliste)
    source_document_name = Column(String(255), nullable=True)
    source_document_path = Column(String(500), nullable=True)
    # Kopfblock-Metadaten (Audit code, CCI/Programme, prepared/reviewed …)
    properties_json = Column(JSONB, nullable=True)
    statistics_json = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, server_default="draft", index=True)
    # Aktuell freigegebene/aktive Versionsnummer (Verweis auf
    # ChecklistTemplateVersion.version_number); NULL = noch keine Version gesetzt.
    current_version = Column(String(40), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    nodes = relationship(
        "ChecklistTemplateNode", back_populates="template",
        cascade="all, delete-orphan",
    )
    versions = relationship(
        "ChecklistTemplateVersion", back_populates="template",
        cascade="all, delete-orphan",
    )
    answer_sets = relationship(
        "ChecklistAnswerSet", back_populates="template",
        cascade="all, delete-orphan",
    )
    categories = relationship(
        "ChecklistQuestionCategory", back_populates="template",
        cascade="all, delete-orphan",
    )
    members = relationship(
        "ChecklistMember", back_populates="template",
        cascade="all, delete-orphan",
    )
    invites = relationship(
        "ChecklistInvite", back_populates="template",
        cascade="all, delete-orphan",
    )


# ── Knoten (rekursiver Baum) ──────────────────────────────────────────────────

class ChecklistTemplateNode(Base):
    """Knoten im Checklisten-Baum (HEADING/QUESTION/DECISION/HINT)."""
    __tablename__ = "workshop_checklist_nodes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36),
        ForeignKey("workshop_checklist_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Selbstreferenz fuer beliebige Tiefe; Tree wird im Service aufgebaut.
    parent_id = Column(
        String(36),
        ForeignKey("workshop_checklist_nodes.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    node_type = Column(String(16), nullable=False, server_default="QUESTION")
    # Bearbeitungsstatus des Knotens im Team-Workflow:
    # pending = offen, in_progress = in Bearbeitung, resolved = erledigt.
    status = Column(String(16), nullable=False, server_default="pending")
    # Zweig unter einem DECISION-Knoten: "JA"/"NEIN"/NULL
    branch = Column(String(8), nullable=True)
    ja_label = Column(Text, nullable=True)    # Aussagesatz JA-Zweig (DECISION)
    nein_label = Column(Text, nullable=True)  # Aussagesatz NEIN-Zweig (DECISION)
    decision_parent_id = Column(String(36), nullable=True, index=True)
    sort_order = Column(Integer, nullable=False, server_default="0")

    title = Column(Text, nullable=True)
    public_remark = Column(Text, nullable=True)
    remark_snippets_json = Column(JSONB, nullable=True)

    # Antwortkonfiguration
    eingabetyp = Column(Integer, nullable=True)  # 0=Auswahl,1=Freitext,2=Betrag,4=Datum
    answer_type = Column(String(16), nullable=True)
    answer_set_id = Column(
        String(36),
        ForeignKey("workshop_checklist_answer_sets.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    category_id = Column(
        String(36),
        ForeignKey("workshop_checklist_categories.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # KOM-spezifisch
    legal_reference = Column(Text, nullable=True)          # Rechtsgrundlage
    relevant_documents_json = Column(JSONB, nullable=True)  # Belegverweise
    is_header_field = Column(Boolean, nullable=False, server_default="false")

    # Online-Uebersetzung EN→DE mit Admin-Review
    source_text_en = Column(Text, nullable=True)
    translated_text_de = Column(Text, nullable=True)
    review_text_de = Column(Text, nullable=True)
    translation_status = Column(String(16), nullable=True)
    translation_error = Column(Text, nullable=True)
    llm_model = Column(String(80), nullable=True)
    translated_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    template = relationship("ChecklistTemplate", back_populates="nodes")
    answer_set = relationship("ChecklistAnswerSet")

    __table_args__ = (
        Index("ix_cl_nodes_template_sort", "template_id", "sort_order"),
    )


# ── Antwortsets (QChess REVIEWANTWORTSET / REVIEWANTWORT) ──────────────────────

class ChecklistAnswerSet(Base):
    """Benannte Antwort-Menge. template_id NULL = globale, wiederverwendbare
    Bibliothek (wie QChess pro Firma); gesetzt = checklistenspezifisch."""
    __tablename__ = "workshop_checklist_answer_sets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36),
        ForeignKey("workshop_checklist_templates.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())

    template = relationship("ChecklistTemplate", back_populates="answer_sets")
    options = relationship(
        "ChecklistAnswerOption", back_populates="answer_set",
        cascade="all, delete-orphan", order_by="ChecklistAnswerOption.sort_order",
    )


class ChecklistAnswerOption(Base):
    """Einzelne Antwortoption eines Antwortsets (QChess REVIEWANTWORT)."""
    __tablename__ = "workshop_checklist_answer_options"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    answer_set_id = Column(
        String(36),
        ForeignKey("workshop_checklist_answer_sets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(120), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    is_standard = Column(Boolean, nullable=False, server_default="false")   # STANDARD
    is_entfaellt = Column(Boolean, nullable=False, server_default="false")  # ENTFAELLT
    value_number = Column(Float, nullable=True)   # wertzahl
    threshold = Column(Float, nullable=True)      # SCHWELLWERT
    bemerkung = Column(Text, nullable=True)

    answer_set = relationship("ChecklistAnswerSet", back_populates="options")


class ChecklistQuestionCategory(Base):
    """Optionale Fragenkategorie-Gruppierung je Checkliste."""
    __tablename__ = "workshop_checklist_categories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36),
        ForeignKey("workshop_checklist_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(120), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())

    template = relationship("ChecklistTemplate", back_populates="categories")


# ── Versionierung (node-level Change-Log, GitHub-artig) ───────────────────────

class ChecklistNodeHistory(Base):
    """Vollstaendiger Aenderungs-Verlauf je Knoten — Commit-History, Diff,
    Restore, "Blame". Entkoppelt von users/project_versions (changed_by_id →
    workshop_registrations)."""
    __tablename__ = "workshop_checklist_node_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(String(36), nullable=False, index=True)
    node_id = Column(String(36), nullable=False, index=True)
    node_version = Column(Integer, nullable=False, server_default="1")
    change_type = Column(String(16), nullable=False, index=True)

    node_snapshot = Column(JSONB, nullable=True)   # Voll-Snapshot des Knotens
    changed_fields = Column(JSONB, nullable=True)  # {feld: {old, new}} fuer Diff

    old_parent_id = Column(String(36), nullable=True)
    new_parent_id = Column(String(36), nullable=True)
    old_position = Column(Integer, nullable=True)
    new_position = Column(Integer, nullable=True)

    changed_by_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    change_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_cl_history_template_created", "template_id", "created_at"),
    )


# ── Mitglieder & Einladungen (In-App, kein Mail) ──────────────────────────────

class ChecklistMember(Base):
    """Mitgliedschaft eines Nutzers an einer Checkliste mit Rolle."""
    __tablename__ = "workshop_checklist_members"
    __table_args__ = (
        UniqueConstraint("template_id", "user_id", name="uq_cl_member"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36),
        ForeignKey("workshop_checklist_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role = Column(String(16), nullable=False, server_default="viewer")
    invited_by_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    template = relationship("ChecklistTemplate", back_populates="members")


class ChecklistInvite(Base):
    """Einladung zur Mitarbeit — als In-App-Mitteilung (Notification), KEIN Mail."""
    __tablename__ = "workshop_checklist_invites"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36),
        ForeignKey("workshop_checklist_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    invited_user_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    invited_by_id = Column(String(36), nullable=True)
    role = Column(String(16), nullable=False, server_default="viewer")
    status = Column(String(16), nullable=False, server_default="pending", index=True)
    created_at = Column(DateTime, server_default=func.now())
    responded_at = Column(DateTime, nullable=True)

    template = relationship("ChecklistTemplate", back_populates="invites")


# ── Node-Locking (Hybrid-Kollaboration) ───────────────────────────────────────

class ChecklistNodeLock(Base):
    """Kurzlebiger Lock auf einen Knoten waehrend der Bearbeitung (Presence +
    Lock + SSE). Ein Lock je Knoten (UniqueConstraint), Auto-Expiry."""
    __tablename__ = "workshop_checklist_node_locks"
    __table_args__ = (
        UniqueConstraint("node_id", name="uq_cl_node_lock"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    node_id = Column(
        String(36),
        ForeignKey("workshop_checklist_nodes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    template_id = Column(String(36), nullable=False, index=True)
    locked_by_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    locked_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False, index=True)


# ── Team-Diskussion / Kommentar-Threads je Knoten ─────────────────────────────

class ChecklistNodeComment(Base):
    """Kommentar/Diskussionsbeitrag an einem Knoten für die Team-Abstimmung.

    Unterstützt eine flache Antwort-Ebene über ``parent_comment_id`` (Self-Ref
    als plain FK-Spalte, ohne ORM-relationship — Abfrage erfolgt per FK). Löschen
    erfolgt soft über ``deleted_at``, damit Threads erhalten bleiben.
    """
    __tablename__ = "workshop_checklist_node_comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36),
        ForeignKey("workshop_checklist_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    node_id = Column(
        String(36),
        ForeignKey("workshop_checklist_nodes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    author_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    message = Column(Text, nullable=False)
    # Self-Referenz für eine Antwort-Ebene (Threading); bewusst ohne relationship.
    parent_comment_id = Column(String(36), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    edited_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)


# ── Unread-Tracking für Kommentare (Lesebestätigungen) ────────────────────────

class ChecklistNoteRead(Base):
    """Lesebestätigung eines Nutzers für einen Kommentar (Unread-Zähler).

    Ein Eintrag je (Nutzer, Kommentar); fehlt der Eintrag, gilt der Kommentar
    für diesen Nutzer als ungelesen. Bewusst nur plain FK-Spalten ohne
    relationship, um Mapper-Verflechtungen zu vermeiden.
    """
    __tablename__ = "workshop_checklist_note_reads"
    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="uq_cl_note_read"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    template_id = Column(String(36), nullable=False, index=True)
    node_id = Column(String(36), nullable=False, index=True)
    comment_id = Column(String(36), nullable=False, index=True)
    read_at = Column(DateTime, server_default=func.now())


# ── Ganz-Checklisten-Versionen (Snapshots des gesamten Baums) ─────────────────

class ChecklistTemplateVersion(Base):
    """Vollständiger Snapshot einer Checkliste als benannte Version.

    Im Gegensatz zur node-level ``ChecklistNodeHistory`` hält dieses Modell den
    kompletten Baum (``tree_snapshot``) als eingefrorene Gesamtversion fest —
    z.B. für Freigaben/Releases. ``is_frozen`` markiert unveränderliche Stände,
    ``status`` unterscheidet draft/released.
    """
    __tablename__ = "workshop_checklist_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(
        String(36),
        ForeignKey("workshop_checklist_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_number = Column(String(40), nullable=False)
    is_frozen = Column(Boolean, nullable=False, server_default="false")
    status = Column(String(16), nullable=False, server_default="draft")  # draft/released
    tree_snapshot = Column(JSONB, nullable=True)
    created_by_id = Column(String(36), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    template = relationship("ChecklistTemplate", back_populates="versions")


# ── Referenzdokumente je Knoten (Belegverweise) ───────────────────────────────

class ChecklistNodeReferenceDoc(Base):
    """Verknüpfung eines Knotens mit einem Referenzdokument/Beleg.

    Hält Anzeigename, optionalen Pfad und optionalen Referenztext (z.B. zitierte
    Passage). Bewusst nur plain FK-Spalten ohne relationship.
    """
    __tablename__ = "workshop_checklist_node_refdocs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(String(36), nullable=False, index=True)
    node_id = Column(
        String(36),
        ForeignKey("workshop_checklist_nodes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_name = Column(String(255), nullable=False)
    document_path = Column(String(500), nullable=True)
    reference_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
