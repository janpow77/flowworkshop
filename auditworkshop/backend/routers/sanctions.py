"""
flowworkshop · routers/sanctions.py
Uebersicht der Sanktionslisten + Multi-Source-Fuzzy-Suche.

Lokal harvestbare Quellen (alle aus OpenSanctions):
- eu_fsf            EU Konsolidierte Finanzsanktionsliste
- un_sc             UN Security Council
- us_ofac_sdn       OFAC SDN List
- gb_hmt_sanctions  UK OFSI Consolidated List
- ch_seco           SECO Schweizer Sanktionsliste

Daneben werden weitere Listen (BAFA, Bundesbank, EU Sanctions Map) nur als
Recherche-Karten gefuehrt — sie sind nicht lokal indexiert.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.auth import require_admin
from services.sanctions_service import (
    DEFAULT_SANCTIONS_SOURCES,
    get_index,
    get_multi_service,
    method_explanation,
    normalize_name,
)

router = APIRouter(prefix="/api/sanctions", tags=["sanctions"])
log = logging.getLogger(__name__)


# ── Statische Liste der Sanktionslisten (Cards-Definitionen) ─────────────────
# `is_searchable_locally=True` markiert die im Backend tatsaechlich indexierten
# Quellen — alles andere bleibt Verlinkung/Recherche-Hinweis.

_SANCTIONS_LISTS = [
    {
        "key": "eu_fsf",
        "name": "EU Konsolidierte Finanzsanktionsliste (FSF)",
        "issuer": "Europaeische Kommission",
        "scope": "Personen, Organisationen, Schiffe — alle EU-Finanzsanktionen",
        "description": (
            "Konsolidierte Liste aller von der EU verhaengten Finanzsanktionen. "
            "Von der Europaeischen Kommission gepflegt; deckt saemtliche "
            "EU-Sanktionsregime nach Art. 215 AEUV ab."
        ),
        "url": "https://webgate.ec.europa.eu/fsd/fsf",
        "search_url": "https://webgate.ec.europa.eu/fsd/fsf/public/searchFSF",
        "data_format": "XML / CSV (ueber OpenSanctions)",
        "update_frequency": "bei Listenaenderung (i.d.R. mehrfach pro Woche)",
        "language": "DE / EN / alle Amtssprachen",
        "color": "rose",
        "icon": "ShieldAlert",
        "tag": "EU-Konsolidiert",
        "use_in_audit": (
            "Zentrale Quelle bei Bezug zu sanktionsrelevanten Personen oder "
            "Organisationen — etwa bei der Plausibilisierung von Beguenstigten "
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
        "update_frequency": "bei Rechtsaktaenderung",
        "language": "EN",
        "color": "indigo",
        "icon": "Globe2",
        "tag": "Recherche",
        "use_in_audit": (
            "Schnelle Orientierung, ob ein Land/Sektor von EU-Sanktionen betroffen "
            "ist und welche Rechtsakte einschlaegig sind."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "un_sc",
        "name": "UN Security Council Consolidated List",
        "issuer": "UN-Sicherheitsrat",
        "scope": "Personen und Organisationen unter UN-Sanktionen",
        "description": (
            "Konsolidierte Liste aller vom Sicherheitsrat verhaengten "
            "Sanktionen. Bildet den Kern der EU-Listen, geht aber bei einzelnen "
            "Regimen darueber hinaus."
        ),
        "url": "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list",
        "search_url": "https://scsanctions.un.org/consolidated/",
        "data_format": "XML / HTML (ueber OpenSanctions als CSV)",
        "update_frequency": "bei Resolution",
        "language": "EN / FR / ES / RU / AR / ZH",
        "color": "sky",
        "icon": "Globe",
        "tag": "international",
        "use_in_audit": (
            "Ergaenzende Recherche bei internationalem Bezug. UN-Listungen werden "
            "in EU-Recht uebernommen, Listung kann aber kurzzeitig vor der "
            "EU-Umsetzung sichtbar sein."
        ),
        "is_searchable_locally": True,
    },
    {
        "key": "us_ofac_sdn",
        "name": "OFAC SDN List",
        "issuer": "U.S. Treasury — OFAC",
        "scope": "Specially Designated Nationals & Blocked Persons (USA)",
        "description": (
            "US-Sanktionsliste. Fuer EFRE-Pruefungen rechtlich nicht bindend, "
            "aber fuer Risikoeinschaetzungen und Bank-/Korrespondenzbezuege "
            "relevant — viele Banken sperren OFAC-gelistete Empfaenger weltweit."
        ),
        "url": "https://sanctionssearch.ofac.treas.gov/",
        "search_url": "https://sanctionssearch.ofac.treas.gov/",
        "data_format": "XML / CSV (ueber OpenSanctions)",
        "update_frequency": "taeglich",
        "language": "EN",
        "color": "amber",
        "icon": "Banknote",
        "tag": "Risiko",
        "use_in_audit": (
            "Hilft bei der Risiko-Triage. Bankzahlungsablehnungen sind oft "
            "auf OFAC-Treffer zurueckzufuehren, auch wenn EU-Listungen fehlen."
        ),
        "is_searchable_locally": True,
    },
    {
        "key": "bafa_de",
        "name": "BAFA — Aussenwirtschaftsrechtliche Embargos",
        "issuer": "Bundesamt fuer Wirtschaft und Ausfuhrkontrolle",
        "scope": "Embargo- und Sanktionsmerkblaetter, deutsche Umsetzung",
        "description": (
            "Aufbereitung der EU-Sanktionen aus deutscher Behoerdensicht: "
            "Embargo-Merkblaetter, Auslegungshinweise, Allgemeinverfuegungen. "
            "Wichtig fuer die Praxis von Aussenwirtschaft und Foerderabwicklung."
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
            "Auslegungshilfe bei Auslandsbezug eines Vorhabens (Lieferketten, "
            "Beteiligungen, Endempfaenger). Bei Dual-Use-Guetern empfehlenswerte Lektuere."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "bundesbank",
        "name": "Deutsche Bundesbank — Finanzsanktionen",
        "issuer": "Deutsche Bundesbank",
        "scope": "Hinweise und Bekanntmachungen zu Finanzsanktionen",
        "description": (
            "Servicebereich der Bundesbank zu EU-Finanzsanktionen — Antrags"
            "formulare fuer Genehmigungen nach §§ 4-6 AWG, Hinweise zur "
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
            "Anlaufstelle fuer Genehmigungen bei eingefrorenem Vermoegen. "
            "Nur relevant, wenn ein Vorhabenempfaenger gelistet ist."
        ),
        "is_searchable_locally": False,
    },
    {
        "key": "gb_hmt_sanctions",
        "name": "UK FCDO/OFSI Consolidated List",
        "issuer": "UK FCDO / HM Treasury — Office of Financial Sanctions Implementation",
        "scope": "UK-Sanktionen post-Brexit (FCDO + HMT/OFSI)",
        "description": (
            "Britische konsolidierte Liste. Seit dem Brexit rechtlich eigen"
            "staendig, ueberlappt aber stark mit der EU FSF. Wichtig bei UK-"
            "Bezug eines Vorhabens (Beteiligungen, Empfangsbank). "
            "OpenSanctions liefert FCDO + HMT/OFSI als kombinierten Datensatz."
        ),
        "url": "https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets",
        "search_url": "https://sanctionssearchapp.ofsi.hmtreasury.gov.uk/",
        "data_format": "CSV / XML (ueber OpenSanctions, gb_fcdo_sanctions)",
        "update_frequency": "woechentlich",
        "language": "EN",
        "color": "violet",
        "icon": "Crown",
        "tag": "UK",
        "use_in_audit": (
            "Bei britischer Beteiligung sinnvoll. Listungen weichen punktuell "
            "von der EU FSF ab."
        ),
        "is_searchable_locally": True,
    },
    {
        "key": "ch_seco",
        "name": "SECO — Schweizer Sanktionsliste",
        "issuer": "Staatssekretariat fuer Wirtschaft (SECO)",
        "scope": "Schweizer Umsetzung internationaler Sanktionen",
        "description": (
            "Die Schweiz uebernimmt EU- und UN-Sanktionen weitgehend, weicht "
            "aber in Einzelfaellen ab. Bei CH-Bezug (Empfaenger, Lieferant) "
            "gegenpruefen."
        ),
        "url": "https://www.seco.admin.ch/seco/de/home/Aussenwirtschaftspolitik_Wirtschaftliche_Zusammenarbeit/Wirtschaftsbeziehungen/exportkontrollen-und-sanktionen/sanktionen-embargos/sanktionsmassnahmen.html",
        "search_url": "https://www.sesam.search.admin.ch/sesam-search-web/pages/searchSanctionedPersons.xhtml",
        "data_format": "HTML / XML (ueber OpenSanctions als CSV)",
        "update_frequency": "anlassbezogen",
        "language": "DE / FR / IT / EN",
        "color": "rose",
        "icon": "Mountain",
        "tag": "CH",
        "use_in_audit": (
            "Bei Schweizer Geschaeftsbeziehungen ergaenzend pruefen — die "
            "Liste ist nicht in der EU FSF enthalten."
        ),
        "is_searchable_locally": True,
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


class SanctionsSourceStatus(BaseModel):
    """Status einer einzelnen lokal indexierten Sanctions-Quelle."""
    key: str
    display_name: str
    issuer: str
    license: str
    download_url: str
    csv_path: str
    loaded: bool
    total_entries: int
    persons: int
    organizations: int
    loaded_at: str | None = None
    source_mtime: str | None = None
    source_size_bytes: int | None = None


class SanctionsSourcesResponse(BaseModel):
    sources_total: int
    sources_loaded: int
    total_entries: int
    sources: list[SanctionsSourceStatus]


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
    # Multi-Source-Felder
    source_key: str = ""
    source_display_name: str = ""


class SearchResponse(BaseModel):
    query: str
    normalized: str
    total_hits: int
    threshold: float
    method: str
    hits: list[SearchHitOut]
    # Multi-Source: welche Quellen wurden tatsaechlich abgefragt
    sources_searched: list[str] = []


# ── Endpunkte ────────────────────────────────────────────────────────────────


@router.get("/lists", response_model=SanctionsListResponse)
def get_lists() -> SanctionsListResponse:
    """Statische Uebersicht aller im Workshop dokumentierten Sanktionslisten."""
    return SanctionsListResponse(count=len(_SANCTIONS_LISTS), lists=_SANCTIONS_LISTS)


@router.get("/sources", response_model=SanctionsSourcesResponse)
def get_sources() -> SanctionsSourcesResponse:
    """Status aller lokal indexierten Sanctions-Quellen mit Per-Source-Stats.

    Liefert pro Quelle Lade-Status, Eintragszahlen, License und Download-URL —
    fuer das Admin-/Status-UI im Frontend.
    """
    svc = get_multi_service()
    aggregated = svc.stats()
    items: list[SanctionsSourceStatus] = []
    for stats in aggregated.get("per_source", []):
        items.append(SanctionsSourceStatus(
            key=stats.get("source_key") or "",
            display_name=stats.get("source_display_name") or "",
            issuer=stats.get("issuer") or "",
            license=stats.get("license") or "",
            download_url=stats.get("download_url") or "",
            csv_path=stats.get("csv_path") or "",
            loaded=bool(stats.get("loaded")),
            total_entries=int(stats.get("total_entries") or 0),
            persons=int(stats.get("persons") or 0),
            organizations=int(stats.get("organizations") or 0),
            loaded_at=stats.get("loaded_at"),
            source_mtime=stats.get("source_mtime"),
            source_size_bytes=stats.get("source_size_bytes"),
        ))
    return SanctionsSourcesResponse(
        sources_total=int(aggregated.get("sources_total") or 0),
        sources_loaded=int(aggregated.get("sources_loaded") or 0),
        total_entries=int(aggregated.get("total_entries") or 0),
        sources=items,
    )


@router.get("/method")
def get_method() -> dict:
    """Methodische Erlaeuterung der Fuzzy-Suche (fuer die Erklaer-Card)."""
    return method_explanation()


@router.get("/stats")
def get_stats() -> dict:
    """Aggregierte Index-Statistik mit Per-Source-Breakdown.

    Backward-Compat: Felder `total_entries`, `persons`, `organizations` werden
    weiterhin als Top-Level-Keys mitgeliefert (Summe ueber alle Quellen).
    Zusaetzlich `per_source` mit Detail-Stats pro Quelle.
    """
    svc = get_multi_service()
    return svc.stats()


def _parse_sources_param(raw: str | None) -> list[str] | None:
    """`?sources=eu_fsf,un_sc` → ["eu_fsf", "un_sc"], None → alle."""
    if not raw:
        return None
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    return keys or None


@router.get("/search", response_model=SearchResponse)
def search_get(
    q: str = Query(..., min_length=2, description="Suchbegriff (Name oder Alias)"),
    limit: int = Query(15, ge=1, le=50),
    min_score: float = Query(65.0, ge=40.0, le=100.0),
    schema_filter: str | None = Query(None, description='"Person" oder "Organization"'),
    sources: str | None = Query(
        None,
        description=(
            "Komma-Liste der Source-Keys (z.B. 'eu_fsf,un_sc'). "
            "Default: alle aktivierten Quellen."
        ),
    ),
) -> SearchResponse:
    """Multi-Source-Fuzzy-Suche gegen alle indexierten Sanctions-Listen.

    Default sind alle aktivierten Quellen. Mit dem `sources`-Parameter kann
    auf einzelne Listen eingeschraenkt werden (Komma-Liste).
    """
    svc = get_multi_service()
    if not svc.is_any_loaded():
        raise HTTPException(503, "Kein Sanctions-Index geladen.")

    source_keys = _parse_sources_param(sources)
    # nur tatsaechlich aktivierte Source-Keys nutzen
    if source_keys is not None:
        valid = set(svc.indices.keys())
        source_keys = [k for k in source_keys if k in valid]
        if not source_keys:
            raise HTTPException(
                400,
                f"Keine bekannten Source-Keys angegeben. "
                f"Verfuegbar: {', '.join(sorted(valid))}",
            )

    hits = svc.search(
        q,
        limit=limit,
        min_score=min_score,
        schema=schema_filter,
        sources=source_keys,
    )
    sources_searched = source_keys or list(svc.indices.keys())

    return SearchResponse(
        query=q,
        normalized=normalize_name(q),
        total_hits=len(hits),
        threshold=min_score,
        method="rapidfuzz.fuzz.token_set_ratio (mit Normalisierung, Multi-Source)",
        sources_searched=sources_searched,
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
                source_key=h.source_key,
                source_display_name=h.source_display_name,
            )
            for h in hits
        ],
    )


@router.post("/refresh")
def refresh(
    source_key: str | None = Query(
        None,
        description=(
            "Wenn gesetzt: nur diese Quelle refreshen (z.B. 'eu_fsf'). "
            "Sonst werden alle aktivierten Quellen sequenziell refreshed."
        ),
    ),
    session: dict = Depends(require_admin),
) -> dict:
    """Laedt eine oder alle Sanctions-CSVs neu von OpenSanctions (Admin-Aktion).

    Phase 6c: Geht ueber ``services.scheduler.run_sanctions_refresh``,
    damit ein ``SanctionsRefreshRun`` angelegt wird, dessen ``id`` als FK auf
    jedem upsertten ``SanctionsEntry`` landet (Audit-Trail).
    """
    svc = get_multi_service()
    if source_key and source_key not in svc.indices:
        raise HTTPException(
            400,
            f"Unbekannte Source: {source_key}. "
            f"Verfuegbar: {', '.join(sorted(svc.indices.keys()))}",
        )
    try:
        from services.scheduler import run_sanctions_refresh
        triggered_by = f"admin:{session.get('user_id') or 'unknown'}"
        return run_sanctions_refresh(triggered_by=triggered_by, source_key=source_key)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("Sanctions-Refresh fehlgeschlagen")
        raise HTTPException(502, f"Download fehlgeschlagen: {e}") from e
