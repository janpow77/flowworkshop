"""
Prüft die Falldatei des Pflicht-Rauchtests nach jedem Deploy
(deploy/functional-smoke.json im Repo-Root).

Die Fälle laufen über die öffentliche Beihilfensuche und brauchen kein
Rauchtestkonto. Die Sanktionssuche bleibt draußen, weil sie nur mit
Admin-Rolle erreichbar ist (``require_admin``) und das Rollenmodell keine
engere Leseberechtigung kennt.

Reine Unit-Tests, keine DB- und keine Netzverbindung.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_FALLDATEI = _BACKEND.parent.parent / "deploy" / "functional-smoke.json"
_HEALTH = re.compile(r"(^|/)(health|healthz|ready|readyz|live|livez|ping|status)/?$", re.I)


def _faelle() -> list[dict]:
    return json.loads(_FALLDATEI.read_text(encoding="utf-8"))["functional_smoke"]


def test_faelle_sind_fachlich_und_eindeutig():
    faelle = _faelle()
    assert 2 <= len(faelle) <= 4
    assert len({f["name"] for f in faelle}) == len(faelle)
    for fall in faelle:
        pfad = urlsplit(fall["path"]).path
        assert fall["path"].startswith("/") and "://" not in fall["path"]
        assert not _HEALTH.search(pfad), fall["name"]
        assert fall["changed_feature"].strip()
        assert fall.get("json_expect") or fall.get("body_contains")


def test_faelle_nur_lesend_und_ohne_zugangsdaten():
    for fall in _faelle():
        assert fall.get("method", "GET").upper() == "GET", fall["name"]
        assert not fall.get("headers_from_env"), fall["name"]
        assert "json_body" not in fall, fall["name"]
        assert urlsplit(fall["path"]).path == "/api/state-aid/search"
        assert "/api/sanctions" not in fall["path"]


def test_schreibweisen_ergeben_die_erwartete_vergleichsform():
    """Die erwartete Vergleichsform muss zur Normalisierung im Code passen."""
    from services.state_aid_service import normalize_company_name

    for fall in _faelle():
        suchbegriff = parse_qs(urlsplit(fall["path"]).query)["q"][0]
        assert normalize_company_name(suchbegriff) == fall["json_expect"]["normalized"], fall["name"]


def test_umlaut_umschrieben_und_zerlegt_erwarten_dieselben_treffer():
    faelle = {f["name"]: f for f in _faelle()}
    varianten = ["beihilfen-suche-umlaut", "beihilfen-suche-umschrieben", "beihilfen-suche-zerlegt"]
    suchbegriffe = [parse_qs(urlsplit(faelle[n]["path"]).query)["q"][0] for n in varianten]
    assert suchbegriffe == ["Südzucker", "Suedzucker", "Südzucker"]
    erwartungen = [faelle[n]["json_expect"] for n in varianten]
    assert all(e == erwartungen[0] for e in erwartungen)
    assert erwartungen[0]["hits.0.confidence"] == "exact"


def test_fantasiename_erwartet_keinen_treffer():
    fall = {f["name"]: f for f in _faelle()}["beihilfen-suche-fantasiename"]
    assert fall["json_expect"]["total_hits"] == 0
    assert fall["json_expect"]["hits"] == []
