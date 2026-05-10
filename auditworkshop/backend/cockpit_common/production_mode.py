"""Production-Mode-Toggle (COCK-03, PLAN.md §7.4).

Production-Aktionen sind nur möglich, wenn der Production-Mode für die
laufende Sitzung explizit aktiviert ist; Aktivierung verlangt Tailscale-
Identität, Geräte-Identität und einen Bestätigungs-Schritt. Ein direkter
API-Aufruf einer Production-Aktion ohne aktivierten Production-Mode
liefert 403.

Das Cockpit verwaltet den Toggle als kurzlebiges Session-Token in
einer In-Memory-Map (`ProductionMode`). Sessions verfallen nach
konfigurierbarer Zeit (Default: 30 Minuten).

Verwendung in Endpoints:

    from cockpit_common.production_mode import (
        ProductionMode, require_production_mode,
    )

    production_mode = ProductionMode()

    @router.post("/some-prod-action")
    def do_it(_=Depends(require_production_mode(production_mode))):
        ...

    @router.post("/internal/production-mode/enable")
    def enable_pm(body: EnableRequest):
        return production_mode.activate(actor=..., device=..., reason=...)
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Header, HTTPException, status

from .logging_setup import current_actor, current_actor_device


@dataclass
class ProductionSession:
    token: str
    actor_identity: str
    actor_device: str | None
    reason: str
    activated_at: datetime
    expires_at: datetime


@dataclass
class ProductionMode:
    """Verwaltung der aktiven Production-Sessions.

    Threadsafe, weil FastAPI single-threaded mit asyncio läuft.
    Bei Multi-Worker-Deploy (uvicorn --workers > 1) Sessions in
    Redis o.ä. auslagern; aktuell genügt In-Memory.
    """

    session_lifetime: timedelta = field(default_factory=lambda: timedelta(minutes=30))
    _sessions: dict[str, ProductionSession] = field(default_factory=dict)

    def activate(
        self,
        actor: str,
        device: str | None,
        reason: str,
    ) -> ProductionSession:
        """Erzeugt eine neue Production-Session.

        Aufrufer ist verantwortlich, vorher Tailscale-Identity
        zu prüfen und einen UI-Bestätigungs-Schritt zu erzwingen
        (das Frontend zeigt einen Modal-Dialog, der vom Nutzer eine
        bewusste Bestätigung verlangt; erst danach wird dieser
        Endpoint aufgerufen).
        """
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        sess = ProductionSession(
            token=token,
            actor_identity=actor,
            actor_device=device,
            reason=reason,
            activated_at=now,
            expires_at=now + self.session_lifetime,
        )
        self._sessions[token] = sess
        self._gc()
        return sess

    def deactivate(self, token: str) -> None:
        self._sessions.pop(token, None)

    def is_active(self, token: str | None) -> bool:
        if not token:
            return False
        sess = self._sessions.get(token)
        if not sess:
            return False
        if sess.expires_at < datetime.now(timezone.utc):
            self._sessions.pop(token, None)
            return False
        return True

    def get(self, token: str | None) -> ProductionSession | None:
        if not token or not self.is_active(token):
            return None
        return self._sessions.get(token)

    def _gc(self) -> None:
        now = datetime.now(timezone.utc)
        for token, sess in list(self._sessions.items()):
            if sess.expires_at < now:
                self._sessions.pop(token, None)


def require_production_mode(
    production_mode: ProductionMode,
) -> Callable:
    """FastAPI-Dependency: lehnt Anfragen ohne aktive Production-Session ab.

    Erwartet den Token im Header ``X-Cockpit-Production-Token``.
    """

    def dependency(
        x_cockpit_production_token: str | None = Header(default=None),
    ) -> ProductionSession:
        actor = current_actor()
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tailscale-Identität fehlt",
            )
        sess = production_mode.get(x_cockpit_production_token)
        if not sess:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Production-Mode nicht aktiv. "
                       "Vor dieser Aktion 'POST /api/v1/production-mode/activate' aufrufen.",
            )
        # Sicherheits-Check: derselbe Akteur muss den Modus aktiviert haben.
        if sess.actor_identity != actor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Production-Mode wurde von anderer Identität aktiviert.",
            )
        device = current_actor_device()
        if sess.actor_device and device and sess.actor_device != device:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Production-Mode wurde auf anderem Gerät aktiviert.",
            )
        return sess

    return dependency
