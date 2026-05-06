"""
flowworkshop · services/sanctions_service.py

Lokale Fuzzy-Suche gegen die EU Konsolidierte Finanzsanktionsliste (FSF).

Datenquelle: OpenSanctions (eu_fsf, targets.simple.csv) — täglich aktualisiert.
Die CSV wird im Container unter /app/data/sanctions/eu_fsf_targets.csv vorgehalten
und beim Start einmal in den Speicher gelesen.

Das Fuzzy-Pattern stammt aus flowinvoice
(app/services/document_reconciliation/matcher.py): Normalisierung der Vergleichs-
namen, anschliessend Token-Set-Ratio (rapidfuzz) — robust gegen Wort­reihenfolge,
Bindestriche, GmbH/Ltd-Suffixe und Transliterationen.
"""
from __future__ import annotations

import csv
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import httpx
from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)

# ── Konfiguration ────────────────────────────────────────────────────────────

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
class FsfRecord:
    """Ein einzelner Eintrag aus der FSF-CSV (vereinfachte Sicht)."""
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


# ── Index ────────────────────────────────────────────────────────────────────


class FsfIndex:
    """In-Memory-Index ueber die FSF-CSV.

    Struktur: zwei parallele Listen `_compare_strings` und `_record_refs`,
    sodass `rapidfuzz.process.extract` direkt darueber suchen kann.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[FsfRecord] = []
        self._compare_strings: list[str] = []      # normalisierte Namen + Aliase
        self._compare_owner: list[int] = []        # Index in _records
        self._compare_field: list[str] = []        # "name" | "alias"
        self._compare_original: list[str] = []     # Original-String pro Vergleich
        self._loaded_at: datetime | None = None
        self._source_mtime: float | None = None
        self._source_size: int | None = None

    # ── Laden ────────────────────────────────────────────────────────────

    def load(self, csv_path: str = FSF_CSV_PATH) -> None:
        """Liest die CSV und baut den In-Memory-Index neu auf."""
        if not os.path.exists(csv_path):
            log.warning("FSF-CSV nicht gefunden: %s", csv_path)
            return

        records: list[FsfRecord] = []
        compare_strings: list[str] = []
        compare_owner: list[int] = []
        compare_field: list[str] = []
        compare_original: list[str] = []

        with open(csv_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                aliases_raw = row.get("aliases") or ""
                aliases = [a.strip() for a in aliases_raw.split(";") if a.strip()]
                rec = FsfRecord(
                    id=row.get("id", ""),
                    schema=row.get("schema", ""),
                    name=row.get("name", ""),
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

                idx = len(records)
                records.append(rec)

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
            self._records = records
            self._compare_strings = compare_strings
            self._compare_owner = compare_owner
            self._compare_field = compare_field
            self._compare_original = compare_original
            self._loaded_at = datetime.now(timezone.utc)
            try:
                stat = os.stat(csv_path)
                self._source_mtime = stat.st_mtime
                self._source_size = stat.st_size
            except OSError:
                self._source_mtime = None
                self._source_size = None

        log.info(
            "FSF-Index geladen: %d Eintraege, %d Vergleichsstrings",
            len(records),
            len(compare_strings),
        )

    # ── Refresh (Download) ───────────────────────────────────────────────

    def refresh_from_source(self) -> dict:
        """Laedt die CSV neu von OpenSanctions und baut den Index auf."""
        os.makedirs(os.path.dirname(FSF_CSV_PATH), exist_ok=True)
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(FSF_DOWNLOAD_URL)
            resp.raise_for_status()
            with open(FSF_CSV_PATH, "wb") as fh:
                fh.write(resp.content)
        self.load(FSF_CSV_PATH)
        return self.stats()

    # ── Stats ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            persons = sum(1 for r in self._records if r.schema == "Person")
            orgs = sum(1 for r in self._records if r.schema == "Organization")
            return {
                "total_entries": len(self._records),
                "persons": persons,
                "organizations": orgs,
                "other": len(self._records) - persons - orgs,
                "compare_strings": len(self._compare_strings),
                "loaded_at": self._loaded_at.isoformat() if self._loaded_at else None,
                "source_size_bytes": self._source_size,
                "source_mtime": (
                    datetime.fromtimestamp(self._source_mtime, timezone.utc).isoformat()
                    if self._source_mtime
                    else None
                ),
                "csv_path": FSF_CSV_PATH,
                "download_url": FSF_DOWNLOAD_URL,
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
        """Fuzzy-Suche ueber Namen und Aliase.

        Algorithmus:
        - Normalisierung der Query und aller Vergleichsstrings (Casefold,
          Sonderzeichen weg, Rechtsform-Suffixe entfernt).
        - rapidfuzz.process.extract mit token_set_ratio:
          * tokenisiert beide Strings
          * vergleicht Mengenbezuege (Reihenfolge irrelevant)
          * ignoriert duplizierte Tokens
        - Pro betroffenem Datensatz wird der hoechste Score behalten.
        - Klassifikation in exact/high/medium/low fuer die Anzeige.
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
        # mapping: record_idx -> (score, choice_idx, score_idx_for_tiebreak)
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
                )
            )

        results.sort(key=lambda h: h.score, reverse=True)
        return results[:limit]

    # ── Status ───────────────────────────────────────────────────────────

    def is_loaded(self) -> bool:
        with self._lock:
            return bool(self._records)


# ── Singleton ────────────────────────────────────────────────────────────────

_index: FsfIndex | None = None


def get_index() -> FsfIndex:
    global _index
    if _index is None:
        _index = FsfIndex()
        _index.load(FSF_CSV_PATH)
    elif not _index.is_loaded():
        _index.load(FSF_CSV_PATH)
    return _index


def warmup() -> None:
    """Wird beim Lifespan-Startup aufgerufen."""
    try:
        idx = get_index()
        log.info("Sanctions-Index Warmup: %s", idx.stats())
    except Exception as e:  # noqa: BLE001
        log.warning("Sanctions-Index Warmup fehlgeschlagen: %s", e)


# ── Methoden-Erlaeuterung (statisch, fuer Frontend-Card) ─────────────────────


def method_explanation() -> dict:
    """Beschreibt das Such-Verfahren für die Frontend-Card."""
    return {
        "title": "Wie funktioniert die Suche?",
        "summary": (
            "Die Eingabe wird mit jedem Namen und Aliase der EU-Sanktionsliste "
            "verglichen. Beide Seiten werden vorher normalisiert (Kleinschreibung, "
            "Akzente und Sonderzeichen entfernt, Rechtsformsuffixe wie GmbH oder "
            "Ltd ignoriert). Anschließend berechnet rapidfuzz mit dem "
            "Token-Set-Ratio einen Ähnlichkeitswert von 0 bis 100."
        ),
        "steps": [
            {
                "title": "1. Normalisierung",
                "text": (
                    "Eingabe und Listenname werden in eine vergleichbare Form gebracht: "
                    "casefold, Diakritika weg, Bindestriche und Punkte als Trennzeichen, "
                    "Rechtsformsuffixe (GmbH, AG, Ltd, OOO …) entfernt. Damit matcht "
                    "‚Müller-Schmidt GmbH‘ auch auf ‚MUELLER SCHMIDT‘."
                ),
            },
            {
                "title": "2. Token-Set-Ratio",
                "text": (
                    "Die normalisierten Strings werden in Tokens zerlegt. Verglichen wird "
                    "die Mengenschnittmenge — Reihenfolge spielt keine Rolle, doppelte "
                    "Tokens werden ignoriert. ‚Anatoly Petrov Sergeev‘ trifft so auf "
                    "‚Sergeev Anatoly‘ mit hoher Ähnlichkeit."
                ),
            },
            {
                "title": "3. Best-Match pro Eintrag",
                "text": (
                    "Pro Datensatz werden Hauptname und alle Aliase einzeln verglichen. "
                    "Behalten wird der höchste Score — so geht ein Treffer in einer "
                    "russischen Schreibung nicht verloren, nur weil der lateinische Name "
                    "schwächer matcht."
                ),
            },
            {
                "title": "4. Konfidenz-Klassen",
                "text": (
                    "exact (≥97): Schreibweise praktisch identisch · "
                    "high (≥90): klare Übereinstimmung, lohnt sich Abklärung · "
                    "medium (≥80): Hinweis, manuell prüfen · "
                    "low (≥65): nur Verdacht, oft Namensgleichheit ohne Bezug."
                ),
            },
        ],
        "library": "rapidfuzz · fuzz.token_set_ratio",
        "source_pattern": "auditworkshop/backend/services/sanctions_service.py",
        "data_source": {
            "name": "OpenSanctions — eu_fsf (targets.simple.csv)",
            "url": FSF_DOWNLOAD_URL,
            "license": "CC BY 4.0",
            "update_frequency": "täglich (OpenSanctions-Crawl)",
        },
        "limits": [
            "Prüfung erfolgt nur gegen die EU-Konsolidierte Finanzsanktionsliste (FSF). "
            "OFAC, UN, BAFA, OFSI, SECO sind hierüber NICHT abgedeckt — dafür separate "
            "Recherche über die jeweiligen offiziellen Tools (siehe Karten unten).",
            "Treffer ersetzen keine offizielle Prüfung. Die Listeneinsicht beim "
            "konsolidierten EU-Verzeichnis ist verbindlich.",
            "Namensgleichheit ist häufig — vor allem bei Russisch-Transliterationen. "
            "Geburtsdatum und Land im Treffer immer mit dem Vorgang abgleichen.",
        ],
    }
