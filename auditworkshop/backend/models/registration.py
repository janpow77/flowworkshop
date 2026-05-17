"""
flowworkshop · models/registration.py
Anmeldung, Tagesordnung, Themenboard.
"""
import enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, Enum, ForeignKey,
    BigInteger, JSON, func,
)
from sqlalchemy.orm import relationship

from database import Base


class AgendaItemType(str, enum.Enum):
    VORTRAG = "vortrag"
    DISKUSSION = "diskussion"
    WORKSHOP = "workshop"
    PAUSE = "pause"
    ORGANISATION = "organisation"


class AgendaItemStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    SKIPPED = "skipped"


class SubmissionVisibility(str, enum.Enum):
    PUBLIC = "public"
    MODERATION = "moderation"


class WorkshopMeta(Base):
    """Workshop-Metadaten (Singleton — immer nur eine Zeile)."""
    __tablename__ = "workshop_meta"

    id = Column(Integer, primary_key=True, default=1)
    title = Column(String(255), default="Prüferworkshop EFRE Hessen")
    subtitle = Column(String(500), default="KI und LLMs in der EFRE-Prüfbehörde")
    date = Column(String(50), default="")
    time = Column(String(50), default="09:00 - 16:00 Uhr")
    location_short = Column(String(255), default="")
    location_full = Column(String(500), default="")
    organizer = Column(String(255), default="Hessische Prüfbehörde")
    registration_deadline = Column(String(50), default="")
    qr_url = Column(String(500), default="")
    admin_pin = Column(String(20), default="1234")
    workshop_mode = Column(Boolean, default=False)  # False=Vorfeld, True=Workshop-Tag
    # Phase nach Veranstaltung — Plan v3.2 §5
    # 'live'    : Sidebar mit Szenarien, Anmeldung offen, HomePage aktiv
    # 'post'    : Hub-Kacheln werden Startseite, Tagesordnung read-only
    phase = Column(String(8), nullable=False, server_default="live")
    archive_started_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgendaItem(Base):
    __tablename__ = "workshop_agenda_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    day = Column(Integer, default=1)  # 1=Dienstag, 2=Mittwoch, 3=Donnerstag
    time = Column(String(20), nullable=False)
    duration_minutes = Column(Integer, default=30)
    item_type = Column(Enum(AgendaItemType), default=AgendaItemType.VORTRAG)
    title = Column(String(500), nullable=False)
    speaker = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    category = Column(String(50), default="plenary")  # plenary, workshop5
    status = Column(Enum(AgendaItemStatus), default=AgendaItemStatus.PENDING)
    started_at = Column(DateTime, nullable=True)  # Wann der Punkt gestartet wurde
    scenario_id = Column(Integer, nullable=True)  # Szenario 1-6 (optional)
    visible = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    page_url = Column(String(500), nullable=True)  # Interne Seite (z.B. /vorstellungsrunde)
    # Phase 4 — Material-Verknüpfung
    related_thread_ids = Column(JSON, nullable=True)
    related_file_ids = Column(JSON, nullable=True)
    notes_md = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    forum_posts = relationship(
        "AgendaForumPost",
        back_populates="agenda_item",
        cascade="all, delete-orphan",
    )


class Registration(Base):
    """User-Modell (Tabelle heißt aus historischen Gründen workshop_registrations).

    Nach Plan v3.2 erweitert um Rolle/Status/Bundesland/Funktion/Quota — die
    bisherige Token-only-Auth (qr_login_secret, invite_token) bleibt für die
    30-Tage-Übergangszeit gültig.
    """
    __tablename__ = "workshop_registrations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    organization = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    department = Column(String(255), nullable=True)
    fund = Column(String(100), nullable=True)  # EFRE, ESF, ESF+, INTERREG, etc.
    password_hash = Column(String(255), nullable=True)
    password_updated_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    qr_login_secret = Column(String(128), nullable=True)
    qr_secret_rotated_at = Column(DateTime, nullable=True)
    invite_token = Column(String(64), nullable=True, unique=True)
    privacy_accepted = Column(Boolean, default=False)
    # Einwilligung in einen KI-personalisierten Absatz in der Anmeldebestätigung.
    # Früher anthropic_consent — der Name war irreführend, weil im KI-Pfad
    # ausschließlich selbst betriebene Modelle (Qwen/BGE) auf eigener Hardware
    # verwendet werden. Idempotenter Rename via Lifespan-Migration in main.py.
    ai_confirmation_consent = Column(Boolean, default=False)
    filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Phase-0-Erweiterung (Plan v3.2 §3+§4)
    # role:    'attendee' | 'moderator' | 'admin'
    # status:  'pending_approval' | 'active' | 'rejected' | 'suspended'
    role = Column(String(16), nullable=False, server_default="attendee", index=True)
    status = Column(String(20), nullable=False, server_default="active", index=True)
    bundesland = Column(String(64), nullable=True)
    function_role = Column(String(80), nullable=True)
    signup_reason = Column(Text, nullable=True)
    avatar_path = Column(String(255), nullable=True)
    quota_bytes = Column(BigInteger, nullable=False, server_default="209715200")  # 200 MB
    used_bytes = Column(BigInteger, nullable=False, server_default="0")
    rejection_reason = Column(Text, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by_id = Column(String(36), nullable=True)  # admin user id
    deleted_at = Column(DateTime, nullable=True)


class PasswordResetToken(Base):
    """Vom Admin generierter Einmal-Token für Passwort-Reset (kein Mail-Versand).
    Admin kopiert den Klartext aus der Antwort, schickt ihn manuell an den User.
    """
    __tablename__ = "workshop_password_reset_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    purpose = Column(String(20), nullable=False, server_default="reset")  # 'reset' | 'setup'
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by_id = Column(String(36), nullable=True)  # admin user id


class SecurityAuditLog(Base):
    """Audit-Trail für Auth-/Admin-Aktionen (Plan v3.2 §3.5).

    Separat von models.audit_log.AuditLog (das ist Workshop-Aktivitäts-Log).
    """
    __tablename__ = "workshop_security_audit"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    target_type = Column(String(40), nullable=True)
    target_id = Column(String(64), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    ip_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class AgendaForumPost(Base):
    __tablename__ = "workshop_agenda_forum_posts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agenda_item_id = Column(
        String(36),
        ForeignKey("workshop_agenda_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_registration_id = Column(
        String(36),
        ForeignKey("workshop_registrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    author_name = Column(String(255), nullable=False)
    author_organization = Column(String(255), nullable=True)
    author_role = Column(String(50), nullable=False, default="participant")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    agenda_item = relationship("AgendaItem", back_populates="forum_posts")


class IcebreakerQuestion(Base):
    """Fragen fuer die Vorstellungsrunde."""
    __tablename__ = "workshop_icebreaker_questions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    label = Column(String(255), nullable=False)        # z.B. "Ihr Name"
    hint = Column(Text, nullable=True)                  # Erlaeuterung
    icon_name = Column(String(50), default="Users")     # Lucide-Icon-Name
    color = Column(String(50), default="blue")          # Farbschema
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class TopicSubmission(Base):
    __tablename__ = "workshop_topic_submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    registration_id = Column(String(36), nullable=True)
    topic = Column(String(500), nullable=False)
    question = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    visibility = Column(Enum(SubmissionVisibility), default=SubmissionVisibility.PUBLIC)
    anonymous = Column(Boolean, default=False)
    organization = Column(String(255), nullable=True)
    votes = Column(Integer, default=0)
    filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
