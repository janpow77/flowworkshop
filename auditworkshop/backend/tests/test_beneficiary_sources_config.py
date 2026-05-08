"""
Phase 6b — Tests fuer die datengetriebenen Beneficiary-Source-Configs.

Schwerpunkte:
  - CRUD-Endpoints (auth-gated): list, get, create, update, delete (soft).
  - Test-Run gegen ein In-Memory-XLSX (kein DB-Write).
  - Manueller Harvest-Trigger.
  - Run-History.
  - Pydantic-Validation (Slug-Pattern, source_url Pflicht bei xlsx_url).

Wir reden gegen die laufende Backend-Instanz (TEST_BASE_URL, Default
http://localhost:8006). Beim Login als TEST_LOGIN_EMAIL muss der User
Admin sein — sonst werden die Tests geskippt.

Lauf: pytest backend/tests/test_beneficiary_sources_config.py -q
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import httpx
import pytest

# Backend-Verzeichnis in den Pfad legen, damit `models.*` importierbar ist.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Test-Source-Key — wird in jedem Test neu angelegt + am Ende geloescht.
TEST_SOURCE_KEY = "phase6b_test_source"


def _auth_is_admin(client: httpx.Client) -> bool:
    """True, wenn der Login-User die Admin-Rolle hat."""
    r = client.get("/api/auth/me")
    if r.status_code != 200:
        return False
    return (r.json() or {}).get("role") == "admin"


def _cleanup_via_api(client: httpx.Client, source_key: str) -> None:
    """Best-effort Cleanup. Soft-Disable reicht — Test-Source-Key ist
    eindeutig und kollidiert nicht mit Produktion."""
    try:
        client.delete(f"/api/admin/beneficiary-sources/{source_key}")
    except Exception:  # noqa: BLE001
        pass


def _cleanup_via_db(source_key: str) -> None:
    """Hartes Cleanup direkt in der DB — entfernt die Test-Config und
    eventuell zugehoerige Runs/Records, damit der naechste Lauf sauber
    startet.

    Versucht zuerst SQLAlchemy (klappt nur, wenn psycopg2 + DB-Zugriff da
    sind — sprich: aus dem Container heraus). Fallback: docker exec mit
    psql, falls die Tests vom Host laufen und kein lokales psycopg2 da ist.
    """
    try:
        from database import SessionLocal
        from models.beneficiary_records import (
            BeneficiaryHarvestRun, BeneficiaryRecord,
        )
        from models.beneficiary_sources_config import BeneficiarySourceConfig

        db = SessionLocal()
        try:
            db.query(BeneficiaryRecord).filter(
                BeneficiaryRecord.source_key == source_key
            ).delete(synchronize_session=False)
            db.query(BeneficiaryHarvestRun).filter(
                BeneficiaryHarvestRun.source_key == source_key
            ).delete(synchronize_session=False)
            db.query(BeneficiarySourceConfig).filter(
                BeneficiarySourceConfig.source_key == source_key
            ).delete(synchronize_session=False)
            db.commit()
            return
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass

    # Fallback: docker exec psql. Best-effort, schluckt jeden Fehler.
    try:
        import subprocess
        subprocess.run(
            [
                "docker", "exec", "auditworkshop-db",
                "psql", "-U", "workshop", "-d", "workshop", "-c",
                f"DELETE FROM workshop_beneficiary_records WHERE source_key='{source_key}'; "
                f"DELETE FROM workshop_beneficiary_harvest_runs WHERE source_key='{source_key}'; "
                f"DELETE FROM workshop_beneficiary_sources_config WHERE source_key='{source_key}';"
            ],
            capture_output=True, timeout=15,
        )
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def admin_client(client: httpx.Client):
    """Stellt sicher, dass der Test-User Admin ist — sonst skip."""
    if not _auth_is_admin(client):
        pytest.skip("Test-User ist kein Admin — CRUD-Tests werden uebersprungen.")
    yield client


@pytest.fixture(autouse=True)
def _isolate_test_source(client: httpx.Client):
    """Vor + nach jedem Test die Test-Source aufraeumen.

    Versucht zuerst DB-direkt (klappt nur, wenn der Test-Runner Zugriff auf
    die DB hat — z.B. innerhalb des Containers). Faellt zurueck auf einen
    harten DELETE ueber die API plus PUT enabled=false. Wenn die Source
    nicht existiert, ist DELETE ein 404 — kein Problem.

    Vor dem Test: garantiert, dass der Source-Key nicht aus einem fruheren
    Lauf rumliegt. Nach dem Test: kein Muell in der Tabelle.
    """
    def _hard_cleanup():
        _cleanup_via_db(TEST_SOURCE_KEY)
        # API-Soft-Disable als Fallback — wenn DB-Cleanup nichts macht
        # (Host ohne psycopg2), bleibt der Datensatz, ist aber disabled.
        # Damit der naechste Test ihn neu anlegen kann, brauchen wir aber
        # einen Hard-Delete: das macht der Direct-DB-Cleanup. Wenn der nicht
        # geht, skippen wir die Tests.
        # Workaround: PUT auf source_type-Werte, damit Konflikt-Tests wie
        # "create xlsx_url ohne url" trotzdem klappen.
        try:
            client.delete(f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}")
        except Exception:  # noqa: BLE001
            pass

    _hard_cleanup()
    yield
    _hard_cleanup()


def _create_payload(**overrides) -> dict:
    base = {
        "source_key": TEST_SOURCE_KEY,
        "display_name": "Phase 6b Testquelle",
        "bundesland": "Hessen",
        "fonds": "EFRE",
        "periode": "2021-2027",
        "country_code": "DE",
        "source_type": "manual_upload",
        "header_row": 0,
        "enabled": True,
    }
    base.update(overrides)
    return base


# ── CRUD ──────────────────────────────────────────────────────────────────────


def test_list_sources_returns_count(admin_client: httpx.Client):
    """GET /api/admin/beneficiary-sources — liefert {count, sources}."""
    r = admin_client.get("/api/admin/beneficiary-sources")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "count" in data
    assert "sources" in data
    assert isinstance(data["sources"], list)


def test_create_source_validates_slug(admin_client: httpx.Client):
    """source_key mit Sonderzeichen wird abgelehnt (422)."""
    payload = _create_payload(source_key="MIT GROSSBUCHSTABEN")
    r = admin_client.post("/api/admin/beneficiary-sources", json=payload)
    assert r.status_code == 422


def test_create_source_xlsx_url_requires_url(admin_client: httpx.Client):
    """source_type=xlsx_url ohne source_url -> 422."""
    payload = _create_payload(source_type="xlsx_url")
    r = admin_client.post("/api/admin/beneficiary-sources", json=payload)
    assert r.status_code == 422


def test_create_get_update_delete_roundtrip(admin_client: httpx.Client):
    """Vollstaendiger CRUD-Roundtrip mit dem TEST_SOURCE_KEY."""
    # 1. Create
    payload = _create_payload()
    r = admin_client.post("/api/admin/beneficiary-sources", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["source_key"] == TEST_SOURCE_KEY
    assert created["enabled"] is True

    # 2. Duplicate -> 409
    r = admin_client.post("/api/admin/beneficiary-sources", json=payload)
    assert r.status_code == 409

    # 3. Get
    r = admin_client.get(f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}")
    assert r.status_code == 200
    assert r.json()["display_name"] == "Phase 6b Testquelle"

    # 4. Update — Field-Mapping setzen
    update = {
        "display_name": "Phase 6b Testquelle (aktualisiert)",
        "field_mapping": {"name": "Beguenstigter"},
        "required_fields": ["beneficiary_name"],
    }
    r = admin_client.put(
        f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}", json=update,
    )
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["display_name"] == "Phase 6b Testquelle (aktualisiert)"
    assert after["field_mapping"] == {"name": "Beguenstigter"}
    assert after["required_fields"] == ["beneficiary_name"]

    # 5. Soft-Delete -> enabled=false
    r = admin_client.delete(f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}")
    assert r.status_code == 200
    r = admin_client.get(f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_get_nonexistent_source_returns_404(admin_client: httpx.Client):
    r = admin_client.get("/api/admin/beneficiary-sources/does_not_exist_xyz")
    assert r.status_code == 404


# ── Test-Run ──────────────────────────────────────────────────────────────────


def _build_minimal_xlsx() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Name des Beguenstigten",
        "Bezeichnung des Vorhabens",
        "Gesamtkosten des Vorhabens",
    ])
    ws.append(["Test GmbH", "Workshop", "10000"])
    ws.append(["Acme KG", "Demoprojekt", "25000"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_test_run_with_uploaded_file(admin_client: httpx.Client):
    """Test-Run liefert Vorschau + erkannte Felder, OHNE in DB zu schreiben."""
    # Setup: Config anlegen.
    admin_client.post(
        "/api/admin/beneficiary-sources", json=_create_payload(),
    )

    xlsx_bytes = _build_minimal_xlsx()
    r = admin_client.post(
        f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}/test-run",
        files={"file": ("test.xlsx", xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["fetch_source"] == "upload"
    assert data["preview_rows_returned"] >= 1
    assert "name" in data["detected_field_mapping"]


def test_test_run_without_file_and_no_url_returns_422(admin_client: httpx.Client):
    """source_type=manual_upload + kein File hochgeladen -> 422."""
    admin_client.post(
        "/api/admin/beneficiary-sources", json=_create_payload(),
    )
    r = admin_client.post(
        f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}/test-run",
    )
    assert r.status_code == 422


# ── Manueller Harvest ────────────────────────────────────────────────────────


def test_manual_harvest_writes_to_db(admin_client: httpx.Client):
    """Manueller Harvest mit Upload schreibt in workshop_beneficiary_records."""
    admin_client.post(
        "/api/admin/beneficiary-sources",
        json=_create_payload(),
    )

    xlsx_bytes = _build_minimal_xlsx()
    r = admin_client.post(
        f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}/harvest",
        files={"file": ("data.xlsx", xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"mode": "smart"},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["status"] in ("ok", "partial")
    assert result["records_inserted"] >= 1

    # Config muss record_count + last_successful_harvest_at haben.
    r2 = admin_client.get(f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}")
    assert r2.status_code == 200
    cfg = r2.json()
    assert cfg["record_count"] >= 1
    assert cfg["last_successful_harvest_at"] is not None
    assert cfg["last_harvest_run_id"] is not None


def test_manual_harvest_invalid_mode_returns_422(admin_client: httpx.Client):
    admin_client.post(
        "/api/admin/beneficiary-sources",
        json=_create_payload(),
    )
    r = admin_client.post(
        f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}/harvest",
        files={"file": ("data.xlsx", b"x",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"mode": "irrelevant"},
    )
    assert r.status_code == 422


# ── Run-History ───────────────────────────────────────────────────────────────


def test_run_history_returns_list(admin_client: httpx.Client):
    """Nach einem Harvest hat /runs mindestens einen Eintrag."""
    admin_client.post(
        "/api/admin/beneficiary-sources", json=_create_payload(),
    )
    xlsx_bytes = _build_minimal_xlsx()
    admin_client.post(
        f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}/harvest",
        files={"file": ("data.xlsx", xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    r = admin_client.get(f"/api/admin/beneficiary-sources/{TEST_SOURCE_KEY}/runs")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    assert data["runs"][0]["source_key"] == TEST_SOURCE_KEY
    assert data["runs"][0]["status"] in ("ok", "partial", "failed", "running", "check_only")


# ── Auth ──────────────────────────────────────────────────────────────────────


def test_unauthed_returns_401(unauthed_client: httpx.Client):
    """Ohne Token -> 401."""
    r = unauthed_client.get("/api/admin/beneficiary-sources")
    assert r.status_code == 401
