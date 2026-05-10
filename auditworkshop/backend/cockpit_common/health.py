"""Standard-Health-Endpoint nach APPS_PREPARATION.md §2.2.

Schema:
    {
      "status": "ready" | "degraded" | "starting" | "draining",
      "version": "<git-sha>",
      "started_at": "<iso8601>",
      "checks": {
        "database":     {"status": "ready", "latency_ms": 3.2},
        "llm_router":   {"status": "degraded", "message": "..."}
      }
    }

Verwendung im App-Backend:

    from cockpit_common.health import HealthRegistry, build_health_handler

    registry = HealthRegistry(service="auditworkshop-backend")

    @registry.subcheck("database")
    def check_db() -> SubcheckResult:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return SubcheckResult(status="ready")

    app.add_api_route("/health", build_health_handler(registry), methods=["GET"])

Damit hat jede App genau dasselbe Schema; die Cockpit-Domäne 1
(Statusübersicht) erhält identisches JSON von allen verwalteten Apps.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

# Vier erlaubte Gesamt-Status-Werte (Pflicht aus APPS_PREPARATION.md §2.2).
HealthStatus = str  # "ready" | "degraded" | "starting" | "draining"


@dataclass
class SubcheckResult:
    """Ergebnis eines einzelnen Subchecks (z.B. Datenbank-Probe)."""

    status: HealthStatus = "ready"
    latency_ms: float | None = None
    message: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status}
        if self.latency_ms is not None:
            out["latency_ms"] = round(self.latency_ms, 1)
        if self.message:
            out["message"] = self.message
        out.update(self.extra)
        return out


SubcheckFunc = Callable[[], SubcheckResult | Awaitable[SubcheckResult]]


class HealthRegistry:
    """Sammelt Subchecks pro Anwendung. Threadsafe für Lese-Anfragen."""

    def __init__(
        self,
        service: str,
        version_env: str = "APP_VERSION",
        version_fallback_env: str = "IMAGE_TAG",
    ) -> None:
        self._service = service
        self._version = (
            os.getenv(version_env)
            or os.getenv(version_fallback_env)
            or "dev"
        )
        self._started_at: str | None = None
        self._drain_mode = False
        self._subchecks: dict[str, SubcheckFunc] = {}
        self._timeouts: dict[str, float] = {}

    # ── Konfiguration ────────────────────────────────────────
    def mark_started(self, when: datetime | None = None) -> None:
        self._started_at = (when or datetime.now(timezone.utc)).isoformat()

    @property
    def started_at(self) -> str | None:
        return self._started_at

    def set_drain_mode(self, drain: bool) -> None:
        """Aktiviert/deaktiviert den Drain-Modus (für Pre-Cutover).
        Ein draining-Status veranlasst das Cockpit, neue Anfragen
        auszuweichen, ohne die App als unhealthy zu markieren."""
        self._drain_mode = drain

    @property
    def drain_mode(self) -> bool:
        return self._drain_mode

    @property
    def version(self) -> str:
        return self._version

    @property
    def service(self) -> str:
        return self._service

    def subcheck(
        self,
        name: str,
        timeout_seconds: float = 5.0,
    ) -> Callable[[SubcheckFunc], SubcheckFunc]:
        """Decorator zum Registrieren eines Subchecks.

        @registry.subcheck("database", timeout_seconds=2.0)
        async def check_db() -> SubcheckResult: ...
        """

        def decorator(func: SubcheckFunc) -> SubcheckFunc:
            self._subchecks[name] = func
            self._timeouts[name] = timeout_seconds
            return func

        return decorator

    def register(
        self,
        name: str,
        func: SubcheckFunc,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._subchecks[name] = func
        self._timeouts[name] = timeout_seconds

    # ── Auswertung ───────────────────────────────────────────
    async def evaluate(self) -> dict[str, Any]:
        results: dict[str, dict[str, Any]] = {}

        async def run_one(name: str, fn: SubcheckFunc) -> tuple[str, SubcheckResult]:
            t0 = time.perf_counter()
            try:
                if inspect.iscoroutinefunction(fn):
                    result = await asyncio.wait_for(
                        fn(), timeout=self._timeouts.get(name, 5.0)
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(fn),
                        timeout=self._timeouts.get(name, 5.0),
                    )
            except asyncio.TimeoutError:
                result = SubcheckResult(status="degraded", message="timeout")
            except Exception as exc:  # noqa: BLE001
                log.exception("Subcheck '%s' fehlgeschlagen", name)
                result = SubcheckResult(
                    status="degraded",
                    message=exc.__class__.__name__,
                )
            if not isinstance(result, SubcheckResult):
                # Subcheck-Func gab versehentlich ein dict oder None zurück.
                result = SubcheckResult(
                    status="degraded",
                    message="invalid subcheck return",
                )
            if result.latency_ms is None:
                result.latency_ms = (time.perf_counter() - t0) * 1000
            return name, result

        if self._subchecks:
            evaluated = await asyncio.gather(
                *(run_one(name, fn) for name, fn in self._subchecks.items())
            )
            for name, res in evaluated:
                results[name] = res.to_dict()

        # Gesamt-Status nach §2.2
        if self._started_at is None:
            overall: HealthStatus = "starting"
        elif self._drain_mode:
            overall = "draining"
        elif all(r.get("status") == "ready" for r in results.values()):
            overall = "ready"
        else:
            overall = "degraded"

        return {
            "status": overall,
            "version": self._version,
            "started_at": self._started_at,
            "checks": results,
            "service": self._service,
        }


def build_health_handler(registry: HealthRegistry):
    """Erzeugt eine FastAPI-Handler-Funktion für `GET /health`."""

    async def health() -> dict[str, Any]:
        return await registry.evaluate()

    return health
