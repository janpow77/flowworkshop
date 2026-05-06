"""
flowworkshop · routers/sanctions.py
Übersicht der Sanktionslisten + Fuzzy-Suche gegen die EU-Konsolidierte FSF.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.sanctions_service import (
    get_index,
    method_explanation,
)

router = APIRouter(prefix="/api/sanctions", tags=["sanctions"])
log = logging.getLogger(__name__)


# ── Statische Liste der Sanktionslisten (Cards-Definitionen) ─────────────────

_SANCTIONS_LISTS = [
    {
        "key": "eu_fsf",
        "name": "EU Konsolidierte Finanzsanktionsliste (FSF)",
        "issuer": "Europäische Kommission",
        "scope": "Personen, Organisationen, Schiffe — alle EU-Finanzsanktionen",
        "description": (
            "Konsolidierte Liste aller von der EU verhängten Finanzsanktionen. "
            "Maßgeblich für Prüfungen nach Art. 215 AEUV und die EU-Sanktions­"
            "verordnungen. Wird von der Kommission gepflegt und ist die "
            "verbindliche Quelle für EU-Mitgliedstaaten."
        ),
        "url": "https://webgate.ec.europa.eu/fsd/fsf",
        "search_url": "https://webgate.ec.europa.eu/fsd/fsf/public/searchFSF",
        "data_format": "XML / CSV (über OpenSanctions)",
        "update_frequency": "bei Listenänderung (i.d.R. mehrfach pro Woche)",
        "language": "DE / EN / alle Amtssprachen",
        "color": "rose",
        "icon": "ShieldAlert",
        "tag": "verbindlich",
        "use_in_audit": (
            "Zentrale Quelle bei Bezug zu sanktionsrelevanten Personen oder "
            "Organisationen — etwa bei der Plausibilisierung von Begünstigten "
            "oder wirtschaftlich Berechtigten."
        ),
        "is_searchable_locally": True,
    },
    {
        "key": "eu_sanctions_map",
        "name": "EU Sanctions Map",
        "issuer": "Rat der EU / EEAS",
        "scope": "Sanktionsregime nach Land/Thema (visuell)",
        "description": (
            "Interaktive Karten- und Listenansicht aller aktiven EU-Sanktionsregime. "
            "Zeigt pro Land die Rechtsakte, betroffene Sektoren und Verlinkungen "
            "zur konsolidierten Liste."
        ),
        "url": "https://www.sanctionsmap.eu/",
        "search_url": "https://www.sanctionsmap.eu/#/main",
        "data_format": "Web-UI",
        "update_frequency": "bei Rechtsaktänderung",
        "language": "EN",
        "color": "indigo",
        "icon": "Globe2",
        "tag": "Recherche",
        "use_in_audit": (
            "Schnelle Orientierung, ob ein Land/Sektor von EU-Sanktionen betroffen "
            "ist und welche Rechtsakte einschlägig sind."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "un_sc",
        "name": "UN Security Council Consolidated List",
        "issuer": "UN-Sicherheitsrat",
        "scope": "Personen und Organisationen unter UN-Sanktionen",
        "description": (
            "Konsolidierte Liste aller vom Sicherheitsrat verhängten "
            "Sanktionen. Bildet den Kern der EU-Listen, geht aber bei einzelnen "
            "Regimen darüber hinaus."
        ),
        "url": "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list",
        "search_url": "https://scsanctions.un.org/consolidated/",
        "data_format": "XML / HTML",
        "update_frequency": "bei Resolution",
        "language": "EN / FR / ES / RU / AR / ZH",
        "color": "sky",
        "icon": "Globe",
        "tag": "international",
        "use_in_audit": (
            "Ergänzende Recherche bei internationalem Bezug. UN-Listungen werden "
            "in EU-Recht übernommen, Listung kann aber kurzzeitig vor der "
            "EU-Umsetzung sichtbar sein."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "ofac_sdn",
        "name": "OFAC SDN List",
        "issuer": "U.S. Treasury — OFAC",
        "scope": "Specially Designated Nationals & Blocked Persons (USA)",
        "description": (
            "US-Sanktionsliste. Für EFRE-Prüfungen rechtlich nicht bindend, "
            "aber für Risikoeinschätzungen und Bank-/Korrespondenz­bezüge "
            "relevant — viele Banken sperren OFAC-gelistete Empfänger weltweit."
        ),
        "url": "https://sanctionssearch.ofac.treas.gov/",
        "search_url": "https://sanctionssearch.ofac.treas.gov/",
        "data_format": "XML / CSV",
        "update_frequency": "täglich",
        "language": "EN",
        "color": "amber",
        "icon": "Banknote",
        "tag": "Risiko",
        "use_in_audit": (
            "Hilft bei der Risiko-Triage. Bank­zahlungs­ablehnungen sind oft "
            "auf OFAC-Treffer zurück­zuführen, auch wenn EU-Listungen fehlen."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "bafa_de",
        "name": "BAFA — Außenwirtschaftsrechtliche Embargos",
        "issuer": "Bundesamt für Wirtschaft und Ausfuhrkontrolle",
        "scope": "Embargo- und Sanktions­merkblätter, deutsche Umsetzung",
        "description": (
            "Aufbereitung der EU-Sanktionen aus deutscher Behörden­sicht: "
            "Embargo-Merkblätter, Auslegungs­hinweise, Allgemein­verfügungen. "
            "Wichtig für die Praxis von Außenwirtschaft und Förder­abwicklung."
        ),
        "url": "https://www.bafa.de/DE/Aussenwirtschaft/Ausfuhrkontrolle/Embargos/embargos_node.html",
        "search_url": "https://www.bafa.de/DE/Aussenwirtschaft/Ausfuhrkontrolle/Embargos/embargos_node.html",
        "data_format": "HTML / PDF",
        "update_frequency": "anlassbezogen",
        "language": "DE",
        "color": "emerald",
        "icon": "Building2",
        "tag": "DE-Praxis",
        "use_in_audit": (
            "Auslegungs­hilfe bei Auslandsbezug eines Vorhabens (Liefer­ketten, "
            "Beteiligungen, Endempfänger). Bei Dual-Use-Gütern empfehlenswerte Lektüre."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "bundesbank",
        "name": "Deutsche Bundesbank — Finanzsanktionen",
        "issuer": "Deutsche Bundesbank",
        "scope": "Hinweise und Bekanntmachungen zu Finanzsanktionen",
        "description": (
            "Servicebereich der Bundesbank zu EU-Finanzsanktionen — Antrags­"
            "formulare für Genehmigungen nach §§ 4–6 AWG, Hinweise zur "
            "Listenanwendung und Newsletter."
        ),
        "url": "https://www.bundesbank.de/de/service/finanzsanktionen",
        "search_url": "https://www.bundesbank.de/de/service/finanzsanktionen",
        "data_format": "HTML",
        "update_frequency": "anlassbezogen",
        "language": "DE",
        "color": "teal",
        "icon": "Landmark",
        "tag": "DE-Genehmigung",
        "use_in_audit": (
            "Anlaufstelle für Genehmigungen bei eingefrorenem Vermögen. "
            "Nur relevant, wenn ein Vorhaben­empfänger gelistet ist."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "uk_ofsi",
        "name": "UK OFSI Consolidated List",
        "issuer": "HM Treasury — Office of Financial Sanctions Implementation",
        "scope": "UK-Finanzsanktionen post-Brexit",
        "description": (
            "Britische konsolidierte Liste. Seit dem Brexit rechtlich eigen­"
            "ständig, überlappt aber stark mit der EU FSF. Wichtig bei UK-"
            "Bezug eines Vorhabens (Beteiligungen, Empfangsbank)."
        ),
        "url": "https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets",
        "search_url": "https://sanctionssearchapp.ofsi.hmtreasury.gov.uk/",
        "data_format": "CSV / XML",
        "update_frequency": "wöchentlich",
        "language": "EN",
        "color": "violet",
        "icon": "Crown",
        "tag": "UK",
        "use_in_audit": (
            "Bei britischer Beteiligung sinnvoll. Listungen weichen punktuell "
            "von der EU FSF ab."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "seco_ch",
        "name": "SECO — Schweizer Sanktionsliste",
        "issuer": "Staatssekretariat für Wirtschaft (SECO)",
        "scope": "Schweizer Umsetzung internationaler Sanktionen",
        "description": (
            "Die Schweiz übernimmt EU- und UN-Sanktionen weitgehend, weicht "
            "aber in Einzelfällen ab. Bei CH-Bezug (Empfänger, Lieferant) "
            "gegenprüfen."
        ),
        "url": "https://www.seco.admin.ch/seco/de/home/Aussenwirtschaftspolitik_Wirtschaftliche_Zusammenarbeit/Wirtschaftsbeziehungen/exportkontrollen-und-sanktionen/sanktionen-embargos/sanktionsmassnahmen.html",
        "search_url": "https://www.sesam.search.admin.ch/sesam-search-web/pages/searchSanctionedPersons.xhtml",
        "data_format": "HTML / XML",
        "update_frequency": "anlassbezogen",
        "language": "DE / FR / IT / EN",
        "color": "rose",
        "icon": "Mountain",
        "tag": "CH",
        "use_in_audit": (
            "Bei Schweizer Geschäfts­beziehungen ergänzend prüfen — die "
            "Liste ist nicht in der EU FSF enthalten."
        ),
        "is_searchable_locally": False,
    },
]


# ── Schemas ──────────────────────────────────────────────────────────────────


class ListEntry(BaseModel):
    key: str
    name: str
    issuer: str
    scope: str
    description: str
    url: str
    search_url: str
    data_format: str
    update_frequency: str
    language: str
    color: str
    icon: str
    tag: str
    use_in_audit: str
    is_searchable_locally: bool


class SanctionsListResponse(BaseModel):
    count: int
    lists: list[ListEntry]


class SearchHitOut(BaseModel):
    id: str
    schema_type: str = Field(..., alias="schema_type")
    name: str
    matched_on: str
    matched_field: str
    score: float
    confidence: str
    aliases: list[str]
    birth_date: str
    countries: str
    addresses: str
    identifiers: str
    sanctions: str
    program_ids: str
    first_seen: str
    last_seen: str


class SearchResponse(BaseModel):
    query: str
    normalized: str
    total_hits: int
    threshold: float
    method: str
    hits: list[SearchHitOut]


# ── Endpunkte ────────────────────────────────────────────────────────────────


@router.get("/lists", response_model=SanctionsListResponse)
def get_lists() -> SanctionsListResponse:
    """Statische Übersicht aller im Workshop dokumentierten Sanktionslisten."""
    return SanctionsListResponse(count=len(_SANCTIONS_LISTS), lists=_SANCTIONS_LISTS)


@router.get("/method")
def get_method() -> dict:
    """Methodische Erläuterung der Fuzzy-Suche (für die Erklär-Card)."""
    return method_explanation()


@router.get("/stats")
def get_stats() -> dict:
    """Index-Statistik (Einträge, letzte Ladung, Quelle)."""
    return get_index().stats()


@router.get("/search", response_model=SearchResponse)
def search_get(
    q: str = Query(..., min_length=2, description="Suchbegriff (Name oder Alias)"),
    limit: int = Query(15, ge=1, le=50),
    min_score: float = Query(65.0, ge=40.0, le=100.0),
    schema_filter: str | None = Query(None, description='"Person" oder "Organization"'),
) -> SearchResponse:
    """Fuzzy-Suche gegen die EU FSF (GET-Variante für einfache Aufrufe)."""
    idx = get_index()
    if not idx.is_loaded():
        raise HTTPException(503, "Sanctions-Index ist nicht geladen.")
    from services.sanctions_service import normalize_name
    hits = idx.search(q, limit=limit, min_score=min_score, schema=schema_filter)
    return SearchResponse(
        query=q,
        normalized=normalize_name(q),
        total_hits=len(hits),
        threshold=min_score,
        method="rapidfuzz.fuzz.token_set_ratio (mit Normalisierung)",
        hits=[
            SearchHitOut(
                id=h.id,
                schema_type=h.schema,
                name=h.name,
                matched_on=h.matched_on,
                matched_field=h.matched_field,
                score=h.score,
                confidence=h.confidence,
                aliases=h.aliases,
                birth_date=h.birth_date,
                countries=h.countries,
                addresses=h.addresses,
                identifiers=h.identifiers,
                sanctions=h.sanctions,
                program_ids=h.program_ids,
                first_seen=h.first_seen,
                last_seen=h.last_seen,
            )
            for h in hits
        ],
    )


@router.post("/refresh")
def refresh() -> dict:
    """Lädt die FSF-CSV neu von OpenSanctions (Admin-Aktion)."""
    idx = get_index()
    try:
        return idx.refresh_from_source()
    except Exception as e:  # noqa: BLE001
        log.exception("FSF-Refresh fehlgeschlagen")
        raise HTTPException(502, f"Download fehlgeschlagen: {e}") from e
