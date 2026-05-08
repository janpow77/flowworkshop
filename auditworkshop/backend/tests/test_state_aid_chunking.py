"""
Unit-Tests fuer die Jahres-Chunk-Zerlegung des State-Aid-Harvesters
(Plan §11 — Chunked Harvest).

Pure-function-Tests fuer ``build_year_chunks`` ohne TAM/DB.

Lauf: pytest backend/tests/test_state_aid_chunking.py -q
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

# Backend-Verzeichnis in den Pfad legen, damit `scripts.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── build_year_chunks: Standardfall ──────────────────────────────────────────


def test_build_year_chunks_three_years_partial_borders():
    """since=2022-06-01, until=2024-03-01 -> drei Chunks (2022/23/24)
    mit korrekt geclippten Grenzen."""
    from scripts.harvest_state_aid import build_year_chunks

    chunks = build_year_chunks(date(2022, 6, 1), date(2024, 3, 1))
    assert chunks == [
        (date(2022, 6, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), date(2024, 3, 1)),
    ]


def test_build_year_chunks_full_history_until_today():
    """Full-History 2014-07-01 bis 2026-05-08 -> 13 Jahres-Chunks."""
    from scripts.harvest_state_aid import build_year_chunks

    chunks = build_year_chunks(date(2014, 7, 1), date(2026, 5, 8))
    # 2014..2026 inklusive = 13 Jahre
    assert len(chunks) == 13
    # Erstes Chunk-Start = explizites since (geclippt auf year_start=2014-01-01)
    assert chunks[0] == (date(2014, 7, 1), date(2014, 12, 31))
    # Letztes Chunk-End = explizites until
    assert chunks[-1] == (date(2026, 1, 1), date(2026, 5, 8))
    # Mittlere Jahre vollstaendig
    assert chunks[5] == (date(2019, 1, 1), date(2019, 12, 31))


def test_build_year_chunks_same_year_single_chunk():
    """since/until im selben Jahr -> genau ein Chunk mit Originalgrenzen."""
    from scripts.harvest_state_aid import build_year_chunks

    chunks = build_year_chunks(date(2024, 3, 1), date(2024, 9, 30))
    assert chunks == [(date(2024, 3, 1), date(2024, 9, 30))]


def test_build_year_chunks_full_year():
    """Volles Kalenderjahr -> ein Chunk 1.1. bis 31.12."""
    from scripts.harvest_state_aid import build_year_chunks

    chunks = build_year_chunks(date(2023, 1, 1), date(2023, 12, 31))
    assert chunks == [(date(2023, 1, 1), date(2023, 12, 31))]


def test_build_year_chunks_single_day():
    """since == until -> ein Chunk mit demselben Tag."""
    from scripts.harvest_state_aid import build_year_chunks

    d = date(2024, 6, 15)
    chunks = build_year_chunks(d, d)
    assert chunks == [(d, d)]


def test_build_year_chunks_two_consecutive_years():
    """Genau zwei Jahre, beide am Jahresanfang/-ende geclippt."""
    from scripts.harvest_state_aid import build_year_chunks

    chunks = build_year_chunks(date(2022, 11, 1), date(2023, 2, 28))
    assert chunks == [
        (date(2022, 11, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 2, 28)),
    ]


# ── Fehlerfaelle ─────────────────────────────────────────────────────────────


def test_build_year_chunks_since_after_until_raises():
    """since > until -> ValueError (Aufrufer-Fehler)."""
    from scripts.harvest_state_aid import build_year_chunks

    with pytest.raises(ValueError):
        build_year_chunks(date(2024, 6, 1), date(2024, 5, 1))


# ── Eigenschaften ────────────────────────────────────────────────────────────


def test_build_year_chunks_no_overlap_no_gap():
    """Aufeinanderfolgende Chunks sind Tag-genau aneinander anschluessend
    (Ende Chunk N = Vortag von Beginn Chunk N+1)."""
    from datetime import timedelta

    from scripts.harvest_state_aid import build_year_chunks

    chunks = build_year_chunks(date(2020, 4, 15), date(2024, 8, 20))
    for i in range(len(chunks) - 1):
        end_curr = chunks[i][1]
        start_next = chunks[i + 1][0]
        assert start_next == end_curr + timedelta(days=1), (
            f"Luecke/Ueberlapp zwischen Chunk {i} und {i+1}: {end_curr} -> {start_next}"
        )


def test_build_year_chunks_first_starts_at_since_last_ends_at_until():
    """Erstes Chunk-Start == since, letztes Chunk-Ende == until."""
    from scripts.harvest_state_aid import build_year_chunks

    since = date(2018, 9, 17)
    until = date(2025, 2, 3)
    chunks = build_year_chunks(since, until)
    assert chunks[0][0] == since
    assert chunks[-1][1] == until


def test_build_year_chunks_year_count_matches_range():
    """Anzahl Chunks == until.year - since.year + 1."""
    from scripts.harvest_state_aid import build_year_chunks

    chunks = build_year_chunks(date(2014, 7, 1), date(2024, 3, 1))
    assert len(chunks) == 11  # 2014..2024 inklusive
