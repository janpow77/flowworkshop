"""
Unit-Tests fuer den Smart-Mode des State-Aid-Harvesters (Plan §11).

Schwerpunkt: pure helper ``_resolve_since`` — die Logik wurde bewusst aus
``run_harvest`` extrahiert, damit sie ohne TAM-Mocks und ohne DB-Verbindung
testbar ist.

Lauf: pytest backend/tests/test_state_aid_smart_mode.py -q
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── _resolve_since: Auto-Since-Logik ─────────────────────────────────────────


def test_resolve_since_smart_with_last_run_uses_lookback():
    """Smart-Modus + last_successful_harvest_at -> 14 Tage davor."""
    from services.state_aid_harvester import _resolve_since, SMART_LOOKBACK_DAYS

    last_run = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
    effective, auto_used = _resolve_since(
        mode="smart",
        explicit_since=None,
        last_successful_harvest_at=last_run,
    )
    assert auto_used is True
    assert effective == last_run.date() - timedelta(days=SMART_LOOKBACK_DAYS)
    # Konkret: 14 Tage vor 2026-05-01 = 2026-04-17
    assert effective == date(2026, 4, 17)


def test_resolve_since_smart_clamps_to_min_date():
    """Auto-Since darf nie vor SMART_MIN_DATE (1990-01-01) liegen."""
    from services.state_aid_harvester import _resolve_since, SMART_MIN_DATE

    # Last run unrealistisch frueh — clamp greift
    last_run = datetime(1990, 1, 5, tzinfo=timezone.utc)
    effective, auto_used = _resolve_since(
        mode="smart",
        explicit_since=None,
        last_successful_harvest_at=last_run,
    )
    assert auto_used is True
    assert effective == SMART_MIN_DATE


def test_resolve_since_explicit_overrides_auto():
    """Wenn der Aufrufer einen since-Wert mitschickt, ist Auto-Since aus."""
    from services.state_aid_harvester import _resolve_since

    last_run = datetime(2026, 5, 1, tzinfo=timezone.utc)
    explicit = date(2024, 1, 1)
    effective, auto_used = _resolve_since(
        mode="smart",
        explicit_since=explicit,
        last_successful_harvest_at=last_run,
    )
    assert auto_used is False
    assert effective == explicit


def test_resolve_since_smart_without_last_run_returns_none():
    """Erster Lauf (kein last_successful_harvest_at) -> kein Auto-Since."""
    from services.state_aid_harvester import _resolve_since

    effective, auto_used = _resolve_since(
        mode="smart",
        explicit_since=None,
        last_successful_harvest_at=None,
    )
    assert auto_used is False
    assert effective is None


def test_resolve_since_full_refresh_no_auto_since():
    """Full-Refresh-Modus: nie Auto-Since, immer expliziten Wert (oder None)."""
    from services.state_aid_harvester import _resolve_since

    last_run = datetime(2026, 5, 1, tzinfo=timezone.utc)
    # ohne explicit -> None, kein Auto
    eff_a, auto_a = _resolve_since(
        mode="full-refresh",
        explicit_since=None,
        last_successful_harvest_at=last_run,
    )
    assert (eff_a, auto_a) == (None, False)

    # mit explicit -> wird durchgereicht
    eff_b, auto_b = _resolve_since(
        mode="full-refresh",
        explicit_since=date(2024, 1, 1),
        last_successful_harvest_at=last_run,
    )
    assert eff_b == date(2024, 1, 1)
    assert auto_b is False


def test_resolve_since_force_no_auto_since():
    """Force-Modus: kein Auto-Since (TAM-Filter unabhaengig vom Delete)."""
    from services.state_aid_harvester import _resolve_since

    last_run = datetime(2026, 5, 1, tzinfo=timezone.utc)
    eff, auto = _resolve_since(
        mode="force",
        explicit_since=None,
        last_successful_harvest_at=last_run,
    )
    assert eff is None
    assert auto is False


def test_resolve_since_custom_lookback():
    """Lookback-Tage muessen ueberschreibbar sein (z.B. fuer Tests)."""
    from services.state_aid_harvester import _resolve_since

    last_run = datetime(2026, 5, 15, tzinfo=timezone.utc)
    effective, auto_used = _resolve_since(
        mode="smart",
        explicit_since=None,
        last_successful_harvest_at=last_run,
        lookback_days=30,
    )
    assert auto_used is True
    assert effective == date(2026, 4, 15)


# ── HarvestParams: Default-Mode ──────────────────────────────────────────────


def test_harvest_params_default_mode_is_smart():
    """Per Default ist mode='smart' — niemand soll versehentlich UPDATE machen."""
    from services.state_aid_harvester import HarvestParams

    p = HarvestParams(country_iso3="DEU")
    assert p.mode == "smart"


def test_harvest_result_has_records_skipped_default_zero():
    """Neuer Counter records_skipped existiert und ist standardmaessig 0."""
    from services.state_aid_harvester import HarvestResult

    r = HarvestResult(
        run_id="x", status="ok", records_seen=0,
        records_inserted=0, records_updated=0, records_failed=0,
    )
    assert r.records_skipped == 0
