"""flowworkshop · services/llm_usage_context.py

Per-Request-Accumulator fuer LLM-Telemetrie + Route-Tracking.

Zwei Mechanismen, die zusammenarbeiten:

1. **Per-Request-Accumulator** (``LlmUsage``):
   - Middleware ruft am Anfang ``start_request()`` auf — frischer Accumulator.
   - ``ollama_service.stream()`` ruft nach jedem Call ``record_call(...)`` —
     summiert Tokens/Dauer in den Accumulator.
   - Middleware ruft am Ende ``collect()`` — schreibt in workshop_access_log.
   - **LIMITATION**: bei SSE-Streaming-Endpoints liefert ``stream()`` Tokens
     NACH dem Middleware-finally (Body wird erst beim Senden konsumiert).
     Fuer SSE-Endpoints bleibt der Accumulator daher leer — die LLM-Felder
     im access_log sind dann NULL. Fuer non-SSE-Endpoints (PDF, JSON)
     funktioniert es.

2. **Direct-Write LLM-Call-Log** (``workshop_llm_call_log``):
   - Unabhaengig vom HTTP-Lifecycle. ``ollama_service.stream()`` macht am
     Ende jedes Calls einen direkten INSERT (Background-Executor).
   - Erfasst auch SSE-Calls vollstaendig.
   - Route wird via ``set_current_route(...)`` ContextVar von der
     Middleware bereitgestellt.

Stats-API queryt beide Tabellen — access_log fuer HTTP-Counts/Latenz,
llm_call_log fuer Token-/Modell-Statistiken.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class LlmUsage:
    """Summen-Telemetrie pro Request."""
    model: str | None = None        # zuletzt verwendetes Modell
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: int = 0
    call_count: int = 0
    models: list[str] = field(default_factory=list)


_USAGE: ContextVar[LlmUsage | None] = ContextVar("llm_usage", default=None)
_ROUTE: ContextVar[str | None] = ContextVar("llm_route", default=None)


def set_current_route(route: str | None) -> None:
    """Speichert die aktuelle Request-Route fuer den direkten LLM-Call-Log."""
    _ROUTE.set(route)


def get_current_route() -> str | None:
    return _ROUTE.get()


def start_request() -> None:
    """Setzt einen frischen Accumulator. Idempotent — wenn schon einer
    laeuft (z.B. bei verschachtelten Middlewares), bleibt der vorhandene
    bestehen."""
    if _USAGE.get() is None:
        _USAGE.set(LlmUsage())


def record_call(
    *,
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    duration_ms: int,
) -> None:
    """Addiert die Telemetrie eines abgeschlossenen LLM-Calls.

    Ist ein No-Op, wenn kein Accumulator aktiv ist (z.B. bei Background-
    Tasks ausserhalb eines Request-Kontexts) — verhindert, dass solche
    Calls den naechsten Request kontaminieren.
    """
    acc = _USAGE.get()
    if acc is None:
        return
    if model:
        acc.model = model
        if model not in acc.models:
            acc.models.append(model)
    if prompt_tokens:
        acc.prompt_tokens += int(prompt_tokens)
    if completion_tokens:
        acc.completion_tokens += int(completion_tokens)
    acc.duration_ms += max(0, int(duration_ms))
    acc.call_count += 1


def collect() -> LlmUsage | None:
    """Liefert den aktuellen Accumulator (oder None, wenn keiner aktiv)
    und setzt ihn auf None zurueck — der naechste Request bekommt einen
    frischen."""
    acc = _USAGE.get()
    _USAGE.set(None)
    return acc if (acc and acc.call_count > 0) else None
