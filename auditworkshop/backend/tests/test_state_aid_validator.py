"""
Tests fuer den State-Aid-Validator (services.state_aid_validator).

Lauft als Integration-Test gegen das laufende Backend (Port 8006).
"""
import pytest
import httpx


def test_validation_last_endpoint(unauthed_client: httpx.Client):
    """Oeffentlicher Endpoint /validation/last antwortet 200 + Schema."""
    res = unauthed_client.get("/api/state-aid/validation/last")
    assert res.status_code == 200
    body = res.json()
    assert "module" in body
    assert "report" in body
    # Report kann None sein (wenn noch nie ausgefuehrt) oder Dict.
    if body["report"] is not None:
        rep = body["report"]
        assert rep["status"] in {"ok", "warnings", "failed"}
        assert isinstance(rep["checks_total"], int)
        assert isinstance(rep["findings"], list)


def test_validation_run_admin_only(unauthed_client: httpx.Client):
    """POST /validation/run ohne Token muss 401/403."""
    res = unauthed_client.post("/api/state-aid/validation/run")
    assert res.status_code in (401, 403)


def test_validation_run_with_admin(client: httpx.Client):
    """Admin kann /validation/run triggern und bekommt einen Report zurueck."""
    res = client.post("/api/state-aid/validation/run")
    if res.status_code == 403:
        pytest.skip("Test-User ist nicht admin — dieser Test braucht admin-role.")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "report" in body
    rep = body["report"]
    assert rep["status"] in {"ok", "warnings", "failed"}
    # Wir haben 9 Checks definiert, alle sollten gelaufen sein.
    assert rep["checks_total"] == 9
    assert rep["checks_passed"] + rep["checks_warned"] + rep["checks_failed"] == 9
    # Findings ist immer eine Liste, auch bei status=ok (ggf. leer).
    assert isinstance(rep["findings"], list)


def test_status_includes_validation_fields(unauthed_client: httpx.Client):
    """GET /status enthaelt last_validation_at/status/findings_count."""
    res = unauthed_client.get("/api/state-aid/status")
    assert res.status_code == 200
    body = res.json()
    assert "last_validation_at" in body
    assert "last_validation_status" in body
    assert "last_validation_findings_count" in body
    # Wenn ein Report existiert: Felder sind konsistent gefuellt.
    if body["last_validation_at"] is not None:
        assert body["last_validation_status"] in {"ok", "warnings", "failed"}
        assert isinstance(body["last_validation_findings_count"], int)


def test_smoke_queries_constants():
    """Sicherheitsnetz: SMOKE_QUERIES sind die 5 vereinbarten Namen."""
    # Nur lokal (im Container) importierbar; Skip wenn psycopg2 fehlt
    try:
        from services.state_aid_validator import SMOKE_QUERIES
    except ModuleNotFoundError:
        pytest.skip("Backend-Imports nicht verfuegbar in dieser Umgebung.")
    assert set(SMOKE_QUERIES) == {"Siemens", "Trumpf", "Volkswagen", "Fraunhofer", "Bosch"}


def test_nuts_regex_matches_known_codes():
    """Sicherheitsnetz: Bekannte gueltige Codes matchen, ungueltige nicht."""
    try:
        from services.state_aid_validator import NUTS_REGEX
    except ModuleNotFoundError:
        pytest.skip("Backend-Imports nicht verfuegbar.")
    for ok in ["DE", "DE2", "DE21", "DE212", "AT", "AT11", "FRH"]:
        assert NUTS_REGEX.match(ok), f"{ok!r} sollte matchen"
    for bad in ["de2", "DE2123", "1DE", "D-2", " DE2", ""]:
        assert not NUTS_REGEX.match(bad), f"{bad!r} sollte NICHT matchen"
