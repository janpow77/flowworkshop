"""
flowworkshop · routers/auth.py
Leichtgewichtige Workshop-Authentifizierung.
Teilnehmer loggen sich mit E-Mail ein (aus Registrierung).
Admin loggt sich mit PIN ein.
"""
import base64
import hashlib
import hmac
import os
import uuid
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models.registration import Registration, PasswordResetToken, SecurityAuditLog
from models.audit_log import AuditLog
from models.session import WorkshopSession
from config import AUTH_TOKEN_SECRET, WORKER_API_TOKEN
from services.country_profiles import REGIONS_FLAT

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)

# Moderatoren-E-Mails (case-insensitive geprueft) — Legacy-Fallback,
# wenn DB-Spalte role noch nicht gesetzt ist (vor Migration).
MODERATOR_EMAILS = {
    "jan.riener@wirtschaft.hessen.de",
    "alexander.lohse@wirtschaft.hessen.de",
    "alexander.lohse@smf.sachsen.de",
}
ADMIN_EMAILS = {"jan.riener@wirtschaft.hessen.de"}

# Erlaubte Werte für die Bundesland-Whitelist (DE+AT+Bund je); werden
# zentral aus country_profiles abgefragt.
ALLOWED_BUNDESLAENDER = REGIONS_FLAT


class LoginRequest(BaseModel):
    email: str
    password: str | None = None


class LoginResponse(BaseModel):
    token: str
    name: str
    organization: str
    role: str  # "participant" oder "admin"


class QrLoginRequest(BaseModel):
    token: str


class PasswordChangeRequest(BaseModel):
    current_password: str | None = None
    new_password: str


class AccountOut(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    name: str
    organization: str
    role: str
    has_password: bool
    last_login_at: str | None = None
    qr_login_token: str
    qr_login_path: str
    qr_valid_until: str
    qr_rotated_at: str | None = None


class GeneratedPasswordOut(BaseModel):
    temporary_password: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 240_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def _verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations_str, salt_b64, digest_b64 = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64 + "=" * (-len(salt_b64) % 4))
        expected = base64.urlsafe_b64decode(digest_b64 + "=" * (-len(digest_b64) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_str))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _ensure_qr_secret(reg: Registration) -> None:
    if reg.qr_login_secret:
        return
    reg.qr_login_secret = secrets.token_urlsafe(32)
    reg.qr_secret_rotated_at = _utcnow()


def _make_qr_login_token(reg: Registration, expires_at: datetime) -> str:
    _ensure_qr_secret(reg)
    expires_ts = int(expires_at.timestamp())
    message = f"{reg.id}:{expires_ts}:{reg.qr_login_secret}".encode("utf-8")
    signature = hmac.new(AUTH_TOKEN_SECRET.encode("utf-8"), message, hashlib.sha256).digest()
    return f"{reg.id}.{expires_ts}.{_b64url_encode(signature)}"


def _resolve_role(reg: Registration) -> str:
    """Bestimmt die Rolle für die Session.
    Priorität: DB-Feld `role` (neu, Plan v3.2) → MODERATOR_EMAILS-Fallback.
    Mapping 'attendee' → 'participant' für Backwards-Compat im Frontend.
    """
    db_role = (getattr(reg, "role", None) or "").strip().lower()
    if db_role == "admin":
        return "admin"
    if db_role == "moderator":
        return "moderator"
    if db_role == "attendee":
        return "participant"
    # Fallback: Hardcoded-Liste für nicht-migrierte Zeilen
    if reg.email.lower() in ADMIN_EMAILS:
        return "admin"
    return "moderator" if reg.email.lower() in MODERATOR_EMAILS else "participant"


def _extract_token(request: Request) -> str:
    return request.headers.get("Authorization", "").replace("Bearer ", "").strip()


def _load_session(token: str) -> dict | None:
    """Liest eine persistente Session aus der DB und aktualisiert last_seen_at."""
    if not token:
        return None
    db = SessionLocal()
    try:
        sess = db.query(WorkshopSession).filter(WorkshopSession.token == token).first()
        if not sess:
            return None
        sess.last_seen_at = _utcnow().replace(tzinfo=None)
        db.commit()
        return {
            "user_id": sess.user_id,
            "email": sess.email,
            "name": sess.name,
            "organization": sess.organization,
            "role": sess.role,
            "created_at": sess.created_at.isoformat() if sess.created_at else None,
        }
    finally:
        db.close()


def _session_from_request(request: Request) -> dict | None:
    return _load_session(_extract_token(request))


def require_session(request: Request) -> dict:
    """FastAPI dependency: verlangt eine gueltige Workshop-Session."""
    session = _session_from_request(request)
    if not session:
        raise HTTPException(401, "Nicht angemeldet.")
    return session


def _resolve_session_optional(request: Request) -> dict | None:
    """Best-effort Lookup der Session ohne 401-Fehler.

    Liest den Authorization-Header und liefert das Session-Dict (falls
    erkannt) oder ``None`` — also genau ``_session_from_request``, aber als
    explizit benannter Pass-Through-Helfer fuer Middleware/Logging.
    Wirft niemals Exceptions: bei DB-Problemen wird ``None`` zurueckgegeben.
    """
    try:
        return _session_from_request(request)
    except Exception:  # noqa: BLE001 — Logging darf den Request nicht stoppen
        return None


def require_moderator(request: Request) -> dict:
    """FastAPI dependency: verlangt mindestens Moderator-Rolle (auch admin)."""
    session = require_session(request)
    email = str(session.get("email", "")).lower()
    role = session.get("role", "")
    if role in ("moderator", "admin") or email in MODERATOR_EMAILS or email in ADMIN_EMAILS:
        return session
    raise HTTPException(403, "Moderator-Login erforderlich.")


def require_moderator_or_worker(request: Request) -> dict:
    """Erlaubt Moderator/Admin oder den internen Automations-Worker."""
    worker_token = request.headers.get("X-Worker-Token", "").strip()
    if worker_token and hmac.compare_digest(worker_token, WORKER_API_TOKEN):
        return {
            "user_id": "system-worker",
            "email": "system-worker@local",
            "name": "System Worker",
            "organization": "Auditworkshop",
            "role": "worker",
        }
    return require_moderator(request)


def require_admin(request: Request) -> dict:
    """FastAPI dependency: verlangt Admin-Rolle."""
    session = require_session(request)
    email = str(session.get("email", "")).lower()
    if session.get("role") == "admin" or email in ADMIN_EMAILS:
        return session
    raise HTTPException(403, "Admin-Login erforderlich.")


def _create_session(reg: Registration, role: str, db: Session) -> LoginResponse:
    token = str(uuid.uuid4())
    sess = WorkshopSession(
        token=token,
        user_id=reg.id,
        email=reg.email,
        name=f"{reg.first_name} {reg.last_name}",
        organization=reg.organization or "",
        role=role,
    )
    db.add(sess)
    db.commit()
    return LoginResponse(
        token=token,
        name=f"{reg.first_name} {reg.last_name}",
        organization=reg.organization,
        role=role,
    )


def _get_authenticated_registration(request: Request, db: Session) -> tuple[dict, Registration]:
    session = require_session(request)

    reg = db.query(Registration).filter(Registration.id == session.get("user_id")).first()
    if not reg:
        raise HTTPException(401, "Anmeldung zur Sitzung nicht gefunden.")
    return session, reg


def _build_account_payload(reg: Registration, role: str) -> AccountOut:
    expires_at = _utcnow() + timedelta(days=180)
    qr_token = _make_qr_login_token(reg, expires_at)
    return AccountOut(
        user_id=reg.id,
        email=reg.email,
        first_name=reg.first_name,
        last_name=reg.last_name,
        name=f"{reg.first_name} {reg.last_name}",
        organization=reg.organization,
        role=role,
        has_password=bool(reg.password_hash),
        last_login_at=reg.last_login_at.isoformat() if reg.last_login_at else None,
        qr_login_token=qr_token,
        qr_login_path=f"/?qr={qr_token}",
        qr_valid_until=expires_at.isoformat(),
        qr_rotated_at=reg.qr_secret_rotated_at.isoformat() if reg.qr_secret_rotated_at else None,
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Login mit registrierter E-Mail-Adresse."""
    email_lower = body.email.strip().lower()
    reg = db.query(Registration).filter(
        func.lower(Registration.email) == email_lower
    ).first()
    if not reg:
        raise HTTPException(401, "E-Mail nicht registriert. Bitte zuerst anmelden.")

    # Status-Check (Plan v3.2 §3): pending_approval / rejected / suspended blocken
    user_status = (getattr(reg, "status", None) or "active").lower()
    if user_status == "pending_approval":
        raise HTTPException(
            403,
            "Ihre Anmeldung wartet noch auf die Freischaltung durch den Admin.",
        )
    if user_status == "rejected":
        raise HTTPException(403, "Anmeldung wurde abgelehnt.")
    if user_status == "suspended":
        raise HTTPException(403, "Konto ist suspendiert.")

    if reg.password_hash:
        if not body.password:
            raise HTTPException(401, "Für dieses Konto ist ein Passwort erforderlich.")
        if not _verify_password(body.password, reg.password_hash):
            raise HTTPException(401, "E-Mail oder Passwort sind nicht korrekt.")

    role = _resolve_role(reg)
    reg.last_login_at = _utcnow()
    _ensure_qr_secret(reg)
    db.commit()

    log.info("Login: %s (%s) role=%s", reg.email, reg.organization, role)
    return _create_session(reg, role, db)


@router.post("/qr-login", response_model=LoginResponse)
def qr_login(body: QrLoginRequest, db: Session = Depends(get_db)):
    try:
        user_id, expires_ts_raw, signature = body.token.split(".", 2)
        expires_ts = int(expires_ts_raw)
    except ValueError as exc:
        raise HTTPException(401, "QR-Code ist ungültig.") from exc

    reg = db.query(Registration).filter(Registration.id == user_id).first()
    if not reg or not reg.qr_login_secret:
        raise HTTPException(401, "QR-Code ist ungültig oder wurde zurückgesetzt.")
    if expires_ts < int(_utcnow().timestamp()):
        raise HTTPException(401, "QR-Code ist abgelaufen. Bitte im Konto neu erzeugen.")

    message = f"{reg.id}:{expires_ts}:{reg.qr_login_secret}".encode("utf-8")
    expected = _b64url_encode(hmac.new(AUTH_TOKEN_SECRET.encode("utf-8"), message, hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "QR-Code ist ungültig oder wurde zurückgesetzt.")

    role = _resolve_role(reg)
    reg.last_login_at = _utcnow()
    db.commit()
    log.info("QR-Login: %s (%s) role=%s", reg.email, reg.organization, role)
    return _create_session(reg, role, db)


@router.get("/me")
def get_me(request: Request):
    """Gibt aktuelle Session-Infos zurueck."""
    session = _session_from_request(request)
    if not session:
        raise HTTPException(401, "Nicht angemeldet.")
    return session


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = _extract_token(request)
    if token:
        db.query(WorkshopSession).filter(WorkshopSession.token == token).delete()
        db.commit()
    return {"status": "logged_out"}


@router.get("/account", response_model=AccountOut)
def get_account(request: Request, db: Session = Depends(get_db)):
    session, reg = _get_authenticated_registration(request, db)
    _ensure_qr_secret(reg)
    db.commit()
    return _build_account_payload(reg, session.get("role", _resolve_role(reg)))


@router.post("/account/password", response_model=AccountOut)
def update_password(body: PasswordChangeRequest, request: Request, db: Session = Depends(get_db)):
    session, reg = _get_authenticated_registration(request, db)
    new_password = body.new_password.strip()
    if len(new_password) < 10:
        raise HTTPException(400, "Das neue Passwort muss mindestens 10 Zeichen haben.")
    if reg.password_hash and not body.current_password:
        raise HTTPException(400, "Bitte das aktuelle Passwort angeben.")
    if reg.password_hash and not _verify_password(body.current_password or "", reg.password_hash):
        raise HTTPException(401, "Das aktuelle Passwort ist nicht korrekt.")

    reg.password_hash = _hash_password(new_password)
    reg.password_updated_at = _utcnow()
    _ensure_qr_secret(reg)
    db.commit()
    db.refresh(reg)
    return _build_account_payload(reg, session.get("role", _resolve_role(reg)))


@router.post("/account/password/generate", response_model=GeneratedPasswordOut)
def generate_password(request: Request, db: Session = Depends(get_db)):
    _session, reg = _get_authenticated_registration(request, db)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!$%&*+-?"
    generated = "".join(secrets.choice(alphabet) for _ in range(16))
    reg.password_hash = _hash_password(generated)
    reg.password_updated_at = _utcnow()
    _ensure_qr_secret(reg)
    db.commit()
    return GeneratedPasswordOut(temporary_password=generated)


@router.post("/account/qr/rotate", response_model=AccountOut)
def rotate_qr_secret(request: Request, db: Session = Depends(get_db)):
    session, reg = _get_authenticated_registration(request, db)
    reg.qr_login_secret = secrets.token_urlsafe(32)
    reg.qr_secret_rotated_at = _utcnow()
    db.commit()
    db.refresh(reg)
    return _build_account_payload(reg, session.get("role", _resolve_role(reg)))


@router.get("/sessions")
def list_sessions(pin: str = "", db: Session = Depends(get_db)):
    """Admin: Zeigt aktive Sessions."""
    if pin != "1234":
        raise HTTPException(403, "Falscher PIN.")
    sessions = db.query(WorkshopSession).order_by(WorkshopSession.last_seen_at.desc()).all()
    return {
        "active_sessions": len(sessions),
        "sessions": [
            {
                "name": s.name,
                "organization": s.organization,
                "role": s.role,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
            }
            for s in sessions
        ],
    }


# ── Audit-Trail Endpoints ────────────────────────────────────────────────────


@router.post("/audit")
def log_action(
    action: str, detail: str = "", request: Request = None, db: Session = Depends(get_db),
):
    """Loggt eine Aktion im Audit-Trail."""
    session = _session_from_request(request) if request else None
    entry = AuditLog(
        user_name=(session or {}).get("name", "Anonym"),
        organization=(session or {}).get("organization", ""),
        action=action,
        detail=detail[:500],
    )
    db.add(entry)
    db.commit()
    return {"status": "logged"}


@router.get("/audit/log")
def get_audit_log(pin: str = "", limit: int = 50, db: Session = Depends(get_db)):
    """Admin: Zeigt Audit-Log."""
    if pin != "1234":
        raise HTTPException(403, "Falscher PIN.")
    entries = (
        db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    )
    return {
        "count": len(entries),
        "entries": [
            {
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "user_name": e.user_name,
                "organization": e.organization,
                "action": e.action,
                "detail": e.detail,
            }
            for e in entries
        ],
    }


# ─────────────────────────────────────────────────────────────────────
# Phase 0 — Selbstanmeldung + Admin-Approval (Plan v3.2 §3)
# ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    organization: str
    bundesland: str
    function_role: str
    signup_reason: str | None = None
    privacy_accepted: bool


class SignupResponse(BaseModel):
    status: str  # "pending_approval"
    message: str


def _validate_password_strength(pw: str) -> str | None:
    if len(pw) < 10:
        return "Passwort muss mindestens 10 Zeichen lang sein."
    if not any(c.isdigit() for c in pw):
        return "Passwort muss mindestens eine Ziffer enthalten."
    if not any(not c.isalnum() for c in pw):
        return "Passwort muss mindestens ein Sonderzeichen enthalten."
    return None


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(
    body: SignupRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Selbstregistrierung — kein Mail-Verify, Account ist `pending_approval`,
    Admin schaltet später frei. Pflichtfelder gemäß Plan v3.2 §3.4.
    """
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(422, "Bitte gültige E-Mail-Adresse angeben.")
    if not body.privacy_accepted:
        raise HTTPException(422, "Datenschutz-Einwilligung erforderlich.")
    pw_err = _validate_password_strength(body.password)
    if pw_err:
        raise HTTPException(422, pw_err)
    if len(body.first_name.strip()) < 2 or len(body.last_name.strip()) < 2:
        raise HTTPException(422, "Bitte Vor- und Nachname angeben.")
    if len(body.organization.strip()) < 3:
        raise HTTPException(422, "Bitte vollständigen Behörden-/Organisationsnamen angeben.")
    if body.bundesland not in ALLOWED_BUNDESLAENDER:
        raise HTTPException(422, "Bundesland nicht in Liste enthalten.")
    if len(body.function_role.strip()) < 2:
        raise HTTPException(422, "Bitte Funktion angeben.")

    existing = db.query(Registration).filter(func.lower(Registration.email) == email).first()
    if existing:
        # Generische Antwort, um keine User-Enumeration zu erlauben
        return SignupResponse(
            status="pending_approval",
            message="Anmeldung eingegangen. Sie werden vom Admin geprüft.",
        )

    new = Registration(
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        organization=body.organization.strip(),
        email=email,
        bundesland=body.bundesland,
        function_role=body.function_role.strip(),
        signup_reason=(body.signup_reason or "").strip()[:2000] or None,
        password_hash=_hash_password(body.password),
        password_updated_at=_utcnow().replace(tzinfo=None),
        role="attendee",
        status="pending_approval",
        privacy_accepted=True,
    )
    db.add(new)
    db.commit()
    log.info("Signup: %s wartet auf Admin-Approval (id=%s)", email, new.id)

    # Notification an alle Admins (Plan v3.2 §6 — internes Bell-Icon)
    try:
        from routers.notifications import push_notification
        admins = db.query(Registration).filter(Registration.role == "admin").all()
        for adm in admins:
            push_notification(
                user_id=adm.id,
                kind="admin_pending",
                title=f"Neue Anmeldung wartet: {new.first_name} {new.last_name}",
                body=f"{new.organization} · {new.email}",
                link="/admin",
            )
    except Exception:
        log.exception("Admin-Pending-Notification fehlgeschlagen")

    # E-Mail-Benachrichtigung an ADMIN_NOTIFY_EMAIL (Background-Task, damit
    # SMTP-Latenz die Signup-Response nicht verzögert)
    try:
        from services.email_service import send_signup_alert
        background_tasks.add_task(
            send_signup_alert,
            user_id=new.id,
            first_name=new.first_name,
            last_name=new.last_name,
            email=new.email,
            organization=new.organization,
            bundesland=new.bundesland,
            function_role=new.function_role,
            signup_reason=new.signup_reason,
        )
    except Exception:  # noqa: BLE001 — Mailfehler darf Signup nicht killen
        log.exception("send_signup_alert konnte nicht eingereiht werden")

    return SignupResponse(
        status="pending_approval",
        message=(
            "Anmeldung eingegangen. Nach Freischaltung durch den Admin "
            "können Sie sich mit Ihrer E-Mail-Adresse und dem von Ihnen "
            "vergebenen Passwort einloggen."
        ),
    )


# ── Admin-User-Verwaltung ───────────────────────────────────────────

class UserListEntry(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    organization: str
    bundesland: str | None = None
    function_role: str | None = None
    signup_reason: str | None = None
    role: str
    status: str
    created_at: str | None = None
    approved_at: str | None = None
    last_login_at: str | None = None


class UserListResponse(BaseModel):
    count: int
    users: list[UserListEntry]


def _user_to_entry(u: Registration) -> UserListEntry:
    return UserListEntry(
        id=u.id, email=u.email,
        first_name=u.first_name, last_name=u.last_name,
        organization=u.organization or "",
        bundesland=u.bundesland,
        function_role=u.function_role,
        signup_reason=u.signup_reason,
        role=u.role or "attendee",
        status=u.status or "active",
        created_at=u.created_at.isoformat() if u.created_at else None,
        approved_at=u.approved_at.isoformat() if u.approved_at else None,
        last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
    )


@router.get("/users", response_model=UserListResponse)
def admin_list_users(
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Admin: Alle Nutzer auflisten, optional gefiltert nach status."""
    require_admin(request)
    q = db.query(Registration).filter(Registration.deleted_at.is_(None))
    if status:
        q = q.filter(Registration.status == status)
    rows = q.order_by(Registration.created_at.desc().nullslast()).all()
    return UserListResponse(count=len(rows), users=[_user_to_entry(u) for u in rows])


class UserActionResponse(BaseModel):
    status: str
    user: UserListEntry


@router.post("/users/{user_id}/approve", response_model=UserActionResponse)
def admin_approve_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    """Admin: User freischalten — Status pending_approval → active."""
    actor = require_admin(request)
    u = db.query(Registration).filter(Registration.id == user_id).first()
    if not u:
        raise HTTPException(404, "User nicht gefunden.")
    if u.status == "active":
        return UserActionResponse(status="already_active", user=_user_to_entry(u))
    u.status = "active"
    u.approved_at = _utcnow().replace(tzinfo=None)
    u.approved_by_id = actor.get("user_id")
    db.commit()
    log.info("admin_approve_user: %s durch %s", u.email, actor.get("email"))
    return UserActionResponse(status="approved", user=_user_to_entry(u))


class UserRejectRequest(BaseModel):
    reason: str | None = None


@router.post("/users/{user_id}/reject", response_model=UserActionResponse)
def admin_reject_user(
    user_id: str, body: UserRejectRequest, request: Request, db: Session = Depends(get_db),
):
    actor = require_admin(request)
    u = db.query(Registration).filter(Registration.id == user_id).first()
    if not u:
        raise HTTPException(404, "User nicht gefunden.")
    u.status = "rejected"
    u.rejection_reason = (body.reason or "").strip()[:1000] or None
    db.commit()
    log.info("admin_reject_user: %s durch %s", u.email, actor.get("email"))
    return UserActionResponse(status="rejected", user=_user_to_entry(u))


@router.post("/users/{user_id}/suspend", response_model=UserActionResponse)
def admin_suspend_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    actor = require_admin(request)
    u = db.query(Registration).filter(Registration.id == user_id).first()
    if not u:
        raise HTTPException(404, "User nicht gefunden.")
    u.status = "suspended"
    db.commit()
    # alle Sessions des Users invalidieren
    db.query(WorkshopSession).filter(WorkshopSession.user_id == u.id).delete()
    db.commit()
    log.info("admin_suspend_user: %s durch %s", u.email, actor.get("email"))
    return UserActionResponse(status="suspended", user=_user_to_entry(u))


class RoleChangeRequest(BaseModel):
    role: str  # 'attendee' | 'moderator' | 'admin'


@router.patch("/users/{user_id}/role", response_model=UserActionResponse)
def admin_change_role(
    user_id: str, body: RoleChangeRequest, request: Request, db: Session = Depends(get_db),
):
    actor = require_admin(request)
    if body.role not in ("attendee", "moderator", "admin"):
        raise HTTPException(422, "Ungültige Rolle.")
    u = db.query(Registration).filter(Registration.id == user_id).first()
    if not u:
        raise HTTPException(404, "User nicht gefunden.")
    u.role = body.role
    if body.role == "moderator" and (u.quota_bytes or 0) < 1024 * 1024 * 1024:
        u.quota_bytes = 1024 * 1024 * 1024  # 1 GB
    if body.role == "admin":
        u.quota_bytes = 9223372036854775807
    db.commit()
    log.info("admin_change_role: %s → %s durch %s", u.email, body.role, actor.get("email"))
    return UserActionResponse(status="ok", user=_user_to_entry(u))


class ResetTokenResponse(BaseModel):
    token: str
    expires_at: str
    setup_url: str
    user_email: str


@router.post("/users/{user_id}/reset-token", response_model=ResetTokenResponse)
def admin_create_reset_token(
    user_id: str, request: Request, db: Session = Depends(get_db),
):
    """Admin: einmaligen Setup-/Reset-Token generieren. Klartext im Response —
    Admin kopiert + verschickt manuell (kein Mail).
    """
    actor = require_admin(request)
    u = db.query(Registration).filter(Registration.id == user_id).first()
    if not u:
        raise HTTPException(404, "User nicht gefunden.")
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = _utcnow().replace(tzinfo=None) + timedelta(hours=24)
    rt = PasswordResetToken(
        user_id=u.id,
        token_hash=token_hash,
        purpose="setup" if not u.password_hash else "reset",
        expires_at=expires,
        created_by_id=actor.get("user_id"),
    )
    db.add(rt)
    db.commit()
    log.info("reset-token erstellt für %s durch %s", u.email, actor.get("email"))
    return ResetTokenResponse(
        token=raw,
        expires_at=expires.isoformat(),
        setup_url=f"/account/setup-password?token={raw}",
        user_email=u.email,
    )


class InviteResponse(BaseModel):
    status: str
    user_email: str
    setup_url: str
    expires_at: str
    mail_sent: bool


@router.post("/users/{user_id}/send-invite", response_model=InviteResponse)
async def admin_send_invite(
    user_id: str, request: Request, db: Session = Depends(get_db),
):
    """Admin: erzeugt einmaligen Setup-Token und schickt ihn dem User per Mail.

    Kombiniert reset-token + send_account_invite, damit der Admin nicht den
    Token kopieren und manuell verschicken muss. Wenn SMTP nicht konfiguriert
    ist, wird der Token trotzdem erstellt und in der Response zurückgegeben,
    damit der Admin auf den manuellen Pfad zurückfallen kann.
    """
    actor = require_admin(request)
    u = db.query(Registration).filter(Registration.id == user_id).first()
    if not u:
        raise HTTPException(404, "User nicht gefunden.")
    if u.status not in ("active", "pending_approval"):
        raise HTTPException(
            409,
            f"Einladung nicht versendbar — Status ist {u.status}.",
        )

    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = _utcnow().replace(tzinfo=None) + timedelta(hours=24)
    rt = PasswordResetToken(
        user_id=u.id,
        token_hash=token_hash,
        purpose="setup" if not u.password_hash else "reset",
        expires_at=expires,
        created_by_id=actor.get("user_id"),
    )
    db.add(rt)
    db.commit()

    from services.email_service import is_configured, send_account_invite

    public_base = (
        os.getenv("EMAIL_PUBLIC_URL")
        or "https://workshop.flowaudit.de"
    ).rstrip("/")
    relative = f"/account/setup-password?token={raw}"
    full_setup_url = f"{public_base}{relative}"

    mail_sent = False
    if is_configured():
        try:
            mail_sent = await send_account_invite(
                first_name=u.first_name,
                last_name=u.last_name,
                email=u.email,
                setup_url=full_setup_url,
            )
        except Exception:  # noqa: BLE001 — Mailfehler darf den Endpoint nicht killen
            log.exception("send_account_invite fehlgeschlagen für %s", u.email)
            mail_sent = False

    log.info(
        "send-invite: user=%s mail_sent=%s actor=%s",
        u.email, mail_sent, actor.get("email"),
    )
    return InviteResponse(
        status="sent" if mail_sent else "token_only",
        user_email=u.email,
        setup_url=full_setup_url,
        expires_at=expires.isoformat(),
        mail_sent=mail_sent,
    )


class SetupPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/setup-password")
def setup_password(body: SetupPasswordRequest, db: Session = Depends(get_db)):
    """User klickt Admin-Link → setzt Passwort über einmaligen Token.

    Funktioniert sowohl für initial-setup als auch für Reset.
    """
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    rt = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )
    if not rt:
        raise HTTPException(400, "Link ungültig.")
    if rt.used_at:
        raise HTTPException(400, "Link wurde bereits verwendet.")
    if rt.expires_at < _utcnow().replace(tzinfo=None):
        raise HTTPException(400, "Link ist abgelaufen.")
    pw_err = _validate_password_strength(body.new_password)
    if pw_err:
        raise HTTPException(422, pw_err)
    u = db.query(Registration).filter(Registration.id == rt.user_id).first()
    if not u:
        raise HTTPException(404, "Nutzer nicht gefunden.")
    u.password_hash = _hash_password(body.new_password)
    u.password_updated_at = _utcnow().replace(tzinfo=None)
    rt.used_at = _utcnow().replace(tzinfo=None)
    # Bei reset: alle bestehenden Sessions invalidieren
    if rt.purpose == "reset":
        db.query(WorkshopSession).filter(WorkshopSession.user_id == u.id).delete()
    db.commit()
    log.info("setup-password angewendet für %s (purpose=%s)", u.email, rt.purpose)
    return {"status": "ok", "purpose": rt.purpose}
