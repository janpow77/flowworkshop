"""Cockpit-konformes Logging-Setup für auditworkshop.

Master-Dokument Abschnitt 7 verlangt JSON-Logging mit den Pflichtfeldern
``timestamp``, ``level``, ``service``, ``message``, ``context`` und
``request_id``, ``actor_identity``, ``environment``. Ausgabe auf
stdout/stderr.

Dieses Modul ist bewusst getrennt von ``config.py``, damit Workshop-System-
Prompts unangetastet bleiben. Bei Migration auf das künftige
``cockpit-logging``-Paket (siehe migration-log Beobachtung 6) ist nur dieses
Modul zu ersetzen.

Aktivierung über Umgebungsvariablen:

    LOG_FORMAT = "json" | "text"   (Default: text, rückwärtskompatibel)
    LOG_LEVEL  = "INFO" | …         (Default: INFO)
    WORKSHOP_SERVICE_NAME           (Default: auditworkshop-backend)
    WORKSHOP_ENVIRONMENT            (Default: development)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Pro Request gesetzte Kontextvariablen, vom Formatter eingelesen.
_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_actor_identity_ctx: ContextVar[str | None] = ContextVar("actor_identity", default=None)


class _ContextFilter(logging.Filter):
    """Hängt Request-ID und Tailscale-Identity an jeden LogRecord."""

    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        record.environment = self._environment
        record.request_id = _request_id_ctx.get() or "-"
        record.actor_identity = _actor_identity_ctx.get() or "anonymous"
        return True


class _JsonFormatter(logging.Formatter):
    """Formatter mit den vom Master-Dokument geforderten Pflichtfeldern."""

    _RESERVED = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
        # eigene Felder
        "service", "environment", "request_id", "actor_identity",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "timestamp":      ts,
            "level":          record.levelname,
            "service":        getattr(record, "service", "auditworkshop-backend"),
            "message":        record.getMessage(),
            "context": {
                "logger":    record.name,
                "module":    record.module,
                "function":  record.funcName,
                "line":      record.lineno,
            },
            "request_id":     getattr(record, "request_id", "-"),
            "actor_identity": getattr(record, "actor_identity", "anonymous"),
            "environment":    getattr(record, "environment", "development"),
        }
        # Beliebige zusätzliche Felder (per `extra={}` an logger übergeben)
        # in den context aufnehmen, damit sie nicht verloren gehen.
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload["context"][key] = value
        if record.exc_info:
            payload["context"]["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Initialisiert das Root-Logger-Handler und ersetzt vorherige Setup-Aufrufe."""
    fmt = (os.getenv("LOG_FORMAT") or "text").strip().lower()
    level = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    service = os.getenv("WORKSHOP_SERVICE_NAME") or "auditworkshop-backend"
    environment = os.getenv("WORKSHOP_ENVIRONMENT") or "development"

    handler = logging.StreamHandler(stream=sys.stdout)
    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(levelname)s  %(name)s  %(message)s  "
            "[req=%(request_id)s actor=%(actor_identity)s]"
        ))
    handler.addFilter(_ContextFilter(service=service, environment=environment))

    root = logging.getLogger()
    # Alle früheren Handler entfernen, damit basicConfig-Aufrufe an anderer
    # Stelle uns nicht duplizieren.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Pro Request eine Request-ID erzeugen und Tailscale-Identity übernehmen.

    Tailscale-Identity wird aus dem ``Tailscale-User-Login``-Header gelesen,
    den Caddy auf CCX23 durchreicht. Ohne Header bleibt ``actor_identity``
    auf ``anonymous``.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        actor = request.headers.get("Tailscale-User-Login")

        rid_token = _request_id_ctx.set(rid)
        actor_token = _actor_identity_ctx.set(actor)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(rid_token)
            _actor_identity_ctx.reset(actor_token)

        response.headers["X-Request-ID"] = rid
        return response
