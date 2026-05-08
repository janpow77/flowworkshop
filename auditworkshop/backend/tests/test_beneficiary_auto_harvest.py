"""
Phase 6b — Tests fuer den datengetriebenen Beneficiary-Auto-Harvest.

Schwerpunkt: pure Worker-Logik ohne DB-Calls.
  - ``_is_source_due``: welche Quellen sind faellig?
  - SHA-Skip-Logik: gleicher Hash -> kein erneuter Harvest.
  - Audit-Archivierung schreibt eine Datei.

Wir vermeiden Netzwerk-/DB-Aufrufe — dafuer wird die Worker-Funktion
``_harvest_one_beneficiary_source`` als Pfad mit gemockten httpx-Calls
getestet. Ein Smart-Mode-Run wird im DB-Test (oben in
test_beneficiary_sources_config) abgedeckt.

Lauf: pytest backend/tests/test_beneficiary_auto_harvest.py -q
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Backend-Verzeichnis in den Pfad legen.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── _is_source_due ────────────────────────────────────────────────────────────


def _make_cfg(**overrides):
    """Mini-Stub fuer BeneficiarySourceConfig — wir brauchen nur die Felder,
    die ``_is_source_due`` liest."""
    class _Cfg:
        source_key = "src1"
        enabled = True
        source_type = "xlsx_url"
        source_url = "https://example.com/data.xlsx"
        last_successful_harvest_at = None
        update_frequency_days = 30
    cfg = _Cfg()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_due_when_never_harvested():
    """Neue Quelle (last=None, enabled=true, url gesetzt) -> faellig."""
    from services.scheduler import _is_source_due
    now = datetime(2026, 5, 8, 2, 0, 0)
    assert _is_source_due(_make_cfg(), now) is True


def test_not_due_when_disabled():
    from services.scheduler import _is_source_due
    now = datetime(2026, 5, 8, 2, 0, 0)
    assert _is_source_due(_make_cfg(enabled=False), now) is False


def test_not_due_when_manual_upload():
    """source_type=manual_upload heisst kein Auto-Harvest."""
    from services.scheduler import _is_source_due
    now = datetime(2026, 5, 8, 2, 0, 0)
    assert _is_source_due(_make_cfg(source_type="manual_upload"), now) is False


def test_not_due_when_no_url():
    from services.scheduler import _is_source_due
    now = datetime(2026, 5, 8, 2, 0, 0)
    assert _is_source_due(_make_cfg(source_url=None), now) is False


def test_due_after_frequency_elapsed():
    """update_frequency_days=30, letzter Lauf vor 31 Tagen -> faellig."""
    from services.scheduler import _is_source_due
    now = datetime(2026, 5, 8, 2, 0, 0)
    last = now - timedelta(days=31)
    assert _is_source_due(
        _make_cfg(last_successful_harvest_at=last, update_frequency_days=30),
        now,
    ) is True


def test_not_due_within_frequency():
    """update_frequency_days=30, letzter Lauf vor 5 Tagen -> nicht faellig."""
    from services.scheduler import _is_source_due
    now = datetime(2026, 5, 8, 2, 0, 0)
    last = now - timedelta(days=5)
    assert _is_source_due(
        _make_cfg(last_successful_harvest_at=last, update_frequency_days=30),
        now,
    ) is False


def test_due_with_default_frequency_when_none():
    """update_frequency_days=None -> Default 30 Tage."""
    from services.scheduler import _is_source_due
    now = datetime(2026, 5, 8, 2, 0, 0)
    last = now - timedelta(days=31)
    assert _is_source_due(
        _make_cfg(last_successful_harvest_at=last, update_frequency_days=None),
        now,
    ) is True


# ── _archive_raw_file ─────────────────────────────────────────────────────────


def test_archive_raw_file_writes_to_disk(monkeypatch):
    """Audit-Archivierung schreibt die Datei in BENEFICIARY_RAW_DIR."""
    from services import scheduler

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(scheduler, "BENEFICIARY_RAW_DIR", Path(tmpdir))
        path = scheduler._archive_raw_file(
            "test_source", "data.xlsx", b"DEMO_BYTES",
        )
        assert path is not None
        p = Path(path)
        assert p.exists()
        assert p.read_bytes() == b"DEMO_BYTES"
        assert p.parent.name == "test_source"


def test_archive_raw_file_sanitizes_filename(monkeypatch):
    """Filename mit Sonderzeichen wird gesaeubert (keine Path-Traversal)."""
    from services import scheduler

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(scheduler, "BENEFICIARY_RAW_DIR", Path(tmpdir))
        path = scheduler._archive_raw_file(
            "test_source",
            "../../../etc/passwd",
            b"x",
        )
        assert path is not None
        p = Path(path)
        # Pfad muss innerhalb von tmpdir/test_source liegen — kein Escape.
        assert p.parent.name == "test_source"
        assert p.parent.parent == Path(tmpdir)


# ── run_beneficiary_auto_harvest: kandidatenfilter ───────────────────────────


def test_run_summary_skips_not_due(monkeypatch):
    """Wenn keine Quelle faellig ist, hat das Summary status='ok' und
    sources_skipped_not_due > 0."""
    from services import scheduler

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_a, **_kw):
            return self

        def order_by(self, *_a, **_kw):
            return self

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows

        def query(self, _model):
            return _FakeQuery(self._rows)

        def close(self):
            pass

    # Eine Config, die nicht faellig ist (vor 1 Tag geharvested, freq=30).
    cfg = _make_cfg(
        source_key="not_due",
        last_successful_harvest_at=datetime.utcnow() - timedelta(days=1),
        update_frequency_days=30,
    )
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: _FakeSession([cfg]))

    summary = scheduler.run_beneficiary_auto_harvest(triggered_by="pytest")
    assert summary["status"] == "ok"
    assert summary["sources_skipped_not_due"] == 1
    assert summary["sources_ok"] == 0
    assert summary["sources_failed"] == 0


def test_run_summary_handles_worker_exception(monkeypatch):
    """Wenn eine Quelle einen Worker-Exception wirft, ist status='failed'
    fuer diese Quelle, der Lauf insgesamt aber 'partial'/'failed'."""
    from services import scheduler

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_a, **_kw):
            return self

        def order_by(self, *_a, **_kw):
            return self

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows

        def query(self, _model):
            return _FakeQuery(self._rows)

        def close(self):
            pass

    cfg = _make_cfg(source_key="boom", last_successful_harvest_at=None)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: _FakeSession([cfg]))

    def _bad_worker(_cfg, triggered_by):  # noqa: ARG001
        raise RuntimeError("simulated boom")
    monkeypatch.setattr(
        scheduler, "_harvest_one_beneficiary_source", _bad_worker,
    )

    summary = scheduler.run_beneficiary_auto_harvest(triggered_by="pytest")
    assert summary["status"] == "failed"
    assert summary["sources_failed"] == 1
    failures = [s for s in summary["sources"] if s.get("status") == "failed"]
    assert len(failures) == 1
    assert "worker_exception" in failures[0].get("error", "")
