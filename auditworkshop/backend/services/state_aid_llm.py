"""
flowworkshop · services/state_aid_llm.py

Klartext-Frage-Pipeline fuer das EU-Beihilfe-Transparenzregister (Plan §11.5).

Architektur (zwei-LLM-Calls + ein SQL-Call dazwischen):

    LLM-Call 1: Frage -> JSON-Filter (Filter-Uebersetzer)
        v
    SQL: routers.state_aid._apply_award_filters + fuzzy_match_company
        v
    LLM-Call 2: Treffer -> Klartext-Zusammenfassung (Stream)

Garantie: Keine LLM-Halluzination im Datenfeld. Beträge, Namen, Behoerden
stammen ausschliesslich aus dem SQL-Ergebnis. Das LLM darf nur bereits
berechnete Aggregate paraphrasieren.

Die System-Prompts liegen lokal in dieser Datei (nicht in config.SYSTEM_PROMPTS),
weil sie spezifisch fuer den State-Aid-Endpoint sind und die zentrale
SYSTEM_PROMPTS-Dictionary fuer die sechs Workshop-Szenarien reserviert bleibt.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, AsyncGenerator

from services.ollama_service import stream as llm_stream

log = logging.getLogger(__name__)


# ── System-Prompts ────────────────────────────────────────────────────────────

# Wird vom Filter-Uebersetzer verwendet. Ausschliesslich Deutsch, JSON-only.
FILTER_SYSTEM_PROMPT = """Du bist ein Filter-Uebersetzer fuer das EU-Beihilfe-Transparenzregister.
Erlaubte JSON-Felder:
  q (string, Unternehmensname-Fragment)
  country_code ("DE" oder "AT")
  nuts_code (z.B. DE7, DE2, DE212; Prefix-Match)
  since (YYYY-MM-DD)
  until (YYYY-MM-DD)
  min_amount (Zahl, EUR)
  max_amount (Zahl, EUR)
  aid_instrument (Substring)
  objective (Substring)
  granting_authority (Substring)
  sa_reference (z.B. "SA.40478")
  source_key ("tam_de" oder "tam_at")
Antworte AUSSCHLIESSLICH als JSON-Block. Keine Felder auserhalb der Liste.
NUTS-Mapping (haeufige Aliase):
  Hessen=DE7, Bayern=DE2, NRW=DEA, Baden-Wuerttemberg=DE1, Berlin=DE3,
  Brandenburg=DE4, Sachsen=DED, Niedersachsen=DE9, Hamburg=DE6, Bremen=DE5,
  Schleswig-Holstein=DEF, Rheinland-Pfalz=DEB, Saarland=DEC,
  Sachsen-Anhalt=DEE, Mecklenburg-Vorpommern=DE8, Thueringen=DEG,
  Wien=AT13, Niederoesterreich=AT12, Burgenland=AT11, Steiermark=AT22,
  Kaernten=AT21, Oberoesterreich=AT31, Salzburg=AT32, Tirol=AT33, Vorarlberg=AT34
Antwortformat:
```json
{"q": "...", "country_code": "DE", "since": "2022-01-01", "until": "2022-12-31"}
```
Lass weg, was die Frage nicht hergibt. Erfinde keine Filter, die nicht in der
Frage stehen. Nur diese 12 Felder sind erlaubt."""


# Wird vom Summary-Streamer verwendet. Streng "keine Halluzination".
SUMMARY_SYSTEM_PROMPT = """Du fasst Beihilfe-Treffer fuer einen Pruefer zusammen.
Regeln:
  - Erfinde NICHTS. Nutze ausschliesslich die uebergebenen Daten.
  - Keine personenbezogenen Wertungen.
  - Betraege in EUR mit Tausendertrennzeichen.
  - Maximal 200 Worte.
  - Struktur: 1) Quantitative Uebersicht 2) Top-Empfaenger 3) Top-Behoerden 4) Auffaelligkeiten / Hinweis auf Pruefrelevanz.
  - Bei <5 Treffern: kurze, prosaische Zusammenfassung statt Tabellen.
  - Schreibe Saetze, keine Aufzaehlungspunkte mit Bindestrich.
  - Erwaehne immer den Disclaimer am Ende: 'Diese Auswertung ist ein Arbeitsmittel; das pruefungsrechtliche Urteil obliegt dem Pruefer.'"""


# ── Erlaubte Filter-Felder ────────────────────────────────────────────────────

# Whitelist gegen LLM-Drift — alles ausserhalb wird verworfen.
ALLOWED_FILTER_FIELDS: frozenset[str] = frozenset({
    "q",
    "country_code",
    "nuts_code",
    "since",
    "until",
    "min_amount",
    "max_amount",
    "aid_instrument",
    "objective",
    "granting_authority",
    "sa_reference",
    "source_key",
})

# NUTS-Aliase als deterministischer Fallback, wenn das LLM versagt.
_NUTS_ALIASES_DE: dict[str, str] = {
    "hessen": "DE7",
    "bayern": "DE2",
    "nrw": "DEA",
    "nordrhein-westfalen": "DEA",
    "baden-wuerttemberg": "DE1",
    "baden württemberg": "DE1",
    "berlin": "DE3",
    "brandenburg": "DE4",
    "sachsen": "DED",
    "niedersachsen": "DE9",
    "hamburg": "DE6",
    "bremen": "DE5",
    "schleswig-holstein": "DEF",
    "rheinland-pfalz": "DEB",
    "saarland": "DEC",
    "sachsen-anhalt": "DEE",
    "mecklenburg-vorpommern": "DE8",
    "thueringen": "DEG",
    "thüringen": "DEG",
}
_NUTS_ALIASES_AT: dict[str, str] = {
    "wien": "AT13",
    "niederoesterreich": "AT12",
    "niederösterreich": "AT12",
    "burgenland": "AT11",
    "steiermark": "AT22",
    "kaernten": "AT21",
    "kärnten": "AT21",
    "oberoesterreich": "AT31",
    "oberösterreich": "AT31",
    "salzburg": "AT32",
    "tirol": "AT33",
    "vorarlberg": "AT34",
}


# ── Datenklassen fuer Stats ──────────────────────────────────────────────────


@dataclass
class TopEntry:
    """Ein Eintrag in der Top-N-Liste (Top-Empfaenger / Top-Behoerden / ...)."""
    name: str
    count: int
    total_eur: float


@dataclass
class HitStats:
    """Aggregate fuer eine Trefferliste — pure berechnet, kein LLM."""
    total_hits: int = 0
    total_eur: float = 0.0
    top_beneficiaries: list[TopEntry] = field(default_factory=list)
    top_authorities: list[TopEntry] = field(default_factory=list)
    top_regions: list[TopEntry] = field(default_factory=list)
    top_objectives: list[TopEntry] = field(default_factory=list)
    by_year: dict[int, dict[str, float | int]] = field(default_factory=dict)
    top_share_pct: float = 0.0  # Anteil des Top-Empfaengers an der Summe

    def to_dict(self) -> dict:
        """Serialisiert die Stats fuer SSE-Antwort."""
        def _entry(e: TopEntry) -> dict:
            return {"name": e.name, "count": e.count, "total_eur": e.total_eur}

        return {
            "total_hits": self.total_hits,
            "total_eur": round(self.total_eur, 2),
            "top_beneficiaries": [_entry(e) for e in self.top_beneficiaries],
            "top_authorities": [_entry(e) for e in self.top_authorities],
            "top_regions": [_entry(e) for e in self.top_regions],
            "top_objectives": [_entry(e) for e in self.top_objectives],
            "by_year": {
                str(year): {
                    "count": int(v["count"]),
                    "total_eur": round(float(v["total_eur"]), 2),
                }
                for year, v in sorted(self.by_year.items())
            },
            "top_share_pct": round(self.top_share_pct, 1),
        }


# ── Robustes JSON-Parsing ────────────────────────────────────────────────────


def _extract_json_block(text: str) -> str | None:
    """Holt den JSON-Block aus einer LLM-Antwort.

    Bevorzugt einen Markdown-Codeblock mit Triple-Backticks und optionalem
    'json'-Sprachmarker; faellt zurueck auf den ersten ausgeglichenen
    {...}-Match per Klammern-Balance.
    """
    if not text:
        return None

    # 1. Bevorzugt: explizit markierter Codeblock
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1)

    # 2. Fallback: erster ausgeglichener {...}-Block
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _coerce_filter_value(field_name: str, value: Any) -> Any | None:
    """Validiert/koerziert ein einzelnes Filter-Feld.

    Liefert `None`, wenn das Feld unbrauchbar ist — der Aufrufer entscheidet,
    es nicht zu uebernehmen.
    """
    if value is None:
        return None
    # Strings
    if field_name in {"q", "nuts_code", "aid_instrument", "objective",
                       "granting_authority", "sa_reference", "source_key",
                       "country_code"}:
        if isinstance(value, str):
            v = value.strip()
            if not v:
                return None
            if field_name == "country_code":
                v = v.upper()
                if v not in {"DE", "AT"}:
                    return None
            elif field_name == "nuts_code":
                v = v.upper()
                # NUTS-Codes haben Format: 2 Buchstaben + (0-3 Zeichen, davon
                # MUSS die erste Stelle eine Ziffer sein). 'BAYERN' soll NICHT
                # matchen, 'DE', 'DE2', 'DE21', 'DE212' schon.
                if not re.match(r"^[A-Z]{2}(\d[0-9A-Z]{0,2})?$", v):
                    return None
            elif field_name == "source_key":
                v = v.lower()
                if v not in {"tam_de", "tam_at"}:
                    return None
            return v
        return None
    # Datumsfelder
    if field_name in {"since", "until"}:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip()[:10]).isoformat()
            except (TypeError, ValueError):
                return None
        return None
    # Zahlen
    if field_name in {"min_amount", "max_amount"}:
        try:
            f = float(value)
            if f < 0:
                return None
            return f
        except (TypeError, ValueError):
            return None
    return None


def _sanitize_filter_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Filtert auf Whitelist + koerziert Werte. Drift-Schutz."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in ALLOWED_FILTER_FIELDS:
            continue
        coerced = _coerce_filter_value(k, v)
        if coerced is None:
            continue
        out[k] = coerced
    return out


# ── Deterministischer Fallback-Parser ────────────────────────────────────────


def _detect_year_window(question: str) -> tuple[str | None, str | None]:
    """Erkennt eine Jahreszahl YYYY und liefert (since, until)."""
    m = re.search(r"\b(20\d{2})\b", question)
    if not m:
        return None, None
    year = m.group(1)
    return f"{year}-01-01", f"{year}-12-31"


def _detect_nuts_alias(question: str) -> str | None:
    """Sucht nach Bundesland-Aliasen in der Frage."""
    q_lower = question.lower()
    for alias, code in _NUTS_ALIASES_DE.items():
        if alias in q_lower:
            return code
    for alias, code in _NUTS_ALIASES_AT.items():
        if alias in q_lower:
            return code
    return None


def _detect_min_amount(question: str) -> float | None:
    """Erkennt 'ueber X EUR' / 'mindestens X EUR' / 'mehr als X Mio'.

    Unterstuetzt deutsche Tausenderpunkte (z.B. '500.000') und Dezimalkommas
    (z.B. '2,5 Mio'). Heuristik: mehrfache Punkte als Tausender behandeln,
    ein einzelner Punkt mit drei Nachkommastellen ebenfalls.
    """
    q = question.lower()
    m = re.search(
        r"(?:ueber|über|mehr als|mind\.?|mindestens|>=?|>)\s*"
        r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)\s*"
        r"(mio|millionen|million|mrd|milliarden|milliarde|tsd|tausend)?",
        q,
    )
    if not m:
        return None
    raw = m.group(1)
    # Deutsche Notation: '.' = Tausender, ',' = Dezimal.
    # Wenn mehr als ein Punkt vorhanden ist oder das Token genau drei Stellen
    # nach dem letzten Punkt hat, behandeln wir Punkte als Tausender.
    if raw.count(".") > 1:
        normalized = raw.replace(".", "").replace(",", ".")
    elif "." in raw and "," in raw:
        # '1.234,56' -> Punkte raus, Komma -> Punkt
        normalized = raw.replace(".", "").replace(",", ".")
    elif "." in raw and re.search(r"\.\d{3}(?!\d)", raw):
        # 'X.YYY' mit genau 3 Stellen nach dem Punkt -> Tausender
        normalized = raw.replace(".", "")
    else:
        normalized = raw.replace(" ", "").replace(",", ".")
    try:
        val = float(normalized)
    except ValueError:
        return None
    unit = m.group(2) or ""
    if unit.startswith("mrd") or unit.startswith("millia"):
        val *= 1_000_000_000
    elif unit.startswith("mio") or unit.startswith("milli"):
        val *= 1_000_000
    elif unit.startswith("tsd") or unit.startswith("tausend"):
        val *= 1_000
    return val if val > 0 else None


def _fallback_filter_from_question(
    question: str, *, country_code: str | None = None,
) -> dict[str, Any]:
    """Pures-Python-Fallback, wenn das LLM keinen brauchbaren JSON liefert.

    Nicht so smart wie das LLM, aber besser als nichts. Der Endpoint
    signalisiert das Frontend, dass der LLM-Filter fehlgeschlagen ist.
    """
    out: dict[str, Any] = {}
    if country_code:
        cc = country_code.upper()
        if cc in {"DE", "AT"}:
            out["country_code"] = cc

    nuts = _detect_nuts_alias(question)
    if nuts:
        out["nuts_code"] = nuts
        # Wenn NUTS aus DE-Mapping → country_code DE setzen falls nicht schon da
        if nuts.startswith("DE") and "country_code" not in out:
            out["country_code"] = "DE"
        elif nuts.startswith("AT") and "country_code" not in out:
            out["country_code"] = "AT"

    since, until = _detect_year_window(question)
    if since and until:
        out["since"] = since
        out["until"] = until

    min_amt = _detect_min_amount(question)
    if min_amt:
        out["min_amount"] = min_amt

    # SA-Referenz?
    sa_match = re.search(r"\bSA[.\s\-]?(\d{4,6})(?:/\d{4})?", question, re.IGNORECASE)
    if sa_match:
        out["sa_reference"] = f"SA.{sa_match.group(1)}"

    return out


# ── LLM-Filter-Aufruf ────────────────────────────────────────────────────────


async def _collect_llm_text(
    user_prompt: str,
    system_prompt: str,
    *,
    max_tokens: int,
    timeout_s: float,
) -> str:
    """Sammelt einen kompletten LLM-Stream zu einer einzigen Antwort.

    Wir verwenden die existierende `stream()`-Infrastruktur, weil sie sich um
    Backends (Ollama vs. Gateway), Retries und `<think>`-Filter kuemmert. Die
    SSE-Frames parsen wir hier zurueck zu einem reinen Text.
    """
    parts: list[str] = []
    try:
        async with asyncio.timeout(timeout_s):
            async for sse_chunk in llm_stream(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                documents=None,
                max_tokens=max_tokens,
            ):
                # SSE-Frame-Format: 'data: {"token": "...", "done": false}\n\n'
                # Wir extrahieren nur den `token`-Inhalt.
                for line in sse_chunk.splitlines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        log.warning("LLM-Stream-Fehler: %s", obj.get("error"))
                        continue
                    token = obj.get("token")
                    if token:
                        parts.append(token)
    except (TimeoutError, asyncio.TimeoutError):
        log.warning("LLM-Sammelaufruf Timeout nach %.1fs", timeout_s)
        return "".join(parts)
    return "".join(parts)


async def parse_question(
    question: str,
    *,
    country_code: str | None = None,
    timeout_s: float = 15.0,
) -> tuple[dict[str, Any], str, str]:
    """Uebersetzt eine Klartext-Frage in einen Filter-Dict.

    Liefert ein Tripel `(filter_dict, raw_llm_text, source)`:
    - `filter_dict`: validierter, sanitisierter Filter (kann leer sein)
    - `raw_llm_text`: die rohe LLM-Antwort (zur Debug-Anzeige)
    - `source`: 'llm' (LLM-Output verwendet), 'fallback' (deterministischer
      Fallback), 'merged' (Mix aus beiden)
    """
    if not question or not question.strip():
        return {}, "", "fallback"

    user_prompt = (
        f"Frage: {question.strip()}\n\n"
        "Gib AUSSCHLIESSLICH einen JSON-Codeblock zurueck."
    )

    raw_text = ""
    try:
        raw_text = await _collect_llm_text(
            user_prompt,
            FILTER_SYSTEM_PROMPT,
            max_tokens=240,
            timeout_s=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Filter-LLM-Aufruf fehlgeschlagen: %s", exc)
        raw_text = ""

    # JSON extrahieren und validieren
    json_block = _extract_json_block(raw_text)
    parsed: dict[str, Any] = {}
    if json_block:
        try:
            parsed_raw = json.loads(json_block)
            if isinstance(parsed_raw, dict):
                parsed = _sanitize_filter_dict(parsed_raw)
        except json.JSONDecodeError as exc:
            log.info("LLM-JSON nicht parsebar (%s): %r", exc, json_block[:200])

    # Voreinsteller aus UI uebernimmt vorrang, wenn das LLM kein country_code
    # setzte. Wenn das LLM ein anderes Land liefert, wird das LLM bevorzugt
    # (Nutzer schreibt z.B. "in Wien" -> AT, auch wenn UI auf DE steht).
    if country_code and "country_code" not in parsed:
        cc = country_code.strip().upper()
        if cc in {"DE", "AT"}:
            parsed["country_code"] = cc

    if parsed:
        return parsed, raw_text, "llm"

    # Fallback
    fallback = _fallback_filter_from_question(question, country_code=country_code)
    if fallback:
        return fallback, raw_text, "fallback"

    return {}, raw_text, "fallback"


# ── Filter-Lockerung bei 0 Treffern ──────────────────────────────────────────


# Reihenfolge: zuerst die spezifischsten Felder lockern.
RELAX_ORDER: tuple[str, ...] = (
    "min_amount",
    "max_amount",
    "objective",
    "aid_instrument",
    "granting_authority",
    "sa_reference",
    "nuts_code",
    "since",
    "until",
)


def relax_filters(current: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Entfernt das spezifischste Filter-Feld.

    Liefert `(neues_filter, entferntes_feld)`. Wenn nichts mehr gelockert
    werden kann, ist `entferntes_feld` None.
    """
    new = dict(current)
    for field_name in RELAX_ORDER:
        if field_name in new:
            new.pop(field_name)
            return new, field_name
    # Letzte Eskalation: country_code raus
    if "country_code" in new:
        new.pop("country_code")
        return new, "country_code"
    return new, None


# ── Aggregat-Berechnung (pure, ohne LLM) ─────────────────────────────────────


def _to_float(value: Any) -> float:
    """Sicheres Decimal/None -> float Casting."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _top_n(items: list[dict], key_field: str, *, n: int = 3) -> list[TopEntry]:
    """Aggregiert Hits nach `key_field` -> TopEntry."""
    bucket: dict[str, dict[str, float]] = {}
    for item in items:
        key = item.get(key_field)
        if not key:
            continue
        key_str = str(key)
        b = bucket.setdefault(key_str, {"count": 0, "total_eur": 0.0})
        b["count"] += 1
        b["total_eur"] += _to_float(item.get("aid_amount_eur"))
    sorted_items = sorted(
        bucket.items(),
        key=lambda kv: (kv[1]["total_eur"], kv[1]["count"]),
        reverse=True,
    )[:n]
    return [
        TopEntry(name=name, count=int(v["count"]), total_eur=v["total_eur"])
        for name, v in sorted_items
    ]


def compute_stats(hits: list[dict]) -> HitStats:
    """Berechnet Aggregate aus einer Trefferliste — pure, ohne DB.

    Erwartet Hits im Format wie von `_serialize_award` produziert:
    - `aid_amount_eur` (float | None)
    - `beneficiary_name` (str)
    - `granting_authority` (str | None)
    - `nuts_label` / `nuts_code` (str | None)
    - `aid_objective` (str | None)
    - `granting_date` (ISO-Date-String | None)
    """
    stats = HitStats()
    if not hits:
        return stats

    stats.total_hits = len(hits)
    total = 0.0
    by_year: dict[int, dict[str, float | int]] = {}

    for h in hits:
        amount = _to_float(h.get("aid_amount_eur"))
        total += amount
        # Jahres-Aggregat
        gd = h.get("granting_date")
        if gd:
            try:
                year = int(str(gd)[:4])
                yb = by_year.setdefault(year, {"count": 0, "total_eur": 0.0})
                yb["count"] = int(yb["count"]) + 1
                yb["total_eur"] = float(yb["total_eur"]) + amount
            except (TypeError, ValueError):
                pass

    stats.total_eur = total
    stats.by_year = by_year
    stats.top_beneficiaries = _top_n(hits, "beneficiary_name", n=3)
    stats.top_authorities = _top_n(hits, "granting_authority", n=3)
    # Bevorzugt das menschenlesbare Label, fallback Code
    region_field = "nuts_label" if any(h.get("nuts_label") for h in hits) else "nuts_code"
    stats.top_regions = _top_n(hits, region_field, n=3)
    stats.top_objectives = _top_n(hits, "aid_objective", n=3)

    # Top-Empfaenger-Anteil an Gesamtsumme
    if stats.top_beneficiaries and total > 0:
        stats.top_share_pct = (stats.top_beneficiaries[0].total_eur / total) * 100.0

    return stats


# ── Summary-Stream ───────────────────────────────────────────────────────────


def _format_eur(amount: float) -> str:
    """1234567.89 -> '1.234.567,89 EUR' (deutsche Tausendertrennung)."""
    return f"{amount:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_summary_user_prompt(
    question: str, hits: list[dict], stats: HitStats,
) -> str:
    """Baut den User-Prompt fuer den Summary-Aufruf.

    Gibt dem LLM nur Aggregate + Top-3-Listen — keine vollstaendigen Hits,
    damit der Kontext kurz bleibt und das LLM nicht in Versuchung kommt,
    einzelne Awards umzudichten.
    """
    lines = [f"Nutzerfrage: {question.strip()}", ""]
    lines.append(f"Treffer-Anzahl: {stats.total_hits}")
    lines.append(f"Gesamtsumme: {_format_eur(stats.total_eur)}")

    if stats.top_beneficiaries:
        lines.append("")
        lines.append("Top-Beguenstigte:")
        for e in stats.top_beneficiaries:
            lines.append(f"  - {e.name}: {_format_eur(e.total_eur)} ({e.count} Vorhaben)")

    if stats.top_authorities:
        lines.append("")
        lines.append("Top-Behoerden:")
        for e in stats.top_authorities:
            lines.append(f"  - {e.name}: {_format_eur(e.total_eur)} ({e.count} Vorhaben)")

    if stats.top_regions:
        lines.append("")
        lines.append("Top-Regionen:")
        for e in stats.top_regions:
            lines.append(f"  - {e.name}: {_format_eur(e.total_eur)} ({e.count} Vorhaben)")

    if stats.top_objectives:
        lines.append("")
        lines.append("Top-Ziele/Massnahmen:")
        for e in stats.top_objectives:
            lines.append(f"  - {e.name}: {_format_eur(e.total_eur)}")

    if stats.by_year:
        lines.append("")
        lines.append("Verteilung pro Jahr:")
        for year, v in sorted(stats.by_year.items()):
            lines.append(
                f"  - {year}: {int(v['count'])} Vorhaben, {_format_eur(float(v['total_eur']))}"
            )

    if stats.top_share_pct >= 50.0:
        lines.append("")
        lines.append(
            f"Hinweis: Der Top-Empfaenger erhielt {stats.top_share_pct:.1f}% der Gesamtsumme."
        )

    lines.append("")
    lines.append(
        "Aufgabe: Schreibe eine knappe Zusammenfassung (max. 200 Worte) auf Deutsch."
    )
    return "\n".join(lines)


async def stream_summary(
    question: str,
    hits: list[dict],
    stats: HitStats,
    *,
    timeout_s: float = 30.0,
) -> AsyncGenerator[str, None]:
    """Streamt eine Klartext-Zusammenfassung der Treffer.

    Yields nur reine Tokens (Text), keine SSE-Frames — der Router formatiert
    die SSE selbst.
    """
    if not hits:
        # Kein LLM-Aufruf bei 0 Treffern — wir geben einen statischen Text aus.
        yield (
            "Keine Treffer fuer diese Frage. "
            "Pruefe, ob die Filter zu eng sind oder ob die Datenquelle den "
            "gewuenschten Zeitraum abdeckt. "
            "Diese Auswertung ist ein Arbeitsmittel; das pruefungsrechtliche "
            "Urteil obliegt dem Pruefer."
        )
        return

    user_prompt = _build_summary_user_prompt(question, hits, stats)
    started = time.monotonic()

    try:
        async with asyncio.timeout(timeout_s):
            async for sse_chunk in llm_stream(
                user_prompt=user_prompt,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                documents=None,
                max_tokens=420,
            ):
                # SSE-Frame parsen und nur den `token`-Inhalt durchreichen.
                for line in sse_chunk.splitlines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        log.warning("Summary-Stream-Fehler: %s", obj.get("error"))
                        continue
                    token = obj.get("token")
                    if token:
                        yield token
    except (TimeoutError, asyncio.TimeoutError):
        elapsed = time.monotonic() - started
        log.warning("Summary-Stream Timeout nach %.1fs", elapsed)
        yield (
            "\n\n[Hinweis: Die LLM-Zusammenfassung wurde nach Timeout abgebrochen. "
            "Die obigen Treffer sind die rohen SQL-Ergebnisse.]"
        )
