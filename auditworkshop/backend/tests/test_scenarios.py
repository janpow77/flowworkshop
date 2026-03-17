"""Szenario-Endpunkt-Tests (Workshop-Router)."""


def test_supported_formats(client):
    r = client.get("/api/workshop/supported-formats")
    assert r.status_code == 200
    data = r.json()
    # Kann Liste oder Wrapper sein
    formats = data if isinstance(data, list) else data.get("extensions", data.get("formats", []))
    assert ".pdf" in formats
    assert ".xlsx" in formats
    assert ".docx" in formats


def test_stream_endpoint_requires_body(client):
    """Stream-Endpunkt muss mindestens scenario_id und text haben."""
    r = client.post("/api/workshop/stream", json={})
    assert r.status_code == 422  # Validation Error


def test_beneficiaries_sources(client):
    r = client.get("/api/beneficiaries/sources")
    assert r.status_code == 200
    data = r.json()
    sources = data if isinstance(data, list) else data.get("sources", [])
    assert isinstance(sources, list)


def test_dataframes_list(client):
    r = client.get("/api/dataframes/")
    assert r.status_code == 200
    data = r.json()
    tables = data if isinstance(data, list) else data.get("tables", [])
    assert isinstance(tables, list)


def test_auth_login_invalid(client):
    r = client.post("/api/auth/login", json={"email": ""})
    assert r.status_code in (400, 401, 422)


def test_reference_data_sources(client):
    r = client.get("/api/reference-data/sources")
    assert r.status_code == 200
    data = r.json()
    sources = data if isinstance(data, list) else data.get("sources", [])
    assert isinstance(sources, list)
