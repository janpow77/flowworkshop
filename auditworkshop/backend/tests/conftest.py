"""
Test-Konfiguration fuer FlowWorkshop Backend.
Nutzt die laufende Anwendung (Integration-Tests gegen localhost:8006).
"""
import os
import pytest
import httpx

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8006")
ADMIN_PIN = os.environ.get("TEST_ADMIN_PIN", "1234")
TEST_LOGIN_EMAIL = os.environ.get("TEST_LOGIN_EMAIL", "jan.riener@wirtschaft.hessen.de")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def admin_pin():
    return ADMIN_PIN


@pytest.fixture(scope="session")
def auth_token():
    """Holt einmal pro Test-Session ein Workshop-Token via /api/auth/login.

    Vorbedingung: TEST_LOGIN_EMAIL ist registriert (Default: Moderator
    jan.riener@wirtschaft.hessen.de). Schlaegt das Login fehl, werden
    alle Tests, die den `client` brauchen, geskippt.
    """
    response = httpx.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_LOGIN_EMAIL},
        timeout=30.0,
    )
    if response.status_code != 200:
        pytest.skip(
            f"Login fuer {TEST_LOGIN_EMAIL} fehlgeschlagen "
            f"(HTTP {response.status_code}). Bitte Test-User registrieren."
        )
    return response.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def client(auth_headers):
    """Synchroner httpx-Client fuer die Test-Session, automatisch authentifiziert.

    Tests, die explizit ohne Token aufrufen wollen, koennen `unauthed_client`
    verwenden oder den Header pro Request mit `headers={}` ueberschreiben.
    """
    with httpx.Client(base_url=BASE_URL, timeout=30.0, headers=auth_headers) as c:
        yield c


@pytest.fixture(scope="session")
def unauthed_client():
    """Client ohne Auth-Header — fuer 401-Erwartungstests."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c
