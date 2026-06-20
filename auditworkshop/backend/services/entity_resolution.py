"""
flowworkshop · services/entity_resolution.py

Phase 6d — Entity-Resolution: matched Original-Records gegen den Master-
Entity-Pool (``workshop_company_entities``) und legt EntityMatches an.

Strategie (von hoch zu niedrig Confidence):
  1. LEI-Match: ``beneficiary_identifier`` enthaelt LEI-Format → 100%
  2. National-Identifier-Match: gleicher HRB/Steuer-Identifier → 95%
  3. Name-Exact (nach Normalisierung): ``canonical_name_normalized``
     identisch → 90%
  4. Name-Fuzzy: ``rapidfuzz.WRatio`` und ``token_set_ratio`` auf
     ``canonical_name_normalized``; Score = max der beiden Werte → 75-89%

Confidence-Schwelle: Below 75 wird KEIN Match angelegt — der Pruefer kann
manuell ueber die UI bestaetigen, falls noch sinnvoll.

Idempotenz: ``link_record`` ist UNIQUE-protected ueber
(source_module, source_record_id) — ein zweiter Aufruf mit denselben
Quell-Daten erzeugt keinen Doppelt-Eintrag.

Die Original-Tabellen werden NICHT veraendert. Diese Schicht ist additiv.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from models.entities import CompanyEntity, EntityMatch

log = logging.getLogger(__name__)


# ── Konstanten ────────────────────────────────────────────────────────────────


CONFIDENCE_LEI = 100.0
CONFIDENCE_IDENTIFIER = 95.0
CONFIDENCE_NAME_EXACT = 90.0
CONFIDENCE_FUZZY_THRESHOLD = 75.0   # darunter: KEIN Match anlegen

# LEI-Format: 20 Zeichen, A-Z + 0-9, Pruefziffer am Ende.
# https://www.gleif.org/en/about-lei/iso-17442-the-lei-code-structure
_LEI_RE = re.compile(r"^[A-Z0-9]{18}\d{2}$")

# Module → Source-Table (Audit-Trail)
SOURCE_TABLES = {
    "state_aid": "workshop_state_aid_awards",
    "beneficiary": "workshop_beneficiary_records",
    "sanctions": "workshop_sanctions_entries",
}


# ── Datenklassen ──────────────────────────────────────────────────────────────


@dataclass
class EntityMatchResult:
    """Ergebnis eines ``resolve_entity``-Aufrufs.

    ``is_new_entity`` zeigt, ob die CompanyEntity gerade neu angelegt wurde
    (zur Statistik im Rebuild-Skript).
    """
    entity: CompanyEntity
    method: str
    confidence: float
    evidence: dict
    is_new_entity: bool


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────


def is_valid_lei(value: str | None) -> bool:
    """True, wenn ``value`` exakt ein LEI ist (ISO 17442)."""
    if not value:
        return False
    s = str(value).strip().upper()
    return bool(_LEI_RE.match(s))


def extract_lei_from_text(value: str | None) -> str | None:
    """Sucht ein LEI-Token in einem freien Text-Feld.

    State-Aid-Datenanbieter packen den LEI manchmal mit anderen Identifiern
    in ein Feld (z.B. ``beneficiary_identifier`` = 'LEI: ABCD1234567890123456').
    Wir extrahieren es entsprechend.
    """
    if not value:
        return None
    # Direkt ein LEI?
    s = str(value).strip().upper()
    if _LEI_RE.match(s):
        return s
    # LEI-Token irgendwo im Feld
    m = re.search(r"\b([A-Z0-9]{18}\d{2})\b", s)
    if m:
        return m.group(1)
    return None


def _normalize_for_match(name: str | None) -> str:
    """Vergleichsform fuer Entity-Resolution.

    Wir nutzen die zentrale Funktion aus ``state_aid_service``, weil sie
    Rechtsformen + Akzente entfernt — exakt das, was wir hier brauchen.
    """
    if not name:
        return ""
    from services.state_aid_service import normalize_company_name
    return normalize_company_name(name)


def _store_identifier(identifiers: dict | None, key: str, value: str | None) -> dict:
    """Fuegt einen Identifier zur Identifiers-JSONB hinzu — ohne Duplikate.

    Liefert immer ein neues Dict zurueck (damit SQLAlchemy es als Aenderung
    erkennt).
    """
    if not value:
        return dict(identifiers or {})
    out = dict(identifiers or {})
    bucket = out.get(key)
    if bucket is None:
        out[key] = [value]
    elif isinstance(bucket, list):
        if value not in bucket:
            bucket.append(value)
            out[key] = bucket
    elif isinstance(bucket, str):
        if value != bucket:
            out[key] = [bucket, value]
    else:
        out[key] = [value]
    return out


# ── Such-Helfer (DB) ──────────────────────────────────────────────────────────


def _find_by_lei(db: Session, lei: str) -> CompanyEntity | None:
    """Sucht eine Entity ueber den LEI."""
    if not lei:
        return None
    return (
        db.query(CompanyEntity)
        .filter(CompanyEntity.lei == lei.upper())
        .first()
    )


def _find_by_identifier(db: Session, identifier: str) -> CompanyEntity | None:
    """Sucht eine Entity, in deren ``identifiers``-JSONB der Wert EXAKT vorkommt.

    Bewusst strukturierte Wert-Gleichheit (``jsonb_path_exists`` mit
    ``$.** ? (@ == $ident)``) statt eines ungeankerten ``::text ILIKE
    '%ident%'``: Letzteres matchte den Identifier auch als Teilstring in
    fremden Werten oder sogar in JSON-Schluesselnamen und verschmolz so
    verschiedene Rechtstraeger mit Confidence 95 (Befund Entity-Resolution #3).
    Die Werte werden in ``_store_identifier`` verbatim abgelegt, daher ist die
    Exakt-Gleichheit konsistent mit der Speicher-Semantik.
    """
    if not identifier:
        return None
    ident_value = identifier.strip()
    if not ident_value:
        return None
    sql = text("""
        SELECT id FROM workshop_company_entities
         WHERE identifiers IS NOT NULL
           AND jsonb_path_exists(
                 identifiers,
                 '$.** ? (@ == $ident)',
                 jsonb_build_object('ident', :ident)
               )
         ORDER BY id ASC
         LIMIT 1
    """)
    row = db.execute(sql, {"ident": ident_value}).first()
    if not row:
        return None
    return db.get(CompanyEntity, int(row[0]))


def _find_by_name_exact(
    db: Session, name_normalized: str, *, country_code: str | None = None,
) -> CompanyEntity | None:
    """Findet eine Entity ueber den exakt gleichen normalisierten Namen.

    Wenn ``country_code`` mitgegeben wird und mehrere Entities denselben
    Namen tragen, wird die mit passendem ``country_code`` bevorzugt.
    """
    if not name_normalized:
        return None
    q = db.query(CompanyEntity).filter(
        CompanyEntity.canonical_name_normalized == name_normalized,
    )
    if country_code:
        cc = country_code.upper()
        # Country-Code ist ISO-2 oder ISO-3 — wir matchen auf beide
        # Deterministisches Tie-Breaking (id asc) — sonst gibt PostgreSQL bei
        # Namensdubletten eine plan-/heap-abhaengige Zeile zurueck (Rebuilds
        # nicht reproduzierbar, Befund Entity-Resolution #4).
        q_cc = q.filter(CompanyEntity.country_code == cc).order_by(CompanyEntity.id.asc())
        ent = q_cc.first()
        if ent:
            return ent
    return q.order_by(CompanyEntity.id.asc()).first()


def _find_by_name_fuzzy(
    db: Session,
    name: str,
    name_normalized: str,
    *,
    country_code: str | None = None,
    min_score: float = CONFIDENCE_FUZZY_THRESHOLD,
    candidate_limit: int = 200,
) -> tuple[CompanyEntity, float] | None:
    """Sucht via rapidfuzz nach der naechsten existierenden Entity.

    Strategie:
      1. SQL-Vorfilter: ILIKE auf den ersten 1-2 Tokens (Bitmap-Index dank
         pg_trgm-GIN auf ``canonical_name_normalized``).
      2. rapidfuzz: max(token_set_ratio, WRatio) → Score.
      3. Bei Score >= min_score: liefere die Top-Entity zurueck.
    """
    if not name_normalized:
        return None
    tokens = [t for t in name_normalized.split() if len(t) >= 3]
    if not tokens:
        return None

    q = db.query(
        CompanyEntity.id,
        CompanyEntity.canonical_name,
        CompanyEntity.canonical_name_normalized,
    )
    if country_code:
        q = q.filter(
            or_(
                CompanyEntity.country_code == country_code.upper(),
                CompanyEntity.country_code.is_(None),
            ),
        )
    # ILIKE-Vorfilter: mindestens ein Token muss enthalten sein
    ors = [
        CompanyEntity.canonical_name_normalized.ilike(f"%{t}%")
        for t in tokens[:3]
    ]
    # Nach pg_trgm-Aehnlichkeit zum VOLLEN normalisierten Namen ordnen, BEVOR
    # bei candidate_limit gekappt wird — sonst liefert die DB willkuerliche
    # ≤200 Zeilen und der beste Match kann ausserhalb des Fensters liegen
    # (Befund Entity-Resolution #8). Nutzt den GIN-trgm-Index ix_entity_name_trgm.
    q = (
        q.filter(or_(*ors))
        .order_by(
            func.similarity(CompanyEntity.canonical_name_normalized, name_normalized).desc()
        )
        .limit(candidate_limit)
    )
    rows = q.all()
    if not rows:
        return None

    choices = [(r.id, r.canonical_name_normalized or "") for r in rows]
    norm_strings = [c[1] for c in choices]
    # token_set_ratio: tolerant gegen Wortreihenfolge
    tsr_hits = process.extract(
        name_normalized, norm_strings, scorer=fuzz.token_set_ratio,
        limit=10, score_cutoff=min_score,
    )
    # WRatio: kombiniert ratio + partial_ratio + token_sort + token_set
    wr_hits = process.extract(
        name_normalized, norm_strings, scorer=fuzz.WRatio,
        limit=10, score_cutoff=min_score,
    )

    best_id: int | None = None
    best_score: float = 0.0
    for raw in (tsr_hits, wr_hits):
        for _value, score, idx in raw:
            cur_id = choices[idx][0]
            if score > best_score:
                best_score = float(score)
                best_id = int(cur_id)

    if best_id is None or best_score < min_score:
        return None
    ent = db.get(CompanyEntity, best_id)
    if ent is None:
        return None
    return ent, round(best_score, 1)


# ── Resolve & Link ────────────────────────────────────────────────────────────


def resolve_entity(
    db: Session,
    *,
    name: str,
    identifier: str | None = None,
    country_code: str | None = None,
    lei: str | None = None,
    addresses: list[dict] | None = None,
    entity_type: str = "company",
) -> EntityMatchResult | None:
    """Matched einen Datensatz gegen den Pool.

    Erzeugt eine neue CompanyEntity, falls keine passende existiert UND der
    Name nicht leer ist.

    Liefert ``None``, wenn kein Match (auch kein Name) moeglich ist —
    sollte praktisch nie passieren, weil wir mit einem Namen immer eine
    Entity erzeugen.
    """
    name = (name or "").strip()
    if not name:
        return None

    name_norm = _normalize_for_match(name)
    if not name_norm:
        return None

    cc = (country_code or "").upper().strip() or None

    # LEI in das identifier-Feld kann mit drinstecken; explizit lookup_lei
    # hat Vorrang.
    found_lei = (lei or "").strip().upper() or None
    if not found_lei:
        if is_valid_lei(identifier):
            found_lei = (identifier or "").strip().upper()
        else:
            extracted = extract_lei_from_text(identifier)
            if extracted:
                found_lei = extracted

    # 1. LEI-Match
    if found_lei:
        ent = _find_by_lei(db, found_lei)
        if ent is not None:
            _enrich_existing(
                ent, identifier=identifier, country_code=cc,
                addresses=addresses, source="lei",
            )
            db.flush()
            return EntityMatchResult(
                entity=ent,
                method="lei",
                confidence=CONFIDENCE_LEI,
                evidence={
                    "lei": found_lei,
                    "name_in_record": name,
                },
                is_new_entity=False,
            )
        # Kein Treffer aber LEI ist da: neue Entity mit LEI anlegen
        ent = _create_entity(
            db,
            canonical_name=name,
            canonical_name_normalized=name_norm,
            country_code=cc,
            lei=found_lei,
            identifier=identifier,
            addresses=addresses,
            first_match_method="lei",
            entity_type=entity_type,
        )
        return EntityMatchResult(
            entity=ent,
            method="lei",
            confidence=CONFIDENCE_LEI,
            evidence={
                "lei": found_lei,
                "name_in_record": name,
            },
            is_new_entity=True,
        )

    # 2. Identifier-Match (HRB, Steuer-Nr.)
    if identifier:
        ident_clean = (identifier or "").strip()
        if ident_clean and len(ident_clean) >= 4:
            ent = _find_by_identifier(db, ident_clean)
            # Identifier-Treffer (Confidence 95) gegen den Namen plausibilisieren —
            # ein zufaellig gleicher Identifier-String darf nicht zwei verschiedene
            # Rechtstraeger verschmelzen (Befund Entity-Resolution #3). Schwelle
            # bewusst niedrig (55), damit Abkuerzungen/Aliase tolerant bleiben.
            if ent is not None and ent.canonical_name_normalized:
                if fuzz.token_set_ratio(name_norm, ent.canonical_name_normalized) < 55:
                    ent = None
            if ent is not None:
                _enrich_existing(
                    ent, identifier=identifier, country_code=cc,
                    addresses=addresses, source="identifier",
                )
                db.flush()
                return EntityMatchResult(
                    entity=ent,
                    method="identifier",
                    confidence=CONFIDENCE_IDENTIFIER,
                    evidence={
                        "identifier": ident_clean,
                        "name_in_record": name,
                    },
                    is_new_entity=False,
                )

    # 3. Name-Exact (gleicher Country wenn moeglich)
    ent = _find_by_name_exact(db, name_norm, country_code=cc)
    if ent is not None:
        _enrich_existing(
            ent, identifier=identifier, country_code=cc,
            addresses=addresses, source="name_exact",
        )
        db.flush()
        return EntityMatchResult(
            entity=ent,
            method="name_exact",
            confidence=CONFIDENCE_NAME_EXACT,
            evidence={
                "name_normalized": name_norm,
                "name_in_record": name,
            },
            is_new_entity=False,
        )

    # 4. Name-Fuzzy
    fuzzy = _find_by_name_fuzzy(
        db, name=name, name_normalized=name_norm,
        country_code=cc, min_score=CONFIDENCE_FUZZY_THRESHOLD,
    )
    if fuzzy is not None:
        ent, score = fuzzy
        _enrich_existing(
            ent, identifier=identifier, country_code=cc,
            addresses=addresses, source=f"name_fuzzy_{score}",
        )
        db.flush()
        return EntityMatchResult(
            entity=ent,
            method=f"name_fuzzy_{score:.0f}",
            confidence=float(score),
            evidence={
                "name_normalized": name_norm,
                "name_in_record": name,
                "matched_canonical_name": ent.canonical_name,
                "matched_normalized": ent.canonical_name_normalized,
                "fuzzy_score": float(score),
            },
            is_new_entity=False,
        )

    # 5. Keine Entity gefunden — neue anlegen
    ent = _create_entity(
        db,
        canonical_name=name,
        canonical_name_normalized=name_norm,
        country_code=cc,
        lei=None,
        identifier=identifier,
        addresses=addresses,
        first_match_method="name_new",
        entity_type=entity_type,
    )
    return EntityMatchResult(
        entity=ent,
        method="name_new",
        confidence=CONFIDENCE_NAME_EXACT,  # neuer Eintrag zaehlt als 'exact'
        evidence={
            "name_normalized": name_norm,
            "name_in_record": name,
            "note": "neue Entity ohne Match-Vorgaenger",
        },
        is_new_entity=True,
    )


def _create_entity(
    db: Session,
    *,
    canonical_name: str,
    canonical_name_normalized: str,
    country_code: str | None,
    lei: str | None,
    identifier: str | None,
    addresses: list[dict] | None,
    first_match_method: str,
    entity_type: str = "company",
) -> CompanyEntity:
    """Legt eine neue CompanyEntity an, samt initialen Identifiern/Adressen."""
    identifiers: dict | None = None
    if identifier and not is_valid_lei(identifier):
        # Heuristik: hrb_xxx → ab "HRB" Praefix wir buckenen unter 'hrb',
        # alle anderen unter 'national'
        bucket = "hrb" if "HRB" in identifier.upper() else "national"
        identifiers = _store_identifier(None, bucket, identifier.strip())

    addr_list: list[dict] | None = None
    if addresses:
        addr_list = []
        for a in addresses:
            if isinstance(a, dict) and any(a.values()):
                addr_list.append(dict(a))

    ent = CompanyEntity(
        canonical_name=canonical_name[:500],
        canonical_name_normalized=canonical_name_normalized[:500],
        entity_type=entity_type,
        country_code=country_code,
        lei=lei,
        identifiers=identifiers,
        addresses=addr_list,
        first_match_method=first_match_method,
    )
    db.add(ent)
    db.flush()
    return ent


def _enrich_existing(
    ent: CompanyEntity,
    *,
    identifier: str | None,
    country_code: str | None,
    addresses: list[dict] | None,
    source: str,
) -> None:
    """Fuegt einer bestehenden Entity zusaetzliche Daten hinzu — additiv."""
    if identifier and not is_valid_lei(identifier):
        bucket = "hrb" if "HRB" in identifier.upper() else "national"
        ent.identifiers = _store_identifier(
            ent.identifiers, bucket, identifier.strip(),
        )
    if country_code and not ent.country_code:
        ent.country_code = country_code
    if addresses:
        existing = list(ent.addresses or [])
        for a in addresses:
            if isinstance(a, dict) and any(a.values()):
                # Dedup: gleiche city/postal_code/country = nicht erneut anlegen
                key = (
                    (a.get("city") or "").strip().lower(),
                    (a.get("postal_code") or "").strip(),
                    (a.get("country") or "").strip().upper(),
                )
                already = any(
                    (
                        (e.get("city") or "").strip().lower(),
                        (e.get("postal_code") or "").strip(),
                        (e.get("country") or "").strip().upper(),
                    ) == key
                    for e in existing
                    if isinstance(e, dict)
                )
                if not already:
                    existing.append(dict(a))
        ent.addresses = existing


def link_record(
    db: Session,
    *,
    source_module: str,
    source_record_id: str,
    source_table: str | None = None,
    name: str,
    identifier: str | None = None,
    country_code: str | None = None,
    lei: str | None = None,
    addresses: list[dict] | None = None,
    entity_type: str = "company",
) -> EntityMatch | None:
    """Matched UND erzeugt EntityMatch.

    Idempotent ueber UNIQUE(source_module, source_record_id) — ein zweiter
    Aufruf mit denselben Quell-IDs erzeugt keinen Doppelt-Eintrag.
    """
    if source_module not in SOURCE_TABLES:
        raise ValueError(f"Unbekanntes source_module: {source_module}")
    if not source_record_id:
        raise ValueError("source_record_id darf nicht leer sein")

    table = source_table or SOURCE_TABLES[source_module]

    # Schon vorhanden? Abgelehnte Matches (rejected) ignorieren, damit ein vom
    # Pruefer abgelehnter Datensatz beim naechsten Lauf neu/anders aufgeloest
    # wird statt dauerhaft auf der falschen Entity zu haengen (Befund #5).
    existing = (
        db.query(EntityMatch)
        .filter(
            EntityMatch.source_module == source_module,
            EntityMatch.source_record_id == str(source_record_id),
            EntityMatch.rejected.is_(False),
        )
        .first()
    )
    if existing is not None:
        return existing

    result = resolve_entity(
        db,
        name=name,
        identifier=identifier,
        country_code=country_code,
        lei=lei,
        addresses=addresses,
        entity_type=entity_type,
    )
    if result is None:
        return None

    match = EntityMatch(
        entity_id=result.entity.id,
        source_module=source_module,
        source_record_id=str(source_record_id),
        source_table=table,
        match_method=result.method,
        match_confidence=float(result.confidence),
        match_evidence=result.evidence,
    )
    db.add(match)
    db.flush()
    return match


# ── Rebuild-Funktionen ────────────────────────────────────────────────────────


def _empty_stats() -> dict:
    return {
        "records_seen": 0,
        "records_skipped_existing": 0,
        "records_failed": 0,
        "matches_created": 0,
        "entities_created": 0,
        "low_confidence_skipped": 0,
    }


def rebuild_entities_from_state_aid(
    db: Session, *, batch: int = 1000, dry: bool = False, limit: int | None = None,
) -> dict:
    """Iteriert ueber ``workshop_state_aid_awards`` und legt Matches an.

    Idempotent: bestehende Matches werden uebersprungen. Erzeugt nur Entities,
    wenn der Match-Confidence >= ``CONFIDENCE_FUZZY_THRESHOLD`` ist (also
    >= 75).
    """
    from models.state_aid import StateAidAward

    stats = _empty_stats()
    base_q = db.query(
        StateAidAward.id,
        StateAidAward.beneficiary_name,
        StateAidAward.beneficiary_identifier,
        StateAidAward.country_code,
    ).order_by(StateAidAward.id)

    offset = 0
    processed = 0
    while True:
        # Wenn ``limit`` gesetzt: Batch klein genug halten, um den Limit
        # nicht zu ueberschreiten.
        cur_batch = batch
        if limit is not None:
            remaining = int(limit) - processed
            if remaining <= 0:
                break
            cur_batch = min(cur_batch, remaining)

        rows = base_q.offset(offset).limit(cur_batch).all()
        if not rows:
            break
        offset += len(rows)
        processed += len(rows)

        for row in rows:
            stats["records_seen"] += 1
            if not row.beneficiary_name:
                stats["records_failed"] += 1
                continue

            # Schon vorhanden?
            existing = (
                db.query(EntityMatch.id)
                .filter(
                    EntityMatch.source_module == "state_aid",
                    EntityMatch.source_record_id == str(row.id),
                    EntityMatch.rejected.is_(False),
                )
                .first()
            )
            if existing is not None:
                stats["records_skipped_existing"] += 1
                continue

            try:
                result = resolve_entity(
                    db,
                    name=row.beneficiary_name,
                    identifier=row.beneficiary_identifier,
                    country_code=row.country_code,
                )
            except Exception:  # noqa: BLE001
                log.exception(
                    "Resolve fehlgeschlagen fuer state_aid award_id=%s",
                    row.id,
                )
                stats["records_failed"] += 1
                continue

            if result is None:
                stats["records_failed"] += 1
                continue
            if result.is_new_entity:
                stats["entities_created"] += 1
            if result.confidence < CONFIDENCE_FUZZY_THRESHOLD:
                stats["low_confidence_skipped"] += 1
                # Wenn die neu angelegte Entity ein "name_new" ist
                # (kein Vorgaenger), dann ist Confidence = 90 und wir lassen
                # den Match drin. Sonst: kein Match-Eintrag.
                continue

            if not dry:
                match = EntityMatch(
                    entity_id=result.entity.id,
                    source_module="state_aid",
                    source_record_id=str(row.id),
                    source_table=SOURCE_TABLES["state_aid"],
                    match_method=result.method,
                    match_confidence=float(result.confidence),
                    match_evidence=result.evidence,
                )
                db.add(match)
            stats["matches_created"] += 1

        if not dry:
            db.commit()
        else:
            db.rollback()

    return stats


def rebuild_entities_from_beneficiaries(
    db: Session, *, batch: int = 1000, dry: bool = False, limit: int | None = None,
) -> dict:
    """Iteriert ueber ``workshop_beneficiary_records`` und legt Matches an.

    BeneficiaryRecord hat keinen LEI, aber ggf. Aktenzeichen + ein
    Adress-Feld (location, plz, landkreis).
    """
    from models.beneficiary_records import BeneficiaryRecord

    stats = _empty_stats()
    base_q = db.query(
        BeneficiaryRecord.id,
        BeneficiaryRecord.beneficiary_name,
        BeneficiaryRecord.project_aktenzeichen,
        BeneficiaryRecord.country_code,
        BeneficiaryRecord.location,
        BeneficiaryRecord.plz,
        BeneficiaryRecord.landkreis,
    ).order_by(BeneficiaryRecord.id)

    offset = 0
    processed = 0
    while True:
        cur_batch = batch
        if limit is not None:
            remaining = int(limit) - processed
            if remaining <= 0:
                break
            cur_batch = min(cur_batch, remaining)

        rows = base_q.offset(offset).limit(cur_batch).all()
        if not rows:
            break
        offset += len(rows)
        processed += len(rows)

        for row in rows:
            stats["records_seen"] += 1
            if not row.beneficiary_name:
                stats["records_failed"] += 1
                continue

            existing = (
                db.query(EntityMatch.id)
                .filter(
                    EntityMatch.source_module == "beneficiary",
                    EntityMatch.source_record_id == str(row.id),
                    EntityMatch.rejected.is_(False),
                )
                .first()
            )
            if existing is not None:
                stats["records_skipped_existing"] += 1
                continue

            addresses: list[dict] = []
            if row.location or row.plz or row.landkreis:
                addresses.append({
                    "city": row.location or "",
                    "postal_code": row.plz or "",
                    "street": "",
                    "country": (row.country_code or "").upper(),
                    "source": "beneficiary",
                })

            try:
                result = resolve_entity(
                    db,
                    name=row.beneficiary_name,
                    identifier=row.project_aktenzeichen,
                    country_code=row.country_code,
                    addresses=addresses,
                )
            except Exception:  # noqa: BLE001
                log.exception(
                    "Resolve fehlgeschlagen fuer beneficiary_id=%s",
                    row.id,
                )
                stats["records_failed"] += 1
                continue

            if result is None:
                stats["records_failed"] += 1
                continue
            if result.is_new_entity:
                stats["entities_created"] += 1
            if result.confidence < CONFIDENCE_FUZZY_THRESHOLD:
                stats["low_confidence_skipped"] += 1
                continue

            if not dry:
                match = EntityMatch(
                    entity_id=result.entity.id,
                    source_module="beneficiary",
                    source_record_id=str(row.id),
                    source_table=SOURCE_TABLES["beneficiary"],
                    match_method=result.method,
                    match_confidence=float(result.confidence),
                    match_evidence=result.evidence,
                )
                db.add(match)
            stats["matches_created"] += 1

        if not dry:
            db.commit()
        else:
            db.rollback()

    return stats


def rebuild_entities_from_sanctions(
    db: Session, *, batch: int = 1000, dry: bool = False, limit: int | None = None,
) -> dict:
    """Iteriert ueber ``workshop_sanctions_entries`` und legt Matches an.

    Sanctions-Eintraege koennen Personen oder Firmen sein (``schema``-Feld).
    Wir erzeugen ``entity_type='person'`` wenn ``schema`` z.B. 'Person',
    sonst 'company'.
    """
    from models.sanctions_entries import SanctionsEntry

    stats = _empty_stats()
    base_q = db.query(
        SanctionsEntry.id,
        SanctionsEntry.name,
        SanctionsEntry.identifiers,
        SanctionsEntry.countries,
        SanctionsEntry.addresses,
        SanctionsEntry.schema,
    ).order_by(SanctionsEntry.id)

    offset = 0
    processed = 0
    while True:
        cur_batch = batch
        if limit is not None:
            remaining = int(limit) - processed
            if remaining <= 0:
                break
            cur_batch = min(cur_batch, remaining)

        rows = base_q.offset(offset).limit(cur_batch).all()
        if not rows:
            break
        offset += len(rows)
        processed += len(rows)

        for row in rows:
            stats["records_seen"] += 1
            if not row.name:
                stats["records_failed"] += 1
                continue

            existing = (
                db.query(EntityMatch.id)
                .filter(
                    EntityMatch.source_module == "sanctions",
                    EntityMatch.source_record_id == str(row.id),
                    EntityMatch.rejected.is_(False),
                )
                .first()
            )
            if existing is not None:
                stats["records_skipped_existing"] += 1
                continue

            # Sanctions-Identifier kann "; "-separiert sein. Wir nehmen den
            # ersten Wert; LEI extrahieren wir wenn vorhanden.
            ident = None
            lei = None
            if row.identifiers:
                first_ident = str(row.identifiers).split(";")[0].strip()
                ident = first_ident or None
                lei = extract_lei_from_text(row.identifiers)

            # Country: erste Position aus "; "-Liste
            cc = None
            if row.countries:
                first_cc = str(row.countries).split(";")[0].strip().upper()
                cc = first_cc or None

            # Adressen: ein einziges Adress-Feld wird als String gespeichert.
            addresses: list[dict] = []
            if row.addresses:
                first_addr = str(row.addresses).split(";")[0].strip()
                if first_addr:
                    addresses.append({
                        "city": "",
                        "postal_code": "",
                        "street": first_addr[:300],
                        "country": cc or "",
                        "source": "sanctions",
                    })

            schema_val = (row.schema or "").lower()
            entity_type = "person" if "person" in schema_val else "company"

            try:
                result = resolve_entity(
                    db,
                    name=row.name,
                    identifier=ident,
                    country_code=cc,
                    lei=lei,
                    addresses=addresses,
                    entity_type=entity_type,
                )
            except Exception:  # noqa: BLE001
                log.exception(
                    "Resolve fehlgeschlagen fuer sanctions_id=%s",
                    row.id,
                )
                stats["records_failed"] += 1
                continue

            if result is None:
                stats["records_failed"] += 1
                continue
            if result.is_new_entity:
                stats["entities_created"] += 1
            if result.confidence < CONFIDENCE_FUZZY_THRESHOLD:
                stats["low_confidence_skipped"] += 1
                continue

            if not dry:
                match = EntityMatch(
                    entity_id=result.entity.id,
                    source_module="sanctions",
                    source_record_id=str(row.id),
                    source_table=SOURCE_TABLES["sanctions"],
                    match_method=result.method,
                    match_confidence=float(result.confidence),
                    match_evidence=result.evidence,
                )
                db.add(match)
            stats["matches_created"] += 1

        if not dry:
            db.commit()
        else:
            db.rollback()

    return stats


# ── Konzernverbund-Verlinkung ─────────────────────────────────────────────────


def link_corporate_group_to_entities(db: Session, group: Any) -> dict:
    """Verankert eine ``CorporateGroup`` (GLEIF/Wikidata) in der Entity-Tabelle.

    Pro Corporate-Entity in der Group:
      1. ueber LEI in CompanyEntity nachschlagen — wenn nicht vorhanden:
         neue Entity anlegen.
      2. ``parent_entity_id`` und ``ultimate_parent_entity_id`` der primary
         und der direct_children setzen.

    Liefert Statistik:
      ``{"entities_created": N, "hierarchies_set": M, "primary_entity_id": id}``

    Wird beim Audit-Report-Bau (``include_corporate_group=True``) automatisch
    ausgefuehrt — der Konzernverbund bleibt persistent in der Entity-
    Hierarchie verankert.
    """
    stats = {
        "entities_created": 0,
        "hierarchies_set": 0,
        "primary_entity_id": None,
        "ultimate_parent_entity_id": None,
        "direct_parent_entity_id": None,
        "children_linked": 0,
    }
    if group is None or getattr(group, "primary_entity", None) is None:
        return stats

    primary_corp = group.primary_entity

    # Primary-Entity holen oder anlegen
    primary_ent = _ensure_entity_for_corporate(
        db, primary_corp, stats=stats,
    )
    if primary_ent is None:
        return stats
    stats["primary_entity_id"] = primary_ent.id

    # Ultimate-Parent
    ultimate_parent_ent = None
    ultimate_corp = getattr(group, "ultimate_parent", None)
    if ultimate_corp is not None and getattr(ultimate_corp, "name", None):
        ultimate_parent_ent = _ensure_entity_for_corporate(
            db, ultimate_corp, stats=stats,
        )
        if ultimate_parent_ent is not None:
            stats["ultimate_parent_entity_id"] = ultimate_parent_ent.id
            primary_ent.ultimate_parent_entity_id = ultimate_parent_ent.id
            stats["hierarchies_set"] += 1

    # Direct-Parent
    direct_parent_ent = None
    direct_corp = getattr(group, "direct_parent", None)
    if direct_corp is not None and getattr(direct_corp, "name", None):
        direct_parent_ent = _ensure_entity_for_corporate(
            db, direct_corp, stats=stats,
        )
        if direct_parent_ent is not None:
            stats["direct_parent_entity_id"] = direct_parent_ent.id
            primary_ent.parent_entity_id = direct_parent_ent.id
            stats["hierarchies_set"] += 1
            # Auch der direct_parent zeigt auf ultimate_parent
            if (
                ultimate_parent_ent is not None
                and direct_parent_ent.id != ultimate_parent_ent.id
            ):
                direct_parent_ent.ultimate_parent_entity_id = (
                    ultimate_parent_ent.id
                )

    # Children: jede Tochter bekommt parent_entity_id = primary_ent.id
    children = list(getattr(group, "children", None) or [])
    for child_corp in children:
        if not getattr(child_corp, "name", None):
            continue
        child_ent = _ensure_entity_for_corporate(
            db, child_corp, stats=stats,
        )
        if child_ent is None:
            continue
        # Tochterfirma → parent ist primary_ent
        if child_ent.id != primary_ent.id:
            child_ent.parent_entity_id = primary_ent.id
            if ultimate_parent_ent is not None:
                child_ent.ultimate_parent_entity_id = ultimate_parent_ent.id
            else:
                child_ent.ultimate_parent_entity_id = primary_ent.id
            stats["children_linked"] += 1
            stats["hierarchies_set"] += 1

    db.flush()
    return stats


def _ensure_entity_for_corporate(
    db: Session, corp_entity: Any, *, stats: dict,
) -> CompanyEntity | None:
    """Holt oder legt eine CompanyEntity fuer eine ``CorporateEntity`` an.

    Bei vorhandenem LEI: Lookup ueber UNIQUE-LEI. Sonst: Name-Exact +
    optional country_code.
    """
    name = (getattr(corp_entity, "name", "") or "").strip()
    if not name:
        return None
    name_norm = _normalize_for_match(name)
    if not name_norm:
        return None
    lei = (getattr(corp_entity, "lei", "") or "").strip().upper() or None
    cc = getattr(corp_entity, "country", None) or None

    # 1. ueber LEI
    if lei:
        ent = _find_by_lei(db, lei)
        if ent is not None:
            # Adresse ergaenzen, country_code aktualisieren
            addr = getattr(corp_entity, "address", None)
            addresses = []
            if addr:
                addresses.append({
                    "city": "",
                    "postal_code": "",
                    "street": str(addr)[:300],
                    "country": (cc or "").upper(),
                    "source": "gleif",
                })
            _enrich_existing(
                ent, identifier=None,
                country_code=(cc or "").upper() or None,
                addresses=addresses,
                source="lei_corporate",
            )
            return ent

    # 2. ueber Name-Exact
    ent = _find_by_name_exact(db, name_norm, country_code=cc)
    if ent is not None:
        # LEI ergaenzen wenn moeglich (nur wenn die Entity noch keinen hat
        # und der LEI nicht woanders vergeben ist).
        if lei and not ent.lei:
            existing_with_lei = _find_by_lei(db, lei)
            if existing_with_lei is None:
                ent.lei = lei
        return ent

    # 3. Neu anlegen
    addresses: list[dict] = []
    addr = getattr(corp_entity, "address", None)
    if addr:
        addresses.append({
            "city": "",
            "postal_code": "",
            "street": str(addr)[:300],
            "country": (cc or "").upper(),
            "source": "gleif",
        })

    ent = _create_entity(
        db,
        canonical_name=name,
        canonical_name_normalized=name_norm,
        country_code=(cc or "").upper() or None,
        lei=lei,
        identifier=None,
        addresses=addresses,
        first_match_method="lei" if lei else "name_new",
    )
    stats["entities_created"] += 1
    return ent


__all__ = [
    "CONFIDENCE_LEI",
    "CONFIDENCE_IDENTIFIER",
    "CONFIDENCE_NAME_EXACT",
    "CONFIDENCE_FUZZY_THRESHOLD",
    "EntityMatchResult",
    "extract_lei_from_text",
    "is_valid_lei",
    "link_corporate_group_to_entities",
    "link_record",
    "rebuild_entities_from_beneficiaries",
    "rebuild_entities_from_sanctions",
    "rebuild_entities_from_state_aid",
    "resolve_entity",
]
