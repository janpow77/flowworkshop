"""
flowworkshop · scripts/profile_fuzzy.py

Latenz-Messung fuer ``fuzzy_match_company`` mit 5 typischen Workshop-Queries.
Gibt eine Markdown-Tabelle aus, die direkt in ``docs/fuzzy-performance.md``
oder ``docs/state-aid-security-audit.md`` uebernommen werden kann.

Ablauf:
    1. Cold run pro Query (Cache leer) → Latenz "kalt".
    2. Warm run pro Query (Cache gefuellt) → Latenz "warm".
    3. EXPLAIN (ANALYZE, BUFFERS) fuer den pg_trgm-Vorfilter.
    4. Optionaler Vergleich gegen die alte OR-ILIKE-Variante via ``--legacy``.

Aufruf:
    docker exec auditworkshop-backend python scripts/profile_fuzzy.py
    docker exec auditworkshop-backend python scripts/profile_fuzzy.py --runs 5
"""
from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
from typing import Callable

sys.path.insert(0, "/app")

from sqlalchemy import or_, text  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.state_aid import StateAidAward  # noqa: E402
from services.state_aid_service import (  # noqa: E402
    _escape_like,
    _smart_fuzzy_score,
    _smart_fuzzy_score_cached,
    fuzzy_match_company,
    normalize_company_name,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
)
log = logging.getLogger("profile_fuzzy")


# Workshop-typische Queries — decken Single-Token, Multi-Token, Behoerde,
# Universitaet und Stadt-Versorger ab.
QUERIES: list[tuple[str, str | None]] = [
    ("Fraunhofer", "DE"),
    ("Müller GmbH", "DE"),
    ("Siemens AG", "DE"),
    ("Justus-Liebig-Universität Gießen", "DE"),
    ("Energieversorgung Offenbach", "DE"),
]


def _measure(fn: Callable[[], int], runs: int = 3) -> tuple[float, float, int]:
    """Misst Latenz fuer ``runs`` Wiederholungen und gibt
    (median_ms, mean_ms, hit_count) zurueck."""
    durations: list[float] = []
    last_count = 0
    for _ in range(runs):
        t0 = time.perf_counter()
        last_count = fn()
        durations.append((time.perf_counter() - t0) * 1000)
    return statistics.median(durations), statistics.mean(durations), last_count


def _legacy_or_ilike_search(db, query: str, country_code: str | None) -> int:
    """Vergleichs-Implementation: das alte OR-ILIKE-Schema, ohne
    Trgm-Pre-Ranking, ohne cdist-Cutoff. Misst nur die SQL-Latenz."""
    q_norm = normalize_company_name(query)
    if not q_norm:
        return 0
    tokens = [t for t in q_norm.split() if len(t) >= 3]
    q = db.query(StateAidAward.id, StateAidAward.beneficiary_name_normalized)
    if country_code:
        q = q.filter(StateAidAward.country_code == country_code)
    if tokens:
        ors = [
            StateAidAward.beneficiary_name_normalized.ilike(
                f"%{_escape_like(t)}%", escape="\\",
            )
            for t in tokens
        ]
        q = q.filter(or_(*ors))
    return q.limit(2000).count()


def _explain_trgm(db, query: str, country_code: str | None) -> str:
    """EXPLAIN (ANALYZE, BUFFERS) fuer den pg_trgm-Vorfilter."""
    q_norm = normalize_company_name(query)
    sql = (
        "EXPLAIN (ANALYZE, BUFFERS) "
        "SELECT id, similarity(beneficiary_name_normalized::text, :q) AS sim "
        "FROM workshop_state_aid_awards "
        "WHERE beneficiary_name_normalized::text % :q "
    )
    params: dict = {"q": q_norm}
    if country_code:
        sql += "  AND country_code = :cc "
        params["cc"] = country_code
    sql += "ORDER BY sim DESC LIMIT 500"
    rows = db.execute(text(sql), params).fetchall()
    return "\n".join(r[0] for r in rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=5,
                   help="Wiederholungen pro Query (Default: 5).")
    p.add_argument("--explain", action="store_true",
                   help="Gibt EXPLAIN (ANALYZE, BUFFERS) fuer einen Sample aus.")
    p.add_argument("--legacy", action="store_true",
                   help="Vergleicht zusaetzlich gegen das alte OR-ILIKE-Schema.")
    args = p.parse_args()

    db = SessionLocal()
    try:
        # Cache leeren — fairer Cold-Run.
        _smart_fuzzy_score_cached.cache_clear()

        rows: list[tuple] = []
        for query, cc in QUERIES:
            # Cache pro Query leeren fuer "kalt"-Messung.
            _smart_fuzzy_score_cached.cache_clear()

            def cold_run(q=query, c=cc):
                return len(fuzzy_match_company(db, q, country_code=c, limit=20))

            cold_med, cold_mean, hits_cold = _measure(cold_run, runs=1)

            # Warm-Run: Cache schon gefuellt durch obigen Lauf — fuer den
            # Multi-Run-Median brauchen wir aber MEHRERE Aufrufe der Sequenz
            # query → fuzzy_match. Daher fuehren wir ``runs - 1`` weitere
            # Aufrufe aus, ohne den Cache zu leeren.
            def warm_run(q=query, c=cc):
                return len(fuzzy_match_company(db, q, country_code=c, limit=20))

            if args.runs > 1:
                warm_med, warm_mean, hits_warm = _measure(warm_run, runs=args.runs - 1)
            else:
                warm_med, warm_mean, hits_warm = cold_med, cold_mean, hits_cold

            legacy_med = legacy_mean = legacy_count = None
            if args.legacy:
                def legacy_run(q=query, c=cc):
                    return _legacy_or_ilike_search(db, q, c)
                legacy_med, legacy_mean, legacy_count = _measure(legacy_run, runs=args.runs)

            rows.append((
                query, cc, hits_cold, cold_med, warm_med,
                legacy_med, legacy_count,
            ))

        # Markdown-Tabelle ausgeben.
        print()
        print("# Fuzzy-Match Performance Profile")
        print()
        print(f"Runs pro Query: {args.runs} (kalt: 1, warm: {max(1, args.runs - 1)})")
        print(f"DB: {SessionLocal.kw['bind'].url if hasattr(SessionLocal, 'kw') else 'session'}")
        print()
        if args.legacy:
            print("| Query | Country | Hits | Cold (ms) | Warm (ms) | "
                  "Legacy SQL (ms) | Legacy Cands |")
            print("|-------|---------|------|-----------|-----------|"
                  "-----------------|--------------|")
            for q, cc, hits, cold, warm, legacy_med, legacy_count in rows:
                print(
                    f"| {q} | {cc or '—'} | {hits} | {cold:.1f} | {warm:.1f} | "
                    f"{legacy_med:.1f} | {legacy_count} |"
                )
        else:
            print("| Query | Country | Hits | Cold (ms) | Warm (ms) |")
            print("|-------|---------|------|-----------|-----------|")
            for q, cc, hits, cold, warm, _l1, _l2 in rows:
                print(
                    f"| {q} | {cc or '—'} | {hits} | {cold:.1f} | {warm:.1f} |"
                )

        cold_vals = [r[3] for r in rows]
        warm_vals = [r[4] for r in rows]
        print()
        print(f"Cold median: {statistics.median(cold_vals):.1f} ms  "
              f"(min={min(cold_vals):.1f}, max={max(cold_vals):.1f})")
        print(f"Warm median: {statistics.median(warm_vals):.1f} ms  "
              f"(min={min(warm_vals):.1f}, max={max(warm_vals):.1f})")

        cache_info = _smart_fuzzy_score_cached.cache_info()
        print()
        print(f"Smart-Score-Cache: hits={cache_info.hits}, misses={cache_info.misses}, "
              f"size={cache_info.currsize}/{cache_info.maxsize}")

        if args.explain:
            sample_q, sample_cc = QUERIES[0]
            plan = _explain_trgm(db, sample_q, sample_cc)
            print()
            print("## EXPLAIN (ANALYZE, BUFFERS) — pg_trgm-Vorfilter")
            print(f"Query: '{sample_q}' (country={sample_cc})")
            print()
            print("```")
            print(plan)
            print("```")

        # Sanity-Check: Smart-Score deterministisch (cached vs. uncached).
        check_q = "siemens"
        check_c = "siemens ag"
        s1, _ = _smart_fuzzy_score(check_q, check_c)
        s2, _ = _smart_fuzzy_score_cached(check_q, check_c)
        if abs(s1 - s2) > 1e-6:
            print(f"\nWARNUNG: Smart-Score uncached={s1} != cached={s2}")
            return 1
        print(f"\nDeterminismus-Check: smart_score('{check_q}', '{check_c}') = {s1:.2f} "
              f"(cached: {s2:.2f})  OK")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
