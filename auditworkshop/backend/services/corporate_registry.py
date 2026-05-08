"""
flowworkshop · services/corporate_registry.py

Konzernverbund-Lookup ueber kostenlose, oeffentliche APIs.

Plan: Audit-Report soll fuer "Siemens AG" auch alle Toechter mitfinden.
Datenstand pro Lookup wird transparent dokumentiert (pro Eintrag das
`lastUpdateDate` der Quelle, plus unser eigener Cache-Zeitstempel).

Quellen:
  1. GLEIF Public API  (https://api.gleif.org/api/v1/) — komplett kostenlos,
     offizielle LEI-Codes. Hierarchie-Endpoints fuer direct-/ultimate-parent
     und direct-/ultimate-children.
  2. Wikidata SPARQL    (https://query.wikidata.org/sparql) — komplett
     kostenlos, fair-use. Properties P127 (owned by), P749 (parent
     organization), P355 (subsidiary).

Architektur:
  * Synchron, mit `httpx` (existiert bereits im Projekt). Aufgerufen via
    `asyncio.to_thread` aus FastAPI-Endpoints, damit der Event-Loop nicht
    blockiert.
  * Pro API-Call max. 10 Sekunden Timeout, gesamter Lookup max. 30 Sek.
  * Graceful Degradation: faellt eine Quelle aus, liefert die andere allein.
  * Rate-Limiting: GLEIF mit `time.sleep(0.2)` pro Request.

WICHTIG (Datenschutz):
  * Konzernhierarchien sind ueber LEI-/Wikidata-Public-Data nicht-personen-
    bezogen — der Cache ist daher unbedenklich.
  * Mittelstaendische Strukturen ohne LEI fehlen gegebenenfalls. Das wird im
    `coverage_note` jedes Lookups ausgewiesen.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx

log = logging.getLogger(__name__)


# ── Konstanten ────────────────────────────────────────────────────────────────

GLEIF_BASE = "https://api.gleif.org/api/v1"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

DEFAULT_USER_AGENT = (
    "FlowWorkshopAuditworkshop/1.0 (https://workshop.flowaudit.de) corporate-registry"
)

GLEIF_RATE_LIMIT_S = 0.2     # ~5 Requests/sec, in der Praxis problemlos
PER_CALL_TIMEOUT_S = 10.0
DEFAULT_TOTAL_TIMEOUT_S = 30.0
DEFAULT_MAX_CHILDREN = 200

CACHE_TTL_DAYS = 7

# Common legal-form Suffixe — werden bei der Normalisierung der Query
# entfernt, um Schreibvarianten zu vereinen.
_LEGAL_SUFFIXES = (
    "ag", "se", "kgaa", "gmbh", "mbh", "ohg", "kg", "gbr",
    "co. kg", "co kg", "ug", "e.v.", "ev",
    "limited", "ltd", "ltd.", "plc", "inc", "inc.", "corp", "corp.",
    "n.v.", "nv", "b.v.", "bv", "s.a.", "sa", "s.a.s.", "sas",
    "s.r.l.", "srl", "s.p.a.", "spa", "s.l.", "sl",
    "holding", "holdings", "group",
)

# Normalisierungs-Regex
_WS_RE = re.compile(r"\s+")
_NONWORD_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)


# ── Datenklassen ──────────────────────────────────────────────────────────────


@dataclass
class CorporateEntity:
    """Eine einzelne Firma (Mutter, Tochter oder die Anker-Entity)."""
    name: str
    legal_form: str | None = None
    country: str | None = None
    lei: str | None = None              # Legal Entity Identifier
    wikidata_id: str | None = None      # Q-ID (z.B. 'Q9601')
    address: str | None = None
    source: Literal["gleif", "wikidata", "manual"] = "gleif"
    source_url: str = ""                # zur Verifikation
    data_freshness: datetime | None = None   # WANN bei der Quelle aktualisiert
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "legal_form": self.legal_form,
            "country": self.country,
            "lei": self.lei,
            "wikidata_id": self.wikidata_id,
            "address": self.address,
            "source": self.source,
            "source_url": self.source_url,
            "data_freshness": (
                self.data_freshness.isoformat() if self.data_freshness else None
            ),
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


@dataclass
class CorporateGroup:
    """Eine Konzern-Hierarchie ausgehend von einem Suchbegriff."""
    query: str
    primary_entity: CorporateEntity | None = None
    ultimate_parent: CorporateEntity | None = None
    direct_parent: CorporateEntity | None = None
    children: list[CorporateEntity] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    coverage_note: str = ""
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "primary_entity": (
                self.primary_entity.to_dict() if self.primary_entity else None
            ),
            "ultimate_parent": (
                self.ultimate_parent.to_dict() if self.ultimate_parent else None
            ),
            "direct_parent": (
                self.direct_parent.to_dict() if self.direct_parent else None
            ),
            "children": [c.to_dict() for c in self.children],
            "children_count": len(self.children),
            "sources_used": list(self.sources_used),
            "coverage_note": self.coverage_note,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


# ── Helfer ────────────────────────────────────────────────────────────────────


def _normalize_query(name: str) -> str:
    """Normalisiert einen Firmennamen fuer Cache-Key + Deduplikation.

    Lowercase, Sonderzeichen weg, Mehrfach-Whitespace reduziert. Wir entfernen
    HIER die Suffixe NICHT — der Cache-Key spiegelt die User-Eingabe wider.
    """
    if not name:
        return ""
    s = name.strip().lower()
    s = _NONWORD_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _strip_legal_form(name: str) -> str:
    """Entfernt typische Rechtsform-Suffixe — fuer Alias-Erzeugung."""
    if not name:
        return ""
    parts = name.strip().split()
    while parts and parts[-1].lower().strip(",.;:") in _LEGAL_SUFFIXES:
        parts.pop()
    # Und ggf. ein Trailing Komma
    return " ".join(parts).strip(" ,;.:")


def search_with_aliases(name: str) -> list[str]:
    """Erzeugt Schreibvarianten (mit/ohne 'AG', 'GmbH', '-Holding').

    GLEIF-Filter ist strikter als erwartet — daher mehrere Varianten
    ausprobieren. Die Reihenfolge ist absichtlich von "spezifisch zu allgemein".
    """
    if not name:
        return []
    base = name.strip()
    aliases: list[str] = [base]
    no_legal = _strip_legal_form(base)
    if no_legal and no_legal != base:
        aliases.append(no_legal)
    # Bindestrich-Variante (z.B. "Fraunhofer-Gesellschaft" -> "Fraunhofer Gesellschaft")
    if "-" in no_legal:
        aliases.append(no_legal.replace("-", " "))
    if "-" in base:
        aliases.append(base.replace("-", " "))
    # Erste Tokens (oft genuegt der Konzernname allein)
    first_token = no_legal.split()[0] if no_legal else ""
    if first_token and len(first_token) >= 4 and first_token not in aliases:
        aliases.append(first_token)
    # Holding-Variante
    if "holding" in base.lower() and base not in aliases:
        aliases.append(base.lower().replace("holding", "").strip())
    # Dedup unter Beibehaltung der Reihenfolge
    seen: set[str] = set()
    out: list[str] = []
    for a in aliases:
        key = a.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(a.strip())
    return out


def _parse_iso_dt(value: Any) -> datetime | None:
    """Liest ein ISO-Datum/Datetime — toleriert 'Z' am Ende und None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# ── GLEIF ─────────────────────────────────────────────────────────────────────


class _GleifClient:
    """Duenner httpx-Wrapper mit Rate-Limit. Kein Singleton — pro Lookup neu."""

    def __init__(self, *, timeout: float = PER_CALL_TIMEOUT_S):
        self.client = httpx.Client(
            base_url=GLEIF_BASE,
            timeout=timeout,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/vnd.api+json",
            },
        )
        self._last_call: float = 0.0

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass

    def _wait(self) -> None:
        delta = time.monotonic() - self._last_call
        if delta < GLEIF_RATE_LIMIT_S:
            time.sleep(GLEIF_RATE_LIMIT_S - delta)

    def get(self, path: str, params: dict | None = None) -> dict | None:
        """GET mit Rate-Limit. Liefert das geparste JSON, sonst None bei Fehler."""
        self._wait()
        try:
            r = self.client.get(path, params=params or {})
            self._last_call = time.monotonic()
        except httpx.RequestError as exc:
            log.warning("GLEIF Request-Fehler %s: %s", path, exc)
            return None
        if r.status_code == 404:
            return None  # legitim — z.B. keine direct-parent
        if r.status_code >= 400:
            log.warning("GLEIF HTTP %d auf %s", r.status_code, path)
            return None
        try:
            return r.json()
        except ValueError:
            log.warning("GLEIF lieferte kein JSON auf %s", path)
            return None


def _gleif_entity_from_record(rec: dict) -> CorporateEntity | None:
    """Extrahiert eine CorporateEntity aus einem GLEIF lei-record."""
    if not isinstance(rec, dict):
        return None
    attrs = rec.get("attributes") or {}
    entity = attrs.get("entity") or {}
    legal_name = (entity.get("legalName") or {}).get("name") or ""
    if not legal_name:
        # Fallback: erste Other-Name
        other_names = entity.get("otherNames") or []
        if other_names and isinstance(other_names, list):
            legal_name = (other_names[0] or {}).get("name") or ""
    legal_form_obj = entity.get("legalForm") or {}
    legal_form = (
        legal_form_obj.get("id")
        or legal_form_obj.get("other")
        or None
    )
    legal_addr = entity.get("legalAddress") or {}
    country = legal_addr.get("country")
    parts = []
    for k in ("addressLines", "city", "region", "postalCode"):
        v = legal_addr.get(k)
        if isinstance(v, list):
            parts.extend([str(x) for x in v if x])
        elif v:
            parts.append(str(v))
    address = ", ".join(parts) if parts else None

    # `lastUpdateDate` liegt unter `attributes.registration` (das ist das
    # Datum der letzten LEI-Registrierungs-Aktualisierung). Manche aeltere
    # Bestaende fuehren das Feld zusaetzlich auf `attributes`-Ebene — wir
    # fallen entsprechend zurueck.
    registration = attrs.get("registration") or {}
    last_update = (
        _parse_iso_dt(registration.get("lastUpdateDate"))
        or _parse_iso_dt(attrs.get("lastUpdateDate"))
    )
    lei = rec.get("id") or attrs.get("lei")

    return CorporateEntity(
        name=legal_name or "(unbekannt)",
        legal_form=legal_form,
        country=country,
        lei=lei,
        wikidata_id=None,
        address=address,
        source="gleif",
        source_url=(
            f"https://search.gleif.org/#/record/{lei}" if lei else GLEIF_BASE
        ),
        data_freshness=last_update,
    )


def _gleif_search_lei(client: _GleifClient, query: str) -> CorporateEntity | None:
    """Sucht via legalName-Filter den passenden LEI-Record.

    Strategie: zuerst exakte legalName-Suche (eng, sehr praezise) — wenn das
    keinen Treffer liefert, fallback auf Fulltext-Suche mit groesserem
    Result-Set und Score-basierter Auswahl.

    Wir probieren mehrere Alias-Schreibweisen pro Strategie.
    """
    # 1) Exakte legalName-Suche pro Alias (sehr praezise)
    for alias in search_with_aliases(query):
        norm_q = _normalize_query(alias)
        params = {
            "filter[entity.legalName]": alias,
            "page[size]": 10,
        }
        resp = client.get("/lei-records", params=params)
        data = (resp or {}).get("data") or []
        if not data:
            continue
        # Bei legalName-Filter sind Treffer schon sehr eng; wir picken den
        # ACTIVE-Eintrag mit der kuerzesten/passendsten Normalform.
        best = None
        best_score = -1
        for rec in data:
            ent = _gleif_entity_from_record(rec)
            if not ent or not ent.name:
                continue
            n = _normalize_query(ent.name)
            score = 50
            if n == norm_q:
                score = 100
            elif norm_q and norm_q in n:
                # Weniger Bonus, damit "Wohlfahrtsfonds Siemens" nicht
                # ueber "Siemens AG" gewinnt.
                score = 75
            elif n and n in norm_q:
                score = 70
            attrs = rec.get("attributes") or {}
            entity = attrs.get("entity") or {}
            if entity.get("status") == "ACTIVE":
                score += 10
            # Bonus fuer Headquarter / minimum-name-length-match (kuerzerer
            # legaler Name ist oft die "echte" Konzernspitze).
            if n and norm_q:
                length_diff = abs(len(n) - len(norm_q))
                score -= min(20, length_diff)
            if score > best_score:
                best_score = score
                best = ent
        if best is not None and best_score >= 80:
            return best

    # 2) Fulltext-Fallback (toleranter, fuer Aliase ohne exakten legalName)
    for alias in search_with_aliases(query):
        params = {
            "filter[fulltext]": alias,
            "page[size]": 10,
        }
        resp = client.get("/lei-records", params=params)
        data = (resp or {}).get("data") or []
        if not data:
            continue
        norm_q = _normalize_query(alias)
        best = None
        best_score = -1
        for rec in data:
            ent = _gleif_entity_from_record(rec)
            if not ent or not ent.name:
                continue
            n = _normalize_query(ent.name)
            score = 0
            if n == norm_q:
                score = 100
            elif norm_q and norm_q in n:
                # Haengt extrem stark von der Laengen-Differenz ab —
                # "siemens ag" in "wohlfahrtsfonds siemens ag" matcht
                # numerisch, ist aber semantisch nicht das richtige.
                score = 60
                length_diff = abs(len(n) - len(norm_q))
                score -= min(40, length_diff // 2)
            elif n and n in norm_q:
                score = 70
            else:
                score = 30
            attrs = rec.get("attributes") or {}
            entity = attrs.get("entity") or {}
            if entity.get("status") == "ACTIVE":
                score += 10
            if score > best_score:
                best_score = score
                best = ent
        if best is not None and best_score >= 50:
            return best
    return None


def _gleif_fetch_relation(
    client: _GleifClient, lei: str, relation: str,
) -> list[CorporateEntity]:
    """Holt eine Relation (direct-parent / ultimate-parent / direct-children
    / ultimate-children) und liefert eine Liste CorporateEntity.

    Behandelt sowohl Single- als auch List-Antworten transparent.
    """
    if not lei or not relation:
        return []
    path = f"/lei-records/{lei}/{relation}"
    out: list[CorporateEntity] = []
    seen_leis: set[str] = set()
    # Pagination — die Children-Endpoints liefern bis zu 200 pro Seite.
    page = 1
    while True:
        params = {"page[size]": 200, "page[number]": page}
        resp = client.get(path, params=params)
        if not resp:
            break
        data = resp.get("data")
        if data is None:
            break
        # Single record (parent) vs list (children)
        if isinstance(data, dict):
            ent = _gleif_entity_from_record(data)
            if ent and ent.lei not in seen_leis:
                seen_leis.add(ent.lei or "")
                out.append(ent)
            break
        if isinstance(data, list):
            if not data:
                break
            for rec in data:
                ent = _gleif_entity_from_record(rec)
                if ent and ent.lei and ent.lei not in seen_leis:
                    seen_leis.add(ent.lei)
                    out.append(ent)
            # Naechste Seite?
            meta = resp.get("meta") or {}
            pagination = meta.get("pagination") or {}
            current = int(pagination.get("currentPage") or page)
            last = int(pagination.get("lastPage") or page)
            if current >= last:
                break
            page += 1
        else:
            break
    return out


def _lookup_via_gleif(
    query: str, *, include_children: bool, max_children: int,
    deadline: float,
) -> tuple[CorporateGroup | None, str | None]:
    """GLEIF-Strategie. Liefert (group, error_or_None).

    `deadline` ist `time.monotonic()`-Zeit, ab der wir abbrechen.
    """
    if time.monotonic() > deadline:
        return None, "GLEIF uebersprungen (Gesamt-Timeout erreicht)."

    client = _GleifClient()
    try:
        primary = _gleif_search_lei(client, query)
        if not primary or not primary.lei:
            return None, "GLEIF: kein LEI-Record gefunden."

        group = CorporateGroup(query=query, primary_entity=primary)
        group.sources_used.append("gleif")

        if time.monotonic() > deadline:
            group.coverage_note = "Gesamt-Timeout vor Hierarchie-Lookup."
            return group, None

        # Direct-Parent
        try:
            parents = _gleif_fetch_relation(client, primary.lei, "direct-parent")
            group.direct_parent = parents[0] if parents else None
        except Exception:  # noqa: BLE001
            log.exception("GLEIF direct-parent fehlgeschlagen")

        if time.monotonic() > deadline:
            return group, None

        # Ultimate-Parent
        try:
            ultimates = _gleif_fetch_relation(client, primary.lei, "ultimate-parent")
            group.ultimate_parent = ultimates[0] if ultimates else None
        except Exception:  # noqa: BLE001
            log.exception("GLEIF ultimate-parent fehlgeschlagen")

        if time.monotonic() > deadline:
            return group, None

        # Children (transitiv via ultimate-children, von der ULTIMATEN Mutter
        # ausgehend, damit wir den ganzen Konzern erfassen — auch wenn die
        # Anker-Firma in der Mitte der Hierarchie steht)
        if include_children:
            anchor_lei = (
                (group.ultimate_parent and group.ultimate_parent.lei)
                or primary.lei
            )
            try:
                children = _gleif_fetch_relation(
                    client, anchor_lei, "ultimate-children",
                )
                # Die Anker-Firma (primary) selbst aus der Kinderliste rauswerfen.
                children = [
                    c for c in children
                    if c.lei and c.lei != primary.lei
                ]
                if max_children and len(children) > max_children:
                    children = children[:max_children]
                group.children = children
            except Exception:  # noqa: BLE001
                log.exception("GLEIF ultimate-children fehlgeschlagen")

        return group, None
    finally:
        client.close()


# ── Wikidata SPARQL ───────────────────────────────────────────────────────────


_SPARQL_QUERY_LOOKUP = """
SELECT ?company ?companyLabel ?countryLabel ?lei ?modified WHERE {
  ?company rdfs:label ?label .
  FILTER(LANG(?label) IN ("de", "en"))
  FILTER(LCASE(STR(?label)) = LCASE("%(name)s"))
  ?company wdt:P31/wdt:P279* wd:Q4830453 .
  OPTIONAL { ?company wdt:P17 ?country . }
  OPTIONAL { ?company wdt:P1278 ?lei . }
  OPTIONAL { ?company schema:dateModified ?modified . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de,en" . }
}
LIMIT 5
"""

_SPARQL_QUERY_CHILDREN = """
SELECT ?subsidiary ?subsidiaryLabel ?countryLabel ?lei ?modified WHERE {
  wd:%(qid)s wdt:P355 ?subsidiary .
  OPTIONAL { ?subsidiary wdt:P17 ?country . }
  OPTIONAL { ?subsidiary wdt:P1278 ?lei . }
  OPTIONAL { ?subsidiary schema:dateModified ?modified . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de,en" . }
}
LIMIT %(limit)s
"""

_SPARQL_QUERY_PARENT = """
SELECT ?parent ?parentLabel ?countryLabel ?lei ?modified WHERE {
  wd:%(qid)s wdt:P749 ?parent .
  OPTIONAL { ?parent wdt:P17 ?country . }
  OPTIONAL { ?parent wdt:P1278 ?lei . }
  OPTIONAL { ?parent schema:dateModified ?modified . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de,en" . }
}
LIMIT 5
"""


def _wd_run_sparql(query: str, *, timeout: float = PER_CALL_TIMEOUT_S) -> list[dict]:
    """Fuehrt eine SPARQL-Abfrage aus und liefert die Bindings (Liste von Dicts).

    Bei Fehlern leere Liste.
    """
    try:
        with httpx.Client(timeout=timeout, headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/sparql-results+json",
        }) as client:
            r = client.get(WIKIDATA_SPARQL, params={
                "query": query,
                "format": "json",
            })
            if r.status_code >= 400:
                log.warning("Wikidata HTTP %d", r.status_code)
                return []
            data = r.json()
            return ((data.get("results") or {}).get("bindings") or [])
    except (httpx.RequestError, ValueError) as exc:
        log.warning("Wikidata Fehler: %s", exc)
        return []


def _wd_extract_qid(uri: str) -> str | None:
    """Holt 'Q12345' aus 'http://www.wikidata.org/entity/Q12345'."""
    if not uri:
        return None
    if "/entity/" in uri:
        return uri.rsplit("/entity/", 1)[1]
    return None


def _wd_binding_to_entity(
    b: dict, *, name_var: str, source_lookup_uri: str = "",
) -> CorporateEntity | None:
    """Wandelt ein SPARQL-Binding in eine CorporateEntity um."""
    label_obj = b.get(f"{name_var}Label") or {}
    name = label_obj.get("value") or ""
    if not name:
        return None
    company_obj = b.get(name_var) or {}
    qid = _wd_extract_qid(company_obj.get("value") or "")
    country = (b.get("countryLabel") or {}).get("value") or None
    lei = (b.get("lei") or {}).get("value") or None
    modified = _parse_iso_dt((b.get("modified") or {}).get("value"))
    return CorporateEntity(
        name=name,
        legal_form=None,
        country=country,
        lei=lei,
        wikidata_id=qid,
        address=None,
        source="wikidata",
        source_url=(
            f"https://www.wikidata.org/wiki/{qid}" if qid else WIKIDATA_SPARQL
        ),
        data_freshness=modified,
    )


def _lookup_via_wikidata(
    query: str, *, include_children: bool, max_children: int,
    deadline: float,
) -> tuple[CorporateGroup | None, str | None]:
    """Wikidata-Strategie. Liefert (group, error_or_None)."""
    if time.monotonic() > deadline:
        return None, "Wikidata uebersprungen (Gesamt-Timeout erreicht)."

    # SPARQL ist case-sensitive in der STR-Vergleiche, daher LCASE(...) genutzt.
    primary: CorporateEntity | None = None
    for alias in search_with_aliases(query):
        # Escape: doppelte Anfuehrungszeichen im Namen entfernen — bei Konzern-
        # namen praktisch nie noetig, aber zur Sicherheit.
        safe = alias.replace('"', "")
        rows = _wd_run_sparql(_SPARQL_QUERY_LOOKUP % {"name": safe})
        if rows:
            primary = _wd_binding_to_entity(rows[0], name_var="company")
            if primary:
                break
        if time.monotonic() > deadline:
            return None, "Wikidata-Lookup abgebrochen (Timeout)."

    if not primary or not primary.wikidata_id:
        return None, "Wikidata: kein passender Eintrag gefunden."

    group = CorporateGroup(query=query, primary_entity=primary)
    group.sources_used.append("wikidata")

    # Direct-Parent (P749)
    if time.monotonic() < deadline:
        try:
            rows = _wd_run_sparql(_SPARQL_QUERY_PARENT % {"qid": primary.wikidata_id})
            if rows:
                p = _wd_binding_to_entity(rows[0], name_var="parent")
                if p:
                    group.direct_parent = p
                    # Wir kennen via Wikidata ohne weitere Hops nicht, ob das
                    # auch der ultimate ist — wir setzen hier die direct_parent
                    # gleich als ultimate, wenn niemand anders gesetzt ist.
                    group.ultimate_parent = p
        except Exception:  # noqa: BLE001
            log.exception("Wikidata parent-Lookup fehlgeschlagen")

    # Subsidiaries (P355)
    if include_children and time.monotonic() < deadline:
        try:
            rows = _wd_run_sparql(_SPARQL_QUERY_CHILDREN % {
                "qid": primary.wikidata_id,
                "limit": max(1, min(int(max_children) * 2, 500)),
            })
            children: list[CorporateEntity] = []
            for r in rows:
                ent = _wd_binding_to_entity(r, name_var="subsidiary")
                if ent:
                    children.append(ent)
            if max_children and len(children) > max_children:
                children = children[:max_children]
            group.children = children
        except Exception:  # noqa: BLE001
            log.exception("Wikidata children-Lookup fehlgeschlagen")

    return group, None


# ── Merge ──────────────────────────────────────────────────────────────────────


def _entity_dedup_key(e: CorporateEntity) -> str:
    """Schluessel fuer Deduplikation. LEI bevorzugt, sonst Name+Country."""
    if e.lei:
        return f"lei:{e.lei.upper()}"
    n = _normalize_query(e.name)
    c = (e.country or "").lower()
    return f"name:{n}|country:{c}"


def _merge_entities(
    primary: CorporateEntity | None,
    secondary: CorporateEntity | None,
) -> CorporateEntity | None:
    """Merged zwei Entities: bevorzugt LEI (GLEIF-stark), ergaenzt fehlende
    Felder aus der Sekundaer-Quelle (Wikidata-stark fuer Q-IDs).
    """
    if not primary and not secondary:
        return None
    if not primary:
        return secondary
    if not secondary:
        return primary
    out = CorporateEntity(
        name=primary.name or secondary.name,
        legal_form=primary.legal_form or secondary.legal_form,
        country=primary.country or secondary.country,
        lei=primary.lei or secondary.lei,
        wikidata_id=primary.wikidata_id or secondary.wikidata_id,
        address=primary.address or secondary.address,
        source=primary.source if primary.lei else secondary.source,
        source_url=primary.source_url or secondary.source_url,
        data_freshness=(
            primary.data_freshness
            if (primary.data_freshness and (
                not secondary.data_freshness
                or primary.data_freshness >= secondary.data_freshness))
            else secondary.data_freshness or primary.data_freshness
        ),
        fetched_at=primary.fetched_at,
    )
    return out


def _merge_groups(
    a: CorporateGroup | None,
    b: CorporateGroup | None,
    *,
    max_children: int,
) -> CorporateGroup | None:
    """Merged GLEIF- und Wikidata-Ergebnisse zu einer einzelnen CorporateGroup.

    Strategie:
      * primary: a bevorzugt, mit Feld-Auffuellung aus b.
      * children: Vereinigung, dedupliziert ueber LEI bzw. Name+Country.
      * sources_used: Vereinigung.
      * max_children wird IMMER durchgesetzt — auch wenn nur eine Quelle
        Daten geliefert hat.
    """
    if not a and not b:
        return None
    # Single-Side: trotzdem Children kappen.
    if not a or not b:
        only = a or b
        if (max_children
            and only is not None
            and len(only.children or []) > max_children):
            only.children = list(only.children)[:max_children]
        return only
    out = CorporateGroup(query=a.query or b.query)
    out.primary_entity = _merge_entities(a.primary_entity, b.primary_entity)
    out.direct_parent = _merge_entities(a.direct_parent, b.direct_parent)
    out.ultimate_parent = _merge_entities(a.ultimate_parent, b.ultimate_parent)
    # Children: Vereinigung mit Dedup
    seen: dict[str, CorporateEntity] = {}
    for ent in (a.children or []) + (b.children or []):
        if not ent or not ent.name:
            continue
        # Anker selbst rauswerfen
        if (out.primary_entity
            and ent.lei and out.primary_entity.lei
            and ent.lei == out.primary_entity.lei):
            continue
        key = _entity_dedup_key(ent)
        if key in seen:
            seen[key] = _merge_entities(seen[key], ent)
        else:
            seen[key] = ent
    children = list(seen.values())
    if max_children and len(children) > max_children:
        children = children[:max_children]
    out.children = children
    out.sources_used = sorted({*(a.sources_used or []), *(b.sources_used or [])})
    return out


# ── Coverage-Note ──────────────────────────────────────────────────────────────

_COVERAGE_NOTE_BASE = (
    "Diese Konzern-Daten stammen aus oeffentlichen Drittquellen "
    "(GLEIF / Wikidata). Sie erfassen primaer LEI-pflichtige Konzerne "
    "(Finanzmarkt-Akteure, grosse Kapitalgesellschaften). Mittelstaendische "
    "Strukturen ohne LEI fehlen evtl. Diese Anwendung fuehrt KEINE eigene "
    "Konzern-Recherche durch — die hier dargestellten Verbindungen stammen "
    "aus den genannten Quellen und sind je nach Eintragspflege bei der "
    "Quelle aktuell. Datenstand pro Eintrag (sofern verfuegbar) wird "
    "separat ausgewiesen."
)


def _build_coverage_note(group: CorporateGroup, errors: list[str]) -> str:
    parts = [_COVERAGE_NOTE_BASE]
    if "gleif" not in group.sources_used:
        parts.append(
            "GLEIF nicht verfuegbar (kein LEI-Treffer oder API-Fehler) — "
            "Daten basieren ausschliesslich auf Wikidata."
        )
    if "wikidata" not in group.sources_used:
        parts.append("Wikidata-Fallback nicht angewandt oder ohne Treffer.")
    if errors:
        parts.append("Hinweise: " + " | ".join(errors[:3]))
    return " ".join(parts)


# ── Hauptfunktion ─────────────────────────────────────────────────────────────


def lookup_corporate_group(
    query: str,
    *,
    include_children: bool = True,
    max_children: int = DEFAULT_MAX_CHILDREN,
    timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_S,
) -> CorporateGroup:
    """Sucht Mutter + Toechter fuer eine Firma.

    Strategie:
      1. GLEIF: legalName-Search → LEI → direct-children + ultimate-children
      2. Wikidata-Fallback: SPARQL mit P749 (parent_organization) und P355
         (subsidiary)
      3. Merge: Wikidata-Treffer ohne LEI ergaenzen, Duplikate ueber Name+Country
         deduplizieren

    Liefert immer eine CorporateGroup-Instanz (auch wenn beide Quellen leer
    waren) — so kann das UI/PDF einheitlich behandeln. `coverage_note` und
    `sources_used` zeigen den Stand transparent an.
    """
    deadline = time.monotonic() + max(1.0, float(timeout_seconds or DEFAULT_TOTAL_TIMEOUT_S))
    errors: list[str] = []

    # 1. GLEIF
    gleif_group: CorporateGroup | None = None
    try:
        gleif_group, gleif_err = _lookup_via_gleif(
            query,
            include_children=include_children,
            max_children=max_children,
            deadline=deadline,
        )
        if gleif_err:
            errors.append(gleif_err)
    except Exception as exc:  # noqa: BLE001
        log.exception("GLEIF-Lookup fehlgeschlagen")
        errors.append(f"GLEIF Exception: {exc}")

    # 2. Wikidata — immer probieren, weil Wikidata oft Q-IDs liefert,
    #    die GLEIF nicht hat (insbes. bei Konzernen ohne LEI).
    wd_group: CorporateGroup | None = None
    if time.monotonic() < deadline:
        try:
            wd_group, wd_err = _lookup_via_wikidata(
                query,
                include_children=include_children,
                max_children=max_children,
                deadline=deadline,
            )
            if wd_err:
                errors.append(wd_err)
        except Exception as exc:  # noqa: BLE001
            log.exception("Wikidata-Lookup fehlgeschlagen")
            errors.append(f"Wikidata Exception: {exc}")

    # 3. Merge
    merged = _merge_groups(gleif_group, wd_group, max_children=max_children)
    if not merged:
        merged = CorporateGroup(query=query)
    if not merged.query:
        merged.query = query

    merged.coverage_note = _build_coverage_note(merged, errors)
    return merged


# ── Cache (DB-basiert, mit TTL und Stale-Refresh) ─────────────────────────────


def _cache_key(query: str) -> str:
    """Cache-Key — normalisierte Query, max. 255 Zeichen (DB-Spalte-Grenze)."""
    return _normalize_query(query)[:255] or "(empty)"


def get_cached_group(
    db, query: str, *, max_age_days: int = CACHE_TTL_DAYS,
) -> tuple[CorporateGroup | None, dict | None]:
    """Liefert (group, meta) aus dem Cache, sonst (None, None).

    `meta` enthaelt `cached`, `fetched_at`, `expired`, `stale`. Stale-but-
    not-yet-expired Eintraege werden zurueckgeliefert, der Aufrufer kann
    dann optional einen Hintergrund-Refresh anstossen.
    """
    try:
        from models.corporate_lookup_cache import CorporateLookupCache
    except Exception:  # noqa: BLE001
        log.exception("CorporateLookupCache nicht importierbar")
        return None, None
    key = _cache_key(query)
    if not key:
        return None, None
    try:
        row = (
            db.query(CorporateLookupCache)
            .filter(CorporateLookupCache.query_normalized == key)
            .order_by(CorporateLookupCache.fetched_at.desc())
            .first()
        )
    except Exception:  # noqa: BLE001
        log.exception("Cache-Lookup fehlgeschlagen")
        return None, None
    if not row:
        return None, None
    now = datetime.utcnow()
    expires_at = row.expires_at or (
        (row.fetched_at or now) + timedelta(days=max_age_days)
    )
    expired = now > expires_at
    payload = row.payload or {}
    if not isinstance(payload, dict):
        try:
            payload = json.loads(payload)
        except Exception:  # noqa: BLE001
            payload = {}
    group = _group_from_cache_payload(payload)
    meta = {
        "cached": True,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expired": expired,
        "source": row.source,
    }
    if expired:
        # Wir liefern den Eintrag trotzdem zurueck, damit der Aufrufer
        # entscheiden kann (z.B. fuer Live-Vorschau ist veraltet OK).
        return group, meta
    return group, meta


def store_group_in_cache(db, group: CorporateGroup) -> None:
    """Persistiert eine CorporateGroup im Cache (Upsert pro normalisiertem Key).

    TTL: 7 Tage (CACHE_TTL_DAYS). Best-Effort — Fehler werden geloggt, aber
    nicht durchgereicht (der Lookup-Path muss niemals durch den Cache fallen).
    """
    try:
        from models.corporate_lookup_cache import CorporateLookupCache
    except Exception:  # noqa: BLE001
        log.exception("CorporateLookupCache nicht importierbar")
        return
    key = _cache_key(group.query)
    if not key:
        return
    payload = group.to_dict()
    fetched_at = group.fetched_at or datetime.utcnow()
    expires_at = fetched_at + timedelta(days=CACHE_TTL_DAYS)
    src = "mixed"
    if group.sources_used:
        if len(group.sources_used) == 1:
            src = group.sources_used[0]
        else:
            src = "mixed"
    try:
        existing = (
            db.query(CorporateLookupCache)
            .filter(CorporateLookupCache.query_normalized == key)
            .first()
        )
        if existing:
            existing.payload = payload
            existing.fetched_at = fetched_at
            existing.expires_at = expires_at
            existing.source = src
        else:
            db.add(CorporateLookupCache(
                query_normalized=key,
                payload=payload,
                fetched_at=fetched_at,
                expires_at=expires_at,
                source=src,
            ))
        db.commit()
    except Exception:  # noqa: BLE001
        log.exception("Cache-Schreiben fehlgeschlagen")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def _entity_from_payload(p: dict | None) -> CorporateEntity | None:
    if not p or not isinstance(p, dict):
        return None
    return CorporateEntity(
        name=p.get("name") or "",
        legal_form=p.get("legal_form"),
        country=p.get("country"),
        lei=p.get("lei"),
        wikidata_id=p.get("wikidata_id"),
        address=p.get("address"),
        source=p.get("source") or "manual",
        source_url=p.get("source_url") or "",
        data_freshness=_parse_iso_dt(p.get("data_freshness")),
        fetched_at=_parse_iso_dt(p.get("fetched_at")) or datetime.utcnow(),
    )


def _group_from_cache_payload(p: dict) -> CorporateGroup:
    g = CorporateGroup(query=p.get("query") or "")
    g.primary_entity = _entity_from_payload(p.get("primary_entity"))
    g.direct_parent = _entity_from_payload(p.get("direct_parent"))
    g.ultimate_parent = _entity_from_payload(p.get("ultimate_parent"))
    g.children = [
        e for e in (
            _entity_from_payload(c) for c in (p.get("children") or [])
        )
        if e is not None
    ]
    g.sources_used = list(p.get("sources_used") or [])
    g.coverage_note = p.get("coverage_note") or ""
    g.fetched_at = _parse_iso_dt(p.get("fetched_at")) or datetime.utcnow()
    return g


def lookup_corporate_group_cached(
    db, query: str,
    *,
    include_children: bool = True,
    max_children: int = DEFAULT_MAX_CHILDREN,
    timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_S,
    use_cache: bool = True,
) -> tuple[CorporateGroup, dict]:
    """Wrapper mit Cache-Logik. Liefert (group, meta).

    `meta` enthaelt mindestens:
      * cache: 'hit' | 'miss' | 'stale-hit' | 'disabled'
      * fetched_at: ISO-Datum des Lookups (entweder live oder Cache)
      * expires_at: ISO-Datum des Cache-Verfalls (None bei 'disabled')
    """
    meta: dict[str, Any] = {"cache": "miss"}
    if use_cache:
        cached, cmeta = get_cached_group(db, query)
        if cached and cmeta and not cmeta.get("expired"):
            meta = {
                "cache": "hit",
                "fetched_at": cmeta.get("fetched_at"),
                "expires_at": cmeta.get("expires_at"),
                "source": cmeta.get("source"),
            }
            return cached, meta
        if cached and cmeta and cmeta.get("expired"):
            meta["cache_previous"] = {
                "fetched_at": cmeta.get("fetched_at"),
                "expires_at": cmeta.get("expires_at"),
            }
    # Live-Lookup
    group = lookup_corporate_group(
        query,
        include_children=include_children,
        max_children=max_children,
        timeout_seconds=timeout_seconds,
    )
    if use_cache:
        try:
            store_group_in_cache(db, group)
        except Exception:  # noqa: BLE001
            log.exception("Cache-Schreiben (post-lookup) fehlgeschlagen")
    meta["fetched_at"] = (
        group.fetched_at.isoformat() if group.fetched_at else None
    )
    meta["expires_at"] = (
        (group.fetched_at + timedelta(days=CACHE_TTL_DAYS)).isoformat()
        if group.fetched_at else None
    )
    if use_cache and meta["cache"] == "miss" and "cache_previous" in meta:
        meta["cache"] = "stale-refreshed"
    return group, meta


# ── Public API: kompakte to_dict-Helfer ─────────────────────────────────────


def group_to_section_dict(group: CorporateGroup, meta: dict | None = None) -> dict:
    """Liefert die Sektion fuer den Audit-Report (kompaktes Dict)."""
    out: dict[str, Any] = group.to_dict()
    if meta:
        out["cache_meta"] = dict(meta)
    return out


# Re-Export fuer Tests
__all__ = [
    "CorporateEntity",
    "CorporateGroup",
    "lookup_corporate_group",
    "lookup_corporate_group_cached",
    "search_with_aliases",
    "get_cached_group",
    "store_group_in_cache",
    "group_to_section_dict",
    "_normalize_query",
    "_strip_legal_form",
    "_entity_dedup_key",
    "_merge_groups",
    "_merge_entities",
    "_gleif_entity_from_record",
    "_wd_binding_to_entity",
    "_group_from_cache_payload",
    "CACHE_TTL_DAYS",
]
