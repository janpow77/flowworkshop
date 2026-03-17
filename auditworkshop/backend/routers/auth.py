"""
flowworkshop · routers/auth.py
Leichtgewichtige Workshop-Authentifizierung.
Teilnehmer loggen sich mit E-Mail ein (aus Registrierung).
Admin loggt sich mit PIN ein.
"""
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.registration import Registration
from models.audit_log import AuditLog

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)

# In-Memory Session Store (fuer Workshop ausreichend)
_sessions: dict[str, dict] = {}


class LoginRequest(BaseModel):
    email: str


class LoginResponse(BaseModel):
    token: str
    name: str
    organization: str
    role: str  # "participant" oder "admin"


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Login mit registrierter E-Mail-Adresse."""
    reg = db.query(Registration).filter(Registration.email == body.email).first()
    if not reg:
        raise HTTPException(401, "E-Mail nicht registriert. Bitte zuerst anmelden.")

    token = str(uuid.uuid4())
    _sessions[token] = {
        "user_id": reg.id,
        "email": reg.email,
        "name": f"{reg.first_name} {reg.last_name}",
        "organization": reg.organization,
        "role": "participant",
        "created_at": datetime.utcnow().isoformat(),
    }

    log.info("Login: %s (%s)", reg.email, reg.organization)
    return LoginResponse(
        token=token,
        name=f"{reg.first_name} {reg.last_name}",
        organization=reg.organization,
        role="participant",
    )


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
