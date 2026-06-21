"""Screenshot-Microservice für den Auditworkshop (Security-Scan-Modul).

Rendert eine Ziel-Webseite mit Headless-Chromium (Playwright) und liefert
die PNG-Bytes zurück. Das Backend ruft `POST /screenshot` mit
`{"url": "...", "full_page": false}` auf und erwartet `image/png` als Antwort.

Härtung:
- Nur `http`/`https`-Schemata sind erlaubt (kein `file:`, kein lokaler
  Dateizugriff) → 400 bei anderen Schemata.
- Strikter Render-Timeout (~25 s).
- Pro Request ein eigener BrowserContext + eine eigene Page, die nach dem
  Screenshot wieder geschlossen werden — kein geteilter Zustand zwischen
  Anfragen.
- Fehler/Timeout beim Rendern → HTTP 502 mit JSON-Fehlermeldung.

Eine einzelne Chromium-Instanz wird beim App-Start hochgefahren und für die
Laufzeit des Dienstes wiederverwendet.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from playwright.async_api import async_playwright
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("security-screenshot")

# Strikter Render-Timeout (Navigation) in Millisekunden.
RENDER_TIMEOUT_MS = 25_000
# Best-effort-Wartezeit auf Netzwerk-Ruhe nach dem DOM (für SPAs, die ihre
# Initialdaten erst nach dem load-Event holen). Wird das nicht erreicht
# (z. B. Polling/SSE), fahren wir nach dem Settle-Delay trotzdem fort.
NETWORKIDLE_TIMEOUT_MS = int(os.getenv("SCREENSHOT_NETWORKIDLE_MS", "8000"))
# Fester Settle-Delay vor der Aufnahme: lässt die SPA nach dem Daten-Fetch
# tatsächlich rendern/painten — verhindert leere Shell-/Spinner-Screenshots.
SETTLE_MS = int(os.getenv("SCREENSHOT_SETTLE_MS", "2000"))
VIEWPORT = {"width": 1280, "height": 800}
ALLOWED_SCHEMES = ("http", "https")

# Chromium-Argumente: --no-sandbox ist im Container nötig (kein User-Namespace).
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startet beim App-Start eine einzelne, geteilte Chromium-Instanz."""
    log.info("Starte Playwright + Chromium (headless) …")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)
    app.state.playwright = playwright
    app.state.browser = browser
    log.info("Chromium bereit.")
    try:
        yield
    finally:
        log.info("Schließe Chromium + Playwright …")
        await browser.close()
        await playwright.stop()


app = FastAPI(title="Auditworkshop Screenshot-Service", lifespan=lifespan)


class ScreenshotRequest(BaseModel):
    url: str
    full_page: bool = False


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/screenshot")
async def screenshot(req: ScreenshotRequest) -> Response:
    """Rendert die Ziel-URL und gibt die PNG-Bytes zurück."""
    parsed = urlparse(req.url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Nur http/https-URLs mit Host sind erlaubt.",
        )

    browser = app.state.browser
    context = None
    try:
        # Eigener Kontext pro Request: schlechte Zertifikate ignorieren,
        # damit auch Seiten mit ungültigem Cert ein Bild liefern.
        context = await browser.new_context(
            ignore_https_errors=True,
            viewport=VIEWPORT,
        )
        page = await context.new_page()
        page.set_default_navigation_timeout(RENDER_TIMEOUT_MS)
        # 1) DOM laden (schnell, robust). 2) Netzwerk-Ruhe abwarten (best
        #    effort — SPAs holen ihre Daten oft erst nach dem load-Event).
        #    3) Fester Settle-Delay, damit die App tatsächlich rendert/paintet.
        #    Ohne (2)+(3) wird die leere Shell bzw. der Lade-Spinner abgelichtet.
        await page.goto(req.url, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
        try:
            await page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            log.info("networkidle nicht erreicht für %s — fahre nach Settle-Delay fort", req.url)
        if SETTLE_MS > 0:
            await page.wait_for_timeout(SETTLE_MS)
        png = await page.screenshot(type="png", full_page=req.full_page)
        return Response(content=png, media_type="image/png")
    except Exception as exc:  # noqa: BLE001
        log.warning("Screenshot fehlgeschlagen für %s: %s", req.url, exc)
        return JSONResponse(
            status_code=502,
            content={"error": "Screenshot fehlgeschlagen", "detail": str(exc)},
        )
    finally:
        if context is not None:
            await context.close()
