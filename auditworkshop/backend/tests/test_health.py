"""Health- und System-Endpunkt-Tests."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "flowworkshop"


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
