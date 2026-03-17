"""
Test-Konfiguration fuer FlowWorkshop Backend.
Nutzt die laufende Anwendung (Integration-Tests gegen localhost:8006).
"""
import os
import pytest
import httpx

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8006")
ADMIN_PIN = os.environ.get("TEST_ADMIN_PIN", "1234")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def admin_pin():
    return ADMIN_PIN


@pytest.fixture(scope="session")
def client():
    """Synchroner httpx-Client fuer die Test-Session."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c
