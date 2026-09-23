"""
Nominatim-Netzpfad über auditcore_geo (ohne Netz, mit Ersatztransport).

Geprüft wird: jsonv2-Anfrage mit identifizierender Kennung, Treffer,
bestätigter Nulltreffer, Netz- und Serverfehler (kein „nicht gefunden“, kein
Negativeintrag im Cache) und die Tagesgrenze von 1 000 Anfragen am
öffentlichen Endpunkt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auditcore_harvest import Response  # noqa: E402

from services import geocoding_service as gs  # noqa: E402
from services import nominatim_client as nc  # noqa: E402


class _Ersatz:
    """Transport, der eine feste Antwort liefert oder einen Netzfehler wirft."""

    def __init__(self, status: int = 200, body=None, fehler: Exception | None = None):
        self.status = status
        self.body = body
        self.fehler = fehler
        self.aufrufe: list[dict] = []

    def request(self, method, url, *, params=None, headers=None, data=None, timeout):
        self.aufrufe.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        if self.fehler is not None:
            raise nc.TransportError(str(self.fehler))
        return Response(self.status, json.dumps(self.body).encode(), {}, url)


@pytest.fixture(autouse=True)
def _ohne_warten(monkeypatch):
    monkeypatch.setattr(nc._Schlaefer, "sleep", lambda self, s: None)


@pytest.fixture
def zaehler(tmp_path):
    return nc.Tageszaehler(tmp_path / "zaehler.json")


_TREFFER = [{
    "lat": "50.1109", "lon": "8.6821", "display_name": "Frankfurt am Main, Hessen, Deutschland",
    "osm_type": "relation", "osm_id": 62400, "category": "boundary", "type": "administrative",
    "licence": "Data © OpenStreetMap contributors, ODbL 1.0. https://osm.org/copyright",
}]


def test_treffer_jsonv2_und_kennung(zaehler):
    t = _Ersatz(body=_TREFFER)
    r = nc.suche("Frankfurt am Main, Deutschland", countrycodes="de", zaehler=zaehler, transport=t)
    assert r.status == "treffer"
    assert r.geo["lat"] == pytest.approx(50.1109) and r.geo["lon"] == pytest.approx(8.6821)
    assert r.geo["display_name"].startswith("Frankfurt")
    assert t.aufrufe[0]["url"] == "https://nominatim.openstreetmap.org/search"
    assert t.aufrufe[0]["params"]["format"] == "jsonv2"
    assert t.aufrufe[0]["params"]["countrycodes"] == "de"
    assert t.aufrufe[0]["params"]["limit"] == "1"
    assert "Auditworkshop" in t.aufrufe[0]["headers"]["User-Agent"]
    assert zaehler.heute_gesendet() == 1


def test_leere_liste_ist_kein_treffer(zaehler):
    r = nc.suche("Nirgendheim, Deutschland", countrycodes="de", zaehler=zaehler, transport=_Ersatz(body=[]))
    assert r.status == "kein_treffer" and r.geo is None


def test_netzfehler_ist_nicht_nicht_gefunden(zaehler):
    r = nc.suche("Kassel, Deutschland", countrycodes="de", zaehler=zaehler,
                 transport=_Ersatz(fehler=OSError("offline")))
    assert r.status == "fehler"


def test_serverfehler_ist_nicht_nicht_gefunden(zaehler):
    r = nc.suche("Kassel, Deutschland", countrycodes="de", zaehler=zaehler,
                 transport=_Ersatz(status=503, body={"error": "busy"}))
    assert r.status == "fehler"


def test_tagesgrenze_1000(zaehler):
    zaehler.hinzufuegen(1000)
    t = _Ersatz(body=_TREFFER)
    r = nc.suche("Kassel, Deutschland", countrycodes="de", zaehler=zaehler, transport=t)
    assert r.status == "nicht_gesendet"
    assert "1000" in r.grund
    assert t.aufrufe == []


def test_zaehler_ueberlebt_neustart(tmp_path):
    pfad = tmp_path / "z.json"
    nc.Tageszaehler(pfad).hinzufuegen(7)
    assert nc.Tageszaehler(pfad).heute_gesendet() == 7


@pytest.fixture
def geocoder(monkeypatch, tmp_path):
    """geocode_single ohne Offline-Treffer, mit Remote-Geocoding und leerem Cache."""
    monkeypatch.setattr(gs, "ALLOW_REMOTE_GEOCODING", True)
    monkeypatch.setattr(gs, "_save_cache", lambda: None)
    monkeypatch.setattr(gs, "_cache", {"__geladen": None})
    monkeypatch.setattr(gs, "lookup_plz", lambda *a, **k: None)
    monkeypatch.setattr(gs, "lookup_city", lambda *a, **k: None)
    monkeypatch.setattr(gs, "_nominatim_zaehler", nc.Tageszaehler(tmp_path / "z.json"))
    return gs


def test_geocode_single_netzfehler_wird_nicht_als_negativ_gespeichert(geocoder, monkeypatch):
    def _offline(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(nc.requests, "request", _offline)
    assert geocoder.geocode_single("Irgendwo Nirgendheim", "DE") is None
    assert "de::irgendwo nirgendheim" not in geocoder._cache


def test_geocode_single_bestaetigter_nulltreffer_wird_gespeichert(geocoder, monkeypatch):
    class _Leer:
        status_code = 200
        content = b"[]"
        headers: dict = {}
        url = "https://nominatim.openstreetmap.org/search"

    monkeypatch.setattr(nc.requests, "request", lambda *a, **k: _Leer())
    assert geocoder.geocode_single("Irgendwo Nirgendheim", "DE") is None
    assert geocoder._cache["de::irgendwo nirgendheim"] is None


def test_geocode_single_treffer(geocoder, monkeypatch):
    class _Voll:
        status_code = 200
        content = json.dumps(_TREFFER).encode()
        headers: dict = {}
        url = "https://nominatim.openstreetmap.org/search"

    monkeypatch.setattr(nc.requests, "request", lambda *a, **k: _Voll())
    geo = geocoder.geocode_single("Frankfurt am Main", "DE")
    assert geo["lat"] == pytest.approx(50.1109)
    assert geocoder._cache["de::frankfurt am main"] == geo
