"""Cockpit-konformes JSON-Logging (APPS_PREPARATION.md §2.5).

Pflichtfelder: ``timestamp``, ``level``, ``service``, ``message``,
``context``, ``request_id``, ``actor_identity``, ``environment``.
Ausgabe auf stdout/stderr.

Verwendung:

    from cockpit_common.logging_setup import (
        configure_logging, RequestContextMiddleware,
    )
    configure_logging(service="auditworkshop-backend", environment="production")
    app.add_middleware(RequestContextMiddleware)

Damit landet jeder Log-Eintrag im einheitlichen Format, das das
Cockpit (Domäne 1, Domäne 4) und Dozzle einheitlich konsumieren können.
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

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_actor_identity_ctx: ContextVar[str | None] = ContextVar("actor_identity", default=None)
_actor_device_ctx: ContextVar[str | None] = ContextVar("actor_device", default=None)


def current_request_id() -> str | None:
    return _request_id_ctx.get()


def current_actor() -> str | None:
    """Tailscale-User-Login der aktuellen Anfrage. None wenn anonym."""
    return _actor_identity_ctx.get()


def current_actor_device() -> str | None:
    return _actor_device_ctx.get()


class _ContextFilter(logging.Filter):
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
    _RESERVED = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
        "service", "environment", "request_id", "actor_identity",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "timestamp":      ts,
            "level":          record.levelname,
            "service":        getattr(record, "service", "unknown"),
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
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload["context"][key] = value
        if record.exc_info:
            payload["context"]["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    *,
    service: str | None = None,
    environment: str | None = None,
    log_format: str | None = None,
    level: str | None = None,
) -> None:
    """Initialisiert das Root-Logger-Handler.

    Argumente überschreiben die korrespondierenden ENV-Werte:
      LOG_FORMAT, LOG_LEVEL,
      WORKSHOP_SERVICE_NAME / COCKPIT_SERVICE_NAME / SERVICE_NAME,
      WORKSHOP_ENVIRONMENT / COCKPIT_ENVIRONMENT / ENVIRONMENT.
    """
    fmt = (log_format or os.getenv("LOG_FORMAT") or "text").strip().lower()
    lvl = (level or os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    svc = (
        service
        or os.getenv("WORKSHOP_SERVICE_NAME")
        or os.getenv("COCKPIT_SERVICE_NAME")
        or os.getenv("SERVICE_NAME")
        or "unknown"
    )
    env = (
        environment
        or os.getenv("WORKSHOP_ENVIRONMENT")
        or os.getenv("COCKPIT_ENVIRONMENT")
        or os.getenv("ENVIRONMENT")
        or "development"
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(levelname)s  %(name)s  %(message)s  "
            "[req=%(request_id)s actor=%(actor_identity)s]"
        ))
    handler.addFilter(_ContextFilter(service=svc, environment=env))

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(lvl)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Pro Request: UUID-Request-ID + Tailscale-Identity in Context-Vars setzen.

    Liest folgende Header (Caddy reicht sie durch):
      X-Request-ID            — übernimmt vorhandene ID, sonst neu erzeugen
      Tailscale-User-Login    — Login-Name des Tailscale-Nutzers
      Tailscale-Device-Name   — Geräte-Name (für Audit-Trail)
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        actor = request.headers.get("Tailscale-User-Login")
        device = request.headers.get("Tailscale-Device-Name")

        rid_token = _request_id_ctx.set(rid)
        actor_token = _actor_identity_ctx.set(actor)
        device_token = _actor_device_ctx.set(device)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(rid_token)
            _actor_identity_ctx.reset(actor_token)
            _actor_device_ctx.reset(device_token)

        response.headers["X-Request-ID"] = rid
        return response
