"""Projekt- und Checklisten-CRUD-Tests."""
import pytest


class TestProjects:
    def test_list_projects(self, client):
        r = client.get("/api/projects/")
        assert r.status_code == 200
        data = r.json()
        # Kann Liste oder Wrapper sein
        projects = data if isinstance(data, list) else data.get("projects", [])
        assert isinstance(projects, list)

    def test_create_and_delete_project(self, client):
        r = client.post("/api/projects/", json={
            "aktenzeichen": "TEST-2026-001",
            "geschaeftsjahr": "2026",
            "program": "EFRE",
            "zuwendungsempfaenger": "Testfirma GmbH",
            "projekttitel": "Test-Vorhaben",
        })
        assert r.status_code == 201
        project = r.json()
        assert project["aktenzeichen"] == "TEST-2026-001"
        project_id = project["id"]

        # Abrufen
        r = client.get(f"/api/projects/{project_id}")
        assert r.status_code == 200
        assert r.json()["id"] == project_id

        # Loeschen
        r = client.delete(f"/api/projects/{project_id}")
        assert r.status_code in (200, 204)

    def test_get_nonexistent_project(self, client):
        r = client.get("/api/projects/nonexistent-id")
        assert r.status_code == 404


class TestDemoData:
    def test_list_templates(self, client):
        r = client.get("/api/demo/templates")
        assert r.status_code == 200
        data = r.json()
        templates = data if isinstance(data, list) else data.get("templates", [])
        assert len(templates) >= 2

    def test_seed_demo(self, client):
        r = client.post("/api/demo/seed")
        assert r.status_code in (200, 201)
        data = r.json()
        assert data["status"] in ("created", "exists")

    def test_demo_documents(self, client):
        r = client.get("/api/documents/demo")
        assert r.status_code == 200
        docs = r.json()
        assert len(docs) >= 5
        names = {d["name"] for d in docs}
        assert "foerderbescheid" in names
        assert "prueffeststellungen" in names
