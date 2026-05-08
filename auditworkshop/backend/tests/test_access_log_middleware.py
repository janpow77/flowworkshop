"""
Tests fuer die AccessLogMiddleware (Plan: Workshop Access-Logging).

Der Test setzt eine eigene FastAPI-Test-App auf — damit wir vom DB-Insert
unabhaengig sind. ``_persist_access_log`` wird durch eine In-Memory-Liste
ersetzt; alle anderen Pfade (Filter, Sanitisierung, Path-Template-Aufloesung)
laufen vollstaendig durch die Middleware.

Lauf: pytest backend/tests/test_access_log_middleware.py -q
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services import access_log_middleware as alm  # noqa: E402


# ── Helper ────────────────────────────────────────────────────────────────────


def make_test_app(captured: list[dict]):
    """Test-App mit Health- + State-Aid-Status-Routen, ohne DB-Insert."""
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/state-aid/status")
    def state_aid_status():
        return {"total_awards": 42}

    @app.get("/api/state-aid/award/{award_id}")
    def state_aid_award(award_id: str):
        return {"id": award_id}

    @app.get("/api/auth/login")
    def login_query():
        # Demo-Endpoint, um Sanitisierung zu pruefen
        return {"ok": True}

    # Middleware NACH den Routen registrieren — Reihenfolge in
    # Starlette/FastAPI ist egal, sobald die App noch nicht laeuft.
    app.add_middleware(alm.AccessLogMiddleware)

    return app


@pytest.fixture
def captured(monkeypatch):
    """Captured-Liste, die anstelle von ``_persist_access_log`` gefuellt wird."""
    items: list[dict] = []

    def fake_persist(payload: dict) -> None:
        items.append(payload)

    monkeypatch.setattr(alm, "_persist_access_log", fake_persist)
    return items


@pytest.fixture
def client(captured):
    app = make_test_app(captured)
    return TestClient(app)


def _wait_for(captured_list, expected_min: int, timeout: float = 1.0):
    """Da der Insert via ``run_in_executor`` laeuft, muessen wir kurz warten."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(captured_list) >= expected_min:
            return
        time.sleep(0.02)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_health_is_not_logged(client, captured):
    r = client.get("/health")
    assert r.status_code == 200
    _wait_for(captured, expected_min=1, timeout=0.3)
    # Health darf NICHT geloggt sein
    assert all(p["path"] != "/health" for p in captured)


def test_state_aid_status_is_logged(client, captured):
    r = client.get("/api/state-aid/status")
    assert r.status_code == 200
    _wait_for(captured, expected_min=1)
    matches = [p for p in captured if p["path"] == "/api/state-aid/status"]
    assert len(matches) >= 1
    p = matches[-1]
    assert p["method"] == "GET"
    assert p["status_code"] == 200
    assert p["path_template"] == "/api/state-aid/status"
    assert p["duration_ms"] is not None and p["duration_ms"] >= 0
    # role default = "anon", kein User
    assert p["role"] == "anon"
    assert p["user_id"] is None


def test_path_template_uses_route_pattern(client, captured):
    r = client.get("/api/state-aid/award/abc-123")
    assert r.status_code == 200
    _wait_for(captured, expected_min=1)
    matches = [p for p in captured if p["path"] == "/api/state-aid/award/abc-123"]
    assert matches, "Eintrag fuer /api/state-aid/award/abc-123 fehlt"
    p = matches[-1]
    # Path-Template muss den Pfadparameter behalten haben
    assert p["path_template"] == "/api/state-aid/award/{award_id}"


def test_query_string_is_sanitized(client, captured):
    r = client.get("/api/auth/login?password=secret&user=jan&token=abc123")
    assert r.status_code == 200
    _wait_for(captured, expected_min=1)
    matches = [p for p in captured if p["path"] == "/api/auth/login"]
    assert matches
    qs = matches[-1]["query_string"]
    assert "password=***" in qs
    assert "token=***" in qs
    # Nicht-sensible Parameter bleiben unveraendert
    assert "user=jan" in qs
    # Klartext-Werte duerfen NICHT erscheinen
    assert "secret" not in qs
    assert "abc123" not in qs


def test_404_is_logged_with_request_path(client, captured):
    r = client.get("/api/state-aid/does-not-exist")
    assert r.status_code == 404
    _wait_for(captured, expected_min=1)
    matches = [p for p in captured if p["path"] == "/api/state-aid/does-not-exist"]
    assert matches, "404-Pfad fehlt im Log"
    p = matches[-1]
    assert p["status_code"] == 404
    # Bei 404 (kein Route-Match) faellt path_template auf den konkreten Pfad
    # zurueck — d.h. path == path_template.
    assert p["path_template"] == p["path"]


def test_healthcheck_user_agent_is_skipped(client, captured):
    captured.clear()
    r = client.get(
        "/api/state-aid/status",
        headers={"user-agent": "kube-probe/1.27"},
    )
    assert r.status_code == 200
    _wait_for(captured, expected_min=0, timeout=0.2)
    # kube-probe darf NICHT geloggt sein
    assert all(
        p.get("ua_short") is None or "kube-probe" not in (p.get("ua_short") or "")
        for p in captured
    )


def test_ip_hash_is_deterministic_and_not_plain():
    h1 = alm._hash_ip("192.0.2.42")
    h2 = alm._hash_ip("192.0.2.42")
    assert h1 == h2
    assert h1 is not None
    assert len(h1) == 64  # SHA256 hex
    # Klartext-IP darf nicht im Hash auftauchen
    assert "192.0.2.42" not in h1
    assert alm._hash_ip(None) is None
    assert alm._hash_ip("") is None


def test_short_user_agent_categorizes():
    assert (alm._short_user_agent("Mozilla/5.0 (X11) Chrome/120") or "").startswith("[Chrome]")
    assert (alm._short_user_agent("Mozilla/5.0 Firefox/115") or "").startswith("[Firefox]")
    assert (alm._short_user_agent("curl/8.0") or "").startswith("[curl]")
    assert (alm._short_user_agent("Googlebot/2.1") or "").startswith("[Bot]")
    assert alm._short_user_agent(None) is None


def test_should_skip_filters():
    assert alm._should_skip("/health", None) is True
    assert alm._should_skip("/api/health", None) is False
    assert alm._should_skip("/openapi.json", None) is True
    assert alm._should_skip("/static/foo.css", None) is True
    assert alm._should_skip("/api/state-aid/status", None) is False
    assert alm._should_skip("/api/state-aid/status", "docker-healthcheck/1.0") is True
