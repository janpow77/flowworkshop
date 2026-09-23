"""
Anbindung von auditcore_entity_matching.

Geprüft wird, dass Normalisierung, LEI-Formatprüfung und Kandidatenbewertung
aus dem installierten Paket kommen und sich gegenüber dem bisherigen Stand
nicht ändern; LEIs werden seit der Entscheidung vom 23.09.2026 einschließlich
Prüfziffern geprüft.
"""

from __future__ import annotations

import sys
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import entity_resolution as er  # noqa: E402
from services import sanctions_service as sn  # noqa: E402
from services import state_aid_service as sa  # noqa: E402


def test_bibliothek_ist_gebunden():
    import auditcore_entity_matching

    assert version("auditcore_entity_matching") == "0.1.0"
    assert er._bibliothek.__name__ == "auditcore_entity_matching.legacy"
    assert auditcore_entity_matching.__file__


def test_varianten_bleiben_getrennt():
    assert sa.normalize_company_name("Müller GmbH") == "mueller"
    # Entscheidung 23.09.2026: auch das Sanktionsscreening schreibt Umlaute um.
    assert sn.normalize_name("Müller GmbH") == "mueller"
    # Übrige Diakritika faltet das Sanktionsprofil weiterhin, anders als State Aid.
    assert sn.normalize_name("Café Élan SARL") == "cafe elan"
    assert sa.normalize_company_name("Café Élan SARL") == "cafe élan"


def test_sanktionen_umlaute_umgeschrieben():
    assert sn.normalize_name("ÖL & GAS GRÖSSE KG") == "oel gas groesse"
    assert sn.normalize_name("Straße Holding AG") == "strasse holding"
    assert sn.normalize_name("Ärzte e.V.") == "aerzte e v"
    assert sn.normalize_name("Mueller-Schmidt Ltd.") == "mueller schmidt"
    assert sn.normalize_name("OOO Wassil") == "wassil"


def test_sanktionen_umlaut_und_umschrift_treffen_sich_exakt():
    from rapidfuzz import fuzz

    # Vorher: "muller" gegen "mueller" (< 100); jetzt identische Vergleichsform.
    assert sn.normalize_name("Müller Bau GmbH") == sn.normalize_name("Mueller Bau GmbH")
    score = fuzz.token_set_ratio(
        sn.normalize_name("Müller Bau GmbH"), sn.normalize_name("Mueller Bau GmbH")
    )
    assert score == 100
    assert sn._classify(score, "mueller bau", "mueller bau") == "exact"


def test_lei_prueft_pruefziffern():
    # Entscheidung 23.09.2026: Format und Prüfziffern (ISO 7064 MOD 97-10).
    for gueltig in ("529900T8BM49AURSDO55", "HWUPKR0MPOU8FGXBT394", " 7ltwfzyicnsx8d621k86 "):
        assert er.is_valid_lei(gueltig) is True
    for ungueltig in ("7LTWFZYICNSX8D621K87", "00000000000000000000", "ABCD1234567890123456"):
        assert er.is_valid_lei(ungueltig) is False
    assert er.extract_lei_from_text("LEI: 529900T8BM49AURSDO55") == "529900T8BM49AURSDO55"
    assert er.extract_lei_from_text("LEI: 7LTWFZYICNSX8D621K87") is None
    assert (
        er.extract_lei_from_text("7LTWFZYICNSX8D621K87 / 529900T8BM49AURSDO55")
        == "529900T8BM49AURSDO55"
    )


def test_klassen_und_teilmengenregel():
    assert sn._classify(100, "putin", "vladimir vladimirovich putin") == "high"
    assert sn._classify(100, "vladimir putin", "putin vladimir") == "exact"
