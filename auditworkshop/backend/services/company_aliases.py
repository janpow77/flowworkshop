"""
Geteiltes Aliases-Modul fuer State-Aid und Beneficiaries.

Quelle: data/state_aid_aliases.json (vom State-Aid-Optimierungs-Agent
gepflegt). Beide Suchpfade nutzen dieselbe Datenbasis, damit ein neuer
Alias (z.B. 'BMWK') in beiden Tools konsistent expandiert wird.

Kategorie: workflow / shared utility — kein Schema, keine Migrationen.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

# Fallback-Set, falls die JSON-Datei (noch) nicht existiert oder unlesbar ist.
# Deckt die haeufigsten Akronyme ab (Bundesministerien, Foerderbanken,
# Forschungseinrichtungen DE/AT) — siehe state_aid_aliases.json fuer das
# voll gepflegte Mapping.
_FALLBACK: dict[str, str] = {
    "kfw": "Kreditanstalt für Wiederaufbau",
    "bmw": "Bayerische Motoren Werke",
    "bmwk": "Bundesministerium für Wirtschaft und Klimaschutz",
    "bmwi": "Bundesministerium für Wirtschaft und Energie",
    "bmbf": "Bundesministerium für Bildung und Forschung",
    "bafa": "Bundesamt für Wirtschaft und Ausfuhrkontrolle",
    "fhg": "Fraunhofer-Gesellschaft",
    "dfg": "Deutsche Forschungsgemeinschaft",
    "dlr": "Deutsches Zentrum für Luft- und Raumfahrt",
    "ihk": "Industrie- und Handelskammer",
    "öbb": "Österreichische Bundesbahnen",
    "ffg": "Österreichische Forschungsförderungsgesellschaft",
}


def _resolve_aliases_path() -> Path:
    """Pfad zur Aliases-JSON. Im Container /app/data, lokal relativ."""
    env_path = os.environ.get("STATE_AID_ALIASES_PATH")
    if env_path:
        return Path(env_path)
    container_path = Path("/app/data/state_aid_aliases.json")
    if container_path.exists():
        return container_path
    # Lokal-Fallback (Tests ausserhalb des Containers)
    return Path(__file__).resolve().parent.parent / "data" / "state_aid_aliases.json"


@lru_cache(maxsize=1)
def load_company_aliases() -> dict[str, str]:
    """Laedt das Alias-Mapping {akronym_lower: vollform}.

    - Eintraege mit '_'-Praefix (Meta) werden ignoriert.
    - Bei Datei-/Parse-Fehler wird das Fallback-Mapping verwendet, damit
      die Suche niemals wegen fehlender JSON crasht.
    """
    path = _resolve_aliases_path()
    if not path.exists():
        log.info("Aliases-Datei %s fehlt — Fallback-Mapping wird verwendet.", path)
        return dict(_FALLBACK)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        result = {
            k.lower().strip(): str(v).strip()
            for k, v in data.items()
            if not k.startswith("_") and isinstance(v, str)
        }
        if not result:
            return dict(_FALLBACK)
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("Aliases konnten nicht geladen werden (%s) — Fallback aktiv.", exc)
        return dict(_FALLBACK)


def expand_alias(query: str) -> tuple[str, str | None]:
    """Erweitert die Query um die ausgeschriebene Form, wenn ein Alias erkannt wird.

    Beispiele:
      - 'KfW'             -> ('Kreditanstalt für Wiederaufbau KfW',
                              'Kreditanstalt für Wiederaufbau')
      - 'BMWK Förderung'  -> ('Bundesministerium für Wirtschaft und Klimaschutz
                              BMWK Förderung', 'Bundesministerium ...')
      - 'XYZ-Random'      -> ('XYZ-Random', None)

    Die expandierte Variante haengt das Original an, damit der Token-Match
    sowohl das Akronym (in Identifier-/Adressfeldern) als auch die Vollform
    (im Namen) findet.
    """
    if not query:
        return query, None
    q = query.strip()
    if not q:
        return q, None

    aliases = load_company_aliases()
    if not aliases:
        return q, None

    q_low = q.lower()
    # 1) Vollstaendige Query als Alias
    if q_low in aliases:
        full = aliases[q_low]
        return f"{full} {q}", full

    # 2) Erstes Token als Alias (typisch: 'BMWK Förderung 2024')
    parts = q_low.split()
    if parts:
        first = parts[0]
        # Nur kurze Akronyme akzeptieren (<=6 Zeichen), damit
        # 'fraunhofer institut ...' nicht als Akronym-Match interpretiert wird,
        # falls 'fraunhofer' im JSON steht.
        if first in aliases and len(first) <= 6:
            full = aliases[first]
            return f"{full} {q}", full

    return q, None


__all__ = ["load_company_aliases", "expand_alias"]
