"""
flowworkshop · services/state_aid_service.py

Normalisierung, SA-Referenz-Erkennung, NUTS-Lookup und Fuzzy-Suche fuer das
EU-Beihilfe-Transparenzregister (Plan §6/7/8).

Wird von Router (`routers/state_aid.py`) und Harvester (`scripts/harvest_state_aid.py`)
gemeinsam genutzt.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process
from rapidfuzz.distance import JaroWinkler
from sqlalchemy import or_, text, func as sql_func
from sqlalchemy.orm import Session

from models.state_aid import StateAidAward

log = logging.getLogger(__name__)


# ── Konfiguration ─────────────────────────────────────────────────────────────

NUTS_CENTROIDS_PATH = Path(
    os.environ.get(
        "STATE_AID_NUTS_PATH",
        "/app/data/nuts/eu_nuts_centroids.json",
    )
)

# ISO-3 → ISO-2 (TAM verwendet ISO-3, NUTS-Codes ISO-2)
ISO3_TO_ISO2 = {
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CYP": "CY",
    "CZE": "CZ", "DNK": "DK", "EST": "EE", "FIN": "FI", "FRA": "FR",
    "DEU": "DE", "GRC": "EL", "HUN": "HU", "IRL": "IE", "ITA": "IT",
    "LVA": "LV", "LTU": "LT", "LUX": "LU", "MLT": "MT", "NLD": "NL",
    "POL": "PL", "PRT": "PT", "ROU": "RO", "SVK": "SK", "SVN": "SI",
    "ESP": "ES", "SWE": "SE", "GBR": "GB",
    # TAM-Sonderfaelle
    "EIB": "EU",
}

ISO2_TO_NAME = {
    "AT": "Österreich", "BE": "Belgien", "BG": "Bulgarien", "HR": "Kroatien",
    "CY": "Zypern", "CZ": "Tschechien", "DK": "Dänemark", "EE": "Estland",
    "FI": "Finnland", "FR": "Frankreich", "DE": "Deutschland", "EL": "Griechenland",
    "HU": "Ungarn", "IE": "Irland", "IT": "Italien", "LV": "Lettland", "LT": "Litauen",
    "LU": "Luxemburg", "MT": "Malta", "NL": "Niederlande", "PL": "Polen", "PT": "Portugal",
    "RO": "Rumänien", "SK": "Slowakei", "SI": "Slowenien", "ES": "Spanien", "SE": "Schweden",
    "GB": "Vereinigtes Königreich",
}

# Englische, franzoesische und alternative Namen → ISO-2 (TAM liefert auf
# Englisch: "Germany", "Austria", "Czech Republic", ...).
NAME_TO_ISO2 = {
    # EN
    "germany": "DE", "austria": "AT", "belgium": "BE", "bulgaria": "BG",
    "croatia": "HR", "cyprus": "CY", "czech republic": "CZ", "czechia": "CZ",
    "denmark": "DK", "estonia": "EE", "finland": "FI", "france": "FR",
    "greece": "EL", "hungary": "HU", "ireland": "IE", "italy": "IT",
    "latvia": "LV", "lithuania": "LT", "luxembourg": "LU", "malta": "MT",
    "netherlands": "NL", "poland": "PL", "portugal": "PT", "romania": "RO",
    "slovakia": "SK", "slovenia": "SI", "spain": "ES", "sweden": "SE",
    "united kingdom": "GB",
    # DE (zusaetzlich zu ISO2_TO_NAME, fuer Lookup)
    "deutschland": "DE", "oesterreich": "AT", "österreich": "AT",
    "tschechien": "CZ", "frankreich": "FR", "italien": "IT", "spanien": "ES",
    "polen": "PL", "rumaenien": "RO", "rumänien": "RO", "ungarn": "HU",
    "slowenien": "SI", "slowakei": "SK", "kroatien": "HR", "griechenland": "EL",
    "niederlande": "NL", "belgien": "BE", "luxemburg": "LU", "irland": "IE",
    "schweden": "SE", "finnland": "FI", "estland": "EE",
    "lettland": "LV", "litauen": "LT", "daenemark": "DK", "dänemark": "DK",
    "zypern": "CY", "bulgarien": "BG",
    # `portugal` und `malta` stehen bereits oben in der EN-Liste — selber Key,
    # selbe ISO-2; hier nicht erneut auffuehren (ruff F601).
}

# Region-Label → NUTS-Code (DE-Bundeslaender → NUTS-1, AT-Bundeslaender → NUTS-2)
DE_REGION_TO_NUTS1 = {
    "baden-wuerttemberg": "DE1", "baden-württemberg": "DE1", "bw": "DE1",
    "bayern": "DE2", "by": "DE2", "bavaria": "DE2",
    "berlin": "DE3", "be": "DE3",
    "brandenburg": "DE4", "bb": "DE4",
    "bremen": "DE5", "hb": "DE5",
    "hamburg": "DE6", "hh": "DE6",
    "hessen": "DE7", "he": "DE7", "hesse": "DE7",
    "mecklenburg-vorpommern": "DE8", "mv": "DE8",
    "niedersachsen": "DE9", "ni": "DE9", "lower saxony": "DE9",
    "nordrhein-westfalen": "DEA", "nrw": "DEA", "north rhine-westphalia": "DEA",
    "rheinland-pfalz": "DEB", "rp": "DEB",
    "saarland": "DEC", "sl": "DEC",
    "sachsen": "DED", "sn": "DED", "saxony": "DED",
    "sachsen-anhalt": "DEE", "st": "DEE", "saxony-anhalt": "DEE",
    "schleswig-holstein": "DEF", "sh": "DEF",
    "thueringen": "DEG", "thüringen": "DEG", "th": "DEG", "thuringia": "DEG",
}

# Oesterreichische Bundeslaender → NUTS-2 (offizielle Eurostat-Codes)
AT_REGION_TO_NUTS2 = {
    "burgenland": "AT11", "bgld": "AT11",
    "niederoesterreich": "AT12", "niederösterreich": "AT12", "noe": "AT12",
    "lower austria": "AT12",
    "wien": "AT13", "vienna": "AT13", "w": "AT13",
    "kaernten": "AT21", "kärnten": "AT21", "ktn": "AT21", "carinthia": "AT21",
    "steiermark": "AT22", "stmk": "AT22", "styria": "AT22",
    "oberoesterreich": "AT31", "oberösterreich": "AT31", "ooe": "AT31",
    "upper austria": "AT31",
    "salzburg": "AT32", "sbg": "AT32",
    "tirol": "AT33", "tyrol": "AT33", "t": "AT33",
    "vorarlberg": "AT34", "vbg": "AT34",
    "ostoesterreich": "AT1", "ostösterreich": "AT1", "eastern austria": "AT1",
    "suedoesterreich": "AT2", "südösterreich": "AT2", "southern austria": "AT2",
    "westoesterreich": "AT3", "westösterreich": "AT3", "western austria": "AT3",
}

# Deutsche NUTS-2 Regierungsbezirke + Statistische Regionen → NUTS-1 Bundesland.
# TAM liefert oft Regierungsbezirke ("Köln", "Düsseldorf") oder NUTS-2-Bezeichner
# ("Oberbayern", "Schwaben"). Diese muessen aufs Bundesland aufgeloest werden.
DE_NUTS2_TO_NUTS1 = {
    # Baden-Wuerttemberg (DE1)
    "stuttgart": "DE1", "karlsruhe": "DE1", "freiburg": "DE1", "tuebingen": "DE1",
    "tübingen": "DE1",
    # Bayern (DE2)
    "oberbayern": "DE2", "niederbayern": "DE2", "oberpfalz": "DE2",
    "oberfranken": "DE2", "mittelfranken": "DE2", "unterfranken": "DE2",
    "schwaben": "DE2",
    # Brandenburg (DE4)
    "brandenburg-nordost": "DE4", "brandenburg-suedwest": "DE4",
    "brandenburg-südwest": "DE4",
    # Hessen (DE7)
    "darmstadt": "DE7", "giessen": "DE7", "gießen": "DE7", "kassel": "DE7",
    # Mecklenburg-Vorpommern (DE8) — keine NUTS-2 Subdivision
    # Niedersachsen (DE9)
    "braunschweig": "DE9", "hannover": "DE9", "lueneburg": "DE9",
    "lüneburg": "DE9", "weser-ems": "DE9",
    # Nordrhein-Westfalen (DEA)
    "duesseldorf": "DEA", "düsseldorf": "DEA", "koeln": "DEA", "köln": "DEA",
    "muenster": "DEA", "münster": "DEA", "detmold": "DEA", "arnsberg": "DEA",
    # Rheinland-Pfalz (DEB)
    "koblenz": "DEB", "trier": "DEB", "rheinhessen-pfalz": "DEB",
    # Sachsen (DED)
    "chemnitz": "DED", "dresden": "DED", "leipzig": "DED",
    # Sachsen-Anhalt (DEE)
    "halle": "DEE", "magdeburg": "DEE",
    # Thueringen (DEG) — keine NUTS-2 Subdivision
}

# Rechtsform-Suffixe (aus sanctions_service erweitert um State-Aid-Faelle)
_LEGAL_SUFFIXES = {
    "gmbh", "ag", "kg", "ohg", "se", "ug", "ev", "ggmbh",
    "ltd", "llc", "inc", "corp", "co", "company", "limited", "plc",
    "sa", "sas", "sarl", "sl", "spa", "srl", "bv", "nv", "oy", "ab",
    "jsc", "ojsc", "pjsc", "ooo", "zao", "fzc", "fz", "lp",
    "kgaa", "mbh", "und", "co.kg", "cokg",
    "sp", "spzoo",
}

# Fuellwoerter, die in der normalisierten Form entfernt werden
_FILLER_WORDS = {
    "holding", "group", "gruppe", "deutschland", "germany",
    "international", "european", "europe",
}

# SA-Referenz-Regex (Plan §6.4)
_SA_REGEX = re.compile(r"\bSA[\s\.\-_]*(\d{4,6})(?:[/\-\.](\d{4}))?", re.IGNORECASE)

# Zahlen-/Whitespace-Cleaner
_WS_RE = re.compile(r"\s+")
# Hyphen wird durch Leerzeichen ersetzt (statt erhalten bleiben), damit
# 'Fraunhofer-Gesellschaft' in Tokens 'fraunhofer' + 'gesellschaft' faellt.
# Sonst wuerden Bindestrich-zusammengezogene Firmennamen die Fuzzy-Suche
# brechen ('Fraunhofer Gesellschaft' findet das Original nicht).
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


# ── Normalisierung ────────────────────────────────────────────────────────────


def _strip_accents(text: str) -> str:
    """Diakritika und deutsche Umlaute fuer Vergleich abbauen."""
    if not text:
        return ""
    table = str.maketrans({
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "ae", "Ö": "oe", "Ü": "ue",
        "á": "a", "à": "a", "â": "a", "ã": "a", "å": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "ô": "o", "õ": "o",
        "ú": "u", "ù": "u", "û": "u",
        "ç": "c", "ñ": "n", "ý": "y",
        "ł": "l", "ń": "n", "ś": "s", "ź": "z", "ż": "z",
        "č": "c", "š": "s", "ž": "z", "đ": "d",
    })
    return text.translate(table)


def normalize_company_name(text: str | None, *, drop_filler: bool = False) -> str:
    """Plan §6.1 — vergleichsform fuer Unternehmensnamen.

    - lowercase, ohne Akzente / Umlaute
    - Rechtsform-Suffixe entfernen
    - Satzzeichen weg, Whitespace kompakt
    - optional: Fuellwoerter entfernen (nur fuer Identifier-Bucket)
    """
    if not text:
        return ""
    s = _strip_accents(text).casefold()
    s = s.replace("&", " und ")
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    tokens: list[str] = []
    for tok in s.split():
        # 'gmbh.' o.ae. faellt durch _PUNCT_RE schon raus
        compact = tok.replace(".", "").replace("-", "")
        if compact in _LEGAL_SUFFIXES:
            continue
        if drop_filler and compact in _FILLER_WORDS:
            continue
        tokens.append(tok)
    return " ".join(tokens)


# ── SA-Referenz ───────────────────────────────────────────────────────────────


def detect_sa_reference(text: str | None) -> tuple[str | None, str | None]:
    """Plan §6.4 — Erkennung und Normalisierung einer SA-Referenz.

    Liefert ``(normalized, case_url)``. ``normalized`` hat die Form ``SA.12345``.
    """
    if not text:
        return None, None
    m = _SA_REGEX.search(text)
    if not m:
        return None, None
    number = m.group(1)
    suffix = m.group(2)
    if suffix:
        normalized = f"SA.{number}/{suffix}"
        url_token = f"SA.{number}/{suffix}"
    else:
        normalized = f"SA.{number}"
        url_token = f"SA.{number}"
    case_url = f"https://competition-cases.ec.europa.eu/cases/{url_token}"
    return normalized, case_url


def build_competition_search_url(beneficiary_or_term: str) -> str:
    """Generischer Suchlink in der Competition Cases Search."""
    import urllib.parse
    return (
        "https://competition-cases.ec.europa.eu/search?searchterm="
        + urllib.parse.quote_plus(beneficiary_or_term)
    )


# ── Betrag ────────────────────────────────────────────────────────────────────


def parse_amount(text: str | None) -> Decimal | None:
    """Plan §6.2 — Betrag aus TAM-String parsen.

    TAM liefert z. B. '1,200,000' oder '1.200.000,00'. Wir versuchen beide
    Konventionen, ohne aktive Waehrungsumrechnung.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s or s in {"-", "—"}:
        return None
    # Currency-Symbole / -Codes entfernen
    s = re.sub(r"[€$£¥]", "", s)
    s = re.sub(r"\b(eur|usd|gbp|chf|sek)\b", "", s, flags=re.IGNORECASE).strip()

    # GBER-Spannen: '500,001 to 1,000,000' → konservativ Obergrenze
    m_range = re.search(r"(.+?)\s+to\s+(.+)", s, flags=re.IGNORECASE)
    if m_range:
        return parse_amount(m_range.group(2))
    m_lt = re.match(r"\s*(?:less than|<)\s*(.+)", s, flags=re.IGNORECASE)
    if m_lt:
        return parse_amount(m_lt.group(1))
    m_gt = re.match(r"\s*(?:more than|>)\s*(.+)", s, flags=re.IGNORECASE)
    if m_gt:
        return parse_amount(m_gt.group(1))

    # Whitespace (auch NBSP) entfernen
    s = re.sub(r"\s+", "", s)
    if "," in s and "." in s:
        # Heuristik: letztes Trennzeichen ist Dezimaltrenner
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Wenn genau ein Komma und 1-2 Nachkommastellen → Dezimaltrenner
        left, _, right = s.rpartition(",")
        if len(right) in (1, 2) and right.isdigit():
            s = f"{left.replace(',', '')}.{right}"
        else:
            s = s.replace(",", "")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


# ── Datum ─────────────────────────────────────────────────────────────────────


def parse_date(text: str | None) -> date | None:
    """TAM liefert Datumsangaben im Format 'DD/MM/YYYY' oder 'YYYY-MM-DD'."""
    if not text:
        return None
    s = str(text).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── NUTS-Lookup ───────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load_nuts_centroids() -> dict:
    """Plan §8.2 — NUTS-Centroids als Lookup-Dictionary.

    Merged Reihenfolge:
    1. eu_nuts_centroids.json (Basis: NUTS-0/1/2 fuer alle EU-Laender)
    2. nuts_de.json (NUTS-3 DE: 401 Kreise mit Centroids)
    3. nuts_at.json (NUTS-3 AT: 35 Bezirke; Centroids ueberwiegend NUTS-2-Fallback)
    """
    out: dict = {}
    # 1. EU-Basis
    if NUTS_CENTROIDS_PATH.exists():
        try:
            with open(NUTS_CENTROIDS_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
            for k, v in data.items():
                if not k.startswith("_"):
                    out[k] = v
        except Exception as exc:
            log.error("NUTS-Centroids konnten nicht geladen werden: %s", exc)
    else:
        log.warning("NUTS-Centroids fehlen: %s", NUTS_CENTROIDS_PATH)

    # 2./3. NUTS-3-Files (DE + AT) zusaetzlich einmergen
    for nuts3_path in (_NUTS_DE_PATH, _NUTS_AT_PATH):
        if not nuts3_path.exists():
            continue
        try:
            with open(nuts3_path, encoding="utf-8") as fh:
                data = json.load(fh)
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                # Nicht ueberschreiben, nur ergaenzen — NUTS-2 hat Vorrang
                # aus EU-Basis; NUTS-3 fehlt dort meistens.
                if k not in out and isinstance(v, dict) and "lat" in v and "lon" in v:
                    out[k] = v
        except Exception as exc:
            log.warning("NUTS-3-Centroid-Merge fehlgeschlagen (%s): %s", nuts3_path, exc)
    return out


_BUNDESLAND_TO_NUTS1 = {
    "Baden-Württemberg": "DE1", "Bayern": "DE2", "Berlin": "DE3",
    "Brandenburg": "DE4", "Bremen": "DE5", "Hamburg": "DE6",
    "Hessen": "DE7", "Mecklenburg-Vorpommern": "DE8",
    "Niedersachsen": "DE9", "Nordrhein-Westfalen": "DEA",
    "Rheinland-Pfalz": "DEB", "Saarland": "DEC",
    "Sachsen": "DED", "Sachsen-Anhalt": "DEE",
    "Schleswig-Holstein": "DEF", "Thüringen": "DEG",
}

_NUTS_DE_PATH = Path("/app/data/nuts_de.json")
_NUTS_AT_PATH = Path("/app/data/nuts_at.json")


def _build_name_lookup_from_nuts_file(path: Path, *, country: str) -> dict[str, str]:
    """Generische NUTS-3-Lookup-Aufbauroutine.

    Erzeugt fuer jede Region in der JSON-Datei eine Map
    `name_lower → nuts3_code`. Akzeptiert die DE-Datei (Top-Level dict
    nuts_code → info) genauso wie die AT-Datei.

    Variants:
    - voller Name
    - ohne Akzente (Umlaute → ae/oe/ue)
    - vor erstem Komma
    - vor erster Klammer
    - vor erstem `/` (z.B. "Wiener Umland/Nordteil" → auch "Wiener Umland")

    Konflikt-Aufloesung beim Bare-Name (z.B. zwei Eintraege mit name=Muenchen):
    Eintraege mit `type=kreisfreie_stadt` haben Vorrang vor `landkreis`. So
    matcht eine Suche `Muenchen` auf DE212 (Stadt), nicht DE21H (Landkreis).
    Volle Namen mit Suffix bleiben eindeutig.
    """
    out: dict[str, str] = {}
    if not path.exists():
        log.warning("NUTS-3 %s Datei fehlt: %s", country, path)
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        log.error("NUTS-3 %s Datei nicht ladbar: %s", country, exc)
        return out

    # Pass 1: vollstaendige Namen registrieren (kollidieren selten).
    # Pass 2: Basis-Namen registrieren — kreisfreie Staedte zuerst, sodass
    # Landkreis-Eintraege nicht ueber Stadt-Eintraege schreiben.
    pass2: list[tuple[int, str, str]] = []  # (sort_priority, name_lower, code)

    def _priority(info: dict) -> int:
        # Kleinere Zahl = hoehere Prioritaet (wird zuerst eingetragen
        # und durch spaetere Eintraege NICHT ueberschrieben, wenn wir
        # `setdefault` verwenden).
        t = (info.get("type") or "").lower()
        if t == "kreisfreie_stadt":
            return 0
        if t == "landkreis":
            return 2
        return 1  # NUTS-3 ohne expliziten type (z.B. AT)

    for code, info in data.items():
        if code.startswith("_"):
            continue
        full_name = (info.get("name") or "").strip()
        if not full_name:
            continue
        nuts_code = code.upper()
        if len(nuts_code) != 5:
            continue

        # Variante 1: voller Name (mit Suffix) — eindeutig
        for v in {full_name, _strip_accents(full_name)}:
            key = v.strip().lower()
            if key:
                out[key] = nuts_code

        # Variante 2: Basis-Namen — sammeln fuer Pass 2 (nach Prioritaet)
        prio = _priority(info)
        for sep in (",", "(", "/"):
            if sep in full_name:
                base = full_name.split(sep)[0].strip()
                if base:
                    for variant in {base, _strip_accents(base)}:
                        k = variant.strip().lower()
                        if k:
                            pass2.append((prio, k, nuts_code))

        # Direkter Code-Match
        out[nuts_code] = nuts_code

    # Pass 2: nach Prioritaet sortieren (0 = kreisfreie_stadt zuerst).
    # `setdefault` traegt nur ein, wenn kein hoeher-prioritaerer Eintrag
    # bereits gesetzt ist.
    pass2.sort(key=lambda t: t[0])
    for _prio, key, code in pass2:
        out.setdefault(key, code)

    return out


@lru_cache(maxsize=1)
def load_nuts3_de_lookup() -> dict[str, str]:
    """NUTS-3-DE-Lookup: Kreis-Name (lowercase, ohne Akzente) → NUTS-3-Code.

    Quelle: backend/data/nuts_de.json (401 Kreise inkl. bundesland).
    Liefert den ECHTEN NUTS-3-Code (z.B. DE212 fuer Muenchen). Aufrufer
    kann per Prefix-Match (DE2*) auf NUTS-1 zurueckaggregieren.
    """
    return _build_name_lookup_from_nuts_file(_NUTS_DE_PATH, country="DE")


@lru_cache(maxsize=1)
def load_nuts3_at_lookup() -> dict[str, str]:
    """NUTS-3-AT-Lookup: Bezirks-Name (lowercase, ohne Akzente) → NUTS-3-Code.

    Quelle: backend/data/nuts_at.json (35 politische Bezirke).
    TAM nennt fuer AT i.d.R. NUTS-3-Bezeichner (z.B. "Oststeiermark",
    "Linz-Wels", "Innviertel"). Diese werden auf den 5-stelligen NUTS-3-Code
    aufgeloest (z.B. AT224, AT312, AT311).
    """
    return _build_name_lookup_from_nuts_file(_NUTS_AT_PATH, country="AT")


def _match_region_dict(label: str, mapping: dict[str, str], min_key_len: int = 3) -> str | None:
    """Token-genauer Match — verhindert dass `"t"` auf `"stadt"` matcht.

    `label` ist bereits ohne Akzente, lower-cased.
    """
    # 1. Vollstaendige Phrasen (Hyphen-Variante, dann Whitespace-Variante)
    for key, code in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if len(key) < min_key_len:
            continue
        if "-" in key or " " in key:
            normal = key.replace("-", " ")
            if key in label or normal in label:
                return code
    # 2. Token-Match
    tokens = [t for t in re.split(r"[\s,;\-]+", label) if t]
    token_set = set(tokens)
    for key, code in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if len(key) < min_key_len:
            continue
        if key in token_set:
            return code
    return None


def derive_nuts_code(*, region_label: str | None, country_iso2: str | None) -> tuple[str | None, int | None]:
    """Versucht aus dem TAM-Region-Label einen NUTS-Code abzuleiten.

    Plan §6.3 — keine Scheingenauigkeit. Wenn nichts erkannt wird, wird der
    Land-Code zurueckgegeben (Level 0).
    """
    if not region_label:
        if country_iso2:
            return country_iso2, 0
        return None, None

    label = _strip_accents(region_label.strip()).lower()

    # Direkter Code (z.B. 'DE7', 'DE71', 'PL92')
    direct = label.upper().replace(" ", "")
    if re.match(r"^[A-Z]{2}[0-9A-Z]{0,4}$", direct):
        if direct in load_nuts_centroids():
            level = max(0, len(direct) - 2)
            return direct, level

    # DE: 4-Stufen-Auflösung
    if country_iso2 == "DE":
        # Stufe 1: direkter Bundesland-Match (Hessen, Bayern, NRW, …)
        code = _match_region_dict(label, DE_REGION_TO_NUTS1)
        if code:
            return code, 1
        # Stufe 2: NUTS-2 Regierungsbezirk (Köln, Düsseldorf, Oberbayern, …)
        code = _match_region_dict(label, DE_NUTS2_TO_NUTS1)
        if code:
            return code, 1
        # Stufe 3: NUTS-3 Kreis/kreisfreie Stadt (München → DE212 Level 3, etc.)
        # Wir speichern den ECHTEN NUTS-3-Code, damit Suche per Prefix
        # `nuts_code LIKE 'DE2%'` Bayern-weite Treffer inkl. Stadt-Awards liefert.
        nuts3_lookup = load_nuts3_de_lookup()
        if nuts3_lookup:
            for candidate in [label, label.split(",")[0].strip(), label.split("(")[0].strip()]:
                if candidate and candidate in nuts3_lookup:
                    return nuts3_lookup[candidate], 3
            for tok in re.split(r"[\s,;]+", label):
                tok = tok.strip().strip("-")
                if tok and tok in nuts3_lookup:
                    return nuts3_lookup[tok], 3
        # Wenn kein NUTS-3-Match: nochmal NUTS-1-Mapping nicht erneut nötig — wir fallen auf Land zurück.

    # AT: 3-Stufen-Aufloesung
    if country_iso2 == "AT":
        # Stufe 1: Bundesland-NUTS-2 / NUTS-1 (Wien, Tirol, Salzburg, ...)
        code = _match_region_dict(label, AT_REGION_TO_NUTS2)
        if code:
            level = max(0, len(code) - 2)
            # Bei NUTS-2 Treffer trotzdem zuerst pruefen, ob TAM einen
            # spezifischeren NUTS-3-Bezirk liefert (z.B. "Salzburg und
            # Umgebung" matcht erst "salzburg" → AT32, ist aber AT323).
            nuts3_lookup = load_nuts3_at_lookup()
            if nuts3_lookup:
                for candidate in [label, label.split(",")[0].strip(),
                                  label.split("(")[0].strip()]:
                    if candidate and candidate in nuts3_lookup:
                        return nuts3_lookup[candidate], 3
            return code, level
        # Stufe 2: NUTS-3 Bezirk (Linz-Wels, Oststeiermark, Waldviertel, ...)
        nuts3_lookup = load_nuts3_at_lookup()
        if nuts3_lookup:
            for candidate in [label, label.split(",")[0].strip(),
                              label.split("(")[0].strip(),
                              label.split("/")[0].strip()]:
                if candidate and candidate in nuts3_lookup:
                    return nuts3_lookup[candidate], 3
            for tok in re.split(r"[\s,;]+", label):
                tok = tok.strip().strip("-")
                if tok and tok in nuts3_lookup:
                    return nuts3_lookup[tok], 3

    # Wenn kein Land bekannt: beide Mappings testen
    if not country_iso2:
        code = _match_region_dict(label, DE_REGION_TO_NUTS1)
        if code:
            return code, 1
        code = _match_region_dict(label, DE_NUTS2_TO_NUTS1)
        if code:
            return code, 1
        code = _match_region_dict(label, AT_REGION_TO_NUTS2)
        if code:
            level = max(0, len(code) - 2)
            return code, level
        # NUTS-3-Lookups blind testen (DE-Kreise / AT-Bezirke), als letzte Stufe
        nuts3_at = load_nuts3_at_lookup()
        if nuts3_at and label in nuts3_at:
            return nuts3_at[label], 3
        nuts3_de = load_nuts3_de_lookup()
        if nuts3_de and label in nuts3_de:
            return nuts3_de[label], 3

    # Fallback: nur Land
    if country_iso2:
        return country_iso2, 0

    return None, None


def centroid_for(nuts_code: str | None) -> tuple[float, float, str] | None:
    """Liefert (lat, lon, label) fuer einen NUTS-Code; trimmt schrittweise."""
    if not nuts_code:
        return None
    centroids = load_nuts_centroids()
    code = nuts_code
    while code:
        info = centroids.get(code)
        if info and info.get("lat") and info.get("lon"):
            return float(info["lat"]), float(info["lon"]), info.get("name") or code
        if len(code) <= 2:
            break
        code = code[:-1]
    return None


# ── Fuzzy-Suche ───────────────────────────────────────────────────────────────


_ALIASES_PATH = Path(
    os.environ.get("STATE_AID_ALIASES_PATH", "/app/data/state_aid_aliases.json")
)


def _escape_like(s: str) -> str:
    """Escapet SQL-LIKE-Wildcards (% und _) damit User-Eingabe wie 'C++',
    '50%' oder 'a_b' nicht als Wildcard interpretiert wird.

    Backslash wird zuerst escapt, weil er als Escape-Zeichen verwendet wird.
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@lru_cache(maxsize=1)
def load_aliases() -> dict[str, str]:
    """Laedt das Alias-Mapping aus state_aid_aliases.json.

    Mapping: Akronym (lowercase) -> ausgeschriebene Form. Eintraege mit
    `_`-Praefix (Meta-Felder) werden ignoriert.
    """
    if not _ALIASES_PATH.exists():
        log.info("Aliases-Datei fehlt: %s — leeres Mapping verwendet.", _ALIASES_PATH)
        return {}
    try:
        with open(_ALIASES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            k.lower().strip(): str(v).strip()
            for k, v in data.items()
            if not k.startswith("_") and isinstance(v, str)
        }
    except Exception as exc:
        log.warning("Aliases konnten nicht geladen werden: %s", exc)
        return {}


def expand_alias(query: str) -> tuple[str, str | None]:
    """Liefert (effektive_query, alias_label).

    Wenn die Query (oder ihr erstes Token) ein bekannter Alias ist, wird die
    expandierte Form mit angehaengtem Original zurueckgegeben — so behaelt
    der Fuzzy-Match beide Pfade (Akronym im Identifier und Vollform im Namen).

    Beispiele:
      - 'KfW'             -> ('Kreditanstalt für Wiederaufbau KfW', 'Kreditanstalt für Wiederaufbau')
      - 'BMWK Förderung'  -> ('Bundesministerium für Wirtschaft und Klimaschutz BMWK Förderung', 'Bundesministerium ...')
      - 'Random'          -> ('Random', None)
    """
    aliases = load_aliases()
    if not aliases:
        return query.strip(), None
    q = query.strip()
    if not q:
        return q, None
    q_low = q.lower()
    # Vollstaendige Query als Alias?
    if q_low in aliases:
        full = aliases[q_low]
        return f"{full} {q}", full
    # Erstes Token als Alias? (z.B. 'BMWK Förderung')
    parts = q_low.split()
    if parts:
        first = parts[0]
        if first in aliases:
            full = aliases[first]
            return f"{full} {q}", full
    return q, None


@dataclass
class AwardHit:
    award_id: str
    score: float
    matched_field: str
    matched_value: str
    confidence: str
    via_alias: str | None = None


def _confidence(score: float) -> str:
    if score >= 97:
        return "exact"
    if score >= 90:
        return "high"
    if score >= 80:
        return "medium"
    return "low"


# ── Generische Stop-Tokens fuer Token-Coverage ────────────────────────────────
# Wenn der einzige gemeinsame Token aus dieser Liste stammt, ist das KEIN
# verlaesslicher Match — diese Woerter kommen in tausenden Firmennamen vor.
_GENERIC_TOKENS = {
    "energy", "energie", "solar", "wind", "tech", "technology", "technologie",
    "consulting", "service", "services", "industries", "industrial", "industry",
    "research", "forschung", "engineering", "logistics", "logistik",
    "chemicals", "chemie", "pharma", "medical", "medizin", "drilling",
    "training", "production", "produktion", "media", "digital",
    "health", "care", "global", "international", "european", "europa",
    "deutschland", "germany", "austria", "oesterreich",
    "drilling", "construction", "bau", "haus", "gebaeude",
    "stadt", "stadtwerke", "kreis", "land", "bund",
    "verlag", "druck", "print", "monolith",
    # Universitaets-/Hochschul-Generika werden ueblicherweise gemeinsam mit
    # Stadt-Token erwaehnt — daher hier nicht als generisch eingestuft.
}


def _smart_fuzzy_score(q_norm: str, c_norm: str) -> tuple[float, dict]:
    """Fuzzy-Score 0..100 mit Multi-Algo-Ensemble + Coverage-Penalty.

    Behebt die token_set_ratio-Schwaeche, dass schon ein einzelner gemeinsamer
    Token Score 100 liefert. Kombiniert fuenf Algorithmen mit unterschiedlichen
    Staerken und gewichtet sie je nach Token-Coverage.

    Algorithmen:
    1. **fuzz.ratio**       — Levenshtein, laengen-sensitiv
    2. **JaroWinkler**      — stark bei gemeinsamem Prefix (typische Konzern-Vorsilbe)
    3. **token_sort_ratio** — Wortreihenfolge-tolerant, laengen-sensitiv
    4. **partial_ratio**    — bester Substring-Match (gut fuer Abkuerzungen)
    5. **token_set_ratio**  — Reihenfolge/Duplikat-tolerant, aber generoes;
                              wird verworfen wenn Coverage zu niedrig oder Common-Token
                              ausschliesslich generisch (Energy, Tech, ...) ist.

    Liefert (score, debug-info) — debug-info enthaelt die einzelnen Sub-Scores
    und die Coverage-Werte fuer Transparenz.

    ``processor=None`` in allen rapidfuzz-Calls — die Strings sind bereits ueber
    ``normalize_company_name`` lower-cased und ohne Akzente; der Default-Processor
    wuerde die Strings nochmal traversieren (verschwendete Zeit).
    """
    debug: dict = {}
    if not q_norm or not c_norm:
        return 0.0, debug

    direct = float(fuzz.ratio(q_norm, c_norm, processor=None))
    sorted_r = float(fuzz.token_sort_ratio(q_norm, c_norm, processor=None))
    partial = float(fuzz.partial_ratio(q_norm, c_norm, processor=None))
    set_r = float(fuzz.token_set_ratio(q_norm, c_norm, processor=None))
    jw = float(JaroWinkler.normalized_similarity(q_norm, c_norm)) * 100.0
    debug.update({"direct": direct, "sorted": sorted_r, "partial": partial,
                  "set": set_r, "jaro_winkler": jw})

    q_tokens = set(t for t in q_norm.split() if t)
    c_tokens = set(t for t in c_norm.split() if t)
    if not q_tokens or not c_tokens:
        return max(direct, sorted_r, set_r, partial, jw), debug

    common = q_tokens & c_tokens
    q_cov = (len(common) / len(q_tokens)) if q_tokens else 0
    c_cov = (len(common) / len(c_tokens)) if c_tokens else 0
    min_cov = min(q_cov, c_cov)
    debug.update({"q_coverage": q_cov, "c_coverage": c_cov, "min_coverage": min_cov,
                  "common_tokens": sorted(common)})

    # Kein Token-Overlap → konservativ Levenshtein/Sorted (JW raus, der ist
    # bei reinem Prefix-Match generoes)
    if not common:
        return max(direct, sorted_r), debug

    # Asymmetrische Coverage:
    # q_cov hoch (>=0.7): Query ist im Wesentlichen in Candidate enthalten →
    #                     valider Abkuerzungs-/Substring-Match (z.B.
    #                     "Fraunhofer Gesellschaft" findet Langform).
    # c_cov hoch (>=0.7) bei len(c_tokens)>=2: Candidate ist substantieller
    #                     Substring der Query (z.B. "Universität Darmstadt"
    #                     in "Technische Universität Darmstadt").
    # c_cov hoch bei len(c_tokens)==1: Candidate ist Single-Token, nur dann
    #                     gueltig wenn der Token NICHT generic ist UND in der
    #                     Query ein dominanter Identifier ist.
    n_q, n_c = len(q_tokens), len(c_tokens)

    # Generic-only-Match: gemeinsame Tokens sind ausschliesslich Stop-Tokens
    only_generic = all(t in _GENERIC_TOKENS for t in common)
    if only_generic:
        debug["penalty"] = "only_generic_tokens"
        return max(direct, sorted_r), debug

    # Trivial-Single-Token-Candidate: c hat nur 1 Token, Coverage in Query
    # gering → klassischer False-Positive ("Liebig GmbH" matcht
    # "Justus-Liebig-Universitaet"). Penalty wenn q_cov < 0.5.
    if n_c == 1 and q_cov < 0.5:
        debug["penalty"] = "single_token_candidate_low_q_coverage"
        return max(direct, sorted_r), debug

    # Hohe Query-Coverage (>=0.7): die Query steckt fast vollstaendig in der
    # Candidate-Langform → Abkuerzungs-Fall, alle Algos zulassen.
    if q_cov >= 0.7:
        return max(direct, sorted_r, partial, set_r, jw), debug

    # Hohe Candidate-Coverage (>=0.7) und Candidate hat mehr als 1 Token:
    # Candidate ist substantieller Substring der Query.
    if c_cov >= 0.7 and n_c >= 2:
        return max(direct, sorted_r, partial, set_r, jw), debug

    # Sehr niedrige Coverage von beiden Seiten → konservativ.
    if min_cov < 0.34:
        debug["penalty"] = "very_low_coverage"
        return max(direct, sorted_r, jw * 0.7), debug

    # Niedrige Coverage (0.34..0.5) → moderater Penalty
    if min_cov < 0.5:
        debug["penalty"] = "low_coverage"
        return max(direct, sorted_r, jw * 0.9, min(partial * 0.85, 85.0)), debug

    # Akzeptable Coverage (>=0.5 beide Seiten) → alle Algos
    return max(direct, sorted_r, partial, set_r, jw), debug


@lru_cache(maxsize=4096)
def _smart_fuzzy_score_cached(q_norm: str, c_norm: str) -> tuple[float, tuple]:
    """Cache-faehige Variante von ``_smart_fuzzy_score`` mit hashbarem Rueckgabewert.

    LRU-Cache deckt wiederholte Audit-Reports / Suchen mit identischen Queries
    ab (z.B. wenn das Frontend die gleiche Eingabe mehrfach sendet). Das
    Debug-Dict wird in ein Tuple aus (key, value)-Paaren umgewandelt, damit
    der Wert hashable bleibt.

    Cache-Groesse 4096 ist bewusst moderat — bei einer Audit-Session mit
    typischerweise 50-200 unterschiedlichen Queries auf max. 200 Top-K-Kandidaten
    pro Query reicht das fuer 100% Hit-Rate beim Wiederlauf. Memory-Footprint
    bleibt unter 1 MB.
    """
    score, debug = _smart_fuzzy_score(q_norm, c_norm)
    # Sortierte Tuple-Repraesentation — common_tokens-Listen werden zum Tuple
    # umgewandelt, damit das Ergebnis hashable ist.
    debug_tuple: tuple = tuple(
        sorted(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in debug.items()
        )
    )
    return score, debug_tuple


# Kandidaten-Cap fuer den SQL-Vorfilter (vor dem Top-K-Cutoff in Python).
# 500 ist grosszuegig genug, um auch Fraunhofer-aehnliche Massenmatches
# abzudecken, und klein genug fuer schnelles cdist-Pre-Ranking.
_FUZZY_SQL_LIMIT = 500
# Top-K-Cutoff fuer das Smart-Score-Ensemble. Statt alle 500 Kandidaten durch
# die 5 Algorithmen zu jagen, nehmen wir nur die 200 besten nach
# pg_trgm-Similarity bzw. token_set_ratio. Das spart 60 % Smart-Score-Calls.
_FUZZY_SMART_TOPK = 200


def _looks_like_identifier(q: str) -> bool:
    """True wenn die Query eher ein Identifier-Code als ein Firmenname ist.

    Heuristik:
    - Enthaelt mindestens eine Ziffer (z.B. ``HRB 12345``, ``DE-2023-001``).
    - Oder ist kurz (<= 8 Zeichen) und ein reines Akronym ohne Whitespace
      (z.B. ``ABER``, ``KUR``, ``IdNr``).

    Vermeidet teure ILIKE-Seq-Scans auf der ``beneficiary_identifier``-Spalte
    fuer typische Firmen-/Behoerden-Queries (``Fraunhofer``, ``Siemens AG``).
    """
    if not q:
        return False
    q = q.strip()
    if not q:
        return False
    # Enthaelt Ziffern → wahrscheinlicher Identifier-Code
    if any(ch.isdigit() for ch in q):
        return True
    # Kurzes Akronym ohne Whitespace (max 8 Zeichen)
    if len(q) <= 8 and " " not in q:
        return True
    return False


# Sehr haeufige deutsche Stoppwoerter, die in firmennamen oft vorkommen aber
# fuer den SQL-Vorfilter NICHT distinktiv sind. Wenn diese in der OR-Liste
# sind, gibt der Planner den Trgm-Index auf und faellt auf einen Bitmap Heap
# Scan ueber den country-Index zurueck — ~50 ms statt 2 ms. Wir entfernen sie
# aus dem SQL-Filter, behalten sie aber im q_norm fuer die Smart-Score-Phase.
_SQL_STOP_TOKENS = {
    "der", "die", "das", "den", "dem", "des",
    "und", "oder", "fuer", "mit", "von", "vom", "zur", "zum",
    "the", "and", "for", "with", "of",
    "ev", "eg", "kg", "ag", "co",
}


def _select_sql_tokens(tokens: list[str], *, max_tokens: int = 4) -> list[str]:
    """Waehlt die distinktivsten Tokens fuer den SQL-Vorfilter aus.

    - Stoppwoerter (``_SQL_STOP_TOKENS``) raus.
    - Ueber die laengsten Tokens praeferieren (laengere Tokens sind in der
      Regel selektiver — der Trgm-Index liefert deutlich weniger Bitmap-
      Treffer pro langem Token).
    - Maximal ``max_tokens`` zurueckliefern, damit die OR-Liste den Planner
      nicht zwingt, den Trgm-Index aufzugeben.

    Beispiele:
    - ``['fraunhofer', 'gesellschaft', 'zur', 'foerderung', 'der']`` →
      ``['fraunhofer', 'foerderung', 'gesellschaft']`` (zur/der raus, Top 3).
    - ``['siemens']`` → ``['siemens']`` (unveraendert).
    """
    if not tokens:
        return []
    # Stoppwoerter raus, Duplikate raus, leere Tokens raus
    unique = []
    seen: set[str] = set()
    for t in tokens:
        if not t or t in seen or t in _SQL_STOP_TOKENS:
            continue
        seen.add(t)
        unique.append(t)
    if not unique:
        # Komplett aus Stoppwoertern bestehende Query — wir brauchen wenigstens
        # einen Token, sonst haben wir keine Filterung.
        unique = [tokens[0]]
    # Nach Laenge sortieren (laengste zuerst), Top-N waehlen.
    unique.sort(key=len, reverse=True)
    return unique[:max_tokens]


def _collect_fuzzy_candidates(
    db: Session,
    *,
    q_norm: str,
    original_query: str,
    tokens: list[str],
    country_code: str | None,
    location_hint_clean: str,
):
    """SQL-Vorfilter fuer ``fuzzy_match_company``.

    Liefert eine Liste von Row-Objekten mit den Spalten
    (id, beneficiary_name, beneficiary_name_normalized, beneficiary_identifier,
    nuts_code, nuts_label, sim).

    Strategie (wichtig fuer Performance — vermeidet Seq Scan auf 170k Rows):

    1. **Hauptquery** uebernimmt NUR Filter, die den GIN-Trgm-Index nutzen:
       ILIKE/Trigram auf ``beneficiary_name_normalized``. So bekommen wir
       garantiert einen Bitmap Index Scan statt einer Sequential Scan.
    2. **Identifier-Match und NUTS-Label-Match** laufen in **separaten**
       Mini-Queries und werden zum Hauptergebnis gemerged. Beide sind selektiv
       und treffen jeweils maximal ~50 Records — der Overhead ist klein.
       (Die Alternative — identifier ILIKE in den OR-Block der Hauptquery —
       defeats den GIN-Trgm-Index und triggert eine Seq Scan, ~5x langsamer.)
    3. **Pre-Ranking via similarity()-Spalte**: Postgres berechnet die
       Trigram-Similarity zu ``q_norm`` und sortiert nach DESC. Wir holen
       nur die Top 500 — der Top-K-Cutoff im Python-Code reduziert das auf 200.

    Vorteile gegenueber dem alten Schema:
    - SQL-Pre-Ranking erspart Top-K-Sortierung in Python.
    - Index-Friendly: der GIN-Trgm-Index wird voll genutzt (Bitmap Index Scan).
    """
    if not q_norm:
        return []

    # Hauptquery — NUR Filter auf beneficiary_name_normalized, damit der
    # GIN-Trgm-Index als Bitmap Index Scan greift. Identifier und NUTS-Label
    # kommen weiter unten in separaten Queries.
    primary_q = db.query(
        StateAidAward.id,
        StateAidAward.beneficiary_name,
        StateAidAward.beneficiary_name_normalized,
        StateAidAward.beneficiary_identifier,
        StateAidAward.nuts_code,
        StateAidAward.nuts_label,
        sql_func.similarity(
            StateAidAward.beneficiary_name_normalized,
            q_norm,
        ).label("sim"),
    )
    if country_code:
        primary_q = primary_q.filter(
            StateAidAward.country_code == country_code,
        )

    ors = [
        StateAidAward.beneficiary_name_normalized.ilike(
            f"%{_escape_like(tok)}%", escape="\\",
        )
        for tok in tokens
    ]
    if ors:
        primary_q = primary_q.filter(or_(*ors))

    # SQL-seitig nach Trigram-Similarity sortieren — Top 500 reichen, das
    # token_set_ratio-cdist-Pre-Ranking macht den finalen Cutoff.
    primary_q = primary_q.order_by(
        sql_func.similarity(
            StateAidAward.beneficiary_name_normalized,
            q_norm,
        ).desc(),
    ).limit(_FUZZY_SQL_LIMIT)

    rows = primary_q.all()
    seen_ids: set[str] = {r.id for r in rows}

    # Identifier-Match: nur ausgefuehrt, wenn die Query identifier-LIKE aussieht
    # (kurze alphanumerische Codes mit Ziffern oder reine Akronyme/Labels) —
    # sonst ist die ILIKE-Suche auf einer Spalte OHNE Trgm-Index ein Seq Scan
    # ueber 170k Rows (~45ms) und damit der groesste Performance-Killer der
    # Funktion. In der Realitaet sind die TAM-Identifier ohnehin nur Labels
    # wie "Handelsregisternummer" oder "Firmenbuchnummer" — Treffer sind nur
    # zu erwarten, wenn die Query selbst ein solcher Code ist.
    q_strip = original_query.strip()
    if _looks_like_identifier(q_strip):
        ident_q = db.query(
            StateAidAward.id,
            StateAidAward.beneficiary_name,
            StateAidAward.beneficiary_name_normalized,
            StateAidAward.beneficiary_identifier,
            StateAidAward.nuts_code,
            StateAidAward.nuts_label,
            sql_func.similarity(
                StateAidAward.beneficiary_name_normalized,
                q_norm,
            ).label("sim"),
        )
        if country_code:
            ident_q = ident_q.filter(
                StateAidAward.country_code == country_code,
            )
        ident_q = ident_q.filter(
            StateAidAward.beneficiary_identifier.ilike(
                f"%{_escape_like(q_strip)}%", escape="\\",
            ),
        ).limit(50)
        for r in ident_q.all():
            if r.id not in seen_ids:
                rows.append(r)
                seen_ids.add(r.id)

    # NUTS-Label-Hint: ebenfalls eigene Mini-Query.
    if location_hint_clean:
        hint_q = db.query(
            StateAidAward.id,
            StateAidAward.beneficiary_name,
            StateAidAward.beneficiary_name_normalized,
            StateAidAward.beneficiary_identifier,
            StateAidAward.nuts_code,
            StateAidAward.nuts_label,
            sql_func.similarity(
                StateAidAward.beneficiary_name_normalized,
                q_norm,
            ).label("sim"),
        )
        if country_code:
            hint_q = hint_q.filter(
                StateAidAward.country_code == country_code,
            )
        hint_q = hint_q.filter(
            StateAidAward.nuts_label.ilike(
                f"%{_escape_like(location_hint_clean)}%", escape="\\",
            ),
        ).limit(200)
        for r in hint_q.all():
            if r.id not in seen_ids:
                rows.append(r)
                seen_ids.add(r.id)

    return rows


def fuzzy_match_company(db: Session, query: str, *, limit: int = 50,
                       min_score: float = 65.0,
                       country_code: str | None = None,
                       location_hint: str | None = None) -> list[AwardHit]:
    """Plan §7 — Fuzzy-Treffer ueber `beneficiary_name_normalized`.

    Strategie (Performance-optimierte Variante, Ziel: ~25ms statt ~200ms):

    1. **Alias-Expansion** (Akronym → Vollform), siehe ``expand_alias()``.
    2. **SQL-Vorfilter mit pg_trgm-Similarity-Pre-Ranking**:
       Statt OR-ILIKE-pro-Token greifen wir direkt auf den pg_trgm-GIN-Index
       (``ix_state_aid_name_trgm``) zu und lassen Postgres bereits nach
       Similarity sortieren. Daraus kommen TOP 500 Kandidaten — unabhaengig
       davon, wie viele Tokens die Query hat. Fuer kurze Queries (< 3 Zeichen)
       und im Edge-Fall (zu wenige Trgm-Treffer) faellt die Funktion auf das
       alte OR-ILIKE-Schema zurueck — Recall hat Vorrang.
    3. **rapidfuzz ``process.cdist``-Pre-Ranking**: token_set_ratio fuer alle
       SQL-Kandidaten in einem einzigen C-Call (Batch-Distanzmatrix). Daraus
       kommen TOP 200 Kandidaten — ein Cutoff, der typischerweise 60 % der
       Smart-Score-Aufrufe spart, ohne den Endscore zu veraendern.
    4. **Smart-Score-Ensemble (gecached)** auf TOP 200: 5-Algo-Ensemble mit
       Coverage-Penalty und LRU-Cache. Die Cache-Hit-Rate ist hoch, sobald
       Audit-Reports identische Queries wiederholen.
    5. **Identifier-Bonus + Location-Hint-Boost** auf das finale Best-Dict.

    ``location_hint`` (Polish-Runde 3, Aufgabe 2): wenn gesetzt, wird das
    Kandidaten-Set zusaetzlich auf Records erweitert, deren ``nuts_label``
    den Hint enthaelt. Im Score-Postprocessing wird Boost (+5) fuer
    Records mit passendem Label gegeben und Penalty (-5) fuer Records mit
    explizit anderem NUTS-3-Prefix.
    """
    # Alias-Expansion: 'KfW' -> 'Kreditanstalt für Wiederaufbau KfW'
    effective_query, alias_label = expand_alias(query)
    q_norm = normalize_company_name(effective_query)
    if not q_norm:
        return []

    location_hint_clean = (location_hint or "").strip()
    raw_tokens = [t for t in q_norm.split() if len(t) >= 3]
    # Nur die distinktivsten Tokens (max 4, Stoppwoerter raus) gehen in den
    # SQL-Vorfilter — sonst gibt der Planner den Trgm-Index auf. Die volle
    # q_norm bleibt fuer das Similarity-Ranking und Smart-Score erhalten.
    sql_tokens = _select_sql_tokens(raw_tokens)

    rows = _collect_fuzzy_candidates(
        db,
        q_norm=q_norm,
        original_query=query,
        tokens=sql_tokens,
        country_code=country_code,
        location_hint_clean=location_hint_clean,
    )

    if not rows:
        return []

    choices = [(r.id, r.beneficiary_name_normalized or "") for r in rows]
    norm_strings = [c[1] for c in choices]
    # NUTS-Daten pro Award vorhalten — fuer Boost/Penalty.
    nuts_by_id: dict[str, tuple[str | None, str | None]] = {
        r.id: (r.nuts_code, r.nuts_label) for r in rows
    }

    # Top-K-Cutoff via rapidfuzz process.cdist — ein einziger C-Call statt
    # N Python-Aufrufe an _smart_fuzzy_score. token_set_ratio ist hier der
    # Vorfilter; den finalen Score liefert _smart_fuzzy_score_cached.
    #
    # ``processor=None`` ueberall — die Strings sind bereits ueber
    # normalize_company_name lower-cased und ohne Akzente; das spart
    # unnoetige Traversierungen.
    score_cutoff = max(50.0, min_score - 20)
    candidate_indices: list[int]
    candidate_pre_scores: list[float]
    if len(norm_strings) <= _FUZZY_SMART_TOPK:
        # Kleiner Kandidatensatz — kein Cutoff noetig, aber wir laufen trotzdem
        # cdist, damit der Code-Pfad einheitlich ist.
        candidate_indices = list(range(len(norm_strings)))
        candidate_pre_scores = [
            float(s)
            for s in process.cdist(
                [q_norm], norm_strings,
                scorer=fuzz.token_set_ratio, processor=None,
            )[0]
        ]
    else:
        # Top-K: Pre-Ranking via cdist (Batch-Distanzmatrix), dann sort+slice.
        pre_scores = process.cdist(
            [q_norm], norm_strings,
            scorer=fuzz.token_set_ratio, processor=None,
            score_cutoff=score_cutoff,
        )[0]
        # Sortierte Indices nach Score absteigend, nur Top-K
        # numpy.argsort liefert sortiert aufsteigend → reverse via [::-1]
        order = pre_scores.argsort()[::-1][:_FUZZY_SMART_TOPK]
        candidate_indices = [int(i) for i in order]
        candidate_pre_scores = [float(pre_scores[i]) for i in candidate_indices]

    best: dict[str, tuple[float, str, str]] = {}
    for idx, pre_score in zip(candidate_indices, candidate_pre_scores):
        if pre_score < score_cutoff:
            continue
        award_id, value = choices[idx]
        if not value:
            continue
        # Smart-Score mit Coverage-Penalty (Multi-Algo-Ensemble), gecached.
        smart, _debug = _smart_fuzzy_score_cached(q_norm, value)
        if smart < min_score:
            continue
        cur = best.get(award_id)
        if cur is None or smart > cur[0]:
            best[award_id] = (smart, "name", value)

    # Identifier-Match boosten
    q_strip = query.strip().casefold()
    if q_strip:
        for r in rows:
            ident = (r.beneficiary_identifier or "").casefold()
            if ident and q_strip in ident:
                cur = best.get(r.id)
                score = 95.0 if q_strip == ident else 88.0
                if cur is None or score > cur[0]:
                    best[r.id] = (score, "identifier", r.beneficiary_identifier or "")

    # Location-Hint: Boost (+5) / Penalty (-5) als kleines Ranking-Tiebreaker.
    # Wir leiten den NUTS-3-Prefix ab, falls der Hint einer Stadt/Region
    # zuordenbar ist — sonst nur Label-Match. Boost/Penalty sind absichtlich
    # klein, damit der Match-Charakter (Name-Aehnlichkeit) dominant bleibt.
    if location_hint_clean and best:
        hint_low = location_hint_clean.casefold()
        # NUTS-Prefix aus dem Hint ableiten (Stadt/Bundesland/Region).
        hint_nuts_prefix3 = _location_hint_to_nuts_prefix(hint_low)
        for award_id, (score, field, val) in list(best.items()):
            nuts_code, nuts_label = nuts_by_id.get(award_id, (None, None))
            label_low = (nuts_label or "").casefold()
            code = (nuts_code or "").upper()
            boosted = float(score)
            if hint_low and label_low and hint_low in label_low:
                boosted = min(100.0, boosted + 5.0)
            elif hint_nuts_prefix3 and code and not code.startswith(
                hint_nuts_prefix3,
            ):
                boosted = max(0.0, boosted - 5.0)
            if boosted != score:
                best[award_id] = (boosted, field, val)

    hits = [
        AwardHit(award_id=aid, score=round(float(score), 1),
                 matched_field=field, matched_value=val,
                 confidence=_confidence(score),
                 via_alias=alias_label)
        for aid, (score, field, val) in best.items()
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def _location_hint_to_nuts_prefix(hint_low: str) -> str | None:
    """Versucht, einen Location-Hint auf einen 3-stelligen NUTS-Prefix
    abzubilden.

    Strategie:
    1. Direkter Lookup in den DE-/AT-Bundeslaender-Mappings.
    2. Direkter Lookup in den DE-Regierungsbezirken (NUTS-2 → NUTS-1).
    3. Fallback: keine Zuordnung — None.
    """
    if not hint_low:
        return None
    # Bundesland exakt
    if hint_low in DE_REGION_TO_NUTS1:
        return DE_REGION_TO_NUTS1[hint_low][:3]
    if hint_low in AT_REGION_TO_NUTS2:
        return AT_REGION_TO_NUTS2[hint_low][:3]
    if hint_low in DE_NUTS2_TO_NUTS1:
        return DE_NUTS2_TO_NUTS1[hint_low][:3]
    # Strip Plural / Suffix-Whitespace
    stripped = hint_low.strip().strip(",").strip()
    if stripped != hint_low:
        return _location_hint_to_nuts_prefix(stripped)
    return None


# ── Karten-Aggregation ────────────────────────────────────────────────────────


def aggregate_for_map(db: Session, *,
                     country_code: str | None = None,
                     since: date | None = None,
                     until: date | None = None,
                     level: int = 1) -> dict:
    """Plan §8 — Aggregation pro NUTS-Code.

    `level=1` (Default): NUTS-3-Codes wie DE212 werden auf NUTS-1 (DE2)
    zurueckgerollt — sonst haetten wir 401 Punkte. NUTS-2 (level=2) und
    NUTS-3 (level=3) sind als Optionen vorgesehen.
    """
    target_prefix = max(2, min(5, 2 + level))  # 0->2, 1->3, 2->4, 3->5
    rolled_code_col = sql_func.substr(StateAidAward.nuts_code, 1, target_prefix)
    q = db.query(
        rolled_code_col.label("nuts_code"),
        sql_func.count(StateAidAward.id).label("count"),
        sql_func.sum(StateAidAward.aid_amount_eur).label("total_eur"),
        sql_func.max(StateAidAward.country_code).label("country_code"),
        sql_func.max(StateAidAward.nuts_level).label("max_level"),
    )
    if country_code:
        q = q.filter(StateAidAward.country_code == country_code)
    if since:
        q = q.filter(StateAidAward.granting_date >= since)
    if until:
        q = q.filter(StateAidAward.granting_date <= until)
    q = q.group_by(rolled_code_col)

    points: list[dict] = []
    unmappable = 0
    total_records = 0
    levels: dict[int, int] = {}

    # Per-Level-Counter für die Datenqualitaets-Anzeige (echte Granularitaet
    # der gespeicherten Records, nicht das Aggregations-Level).
    level_q = db.query(
        StateAidAward.nuts_level,
        sql_func.count(StateAidAward.id).label("count"),
    )
    if country_code:
        level_q = level_q.filter(StateAidAward.country_code == country_code)
    if since:
        level_q = level_q.filter(StateAidAward.granting_date >= since)
    if until:
        level_q = level_q.filter(StateAidAward.granting_date <= until)
    level_q = level_q.group_by(StateAidAward.nuts_level)
    for row in level_q.all():
        if row.nuts_level is not None:
            levels[int(row.nuts_level)] = int(row.count or 0)

    for row in q.all():
        cnt = int(row.count or 0)
        total_records += cnt
        centroid = centroid_for(row.nuts_code) if row.nuts_code else None
        if not centroid:
            unmappable += cnt
            continue
        lat, lon, label = centroid
        points.append({
            "nuts_code": row.nuts_code,
            "nuts_label": label,
            "nuts_level": level,
            "country_code": row.country_code,
            "lat": lat,
            "lon": lon,
            "count": cnt,
            "total_eur": float(row.total_eur) if row.total_eur is not None else None,
        })

    return {
        "points": points,
        "total_records": total_records,
        "unmappable": unmappable,
        "by_level": levels,
        "filters": {
            "country_code": country_code,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "aggregate_level": level,
        },
    }


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────


def normalize_country_code(country_value: str | None) -> tuple[str | None, str | None]:
    """Beliebige TAM-/ISO-Eingabe → (ISO-2, Anzeigename).

    Akzeptiert ISO-2, ISO-3, deutschen Namen, englischen Namen und gaengige
    Synonyme (z.B. "Czechia" / "Czech Republic"). TAM liefert auf Englisch.
    """
    if not country_value:
        return None, None
    c = country_value.strip().upper()
    if len(c) == 3 and c in ISO3_TO_ISO2:
        c2 = ISO3_TO_ISO2[c]
        return c2, ISO2_TO_NAME.get(c2, country_value)
    if len(c) == 2:
        return c, ISO2_TO_NAME.get(c, country_value)
    # Fallback: Name (DE, EN, andere Sprachen)
    name_lower = country_value.strip().lower()
    if name_lower in NAME_TO_ISO2:
        code = NAME_TO_ISO2[name_lower]
        return code, ISO2_TO_NAME.get(code, country_value)
    for code, n in ISO2_TO_NAME.items():
        if n.lower() == name_lower:
            return code, n
    return None, country_value
