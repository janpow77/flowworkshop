"""
flowworkshop · services/state_aid_harvester.py

TAM (Transparency Aid Module) Harvester. Plan §11. HTTP + BeautifulSoup,
keine Browser-Automation. Wird vom CLI-Skript und vom Admin-Endpoint genutzt.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models.state_aid import StateAidAward, StateAidHarvestRun, StateAidSource
from services.state_aid_service import (
    build_competition_search_url,
    derive_nuts_code,
    detect_sa_reference,
    normalize_company_name,
    normalize_country_code,
    parse_amount,
    parse_date,
)

log = logging.getLogger(__name__)


TAM_BASE = "https://webgate.ec.europa.eu/competition/transparency/public"
TAM_HOME = f"{TAM_BASE}?lang=en"
TAM_SEARCH = f"{TAM_BASE}/search"
TAM_RESULTS = f"{TAM_BASE}/search/results"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; FlowWorkshopStateAid/1.0; "
    "https://workshop.flowaudit.de)"
)
RATE_LIMIT_SECONDS = 0.6
HARVEST_TIMEOUT = 60.0

# Smart-Mode-Konstanten (Plan §11): TAM publiziert Awards nachtraeglich,
# daher schauen wir 14 Tage vor `last_successful_harvest_at` zurueck, um
# spaet eingestellte Eintraege nicht zu verpassen.
SMART_LOOKBACK_DAYS = 14
SMART_MIN_DATE = date(1990, 1, 1)


# Drei Modi (Plan §11):
#   smart         — nur neue Datensaetze einfuegen, alte unveraendert lassen.
#                   Auto-Since 14 Tage vor letztem Lauf, ON CONFLICT DO NOTHING.
#   full-refresh  — vollen Re-Scan; bei Konflikt UPDATE (fuer korrigierte
#                   TAM-Daten).
#   force         — alle Awards der Quelle vorab loeschen, danach Insert.
HarvestMode = Literal["smart", "full-refresh", "force"]


# ── Datenklassen ──────────────────────────────────────────────────────────────


@dataclass
class HarvestParams:
    country_iso3: str = "DEU"   # TAM-Code: DEU, AUT, ...
    region_codes: list[str] = field(default_factory=list)
    since: date | None = None
    until: date | None = None
    limit: int = 500
    page_size: int = 100
    triggered_by: str = "cli"
    source_key: str | None = None   # Default-Mapping aus country_iso3
    # Drei Modi: smart (Default, idempotent), full-refresh, force.
    mode: HarvestMode = "smart"


@dataclass
class HarvestResult:
    run_id: str
    status: str
    records_seen: int
    records_inserted: int
    records_updated: int
    records_failed: int
    records_skipped: int = 0
    error: str | None = None
    pages_fetched: int = 0


# ── Helpers ────────────────────────────────────────────────────────────────────


def _resolve_since(
    *,
    mode: HarvestMode,
    explicit_since: date | None,
    last_successful_harvest_at: datetime | None,
    lookback_days: int = SMART_LOOKBACK_DAYS,
    min_date: date = SMART_MIN_DATE,
) -> tuple[date | None, bool]:
    """Pure Helper — bestimmt den effektiven `since`-Wert eines Laufs.

    Im smart-Modus wird ein Auto-Since berechnet, wenn weder ein expliziter
    `since`-Parameter noch ein explizites `until` vorgegeben ist. Der
    Auto-Since-Wert ist `last_successful_harvest_at - lookback_days` und
    wird auf `min_date` (1990-01-01) geclampt.

    Rueckgabe: (effective_since, auto_since_used).
    """
    # Explizit gesetzter since hat immer Vorrang.
    if explicit_since is not None:
        return explicit_since, False
    # Auto-Since nur im smart-Modus und nur, wenn ein voriger Lauf existiert.
    if mode != "smart":
        return None, False
    if last_successful_harvest_at is None:
        return None, False
    base_date = last_successful_harvest_at.date()
    effective = base_date - timedelta(days=lookback_days)
    if effective < min_date:
        effective = min_date
    return effective, True


def _default_source_key(country_iso3: str) -> str:
    if country_iso3.upper() == "DEU":
        return "tam_de"
    if country_iso3.upper() == "AUT":
        return "tam_at"
    return f"tam_{country_iso3.lower()}"


def _format_date_for_tam(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _text(element) -> str:
    """Trim + Whitespace-Kompaktor fuer BS-Elemente."""
    if element is None:
        return ""
    return " ".join(element.get_text(" ", strip=True).split())


def _attr_title_else_text(td) -> str:
    """TAM trunkiert lange Werte und legt den vollen Wert in `title`. """
    if td is None:
        return ""
    title = td.get("title", "").strip()
    if title:
        return title
    return _text(td)


# ── HTTP-Session ──────────────────────────────────────────────────────────────


class TamSession:
    """Einfache Session mit Cookie-Jar und CSRF-Token."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.client = httpx.Client(
            timeout=HARVEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"},
        )
        self.csrf_token: str | None = None

    def __enter__(self) -> "TamSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.client.close()

    def _extract_csrf(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        token = soup.find("input", {"name": "CSRFTOKEN"})
        if token:
            return token.get("value", "").strip() or None
        return None

    def init(self) -> None:
        resp = self.client.get(TAM_HOME)
        resp.raise_for_status()
        # TAM setzt LB_TRANSPARENCY mit malformed `domain=;` — Pythons cookiejar
        # verwirft das. Manuelle Extraktion erforderlich, sonst landet jeder
        # Folge-Request wieder auf dem Sprach-Picker.
        for sc in resp.headers.get_list("set-cookie"):
            name_value = sc.split(";", 1)[0]
            if "=" not in name_value:
                continue
            n, v = name_value.split("=", 1)
            n, v = n.strip(), v.strip()
            if n.lower() == "lb_transparency":
                self.client.cookies.set(
                    n, v,
                    domain="webgate.ec.europa.eu",
                    path="/competition/transparency",
                )
        self.csrf_token = self._extract_csrf(resp.text)
        if not self.csrf_token:
            raise RuntimeError("TAM: CSRF-Token konnte nicht gelesen werden.")

    def submit_search(self, params: HarvestParams) -> str:
        """Sendet die Suchparameter direkt an /search/results.

        TAM akzeptiert auch die direkte Submit auf /search/results, solange
        CSRF, Cookie und ``resetSearch=true`` mitgeschickt werden. Die
        ``/search``-Zwischenstufe ist nur fuer das Refinement der GUI relevant.
        """
        if not self.csrf_token:
            self.init()
        form_pairs: list[tuple[str, str]] = [
            ("CSRFTOKEN", self.csrf_token or ""),
            ("resetSearch", "true"),
            ("countries", f"Country{params.country_iso3.upper()}"),
            ("dateGrantedFrom", _format_date_for_tam(params.since)),
            ("dateGrantedTo", _format_date_for_tam(params.until)),
            ("currency", "EUR"),
            ("max", str(params.page_size)),
            ("offset", "0"),
        ]
        for region in params.region_codes:
            form_pairs.append(("grantingAuthorityRegions", region))
        # urlencode mit doseq=False, damit list-of-tuples mit duplizierten
        # Schluesseln korrekt erzeugt wird (httpx 0.27.x verarbeitet `data=`
        # mit Tuple-Listen unterschiedlich je Version).
        body = urlencode(form_pairs)
        resp = self.client.post(
            TAM_RESULTS,
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://webgate.ec.europa.eu",
                "Referer": TAM_HOME,
            },
        )
        resp.raise_for_status()
        new_csrf = self._extract_csrf(resp.text)
        if new_csrf:
            self.csrf_token = new_csrf
        return resp.text

    def get_page(self, offset: int, page_size: int) -> str:
        url = f"{TAM_RESULTS}?offset={offset}&max={page_size}"
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.text


# ── HTML-Parser ───────────────────────────────────────────────────────────────


def parse_results(html: str) -> tuple[list[dict], int | None]:
    """Liefert (rows, total_records). Total kommt aus der Pagination-Anzeige."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": "resultsTable"})
    rows: list[dict] = []
    if not table:
        return rows, None

    tbody = table.find("tbody")
    if not tbody:
        return rows, None

    for tr in tbody.find_all("tr", recursive=False):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 14:
            continue

        # Spalten-Reihenfolge laut TAM Public Search (siehe state-aid-source-analysis.md)
        country = _text(cells[0])
        title_text = _attr_title_else_text(cells[1])

        sa_link = cells[2].find("a") if len(cells) > 2 else None
        sa_text = _text(cells[2])
        sa_href = sa_link.get("href") if sa_link and sa_link.has_attr("href") else None

        ref_link = cells[3].find("a") if len(cells) > 3 else None
        ref_text = _text(cells[3])
        ref_href = ref_link.get("href") if ref_link and ref_link.has_attr("href") else None

        national_id = _attr_title_else_text(cells[4])
        beneficiary_name = _attr_title_else_text(cells[5])
        beneficiary_type = _text(cells[6])
        region = _text(cells[7])
        nace = _attr_title_else_text(cells[8])
        instrument = _text(cells[9])
        objective = _attr_title_else_text(cells[10])

        # Spalten 11/12: Nominal / Granted (mit Currency-Tag)
        nominal_amount_raw = _attr_title_else_text(cells[11])
        granted_amount_raw = _attr_title_else_text(cells[12])

        date_granted = _text(cells[13]) if len(cells) > 13 else ""
        granting_authority = _text(cells[14]) if len(cells) > 14 else ""
        entrusted_entity = _text(cells[15]) if len(cells) > 15 else ""
        financial_intermediaries = _text(cells[16]) if len(cells) > 16 else ""
        published_date = _text(cells[17]) if len(cells) > 17 else ""

        rows.append({
            "country": country,
            "title": title_text,
            "sa_text": sa_text,
            "sa_href": sa_href,
            "ref_text": ref_text,
            "ref_href": ref_href,
            "national_id": national_id,
            "beneficiary_name": beneficiary_name,
            "beneficiary_type": beneficiary_type,
            "region": region,
            "nace": nace,
            "instrument": instrument,
            "objective": objective,
            "nominal_amount_raw": nominal_amount_raw,
            "granted_amount_raw": granted_amount_raw,
            "date_granted": date_granted,
            "granting_authority": granting_authority,
            "entrusted_entity": entrusted_entity,
            "financial_intermediaries": financial_intermediaries,
            "published_date": published_date,
        })

    # Total: pagination zeigt letzte Step-Zahl an, oder die Tabelle hat <= page_size
    total: int | None = None
    pagination = soup.find("div", {"class": "pagination"})
    if pagination:
        steps = pagination.find_all("a", {"class": "step"})
        if steps:
            try:
                last_text = steps[-1].get_text(strip=True)
                if last_text.isdigit():
                    total = int(last_text) * len(rows) if rows else None
            except Exception:
                total = None
    return rows, total


# ── Mapping zu DB-Award ───────────────────────────────────────────────────────


def map_row_to_award(row: dict, *, source_key: str, run_id: str) -> dict:
    """TAM-Zeile -> Dict fuer ON-CONFLICT-Insert."""
    iso2, country_name = normalize_country_code(row.get("country") or "")
    nuts_code, nuts_level = derive_nuts_code(
        region_label=row.get("region"), country_iso2=iso2,
    )
    sa_norm, case_url = detect_sa_reference(row.get("sa_text") or row.get("title") or "")
    if not case_url and sa_norm and row.get("sa_href"):
        case_url = row["sa_href"]
    elif not case_url and sa_norm:
        case_url = build_competition_search_url(sa_norm)

    detail_url = row.get("ref_href") or ""
    if detail_url and detail_url.startswith("/"):
        detail_url = f"https://webgate.ec.europa.eu{detail_url}"

    aid_amount = parse_amount(row.get("granted_amount_raw") or "")
    nominal_amount = parse_amount(row.get("nominal_amount_raw") or "")
    currency = "EUR"  # TAM-Search forciert EUR; sonst beim Detail nachladen

    name = (row.get("beneficiary_name") or "").strip()
    record_id = (row.get("ref_text") or "").strip() or detail_url or name

    return {
        "source_key": source_key,
        "source_record_id": record_id,
        "source_url": detail_url or None,
        "harvest_run_id": run_id,
        "beneficiary_name": name,
        "beneficiary_name_normalized": normalize_company_name(name),
        "beneficiary_identifier": (row.get("national_id") or "").strip() or None,
        "beneficiary_type": (row.get("beneficiary_type") or "").strip() or None,
        "country_code": iso2,
        "country_name": country_name or row.get("country") or None,
        "nuts_code": nuts_code,
        "nuts_label": (row.get("region") or "").strip() or None,
        "nuts_level": nuts_level,
        "nace_code": None,
        "nace_label": (row.get("nace") or "").strip() or None,
        "aid_amount": aid_amount,
        "aid_currency": currency,
        "aid_amount_eur": aid_amount,
        "aid_nominal_amount": nominal_amount,
        "aid_instrument": (row.get("instrument") or "").strip() or None,
        "aid_objective": (row.get("objective") or "").strip() or None,
        "aid_measure_title": (row.get("title") or "").strip() or None,
        "granting_authority": (row.get("granting_authority") or "").strip() or None,
        "entrusted_entity": (row.get("entrusted_entity") or "").strip() or None,
        "financial_intermediaries": (row.get("financial_intermediaries") or "").strip() or None,
        "granting_date": parse_date(row.get("date_granted")),
        "publication_date": parse_date(row.get("published_date")),
        "measure_reference": (row.get("ref_text") or "").strip() or None,
        "sa_reference": sa_norm,
        "case_url": case_url,
        "decision_url": None,
        "raw_payload": row,
    }


# ── Hauptfunktion ─────────────────────────────────────────────────────────────


def run_harvest(db: Session, params: HarvestParams, *, check_only: bool = False) -> HarvestResult:
    """Plan §11.1 — TAM-Harvest mit Pagination und Modus-abhaengiger Schreibstrategie.

    Modi:
      - ``smart`` (Default): Auto-Since 14 Tage vor letztem erfolgreichen
        Lauf, ``ON CONFLICT DO NOTHING``. Bestehende Awards bleiben
        unveraendert; neue werden eingefuegt, Duplikate als ``skipped``
        gezaehlt.
      - ``full-refresh``: ``since``/``until`` wie uebergeben; Konflikte
        werden via ``ON CONFLICT DO UPDATE`` aktualisiert (Korrekturen
        seitens TAM ziehen nach).
      - ``force``: Vor dem Lauf werden alle Awards der Quelle geloescht,
        danach Insert. Anzahl geloeschter Records wird in
        ``error_message`` (Info-Text) protokolliert.
    """
    source_key = params.source_key or _default_source_key(params.country_iso3)
    mode: HarvestMode = params.mode or "smart"

    # ── Mode 'force': vor dem Lauf bestehende Awards der Quelle loeschen ──
    force_deleted_count = 0
    if mode == "force" and not check_only:
        force_deleted_count = (
            db.query(StateAidAward)
            .filter(StateAidAward.source_key == source_key)
            .delete(synchronize_session=False)
        )
        db.commit()
        log.warning(
            "Harvest mode=force: %d bestehende Awards aus '%s' geloescht.",
            force_deleted_count, source_key,
        )

    # ── Smart-Mode: Auto-Since berechnen, wenn nicht explizit gesetzt ──
    src_record = (
        db.query(StateAidSource)
        .filter(StateAidSource.source_key == source_key)
        .first()
    )
    last_success = src_record.last_successful_harvest_at if src_record else None
    effective_since, auto_since_used = _resolve_since(
        mode=mode,
        explicit_since=params.since,
        last_successful_harvest_at=last_success,
    )
    if auto_since_used:
        log.info(
            "Smart-Mode Auto-Since aktiv: source=%s last_success=%s effective_since=%s",
            source_key, last_success, effective_since,
        )
        # Den effektiven Wert in den Params spiegeln, damit submit_search()
        # ihn an TAM mitschickt.
        params.since = effective_since

    run = StateAidHarvestRun(
        source_key=source_key,
        source_url=TAM_BASE,
        triggered_by=params.triggered_by,
        status="running",
        parameters={
            "mode": mode,
            "country_iso3": params.country_iso3,
            "region_codes": params.region_codes,
            "since": params.since.isoformat() if params.since else None,
            "until": params.until.isoformat() if params.until else None,
            "effective_since": effective_since.isoformat() if effective_since else None,
            "auto_since_used": auto_since_used,
            "limit": params.limit,
            "page_size": params.page_size,
            "check_only": check_only,
            "force_deleted_before": force_deleted_count if mode == "force" else None,
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    seen = inserted = updated = failed = skipped = pages = 0
    error_msg: str | None = None
    if mode == "force" and force_deleted_count:
        # Info-Text, kein Fehler — landet in error_message zur Audit-Spur.
        error_msg = f"force-mode: {force_deleted_count} bestehende Awards vorab geloescht."

    try:
        with TamSession() as tam:
            tam.init()
            html = tam.submit_search(params)
            rows, _total = parse_results(html)
            pages = 1
            # Coverage-Sektion (Polish-Runde 3, Aufgabe 3): erwartete
            # Gesamtzahl der Quelle persistieren — wird vom Audit-Report fuer
            # `coverage_percent` benutzt. Best-Effort, idempotent.
            if _total and isinstance(_total, int) and _total > 0:
                try:
                    src_for_total = (
                        db.query(StateAidSource)
                        .filter(StateAidSource.source_key == source_key)
                        .first()
                    )
                    if src_for_total is not None:
                        src_for_total.expected_total = int(_total)
                        src_for_total.expected_total_updated_at = (
                            datetime.now(timezone.utc)
                        )
                        db.commit()
                except Exception:  # noqa: BLE001
                    log.exception(
                        "expected_total-Update fehlgeschlagen (best-effort)",
                    )
                    try:
                        db.rollback()
                    except Exception:  # noqa: BLE001
                        pass
            if check_only:
                run.status = "check_only"
                run.records_seen = len(rows)
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return HarvestResult(
                    run_id=run.id, status="check_only",
                    records_seen=len(rows),
                    records_inserted=0, records_updated=0, records_failed=0,
                    records_skipped=0,
                    pages_fetched=1,
                )

            offset = 0
            while rows and seen < params.limit:
                for row in rows:
                    if seen >= params.limit:
                        break
                    seen += 1
                    try:
                        award = map_row_to_award(row, source_key=source_key, run_id=run.id)
                        if not award["beneficiary_name"]:
                            failed += 1
                            continue
                        # Modusabhaengige Schreibstrategie
                        stmt = pg_insert(StateAidAward).values(**award)
                        if mode == "smart":
                            # Idempotent: alte Datensaetze bleiben unveraendert.
                            stmt = stmt.on_conflict_do_nothing(
                                index_elements=["source_key", "source_record_id"],
                            )
                        elif mode == "full-refresh":
                            # Korrekturen seitens TAM uebernehmen.
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["source_key", "source_record_id"],
                                set_={
                                    k: getattr(stmt.excluded, k) for k in (
                                        "source_url", "harvest_run_id",
                                        "beneficiary_name", "beneficiary_name_normalized",
                                        "beneficiary_identifier", "beneficiary_type",
                                        "country_code", "country_name", "nuts_code",
                                        "nuts_label", "nuts_level", "nace_label",
                                        "aid_amount", "aid_currency", "aid_amount_eur",
                                        "aid_nominal_amount", "aid_instrument",
                                        "aid_objective", "aid_measure_title",
                                        "granting_authority", "entrusted_entity",
                                        "financial_intermediaries", "granting_date",
                                        "publication_date", "measure_reference",
                                        "sa_reference", "case_url", "raw_payload",
                                    )
                                },
                            )
                        # mode == "force": kein Conflict moeglich (Tabelle vorab geleert).
                        result = db.execute(stmt)
                        rc = result.rowcount or 0
                        if mode == "smart":
                            if rc > 0:
                                inserted += 1
                            else:
                                # Konflikt -> Datensatz war bereits vorhanden,
                                # bleibt unveraendert. Nicht als failed werten.
                                skipped += 1
                        else:
                            # full-refresh / force: rowcount > 0 als Touch-Counter.
                            # Saubere Trennung insert/update wuerde SELECT vorab
                            # erfordern -- bewusst weggelassen (Performance).
                            if rc > 0:
                                inserted += 1
                    except Exception as exc:  # noqa: BLE001
                        failed += 1
                        log.warning("State-Aid Upsert fehlgeschlagen: %s", exc)
                db.commit()

                if seen >= params.limit:
                    break

                offset += len(rows)
                time.sleep(RATE_LIMIT_SECONDS)
                try:
                    next_html = tam.get_page(offset, params.page_size)
                except httpx.HTTPError as exc:
                    error_msg = f"Pagination-Fehler bei offset={offset}: {exc}"
                    break
                rows, _ = parse_results(next_html)
                pages += 1
                if not rows:
                    break

        run.status = "ok" if failed == 0 else "partial"
    except Exception as exc:  # noqa: BLE001
        log.exception("State-Aid Harvest fehlgeschlagen")
        run.status = "failed"
        error_msg = str(exc)
    finally:
        run.records_seen = seen
        run.records_inserted = inserted
        run.records_updated = updated
        run.records_failed = failed
        # records_skipped via setattr fuer den Fall, dass die Migration
        # noch nicht durchgelaufen ist (defensive).
        try:
            run.records_skipped = skipped
        except Exception:
            pass
        run.error_message = error_msg
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

        # Quellenstatus aktualisieren
        try:
            src = db.query(StateAidSource).filter(StateAidSource.source_key == source_key).first()
            if src and run.status in ("ok", "partial"):
                src.last_successful_harvest_at = run.finished_at
                src.record_count = (
                    db.query(StateAidAward)
                    .filter(StateAidAward.source_key == source_key)
                    .count()
                )
                if seen > 0 and failed < seen:
                    src.quality = "green" if failed == 0 else "yellow"
                db.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("Source-Status-Update fehlgeschlagen: %s", exc)

    return HarvestResult(
        run_id=run.id,
        status=run.status,
        records_seen=seen,
        records_inserted=inserted,
        records_updated=updated,
        records_failed=failed,
        records_skipped=skipped,
        error=error_msg,
        pages_fetched=pages,
    )
