"""Health- und System-Endpunkt-Tests."""


def test_livez_is_fast_and_dependency_free(client):
    r = client.get("/livez")
    assert r.status_code == 200
    assert r.json() == {
        "status": "alive",
        "service": "auditworkshop-backend",
    }


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    # Der Endpunkt liefert "ready" (alle Checks ok) oder "degraded" (eine
    # weiche Abhängigkeit wie der zentrale llm_router ist transient nicht
    # erreichbar) — beides ist betriebsbereit.
    assert data["status"] in ("ready", "degraded")
    assert data["service"] == "auditworkshop-backend"
    # Die kritische Abhängigkeit (Datenbank) muss bereit sein.
    assert data["checks"]["database"]["status"] == "ready"


def test_ollama_status(client):
    r = client.get("/api/system/ollama")
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "models" in data


def test_system_info(client):
    r = client.get("/api/system/info")
    assert r.status_code == 200
    data = r.json()
    assert "cpu" in data
    assert "host_ram" in data


def test_system_profile(client):
    r = client.get("/api/system/profile")
    assert r.status_code == 200
    data = r.json()
    assert "model_name" in data
    assert "privacy_mode" in data
