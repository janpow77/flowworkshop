"""Audit-Trail-Middleware für schreibende API-Aktionen (COCK-04).

Jede zustandsverändernde Anfrage (POST, PUT, PATCH, DELETE) erzeugt
automatisch einen Audit-Eintrag mit Zeitstempel, Akteur, Tailscale-
Geräte-ID, HTTP-Methode, Pfad, Statuscode, Response-Latenz.

Das Schreib-Backend (`AuditWriter`) ist abstrahiert; die App stellt
eine konkrete Implementierung bereit, die in ihre Datenbank schreibt
(z.B. SQLAlchemy oder raw-SQL gegen `audit_log`).

Verwendung:

    from cockpit_common.audit import AuditTrailMiddleware, AuditWriter

    class MyWriter(AuditWriter):
        async def write(self, entry): ...   # in DB persistieren

    app.add_middleware(AuditTrailMiddleware, writer=MyWriter())
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging_setup import (
    current_actor,
    current_actor_device,
    current_request_id,
)

log = logging.getLogger(__name__)

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class AuditEntry:
    """Ein einzelner Eintrag im Audit-Trail."""

    ts: datetime
    request_id: str
    actor_identity: str
    actor_device: str | None
    method: str
    path: str
    query_string: str
    status_code: int
    duration_ms: float
    environment: str
    extra: dict[str, Any] = field(default_factory=dict)


class AuditWriter(ABC):
    """Persistenz-Strategie für Audit-Einträge."""

    @abstractmethod
    async def write(self, entry: AuditEntry) -> None:
        """Schreibt einen Eintrag. Darf nicht blockieren — failure ist
        nicht-kritisch und wird nur geloggt."""


class NullAuditWriter(AuditWriter):
    """Default-Writer: schreibt nur ins Log."""

    async def write(self, entry: AuditEntry) -> None:
        log.info(
            "audit",
            extra={
                "audit_method": entry.method,
                "audit_path": entry.path,
                "audit_status": entry.status_code,
                "audit_duration_ms": entry.duration_ms,
            },
        )


class AuditTrailMiddleware(BaseHTTPMiddleware):
    """Schreibt für jede Schreib-Anfrage einen Audit-Eintrag.

    Lese-Anfragen (GET, HEAD, OPTIONS) erzeugen keine Audit-Einträge,
    weil sie keinen Zustand ändern und ihre Menge die Tabelle aufblähen
    würde. Zugriffs-Statistik liefert die Domäne 4 (Traffic Control).
    """

    def __init__(
        self,
        app,
        writer: AuditWriter | None = None,
        ignore_paths: tuple[str, ...] = ("/health", "/metrics"),
        environment: str = "development",
    ) -> None:
        super().__init__(app)
        self._writer = writer or NullAuditWriter()
        self._ignore_paths = ignore_paths
        self._environment = environment

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        if request.method not in WRITE_METHODS:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in self._ignore_paths):
            return await call_next(request)

        t0 = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - t0) * 1000

        entry = AuditEntry(
            ts=datetime.now(timezone.utc),
            request_id=current_request_id() or "-",
            actor_identity=current_actor() or "anonymous",
            actor_device=current_actor_device(),
            method=request.method,
            path=request.url.path,
            query_string=request.url.query,
            status_code=response.status_code,
            duration_ms=duration_ms,
            environment=self._environment,
        )
        try:
            await self._writer.write(entry)
        except Exception:  # noqa: BLE001
            log.exception("Audit-Eintrag konnte nicht persistiert werden")

        return response
