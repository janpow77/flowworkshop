"""
flowworkshop · services/state_aid_audit_report.py

Cross-Register-Pruefbericht: aggregiert State-Aid + Beneficiaries + Sanctions
zu einem strukturierten Bericht. Keine Bewertung — neutral, faktisch.

Wichtig:
- Keine Begriffe wie "Risiko", "auffaellig", "verdaechtig" im Code/Output.
- Stattdessen: "Querbezug", "Beobachtung", "Zusammenfassung".
- Cross-References sind NEUTRAL aufgelistete Beobachtungen mit Evidenz —
  keine Severity, kein Score. Der Pruefer urteilt selbst.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.orm import Session

from models.state_aid import StateAidAward, StateAidSource
from services.state_aid_service import (
    _smart_fuzzy_score,
    fuzzy_match_company,
    normalize_company_name,
)

log = logging.getLogger(__name__)


# ── Datenklassen ─────────────────────────────────────────────────────────────


@dataclass
class StateAidSection:
    """Sektion State-Aid (EU TAM + nationale Register)."""
    total_count: int = 0
    total_amount_eur: float = 0.0
    awards: list[dict] = field(default_factory=list)
    by_year: list[dict] = field(default_factory=list)
    by_authority: list[dict] = field(default_factory=list)
    by_nuts: list[dict] = field(default_factory=list)
    by_instrument: list[dict] = field(default_factory=list)
    sa_references: list[str] = field(default_factory=list)
    case_urls: list[str] = field(default_factory=list)


@dataclass
class BeneficiariesSection:
    """Sektion Beguenstigtenverzeichnis (lokale Transparenzlisten)."""
    total_count: int = 0
    total_amount_eur: float = 0.0
    matches: list[dict] = field(default_factory=list)
    by_bundesland: list[dict] = field(default_factory=list)
    by_fonds: list[dict] = field(default_factory=list)


@dataclass
class SanctionsSection:
    """Sektion Sanktionslisten-Check (EU FSF lokal)."""
    total_hits: int = 0
    hits: list[dict] = field(default_factory=list)
    listing_sources: list[str] = field(default_factory=list)


@dataclass
class CorporateGroupSection:
    """Konzernverbund-Erweiterung des Audit-Reports (Item 2 der Mai-2026-
    Erweiterung).

    Faktisch, neutral. Listet primaere Firma + Mutter + Toechter aus
    GLEIF/Wikidata. Die Treffer aus den Tochterfirmen in State-Aid und
    Beneficiaries werden separat ausgewiesen — KEINE implizite Vermischung
    mit der Direkt-Suche.
    """
    primary_entity: dict | None = None
    ultimate_parent: dict | None = None
    direct_parent: dict | None = None
    children_count: int = 0
    children_top: list[dict] = field(default_factory=list)
    additional_state_aid_count: int = 0
    additional_state_aid_amount_eur: float = 0.0
    additional_state_aid_awards: list[dict] = field(default_factory=list)
    additional_beneficiaries_count: int = 0
    additional_beneficiaries_amount_eur: float = 0.0
    additional_beneficiaries: list[dict] = field(default_factory=list)
    coverage_note: str = ""
    sources_used: list[str] = field(default_factory=list)
    fetched_at: datetime | None = None
    cache_meta: dict = field(default_factory=dict)


@dataclass
class CrossReference:
    """NEUTRALE Beobachtung, keine Bewertung.

    `type` beschreibt die Art des Querbezugs, `description` ist eine
    sachliche Erlaeuterung, `evidence` enthaelt die zugrundeliegenden
    Datensaetze (welches Feld in welchem Register).

    Layer-B-Felder (LLM-Re-Ranker, services/audit_match_verifier.py):
        - ``filtered_by_llm``: True, wenn das LLM ``match='no'`` zurueckgab.
          Der Eintrag bleibt in der Liste (Audit-Trail), wird im PDF aber
          ausgeblendet. UI/JSON-Konsumenten koennen Filterung selbst steuern.
        - ``llm_confirmed``: True, wenn das LLM ``match='yes'`` zurueckgab.
          Reine Markierung — KEIN automatisches Weiterleiten an Pruefer.
    """
    type: Literal[
        "name_match_state_aid_beneficiary",
        "identifier_match",
        "sa_reference_kom_case_linked",
        "duplicate_award_within_year",
        "address_match",
        # Layer A — Embedding-Layer (semantische Nachbarn). Strikt neutral:
        # KEIN Identitaets-Beweis, sondern Hinweis auf verwandte Vorgaenge.
        "semantic_neighbor_state_aid",
        "semantic_neighbor_beneficiary",
        "semantic_neighbor_sanctions",
    ]
    description: str
    evidence: dict
    # Layer B — LLM-Re-Ranker (audit_match_verifier.py). Default False, wird
    # nur gesetzt, wenn ``include_llm_verification=True`` an
    # ``build_audit_report`` uebergeben wurde.
    filtered_by_llm: bool = False
    llm_confirmed: bool = False


@dataclass
class SourceExplanation:
    """Erlaeuterung zu einer der drei Datenquellen.

    `last_data_update` ist optional — wenn die Quelle keine Datums-Metadaten
    hinterlegt (z.B. lokale Transparenzlisten), bleibt das Feld None.
    `record_count` ist die Anzahl Records in der lokalen Kopie.
    """
    name: str
    url: str
    description: str
    last_data_update: datetime | None
    record_count: int


@dataclass
class EntityResolutionSection:
    """Phase 6d — Master-Entity-Aufloesung des Suchbegriffs.

    Wenn die Suche auf eine ``CompanyEntity`` aufgeloest werden konnte,
    enthaelt diese Sektion den kanonischen Namen, alle bekannten Identifier,
    Adressen und Konzern-Position. Dient als Anker fuer den Pruefer:
    statt fuzzy-Score zu vertrauen, sieht er die persistierte Master-
    Identitaet.

    Bleibt None, wenn keine Entity zur Suche gefunden wurde (z.B. weil das
    Rebuild-Skript noch nicht durchgelaufen ist).
    """
    entity_id: int | None = None
    canonical_name: str | None = None
    canonical_name_normalized: str | None = None
    entity_type: str | None = None
    country_code: str | None = None
    lei: str | None = None
    identifiers: dict | None = None
    addresses: list[dict] | None = None
    aliases: list[str] = field(default_factory=list)
    parent_entity_id: int | None = None
    parent_entity_name: str | None = None
    ultimate_parent_entity_id: int | None = None
    ultimate_parent_entity_name: str | None = None
    matches_total: int = 0
    matches_state_aid: int = 0
    matches_beneficiary: int = 0
    matches_sanctions: int = 0
    coverage_note: str = ""


@dataclass
class PersonCheckEntry:
    """Ergebnis eines Sanctions-Checks fuer eine vom Pruefer eingegebene Person.

    Wird je Person genau einmal angelegt — auch wenn die Person in mehreren
    Listen erscheint, sammeln wir alle Treffer in ``hits`` und leiten daraus
    ``matched_sources`` und ``has_match`` ab.
    """
    name: str
    role: str | None
    hits: list[dict] = field(default_factory=list)            # SanctionsHit-Liste, schema='Person'
    matched_sources: list[str] = field(default_factory=list)  # ['un_sc', 'us_ofac_sdn']
    has_match: bool = False                                    # bei min_score >= 80


@dataclass
class PersonsCheckSection:
    """Personen-Sanctions-Sektion des Audit-Reports.

    Strikt neutral. Wir checken jede Person gegen alle 5 Sanctions-Listen
    (schema='Person'), zaehlen Treffer und merken uns, in welchen Listen sie
    erschienen sind. Keine Severity, kein Risiko-Score — nur Fakt + Coverage-
    Hinweis.
    """
    persons_checked: list[PersonCheckEntry] = field(default_factory=list)
    total_persons: int = 0
    persons_with_match: int = 0
    coverage_note: str = ""


@dataclass
class CoverageEntry:
    """Ein einzelner Coverage-Eintrag pro Datenquelle.

    Coverage-Status (``completeness_note``) ist eine WARTUNGS-Aussage ueber
    den lokalen Datenbestand — KEINE Risiko-Aussage ueber die geprueften
    Firmen. Der Status zeigt, ob der lokale Cache aktuell und vollstaendig
    ist; er sagt nichts darueber, ob in der Quelle relevante Treffer waren.
    """
    source_module: Literal["state_aid", "beneficiary", "sanctions"]
    source_key: str
    display_name: str
    local_count: int
    expected_count: int | None
    coverage_percent: float | None  # None wenn expected_count fehlt
    last_harvest_at: datetime | None
    completeness_note: str          # 'vollstaendig' | 'partiell' | 'unbekannt'


@dataclass
class CoverageSection:
    """Wartungs-Ampel ueber alle Datenquellen.

    ``overall_completeness`` ist die WARTUNGS-Ampel:
    - "green":  alle Quellen >= 95%
    - "yellow": mindestens eine Quelle 50..95% oder unbekannt
    - "red":    mindestens eine Quelle < 50% oder leerer lokaler Bestand

    Diese Ampel sagt NICHTS ueber Risiko der geprueften Firma — sie sagt
    nur, ob der Pruefer dem lokalen Bestand vertrauen kann oder zusaetz-
    lich beim Original-Register nachschauen sollte.
    """
    entries: list[CoverageEntry] = field(default_factory=list)
    overall_completeness: Literal["green", "yellow", "red"] = "yellow"


@dataclass
class AuditReportData:
    """Gesamtdaten fuer den Cross-Register-Pruefbericht."""
    query: str
    issued_at: datetime
    auftraggeber: str | None
    pruefer_name: str | None

    state_aid: StateAidSection
    beneficiaries: BeneficiariesSection
    sanctions: SanctionsSection
    cross_references: list[CrossReference]
    data_freshness: dict

    # Neu (Mai 2026): explizite Quellen-Erlaeuterung + Disclaimer fuer
    # UI-Live-Vorschau und PDF.
    sources_explanation: list[SourceExplanation] = field(default_factory=list)
    disclaimer: str = ""

    # Konzernverbund-Erweiterung (Mai 2026, Item 2): nur gesetzt, wenn
    # `include_corporate_group=True` an `build_audit_report` uebergeben wurde.
    # Die Sektion bleibt sonst None — JSON-Konsumenten muessen explizit
    # auf None pruefen.
    corporate_group: CorporateGroupSection | None = None

    # Phase 6d: Entity-Resolution-Anker (kanonische Master-Entity).
    entity_resolution: EntityResolutionSection | None = None

    # Polish-Runde 3 (Mai 2026, Item 1): Personen-Sanctions-Sektion. Nur
    # gesetzt, wenn der Pruefer mindestens eine Person uebergeben hat —
    # sonst None.
    persons_check: PersonsCheckSection | None = None

    # Polish-Runde 3 (Mai 2026, Item 5): Coverage / Vollstaendigkeit pro
    # Quelle. Wartungs-Aussage, keine Risiko-Bewertung.
    coverage: CoverageSection | None = None

    # Layer B (Mai 2026): LLM-Re-Ranker fuer ambivalente Cross-References.
    # Nur gesetzt, wenn `include_llm_verification=True` an `build_audit_report`
    # uebergeben wurde. Enthaelt pro Verifikation ein strukturiertes Verdict
    # (yes/no/unknown + confidence + 1-Satz-Begruendung). Die einzelnen
    # Verdicts sind zusaetzlich an den jeweiligen ``CrossReference.evidence
    # ['llm_verdict']`` angehaengt.
    llm_verification: "Any | None" = None  # services.audit_match_verifier.LlmVerificationResult

    def to_dict(self) -> dict:
        """JSON-serialisierbares Dict (z.B. fuer UI-Live-Vorschau)."""
        return {
            "query": self.query,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "auftraggeber": self.auftraggeber,
            "pruefer_name": self.pruefer_name,
            "state_aid": asdict(self.state_aid),
            "beneficiaries": asdict(self.beneficiaries),
            "sanctions": asdict(self.sanctions),
            "cross_references": [asdict(c) for c in self.cross_references],
            "data_freshness": self.data_freshness,
            "sources_explanation": [
                {
                    "name": s.name,
                    "url": s.url,
                    "description": s.description,
                    "last_data_update": (
                        s.last_data_update.isoformat()
                        if s.last_data_update else None
                    ),
                    "record_count": s.record_count,
                }
                for s in self.sources_explanation
            ],
            "disclaimer": self.disclaimer,
            "corporate_group": (
                _corporate_group_section_to_dict(self.corporate_group)
                if self.corporate_group is not None else None
            ),
            "entity_resolution": (
                asdict(self.entity_resolution)
                if self.entity_resolution is not None else None
            ),
            "persons_check": (
                asdict(self.persons_check)
                if self.persons_check is not None else None
            ),
            "coverage": (
                _coverage_section_to_dict(self.coverage)
                if self.coverage is not None else None
            ),
            "llm_verification": (
                self.llm_verification.to_dict()
                if self.llm_verification is not None
                and hasattr(self.llm_verification, "to_dict")
                else None
            ),
        }


# ── Helper ────────────────────────────────────────────────────────────────────


def _corporate_group_section_to_dict(s: "CorporateGroupSection | None") -> dict | None:
    """Serialisiert die CorporateGroupSection JSON-tauglich.

    `fetched_at` wird in ISO-Form ausgegeben; alle anderen Felder sind
    bereits einfache Typen.
    """
    if s is None:
        return None
    out = asdict(s)
    if isinstance(s.fetched_at, datetime):
        out["fetched_at"] = s.fetched_at.isoformat()
    return out


def _coverage_section_to_dict(s: "CoverageSection | None") -> dict | None:
    """Serialisiert die CoverageSection JSON-tauglich.

    ``last_harvest_at`` pro Eintrag wird in ISO-Form ausgegeben.
    """
    if s is None:
        return None
    out = asdict(s)
    for entry, raw_entry in zip(out.get("entries") or [], s.entries):
        if isinstance(raw_entry.last_harvest_at, datetime):
            entry["last_harvest_at"] = raw_entry.last_harvest_at.isoformat()
    return out


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _serialize_award_for_report(award: StateAidAward) -> dict:
    """Reduzierte Award-Repraesentation fuer den Bericht."""
    return {
        "id": award.id,
        "beneficiary_name": award.beneficiary_name,
        "beneficiary_identifier": award.beneficiary_identifier,
        "country_code": award.country_code,
        "country_name": award.country_name,
        "nuts_code": award.nuts_code,
        "nuts_label": award.nuts_label,
        "aid_amount_eur": _to_float(award.aid_amount_eur),
        "aid_currency": award.aid_currency,
        "aid_instrument": award.aid_instrument,
        "aid_objective": award.aid_objective,
        "aid_measure_title": award.aid_measure_title,
        "granting_authority": award.granting_authority,
        "granting_date": award.granting_date.isoformat() if award.granting_date else None,
        "publication_date": award.publication_date.isoformat() if award.publication_date else None,
        "sa_reference": award.sa_reference,
        "case_url": award.case_url,
        "decision_url": award.decision_url,
        "source_key": award.source_key,
        "source_url": award.source_url,
    }


def _aggregate_top(
    items: list[dict], key: str, *,
    amount_key: str = "aid_amount_eur",
    limit: int = 10,
) -> list[dict]:
    """Top-N Aggregation: Count + Summe pro Schluessel."""
    bucket: dict[str, dict] = {}
    for it in items:
        k = it.get(key)
        if not k:
            continue
        b = bucket.setdefault(k, {"key": k, "count": 0, "total_eur": 0.0})
        b["count"] += 1
        b["total_eur"] += _to_float(it.get(amount_key))
    rows = sorted(
        bucket.values(),
        key=lambda r: (-r["total_eur"], -r["count"], r["key"]),
    )
    return rows[:limit]


def _aggregate_by_year(items: list[dict]) -> list[dict]:
    """Aggregation pro Jahr (granting_date)."""
    bucket: dict[int, dict] = {}
    for it in items:
        gd = it.get("granting_date")
        if not gd:
            continue
        try:
            year = int(str(gd)[:4])
        except (TypeError, ValueError):
            continue
        b = bucket.setdefault(year, {"year": year, "count": 0, "total_eur": 0.0})
        b["count"] += 1
        b["total_eur"] += _to_float(it.get("aid_amount_eur"))
    return sorted(bucket.values(), key=lambda r: r["year"])


def _aggregate_by_nuts1(items: list[dict], limit: int = 10) -> list[dict]:
    """NUTS-1-Aggregation: nuts_code wird auf 3 Zeichen gekuerzt (z.B. DE2)."""
    bucket: dict[str, dict] = {}
    for it in items:
        nc = it.get("nuts_code")
        if not nc or len(str(nc)) < 2:
            continue
        # NUTS-1 = 3 Zeichen (Land-Code 2 + 1 Ziffer/Buchstabe)
        n1 = str(nc)[:3] if len(str(nc)) >= 3 else str(nc)
        b = bucket.setdefault(n1, {
            "nuts_code": n1, "count": 0, "total_eur": 0.0,
        })
        b["count"] += 1
        b["total_eur"] += _to_float(it.get("aid_amount_eur"))
    rows = sorted(
        bucket.values(),
        key=lambda r: (-r["total_eur"], -r["count"], r["nuts_code"]),
    )
    return rows[:limit]


# ── Hauptfunktion ─────────────────────────────────────────────────────────────


def build_audit_report(
    db: Session,
    query: str,
    *,
    country_code: str | None = None,
    auftraggeber: str | None = None,
    pruefer_name: str | None = None,
    include_corporate_group: bool = False,
    corporate_group_max_children: int = 50,
    corporate_group_timeout_s: float = 30.0,
    persons: list[dict] | None = None,
    include_semantic_neighbors: bool = False,
    semantic_neighbors_top_n: int = 5,
    semantic_min_similarity: float = 0.7,
    include_llm_verification: bool = False,
    llm_verify_score_min: float = 75.0,
    llm_verify_score_max: float = 89.0,
    llm_verify_max: int = 20,
    llm_verify_overall_timeout_s: float = 240.0,
    pruefer_user_id: str | None = None,
) -> AuditReportData:
    """Aggregiert alle drei Register zu einem Pruefbericht.

    Cross-Reference-Logik (alle NEUTRAL, keine Bewertung):
    - Gleicher (normalisierter) Name in State-Aid und Beneficiaries
      → name_match_state_aid_beneficiary
    - Gleicher Identifier (HRB, Steuer-Nr.) in beiden Registern
      → identifier_match
    - SA-Referenz mit verlinktem KOM-Fall → sa_reference_kom_case_linked
    - 5+ Awards desselben Beguenstigten in 12-Monats-Fenster
      → duplicate_award_within_year
    - (Adress-Match wuerde kuenftig hier ergaenzt — derzeit nicht
      zuverlaessig, weil State-Aid keine Adressfelder fuehrt.)

    Sanctions-Treffer werden als Fakt aufgelistet, NICHT als Risiko bewertet.
    """
    issued_at = datetime.utcnow()
    cc = country_code.upper() if country_code else None

    # ── State-Aid ────────────────────────────────────────────────────────────
    state_aid = StateAidSection()
    sa_award_objs: list[StateAidAward] = []
    try:
        sa_hits = fuzzy_match_company(
            db, query, limit=200, min_score=70.0, country_code=cc,
        )
        if sa_hits:
            sa_award_objs = (
                db.query(StateAidAward)
                .filter(StateAidAward.id.in_([h.award_id for h in sa_hits]))
                .all()
            )
            state_aid.awards = [_serialize_award_for_report(a) for a in sa_award_objs]
            state_aid.total_count = len(state_aid.awards)
            state_aid.total_amount_eur = sum(
                a.get("aid_amount_eur") or 0.0 for a in state_aid.awards
            )
            state_aid.by_year = _aggregate_by_year(state_aid.awards)
            state_aid.by_authority = _aggregate_top(
                state_aid.awards, "granting_authority", limit=10,
            )
            state_aid.by_nuts = _aggregate_by_nuts1(state_aid.awards, limit=10)
            state_aid.by_instrument = _aggregate_top(
                state_aid.awards, "aid_instrument", limit=10,
            )
            sa_refs = sorted({
                a["sa_reference"] for a in state_aid.awards
                if a.get("sa_reference")
            })
            state_aid.sa_references = sa_refs
            case_urls = sorted({
                a["case_url"] for a in state_aid.awards
                if a.get("case_url")
            })
            state_aid.case_urls = case_urls
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: State-Aid-Aggregation fehlgeschlagen")

    # ── Beneficiaries ────────────────────────────────────────────────────────
    beneficiaries = BeneficiariesSection()
    ben_records: list[dict] = []
    try:
        from services.dataframe_service import search_beneficiary_records
        ben_result = search_beneficiary_records(
            query=query, scope="company", limit=60, country_code=cc,
        )
        if isinstance(ben_result, dict):
            ben_records = (
                ben_result.get("records")
                or ben_result.get("results")
                or ben_result.get("entries")
                or []
            )
            # `records` enthaelt Einzeleintraege mit kosten/bundesland/fonds.
            # `companies` waere die aggregierte Sicht — wir nehmen `records`
            # damit wir pro Eintrag aktenzeichen + projekt fuehren koennen.
            companies_view = ben_result.get("companies") or []
            beneficiaries.total_count = len(ben_records)
            for r in ben_records:
                beneficiaries.matches.append({
                    "company_name": r.get("company_name") or "",
                    "project_name": r.get("project_name") or "",
                    "aktenzeichen": r.get("aktenzeichen") or "",
                    "location": r.get("location") or "",
                    "kosten": _to_float(r.get("kosten")),
                    "kosten_label": r.get("kosten_label") or "",
                    "source": r.get("source") or "",
                    "bundesland": r.get("bundesland") or "",
                    "fonds": r.get("fonds") or "",
                    "periode": r.get("periode") or "",
                    "country_code": r.get("country_code") or "",
                    "match_confidence": r.get("match_confidence") or "",
                    # NUTS-Code wird fuer den Address-Match-Cross-Reference
                    # (Polish-Runde 3, Aufgabe 2) gebraucht.
                    "nuts_code": r.get("nuts_code") or "",
                })
            beneficiaries.total_amount_eur = sum(
                m.get("kosten") or 0.0 for m in beneficiaries.matches
            )
            beneficiaries.by_bundesland = _aggregate_top(
                beneficiaries.matches, "bundesland",
                amount_key="kosten", limit=20,
            )
            beneficiaries.by_fonds = _aggregate_top(
                beneficiaries.matches, "fonds",
                amount_key="kosten", limit=20,
            )
            # Wenn `companies_view` da ist und `matches` leer waere,
            # alternative Anzeige aus `companies` ableiten.
            if not beneficiaries.matches and companies_view:
                for c in companies_view:
                    beneficiaries.matches.append({
                        "company_name": c.get("company_name") or "",
                        "project_name": "",
                        "aktenzeichen": "; ".join(c.get("aktenzeichen") or [])[:120],
                        "location": "; ".join(c.get("standorte") or [])[:120],
                        "kosten": _to_float(c.get("total_kosten")),
                        "kosten_label": c.get("total_kosten_label") or "",
                        "source": "; ".join(c.get("sources") or []),
                        "bundesland": "; ".join(c.get("bundeslaender") or []),
                        "fonds": "; ".join(c.get("fonds") or []),
                        "match_confidence": c.get("match_confidence") or "",
                    })
                beneficiaries.total_count = len(beneficiaries.matches)
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Beneficiaries-Aggregation fehlgeschlagen")

    # ── Sanctions (Multi-Source: EU FSF + UN + OFAC + OFSI + SECO) ──────────
    sanctions = SanctionsSection()
    try:
        from services.sanctions_service import get_multi_service
        svc = get_multi_service()
        if svc.is_any_loaded():
            # Top-20 ueber alle aktivierten Quellen aggregiert
            for h in svc.search(query, limit=20, min_score=80.0):
                sanctions.hits.append({
                    "id": h.id,
                    "schema": h.schema,
                    "name": h.name,
                    "matched_on": h.matched_on,
                    "matched_field": h.matched_field,
                    "score": h.score,
                    "confidence": h.confidence,
                    "aliases": list(h.aliases or [])[:8],
                    "countries": h.countries,
                    "addresses": h.addresses,
                    "identifiers": h.identifiers,
                    "sanctions": h.sanctions,
                    "program_ids": h.program_ids,
                    "source_key": h.source_key,
                    "source_display_name": h.source_display_name,
                })
            sanctions.total_hits = len(sanctions.hits)
            # listing_sources: alle Quellen, in denen Treffer vorkamen
            seen_sources: dict[str, str] = {}
            for hit in sanctions.hits:
                sk = hit.get("source_key") or ""
                if sk and sk not in seen_sources:
                    seen_sources[sk] = (
                        hit.get("source_display_name") or sk
                    )
            sanctions.listing_sources = list(seen_sources.values())
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Sanctions-Aggregation fehlgeschlagen")

    # ── Cross-References (neutrale Beobachtungen) ────────────────────────────
    cross_references = _build_cross_references(
        query=query,
        sa_award_objs=sa_award_objs,
        sa_dicts=state_aid.awards,
        beneficiaries=beneficiaries.matches,
    )

    # ── Address-Match Cross-References (Polish-Runde 3, Aufgabe 2) ──────────
    # Beobachtung: Beneficiary und State-Aid-Award haben den GLEICHEN
    # 3-stelligen NUTS-Prefix UND aehnlichen Namen (Score >= 80) UND gleiches
    # Bundesland. Nur Top-50 pro Seite — sonst quadratische Vergleiche.
    try:
        addr_refs = _build_address_match_cross_refs(
            sa_award_objs=sa_award_objs,
            beneficiaries=beneficiaries.matches,
        )
        cross_references.extend(addr_refs)
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Address-Match-Cross-Reference fehlgeschlagen")

    # ── Semantische Nachbarschaft (Layer A) ──────────────────────────────────
    # Optional: top-N semantisch aehnliche Records pro Modul. Strikt neutral —
    # KEIN Identitaets-Beweis, sondern Hinweis auf verwandte Vorgaenge. Wird
    # nur ausgefuehrt, wenn ``include_semantic_neighbors=True``. Bei fehlendem
    # Embedding-Index oder Gateway-Ausfall: graceful skip, kein Fehler.
    if include_semantic_neighbors:
        try:
            semantic_refs = _build_semantic_neighbor_cross_refs(
                db,
                query=query,
                top_n=int(semantic_neighbors_top_n),
                min_similarity=float(semantic_min_similarity),
                exclude_state_aid_ids={
                    a.id for a in sa_award_objs if a and a.id
                },
                exclude_beneficiary_ids={
                    int(m.get("id"))
                    for m in beneficiaries.matches
                    if m.get("id") is not None
                    and str(m.get("id")).isdigit()
                },
            )
            cross_references.extend(semantic_refs)
        except Exception:  # noqa: BLE001
            log.exception(
                "Audit-Report: Semantische-Nachbarschaft fehlgeschlagen — "
                "weiter ohne diese Sektion.",
            )

    # ── Datenstand pro Quelle ────────────────────────────────────────────────
    data_freshness = _collect_data_freshness(db)

    # ── Quellen-Erlaeuterung + Disclaimer (Live-Preview + PDF) ──────────────
    sources_explanation = _collect_sources_explanation(db)
    disclaimer = _build_disclaimer_text()

    # ── Konzernverbund-Erweiterung (Mai 2026, Item 2) ────────────────────────
    corporate_group_section: CorporateGroupSection | None = None
    corporate_group_obj = None
    if include_corporate_group:
        try:
            corporate_group_section, corporate_group_obj = (
                _build_corporate_group_section_with_obj(
                    db, query,
                    country_code=cc,
                    primary_state_aid_award_ids={
                        a.id for a in sa_award_objs if a and a.id
                    },
                    primary_beneficiaries=beneficiaries.matches,
                    max_children=corporate_group_max_children,
                    timeout_seconds=corporate_group_timeout_s,
                )
            )
        except Exception:  # noqa: BLE001
            log.exception("Audit-Report: Konzernverbund-Sektion fehlgeschlagen")

    # ── Entity-Resolution (Phase 6d) ─────────────────────────────────────────
    # Findet die kanonische Master-Entity, falls Phase-6d-Rebuild gelaufen
    # ist. Nicht-blockierend — der Bericht funktioniert auch ohne.
    entity_section: "EntityResolutionSection | None" = None
    try:
        entity_section = _build_entity_resolution_section(
            db, query, country_code=cc,
        )
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Entity-Resolution-Sektion fehlgeschlagen")
    # Cross-References ggf. mit entity_id anreichern
    if entity_section is not None and entity_section.entity_id:
        for cr in cross_references:
            if cr.evidence is None:
                continue
            cr.evidence["entity_id"] = entity_section.entity_id
            cr.evidence["entity_canonical_name"] = (
                entity_section.canonical_name or ""
            )

    # Konzernverbund-Hierarchie persistent in der Entity-Tabelle verankern.
    # (Wenn `include_corporate_group=True` und ein Group-Objekt vorliegt.)
    if corporate_group_obj is not None:
        try:
            from services.entity_resolution import (
                link_corporate_group_to_entities,
            )
            link_stats = link_corporate_group_to_entities(
                db, corporate_group_obj,
            )
            db.commit()
            if entity_section is not None and link_stats.get(
                "primary_entity_id",
            ):
                entity_section.coverage_note = (
                    f"Konzernverbund verankert: "
                    f"{link_stats.get('entities_created', 0)} neue Entities, "
                    f"{link_stats.get('hierarchies_set', 0)} Hierarchie-"
                    f"Verknuepfungen."
                )
        except Exception:  # noqa: BLE001
            log.exception(
                "Audit-Report: Konzernverbund-Persistierung fehlgeschlagen",
            )
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass

    # ── Personen-Sanctions-Check (Polish-Runde 3, Aufgabe 1) ─────────────────
    persons_check_section: PersonsCheckSection | None = None
    if persons:
        try:
            persons_check_section = _build_persons_check_section(persons)
        except Exception:  # noqa: BLE001
            log.exception("Audit-Report: Personen-Check fehlgeschlagen")
            persons_check_section = PersonsCheckSection(
                persons_checked=[],
                total_persons=0,
                persons_with_match=0,
                coverage_note=(
                    "Personen-Check fehlgeschlagen — bitte Logs pruefen."
                ),
            )

    # ── Coverage / Vollstaendigkeit (Polish-Runde 3, Aufgabe 3) ──────────────
    coverage_section: CoverageSection | None = None
    try:
        coverage_section = _build_coverage_section(db)
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Coverage-Sektion fehlgeschlagen")

    # ── LLM-Verifikation (Layer B) ───────────────────────────────────────────
    # Optionale Pruefung der ambivalenten Cross-References durch das LLM.
    # Nur wenn ``include_llm_verification=True``. Bei Fehlern: graceful skip,
    # der Bericht bleibt vollstaendig nutzbar.
    llm_verification_result = None
    if include_llm_verification:
        try:
            llm_verification_result = _run_llm_verification(
                cross_references,
                score_min=float(llm_verify_score_min),
                score_max=float(llm_verify_score_max),
                max_to_verify=int(llm_verify_max),
                overall_timeout_s=float(llm_verify_overall_timeout_s),
                pruefer_user_id=pruefer_user_id,
            )
        except Exception:  # noqa: BLE001
            log.exception(
                "Audit-Report: LLM-Verifikation fehlgeschlagen — "
                "weiter ohne diese Sektion.",
            )

    return AuditReportData(
        query=query,
        issued_at=issued_at,
        auftraggeber=auftraggeber,
        pruefer_name=pruefer_name,
        state_aid=state_aid,
        beneficiaries=beneficiaries,
        sanctions=sanctions,
        cross_references=cross_references,
        data_freshness=data_freshness,
        sources_explanation=sources_explanation,
        disclaimer=disclaimer,
        corporate_group=corporate_group_section,
        entity_resolution=entity_section,
        persons_check=persons_check_section,
        coverage=coverage_section,
        llm_verification=llm_verification_result,
    )


# ── LLM-Verifikation (Layer B) ───────────────────────────────────────────────


def _run_llm_verification(
    cross_references: list[CrossReference],
    *,
    score_min: float,
    score_max: float,
    max_to_verify: int,
    overall_timeout_s: float,
    pruefer_user_id: str | None,
) -> "Any | None":
    """Synchroner Wrapper um den asynchronen Re-Ranker.

    Wir laufen in einem synchronen FastAPI-Endpoint und muessen das Async-
    Coroutine entsprechend ausfuehren. Bei einem bereits laufenden Event-
    Loop (z.B. Tests im pytest-asyncio-Modus) faellt diese Funktion auf
    ``asyncio.run()`` in einem Worker-Thread zurueck.

    Liefert das ``LlmVerificationResult`` (oder ``None`` bei vollstaendigem
    Fehler).
    """
    try:
        from services.audit_match_verifier import (
            log_verdict_to_db,
            verify_cross_references,
        )
    except Exception:  # noqa: BLE001
        log.exception("LLM-Verifier-Service nicht importierbar")
        return None

    coro = verify_cross_references(
        cross_references,
        score_min=score_min,
        score_max=score_max,
        max_to_verify=max_to_verify,
        overall_timeout_s=overall_timeout_s,
    )
    result = _run_coro_blocking(coro)
    if result is None:
        return None

    # Verdicts an die jeweiligen Cross-References anhaengen + Filter-Flags
    # setzen. Persistierung pro Verdict in LlmQuestionLog (Audit-Trail).
    for verdict in result.verdicts:
        idx = verdict.cross_ref_index
        if idx < 0 or idx >= len(cross_references):
            continue
        cr = cross_references[idx]
        if cr.evidence is None:
            cr.evidence = {}
        cr.evidence["llm_verdict"] = {
            "match": verdict.match,
            "confidence": verdict.confidence,
            "reason": verdict.reason,
        }
        if verdict.match == "no":
            cr.filtered_by_llm = True
        elif verdict.match == "yes":
            cr.llm_confirmed = True
        # 'unknown' → keine Markierung, raw bleibt bestehen

        try:
            log_verdict_to_db(
                cross_ref=cr,
                verdict=verdict,
                user_id=pruefer_user_id,
            )
        except Exception:  # noqa: BLE001
            log.exception("LLM-Verdict-Logging fehlgeschlagen (idx=%d)", idx)

    return result


def _run_coro_blocking(coro: Any) -> Any:
    """Fuehrt eine Coroutine synchron aus.

    Standardweg: ``asyncio.run``. Wenn bereits ein Event-Loop laeuft (z.B.
    pytest-asyncio), starten wir das Coro in einem dedizierten Thread.
    """
    import asyncio as _asyncio
    try:
        return _asyncio.run(coro)
    except RuntimeError:
        # "asyncio.run() cannot be called from a running event loop"
        import threading
        result_holder: dict[str, Any] = {}

        def _runner() -> None:
            try:
                result_holder["result"] = _asyncio.run(coro)
            except Exception as exc:  # noqa: BLE001
                result_holder["error"] = exc

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        if "error" in result_holder:
            raise result_holder["error"]  # type: ignore[misc]
        return result_holder.get("result")


# ── Cross-References ──────────────────────────────────────────────────────────


def _build_cross_references(
    *,
    query: str,
    sa_award_objs: list[StateAidAward],
    sa_dicts: list[dict],
    beneficiaries: list[dict],
) -> list[CrossReference]:
    """Erkennt neutrale Querbezuege zwischen den Registern.

    KEIN Severity-Score. KEINE Bewertung. Nur Fakten + Evidenz.
    """
    refs: list[CrossReference] = []

    # 1. Name-Match: gleicher (normalisierter) Name in State-Aid + Beneficiaries
    if sa_dicts and beneficiaries:
        sa_norms: dict[str, str] = {}
        for a in sa_dicts:
            n = normalize_company_name(a.get("beneficiary_name") or "")
            if n:
                sa_norms.setdefault(n, a.get("beneficiary_name") or "")
        ben_norms: dict[str, str] = {}
        for b in beneficiaries:
            n = normalize_company_name(b.get("company_name") or "")
            if n:
                ben_norms.setdefault(n, b.get("company_name") or "")
        common = set(sa_norms.keys()) & set(ben_norms.keys())
        for n in sorted(common):
            refs.append(CrossReference(
                type="name_match_state_aid_beneficiary",
                description=(
                    f"Beguenstigter '{sa_norms[n]}' erscheint sowohl im "
                    f"EU-State-Aid-Register als auch im lokalen "
                    f"Beguenstigtenverzeichnis."
                ),
                evidence={
                    "shared_field": "beneficiary_name (normalisiert)",
                    "normalized_value": n,
                    "register_a": {
                        "register": "state_aid",
                        "value": sa_norms[n],
                    },
                    "register_b": {
                        "register": "beneficiaries",
                        "value": ben_norms[n],
                    },
                },
            ))

    # 2. Identifier-Match (HRB, Steuer-Nr.)
    if sa_award_objs and beneficiaries:
        sa_ids: dict[str, str] = {}
        for a in sa_award_objs:
            ident = (a.beneficiary_identifier or "").strip()
            if ident:
                sa_ids.setdefault(ident.casefold(), a.beneficiary_name or "")
        # Beneficiaries fuehren Aktenzeichen / Identifier in `aktenzeichen`
        for b in beneficiaries:
            ak = (b.get("aktenzeichen") or "").strip()
            if not ak:
                continue
            for sa_id, sa_name in sa_ids.items():
                if sa_id and sa_id in ak.casefold():
                    refs.append(CrossReference(
                        type="identifier_match",
                        description=(
                            f"Identifier '{sa_id}' findet sich sowohl im "
                            f"State-Aid-Award (Beguenstigter: {sa_name}) als "
                            f"auch im Aktenzeichen-Feld eines "
                            f"Beguenstigtenverzeichnis-Eintrags."
                        ),
                        evidence={
                            "shared_field": "beneficiary_identifier / aktenzeichen",
                            "shared_value": sa_id,
                            "register_a": {
                                "register": "state_aid",
                                "field": "beneficiary_identifier",
                                "value": sa_id,
                                "context": sa_name,
                            },
                            "register_b": {
                                "register": "beneficiaries",
                                "field": "aktenzeichen",
                                "value": ak,
                                "context": b.get("company_name") or "",
                            },
                        },
                    ))

    # 3. SA-Referenz mit KOM-Fall verlinkt
    seen_refs: set[str] = set()
    for a in sa_dicts:
        sa_ref = a.get("sa_reference")
        case_url = a.get("case_url")
        if sa_ref and case_url and sa_ref not in seen_refs:
            seen_refs.add(sa_ref)
            refs.append(CrossReference(
                type="sa_reference_kom_case_linked",
                description=(
                    f"SA-Referenz '{sa_ref}' verlinkt einen Beihilfen-Fall "
                    f"der Europaeischen Kommission."
                ),
                evidence={
                    "shared_field": "sa_reference",
                    "sa_reference": sa_ref,
                    "case_url": case_url,
                    "beneficiary": a.get("beneficiary_name"),
                },
            ))

    # 4. Mehrere Awards desselben Beguenstigten in 12-Monats-Fenster
    #    (Schwelle: 5+ Awards). Nur Beobachtung — Pruefer entscheidet,
    #    ob Vorhaben rechtlich zusammenhaengen.
    if sa_award_objs:
        per_ben: dict[str, list[StateAidAward]] = defaultdict(list)
        for a in sa_award_objs:
            n = normalize_company_name(a.beneficiary_name or "")
            if n and a.granting_date:
                per_ben[n].append(a)
        for n, awards_for_ben in per_ben.items():
            if len(awards_for_ben) < 5:
                continue
            # Sortieren nach granting_date
            awards_sorted = sorted(
                [x for x in awards_for_ben if x.granting_date],
                key=lambda x: x.granting_date,
            )
            # Sliding window: erste Datum, das mindestens 5 weitere Awards
            # in 365 Tagen hat
            for i, base in enumerate(awards_sorted):
                window_end = base.granting_date + timedelta(days=365)
                in_window = [
                    x for x in awards_sorted[i:]
                    if x.granting_date <= window_end
                ]
                if len(in_window) >= 5:
                    total_eur = sum(
                        _to_float(x.aid_amount_eur) for x in in_window
                    )
                    refs.append(CrossReference(
                        type="duplicate_award_within_year",
                        description=(
                            f"Beguenstigter '{awards_sorted[0].beneficiary_name}' "
                            f"hat im 12-Monats-Fenster ab "
                            f"{base.granting_date.isoformat()} "
                            f"{len(in_window)} State-Aid-Awards "
                            f"erhalten (Summe: {total_eur:,.2f} EUR)."
                        ),
                        evidence={
                            "shared_field": "beneficiary_name (normalisiert)",
                            "normalized_value": n,
                            "window_start": base.granting_date.isoformat(),
                            "window_end": min(
                                window_end,
                                in_window[-1].granting_date,
                            ).isoformat(),
                            "award_count": len(in_window),
                            "total_amount_eur": total_eur,
                            "award_ids": [x.id for x in in_window],
                        },
                    ))
                    break  # je Beguenstigter nur einen Eintrag

    return refs


# ── Address-Match Cross-Reference (Polish-Runde 3, Aufgabe 2) ────────────────


# Mapping NUTS-1-Praefix → menschenlesbares Bundesland fuer die Evidenz.
_NUTS1_TO_BUNDESLAND = {
    "DE1": "Baden-Wuerttemberg", "DE2": "Bayern", "DE3": "Berlin",
    "DE4": "Brandenburg", "DE5": "Bremen", "DE6": "Hamburg",
    "DE7": "Hessen", "DE8": "Mecklenburg-Vorpommern",
    "DE9": "Niedersachsen", "DEA": "Nordrhein-Westfalen",
    "DEB": "Rheinland-Pfalz", "DEC": "Saarland", "DED": "Sachsen",
    "DEE": "Sachsen-Anhalt", "DEF": "Schleswig-Holstein", "DEG": "Thueringen",
    # Oesterreich (NUTS-1)
    "AT1": "Ostoesterreich", "AT2": "Suedoesterreich", "AT3": "Westoesterreich",
}


def _nuts_prefix3(nuts_code: str | None) -> str | None:
    """Liefert den 3-stelligen NUTS-Prefix (Land + 1. Ebene)."""
    if not nuts_code:
        return None
    s = str(nuts_code).strip().upper()
    if len(s) < 3:
        return None
    return s[:3]


def _build_address_match_cross_refs(
    *,
    sa_award_objs: list[StateAidAward],
    beneficiaries: list[dict],
) -> list[CrossReference]:
    """Erkennt Adress-/NUTS-Uebereinstimmungen zwischen State-Aid und
    Beneficiaries.

    Bedingung fuer einen Treffer:
      - Beide Datensaetze haben einen ``nuts_code``
      - Gleicher 3-stelliger NUTS-Prefix (z.B. beide ``DE7``)
      - Fuzzy-Score Name >= 80 (smart_fuzzy_score)

    Volumen-Schutz: Wir nehmen die Top-50 Awards (nach Volumen, hoch->niedrig)
    und Top-50 Beneficiaries (nach Kosten, hoch->niedrig). Pro Paar wird der
    Score nur einmal berechnet.

    Eine Beobachtung pro (award_id, beneficiary_index) — KEIN Score-Boost im
    normalen Search-Result; nur als CrossReference zur Anzeige.
    """
    refs: list[CrossReference] = []
    if not sa_award_objs or not beneficiaries:
        return refs

    # Top-50 Awards nach Volumen
    top_awards = sorted(
        [a for a in sa_award_objs if a.nuts_code and a.beneficiary_name],
        key=lambda a: _to_float(a.aid_amount_eur),
        reverse=True,
    )[:50]
    # Top-50 Beneficiaries nach kosten
    top_bens = sorted(
        [b for b in beneficiaries if b.get("nuts_code") and b.get("company_name")],
        key=lambda b: _to_float(b.get("kosten")),
        reverse=True,
    )[:50]
    if not top_awards or not top_bens:
        return refs

    seen: set[tuple[str, str]] = set()
    for a in top_awards:
        a_pre = _nuts_prefix3(a.nuts_code)
        if not a_pre:
            continue
        a_name = a.beneficiary_name or ""
        a_norm = normalize_company_name(a_name)
        if not a_norm:
            continue
        for b in top_bens:
            b_pre = _nuts_prefix3(b.get("nuts_code"))
            if not b_pre or b_pre != a_pre:
                continue
            b_name = b.get("company_name") or ""
            b_norm = normalize_company_name(b_name)
            if not b_norm:
                continue
            # Smart-Score (gleiche Logik wie in fuzzy_match_company)
            score, _dbg = _smart_fuzzy_score(a_norm, b_norm)
            if score < 80.0:
                continue
            key = (str(a.id), b_norm)
            if key in seen:
                continue
            seen.add(key)
            bundesland = (
                _NUTS1_TO_BUNDESLAND.get(a_pre)
                or b.get("bundesland")
                or "—"
            )
            refs.append(CrossReference(
                type="address_match",
                description=(
                    f"State-Aid-Award fuer '{a_name}' und Beneficiary-Eintrag "
                    f"'{b_name}' liegen beide in NUTS-Region '{a_pre}' "
                    f"({bundesland}) und tragen aehnliche Namen "
                    f"(Score {score:.0f})."
                ),
                evidence={
                    "shared_field": "nuts_code (3-stellig) + beneficiary_name (fuzzy)",
                    "nuts_code": a_pre,
                    "bundesland": bundesland,
                    "name_similarity_score": round(float(score), 1),
                    "register_a": {
                        "register": "state_aid",
                        "value": a_name,
                        "nuts_code": a.nuts_code,
                    },
                    "register_b": {
                        "register": "beneficiaries",
                        "value": b_name,
                        "nuts_code": b.get("nuts_code"),
                        "bundesland": b.get("bundesland"),
                    },
                },
            ))
    return refs


# ── Semantische Nachbarschaft (Layer A, Embedding-Index) ─────────────────────


def _build_semantic_neighbor_cross_refs(
    db: Session,
    *,
    query: str,
    top_n: int = 5,
    min_similarity: float = 0.7,
    exclude_state_aid_ids: set[int] | None = None,
    exclude_beneficiary_ids: set[int] | None = None,
) -> list[CrossReference]:
    """Erkennt semantisch aehnliche Records pro Modul (Embedding-Layer).

    Strikt neutral: KEIN Identitaets-Beweis, sondern Hinweis auf verwandte
    Vorgaenge. Pro Modul werden die top-N Records mit ``cosine_similarity >=
    min_similarity`` ausgewiesen.

    Records, die bereits in den klassischen Cross-Refs auftauchen
    (``exclude_state_aid_ids`` / ``exclude_beneficiary_ids``), werden hier
    NICHT erneut gelistet.

    Bei fehlendem Embedding-Index oder Gateway-Ausfall liefert die Funktion
    eine leere Liste — der Bericht funktioniert ohne diese Sektion.
    """
    refs: list[CrossReference] = []

    try:
        from services.entity_embeddings import search_semantic
    except Exception:  # noqa: BLE001
        log.exception("Embedding-Service nicht verfuegbar")
        return refs

    type_by_module = {
        "state_aid": "semantic_neighbor_state_aid",
        "beneficiary": "semantic_neighbor_beneficiary",
        "sanctions": "semantic_neighbor_sanctions",
    }
    excluded_by_module: dict[str, set[int]] = {
        "state_aid": exclude_state_aid_ids or set(),
        "beneficiary": exclude_beneficiary_ids or set(),
        "sanctions": set(),
    }

    for module, ref_type in type_by_module.items():
        try:
            # Hole etwas mehr als top_n, damit Filter (excludes) nicht zu
            # leerem Ergebnis fuehren.
            results = search_semantic(
                db, query,
                module=module,
                limit=int(top_n) * 3,
                min_similarity=float(min_similarity),
            )
        except Exception:  # noqa: BLE001
            log.exception(
                "Semantische Suche fuer module=%s fehlgeschlagen.", module,
            )
            continue

        excluded = excluded_by_module.get(module) or set()
        kept = 0
        for r in results:
            if kept >= top_n:
                break
            sid_raw = r.get("source_record_id")
            try:
                sid_int = int(sid_raw) if sid_raw is not None else None
            except (TypeError, ValueError):
                sid_int = None
            if sid_int is not None and sid_int in excluded:
                continue

            cos = r.get("cosine_similarity")
            text_input = r.get("text_input") or ""

            refs.append(CrossReference(
                type=ref_type,  # type: ignore[arg-type]
                description=(
                    f"Vom KI-Embedding wurde im Modul '{module}' ein "
                    f"Record als semantisch aehnlich erkannt "
                    f"(cosine_similarity {cos}). Dies ist ein Hinweis "
                    f"auf einen verwandten Vorgang, kein Identitaets-Beweis."
                ),
                evidence={
                    "shared_field": "embedding (bge-m3)",
                    "cosine_similarity": cos,
                    "module": module,
                    "original_record_id": str(sid_raw) if sid_raw is not None else "",
                    "text_input": text_input[:300],
                    "model_name": r.get("model_name"),
                },
            ))
            kept += 1

    return refs


# ── Personen-Sanctions-Sektion (Polish-Runde 3, Aufgabe 1) ───────────────────


def _build_persons_check_section(
    persons: list[dict],
) -> PersonsCheckSection:
    """Sanctions-Check fuer eine Liste vom Pruefer eingegebener Personen.

    Pro Person wird gegen alle 5 Sanctions-Listen mit ``schema='Person'``
    gesucht. Strikt neutral, kein Severity-Marker. Treffer-Schwelle: Score
    >= 80 entspricht ``has_match=True`` — niedrigere Treffer werden zwar
    aufgelistet, aber nicht als Match gezaehlt.

    Coverage-Note: zaehlt geprueft gegen wieviele Listen mit wievielen
    Eintraegen.
    """
    out_persons: list[PersonCheckEntry] = []
    persons_with_match = 0
    sources_loaded = 0
    total_person_entries = 0

    try:
        from services.sanctions_service import get_multi_service
        svc = get_multi_service()
    except Exception:  # noqa: BLE001
        log.exception("Personen-Check: MultiSanctionsService nicht verfuegbar")
        svc = None

    if svc is not None:
        try:
            agg = svc.stats()
            sources_loaded = int(agg.get("sources_loaded") or 0)
            total_person_entries = int(agg.get("persons") or 0)
        except Exception:  # noqa: BLE001
            log.exception("Personen-Check: Stats-Abruf fehlgeschlagen")

    # Defensive: doppelte Personen-Eintraege deduplizieren.
    seen_keys: set[str] = set()
    cleaned: list[dict] = []
    for p in persons or []:
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or "").strip()
        if not name:
            continue
        role = (p.get("role") or "").strip() or None
        key = f"{name.casefold()}|{(role or '').casefold()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        cleaned.append({"name": name, "role": role})

    for p in cleaned:
        entry = PersonCheckEntry(name=p["name"], role=p["role"])
        if svc is None or not svc.is_any_loaded():
            out_persons.append(entry)
            continue
        try:
            hits = svc.search(
                p["name"], limit=10, min_score=70.0, schema="Person",
            )
        except Exception:  # noqa: BLE001
            log.exception("Personen-Check Suche fehlgeschlagen: %s", p["name"])
            hits = []

        # has_match: mindestens ein Treffer mit Score >= 80
        matched_sources_set: set[str] = set()
        any_at_or_above_80 = False
        for h in hits:
            entry.hits.append({
                "id": h.id,
                "schema": h.schema,
                "name": h.name,
                "matched_on": h.matched_on,
                "matched_field": h.matched_field,
                "score": h.score,
                "confidence": h.confidence,
                "aliases": list(h.aliases or [])[:8],
                "birth_date": h.birth_date,
                "countries": h.countries,
                "addresses": h.addresses,
                "identifiers": h.identifiers,
                "sanctions": h.sanctions,
                "program_ids": h.program_ids,
                "source_key": h.source_key,
                "source_display_name": h.source_display_name,
            })
            if h.source_key:
                matched_sources_set.add(h.source_key)
            if h.score >= 80.0:
                any_at_or_above_80 = True
        entry.matched_sources = sorted(matched_sources_set)
        entry.has_match = any_at_or_above_80
        if any_at_or_above_80:
            persons_with_match += 1
        out_persons.append(entry)

    coverage_note = (
        f"Geprueft gegen {sources_loaded} Sanctions-Liste(n) mit insgesamt "
        f"{total_person_entries:,} Personen-Eintraegen "
        f"(schema='Person'). Match-Schwelle: Score >= 80. Personen-Match "
        f"ohne Geburtsdatum-Abgleich ist eine Indikation, kein Beweis."
    ).replace(",", ".")

    return PersonsCheckSection(
        persons_checked=out_persons,
        total_persons=len(out_persons),
        persons_with_match=persons_with_match,
        coverage_note=coverage_note,
    )


# ── Coverage / Vollstaendigkeit (Polish-Runde 3, Aufgabe 3) ──────────────────


def _completeness_label(percent: float | None, local_count: int) -> str:
    """Wartungs-Status pro Quelle. KEINE Risiko-Aussage.

    - ``vollstaendig``  : >= 95 % oder lokal == erwartet
    - ``partiell``      : 1..94 %
    - ``unbekannt``     : keine erwartete Zahl bekannt oder local_count==0
    """
    if percent is None:
        return "unbekannt"
    if local_count <= 0:
        return "unbekannt"
    if percent >= 95.0:
        return "vollstaendig"
    return "partiell"


def _aggregate_overall_completeness(
    entries: list[CoverageEntry],
) -> Literal["green", "yellow", "red"]:
    """Wartungs-Ampel ueber alle Eintraege.

    - ``green``   : alle Eintraege mit Coverage >= 95 %
    - ``yellow``  : mindestens einer 50..95 % oder unbekannt (aber kein roter)
    - ``red``     : mindestens einer < 50 % ODER local_count == 0 mit
                    expected_count > 0
    """
    if not entries:
        return "yellow"
    has_red = False
    has_yellow = False
    for e in entries:
        if e.expected_count is not None and e.local_count == 0 and e.expected_count > 0:
            has_red = True
            break
        if e.coverage_percent is None:
            has_yellow = True
            continue
        if e.coverage_percent < 50.0:
            has_red = True
            break
        if e.coverage_percent < 95.0:
            has_yellow = True
    if has_red:
        return "red"
    if has_yellow:
        return "yellow"
    return "green"


def _build_coverage_section(db: Session) -> CoverageSection:
    """Sammelt Coverage-Status pro Quelle (State-Aid + Beneficiaries + Sanctions).

    Wartungs-Aussage, keine Risiko-Bewertung. Die Ampel sagt nur, ob der
    lokale Bestand der Pruefumgebung dem aktuellen Stand der Quelle
    entspricht.
    """
    entries: list[CoverageEntry] = []

    # ── State-Aid-Quellen ────────────────────────────────────────────────────
    try:
        sources = db.query(StateAidSource).all()
        for s in sources:
            local = int(s.record_count or 0)
            expected = (
                int(s.expected_total)
                if getattr(s, "expected_total", None) is not None else None
            )
            percent: float | None = None
            if expected and expected > 0:
                percent = min(100.0, (local / expected) * 100.0)
            note = _completeness_label(percent, local)
            entries.append(CoverageEntry(
                source_module="state_aid",
                source_key=s.source_key,
                display_name=s.display_name or s.source_key,
                local_count=local,
                expected_count=expected,
                coverage_percent=(
                    round(float(percent), 1) if percent is not None else None
                ),
                last_harvest_at=s.last_successful_harvest_at,
                completeness_note=note,
            ))
    except Exception:  # noqa: BLE001
        log.exception("Coverage: State-Aid-Quellen fehlgeschlagen")

    # ── Beneficiaries-Quellen ────────────────────────────────────────────────
    # Erwartet == lokal, weil wir keine externe Total-Zahl haben → 100 %.
    try:
        from services.dataframe_service import get_beneficiary_sources
        for src in get_beneficiary_sources():
            local = int(src.get("row_count") or 0)
            # Wir haben keine externe Total-Zahl — somit ist `expected==local`
            # die ehrlichste Annahme. Coverage 100 %, Status "vollstaendig"
            # solange local > 0; sonst "unbekannt".
            expected = local if local > 0 else None
            percent = 100.0 if local > 0 else None
            entries.append(CoverageEntry(
                source_module="beneficiary",
                source_key=src.get("source") or src.get("table_name") or "—",
                display_name=(
                    f"{src.get('source') or '—'} "
                    f"({src.get('bundesland') or '—'}/"
                    f"{src.get('fonds') or '—'})"
                ).strip(),
                local_count=local,
                expected_count=expected,
                coverage_percent=(
                    round(float(percent), 1) if percent is not None else None
                ),
                last_harvest_at=None,  # XLSX-Uploads tragen keinen Zeitstempel
                completeness_note=_completeness_label(percent, local),
            ))
    except Exception:  # noqa: BLE001
        log.exception("Coverage: Beneficiaries-Quellen fehlgeschlagen")

    # ── Sanctions-Quellen ────────────────────────────────────────────────────
    # Erwartet == lokal, weil die CSV-Datei der Truth-Source ist.
    try:
        from services.sanctions_service import get_multi_service
        svc = get_multi_service()
        agg = svc.stats()
        per_source = agg.get("per_source", []) or []
        for ps in per_source:
            local = int(ps.get("total_entries") or 0)
            mtime_str = ps.get("source_mtime")
            mtime: datetime | None = None
            if mtime_str:
                try:
                    mtime = datetime.fromisoformat(
                        str(mtime_str).replace("Z", "+00:00"),
                    )
                except (TypeError, ValueError):
                    mtime = None
            expected = local if local > 0 else None
            percent = 100.0 if local > 0 else None
            entries.append(CoverageEntry(
                source_module="sanctions",
                source_key=ps.get("source_key") or "—",
                display_name=ps.get("source_display_name") or ps.get(
                    "source_key") or "—",
                local_count=local,
                expected_count=expected,
                coverage_percent=(
                    round(float(percent), 1) if percent is not None else None
                ),
                last_harvest_at=mtime,
                completeness_note=_completeness_label(percent, local),
            ))
    except Exception:  # noqa: BLE001
        log.exception("Coverage: Sanctions-Quellen fehlgeschlagen")

    overall = _aggregate_overall_completeness(entries)
    return CoverageSection(
        entries=entries,
        overall_completeness=overall,
    )


# ── Konzernverbund (Mai 2026) ────────────────────────────────────────────────


def _build_corporate_group_section_with_obj(
    db: Session,
    query: str,
    *,
    country_code: str | None,
    primary_state_aid_award_ids: set,
    primary_beneficiaries: list[dict],
    max_children: int = 50,
    timeout_seconds: float = 30.0,
) -> tuple["CorporateGroupSection", "Any"]:
    """Wrapper, der zusaetzlich das ``CorporateGroup``-Objekt liefert,
    damit ``link_corporate_group_to_entities`` die Hierarchie persistieren
    kann.

    Liefert (section, corporate_group_obj_or_None).
    """
    section = _build_corporate_group_section(
        db, query,
        country_code=country_code,
        primary_state_aid_award_ids=primary_state_aid_award_ids,
        primary_beneficiaries=primary_beneficiaries,
        max_children=max_children,
        timeout_seconds=timeout_seconds,
    )
    # Re-Fetch der Group-Instance — der Cache liefert ein dataclass; wir
    # nehmen denselben Pfad wie ``_build_corporate_group_section``.
    try:
        from services.corporate_registry import lookup_corporate_group_cached
        group, _meta = lookup_corporate_group_cached(
            db, query,
            include_children=True,
            max_children=int(max_children) * 4,
            timeout_seconds=float(timeout_seconds),
            use_cache=True,
        )
        return section, group
    except Exception:  # noqa: BLE001
        log.exception(
            "Konzernverbund: zweiter Lookup zur Persistierung fehlgeschlagen",
        )
        return section, None


def _build_entity_resolution_section(
    db: Session, query: str, *, country_code: str | None,
) -> "EntityResolutionSection | None":
    """Baut die Entity-Resolution-Sektion auf.

    Strategie:
    1. Suche nach exaktem Normalized-Name in workshop_company_entities
       (mit optionalem country_code-Filter).
    2. Falls keiner: rapidfuzz-Fallback gegen den Top-N-Pool.
    3. Wenn Treffer: alle Match-Aggregate (state_aid/beneficiary/sanctions)
       einsammeln, Aliase aus EntityMatch-Evidence ziehen.

    Liefert ``None``, wenn keine Entity gefunden wurde.
    """
    try:
        from models.entities import CompanyEntity, EntityMatch
        from services.entity_resolution import _find_by_name_exact, _find_by_name_fuzzy
    except Exception:  # noqa: BLE001
        log.exception("Entity-Resolution-Imports fehlgeschlagen")
        return None

    name_norm = normalize_company_name(query)
    if not name_norm:
        return None

    ent = _find_by_name_exact(db, name_norm, country_code=country_code)
    if ent is None:
        fuzzy = _find_by_name_fuzzy(
            db, name=query, name_normalized=name_norm,
            country_code=country_code, min_score=80.0,
        )
        if fuzzy is not None:
            ent = fuzzy[0]
    if ent is None:
        return None

    # Konzern-Eltern
    parent_name = None
    ultimate_parent_name = None
    if ent.parent_entity_id:
        p = db.get(CompanyEntity, int(ent.parent_entity_id))
        if p is not None:
            parent_name = p.canonical_name
    if ent.ultimate_parent_entity_id:
        u = db.get(CompanyEntity, int(ent.ultimate_parent_entity_id))
        if u is not None:
            ultimate_parent_name = u.canonical_name

    # Aliase: alle name_in_record-Werte aus EntityMatch.match_evidence
    matches = (
        db.query(EntityMatch)
        .filter(
            EntityMatch.entity_id == ent.id,
            EntityMatch.rejected.is_(False),
        )
        .all()
    )
    aliases: set[str] = set()
    for m in matches:
        if isinstance(m.match_evidence, dict):
            v = m.match_evidence.get("name_in_record")
            if v and v != ent.canonical_name:
                aliases.add(v)
    counts = {"state_aid": 0, "beneficiary": 0, "sanctions": 0}
    for m in matches:
        if m.source_module in counts:
            counts[m.source_module] += 1

    return EntityResolutionSection(
        entity_id=ent.id,
        canonical_name=ent.canonical_name,
        canonical_name_normalized=ent.canonical_name_normalized,
        entity_type=ent.entity_type,
        country_code=ent.country_code,
        lei=ent.lei,
        identifiers=(
            ent.identifiers if isinstance(ent.identifiers, dict) else None
        ),
        addresses=(
            ent.addresses if isinstance(ent.addresses, list) else None
        ),
        aliases=sorted(aliases)[:20],
        parent_entity_id=ent.parent_entity_id,
        parent_entity_name=parent_name,
        ultimate_parent_entity_id=ent.ultimate_parent_entity_id,
        ultimate_parent_entity_name=ultimate_parent_name,
        matches_total=len(matches),
        matches_state_aid=counts["state_aid"],
        matches_beneficiary=counts["beneficiary"],
        matches_sanctions=counts["sanctions"],
    )


def _build_corporate_group_section(
    db: Session,
    query: str,
    *,
    country_code: str | None,
    primary_state_aid_award_ids: set,
    primary_beneficiaries: list[dict],
    max_children: int = 50,
    timeout_seconds: float = 30.0,
) -> "CorporateGroupSection":
    """Baut die Konzernverbund-Sektion auf.

    Strategie:
      1. CorporateGroup ueber `lookup_corporate_group_cached` holen (GLEIF +
         Wikidata, mit DB-Cache).
      2. Fuer jede Tochterfirma: zusaetzliche Suche in State-Aid und in
         Beneficiaries — die ZUSAETZLICHEN Treffer (also Awards/Records, die
         nicht schon in der Direkt-Suche gefunden wurden) werden separat
         ausgewiesen.

    Wichtig: Die Treffer werden NICHT mit der Direkt-Suche vermischt — sie
    bekommen ein zusaetzliches Feld `via_corporate_child` (Konzernfirma, ueber
    die der Treffer gefunden wurde). UI/PDF muss das transparent zeigen.
    """
    from services.corporate_registry import lookup_corporate_group_cached
    from services.state_aid_service import (
        fuzzy_match_company,
        normalize_company_name,
    )
    from models.state_aid import StateAidAward

    section = CorporateGroupSection()
    try:
        group, cache_meta = lookup_corporate_group_cached(
            db, query,
            include_children=True,
            max_children=int(max_children) * 4,  # vor Dedup grosszuegig
            timeout_seconds=float(timeout_seconds),
            use_cache=True,
        )
    except Exception:  # noqa: BLE001
        log.exception("Konzernverbund-Lookup fehlgeschlagen")
        section.coverage_note = (
            "Konzernverbund-Lookup fehlgeschlagen — keine GLEIF/Wikidata-Daten."
        )
        return section

    section.cache_meta = cache_meta or {}
    section.sources_used = list(group.sources_used or [])
    section.coverage_note = group.coverage_note
    section.fetched_at = group.fetched_at
    section.primary_entity = (
        group.primary_entity.to_dict() if group.primary_entity else None
    )
    section.ultimate_parent = (
        group.ultimate_parent.to_dict() if group.ultimate_parent else None
    )
    section.direct_parent = (
        group.direct_parent.to_dict() if group.direct_parent else None
    )

    # Children: alle, aber im Detail-Output kappen.
    children = list(group.children or [])
    section.children_count = len(children)
    if max_children and len(children) > max_children:
        section.children_top = [c.to_dict() for c in children[:max_children]]
    else:
        section.children_top = [c.to_dict() for c in children]

    if not children:
        return section

    # ── Zusaetzliche State-Aid-Treffer aus Tochterfirmen ────────────────────
    extra_state_aid: list[dict] = []
    seen_award_ids: set = set(primary_state_aid_award_ids or set())
    for child in children:
        if not child or not child.name:
            continue
        try:
            child_hits = fuzzy_match_company(
                db, child.name, limit=20, min_score=80.0,
                country_code=country_code,
            )
            if not child_hits:
                continue
            new_ids = [
                h.award_id for h in child_hits
                if h.award_id and h.award_id not in seen_award_ids
            ]
            if not new_ids:
                continue
            new_awards = (
                db.query(StateAidAward)
                .filter(StateAidAward.id.in_(new_ids))
                .all()
            )
            for a in new_awards:
                if a.id in seen_award_ids:
                    continue
                seen_award_ids.add(a.id)
                payload = _serialize_award_for_report(a)
                payload["via_corporate_child"] = {
                    "name": child.name,
                    "lei": child.lei,
                    "wikidata_id": child.wikidata_id,
                    "country": child.country,
                    "source": child.source,
                }
                extra_state_aid.append(payload)
        except Exception:  # noqa: BLE001
            log.exception("Konzernverbund: State-Aid-Sub-Suche fehlgeschlagen")
    section.additional_state_aid_count = len(extra_state_aid)
    section.additional_state_aid_amount_eur = sum(
        _to_float(a.get("aid_amount_eur")) for a in extra_state_aid
    )
    # Ausgabe begrenzen, damit die JSON-Antwort handhabbar bleibt.
    section.additional_state_aid_awards = extra_state_aid[:200]

    # ── Zusaetzliche Beneficiary-Treffer aus Tochterfirmen ──────────────────
    seen_keys: set[str] = set()
    for m in primary_beneficiaries or []:
        seen_keys.add(_beneficiary_dedup_key(m))
    extra_beneficiaries: list[dict] = []
    try:
        from services.dataframe_service import search_beneficiary_records
        for child in children:
            if not child or not child.name:
                continue
            try:
                ben_result = search_beneficiary_records(
                    query=child.name, scope="company", limit=20,
                    country_code=country_code,
                )
            except Exception:  # noqa: BLE001
                log.exception("Konzernverbund: Beneficiary-Sub-Suche fehlgeschlagen")
                continue
            if not isinstance(ben_result, dict):
                continue
            records = (
                ben_result.get("records")
                or ben_result.get("results")
                or ben_result.get("entries")
                or []
            )
            for r in records:
                key = _beneficiary_dedup_key(r)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                entry = {
                    "company_name": r.get("company_name") or "",
                    "project_name": r.get("project_name") or "",
                    "aktenzeichen": r.get("aktenzeichen") or "",
                    "location": r.get("location") or "",
                    "kosten": _to_float(r.get("kosten")),
                    "kosten_label": r.get("kosten_label") or "",
                    "source": r.get("source") or "",
                    "bundesland": r.get("bundesland") or "",
                    "fonds": r.get("fonds") or "",
                    "periode": r.get("periode") or "",
                    "country_code": r.get("country_code") or "",
                    "match_confidence": r.get("match_confidence") or "",
                    "via_corporate_child": {
                        "name": child.name,
                        "lei": child.lei,
                        "wikidata_id": child.wikidata_id,
                        "country": child.country,
                        "source": child.source,
                    },
                }
                extra_beneficiaries.append(entry)
    except Exception:  # noqa: BLE001
        log.exception("Konzernverbund: Beneficiary-Schleife fehlgeschlagen")

    section.additional_beneficiaries_count = len(extra_beneficiaries)
    section.additional_beneficiaries_amount_eur = sum(
        _to_float(e.get("kosten")) for e in extra_beneficiaries
    )
    section.additional_beneficiaries = extra_beneficiaries[:200]

    return section


def _beneficiary_dedup_key(record: dict) -> str:
    """Erzeugt einen Dedup-Schluessel fuer einen Beneficiary-Record.

    Wir nehmen company_name + aktenzeichen — das ist in den Transparenzlisten
    eindeutig genug, ohne dass wir die ID aus dem Quell-DataFrame brauchen.
    """
    if not isinstance(record, dict):
        return ""
    name = (record.get("company_name") or "").strip().lower()
    ak = (record.get("aktenzeichen") or "").strip().lower()
    proj = (record.get("project_name") or "").strip().lower()
    return f"{name}|{ak}|{proj}"


# ── Datenstand ────────────────────────────────────────────────────────────────


def _collect_data_freshness(db: Session) -> dict:
    """Sammelt den Datenstand aus den Quell-Metadaten.

    Liefert ein Dict mit drei Eintraegen — state_aid, beneficiaries, sanctions.
    Der Wert ist ein Dict mit `as_of` (ISO-Datum) und `note` (kurzer Text).
    """
    out: dict = {}

    # State-Aid: juengster last_successful_harvest_at ueber alle Quellen
    try:
        sources = db.query(StateAidSource).all()
        last_harvests = [
            s.last_successful_harvest_at for s in sources
            if s.last_successful_harvest_at
        ]
        record_total = sum(int(s.record_count or 0) for s in sources)
        if last_harvests:
            most_recent = max(last_harvests)
            out["state_aid"] = {
                "as_of": most_recent.isoformat(),
                "record_count": record_total,
                "note": (
                    f"Letzter erfolgreicher Harvest "
                    f"{most_recent.strftime('%Y-%m-%d %H:%M UTC')}"
                ),
            }
        else:
            out["state_aid"] = {
                "as_of": None,
                "record_count": record_total,
                "note": "Kein Harvest-Lauf protokolliert.",
            }
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: State-Aid-Datenstand fehlgeschlagen")
        out["state_aid"] = {"as_of": None, "note": "—"}

    # Beneficiaries: aus den XLSX-Uploads (Datei-mtime nicht trivial verfuegbar)
    # — wir geben den Stand "lokal eingespielt" zurueck.
    out["beneficiaries"] = {
        "as_of": None,
        "note": (
            "Stand der lokal eingespielten Transparenzlisten "
            "(Hessen, ESF, JTF). Genaues Datum siehe Quelldatei-Upload."
        ),
    }

    # Sanctions: Multi-Source — juengstes mtime ueber alle Quellen + Aggregat
    try:
        from services.sanctions_service import get_multi_service
        svc = get_multi_service()
        agg = svc.stats()
        per_source = agg.get("per_source", []) or []
        mtimes = [s.get("source_mtime") for s in per_source if s.get("source_mtime")]
        latest_mtime = max(mtimes) if mtimes else None
        loaded_keys = [s.get("source_key") for s in per_source if s.get("loaded")]
        out["sanctions"] = {
            "as_of": latest_mtime,
            "record_count": int(agg.get("total_entries") or 0),
            "sources_loaded": int(agg.get("sources_loaded") or 0),
            "sources_total": int(agg.get("sources_total") or 0),
            "loaded_keys": loaded_keys,
            "note": (
                f"OpenSanctions Multi-Source ({len(loaded_keys)} Quelle(n) lokal), "
                f"Stand {(latest_mtime or '—')[:10] if latest_mtime else '—'}."
            ),
        }
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Sanctions-Datenstand fehlgeschlagen")
        out["sanctions"] = {"as_of": None, "note": "—"}

    return out


# ── Quellen-Erlaeuterung (UI + PDF) ──────────────────────────────────────────


def _collect_sources_explanation(db: Session) -> list[SourceExplanation]:
    """Sammelt die drei Datenquellen mit Stand und Record-Anzahl.

    Wird sowohl vom JSON-Endpoint als auch vom PDF-Renderer genutzt, damit
    UI-Vorschau und PDF identische Texte/Daten zeigen.
    """
    out: list[SourceExplanation] = []

    # 1. EU-State-Aid TAM
    last_harvest_dt: datetime | None = None
    sa_record_count = 0
    try:
        sources = db.query(StateAidSource).all()
        last_harvests = [
            s.last_successful_harvest_at for s in sources
            if s.last_successful_harvest_at
        ]
        if last_harvests:
            last_harvest_dt = max(last_harvests)
        sa_record_count = sum(int(s.record_count or 0) for s in sources)
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: State-Aid-Quelle-Stats fehlgeschlagen")

    out.append(SourceExplanation(
        name="EU-State-Aid Transparency Aid Module (TAM)",
        url="https://webgate.ec.europa.eu/competition/transparency/public",
        description=(
            "Veröffentlichungspflichtige Beihilfen nach Art. 9 Abs. 1 lit. c) "
            "VO (EU) 651/2014 (AGVO) — i.d.R. > 100.000 EUR "
            "(Agrarbereich >= 10.000 EUR)."
        ),
        last_data_update=last_harvest_dt,
        record_count=int(sa_record_count),
    ))

    # 2. Begünstigtenverzeichnis (Transparenzlisten)
    ben_record_count = 0
    try:
        from services.dataframe_service import get_beneficiary_sources
        ben_sources = get_beneficiary_sources()
        ben_record_count = sum(int(s.get("row_count") or 0) for s in ben_sources)
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Beneficiaries-Quelle-Stats fehlgeschlagen")

    out.append(SourceExplanation(
        name="Begünstigtenverzeichnis (Transparenzlisten)",
        url="(lokale Uploads der EFRE-/ESF-/JTF-Förderbehörden)",
        description=(
            "Hochgeladene Transparenzlisten der Bundesländer (Hessen, "
            "Niedersachsen, …) und Österreichs (BMK). EFRE/ESF/JTF-"
            "geförderte Vorhaben gemäß Art. 49/69 VO (EU) 2021/1060."
        ),
        last_data_update=None,
        record_count=int(ben_record_count),
    ))

    # 3. Sanctions (Multi-Source: EU FSF + UN + OFAC + OFSI + SECO)
    san_mtime: datetime | None = None
    san_record_count = 0
    loaded_source_count = 0
    try:
        from services.sanctions_service import get_multi_service
        svc = get_multi_service()
        agg = svc.stats()
        san_record_count = int(agg.get("total_entries") or 0)
        loaded_source_count = int(agg.get("sources_loaded") or 0)
        per_source = agg.get("per_source", []) or []
        mtime_strs = [
            s.get("source_mtime") for s in per_source if s.get("source_mtime")
        ]
        if mtime_strs:
            try:
                san_mtime = max(
                    datetime.fromisoformat(str(m).replace("Z", "+00:00"))
                    for m in mtime_strs
                )
            except (TypeError, ValueError):
                san_mtime = None
    except Exception:  # noqa: BLE001
        log.exception("Audit-Report: Sanctions-Quelle-Stats fehlgeschlagen")

    out.append(SourceExplanation(
        name=(
            f"Sanktionslisten (EU FSF, UN, OFAC, OFSI, SECO — "
            f"{loaded_source_count} Quelle(n) lokal)"
        ),
        url="https://data.opensanctions.org/",
        description=(
            "Aggregierte Sanktionsdaten aus OpenSanctions: EU Konsolidierte "
            "Finanzsanktionsliste (FSF), UN Security Council Consolidated "
            "List, OFAC SDN List, UK OFSI Consolidated List und SECO "
            "Schweizer Sanktionsliste. Personen/Organisationen unter "
            "Finanzsanktionen nach Art. 215 AEUV plus internationale Listen."
        ),
        last_data_update=san_mtime,
        record_count=int(san_record_count),
    ))

    return out


# ── Disclaimer (UI + PDF) ────────────────────────────────────────────────────


def _build_disclaimer_text() -> str:
    """Liefert den Disclaimer-Text fuer JSON-Antwort und PDF-Anhang.

    Eine einheitliche Quelle, damit Live-Preview im Frontend und PDF
    wortgleich den gleichen Hinweis zeigen.
    """
    return (
        "Diese Anwendung ist eine kostenlose Demonstrations- und Pruefhilfe. "
        "Sie wurde von einem einzelnen EFRE-Pruefer als Eigeninitiative "
        "entwickelt und stellt KEINE offizielle behoerdliche Anwendung dar.\n\n"
        "Es wird KEINERLEI GEWAEHRLEISTUNG fuer die Vollstaendigkeit, "
        "Richtigkeit oder Aktualitaet der Daten oder der Aggregation "
        "uebernommen. Die Anwendung dient ausschliesslich zur Unterstuetzung "
        "der manuellen Recherche und ersetzt nicht die eigenstaendige "
        "Pruefung der Originalquellen.\n\n"
        "Personen-Match-Hinweis: Ein Personen-Match ohne Geburtsdatum-"
        "Abgleich ist eine reine Indikation, kein Beweis. Russisch-/"
        "Kyrillisch-Transliterationen erzeugen haeufige Namensgleichheiten — "
        "ein Treffer ist somit erst nach Pruefer-Quervalidierung "
        "(Geburtsdatum, Adresse, Identifier) belastbar.\n\n"
        "Datenschutz: Alle Daten werden lokal verarbeitet, es findet kein "
        "Versand an externe Dienste statt (Ausnahme: Aktualisierung der "
        "Quellen ueber die genannten oeffentlichen Endpunkte).\n\n"
        "Code & Lizenz: Die Anwendung ist Open Source. Verbesserungen und "
        "Hinweise willkommen."
    )


# ── Pflichthinweis (Plan §13) ─────────────────────────────────────────────────


def pflichthinweis(data: AuditReportData) -> str:
    """Plan §13 — Pflichthinweis zur Datenherkunft (in jedem Bericht).

    Faktisch, neutral. Keine Bewertung, keine Empfehlung.
    """
    parts = [
        "Quelle: EU Transparency Aid Module (TAM) und nationale Beihilfe-Register, "
        "lokale Beguenstigtenverzeichnis-Uploads (Transparenzlisten der Laender) "
        "sowie OpenSanctions Multi-Source-CSVs (EU FSF, UN Security Council, "
        "OFAC SDN, UK OFSI, SECO).",
    ]
    sa_meta = data.data_freshness.get("state_aid") or {}
    sn_meta = data.data_freshness.get("sanctions") or {}
    if sa_meta.get("as_of"):
        parts.append(f"State-Aid-Datenstand: {sa_meta['as_of']}.")
    if sn_meta.get("as_of"):
        parts.append(f"Sanktionslisten-Datenstand: {sn_meta['as_of']}.")
    parts.append(
        "Vollstaendigkeit kann nicht garantiert werden. "
        "Die Pruefer-Bewertung obliegt dem Anwender — dieser Bericht "
        "liefert ausschliesslich aufbereitete Fakten ohne Bewertung "
        "und ohne Empfehlung."
    )
    return " ".join(parts)
