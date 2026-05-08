"""
flowworkshop · services/access_log_middleware.py
ASGI-Middleware: schreibt pro /api/*-Request einen Eintrag in
``workshop_access_log``.

Design-Ziele:
- Datenschutz: kein Klartext-IP, kein Body, keine Token-Werte in Query.
- Performance: Insert in Background-Thread (run_in_executor) — der Hot-Path
  der Response-Auslieferung wird nicht blockiert.
- Robustheit: jede Exception im Logging wird verschluckt, sodass die
  eigentliche Response NIE durch Logging-Fehler beeintraechtigt wird.
- Best-effort User-Erkennung: nutzt ``request.state.user_id``/``role`` falls
  vorhanden (z.B. nachdem ``require_session`` lief), sonst Pass-Through-
  Helfer ``_resolve_session_optional``.

Filter-Regeln (NICHT loggen):
- Pfade ausserhalb von ``/api/*``
- ``/health``, ``/openapi.json``, ``/docs``, ``/redoc``
- Statische Assets (``/static/*``, ``/assets/*``, ``/favicon.ico``)
- Health-Probes mit User-Agent ``kube-probe`` oder ``docker-healthcheck``
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger(__name__)


# ── Konfiguration ────────────────────────────────────────────────────────────

WORKSHOP_IP_SALT = os.environ.get("WORKSHOP_IP_SALT", "flowworkshop-2026")

# Sensible Query-Parameter (case-insensitive). Wert wird durch ``***`` ersetzt.
SENSITIVE_QUERY_KEYS = {
    "password", "passwd", "pwd", "token", "api_key", "apikey",
    "secret", "auth", "authorization", "qr", "pin",
}

# Pfade, die NIE geloggt werden (exakter Match oder Prefix)
NEVER_LOG_EXACT = {"/health", "/openapi.json", "/docs", "/redoc", "/favicon.ico"}
NEVER_LOG_PREFIX = ("/static/", "/assets/", "/docs/", "/redoc/")

# User-Agent-Snippets, bei denen wir nicht loggen
HEALTHCHECK_UA_MARKERS = ("kube-probe", "docker-healthcheck")


# ── Helper ────────────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str | None:
    """Liest die Client-IP. Bevorzugt X-Forwarded-For (erstes Element)
    wenn das Backend hinter einem Reverse-Proxy steht.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client:
        return request.client.host
    return None


def _hash_ip(ip: str | None) -> str | None:
    """SHA256(IP + Salt) — Hex 64 Zeichen. None bei leerem Input."""
    if not ip:
        return None
    digest = hashlib.sha256(f"{ip}|{WORKSHOP_IP_SALT}".encode("utf-8")).hexdigest()
    return digest


_BROWSER_PATTERNS = [
    ("Bot", re.compile(r"bot|crawler|spider|preview", re.IGNORECASE)),
    ("Edge", re.compile(r"\bEdg/", re.IGNORECASE)),
    ("Chrome", re.compile(r"\bChrome/")),
    ("Safari", re.compile(r"\bSafari/")),
    ("Firefox", re.compile(r"\bFirefox/")),
    ("curl", re.compile(r"^curl/", re.IGNORECASE)),
    ("python", re.compile(r"^python|httpx|requests|aiohttp", re.IGNORECASE)),
]


def _short_user_agent(ua: str | None) -> str | None:
    """Erste 80 Zeichen + Browser-Kategorie als Praefix.
    Beispiel: "[Chrome] Mozilla/5.0 (X11; Linux x86_64) AppleWebKit..."
    """
    if not ua:
        return None
    label = "Other"
    for name, pat in _BROWSER_PATTERNS:
        if pat.search(ua):
            label = name
            break
    short = ua.strip().replace("\n", " ").replace("\r", " ")
    # 80 Zeichen brutto inkl. Praefix
    payload = f"[{label}] {short}"
    return payload[:80]


def _sanitize_query_string(query: str) -> str:
    """Sensible Parameter werden auf ``***`` gesetzt. Andere bleiben unveraendert.
    Liefert einen URL-encodeten String (gleiche Reihenfolge wie Original).
    """
    if not query:
        return ""
    try:
        pairs = parse_qsl(query, keep_blank_values=True)
    except Exception:
        return query[:500]
    sanitized: list[tuple[str, str]] = []
    for key, value in pairs:
        if key.lower() in SENSITIVE_QUERY_KEYS and value:
            sanitized.append((key, "***"))
        else:
            sanitized.append((key, value))
    # quote_via mit zusaetzlichem safe-Char ``*`` laesst den Marker ``***``
    # als Klartext im Log stehen — sonst waere er als ``%2A%2A%2A`` codiert.
    def _quote(s: str, safe: str = "", encoding=None, errors=None) -> str:
        return quote_plus(s, safe=safe + "*", encoding=encoding, errors=errors)

    encoded = urlencode(sanitized, doseq=True, quote_via=_quote)
    return encoded[:500]


def _path_template(request: Request) -> str | None:
    """FastAPI-Route-Template (z.B. ``/api/state-aid/award/{id}``).
    Liefert ``None``, falls kein Match (z.B. 404 vor Routing).
    """
    route = request.scope.get("route")
    if route is None:
        return None
    # Starlette Route hat ``path``, FastAPI APIRoute hat ``path`` und ``path_format``.
    path = getattr(route, "path", None) or getattr(route, "path_format", None)
    return path


def _referer_path(request: Request) -> str | None:
    """Nur den Pfad-Teil eines Referer extrahieren — keine Query-Strings."""
    ref = request.headers.get("referer")
    if not ref:
        return None
    try:
        parsed = urlparse(ref)
        path = parsed.path or "/"
        return path[:255]
    except Exception:
        return None


def _should_skip(path: str, ua: str | None) -> bool:
    """True, wenn dieser Request NICHT geloggt werden soll."""
    if not path.startswith("/api/"):
        return True
    if path in NEVER_LOG_EXACT:
        return True
    for prefix in NEVER_LOG_PREFIX:
        if path.startswith(prefix):
            return True
    if ua:
        ua_lower = ua.lower()
        for marker in HEALTHCHECK_UA_MARKERS:
            if marker in ua_lower:
                return True
    return False


def _resolve_user_from_request(request: Request) -> tuple[str | None, str]:
    """Liest user_id + role. Reihenfolge:
    1) ``request.state.user_id`` / ``request.state.role`` (falls Auth-Dependency lief)
    2) ``_resolve_session_optional`` (Pass-Through ohne 401)
    Liefert (user_id|None, role-string). Default-Rolle: ``"anon"``.
    """
    user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)
    if user_id:
        return user_id, role or "anon"
    try:
        from routers.auth import _resolve_session_optional  # lazy import
        session = _resolve_session_optional(request)
    except Exception:  # noqa: BLE001
        session = None
    if not session:
        return None, "anon"
    return session.get("user_id"), (session.get("role") or "anon")


# ── DB-Insert (Background) ───────────────────────────────────────────────────


def _persist_access_log(payload: dict) -> None:
    """Synchroner DB-Insert in einer eigenen Session. Soll NICHT vom
    Request-Hot-Path aufgerufen werden — stattdessen via
    ``run_in_executor``/``asyncio.create_task``.
    """
    try:
        # Lazy-Import: vermeidet Zyklen beim Modul-Load
        from database import SessionLocal
        from models.access_log import AccessLog
    except Exception:
        log.exception("AccessLog-Import fehlgeschlagen")
        return

    db = SessionLocal()
    try:
        db.add(AccessLog(**payload))
        db.commit()
    except Exception:
        # Logging-Fehler darf die App nicht beeintraechtigen
        log.exception("AccessLog-Insert fehlgeschlagen")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass


# ── Middleware ────────────────────────────────────────────────────────────────


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Middleware, die /api/*-Requests in ``workshop_access_log`` ablegt."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        ua = request.headers.get("user-agent")

        # Frueh-Filter: keine Arbeit, wenn wir nicht loggen
        if _should_skip(path, ua):
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        response_size: int | None = None
        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            # Content-Length auswerten, falls vorhanden
            try:
                cl = response.headers.get("content-length")
                if cl is not None:
                    response_size = int(cl)
            except Exception:  # noqa: BLE001
                response_size = None
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            try:
                user_id, role = _resolve_user_from_request(request)
            except Exception:  # noqa: BLE001
                user_id, role = None, "anon"

            payload = {
                # tz-naive UTC fuer Spalten vom Typ DateTime ohne TZ.
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                "method": request.method[:8],
                "path": path[:255],
                "path_template": (_path_template(request) or path)[:255],
                "query_string": _sanitize_query_string(request.url.query),
                "status_code": int(status_code),
                "duration_ms": duration_ms,
                "user_id": user_id,
                "role": role[:16] if role else "anon",
                "ip_hash": _hash_ip(_client_ip(request)),
                "ua_short": _short_user_agent(ua),
                "referer_path": _referer_path(request),
                "response_size": response_size,
            }

            # Background-Insert: vermeidet Blocking im Hot-Path.
            # ``asyncio.get_running_loop().run_in_executor`` haengt sich nicht
            # an die Response — d.h. der Client erhaelt die Antwort sofort,
            # der Insert laeuft im Default-ThreadPool.
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _persist_access_log, payload)
            except RuntimeError:
                # Kein laufender Event-Loop (sehr seltene Edge-Case-Situation):
                # synchron persistieren, damit der Eintrag nicht verloren geht.
                _persist_access_log(payload)
            except Exception:  # noqa: BLE001
                log.exception("AccessLog-Background-Schedule fehlgeschlagen")
