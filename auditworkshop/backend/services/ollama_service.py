"""
flowworkshop · ollama_service.py
LLM-Anbindung fuer direktes Ollama oder den egpu-manager.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import AsyncGenerator

import httpx

from config import (
    EGPU_GATEWAY_APP_ID,
    EGPU_GATEWAY_URL,
    EGPU_WORKLOAD_TYPE,
    LLM_BACKEND,
    LLM_NUM_CTX,
    LLM_NUM_GPU,
    LLM_TEMPERATURE,
    MODEL_NAME,
    OLLAMA_URL,
)

log = logging.getLogger(__name__)

FALLBACK_MODELS = [MODEL_NAME, "mistral:7b", "qwen3:8b", "llama3.1:8b"]


def _use_gateway() -> bool:
    return LLM_BACKEND in {"egpu-manager", "egpu_manager", "gateway"}


def _chunk_text(text: str) -> list[str]:
    parts = re.findall(r"\S+\s*|\n", text)
    if not parts:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > 56 and not part.endswith("\n"):
            chunks.append(current)
            current = part
            continue
        current += part
        if part.endswith("\n"):
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)
    return chunks


async def _fetch_gateway_providers(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(f"{EGPU_GATEWAY_URL}/api/llm/providers")
    resp.raise_for_status()
    return resp.json().get("providers", [])


def _healthy_gateway_models(providers: list[dict]) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for provider in providers:
        if not provider.get("healthy"):
            continue
        for model in provider.get("models", []):
            if model and model not in seen:
                seen.add(model)
                models.append(model)
    return models


def _healthy_gateway_provider_names(providers: list[dict]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for provider in providers:
        if not provider.get("healthy"):
            continue
        name = provider.get("name") or "unknown"
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _extract_gateway_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text or f"HTTP {resp.status_code}"
    return (
        data.get("error", {}).get("message")
        or data.get("message")
        or resp.text
        or f"HTTP {resp.status_code}"
    )


async def check_ollama() -> dict:
    """Prueft ob der konfigurierte LLM-Backend erreichbar ist."""
    if _use_gateway():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                health_resp = await client.get(f"{EGPU_GATEWAY_URL}/api/llm/health")
                health_resp.raise_for_status()
                health = health_resp.json()
                providers = await _fetch_gateway_providers(client)

            healthy_models = _healthy_gateway_models(providers)
            configured_ok = MODEL_NAME in healthy_models if MODEL_NAME else bool(healthy_models)
            healthy_providers = _healthy_gateway_provider_names(providers)
            return {
                "ok": health.get("status") == "ok" and configured_ok,
                "models": [MODEL_NAME] if configured_ok else healthy_models,
                "url": EGPU_GATEWAY_URL,
                "backend": "egpu-manager",
                "app_id": EGPU_GATEWAY_APP_ID,
                "providers": healthy_providers,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "url": EGPU_GATEWAY_URL,
                "backend": "egpu-manager",
                "app_id": EGPU_GATEWAY_APP_ID,
            }

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "models": models, "url": OLLAMA_URL, "backend": "ollama"}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": OLLAMA_URL, "backend": "ollama"}


async def _resolve_model() -> str:
    """Gibt das erste verfuegbare Modell zurueck."""
    if _use_gateway():
        return MODEL_NAME

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            available = [m["name"] for m in r.json().get("models", [])]
            for candidate in FALLBACK_MODELS:
                if any(candidate in a for a in available):
                    if candidate != MODEL_NAME:
                        log.warning("Modell-Fallback: %s -> %s", MODEL_NAME, candidate)
                    return candidate
    except Exception:
        pass
    return MODEL_NAME


def _build_prompt(user_prompt: str, system_prompt: str, documents: list[str]) -> str:
    """Setzt Kontext, System-Prompt und Nutzerprompt zusammen."""
    parts = []
    if documents:
        combined = "\n\n---\n\n".join(documents)
        if len(combined) > 32_000:
            combined = combined[:32_000]
            log.warning("Kontext auf 32.000 Zeichen gekuerzt.")
        parts.append(f"[DOKUMENTE]\n{combined}\n[/DOKUMENTE]")
    parts.append(user_prompt)
    return "\n\n".join(parts)


async def _stream_via_gateway(
    user_prompt: str,
    system_prompt: str,
    documents: list[str],
) -> AsyncGenerator[str, None]:
    model = await _resolve_model()
    full_prompt = _build_prompt(user_prompt, system_prompt, documents)
    t_start = time.monotonic()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt},
        ],
        "stream": False,
        "temperature": LLM_TEMPERATURE,
        "workload_type": EGPU_WORKLOAD_TYPE,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=300)) as client:
                resp = await client.post(
                    f"{EGPU_GATEWAY_URL}/api/llm/chat/completions",
                    json=payload,
                    headers={"X-App-Id": EGPU_GATEWAY_APP_ID},
                )
                if resp.status_code >= 400:
                    raise RuntimeError(_extract_gateway_error(resp))

                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = message.get("content", "")
                if not content:
                    raise RuntimeError("Leere Gateway-Antwort")

                usage = data.get("usage") or {}
                token_count = int(
                    usage.get("completion_tokens") or len(re.findall(r"\S+", content))
                )
                model_name = data.get("model") or model

                for chunk in _chunk_text(content):
                    yield f"data: {json.dumps({'token': chunk, 'done': False})}\n\n"
                    await asyncio.sleep(0)

                elapsed = round(time.monotonic() - t_start, 1)
                tok_per_s = round(token_count / elapsed, 1) if elapsed > 0 else 0
                done_data = json.dumps(
                    {
                        "done": True,
                        "token_count": token_count,
                        "model": model_name,
                        "elapsed_s": elapsed,
                        "tok_per_s": tok_per_s,
                    }
                )
                yield f"data: {done_data}\n\n"
                return
        except httpx.TimeoutException:
            if attempt < 2:
                log.warning("Gateway Timeout - Versuch %d/3", attempt + 1)
                continue
            yield f"data: {json.dumps({'error': 'timeout', 'done': True})}\n\n"
            return
        except Exception as e:
            if attempt < 2:
                wait = [1, 3][attempt]
                log.warning("Gateway-Fehler (%s) - Retry in %ds", e, wait)
                await asyncio.sleep(wait)
                continue
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
            return


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
    if _use_gateway():
        async for chunk in _stream_via_gateway(user_prompt, system_prompt, documents or []):
            yield chunk
        return

    model = await _resolve_model()
    full_prompt = _build_prompt(user_prompt, system_prompt, documents or [])
    token_count = 0
    t_start = time.monotonic()

    payload = {
        "model": model,
        "prompt": full_prompt,
        "system": system_prompt,
        "stream": True,
        "think": False,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "num_ctx": LLM_NUM_CTX,
            "num_gpu": LLM_NUM_GPU,
        },
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=300)) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/generate",
                    json=payload,
                ) as resp:
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
                            done_data = json.dumps(
                                {
                                    "done": True,
                                    "token_count": token_count,
                                    "model": model,
                                    "elapsed_s": elapsed,
                                    "tok_per_s": tok_per_s,
                                }
                            )
                            yield f"data: {done_data}\n\n"
                            return
            return
        except httpx.TimeoutException:
            if attempt < 2:
                log.warning("Ollama Timeout - Versuch %d/3", attempt + 1)
                continue
            yield f"data: {json.dumps({'error': 'timeout', 'done': True})}\n\n"
            return
        except Exception as e:
            if attempt < 2:
                wait = [1, 3][attempt]
                log.warning("Ollama-Fehler (%s) - Retry in %ds", e, wait)
                await asyncio.sleep(wait)
                continue
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
            return
