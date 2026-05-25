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

import csv
import io
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from routers.auth import require_admin
from services.sanctions_service import (
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
        "issuer": "Europäische Kommission",
        "scope": "Personen, Organisationen, Schiffe — alle EU-Finanzsanktionen",
        "description": (
            "Konsolidierte Liste aller von der EU verhängten Finanzsanktionen. "
            "Von der Europäischen Kommission gepflegt; deckt sämtliche "
            "EU-Sanktionsregime nach Art. 215 AEUV ab."
        ),
        "url": "https://webgate.ec.europa.eu/fsd/fsf",
        "search_url": "https://webgate.ec.europa.eu/fsd/fsf/public/searchFSF",
        "data_format": "XML / CSV (über OpenSanctions)",
        "update_frequency": "bei Listenänderung (i.d.R. mehrfach pro Woche)",
        "language": "DE / EN / alle Amtssprachen",
        "color": "rose",
        "icon": "ShieldAlert",
        "tag": "EU-Konsolidiert",
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
        "data_format": "XML / HTML (über OpenSanctions als CSV)",
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
        "is_searchable_locally": True,
    },
    {
        "key": "us_ofac_sdn",
        "name": "OFAC SDN List",
        "issuer": "U.S. Treasury — OFAC",
        "scope": "Specially Designated Nationals & Blocked Persons (USA)",
        "description": (
            "US-Sanktionsliste. Für EFRE-Prüfungen rechtlich nicht bindend, "
            "aber für Risikoeinschätzungen und Bank-/Korrespondenzbezüge "
            "relevant — viele Banken sperren OFAC-gelistete Empfänger weltweit."
        ),
        "url": "https://sanctionssearch.ofac.treas.gov/",
        "search_url": "https://sanctionssearch.ofac.treas.gov/",
        "data_format": "XML / CSV (über OpenSanctions)",
        "update_frequency": "täglich",
        "language": "EN",
        "color": "amber",
        "icon": "Banknote",
        "tag": "Risiko",
        "use_in_audit": (
            "Hilft bei der Risiko-Triage. Bankzahlungsablehnungen sind oft "
            "auf OFAC-Treffer zurückzuführen, auch wenn EU-Listungen fehlen."
        ),
        "is_searchable_locally": True,
    },
    {
        "key": "bafa_de",
        "name": "BAFA — Außenwirtschaftsrechtliche Embargos",
        "issuer": "Bundesamt für Wirtschaft und Ausfuhrkontrolle",
        "scope": "Embargo- und Sanktionsmerkblätter, deutsche Umsetzung",
        "description": (
            "Aufbereitung der EU-Sanktionen aus deutscher Behördensicht: "
            "Embargo-Merkblätter, Auslegungshinweise, Allgemeinverfügungen. "
            "Wichtig für die Praxis von Außenwirtschaft und Förderabwicklung."
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
            "Servicebereich der Bundesbank zu EU-Finanzsanktionen — Antrags"
            "formulare für Genehmigungen nach §§ 4-6 AWG, Hinweise zur "
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
            "Nur relevant, wenn ein Vorhabenempfänger gelistet ist."
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
            "ständig, überlappt aber stark mit der EU FSF. Wichtig bei UK-"
            "Bezug eines Vorhabens (Beteiligungen, Empfangsbank). "
            "OpenSanctions liefert FCDO + HMT/OFSI als kombinierten Datensatz."
        ),
        "url": "https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets",
        "search_url": "https://sanctionssearchapp.ofsi.hmtreasury.gov.uk/",
        "data_format": "CSV / XML (über OpenSanctions, gb_fcdo_sanctions)",
        "update_frequency": "wöchentlich",
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
        "issuer": "Staatssekretariat für Wirtschaft (SECO)",
        "scope": "Schweizer Umsetzung internationaler Sanktionen",
        "description": (
            "Die Schweiz übernimmt EU- und UN-Sanktionen weitgehend, weicht "
            "aber in Einzelfällen ab. Bei CH-Bezug (Empfänger, Lieferant) "
            "gegenprüfen."
        ),
        "url": "https://www.seco.admin.ch/seco/de/home/Aussenwirtschaftspolitik_Wirtschaftliche_Zusammenarbeit/Wirtschaftsbeziehungen/exportkontrollen-und-sanktionen/sanktionen-embargos/sanktionsmassnahmen.html",
        "search_url": "https://www.sesam.search.admin.ch/sesam-search-web/pages/searchSanctionedPersons.xhtml",
        "data_format": "HTML / XML (über OpenSanctions als CSV)",
        "update_frequency": "anlassbezogen",
        "language": "DE / FR / IT / EN",
        "color": "rose",
        "icon": "Mountain",
        "tag": "CH",
        "use_in_audit": (
            "Bei Schweizer Geschäftsbeziehungen ergänzend prüfen — die "
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
    _actor: dict = Depends(require_admin),
) -> SearchResponse:
    """Multi-Source-Fuzzy-Suche gegen alle indexierten Sanctions-Listen.

    Aus DSGVO-Gründen Admin-Only: die Fuzzy-Schwelle 65 % produziert in einer
    Demo-Plattform leicht False-Positives für unbeteiligte Namensvettern, und
    die Verarbeitung von Personennamen Dritter ist außerhalb der eigentlichen
    Prüfung nicht durch die Zweckbindung (Art. 5 Abs. 1 lit. b DSGVO) gedeckt.

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
                f"Verfügbar: {', '.join(sorted(valid))}",
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


# ── Export ────────────────────────────────────────────────────────────────────


_SANCTIONS_EXPORT_PFLICHTHINWEIS = (
    "Datenstand abhängig vom letzten Refresh pro Quelle (siehe "
    "GET /api/sanctions/sources). Der lokale Index wird aus den OpenSanctions-"
    "CSVs gebaut. Treffer sind nicht rechtlich verbindlich — vor Maßnahmen "
    "stets die offizielle Quelle (EU FSF, UN-Liste, OFAC, OFSI, SECO) prüfen."
)

_SANCTIONS_EXPORT_COLUMNS = [
    "id", "source_key", "source_display_name",
    "schema_type", "name", "score", "confidence",
    "matched_field", "matched_on",
    "aliases", "birth_date", "countries", "addresses",
    "identifiers", "sanctions", "program_ids",
    "first_seen", "last_seen",
]


def _hit_to_dict(hit) -> dict:
    """Vereinheitlicht ein SanctionsHit-Objekt zu einem Export-Dict."""
    return {
        "id": hit.id,
        "source_key": hit.source_key,
        "source_display_name": hit.source_display_name,
        "schema_type": hit.schema,
        "name": hit.name,
        "score": round(float(hit.score), 1),
        "confidence": hit.confidence,
        "matched_field": hit.matched_field,
        "matched_on": hit.matched_on,
        "aliases": hit.aliases,
        "birth_date": hit.birth_date,
        "countries": hit.countries,
        "addresses": hit.addresses,
        "identifiers": hit.identifiers,
        "sanctions": hit.sanctions,
        "program_ids": hit.program_ids,
        "first_seen": hit.first_seen,
        "last_seen": hit.last_seen,
    }


def _safe_filename_part(value: str) -> str:
    """Macht aus einem Suchbegriff einen sicheren Dateinamen-Bestandteil."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())[:40]
    return cleaned or "alle"


@router.get("/export")
def export_sanctions_search(
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    q: str = Query(..., min_length=2, description="Suchbegriff (Name oder Alias)"),
    limit: int = Query(50, ge=1, le=500),
    min_score: float = Query(65.0, ge=40.0, le=100.0),
    schema_filter: str | None = Query(None, description='"Person" oder "Organization"'),
    sources: str | None = Query(
        None,
        description=(
            "Komma-Liste der Source-Keys (z.B. 'eu_fsf,un_sc'). "
            "Default: alle aktivierten Quellen."
        ),
    ),
    _actor: dict = Depends(require_admin),
):
    """Export der Sanctions-Suche in CSV / XLSX / PDF.

    Aus DSGVO-Gründen Admin-Only — siehe Erläuterung bei /search.

    Selbe Filter-Parameter wie GET /search. Pflichthinweis und Datenstand pro
    Quelle werden in den Export aufgenommen (CSV als Kommentarzeilen, XLSX in
    eigenem Sheet "Hinweise", PDF im Footer).
    """
    svc = get_multi_service()
    if not svc.is_any_loaded():
        raise HTTPException(503, "Kein Sanctions-Index geladen.")

    source_keys = _parse_sources_param(sources)
    if source_keys is not None:
        valid = set(svc.indices.keys())
        source_keys = [k for k in source_keys if k in valid]
        if not source_keys:
            raise HTTPException(
                400,
                f"Keine bekannten Source-Keys angegeben. "
                f"Verfügbar: {', '.join(sorted(valid))}",
            )

    hits = svc.search(
        q,
        limit=limit,
        min_score=min_score,
        schema=schema_filter,
        sources=source_keys,
    )
    rows = [_hit_to_dict(h) for h in hits]

    sources_searched = source_keys or list(svc.indices.keys())
    stats_aggregated = svc.stats()
    per_source_metadata: dict[str, str] = {}
    for s in stats_aggregated.get("per_source", []):
        key = s.get("source_key") or ""
        if not key:
            continue
        loaded_at = s.get("loaded_at") or "—"
        per_source_metadata[key] = (
            f"{int(s.get('total_entries') or 0)} Einträge · "
            f"geladen {loaded_at}"
        )

    metadata = {
        "Suchbegriff": q,
        "Trefferzahl": str(len(rows)),
        "Schwellenwert": f"{min_score:.1f}",
        "Schema-Filter": schema_filter or "alle",
        "Listen-Filter": ", ".join(sources_searched) or "alle",
    }
    metadata.update(per_source_metadata)

    safe_q = _safe_filename_part(q)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if format == "xlsx":
        from services.excel_export import (
            XLSX_MEDIA_TYPE,
            make_xlsx,
            xlsx_response_headers,
        )
        xlsx_bytes = make_xlsx(
            rows,
            sheet_name="Sanktionen-Treffer",
            headers=_SANCTIONS_EXPORT_COLUMNS,
            table_name="SanktionenTreffer",
            pflichthinweis=_SANCTIONS_EXPORT_PFLICHTHINWEIS,
            metadata=metadata,
            notes_title="Sanktionsprüfung · Hinweise",
        )
        filename = f"sanktionen_search_{safe_q}_{timestamp}.xlsx"
        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type=XLSX_MEDIA_TYPE,
            headers=xlsx_response_headers(filename),
        )

    if format == "pdf":
        return _stream_sanctions_pdf(rows, metadata)

    # CSV-Export (default)
    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM für Excel
    buf.write(f"# FlowWorkshop · Sanctions-Search-Export · {datetime.utcnow().isoformat()}Z\n")
    buf.write(f"# {_SANCTIONS_EXPORT_PFLICHTHINWEIS}\n")
    buf.write(f"# Suchbegriff: {q}\n")
    buf.write(f"# Schwelle: {min_score:.1f}  ·  Schema-Filter: {schema_filter or 'alle'}\n")
    buf.write(f"# Listen-Filter: {', '.join(sources_searched) or 'alle'}\n")
    for key, info in per_source_metadata.items():
        buf.write(f"# Datenstand {key}: {info}\n")

    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_SANCTIONS_EXPORT_COLUMNS)
    for d in rows:
        cells = []
        for k in _SANCTIONS_EXPORT_COLUMNS:
            v = d.get(k)
            if v is None:
                cells.append("")
            elif isinstance(v, (list, tuple)):
                cells.append(" | ".join(str(x) for x in v if x))
            else:
                cells.append(str(v))
        writer.writerow(cells)

    filename = f"sanktionen_search_{safe_q}_{timestamp}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _stream_sanctions_pdf(rows: list[dict], metadata: dict[str, str]) -> StreamingResponse:
    """Sanctions-PDF analog zu state_aid: pymupdf, A4 quer, Pflichthinweis im Footer."""
    try:
        import fitz  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            501,
            f"PDF-Export nicht verfügbar: pymupdf nicht installiert ({exc}).",
        ) from exc

    doc = fitz.open()
    page = doc.new_page(width=842, height=595)  # A4 Querformat
    margin = 28
    cursor_y = margin
    line_height = 11

    def _write(text: str, *, size: int = 9, bold: bool = False) -> None:
        nonlocal cursor_y, page
        if cursor_y > page.rect.height - margin - line_height:
            page = doc.new_page(width=842, height=595)
            cursor_y = margin
        font = "helvB" if bold else "helv"
        try:
            page.insert_text(
                (margin, cursor_y), text, fontsize=size, fontname=font,
            )
        except Exception:
            page.insert_text((margin, cursor_y), text, fontsize=size)
        cursor_y += line_height + (size - 9)

    _write("FlowWorkshop · Sanktionsprüfung", size=14, bold=True)
    _write(datetime.utcnow().strftime("Erstellt: %Y-%m-%d %H:%M UTC"), size=9)
    for k, v in metadata.items():
        _write(f"  · {k}: {v}", size=8)
    cursor_y += line_height // 2

    _write(f"Treffer: {len(rows)}", size=10, bold=True)
    cursor_y += line_height // 2

    for row in rows:
        _write(
            f"{row.get('name', '')} · {row.get('schema_type', '')} · Score "
            f"{row.get('score', 0):.1f} ({row.get('confidence', '')}) · "
            f"{row.get('source_display_name') or row.get('source_key', '')}",
            size=9, bold=True,
        )
        if row.get("aliases"):
            aliases = row["aliases"]
            if isinstance(aliases, (list, tuple)):
                aliases_str = ", ".join(str(a) for a in aliases[:6] if a)
            else:
                aliases_str = str(aliases)
            if aliases_str:
                _write(f"   Aliase: {aliases_str[:160]}", size=8)
        if row.get("countries"):
            _write(f"   Länder: {row['countries'][:160]}", size=8)
        if row.get("sanctions"):
            _write(f"   Rechtsakt: {row['sanctions'][:160]}", size=8)
        cursor_y += 2

    _write("", size=8)
    _write(_SANCTIONS_EXPORT_PFLICHTHINWEIS, size=7)

    pdf_bytes = doc.tobytes()
    doc.close()

    suchbegriff = metadata.get("Suchbegriff", "alle")
    filename = (
        f"sanktionen_search_{_safe_filename_part(suchbegriff)}_"
        f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
            f"Verfügbar: {', '.join(sorted(svc.indices.keys()))}",
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
