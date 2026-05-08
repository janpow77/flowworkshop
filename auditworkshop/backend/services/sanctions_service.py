"""
flowworkshop · services/sanctions_service.py

Lokale Fuzzy-Suche gegen mehrere internationale Sanktionslisten.

Datenquellen (alle aus OpenSanctions, targets.simple.csv):
- eu_fsf            EU Konsolidierte Finanzsanktionsliste (FSF)
- un_sc             UN Security Council Consolidated List
- us_ofac_sdn       OFAC SDN List (U.S. Treasury)
- gb_hmt_sanctions  UK OFSI Consolidated List
- ch_seco           SECO Schweizer Sanktionsliste

Pro Quelle wird ein eigener In-Memory-Index gefuehrt; die Suche aggregiert
ueber alle aktivierten Quellen und liefert Treffer mit `source_key` markiert.

Das Fuzzy-Pattern stammt aus flowinvoice
(app/services/document_reconciliation/matcher.py): Normalisierung der Vergleichs-
namen, anschliessend Token-Set-Ratio (rapidfuzz) — robust gegen Wort­reihenfolge,
Bindestriche, GmbH/Ltd-Suffixe und Transliterationen.

Backward-Compatibility:
- `FsfIndex` bleibt als Alias auf `SanctionsListIndex` erhalten.
- `get_index()` liefert weiterhin den `eu_fsf`-Index (Default).
- `FSF_CSV_PATH`, `FSF_DOWNLOAD_URL` bleiben Modul-Konstanten.
"""
from __future__ import annotations

import csv
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, TYPE_CHECKING

import httpx
from rapidfuzz import fuzz, process

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# ── Konfiguration ────────────────────────────────────────────────────────────

# Default-Pfade fuer die einzelnen Quellen. Per ENV pro Quelle ueberschreibbar:
#   FSF_CSV_PATH, UN_SC_CSV_PATH, OFAC_SDN_CSV_PATH, ...
# Die alten FSF_*-Variablen bleiben fuer Rueckwaerts­kompatibilitaet erhalten.

FSF_CSV_PATH = os.environ.get(
    "FSF_CSV_PATH",
    "/app/data/sanctions/eu_fsf_targets.csv",
)
FSF_DOWNLOAD_URL = os.environ.get(
    "FSF_DOWNLOAD_URL",
    "https://data.opensanctions.org/datasets/latest/eu_fsf/targets.simple.csv",
)

# Wortlisten, die im Vergleich nicht ueberbewertet werden sollen
_LEGAL_SUFFIXES = {
    "gmbh", "ag", "kg", "ohg", "se", "ug", "ev",
    "ltd", "llc", "inc", "corp", "co", "company", "limited",
    "sa", "sas", "sarl", "sl", "spa", "srl", "bv", "nv", "oy", "ab",
    "jsc", "ojsc", "pjsc", "ooo", "zao", "fzc", "fz", "lp", "plc",
}


# ── Datenmodelle ─────────────────────────────────────────────────────────────


@dataclass
class SanctionsSource:
    """Beschreibt eine Sanctions-Quelle (Metadaten + Pfade)."""
    key: str
    display_name: str
    issuer: str
    download_url: str
    csv_path: str
    license: str

    def __post_init__(self) -> None:
        # ENV-Override pro Quelle, falls explizit gesetzt
        # (z.B. UN_SC_CSV_PATH, US_OFAC_SDN_CSV_PATH, ...)
        env_key_path = f"{self.key.upper()}_CSV_PATH"
        env_key_url = f"{self.key.upper()}_DOWNLOAD_URL"
        self.csv_path = os.environ.get(env_key_path, self.csv_path)
        self.download_url = os.environ.get(env_key_url, self.download_url)


@dataclass
class FsfRecord:
    """Ein einzelner Eintrag aus einer Sanctions-CSV (vereinfachte Sicht).

    Name aus Legacy-Gruenden beibehalten; tatsaechlich generisch verwendbar
    fuer alle OpenSanctions targets.simple.csv-Quellen.
    """
    id: str
    schema: str           # "Person" | "Organization" | ...
    name: str
    aliases: list[str]
    birth_date: str
    countries: str
    addresses: str
    identifiers: str
    sanctions: str
    program_ids: str
    first_seen: str
    last_seen: str

    # vorberechnete Vergleichsformen (gefuellt beim Laden)
    name_norm: str = ""
    alias_norms: tuple[str, ...] = ()


@dataclass
class SanctionsHit:
    """Ergebnis eines Treffers."""
    id: str
    schema: str
    name: str
    matched_on: str          # Originalstring, gegen den der Score berechnet wurde
    matched_field: str       # "name" oder "alias"
    score: float             # 0..100
    confidence: str          # "exact" | "high" | "medium" | "low"
    aliases: list[str]
    birth_date: str
    countries: str
    addresses: str
    identifiers: str
    sanctions: str
    program_ids: str
    first_seen: str
    last_seen: str
    # Multi-Source-Felder — Default leer fuer Backward-Compat
    source_key: str = ""
    source_display_name: str = ""


# ── Default-Quellen ──────────────────────────────────────────────────────────


DEFAULT_SANCTIONS_SOURCES: list[SanctionsSource] = [
    SanctionsSource(
        key="eu_fsf",
        display_name="EU Konsolidierte Finanzsanktionsliste (FSF)",
        issuer="Europaeische Kommission",
        download_url="https://data.opensanctions.org/datasets/latest/eu_fsf/targets.simple.csv",
        csv_path="/app/data/sanctions/eu_fsf_targets.csv",
        license="CC BY 4.0",
    ),
    SanctionsSource(
        key="un_sc",
        display_name="UN Security Council Consolidated List",
        issuer="UN-Sicherheitsrat",
        # OpenSanctions-Key: `un_sc_sanctions` (Stand 2026-05).
        download_url="https://data.opensanctions.org/datasets/latest/un_sc_sanctions/targets.simple.csv",
        csv_path="/app/data/sanctions/un_sc_targets.csv",
        license="Public Domain",
    ),
    SanctionsSource(
        key="us_ofac_sdn",
        display_name="OFAC SDN List",
        issuer="U.S. Treasury — OFAC",
        download_url="https://data.opensanctions.org/datasets/latest/us_ofac_sdn/targets.simple.csv",
        csv_path="/app/data/sanctions/us_ofac_sdn_targets.csv",
        license="Public Domain",
    ),
    SanctionsSource(
        key="gb_hmt_sanctions",
        display_name="UK FCDO/OFSI Consolidated List",
        issuer="UK Foreign, Commonwealth & Development Office / HM Treasury OFSI",
        # OpenSanctions stellt den HMT/OFSI-Bestand unter `gb_fcdo_sanctions`
        # bereit (Stand 2026-05). Der Datensatz enthaelt sowohl die FCDO-
        # als auch die HMT-Listungen und ersetzt das frueher separate
        # `gb_hmt_sanctions`-Dataset.
        download_url="https://data.opensanctions.org/datasets/latest/gb_fcdo_sanctions/targets.simple.csv",
        csv_path="/app/data/sanctions/gb_hmt_sanctions_targets.csv",
        license="Crown Copyright (UK Open Government Licence)",
    ),
    SanctionsSource(
        key="ch_seco",
        display_name="SECO Schweizer Sanktionsliste",
        issuer="SECO Schweiz",
        # OpenSanctions-Key: `ch_seco_sanctions` (Stand 2026-05).
        download_url="https://data.opensanctions.org/datasets/latest/ch_seco_sanctions/targets.simple.csv",
        csv_path="/app/data/sanctions/ch_seco_targets.csv",
        license="Public Domain",
    ),
]


# ── Normalisierung ───────────────────────────────────────────────────────────


def normalize_name(text: str) -> str:
    """Vergleichsform fuer Namen: lowercase, ohne Akzente/Sonderzeichen,
    ohne Rechtsform­suffixe, kompakte Whitespaces.
    """
    if not text:
        return ""
    s = text.casefold()
    # Nicht-Wort-Zeichen durch Leerzeichen ersetzen
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    # Mehrfach-Whitespaces normalisieren
    tokens = [t for t in s.split() if t and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


def _classify(score: float) -> str:
    if score >= 97:
        return "exact"
    if score >= 90:
        return "high"
    if score >= 80:
        return "medium"
    return "low"


# ── Pure Helpers: CSV / DB → FsfRecord ──────────────────────────────────────


def _row_to_record(row: dict) -> "FsfRecord":
    """Wandelt eine CSV/DB-Zeile in einen `FsfRecord` (mit name_norm) um.

    Pure Helper — kein I/O. Aliases werden semikolongetrennt erwartet,
    Original-Strings unveraendert weitergereicht.
    """
    aliases_raw = row.get("aliases") or ""
    if isinstance(aliases_raw, list):
        aliases = [a for a in aliases_raw if a]
    else:
        aliases = [a.strip() for a in str(aliases_raw).split(";") if a.strip()]
    rec = FsfRecord(
        id=row.get("id", "") or "",
        schema=row.get("schema", "") or "",
        name=row.get("name", "") or "",
        aliases=aliases,
        birth_date=row.get("birth_date", "") or "",
        countries=row.get("countries", "") or "",
        addresses=row.get("addresses", "") or "",
        identifiers=row.get("identifiers", "") or "",
        sanctions=row.get("sanctions", "") or "",
        program_ids=row.get("program_ids", "") or "",
        first_seen=row.get("first_seen", "") or "",
        last_seen=row.get("last_seen", "") or "",
    )
    rec.name_norm = normalize_name(rec.name)
    rec.alias_norms = tuple(normalize_name(a) for a in rec.aliases)
    return rec


def _records_from_csv(csv_path: str) -> Iterable["FsfRecord"]:
    """Liest eine CSV und yieldet `FsfRecord`-Instanzen."""
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield _row_to_record(row)


def download_csv(source: "SanctionsSource") -> int:
    """Laedt die CSV einer Quelle von OpenSanctions und schreibt sie auf Platte.

    Liefert die Anzahl der geschriebenen Bytes. Wirft bei Netzwerk-/HTTP-
    Fehlern weiter (`httpx.HTTPError`).
    """
    os.makedirs(os.path.dirname(source.csv_path), exist_ok=True)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        resp = client.get(source.download_url)
        resp.raise_for_status()
        with open(source.csv_path, "wb") as fh:
            fh.write(resp.content)
        return len(resp.content)


# ── DB-Persistenz: CSV → DB Upsert + DB → In-Memory ──────────────────────────


def load_from_csv_to_db(
    db: "Session",
    source_key: str,
    csv_path: str,
    *,
    refresh_run_id: int | None = None,
    chunk_size: int = 1000,
) -> dict:
    """Liest eine OpenSanctions-CSV und upsertet die Eintraege nach
    ``workshop_sanctions_entries``.

    Verwendet ``ON CONFLICT (source_key, entry_id) DO UPDATE`` — bestehende
    Eintraege werden mit den neuen Werten aktualisiert, neue dazu eingefuegt.
    Original-Strings werden VERBATIM uebernommen; nur ``name_normalized``
    wird per ``normalize_name()`` befuellt.

    Args:
      db: aktive SQLAlchemy-Session (synchron).
      source_key: Quelle (z.B. ``"eu_fsf"``).
      csv_path: Pfad zur CSV (im Container ueblicherweise ``/app/data/sanctions/<key>_targets.csv``).
      refresh_run_id: Optional — wird auf jeden upsertten Eintrag geschrieben,
                      damit ueber ``SanctionsRefreshRun`` nachvollziehbar ist,
                      wann der Eintrag das letzte Mal beruehrt wurde.
      chunk_size: Anzahl Records pro Bulk-Upsert (Default 1000).

    Returns:
      Dict mit ``records_seen`` (CSV-Zeilen total), ``records_upserted``
      (alle Zeilen, die DB beruehrt haben — Insert+Update zusammen) und
      ``records_skipped`` (Zeilen ohne ``id``/``name``, ueberspruengen).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from models.sanctions_entries import SanctionsEntry

    if not os.path.exists(csv_path):
        log.warning(
            "load_from_csv_to_db: CSV fehlt (source=%s) — %s",
            source_key, csv_path,
        )
        return {
            "source_key": source_key,
            "records_seen": 0,
            "records_upserted": 0,
            "records_skipped": 0,
            "csv_path": csv_path,
        }

    seen = 0
    upserted = 0
    skipped = 0
    batch: list[dict] = []

    def _flush() -> int:
        if not batch:
            return 0
        stmt = pg_insert(SanctionsEntry).values(batch)
        update_cols = {
            col: getattr(stmt.excluded, col) for col in (
                "schema", "name", "name_normalized", "aliases",
                "birth_date", "countries", "addresses", "identifiers",
                "sanctions_program", "program_ids",
                "first_seen", "last_seen", "raw_payload",
                "refresh_run_id",
            )
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_key", "entry_id"],
            set_=update_cols,
        )
        result = db.execute(stmt)
        db.commit()
        return int(result.rowcount or 0)

    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            seen += 1
            entry_id = (row.get("id") or "").strip()
            name = row.get("name") or ""
            if not entry_id or not name:
                skipped += 1
                continue
            aliases_raw = row.get("aliases") or ""
            aliases_list = [a.strip() for a in aliases_raw.split(";") if a.strip()]
            batch.append({
                "source_key": source_key,
                "entry_id": entry_id,
                "schema": row.get("schema") or "",
                "name": name,
                "name_normalized": normalize_name(name),
                "aliases": aliases_list or None,
                "birth_date": (row.get("birth_date") or "") or None,
                "countries": (row.get("countries") or "") or None,
                "addresses": (row.get("addresses") or "") or None,
                "identifiers": (row.get("identifiers") or "") or None,
                "sanctions_program": (row.get("sanctions") or "") or None,
                "program_ids": (row.get("program_ids") or "") or None,
                "first_seen": (row.get("first_seen") or "") or None,
                "last_seen": (row.get("last_seen") or "") or None,
                "raw_payload": dict(row),
                "refresh_run_id": refresh_run_id,
            })
            if len(batch) >= chunk_size:
                upserted += _flush()
                batch.clear()

    if batch:
        upserted += _flush()
        batch.clear()

    log.info(
        "load_from_csv_to_db [%s]: seen=%d upserted=%d skipped=%d",
        source_key, seen, upserted, skipped,
    )
    return {
        "source_key": source_key,
        "records_seen": seen,
        "records_upserted": upserted,
        "records_skipped": skipped,
        "csv_path": csv_path,
    }


def load_index_from_db(
    db: "Session",
    source: "SanctionsSource",
) -> "SanctionsListIndex":
    """Baut einen `SanctionsListIndex` aus den DB-Eintraegen einer Quelle auf.

    Streamt alle Records einer ``source_key`` aus
    ``workshop_sanctions_entries`` und befuellt den In-Memory-Index. Die
    Aliase werden aus dem JSONB-Feld ``aliases`` rekonstruiert (Liste von
    Strings). Wenn die DB-Tabelle leer ist, ist der Index ebenfalls leer
    — der Aufrufer kann dann auf den CSV-Path zurueckfallen.
    """
    from models.sanctions_entries import SanctionsEntry

    idx = SanctionsListIndex(source)
    rows = (
        db.query(SanctionsEntry)
        .filter(SanctionsEntry.source_key == source.key)
        .order_by(SanctionsEntry.id.asc())
        .all()
    )
    records: list[FsfRecord] = []
    for r in rows:
        # JSONB → Python-Liste
        aliases = list(r.aliases) if r.aliases else []
        rec = FsfRecord(
            id=r.entry_id or "",
            schema=r.schema or "",
            name=r.name or "",
            aliases=aliases,
            birth_date=r.birth_date or "",
            countries=r.countries or "",
            addresses=r.addresses or "",
            identifiers=r.identifiers or "",
            sanctions=r.sanctions_program or "",
            program_ids=r.program_ids or "",
            first_seen=r.first_seen or "",
            last_seen=r.last_seen or "",
        )
        rec.name_norm = r.name_normalized or normalize_name(rec.name)
        rec.alias_norms = tuple(normalize_name(a) for a in rec.aliases)
        records.append(rec)
    idx.load_from_records(records)
    return idx


# ── Index pro Quelle ─────────────────────────────────────────────────────────


class SanctionsListIndex:
    """In-Memory-Index ueber eine einzelne Sanctions-CSV.

    Struktur: zwei parallele Listen `_compare_strings` und `_record_refs`,
    sodass `rapidfuzz.process.extract` direkt darueber suchen kann.

    Pro Index wird die Quelle (`SanctionsSource`) gehalten; Treffer aus
    `search()` enthalten den `source_key` automatisch.
    """

    def __init__(
        self,
        source: SanctionsSource | None = None,
    ) -> None:
        self._lock = threading.Lock()
        # Default-Source = EU FSF (Backward-Compat: alter FsfIndex())
        if source is None:
            source = DEFAULT_SANCTIONS_SOURCES[0]
        self.source = source
        self._records: list[FsfRecord] = []
        self._compare_strings: list[str] = []      # normalisierte Namen + Aliase
        self._compare_owner: list[int] = []        # Index in _records
        self._compare_field: list[str] = []        # "name" | "alias"
        self._compare_original: list[str] = []     # Original-String pro Vergleich
        self._loaded_at: datetime | None = None
        self._source_mtime: float | None = None
        self._source_size: int | None = None

    # ── Laden ────────────────────────────────────────────────────────────

    def load(self, csv_path: str | None = None) -> None:
        """Liest die CSV und baut den In-Memory-Index neu auf.

        Backward-Compat-Pfad fuer Tests + Erststart, wenn die DB-Tabelle leer
        ist und der Hot-Path-Code (DB → Index) noch keine Daten hat.
        """
        if csv_path is None:
            csv_path = self.source.csv_path
        if not os.path.exists(csv_path):
            log.warning(
                "Sanctions-CSV nicht gefunden (source=%s): %s",
                self.source.key, csv_path,
            )
            return

        records = list(_records_from_csv(csv_path))
        self._set_records(records)

        # CSV-Metadaten aufnehmen — fuer /sources-Endpoint
        with self._lock:
            try:
                stat = os.stat(csv_path)
                self._source_mtime = stat.st_mtime
                self._source_size = stat.st_size
            except OSError:
                self._source_mtime = None
                self._source_size = None

        log.info(
            "Sanctions-Index geladen [%s]: %d Eintraege, %d Vergleichsstrings (Quelle: CSV)",
            self.source.key, len(records), len(self._compare_strings),
        )

    def load_from_records(self, records: list["FsfRecord"]) -> None:
        """Setzt den In-Memory-Index aus einer fertigen `FsfRecord`-Liste.

        Wird vom DB → Index-Rebuild verwendet (siehe ``load_index_from_db``).
        Erwartet, dass `name_norm` und `alias_norms` bereits gesetzt sind.
        """
        self._set_records(records)
        log.info(
            "Sanctions-Index geladen [%s]: %d Eintraege, %d Vergleichsstrings (Quelle: DB)",
            self.source.key, len(records), len(self._compare_strings),
        )

    def _set_records(self, records: list["FsfRecord"]) -> None:
        """Internes Helfer: nimmt fertige Records, baut Vergleichsindizes auf
        und tauscht den Inhalt unter Lock atomar aus.
        """
        compare_strings: list[str] = []
        compare_owner: list[int] = []
        compare_field: list[str] = []
        compare_original: list[str] = []

        for idx, rec in enumerate(records):
            if rec.name_norm:
                compare_strings.append(rec.name_norm)
                compare_owner.append(idx)
                compare_field.append("name")
                compare_original.append(rec.name)
            for alias_orig, alias_norm in zip(rec.aliases, rec.alias_norms):
                if alias_norm and alias_norm != rec.name_norm:
                    compare_strings.append(alias_norm)
                    compare_owner.append(idx)
                    compare_field.append("alias")
                    compare_original.append(alias_orig)

        with self._lock:
            self._records = list(records)
            self._compare_strings = compare_strings
            self._compare_owner = compare_owner
            self._compare_field = compare_field
            self._compare_original = compare_original
            self._loaded_at = datetime.now(timezone.utc)

    # ── Refresh (Download) ───────────────────────────────────────────────

    def refresh_from_source(self) -> dict:
        """Legacy CSV-only Refresh.

        Phase 6c: Wenn der `MultiSanctionsService` mit DB-Backing genutzt wird,
        sollte stattdessen ``MultiSanctionsService.refresh_source(key, db=...)``
        aufgerufen werden — dort laeuft Download → DB-Upsert → Index-Rebuild.
        """
        download_csv(self.source)
        self.load(self.source.csv_path)
        return self.stats()

    # ── Stats ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            persons = sum(1 for r in self._records if r.schema == "Person")
            orgs = sum(1 for r in self._records if r.schema == "Organization")
            return {
                "source_key": self.source.key,
                "source_display_name": self.source.display_name,
                "issuer": self.source.issuer,
                "license": self.source.license,
                "total_entries": len(self._records),
                "persons": persons,
                "organizations": orgs,
                "other": len(self._records) - persons - orgs,
                "compare_strings": len(self._compare_strings),
                "loaded": bool(self._records),
                "loaded_at": self._loaded_at.isoformat() if self._loaded_at else None,
                "source_size_bytes": self._source_size,
                "source_mtime": (
                    datetime.fromtimestamp(self._source_mtime, timezone.utc).isoformat()
                    if self._source_mtime
                    else None
                ),
                "csv_path": self.source.csv_path,
                "download_url": self.source.download_url,
            }

    # ── Suche ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        limit: int = 15,
        min_score: float = 65.0,
        schema: str | None = None,
    ) -> list[SanctionsHit]:
        """Fuzzy-Suche ueber Namen und Aliase einer einzelnen Quelle.

        Algorithmus:
        - Normalisierung der Query und aller Vergleichsstrings (Casefold,
          Sonderzeichen weg, Rechtsform-Suffixe entfernt).
        - rapidfuzz.process.extract mit token_set_ratio:
          * tokenisiert beide Strings
          * vergleicht Mengenbezuege (Reihenfolge irrelevant)
          * ignoriert duplizierte Tokens
        - Pro betroffenem Datensatz wird der hoechste Score behalten.
        - Klassifikation in exact/high/medium/low fuer die Anzeige.
        - Treffer enthalten `source_key` und `source_display_name` der Quelle.
        """
        q_norm = normalize_name(query)
        if not q_norm:
            return []

        with self._lock:
            choices = list(self._compare_strings)
            owners = list(self._compare_owner)
            fields = list(self._compare_field)
            originals = list(self._compare_original)
            records = list(self._records)

        if not choices:
            return []

        # rapidfuzz: alle Kandidaten ueber Score >= min_score holen
        # limit hier hoch ansetzen, weil ein Datensatz mehrere Vergleichs-
        # strings (Name + N Aliase) liefern kann.
        raw_hits = process.extract(
            q_norm,
            choices,
            scorer=fuzz.token_set_ratio,
            limit=limit * 8,
            score_cutoff=min_score,
        )

        # Pro Datensatz nur den besten Treffer behalten
        best_per_record: dict[int, tuple[float, int, int]] = {}
        for choice, score, idx in raw_hits:
            owner_idx = owners[idx]
            current = best_per_record.get(owner_idx)
            if current is None or score > current[0]:
                best_per_record[owner_idx] = (score, idx, idx)

        results: list[SanctionsHit] = []
        for owner_idx, (score, choice_idx, _) in best_per_record.items():
            rec = records[owner_idx]
            if schema and rec.schema != schema:
                continue
            results.append(
                SanctionsHit(
                    id=rec.id,
                    schema=rec.schema,
                    name=rec.name,
                    matched_on=originals[choice_idx],
                    matched_field=fields[choice_idx],
                    score=round(float(score), 1),
                    confidence=_classify(score),
                    aliases=rec.aliases[:8],  # nicht alle 50+ rausgeben
                    birth_date=rec.birth_date,
                    countries=rec.countries,
                    addresses=rec.addresses,
                    identifiers=rec.identifiers,
                    sanctions=rec.sanctions,
                    program_ids=rec.program_ids,
                    first_seen=rec.first_seen,
                    last_seen=rec.last_seen,
                    source_key=self.source.key,
                    source_display_name=self.source.display_name,
                )
            )

        results.sort(key=lambda h: h.score, reverse=True)
        return results[:limit]

    # ── Status ───────────────────────────────────────────────────────────

    def is_loaded(self) -> bool:
        with self._lock:
            return bool(self._records)


# ── Backward-Compat Alias ────────────────────────────────────────────────────

# `FsfIndex` ist der historische Name aus Phase 1. Bleibt als Alias auf
# `SanctionsListIndex` erhalten, damit aelterer Code (Tests, Downstream-Tools)
# weiter funktioniert. Neue Aufrufer sollten `SanctionsListIndex` nutzen.
FsfIndex = SanctionsListIndex


# ── Multi-Source-Service ─────────────────────────────────────────────────────


class MultiSanctionsService:
    """Container fuer mehrere `SanctionsListIndex`-Instanzen.

    Verwaltet alle aktivierten Sanctions-Quellen und bietet aggregierte
    Suche/Stats/Refresh ueber alle Quellen hinweg. Pro Quelle wird ein
    eigener In-Memory-Index gehalten.
    """

    def __init__(
        self,
        sources: list[SanctionsSource] | None = None,
        *,
        use_db: bool = False,
    ) -> None:
        """
        Args:
          sources: explizite Quellen-Liste; Default = alle 5 OpenSanctions-Quellen.
          use_db: wenn ``True``, laedt ``load_all()`` aus der DB-Tabelle und
                  ``refresh_*()`` schreibt CSV → DB → Index. Default ``False``,
                  damit Tests ohne DB funktionieren — der Workshop-Singleton
                  schaltet das per ``get_multi_service()`` auf ``True``.
        """
        self._lock = threading.Lock()
        if sources is None:
            sources = list(DEFAULT_SANCTIONS_SOURCES)
        self.sources: list[SanctionsSource] = sources
        self.indices: dict[str, SanctionsListIndex] = {
            s.key: SanctionsListIndex(s) for s in sources
        }
        self._use_db: bool = use_db

    # ── Initial-Load ─────────────────────────────────────────────────────

    def load_all(self, *, use_db: bool | None = None) -> None:
        """Laedt alle aktivierten Sanctions-Indizes in den Speicher.

        Phase 6c — DB ist Source-of-Truth:
        1. Pro Source wird zuerst versucht, den Index aus der DB-Tabelle
           ``workshop_sanctions_entries`` aufzubauen (kein CSV-IO im Hot-Path).
        2. Wenn die DB-Tabelle leer ist (Erststart, frisch migriert) und die
           CSV vorliegt, wird die CSV in die DB upsertet UND der Index aus den
           CSV-Records aufgebaut. Damit ist der naechste Start DB-only.
        3. Wenn weder DB noch CSV vorliegen, bleibt der Index leer
           (``loaded=False`` im /sources-Endpoint) — die fehlende Quelle wird
           ueber den Lifespan-Background-Refresh nachgeholt.

        Args:
          use_db: Wenn ``True``, wird der DB-Pfad genutzt. Default = der beim
                  Konstruktor gesetzte Wert (``self._use_db``). ``False``
                  erzwingt CSV-only fuer Tests.
        """
        if use_db is None:
            use_db = self._use_db
        if not use_db:
            for key, idx in self.indices.items():
                try:
                    idx.load()
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "Sanctions-Index Load (CSV) fuer %s fehlgeschlagen: %s",
                        key, exc,
                    )
            return

        # DB-Pfad — lazy import, damit Test-Pfade ohne DB weiter funktionieren.
        try:
            from database import SessionLocal
        except Exception:  # noqa: BLE001
            log.warning(
                "Sanctions-Index Load: DATABASE nicht verfuegbar, falle auf CSV-only zurueck.",
            )
            self.load_all(use_db=False)
            return

        db = SessionLocal()
        try:
            for source in self.sources:
                try:
                    new_idx = load_index_from_db(db, source)
                    if new_idx.is_loaded():
                        # In-Memory-Slot ueberschreiben; bestehende Referenzen
                        # auf `self.indices[key]` werden ggf. invalidiert, aber
                        # der Service ist die einzige Stelle, die den Index
                        # weiterreicht (get_index() liefert frisch).
                        self.indices[source.key] = new_idx
                        continue
                except Exception:
                    log.exception(
                        "Sanctions-Index Load (DB) fuer %s fehlgeschlagen",
                        source.key,
                    )

                # DB leer fuer diese Quelle → CSV-Fallback + Upsert in DB
                if os.path.exists(source.csv_path):
                    log.info(
                        "Sanctions: DB leer fuer source=%s — upserte aus CSV %s",
                        source.key, source.csv_path,
                    )
                    try:
                        load_from_csv_to_db(db, source.key, source.csv_path)
                        # Index aus DB neu bauen, damit bestaetigt ist, dass
                        # der DB-Pfad funktioniert; der naechste Start ist
                        # damit reiner DB-Read.
                        new_idx = load_index_from_db(db, source)
                        if new_idx.is_loaded():
                            self.indices[source.key] = new_idx
                            continue
                    except Exception:
                        log.exception(
                            "Sanctions: CSV-Erst-Upsert fuer %s fehlgeschlagen, falle auf In-Memory-CSV zurueck.",
                            source.key,
                        )
                    # Fallback auf reine In-Memory-CSV-Last
                    try:
                        self.indices[source.key].load(source.csv_path)
                    except Exception as exc:  # noqa: BLE001
                        log.warning(
                            "Sanctions-Index In-Memory-Load fuer %s fehlgeschlagen: %s",
                            source.key, exc,
                        )
                else:
                    log.info(
                        "Sanctions: keine DB-Daten + keine CSV fuer source=%s — "
                        "wird ueber Background-Refresh nachgezogen.",
                        source.key,
                    )
        finally:
            db.close()

    # ── Refresh ──────────────────────────────────────────────────────────

    def refresh_source(self, key: str, *, refresh_run_id: int | None = None) -> dict:
        """Refresht eine einzelne Quelle: CSV download → DB upsert → Index-Rebuild.

        Phase 6c — die DB ist Source-of-Truth, der In-Memory-Index wird aus
        ihr gefuellt. Der ``refresh_run_id`` (FK auf ``SanctionsRefreshRun``)
        wird beim Upsert auf jeden beruehrten Eintrag gesetzt.

        Backward-Compat: Wenn keine DB verfuegbar ist (Tests), wird der
        klassische Pfad (Download → CSV → In-Memory) genommen.
        """
        source = next((s for s in self.sources if s.key == key), None)
        idx = self.indices.get(key)
        if source is None or idx is None:
            raise KeyError(f"Unbekannte Sanctions-Source: {key}")

        # CSV-only-Pfad fuer Tests (ohne DB) bleibt erhalten.
        if not self._use_db:
            try:
                stats = idx.refresh_from_source()
                return {"source_key": key, "status": "success", "stats": stats}
            except Exception as exc:  # noqa: BLE001
                log.exception("Sanctions-Refresh (CSV-only) fuer %s fehlgeschlagen", key)
                return {"source_key": key, "status": "failed", "error": str(exc)[:500]}

        try:
            from database import SessionLocal
        except Exception:  # noqa: BLE001
            try:
                stats = idx.refresh_from_source()
                return {"source_key": key, "status": "success", "stats": stats}
            except Exception as exc:  # noqa: BLE001
                log.exception("Sanctions-Refresh (CSV-only Fallback) fuer %s fehlgeschlagen", key)
                return {"source_key": key, "status": "failed", "error": str(exc)[:500]}

        db = SessionLocal()
        try:
            # 1. Download
            try:
                bytes_written = download_csv(source)
            except Exception as exc:  # noqa: BLE001
                log.exception("Sanctions-Refresh Download fuer %s fehlgeschlagen", key)
                return {"source_key": key, "status": "failed", "error": str(exc)[:500]}

            # 2. CSV → DB
            try:
                upsert_summary = load_from_csv_to_db(
                    db, key, source.csv_path,
                    refresh_run_id=refresh_run_id,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("Sanctions-Refresh DB-Upsert fuer %s fehlgeschlagen", key)
                return {"source_key": key, "status": "failed", "error": str(exc)[:500]}

            # 3. DB → In-Memory-Index
            try:
                new_idx = load_index_from_db(db, source)
                # CSV-Mtime in den frischen Index uebernehmen, damit /sources
                # den File-Stand sieht (bevorzugt vom Datei-stat).
                try:
                    stat = os.stat(source.csv_path)
                    with new_idx._lock:  # noqa: SLF001
                        new_idx._source_mtime = stat.st_mtime  # noqa: SLF001
                        new_idx._source_size = stat.st_size  # noqa: SLF001
                except OSError:
                    pass
                self.indices[key] = new_idx
            except Exception as exc:  # noqa: BLE001
                log.exception("Sanctions-Refresh Index-Rebuild fuer %s fehlgeschlagen", key)
                return {"source_key": key, "status": "failed", "error": str(exc)[:500]}

            stats = self.indices[key].stats()
            stats["bytes_written"] = bytes_written
            stats["records_seen"] = upsert_summary.get("records_seen")
            stats["records_upserted"] = upsert_summary.get("records_upserted")
            stats["records_skipped_csv"] = upsert_summary.get("records_skipped")
            return {"source_key": key, "status": "success", "stats": stats}
        finally:
            db.close()

    def refresh_all(self, *, refresh_run_id: int | None = None) -> dict:
        """Refresht alle aktivierten Quellen sequenziell.

        Liefert ein Dict mit Pro-Source-Subreport und Gesamtstatus
        (success | partial | failed). Der ``refresh_run_id`` wird an alle
        Sources weitergereicht — damit teilen sich die SanctionsEntry-Rows
        des Laufs denselben FK.
        """
        per_source: list[dict] = []
        ok = 0
        failed = 0
        for source in self.sources:
            result = self.refresh_source(source.key, refresh_run_id=refresh_run_id)
            per_source.append(result)
            if result["status"] == "success":
                ok += 1
            else:
                failed += 1

        if failed == 0:
            status = "success"
        elif ok == 0:
            status = "failed"
        else:
            status = "partial"

        return {
            "status": status,
            "sources_total": len(per_source),
            "sources_ok": ok,
            "sources_failed": failed,
            "per_source": per_source,
        }

    # ── Suche ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        limit: int = 15,
        min_score: float = 65.0,
        schema: str | None = None,
        sources: list[str] | None = None,
    ) -> list[SanctionsHit]:
        """Aggregiert die Treffer aus allen aktivierten (oder gefilterten) Quellen.

        Args:
          sources: Optionaler Filter auf einzelne Source-Keys (z.B.
                   `["eu_fsf", "un_sc"]`). None = alle aktivierten Quellen.

        Pro Quelle wird `limit*2` geholt; danach global nach Score sortiert
        und auf `limit` zugeschnitten.
        """
        active_keys: list[str]
        if sources:
            active_keys = [k for k in sources if k in self.indices]
        else:
            active_keys = list(self.indices.keys())

        all_hits: list[SanctionsHit] = []
        for key in active_keys:
            idx = self.indices.get(key)
            if not idx or not idx.is_loaded():
                continue
            try:
                # pro Quelle bewusst grosszuegiger holen, damit die globale
                # Top-Liste nicht durch lokale Limits abgeschnitten wird
                hits = idx.search(
                    query,
                    limit=max(limit, 5) * 2,
                    min_score=min_score,
                    schema=schema,
                )
                all_hits.extend(hits)
            except Exception:
                log.exception("Sanctions-Search fuer %s fehlgeschlagen", key)

        all_hits.sort(key=lambda h: h.score, reverse=True)
        return all_hits[:limit]

    # ── Stats ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Aggregierte Stats inkl. Per-Source-Breakdown."""
        per_source: list[dict] = []
        total = 0
        persons = 0
        orgs = 0
        loaded_count = 0
        for source in self.sources:
            idx = self.indices.get(source.key)
            stats = idx.stats() if idx else {}
            per_source.append(stats)
            total += int(stats.get("total_entries") or 0)
            persons += int(stats.get("persons") or 0)
            orgs += int(stats.get("organizations") or 0)
            if stats.get("loaded"):
                loaded_count += 1

        return {
            "sources_total": len(self.sources),
            "sources_loaded": loaded_count,
            "total_entries": total,
            "persons": persons,
            "organizations": orgs,
            "per_source": per_source,
        }

    # ── Status ───────────────────────────────────────────────────────────

    def is_any_loaded(self) -> bool:
        return any(idx.is_loaded() for idx in self.indices.values())

    def get_index(self, key: str) -> SanctionsListIndex | None:
        return self.indices.get(key)

    def has_missing_csvs(self) -> bool:
        """True, wenn mindestens eine CSV-Datei fehlt — Trigger fuer Auto-Refresh."""
        return any(
            not os.path.exists(s.csv_path)
            for s in self.sources
        )

    def missing_source_keys(self) -> list[str]:
        return [s.key for s in self.sources if not os.path.exists(s.csv_path)]


# ── Singletons ───────────────────────────────────────────────────────────────

_index: SanctionsListIndex | None = None        # Backward-Compat: nur eu_fsf
_multi_service: MultiSanctionsService | None = None
_singleton_lock = threading.Lock()


def get_index() -> SanctionsListIndex:
    """Backward-Compat: liefert den `eu_fsf`-Index.

    Bestandscode (Tests, FlowInvoice, audit_designer) ruft `get_index()` ohne
    Parameter — fuer den ist eu_fsf der Default. Neue Aufrufer sollten
    stattdessen `get_multi_service()` verwenden.

    Single Source of Truth: wir greifen IMMER auf den `eu_fsf`-Index aus dem
    `MultiSanctionsService` zu (auch wenn dieser noch nicht existiert: lazy
    Initialisierung). Damit teilen `get_index()` und `get_multi_service()`
    immer denselben In-Memory-Index — kein doppeltes Laden.
    """
    global _index
    # MultiService ueber den Lock seiner eigenen Funktion holen, damit kein
    # Deadlock entsteht (get_multi_service nutzt denselben Lock).
    svc = get_multi_service()
    with _singleton_lock:
        idx = svc.get_index("eu_fsf")
        if idx is None:
            # Sollte nie passieren (eu_fsf ist immer in DEFAULT_SANCTIONS_SOURCES),
            # aber fuer den Fall: Fallback auf Legacy-Pfad.
            if _index is None:
                _index = SanctionsListIndex(DEFAULT_SANCTIONS_SOURCES[0])
                _index.load(FSF_CSV_PATH)
            return _index
        _index = idx
        if not _index.is_loaded():
            _index.load(FSF_CSV_PATH)
    return _index


def get_multi_service() -> MultiSanctionsService:
    """Singleton der Multi-Source-Sanctions.

    Phase 6c: Der Singleton wird mit ``use_db=True`` initialisiert — der
    Hot-Path liest aus ``workshop_sanctions_entries`` und schreibt
    Refreshes ueber CSV → DB → Index. Tests koennen weiterhin eigene
    `MultiSanctionsService(...)`-Instanzen mit Default ``use_db=False``
    bauen und sind damit DB-frei.
    """
    global _multi_service, _index
    with _singleton_lock:
        if _multi_service is None:
            _multi_service = MultiSanctionsService(use_db=True)
            # eu_fsf-Index aus dem Multi-Service auch als Legacy-Singleton
            # anbieten, damit `get_index()` und `get_multi_service()` denselben
            # Speicher teilen.
            _index = _multi_service.get_index("eu_fsf")
    return _multi_service


def warmup() -> None:
    """Wird beim Lifespan-Startup aufgerufen.

    Laedt alle vorhandenen CSVs in den Speicher. Fehlende Dateien werden
    nicht heruntergeladen — das laeuft separat als Background-Task im
    Lifespan (siehe `main.py`).
    """
    try:
        svc = get_multi_service()
        svc.load_all()
        # Legacy-Singleton aktualisieren
        global _index
        with _singleton_lock:
            _index = svc.get_index("eu_fsf")
        log.info("Sanctions-Multi-Service Warmup: %s", {
            "sources_total": len(svc.sources),
            "sources_loaded": sum(1 for i in svc.indices.values() if i.is_loaded()),
            "total_entries": sum(
                len(i._records) for i in svc.indices.values()  # noqa: SLF001
            ),
        })
    except Exception as e:  # noqa: BLE001
        log.warning("Sanctions-Multi-Service Warmup fehlgeschlagen: %s", e)


# ── Methoden-Erlaeuterung (statisch, fuer Frontend-Card) ─────────────────────


def method_explanation() -> dict:
    """Beschreibt das Such-Verfahren für die Frontend-Card."""
    return {
        "title": "Wie funktioniert die Suche?",
        "summary": (
            "Die Eingabe wird mit jedem Namen und Aliase aller aktivierten "
            "Sanktionslisten verglichen. Beide Seiten werden vorher normalisiert "
            "(Kleinschreibung, Akzente und Sonderzeichen entfernt, Rechtsform­"
            "suffixe wie GmbH oder Ltd ignoriert). Anschliessend berechnet "
            "rapidfuzz mit dem Token-Set-Ratio einen Aehnlichkeitswert von 0 bis 100. "
            "Treffer werden quellenuebergreifend aggregiert und mit Quelle markiert."
        ),
        "steps": [
            {
                "title": "1. Normalisierung",
                "text": (
                    "Eingabe und Listenname werden in eine vergleichbare Form gebracht: "
                    "casefold, Diakritika weg, Bindestriche und Punkte als Trennzeichen, "
                    "Rechtsformsuffixe (GmbH, AG, Ltd, OOO …) entfernt. Damit matcht "
                    "‚Mueller-Schmidt GmbH‘ auch auf ‚MUELLER SCHMIDT‘."
                ),
            },
            {
                "title": "2. Token-Set-Ratio",
                "text": (
                    "Die normalisierten Strings werden in Tokens zerlegt. Verglichen wird "
                    "die Mengenschnittmenge — Reihenfolge spielt keine Rolle, doppelte "
                    "Tokens werden ignoriert. ‚Anatoly Petrov Sergeev‘ trifft so auf "
                    "‚Sergeev Anatoly‘ mit hoher Aehnlichkeit."
                ),
            },
            {
                "title": "3. Best-Match pro Eintrag",
                "text": (
                    "Pro Datensatz werden Hauptname und alle Aliase einzeln verglichen. "
                    "Behalten wird der hoechste Score — so geht ein Treffer in einer "
                    "russischen Schreibung nicht verloren, nur weil der lateinische Name "
                    "schwaecher matcht."
                ),
            },
            {
                "title": "4. Multi-Source-Aggregation",
                "text": (
                    "Die Suche laeuft pro Quelle (EU FSF, UN, OFAC, OFSI, SECO) separat "
                    "und aggregiert anschliessend nach Score. Treffer werden mit der "
                    "Quelle markiert, sodass der Pruefer sehen kann, welche Liste "
                    "gelistet hat. Eine Person kann durchaus auf mehreren Listen "
                    "stehen — alle Treffer werden ausgegeben."
                ),
            },
            {
                "title": "5. Konfidenz-Klassen",
                "text": (
                    "exact (>=97): Schreibweise praktisch identisch · "
                    "high (>=90): klare Uebereinstimmung, lohnt sich Abklaerung · "
                    "medium (>=80): Hinweis, manuell pruefen · "
                    "low (>=65): nur Verdacht, oft Namensgleichheit ohne Bezug."
                ),
            },
        ],
        "library": "rapidfuzz · fuzz.token_set_ratio",
        "source_pattern": "auditworkshop/backend/services/sanctions_service.py",
        "data_sources": [
            {
                "key": s.key,
                "name": s.display_name,
                "issuer": s.issuer,
                "url": s.download_url,
                "license": s.license,
                "update_frequency": "taeglich (OpenSanctions-Crawl)",
            }
            for s in DEFAULT_SANCTIONS_SOURCES
        ],
        "data_source": {
            # Backward-Compat: Frontend-Card erwartet ggf. das alte Feld
            "name": "OpenSanctions — eu_fsf (targets.simple.csv)",
            "url": FSF_DOWNLOAD_URL,
            "license": "CC BY 4.0",
            "update_frequency": "taeglich (OpenSanctions-Crawl)",
        },
        "limits": [
            "Pruefung erfolgt gegen die EU-Konsolidierte Finanzsanktionsliste (FSF), "
            "UN-Sicherheitsrats-Liste, OFAC SDN, UK OFSI und SECO. BAFA und "
            "Bundesbank-Hinweise sind hierueber nicht abgedeckt — dafuer separate "
            "Recherche ueber die jeweiligen offiziellen Tools (siehe Karten unten).",
            "Namensgleichheit ist haeufig — vor allem bei Russisch-Transliterationen. "
            "Geburtsdatum und Land im Treffer immer mit dem Vorgang abgleichen.",
        ],
    }
