"""Event-Router Tests: Agenda, Registrierung, Einladungslinks, Themenboard."""
import pytest


class TestMeta:
    def test_get_meta(self, client):
        r = client.get("/api/event/meta")
        assert r.status_code == 200
        data = r.json()
        assert "title" in data
        assert "date" in data
        assert "location_short" in data
        assert data["location_short"] == "Hannover"

    def test_update_meta_requires_pin(self, client):
        r = client.put("/api/event/admin/meta", params={"pin": "wrong"}, json={"title": "x"})
        assert r.status_code == 403

    def test_update_meta_with_pin(self, client, admin_pin):
        r = client.put("/api/event/admin/meta", params={"pin": admin_pin}, json={"subtitle": "Test-Update"})
        assert r.status_code == 200
        assert r.json()["subtitle"] == "Test-Update"
        # Wiederherstellen
        client.put("/api/event/admin/meta", params={"pin": admin_pin},
                    json={"subtitle": "Handwerkszeug 21-27: Checklisten, Eigenerklärung, Charta der Grundrechte, Best-Practice, Tools, KI und Digitalisierung"})


class TestAgenda:
    def test_get_agenda_flat(self, client):
        r = client.get("/api/event/agenda")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) > 0
        assert all("id" in i and "time" in i and "title" in i for i in items)

    def test_get_agenda_filtered(self, client):
        r = client.get("/api/event/agenda", params={"category": "workshop5"})
        assert r.status_code == 200
        items = r.json()
        assert all(i["category"] == "workshop5" for i in items)

    def test_get_agenda_by_days(self, client):
        r = client.get("/api/event/agenda/days")
        assert r.status_code == 200
        days = r.json()
        assert isinstance(days, list)
        assert len(days) == 3  # Di, Mi, Do
        for day in days:
            assert "day" in day
            assert "label" in day
            assert "items" in day
            assert len(day["items"]) > 0

    def test_get_agenda_by_days_workshop5(self, client):
        r = client.get("/api/event/agenda/days", params={"category": "workshop5"})
        assert r.status_code == 200
        days = r.json()
        assert len(days) == 3
        total_items = sum(len(d["items"]) for d in days)
        assert total_items == 23  # Workshop 5 hat 23 Punkte

    def test_agenda_item_has_status_and_scenario(self, client):
        r = client.get("/api/event/agenda", params={"category": "workshop5"})
        items = r.json()
        assert all("status" in i for i in items)
        assert all("scenario_id" in i for i in items)
        # Mindestens ein Item sollte ein Szenario haben
        scenarios = [i for i in items if i["scenario_id"] is not None]
        assert len(scenarios) >= 4  # Szenarien 1, 2, 3, 5/6


class TestAgendaAdmin:
    def test_start_item(self, client, admin_pin):
        items = client.get("/api/event/agenda", params={"category": "workshop5"}).json()
        first_id = items[0]["id"]

        r = client.post(f"/api/event/admin/agenda/{first_id}/start", params={"pin": admin_pin})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "active"
        assert data["started_at"] is not None

    def test_adjust_time(self, client, admin_pin):
        items = client.get("/api/event/agenda", params={"category": "workshop5"}).json()
        active = next((i for i in items if i["status"] == "active"), items[0])
        if active["status"] != "active":
            client.post(f"/api/event/admin/agenda/{active['id']}/start", params={"pin": admin_pin})
            active = client.get(f"/api/event/agenda", params={"category": "workshop5"}).json()
            active = next(i for i in active if i["status"] == "active")

        current_dur = active["duration_minutes"]
        # Falls an der Obergrenze, erst runtergehen
        if current_dur >= 475:
            client.post(f"/api/event/admin/agenda/{active['id']}/adjust-time",
                        params={"pin": admin_pin, "minutes": -400})
            current_dur = client.get("/api/event/agenda", params={"category": "workshop5"}).json()
            current_dur = next(i for i in current_dur if i["status"] == "active")["duration_minutes"]

        r = client.post(f"/api/event/admin/agenda/{active['id']}/adjust-time",
                        params={"pin": admin_pin, "minutes": 5})
        assert r.status_code == 200
        assert r.json()["duration_minutes"] == current_dur + 5

        # Zurueck
        client.post(f"/api/event/admin/agenda/{active['id']}/adjust-time",
                    params={"pin": admin_pin, "minutes": -5})

    def test_adjust_time_bounds(self, client, admin_pin):
        items = client.get("/api/event/agenda", params={"category": "workshop5"}).json()
        active = next((i for i in items if i["status"] == "active"), None)
        if not active:
            pytest.skip("Kein aktiver Punkt")
        # Darf nicht unter 5 Min fallen
        r = client.post(f"/api/event/admin/agenda/{active['id']}/adjust-time",
                        params={"pin": admin_pin, "minutes": -9999})
        assert r.status_code == 200
        assert r.json()["duration_minutes"] >= 5

        # Darf nicht ueber 480 Min
        r = client.post(f"/api/event/admin/agenda/{active['id']}/adjust-time",
                        params={"pin": admin_pin, "minutes": 9999})
        assert r.status_code == 200
        assert r.json()["duration_minutes"] <= 480

    def test_reset_timer(self, client, admin_pin):
        items = client.get("/api/event/agenda", params={"category": "workshop5"}).json()
        active = next((i for i in items if i["status"] == "active"), None)
        if not active:
            pytest.skip("Kein aktiver Punkt")
        r = client.post(f"/api/event/admin/agenda/{active['id']}/reset-timer",
                        params={"pin": admin_pin})
        assert r.status_code == 200
        assert r.json()["started_at"] is not None

    def test_reset_timer_requires_active(self, client, admin_pin):
        # Einen pending Punkt finden
        items = client.get("/api/event/agenda", params={"category": "workshop5"}).json()
        pending = next((i for i in items if i["status"] == "pending"), None)
        if not pending:
            pytest.skip("Kein pending Punkt")
        r = client.post(f"/api/event/admin/agenda/{pending['id']}/reset-timer",
                        params={"pin": admin_pin})
        assert r.status_code == 400

    def test_reset_status(self, client, admin_pin):
        r = client.post("/api/event/admin/agenda/reset-status",
                        params={"pin": admin_pin, "category": "workshop5"})
        assert r.status_code == 200
        assert r.json()["reset"] >= 1

    def test_set_status(self, client, admin_pin):
        items = client.get("/api/event/agenda", params={"category": "workshop5"}).json()
        item_id = items[0]["id"]
        r = client.put(f"/api/event/admin/agenda/{item_id}/status",
                       params={"pin": admin_pin, "status": "done"})
        assert r.status_code == 200
        assert r.json()["status"] == "done"
        # Zurueck
        client.post("/api/event/admin/agenda/reset-status",
                    params={"pin": admin_pin, "category": "workshop5"})


class TestInviteLinks:
    def test_valid_invite(self, client):
        r = client.get("/api/event/invite/b354305c2a9df35f")
        assert r.status_code == 200
        data = r.json()
        assert data["first_name"] == "Patrick"
        assert data["last_name"] == "Heitbrink"
        assert data["organization"] == "Hamburg"
        assert data["fund"] == "ESF"

    def test_invalid_invite(self, client):
        r = client.get("/api/event/invite/invalid_token_xyz")
        assert r.status_code == 404


class TestRegistrations:
    def test_list_registrations(self, client, admin_pin):
        r = client.get("/api/event/admin/registrations", params={"pin": admin_pin})
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 22
        # Pruefen ob fund und invite_token vorhanden
        invited = [reg for reg in data["registrations"] if reg.get("invite_token")]
        assert len(invited) >= 22
        for reg in invited:
            assert reg["fund"] is not None

    def test_register_duplicate_email_updates(self, client):
        r = client.post("/api/event/register", json={
            "first_name": "Test",
            "last_name": "Duplicate",
            "organization": "Testorg",
            "email": "patrick.heitbrink@bwai.hamburg.de",
            "privacy_accepted": True,
        })
        assert r.status_code == 201
        assert r.json()["status"] == "registered"

    def test_register_requires_privacy(self, client):
        r = client.post("/api/event/register", json={
            "first_name": "A",
            "last_name": "B",
            "organization": "C",
            "email": "a@b.de",
            "privacy_accepted": False,
        })
        assert r.status_code == 400


class TestTopics:
    def test_list_topics(self, client):
        r = client.get("/api/event/topics")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_vote(self, client):
        topics = client.get("/api/event/topics").json()
        if not topics:
            pytest.skip("Keine Topics vorhanden")
        topic_id = topics[0]["id"]
        before = topics[0]["votes"]
        r = client.post(f"/api/event/topics/{topic_id}/vote")
        assert r.status_code == 200
        assert r.json()["votes"] == before + 1

    def test_submit_topic_invalid_registration(self, client):
        r = client.post("/api/event/topics", params={"registration_id": "nonexistent"}, json={
            "topic": "Test",
        })
        assert r.status_code == 404
