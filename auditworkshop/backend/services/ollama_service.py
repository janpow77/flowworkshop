"""
flowworkshop · ollama_service.py
Streaming-Anbindung an Ollama via Server-Sent Events.
"""
from __future__ import annotations
import json
import logging
import time
from typing import AsyncGenerator

import httpx

from config import OLLAMA_URL, MODEL_NAME, LLM_NUM_CTX, LLM_TEMPERATURE, LLM_NUM_GPU

log = logging.getLogger(__name__)

FALLBACK_MODELS = [MODEL_NAME, "mistral:7b", "qwen3:8b", "llama3.1:8b"]


async def check_ollama() -> dict:
    """Prüft ob Ollama erreichbar ist und welche Modelle verfügbar sind."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "models": models, "url": OLLAMA_URL}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": OLLAMA_URL}


async def _resolve_model() -> str:
    """Gibt das erste verfügbare Modell aus der Fallback-Kette zurück."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            available = [m["name"] for m in r.json().get("models", [])]
            for candidate in FALLBACK_MODELS:
                if any(candidate in a for a in available):
                    if candidate != MODEL_NAME:
                        log.warning("Modell-Fallback: %s → %s", MODEL_NAME, candidate)
                    return candidate
    except Exception:
        pass
    return MODEL_NAME


def _build_prompt(user_prompt: str, system_prompt: str, documents: list[str]) -> str:
    """Setzt Kontext, System-Prompt und Nutzerprompt zusammen."""
    parts = []
    if documents:
        # Kontextfenster-Schätzung: max. 8000 Tokens ≈ 32.000 Zeichen
        combined = "\n\n---\n\n".join(documents)
        if len(combined) > 32_000:
            combined = combined[:32_000]
            log.warning("Kontext auf 32.000 Zeichen gekürzt.")
        parts.append(f"[DOKUMENTE]\n{combined}\n[/DOKUMENTE]")
    parts.append(user_prompt)
    return "\n\n".join(parts)


async def stream(
    user_prompt: str,
    system_prompt: str,
    documents: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streamt eine LLM-Antwort als Server-Sent-Events.

    Yields:
        SSE-Zeilen: 'data: {"token": "...", "done": false}\\n\\n'
        Abschluss:  'data: {"done": true, "token_count": N, "model": "..."}\\n\\n'
        Fehler:     'data: {"error": "...", "done": true}\\n\\n'
    """
    model = await _resolve_model()
    full_prompt = _build_prompt(user_prompt, system_prompt, documents or [])
    token_count = 0
    t_start = time.monotonic()

    payload = {
        "model": model,
        "prompt": full_prompt,
        "system": system_prompt,
        "stream": True,
        "think": False,          # Qwen3 Thinking-Modus deaktivieren
        "options": {"temperature": LLM_TEMPERATURE, "num_ctx": LLM_NUM_CTX, "num_gpu": LLM_NUM_GPU},
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=300)) as client:
                async with client.stream("POST", f"{OLLAMA_URL}/api/generate",
                                         json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            token_count += 1
                            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                        if data.get("done"):
                            elapsed = round(time.monotonic() - t_start, 1)
                            tok_per_s = round(token_count / elapsed, 1) if elapsed > 0 else 0
                            done_data = json.dumps({
                                'done': True, 'token_count': token_count,
                                'model': model, 'elapsed_s': elapsed, 'tok_per_s': tok_per_s,
                            })
                            yield f"data: {done_data}\n\n"
                            return
            return  # Erfolg
        except httpx.TimeoutException:
            if attempt < 2:
                log.warning("Ollama Timeout — Versuch %d/3", attempt + 1)
                continue
            yield f"data: {json.dumps({'error': 'timeout', 'done': True})}\n\n"
            return
        except Exception as e:
            if attempt < 2:
                wait = [1, 3][attempt]
                log.warning("Ollama Fehler (%s) — Retry in %ds", e, wait)
                import asyncio
                await asyncio.sleep(wait)
                continue
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
            return
