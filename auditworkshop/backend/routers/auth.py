"""
flowworkshop · routers/auth.py
Leichtgewichtige Workshop-Authentifizierung.
Teilnehmer loggen sich mit E-Mail ein (aus Registrierung).
Admin loggt sich mit PIN ein.
"""
import base64
import hashlib
import hmac
import uuid
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.registration import Registration
from models.audit_log import AuditLog
from config import AUTH_TOKEN_SECRET

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)

# In-Memory Session Store (fuer Workshop ausreichend)
_sessions: dict[str, dict] = {}

# Moderatoren-E-Mails (case-insensitive geprueft)
MODERATOR_EMAILS = {
    "jan.riener@wirtschaft.hessen.de",
    "alexander.lohse@wirtschaft.hessen.de",
    "alexander.lohse@smf.sachsen.de",
}


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
    return "moderator" if reg.email.lower() in MODERATOR_EMAILS else "participant"


def _create_session(reg: Registration, role: str) -> LoginResponse:
    token = str(uuid.uuid4())
    _sessions[token] = {
        "user_id": reg.id,
        "email": reg.email,
        "name": f"{reg.first_name} {reg.last_name}",
        "organization": reg.organization,
        "role": role,
        "created_at": _utcnow().isoformat(),
    }
    return LoginResponse(
        token=token,
        name=f"{reg.first_name} {reg.last_name}",
        organization=reg.organization,
        role=role,
    )


def _get_authenticated_registration(request: Request, db: Session) -> tuple[dict, Registration]:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = _sessions.get(token)
    if not session:
        raise HTTPException(401, "Nicht angemeldet.")

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
    return _create_session(reg, role)


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
    return _create_session(reg, role)


@router.get("/me")
def get_me(request: Request):
    """Gibt aktuelle Session-Infos zurueck."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = _sessions.get(token)
    if not session:
        raise HTTPException(401, "Nicht angemeldet.")
    return session


@router.post("/logout")
def logout(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    _sessions.pop(token, None)
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
def list_sessions(pin: str = ""):
    """Admin: Zeigt aktive Sessions."""
    if pin != "1234":
        raise HTTPException(403, "Falscher PIN.")
    return {
        "active_sessions": len(_sessions),
        "sessions": [
            {"name": s["name"], "organization": s["organization"], "created_at": s["created_at"]}
            for s in _sessions.values()
        ],
    }


# ── Audit-Trail Endpoints ────────────────────────────────────────────────────


@router.post("/audit")
def log_action(
    action: str, detail: str = "", request: Request = None, db: Session = Depends(get_db),
):
    """Loggt eine Aktion im Audit-Trail."""
    token = (
        request.headers.get("Authorization", "").replace("Bearer ", "")
        if request
        else ""
    )
    session = _sessions.get(token, {})
    entry = AuditLog(
        user_name=session.get("name", "Anonym"),
        organization=session.get("organization", ""),
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
