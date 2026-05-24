"""
flowworkshop · services/checklist_events.py

In-Memory-Pub/Sub-Broker + Presence-Registry fuer die Hybrid-Kollaboration des
KOM-Checklisten-Designers (Presence + Node-Locking + Live-Updates via SSE).

Pro ``template_id`` wird eine Menge von Subscribern (je eine ``asyncio.Queue``)
und eine Presence-Map (verbundene Nutzer mit Stammdaten + ``last_seen``)
gefuehrt. Ein Event, das in ``publish(...)`` eingespeist wird, landet in jeder
Queue der Subscriber dieses Templates; der SSE-Endpoint liest aus seiner Queue
und schreibt die Events als ``text/event-stream`` an den Browser.

WICHTIGE ANNAHME / LIMITIERUNG — EIN uvicorn-Worker
---------------------------------------------------
Dieser Broker haelt seinen Zustand AUSSCHLIESSLICH im Prozessspeicher. Das ist
korrekt, solange das Backend mit genau EINEM Worker laeuft (das Dockerfile-CMD
startet uvicorn single-worker). Bei mehreren Workern/Prozessen saehe jeder Worker
nur seine eigenen Subscriber — Events aus Worker A erreichten Clients an Worker B
nicht. Fuer Multi-Worker-Betrieb muesste der Broker durch einen externen
Message-Bus (z.B. Redis Pub/Sub) ersetzt werden. Das ist hier bewusst NICHT
implementiert (keine neuen pip-Abhaengigkeiten, single-worker-Deployment).

Sync→Async-Publish
------------------
Die schreibenden Request-Handler (create/update/delete/move node, lock/unlock)
sind synchrone Funktionen und laufen unter FastAPI im Threadpool — also NICHT im
Event-Loop-Thread. ``asyncio.Queue.put_nowait`` ist nicht threadsafe. Deshalb
merkt sich der Broker beim Start (Lifespan) den laufenden Event-Loop und stellt
das Einreihen per ``loop.call_soon_threadsafe(...)`` zu. ``publish(...)`` ist
damit sowohl aus synchronem als auch aus asynchronem Kontext sicher aufrufbar.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Maximale Queue-Tiefe je Subscriber. Ein langsamer/haengender Client laeuft
# nicht unbegrenzt voll — bei Ueberlauf wird sein aeltestes Event verworfen.
_QUEUE_MAXSIZE = 256


def _utcnow() -> datetime:
    """Naive UTC-Zeit (konsistent mit den tz-losen DateTime-Spalten)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChecklistEventBroker:
    """Prozesslokaler Pub/Sub-Broker + Presence-Registry je Template.

    Nicht fuer Multi-Worker geeignet (siehe Modul-Docstring)."""

    def __init__(self) -> None:
        # template_id → Menge aktiver Subscriber-Queues
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        # template_id → {user_id: {name, organization, bundesland, last_seen}}
        self._presence: dict[str, dict[str, dict]] = {}
        # Verbindungs-Zaehler je (template_id, user_id). Ein Nutzer kann dieselbe
        # Checkliste in mehreren Tabs/Geraeten offen haben — jede SSE-Verbindung
        # zaehlt einzeln. Der Presence-Eintrag wird erst entfernt, wenn die
        # LETZTE Verbindung schliesst (Zaehler faellt auf 0). Verhindert, dass das
        # Schliessen eines von mehreren Tabs den Nutzer faelschlich verschwinden
        # laesst (F-007).
        self._conn_counts: dict[str, dict[str, int]] = {}
        # Referenz auf den Server-Event-Loop, gesetzt im Lifespan-Startup. Wird
        # fuer das threadsafe Einreihen aus Sync-Handlern benoetigt.
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── Event-Loop-Bindung ────────────────────────────────────────────────
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Merkt sich den laufenden Event-Loop (im Lifespan-Startup aufrufen)."""
        self._loop = loop

    # ── Subscriber-Verwaltung (nur aus async-Kontext) ─────────────────────
    def subscribe(self, template_id: str) -> asyncio.Queue:
        """Registriert einen neuen Subscriber und liefert dessen Queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subscribers.setdefault(template_id, set()).add(queue)
        return queue

    def unsubscribe(self, template_id: str, queue: asyncio.Queue) -> None:
        """Entfernt einen Subscriber (beim SSE-Disconnect aufrufen)."""
        subs = self._subscribers.get(template_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(template_id, None)

    # ── Publish (aus sync ODER async aufrufbar) ───────────────────────────
    def publish(self, template_id: str, event: dict) -> None:
        """Verteilt ``event`` an alle Subscriber des Templates.

        Threadsafe: wird aus einem synchronen Request-Handler (Threadpool)
        aufgerufen, erfolgt die Zustellung ueber
        ``loop.call_soon_threadsafe``. Aus dem Event-Loop-Thread heraus wird
        direkt eingereiht. Hat das Template keine Subscriber, ist der Aufruf
        ein guenstiger No-op.
        """
        subs = self._subscribers.get(template_id)
        if not subs:
            return

        running: asyncio.AbstractEventLoop | None
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is not None:
            # Wir sind bereits im Event-Loop-Thread — direkt einreihen.
            self._enqueue(template_id, event)
            return

        # Sync-Kontext (Threadpool): ueber den gebundenen Loop threadsafe
        # einreihen. Ohne gebundenen Loop koennen wir nichts tun (Broker wurde
        # nie initialisiert) — wir verwerfen das Event lautlos.
        loop = self._loop
        if loop is None:
            log.debug("publish() ohne gebundenen Event-Loop — Event verworfen.")
            return
        loop.call_soon_threadsafe(self._enqueue, template_id, event)

    def _enqueue(self, template_id: str, event: dict) -> None:
        """Reiht ``event`` in alle Subscriber-Queues ein (nur im Loop-Thread).

        Bei vollem Puffer (langsamer Client) wird das aelteste Event
        verworfen, damit ein haengender Client den Broker nicht blockiert."""
        for queue in list(self._subscribers.get(template_id, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except Exception:  # noqa: BLE001
                    pass

    # ── Presence-Registry ─────────────────────────────────────────────────
    def presence_join(
        self,
        template_id: str,
        user_id: str,
        *,
        name: str | None,
        organization: str | None,
        bundesland: str | None,
    ) -> dict:
        """Traegt einen Nutzer in die Presence-Map ein bzw. aktualisiert ihn.

        Liefert den aktuellen Presence-Eintrag des Nutzers zurueck."""
        entry = {
            "user_id": user_id,
            "name": name,
            "organization": organization,
            "bundesland": bundesland,
            "last_seen": _utcnow().isoformat(),
        }
        self._presence.setdefault(template_id, {})[user_id] = entry
        return entry

    def presence_touch(self, template_id: str, user_id: str) -> None:
        """Aktualisiert ``last_seen`` eines bereits eingetragenen Nutzers."""
        entry = self._presence.get(template_id, {}).get(user_id)
        if entry is not None:
            entry["last_seen"] = _utcnow().isoformat()

    def presence_connect(self, template_id: str, user_id: str) -> int:
        """Registriert eine NEUE Verbindung (Tab/Geraet) des Nutzers.

        Erhoeht den Verbindungs-Zaehler je ``(template_id, user_id)`` und liefert
        den neuen Stand zurueck. Bei jedem SSE-Connect EINMAL aufrufen — die
        Stammdaten werden weiterhin ueber ``presence_join`` gepflegt (idempotent).
        """
        counts = self._conn_counts.setdefault(template_id, {})
        counts[user_id] = counts.get(user_id, 0) + 1
        return counts[user_id]

    def presence_leave(self, template_id: str, user_id: str) -> int:
        """Meldet das Schliessen EINER Verbindung des Nutzers.

        Verringert den Verbindungs-Zaehler. Erst wenn die letzte Verbindung
        geschlossen wird (Zaehler 0), wird der Presence-Eintrag tatsaechlich
        entfernt. So bleibt ein Nutzer praesent, solange noch mindestens ein Tab
        offen ist (F-007). Liefert die Zahl der verbleibenden Verbindungen.
        """
        counts = self._conn_counts.get(template_id)
        remaining = 0
        if counts and user_id in counts:
            remaining = counts[user_id] - 1
            if remaining > 0:
                counts[user_id] = remaining
            else:
                counts.pop(user_id, None)
                if not counts:
                    self._conn_counts.pop(template_id, None)

        # Nur beim Schliessen der letzten Verbindung aus der Presence-Map nehmen.
        if remaining <= 0:
            users = self._presence.get(template_id)
            if users:
                users.pop(user_id, None)
                if not users:
                    self._presence.pop(template_id, None)
        return max(remaining, 0)

    def presence_list(self, template_id: str) -> list[dict]:
        """Liefert die aktuell verbundenen Nutzer eines Templates als Liste."""
        return list(self._presence.get(template_id, {}).values())


# Modul-Singleton — ein Broker pro Prozess.
broker = ChecklistEventBroker()
