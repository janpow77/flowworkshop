"""
Anbindung von auditcore_entity_matching.

Geprüft wird, dass Normalisierung, LEI-Formatprüfung und Kandidatenbewertung
aus dem installierten Paket kommen und sich gegenüber dem bisherigen Stand
nicht ändern (Prüfziffern werden bewusst weiterhin nicht verlangt).
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
    assert sn.normalize_name("Müller GmbH") == "muller"


def test_lei_bleibt_formatpruefung_wie_bisher():
    # Falsche Prüfziffern: bisheriges Verhalten bleibt bis zur fachlichen Entscheidung.
    assert er.is_valid_lei("7LTWFZYICNSX8D621K87") is True
    assert er.extract_lei_from_text("LEI: 529900T8BM49AURSDO55") == "529900T8BM49AURSDO55"


def test_klassen_und_teilmengenregel():
    assert sn._classify(100, "putin", "vladimir vladimirovich putin") == "high"
    assert sn._classify(100, "vladimir putin", "putin vladimir") == "exact"
