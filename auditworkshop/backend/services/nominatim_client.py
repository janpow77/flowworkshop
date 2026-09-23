"""
flowworkshop · services/nominatim_client.py

Nominatim-Abfrage über ``auditcore_geo.nominatim`` (Adapter auf
``auditcore_harvest``). Die Anwendung stellt nur Transport, Uhr, Zähler und
Senke; Anfragebildung (``format=jsonv2``), Trefferprüfung, Budget und die
Tagesgrenze kommen aus der Bibliothek.

Unterschiede zum früheren Direktaufruf in ``geocoding_service.geocode_single``:

- Netz-, Zeit- und Serverfehler sowie unlesbare Antworten sind **kein**
  „nicht gefunden“ (GEO-C10). Nur eine gültige, leere Trefferliste ergibt
  ``kein_treffer``; alles andere ist ``fehler`` und wird vom Aufrufer nicht
  als Negativtreffer zwischengespeichert.
- ``format=jsonv2`` statt ``json`` (GEO-C11).
- Am öffentlichen Endpunkt höchstens 1 000 Anfragen je Tag für diesen Consumer
  (Entscheidung D5 vom 23.09.2026) und mindestens 1 s Abstand; darüber wird
  nicht mehr gefragt (``nicht_gesendet``), bis der Tag wechselt.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests
from auditcore_geo.nominatim import (
    NAMENSNENNUNG,
    OEFFENTLICHER_ENDPUNKT,
    NominatimAdapter,
    empfohlene_laufparameter,
    ist_oeffentlicher_endpunkt,
    pruefe_laufparameter,
)
from auditcore_harvest import (
    ConfigError,
    HarvestEngine,
    RateLimit,
    Response,
    RetryPolicy,
    RunStatus,
    TransportError,
)
from auditcore_harvest.memory import ListSink, MemoryStateStore, StaticCredentials

log = logging.getLogger(__name__)

#: Identifizierende Kennung nach den OSMF-Nutzungsbedingungen.
USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "Auditworkshop-EFRE-Demo/1.0 (+https://github.com/janpow77/flowworkshop)",
)
#: Eigene Instanz statt des öffentlichen Dienstes (dann gilt die Tagesgrenze nicht).
BASIS_URL = os.environ.get("NOMINATIM_BASE_URL", OEFFENTLICHER_ENDPUNKT)
#: Zeitgrenze je Anfrage (wie bisher 5 s).
ZEITGRENZE_S = 5.0
#: Der frühere Dienst hielt 1,1 s Abstand ein; die Bibliothek verlangt mindestens 1 s.
MINDESTABSTAND_S = 1.1


@dataclass(frozen=True)
class NominatimErgebnis:
    """Ergebnis einer Anfrage: ``treffer``, ``kein_treffer``, ``fehler`` oder ``nicht_gesendet``."""

    status: str
    geo: dict | None = None
    grund: str = ""


class _RequestsTransport:
    """``auditcore_harvest.Transport`` über ``requests``; Netzfehler → ``TransportError``."""

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        data: bytes | None = None,
        timeout: float,
    ) -> Response:
        try:
            r = requests.request(
                method, url, params=params, headers=headers, data=data, timeout=timeout
            )
        except requests.RequestException as exc:
            raise TransportError(f"Netzfehler: {type(exc).__name__}") from exc
        return Response(r.status_code, r.content, dict(r.headers), r.url)


class _Systemuhr:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


class _Schlaefer:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class Tageszaehler:
    """Anfragen dieses Consumers am Endpunkt je UTC-Tag (Datei neben dem Geocode-Cache).

    Die Datei hält ``{"tag": "YYYY-MM-DD", "gesendet": n}``; ein Tageswechsel
    setzt den Zähler zurück. Ist die Datei nicht schreibbar, zählt der Prozess
    im Speicher weiter.
    """

    def __init__(self, pfad: Path | None) -> None:
        self.pfad = pfad
        self._lock = threading.Lock()
        self._tag = ""
        self._gesendet = 0
        self._geladen = False

    @staticmethod
    def _heute() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _laden(self) -> None:
        if self._geladen:
            return
        self._geladen = True
        if self.pfad and self.pfad.exists():
            try:
                daten = json.loads(self.pfad.read_text(encoding="utf-8"))
                self._tag = str(daten.get("tag", ""))
                self._gesendet = int(daten.get("gesendet", 0))
            except (OSError, ValueError, TypeError):
                log.warning("Nominatim-Tageszähler unlesbar, beginne bei 0: %s", self.pfad)

    def heute_gesendet(self) -> int:
        with self._lock:
            self._laden()
            if self._tag != self._heute():
                self._tag, self._gesendet = self._heute(), 0
            return self._gesendet

    def hinzufuegen(self, anzahl: int) -> None:
        with self._lock:
            self._laden()
            if self._tag != self._heute():
                self._tag, self._gesendet = self._heute(), 0
            self._gesendet += anzahl
            if self.pfad:
                try:
                    self.pfad.write_text(
                        json.dumps({"tag": self._tag, "gesendet": self._gesendet}),
                        encoding="utf-8",
                    )
                except OSError as exc:
                    log.warning("Nominatim-Tageszähler nicht schreibbar: %s", exc)


_engine_lock = threading.Lock()
#: Ein Takt für alle Aufrufe des Prozesses, damit der Abstand auch zwischen
#: einzelnen Standorten gilt (jeder Aufruf ist ein eigener Lauf).
_TAKT = RateLimit(MINDESTABSTAND_S)


def suche(
    q: str,
    *,
    countrycodes: str | None,
    zaehler: Tageszaehler,
    transport: Any | None = None,
) -> NominatimErgebnis:
    """Genau eine Freitextsuche (``limit=1``) über den Bibliotheksadapter.

    Läuft seriell (ein Thread je Prozess, OSMF-Bedingung) und hält den
    Mindestabstand zwischen aufeinanderfolgenden Aufrufen ein.
    """
    config: dict[str, Any] = {
        "anfragen": [{"id": "geocode", "q": q}],
        "user_agent": USER_AGENT,
        "budget": 1,
        "laufart": "einmalig",
        "basis_url": BASIS_URL,
        "limit": 1,
    }
    if countrycodes:
        config["countrycodes"] = countrycodes.lower()

    with _engine_lock:
        oeffentlich = ist_oeffentlicher_endpunkt(BASIS_URL)
        try:
            bereits = zaehler.heute_gesendet() if oeffentlich else 0
            _, request = empfohlene_laufparameter(
                config, f"geocode-{uuid.uuid4().hex[:12]}", heute_bereits_gesendet=bereits
            )
            # Der prozessweite Takt muss den Mindestabstand des Endpunkts einhalten.
            pruefe_laufparameter(config, _TAKT, request, heute_bereits_gesendet=bereits)
        except ConfigError as exc:
            return NominatimErgebnis("nicht_gesendet", grund=str(exc))

        sink = ListSink()
        engine = HarvestEngine(
            transport=transport or _RequestsTransport(),
            credentials=StaticCredentials(),
            state=MemoryStateStore(),
            clock=_Systemuhr(),
            sleeper=_Schlaefer(),
            # Eine Anfrage je Standort wie bisher; Wiederholung erst beim nächsten Aufruf.
            retry=RetryPolicy(max_attempts=1),
            rate_limit=_TAKT,
            request_timeout=ZEITGRENZE_S,
        )
        ergebnis = engine.run(NominatimAdapter(), request, sink, config=config)
        if oeffentlich:
            zaehler.hinzufuegen(max(1, ergebnis.attempts))

    if ergebnis.status is not RunStatus.COMPLETE or not sink.records:
        codes = ", ".join(str(e.get("code", "?")) for e in ergebnis.errors) or "unvollständig"
        return NominatimErgebnis("fehler", grund=codes)
    daten = next(iter(sink.records.values())).normalized
    if daten["status"] == "kein_treffer":
        return NominatimErgebnis("kein_treffer")
    if daten["status"] != "treffer":
        return NominatimErgebnis("fehler", grund="Antwort ohne gültige Koordinate")
    erster = daten["treffer"][0]
    return NominatimErgebnis(
        "treffer",
        geo={
            "lat": float(erster["lat"]),
            "lon": float(erster["lon"]),
            "display_name": erster.get("anzeigename") or "",
            "source": "nominatim",
            "attribution": NAMENSNENNUNG,
        },
    )
