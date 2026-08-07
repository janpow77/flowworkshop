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
    """Eine eingerichtete, heute nicht faellige Quelle ergibt 'idle'.

    Frueher meldete dieser Fall schlicht 'ok' — dadurch war er nicht von
    einem Lauf zu unterscheiden, der gar nichts holen konnte. Getrennt
    werden die beiden jetzt ueber 'idle' (normal) und 'noop' (Missstand).
    """
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
    assert summary["status"] == "idle"
    assert summary["sources_skipped_not_due"] == 1
    assert summary["sources_not_configured"] == 0
    assert summary["sources_ok"] == 0
    assert summary["sources_failed"] == 0


def test_manual_upload_zaehlt_als_nicht_konfiguriert(monkeypatch):
    """manual_upload ohne URL ist eine Konfigurationsluecke, kein 'not_due'.

    Genau dieser Fall lag in der Produktion vor: 35 Quellen ohne
    Download-URL wurden als 'nicht faellig' verbucht und blieben unsichtbar.
    """
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

    cfg = _make_cfg(
        source_key="manuell", source_type="manual_upload", source_url=None,
    )
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: _FakeSession([cfg]))

    summary = scheduler.run_beneficiary_auto_harvest(triggered_by="pytest")
    assert summary["status"] == "noop"
    assert summary["sources_not_configured"] == 1
    assert summary["sources_skipped_not_due"] == 0
    assert summary["sources_total"] == 1


def test_auto_capable_erkennt_konfigurationsluecken():
    """_is_source_auto_capable trennt Konfiguration von Faelligkeit."""
    from services.scheduler import _is_source_auto_capable

    assert _is_source_auto_capable(_make_cfg()) is True
    assert _is_source_auto_capable(_make_cfg(source_type="csv_url")) is True
    assert _is_source_auto_capable(_make_cfg(source_type="manual_upload")) is False
    assert _is_source_auto_capable(_make_cfg(source_url=None)) is False
    assert _is_source_auto_capable(_make_cfg(enabled=False)) is False


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


# ── Dateityp-Erkennung ────────────────────────────────────────────────────────


def test_dateiname_nutzt_endung_aus_url():
    """Eine saubere Endung in der URL wird uebernommen."""
    from services.scheduler import _dateiname_fuer_inhalt

    name = _dateiname_fuer_inhalt(
        "https://example.org/pfad/Liste_der_Vorhaben.xlsx", b"PK\x03\x04xx", "land_efre",
    )
    assert name == "Liste_der_Vorhaben.xlsx"


def test_dateiname_ignoriert_abfrageparameter():
    """`…liste.xlsx?ts=123` hat frueher die Typerkennung gebrochen."""
    from services.scheduler import _dateiname_fuer_inhalt

    name = _dateiname_fuer_inhalt(
        "https://example.org/liste.xlsx?ts=1774519001", b"PK\x03\x04xx", "land_esf",
    )
    assert name.endswith(".xlsx")


def test_dateiname_erkennt_xlsx_am_inhalt():
    """Adressen ohne Endung (z.B. sixcms/media.php/9/…) über den Inhalt lösen."""
    from services.scheduler import _dateiname_fuer_inhalt

    name = _dateiname_fuer_inhalt(
        "https://example.org/sixcms/media.php/9/12345", b"PK\x03\x04rest", "land_efre",
    )
    assert name == "land_efre.xlsx"


def test_dateiname_faellt_auf_csv_zurueck():
    """Kein ZIP-Kopf, keine Endung → als CSV behandeln."""
    from services.scheduler import _dateiname_fuer_inhalt

    name = _dateiname_fuer_inhalt(
        "https://example.org/export", b"Name;Ort\nMuster;Kassel\n", "land_esf",
    )
    assert name == "land_esf.csv"


def _fake_session_mit(cfgs):
    """Baut eine Session-Attrappe, die genau diese Configs liefert."""
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
        def query(self, _model):
            return _FakeQuery(cfgs)

        def close(self):
            pass

    return lambda: _FakeSession()


def test_eingerichtete_aber_nicht_faellige_quellen_sind_idle(monkeypatch):
    """Zwischen zwei Aktualisierungen ist Nichtstun der Normalfall.

    Das darf kein 'noop' mit Warnung sein — sonst kaeme bei einem
    Monatsintervall 29 von 30 Naechten ein Fehlalarm.
    """
    from services import scheduler

    cfg = _make_cfg(
        source_key="faellig_erst_spaeter",
        last_successful_harvest_at=datetime.utcnow() - timedelta(days=1),
        update_frequency_days=30,
    )
    monkeypatch.setattr(scheduler, "SessionLocal", _fake_session_mit([cfg]))

    summary = scheduler.run_beneficiary_auto_harvest(triggered_by="pytest")
    assert summary["status"] == "idle"
    assert summary["sources_auto_faehig"] == 1
    assert summary["sources_skipped_not_due"] == 1


def test_ohne_jede_holbare_quelle_bleibt_es_noop(monkeypatch):
    """Gibt es gar keine auto-faehige Quelle, ist das ein Missstand."""
    from services import scheduler

    cfg = _make_cfg(
        source_key="nur_manuell", source_type="manual_upload", source_url=None,
    )
    monkeypatch.setattr(scheduler, "SessionLocal", _fake_session_mit([cfg]))

    summary = scheduler.run_beneficiary_auto_harvest(triggered_by="pytest")
    assert summary["status"] == "noop"
    assert summary["sources_auto_faehig"] == 0
    assert summary["sources_not_configured"] == 1


# ── Meldung an die Admins ────────────────────────────────────────────────────


def _gesammelte_meldungen(monkeypatch):
    """Fängt ab, was an die Glocke ginge."""
    from services import scheduler

    gesendet = []
    monkeypatch.setattr(
        scheduler, "_benachrichtige_admins",
        lambda titel, text, **kw: gesendet.append((titel, text)),
    )
    return gesendet


def test_erfolgreicher_lauf_meldet_nichts(monkeypatch):
    """Wer bei jedem Erfolg meldet, wird nicht mehr gelesen."""
    from services.scheduler import _melde_beneficiary_ergebnis

    gesendet = _gesammelte_meldungen(monkeypatch)
    _melde_beneficiary_ergebnis({"status": "ok", "sources": []})
    assert gesendet == []


def test_leerlauf_meldet_nichts(monkeypatch):
    """Zwischen zwei Aktualisierungen ist Nichtstun der Regelfall."""
    from services.scheduler import _melde_beneficiary_ergebnis

    gesendet = _gesammelte_meldungen(monkeypatch)
    _melde_beneficiary_ergebnis({"status": "idle", "sources": []})
    assert gesendet == []


def test_fehlschlaege_ergeben_genau_eine_meldung(monkeypatch):
    """Bei zehn kaputten Quellen waeren zehn Eintraege kein Signal mehr."""
    from services.scheduler import _melde_beneficiary_ergebnis

    gesendet = _gesammelte_meldungen(monkeypatch)
    _melde_beneficiary_ergebnis({
        "status": "partial",
        "sources_auto_faehig": 29,
        "sources": (
            [{"source_key": f"land_{i}", "status": "failed", "error": "HTTP 404"}
             for i in range(9)]
            + [{"source_key": "land_ok", "status": "ok"}]
        ),
    })
    assert len(gesendet) == 1
    titel, text = gesendet[0]
    assert "9 von 29" in titel
    # Nur die ersten sechs werden aufgezaehlt, der Rest zusammengefasst.
    assert "und 3 weitere" in text


def test_ohne_abrufbare_quelle_wird_deutlich_gemeldet(monkeypatch):
    from services.scheduler import _melde_beneficiary_ergebnis

    gesendet = _gesammelte_meldungen(monkeypatch)
    _melde_beneficiary_ergebnis({
        "status": "noop", "sources": [], "sources_not_configured": 35,
    })
    assert len(gesendet) == 1
    assert "keine abrufbare Quelle" in gesendet[0][0]
    assert "35" in gesendet[0][1]
