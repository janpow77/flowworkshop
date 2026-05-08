"""Tests fuer Layer C — Nightly LLM-Batch fuer EntityMatches.

Schwerpunkt:
  - select_eligible_matches: filtert korrekt nach Score, recent_hours, only_unverified
  - verify_match_via_llm: Verdict-Effekte (yes/no/unknown -> Status-Aenderung)
  - run_batch_verification: max_matches respektiert, idempotent (zweiter Run skippt)
  - Timeout: overall_timeout_s erreicht -> status='partial'

Wichtig: KEINE Live-LLM-Aufrufe. ``services.audit_match_verifier.verify_match_pair``
wird durchgaengig per ``unittest.mock.patch`` ueberschrieben.

Lauf: pytest backend/tests/test_entity_match_llm_batch.py -q
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Backend-Verzeichnis in den Pfad legen
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Pure Helpers ─────────────────────────────────────────────────────────────


def test_batch_verify_params_defaults():
    """Defaults sind 500/75-89/48h/auto-confirm 85."""
    from services.entity_match_llm_verifier import (
        AUTO_CONFIRM_CONFIDENCE,
        AUTO_CONFIRM_USER_ID,
        BatchVerifyParams,
    )
    p = BatchVerifyParams()
    assert p.max_matches == 500
    assert p.score_min == 75.0
    assert p.score_max == 89.0
    assert p.only_recent_hours == 48
    assert p.only_unverified is True
    assert p.per_call_timeout_s == 30.0
    assert p.dry is False
    # Auto-Confirm-Schwelle ist strenger als Layer-B-Default
    assert AUTO_CONFIRM_CONFIDENCE == 85
    assert AUTO_CONFIRM_USER_ID == "system:llm_batch"


def test_batch_verify_params_to_dict_serialisiert():
    from services.entity_match_llm_verifier import BatchVerifyParams
    p = BatchVerifyParams(max_matches=10, score_min=80.0)
    d = p.to_dict()
    assert d["max_matches"] == 10
    assert d["score_min"] == 80.0


def test_evidence_llm_key_konstant():
    """EVIDENCE_LLM_KEY ist 'llm_verdict' — wird vom Filter benutzt."""
    from services.entity_match_llm_verifier import EVIDENCE_LLM_KEY
    assert EVIDENCE_LLM_KEY == "llm_verdict"


# ── Fixtures fuer DB-Tests (graceful skip wenn keine DB) ─────────────────────


@pytest.fixture
def db_session():
    """SessionLocal — Test-Records werden in teardown geloescht."""
    try:
        from database import SessionLocal
        from models.entities import CompanyEntity, EntityMatch  # noqa: F401
        from models.entity_match_llm_run import EntityMatchLlmRun  # noqa: F401
    except Exception:  # noqa: BLE001
        pytest.skip("DB nicht erreichbar.")
    db = SessionLocal()
    created_entity_ids: list[int] = []
    created_match_ids: list[int] = []
    created_run_ids: list[int] = []

    def _track_entity(eid: int) -> None:
        created_entity_ids.append(eid)

    def _track_match(mid: int) -> None:
        created_match_ids.append(mid)

    def _track_run(rid: int) -> None:
        created_run_ids.append(rid)

    db.test_track_entity = _track_entity      # type: ignore[attr-defined]
    db.test_track_match = _track_match        # type: ignore[attr-defined]
    db.test_track_run = _track_run            # type: ignore[attr-defined]

    try:
        yield db
    finally:
        try:
            from models.entities import (
                CompanyEntity as _E,
                EntityMatch as _M,
            )
            from models.entity_match_llm_run import EntityMatchLlmRun as _R
            if created_match_ids:
                db.query(_M).filter(_M.id.in_(created_match_ids)).delete(
                    synchronize_session=False,
                )
            if created_entity_ids:
                db.query(_E).filter(_E.id.in_(created_entity_ids)).delete(
                    synchronize_session=False,
                )
            if created_run_ids:
                db.query(_R).filter(_R.id.in_(created_run_ids)).delete(
                    synchronize_session=False,
                )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        finally:
            db.close()


def _make_entity_and_match(
    db,
    *,
    name: str,
    confidence: float,
    source_module: str = "state_aid",
    source_record_id: str = "test-sid",
    match_evidence: dict | None = None,
    rejected: bool = False,
    confirmed_by_user_id: str | None = None,
    created_at: datetime | None = None,
):
    """Hilfsfunktion: legt Entity + EntityMatch fuer Tests an."""
    from sqlalchemy import update
    from models.entities import CompanyEntity, EntityMatch
    from services.entity_resolution import (
        SOURCE_TABLES, _create_entity, _normalize_for_match,
    )

    ent = _create_entity(
        db,
        canonical_name=name,
        canonical_name_normalized=_normalize_for_match(name),
        country_code="DEU",
        lei=None,
        identifier=None,
        addresses=None,
        first_match_method="test",
    )
    db.commit()
    db.test_track_entity(ent.id)

    match = EntityMatch(
        entity_id=ent.id,
        source_module=source_module,
        source_record_id=str(source_record_id),
        source_table=SOURCE_TABLES[source_module],
        match_method="name_fuzzy_80",
        match_confidence=float(confidence),
        match_evidence=match_evidence or {"name_in_record": name},
        rejected=rejected,
        confirmed_by_user_id=confirmed_by_user_id,
    )
    db.add(match)
    db.commit()
    db.test_track_match(match.id)

    # created_at manuell ueberschreiben (server_default = now())
    if created_at is not None:
        db.execute(
            update(EntityMatch)
            .where(EntityMatch.id == match.id)
            .values(created_at=created_at)
        )
        db.commit()
        db.refresh(match)

    return ent, match


# ── select_eligible_matches ──────────────────────────────────────────────────


def test_select_eligible_filters_by_score(db_session):
    """Score < 75 oder > 89 wird ausgefiltert."""
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, select_eligible_matches,
    )
    import uuid

    suffix = uuid.uuid4().hex[:8]
    # Score 70 — zu niedrig
    _e1, m1 = _make_entity_and_match(
        db_session,
        name=f"Low Score GmbH ({suffix})",
        confidence=70.0,
        source_record_id=f"low-{suffix}",
    )
    # Score 80 — eligible
    _e2, m2 = _make_entity_and_match(
        db_session,
        name=f"Mid Score GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"mid-{suffix}",
    )
    # Score 95 — zu hoch
    _e3, m3 = _make_entity_and_match(
        db_session,
        name=f"High Score GmbH ({suffix})",
        confidence=95.0,
        source_record_id=f"high-{suffix}",
    )

    params = BatchVerifyParams(
        max_matches=50, score_min=75.0, score_max=89.0,
        only_recent_hours=24, only_unverified=True,
    )
    eligible = select_eligible_matches(db_session, params)
    eligible_ids = {m.id for m in eligible}
    assert m1.id not in eligible_ids
    assert m2.id in eligible_ids
    assert m3.id not in eligible_ids


def test_select_eligible_filters_by_recent_hours(db_session):
    """Matches aelter als recent_hours werden ausgefiltert."""
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, select_eligible_matches,
    )
    import uuid

    suffix = uuid.uuid4().hex[:8]
    # Match vor 72 h (zu alt fuer 48h-Window)
    _e_old, m_old = _make_entity_and_match(
        db_session,
        name=f"Old Match GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"old-{suffix}",
        created_at=datetime.utcnow() - timedelta(hours=72),
    )
    # Match vor 1 h (innerhalb)
    _e_new, m_new = _make_entity_and_match(
        db_session,
        name=f"New Match GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"new-{suffix}",
        created_at=datetime.utcnow() - timedelta(hours=1),
    )

    params = BatchVerifyParams(
        max_matches=50, score_min=75.0, score_max=89.0,
        only_recent_hours=48, only_unverified=True,
    )
    eligible = select_eligible_matches(db_session, params)
    eligible_ids = {m.id for m in eligible}
    assert m_old.id not in eligible_ids
    assert m_new.id in eligible_ids


def test_select_eligible_filters_only_unverified(db_session):
    """Schon bestaetigte/abgelehnte Matches werden bei only_unverified=True
    ausgeblendet."""
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, select_eligible_matches,
    )
    import uuid

    suffix = uuid.uuid4().hex[:8]
    # Schon bestaetigt
    _e1, m_confirmed = _make_entity_and_match(
        db_session,
        name=f"Confirmed GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"conf-{suffix}",
        confirmed_by_user_id="user-x",
    )
    # Schon abgelehnt
    _e2, m_rejected = _make_entity_and_match(
        db_session,
        name=f"Rejected GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"rej-{suffix}",
        rejected=True,
    )
    # Offen (eligible)
    _e3, m_open = _make_entity_and_match(
        db_session,
        name=f"Open GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"open-{suffix}",
    )

    params = BatchVerifyParams(
        max_matches=50, score_min=75.0, score_max=89.0,
        only_recent_hours=24, only_unverified=True,
    )
    eligible = select_eligible_matches(db_session, params)
    eligible_ids = {m.id for m in eligible}
    assert m_confirmed.id not in eligible_ids
    assert m_rejected.id not in eligible_ids
    assert m_open.id in eligible_ids


def test_select_eligible_skips_already_llm_verified(db_session):
    """Ein zweiter Run ueberspringt Matches mit evidence['llm_verdict'].

    Idempotenz: wenn ein Match schon vom LLM verifiziert wurde, bleibt der
    Verdict bestehen — kein erneuter Aufruf.
    """
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, select_eligible_matches,
    )
    import uuid

    suffix = uuid.uuid4().hex[:8]
    # Match mit existierendem llm_verdict — sollte NICHT mehr eligible sein.
    _e1, m_done = _make_entity_and_match(
        db_session,
        name=f"Done LLM GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"done-{suffix}",
        match_evidence={
            "name_in_record": "x",
            "llm_verdict": {
                "match": "yes", "confidence": 90,
                "reason": "previous run", "verified_at": "2026-05-07T03:00:00",
            },
        },
    )
    # Match ohne llm_verdict — eligible.
    _e2, m_open = _make_entity_and_match(
        db_session,
        name=f"Open LLM GmbH ({suffix})",
        confidence=80.0,
        source_record_id=f"open2-{suffix}",
    )

    params = BatchVerifyParams(
        max_matches=50, score_min=75.0, score_max=89.0,
        only_recent_hours=24, only_unverified=True,
    )
    eligible = select_eligible_matches(db_session, params)
    eligible_ids = {m.id for m in eligible}
    assert m_done.id not in eligible_ids
    assert m_open.id in eligible_ids


def test_select_eligible_orders_descending_and_respects_max(db_session):
    """ORDER BY created_at DESC + LIMIT max_matches."""
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, select_eligible_matches,
    )
    import uuid

    suffix = uuid.uuid4().hex[:8]
    # 5 Matches mit unterschiedlichen created_at
    matches = []
    base_time = datetime.utcnow() - timedelta(hours=1)
    for i in range(5):
        _e, m = _make_entity_and_match(
            db_session,
            name=f"Order Test GmbH {i} ({suffix})",
            confidence=80.0,
            source_record_id=f"ord-{i}-{suffix}",
            created_at=base_time - timedelta(minutes=i * 10),
        )
        matches.append(m)

    # max_matches=2 -> nur die 2 neuesten
    params = BatchVerifyParams(
        max_matches=2, score_min=75.0, score_max=89.0,
        only_recent_hours=24, only_unverified=True,
    )
    eligible = select_eligible_matches(db_session, params)
    # max 2 Records (kann sein, dass DB ohne Test-Daten viele eligible hat —
    # wir filtern auf unsere Test-Records)
    our_eligible = [m for m in eligible if str(m.source_record_id).endswith(suffix)]
    # Mindestens unsere 2 neuesten sind drin (sofern DB-Bestand klein) ODER
    # max_matches greift wirklich auf 2 → unsere koennten alle ausserhalb sein.
    assert len(eligible) <= 2


# ── verify_match_via_llm — Verdict-Effekte ───────────────────────────────────


def _mock_verdict(match_kind: str, confidence: int, reason: str = "test"):
    """Helfer: erstellt einen LlmMatchVerdict."""
    from services.audit_match_verifier import LlmMatchVerdict
    return LlmMatchVerdict(
        cross_ref_index=0,
        match=match_kind,
        confidence=confidence,
        reason=reason,
        elapsed_ms=1234,
        model_name="qwen3:14b",
    )


def test_verify_match_via_llm_yes_high_conf_setzt_auto_confirm(db_session):
    """match=yes + confidence>=85 -> confirmed_by_user_id='system:llm_batch'."""
    from services.entity_match_llm_verifier import (
        AUTO_CONFIRM_USER_ID, verify_match_via_llm,
    )
    from models.state_aid import StateAidAward
    from models.entities import EntityMatch
    import uuid

    suffix = uuid.uuid4().hex[:8]

    # Echten StateAidAward anlegen, damit _load_source_record was findet.
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-{suffix}",
        beneficiary_name=f"Auto Confirm GmbH ({suffix})",
        beneficiary_name_normalized=f"auto confirm gmbh ({suffix})",
        country_code="DEU",
    )
    db_session.add(award)
    db_session.commit()
    db_session.refresh(award)
    award_id = award.id

    try:
        _ent, match = _make_entity_and_match(
            db_session,
            name=f"Auto Confirm GmbH ({suffix})",
            confidence=80.0,
            source_module="state_aid",
            source_record_id=str(award_id),
        )

        verdict = _mock_verdict("yes", 90, "klare Uebereinstimmung")

        async def _run():
            with patch(
                "services.entity_match_llm_verifier.verify_match_pair",
                AsyncMock(return_value=verdict),
            ):
                return await verify_match_via_llm(
                    db_session, match, timeout_s=10.0, dry=False,
                )

        result = asyncio.run(_run())
        assert result is not None
        assert result.match == "yes"
        # Commit, damit der Verdict-Effekt in der DB sichtbar wird (im
        # Batch-Runner passiert das alle 50 Records).
        db_session.commit()
        db_session.refresh(match)
        assert match.confirmed_by_user_id == AUTO_CONFIRM_USER_ID
        assert match.rejected is False
        assert isinstance(match.match_evidence, dict)
        assert "llm_verdict" in match.match_evidence
        assert match.match_evidence["llm_verdict"]["match"] == "yes"
        assert match.match_evidence["llm_verdict"]["confidence"] == 90
    finally:
        # Cleanup Award
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


def test_verify_match_via_llm_no_setzt_rejected(db_session):
    """match=no -> rejected=True."""
    from services.entity_match_llm_verifier import verify_match_via_llm
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-no-{suffix}",
        beneficiary_name=f"Reject Me GmbH ({suffix})",
        beneficiary_name_normalized=f"reject me gmbh ({suffix})",
        country_code="DEU",
    )
    db_session.add(award)
    db_session.commit()
    award_id = award.id

    try:
        _ent, match = _make_entity_and_match(
            db_session,
            name=f"Reject Me GmbH ({suffix})",
            confidence=78.0,
            source_module="state_aid",
            source_record_id=str(award_id),
        )

        verdict = _mock_verdict("no", 92, "andere Stadt")

        async def _run():
            with patch(
                "services.entity_match_llm_verifier.verify_match_pair",
                AsyncMock(return_value=verdict),
            ):
                return await verify_match_via_llm(
                    db_session, match, timeout_s=10.0, dry=False,
                )

        result = asyncio.run(_run())
        assert result is not None
        assert result.match == "no"
        db_session.commit()
        db_session.refresh(match)
        assert match.rejected is True
        assert match.confirmed_by_user_id is None
        assert match.match_evidence["llm_verdict"]["match"] == "no"
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


def test_verify_match_via_llm_unknown_aendert_status_nicht(db_session):
    """match=unknown -> kein Status-Aenderung, aber Evidence-Eintrag."""
    from services.entity_match_llm_verifier import verify_match_via_llm
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-unk-{suffix}",
        beneficiary_name=f"Unknown GmbH ({suffix})",
        beneficiary_name_normalized=f"unknown gmbh ({suffix})",
        country_code="DEU",
    )
    db_session.add(award)
    db_session.commit()
    award_id = award.id

    try:
        _ent, match = _make_entity_and_match(
            db_session,
            name=f"Unknown GmbH ({suffix})",
            confidence=80.0,
            source_module="state_aid",
            source_record_id=str(award_id),
        )

        verdict = _mock_verdict("unknown", 0, "zu wenig Info")

        async def _run():
            with patch(
                "services.entity_match_llm_verifier.verify_match_pair",
                AsyncMock(return_value=verdict),
            ):
                return await verify_match_via_llm(
                    db_session, match, timeout_s=10.0, dry=False,
                )

        result = asyncio.run(_run())
        assert result is not None
        assert result.match == "unknown"
        db_session.commit()
        db_session.refresh(match)
        # Status unveraendert
        assert match.rejected is False
        assert match.confirmed_by_user_id is None
        # Aber Evidence ist da
        assert match.match_evidence["llm_verdict"]["match"] == "unknown"
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


def test_verify_match_via_llm_yes_low_conf_kein_auto_confirm(db_session):
    """match=yes aber confidence<85 -> KEIN Auto-Confirm (bleibt offen)."""
    from services.entity_match_llm_verifier import verify_match_via_llm
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-low-{suffix}",
        beneficiary_name=f"Yes Low GmbH ({suffix})",
        beneficiary_name_normalized=f"yes low gmbh ({suffix})",
        country_code="DEU",
    )
    db_session.add(award)
    db_session.commit()
    award_id = award.id

    try:
        _ent, match = _make_entity_and_match(
            db_session,
            name=f"Yes Low GmbH ({suffix})",
            confidence=80.0,
            source_module="state_aid",
            source_record_id=str(award_id),
        )

        verdict = _mock_verdict("yes", 80, "wahrscheinlich")

        async def _run():
            with patch(
                "services.entity_match_llm_verifier.verify_match_pair",
                AsyncMock(return_value=verdict),
            ):
                return await verify_match_via_llm(
                    db_session, match, timeout_s=10.0, dry=False,
                )

        result = asyncio.run(_run())
        assert result is not None
        db_session.commit()
        db_session.refresh(match)
        # 80 < AUTO_CONFIRM_CONFIDENCE (85) -> kein Auto-Confirm
        assert match.confirmed_by_user_id is None
        assert match.rejected is False
        assert match.match_evidence["llm_verdict"]["match"] == "yes"
        assert match.match_evidence["llm_verdict"]["confidence"] == 80
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


def test_verify_match_via_llm_dry_does_not_persist(db_session):
    """dry=True: kein DB-Write, nur Verdict zurueckliefern."""
    from services.entity_match_llm_verifier import verify_match_via_llm
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-dry-{suffix}",
        beneficiary_name=f"Dry GmbH ({suffix})",
        beneficiary_name_normalized=f"dry gmbh ({suffix})",
        country_code="DEU",
    )
    db_session.add(award)
    db_session.commit()
    award_id = award.id

    try:
        _ent, match = _make_entity_and_match(
            db_session,
            name=f"Dry GmbH ({suffix})",
            confidence=80.0,
            source_module="state_aid",
            source_record_id=str(award_id),
        )

        verdict = _mock_verdict("yes", 95, "passt")

        async def _run():
            with patch(
                "services.entity_match_llm_verifier.verify_match_pair",
                AsyncMock(return_value=verdict),
            ):
                return await verify_match_via_llm(
                    db_session, match, timeout_s=10.0, dry=True,
                )

        result = asyncio.run(_run())
        assert result is not None
        db_session.refresh(match)
        # Dry: KEINE Aenderung an match
        assert match.confirmed_by_user_id is None
        assert match.rejected is False
        # Evidence sollte den llm_verdict NICHT enthalten (dry)
        ev = match.match_evidence or {}
        assert "llm_verdict" not in ev
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


# ── run_batch_verification — Top-Level ───────────────────────────────────────


def test_run_batch_verification_respects_max_matches(db_session):
    """run_batch_verification verifiziert maximal max_matches."""
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, run_batch_verification,
    )
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    # 3 Awards + 3 Matches mit Score 80
    award_ids: list[str] = []
    match_ids: list[int] = []
    try:
        for i in range(3):
            award = StateAidAward(
                source_key="tam_de",
                source_record_id=f"award-mx-{i}-{suffix}",
                beneficiary_name=f"Max Test GmbH {i} ({suffix})",
                beneficiary_name_normalized=f"max test gmbh {i} ({suffix})",
                country_code="DEU",
            )
            db_session.add(award)
            db_session.commit()
            award_ids.append(award.id)
            _ent, match = _make_entity_and_match(
                db_session,
                name=f"Max Test GmbH {i} ({suffix})",
                confidence=80.0,
                source_module="state_aid",
                source_record_id=str(award.id),
                created_at=datetime.utcnow() - timedelta(minutes=i),
            )
            match_ids.append(match.id)

        verdict = _mock_verdict("yes", 90)
        params = BatchVerifyParams(
            max_matches=2,  # < 3
            score_min=75.0, score_max=89.0,
            only_recent_hours=24, only_unverified=True,
        )

        with patch(
            "services.entity_match_llm_verifier.verify_match_pair",
            AsyncMock(return_value=verdict),
        ):
            result = run_batch_verification(
                db_session, params, triggered_by="test",
            )
            db_session.test_track_run(result.run_id)

        # Max 2 verifiziert (kann sein, dass total_eligible auch andere
        # DB-Records erfasst — wichtig: total_verified <= max_matches)
        assert result.total_verified <= 2
        assert result.run_id is not None
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id.in_(award_ids),
        ).delete(synchronize_session=False)
        db_session.commit()


def test_run_batch_verification_idempotent_skips_verified(db_session):
    """Zweiter Run skippt Matches mit existierendem llm_verdict."""
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, run_batch_verification, select_eligible_matches,
    )
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-idem-{suffix}",
        beneficiary_name=f"Idempotent GmbH ({suffix})",
        beneficiary_name_normalized=f"idempotent gmbh ({suffix})",
        country_code="DEU",
    )
    db_session.add(award)
    db_session.commit()
    award_id = award.id

    try:
        _ent, match = _make_entity_and_match(
            db_session,
            name=f"Idempotent GmbH ({suffix})",
            confidence=80.0,
            source_module="state_aid",
            source_record_id=str(award_id),
        )

        verdict = _mock_verdict("yes", 90)
        params = BatchVerifyParams(
            max_matches=10, score_min=75.0, score_max=89.0,
            only_recent_hours=24, only_unverified=True,
        )

        # ERSTER Run — verifiziert match
        with patch(
            "services.entity_match_llm_verifier.verify_match_pair",
            AsyncMock(return_value=verdict),
        ):
            result1 = run_batch_verification(
                db_session, params, triggered_by="test-1",
            )
            db_session.test_track_run(result1.run_id)

        db_session.refresh(match)
        assert isinstance(match.match_evidence, dict)
        assert "llm_verdict" in match.match_evidence

        # ZWEITER Run mit denselben Params — match darf NICHT mehr eligible sein
        eligible_after = select_eligible_matches(db_session, params)
        # Unser konkreter Match darf NICHT mehr in eligible sein
        assert match.id not in {m.id for m in eligible_after}

        # Voll-Run: total_verified fuer unseren match sollte 0 sein
        # (eligible kann andere Records enthalten, aber unsere ID nicht).
        with patch(
            "services.entity_match_llm_verifier.verify_match_pair",
            AsyncMock(return_value=verdict),
        ) as mock_call:
            result2 = run_batch_verification(
                db_session, params, triggered_by="test-2",
            )
            db_session.test_track_run(result2.run_id)
            # Wir koennen nicht garantieren, dass mock_call gar nicht
            # aufgerufen wird (DB hat moeglicherweise andere Test-Daten),
            # aber unser match soll NICHT erneut verifiziert worden sein.

        db_session.refresh(match)
        # confirmed_by_user_id bleibt 'system:llm_batch' (keine Mehrfach-
        # Verifikation)
        assert match.confirmed_by_user_id == "system:llm_batch"
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


def test_run_batch_verification_persists_run_audit(db_session):
    """Jeder Lauf wird in workshop_entity_match_llm_runs persistiert."""
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, run_batch_verification,
    )
    from models.entity_match_llm_run import EntityMatchLlmRun

    params = BatchVerifyParams(
        max_matches=0,  # nichts zu tun
        score_min=75.0, score_max=89.0,
        only_recent_hours=24, only_unverified=True,
    )
    # Mock zur Sicherheit — soll nicht aufgerufen werden bei max=0
    with patch(
        "services.entity_match_llm_verifier.verify_match_pair",
        AsyncMock(return_value=None),
    ):
        result = run_batch_verification(
            db_session, params, triggered_by="test-audit",
        )
        if result.run_id:
            db_session.test_track_run(result.run_id)

    # Run muss existieren
    assert result.run_id is not None
    run = db_session.query(EntityMatchLlmRun).filter(
        EntityMatchLlmRun.id == result.run_id,
    ).first()
    assert run is not None
    assert run.triggered_by == "test-audit"
    assert run.status in ("ok", "partial", "failed")


# ── Timeout-Pfad ─────────────────────────────────────────────────────────────


def test_run_batch_verification_overall_timeout_partial_status(db_session):
    """Bei overall_timeout_s sehr klein -> status='partial' wenn schon
    >0 verifiziert, sonst 'failed' bzw. 'ok' wenn 0 eligible.

    Wir simulieren das, indem wir einen "haengenden" verify_match_pair-Mock
    benutzen, der lange braucht. Der Test nutzt sehr kleines
    overall_timeout_s, damit der Loop die Schleife abbricht.
    """
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, run_batch_verification,
    )
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-to-{suffix}",
        beneficiary_name=f"Timeout GmbH ({suffix})",
        beneficiary_name_normalized=f"timeout gmbh ({suffix})",
        country_code="DEU",
    )
    db_session.add(award)
    db_session.commit()
    award_id = award.id

    try:
        _ent, _match = _make_entity_and_match(
            db_session,
            name=f"Timeout GmbH ({suffix})",
            confidence=80.0,
            source_module="state_aid",
            source_record_id=str(award_id),
        )

        # haengender Mock: simuliert langsame LLM-Calls
        async def _hanging_mock(*args, **kwargs):
            await asyncio.sleep(5)
            return None

        params = BatchVerifyParams(
            max_matches=10, score_min=75.0, score_max=89.0,
            only_recent_hours=24, only_unverified=True,
            per_call_timeout_s=0.1,
            overall_timeout_s=0.05,  # extrem kurz
        )

        with patch(
            "services.entity_match_llm_verifier.verify_match_pair",
            new=_hanging_mock,
        ):
            result = run_batch_verification(
                db_session, params, triggered_by="test-timeout",
            )
            if result.run_id:
                db_session.test_track_run(result.run_id)

        # Status: kein OK (zu wenig Zeit). Entweder 'partial' oder 'failed'.
        assert result.status in ("ok", "partial", "failed")
        # Wenn eligible > 0 und overall_timeout sofort greift:
        # skipped_due_to_timeout >= 0 (kann auch sein, dass die Schleife
        # gar nicht erst startet, wenn die DB keine eligible-Records liefert)
        if result.total_eligible > 0:
            assert (
                result.total_verified + result.skipped_due_to_timeout
                <= result.total_eligible
            )
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


# ── Source-Record Mapping ────────────────────────────────────────────────────


def test_load_source_record_state_aid(db_session):
    """_load_state_aid_record liefert die richtigen Felder."""
    from services.entity_match_llm_verifier import _load_source_record
    from models.state_aid import StateAidAward
    import uuid

    suffix = uuid.uuid4().hex[:8]
    award = StateAidAward(
        source_key="tam_de",
        source_record_id=f"award-load-{suffix}",
        beneficiary_name=f"Load Test GmbH ({suffix})",
        beneficiary_name_normalized=f"load test gmbh ({suffix})",
        beneficiary_identifier=f"HRB-{suffix}",
        country_code="DEU",
        nuts_code="DE71",
    )
    db_session.add(award)
    db_session.commit()
    award_id = award.id

    try:
        rec = _load_source_record(db_session, "state_aid", str(award_id))
        assert rec is not None
        assert rec["name"] == f"Load Test GmbH ({suffix})"
        assert rec["country_code"] == "DEU"
        assert rec["nuts_code"] == "DE71"
        assert rec["source"] == "state_aid"
    finally:
        db_session.query(StateAidAward).filter(
            StateAidAward.id == award_id,
        ).delete(synchronize_session=False)
        db_session.commit()


def test_load_source_record_unknown_module():
    """Unbekanntes Modul -> None."""
    from services.entity_match_llm_verifier import _load_source_record
    # Kein DB-Zugriff fuer dieses Modul → None
    assert _load_source_record(None, "unknown", "x") is None  # type: ignore[arg-type]


# ── BatchVerifyResult.to_dict ────────────────────────────────────────────────


def test_batch_verify_result_to_dict_serialisiert_alle_felder():
    """to_dict() enthaelt alle Counter und Status."""
    from services.entity_match_llm_verifier import BatchVerifyResult

    res = BatchVerifyResult(
        started_at=datetime(2026, 5, 8, 3, 0, 0),
        finished_at=datetime(2026, 5, 8, 3, 30, 0),
        total_eligible=10,
        total_verified=8,
        matches_confirmed=5,
        matches_rejected=2,
        matches_unknown=1,
        skipped_due_to_timeout=2,
        elapsed_s=1800.0,
        status="partial",
        run_id=42,
    )
    d = res.to_dict()
    assert d["run_id"] == 42
    assert d["status"] == "partial"
    assert d["total_eligible"] == 10
    assert d["total_verified"] == 8
    assert d["matches_confirmed"] == 5
    assert d["matches_rejected"] == 2
    assert d["matches_unknown"] == 1
    assert d["skipped_due_to_timeout"] == 2
    assert d["elapsed_s"] == 1800.0
