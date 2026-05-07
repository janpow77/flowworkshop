"""
flowworkshop · country_profiles.py
Zentrale Hinterlegung der Länder, die in Szenario 6 (Begünstigtenverzeichnis)
unterstützt werden. Wird von dataframe_service, geocoding_service und dem
beneficiaries-Router verwendet, damit Frontend und Backend dieselben
Bundesland-/Region-Listen, Aliasse und Geocoding-Hints kennen.
"""
from __future__ import annotations

import re
import unicodedata


COUNTRY_PROFILES: dict[str, dict] = {
    "DE": {
        "country_name": "Deutschland",
        "nominatim_countrycode": "de",
        "region_label": "Bundesland",
        "regions": [
            "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen",
            "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen",
            "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen",
            "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
            # Bundesebene (für Bundesfonds wie ISF und AMIF — keine Region,
            # aber als logische Klammer in der UI)
            "Bund",
        ],
        "aliases": ["deutschland", "germany", "de"],
    },
    "AT": {
        "country_name": "Österreich",
        "nominatim_countrycode": "at",
        "region_label": "Bundesland",
        "regions": [
            "Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich",
            "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien",
        ],
        "aliases": ["österreich", "oesterreich", "austria", "at"],
    },
}


# Vorkonfigurierte Quellen, die in der Demo angezeigt werden, sobald jemand
# eine österreichische Liste hochlädt oder die Quellen erfragt.
AUSTRIA_BENEFICIARY_SOURCES = [
    {
        "source_id": "austria_efre_jtf_2021_2027",
        "country_code": "AT",
        "country_name": "Österreich",
        "fonds": "EFRE/JTF",
        "periode": "2021-2027",
        "source_url": "https://www.efre.gv.at/projekte/projektlandkarte",
        "display_name": "Österreich EFRE/JTF 2021-2027",
    },
    {
        "source_id": "austria_esf_jtf_2021_2027",
        "country_code": "AT",
        "country_name": "Österreich",
        "fonds": "ESF+/JTF",
        "periode": "2021-2027",
        "source_url": "https://www.esf.at/projekte/liste-der-vorhaben-2/",
        "display_name": "Österreich ESF+/JTF 2021-2027",
    },
]


# Flache Liste aller erlaubten Bundeslaender / Regionen ueber alle Laender.
# Wird vom Auth-Signup als Whitelist genutzt + ergaenzt um "Bund (Österreich)"
# fuer AT-Bundesfonds.
REGIONS_FLAT: tuple[str, ...] = tuple(
    sorted({
        *COUNTRY_PROFILES["DE"]["regions"],
        *COUNTRY_PROFILES["AT"]["regions"],
        "Bund (Österreich)",
    })
)


def _normalize(value: str | None) -> str:
    text_value = str(value or "").lower()
    text_value = (
        text_value.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    text_value = unicodedata.normalize("NFKD", text_value)
    text_value = "".join(ch for ch in text_value if not unicodedata.combining(ch))
    text_value = re.sub(r"[_/\\.\-]+", " ", text_value)
    text_value = re.sub(r"[^a-z0-9 ]+", " ", text_value)
    return re.sub(r"\s+", " ", text_value).strip()


def get_country_profile(country_code: str | None) -> dict | None:
    if not country_code:
        return None
    return COUNTRY_PROFILES.get(country_code.upper())


def list_country_codes() -> list[str]:
    return list(COUNTRY_PROFILES.keys())


def get_regions(country_code: str | None) -> list[str]:
    profile = get_country_profile(country_code)
    return list(profile["regions"]) if profile else []


def get_region_label(country_code: str | None) -> str:
    profile = get_country_profile(country_code)
    if profile:
        return profile["region_label"]
    return "Region/Bundesland"


def get_country_name(country_code: str | None) -> str | None:
    profile = get_country_profile(country_code)
    return profile["country_name"] if profile else None


def detect_country_code(*texts: str | None) -> str | None:
    """Findet den Country-Code (DE/AT) aus Dateinamen, Titelzeilen oder Bundesland-Werten.

    Konvention: Das erste Argument ist der Dateiname (oder eine andere
    kompakte Quelle). Kurze Aliasse mit weniger als 4 Buchstaben (z.B. ``de``,
    ``at``) werden nur darauf gematcht, weil sie sonst in freiem Datentext
    triviale False Positives liefern (etwa ``Diakonie de la Tour`` oder das
    englische ``at``).
    """
    normalized_inputs = [_normalize(text) for text in texts if text]
    if not normalized_inputs:
        return None

    filename_input = normalized_inputs[0]
    text_inputs = normalized_inputs[1:] if len(normalized_inputs) > 1 else []

    # 1. Aliasse direkt pruefen
    for code, profile in COUNTRY_PROFILES.items():
        for alias in profile.get("aliases", []):
            normalized_alias = _normalize(alias)
            if not normalized_alias:
                continue
            haystacks = [filename_input]
            if len(normalized_alias) >= 4:
                haystacks.extend(text_inputs)
            for normalized_input in haystacks:
                if re.search(rf"\b{re.escape(normalized_alias)}\b", normalized_input):
                    return code

    # 2. Region/Bundesland → Land ableiten (längster Treffer gewinnt)
    candidates: list[tuple[int, str]] = []
    for code, profile in COUNTRY_PROFILES.items():
        for region in profile.get("regions", []):
            normalized_region = _normalize(region)
            if not normalized_region:
                continue
            for normalized_input in normalized_inputs:
                if normalized_region in normalized_input:
                    candidates.append((len(normalized_region), code))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    # 3. Spezifische Dateiname-Hints für Österreich (z.B. efre_at, esf-at)
    austria_hints = ("efre at", "esf at", "esf plus at", "jtf at")
    for hint in austria_hints:
        if hint in filename_input:
            return "AT"

    return None


def country_code_for_bundesland(region: str | None) -> str | None:
    """Liefert das Land zu einem Bundesland-/Region-Wert (case-/diakritik-insensitiv)."""
    if not region:
        return None
    normalized_target = _normalize(region)
    if not normalized_target:
        return None
    for code, profile in COUNTRY_PROFILES.items():
        for candidate in profile.get("regions", []):
            if _normalize(candidate) == normalized_target:
                return code
    return None
