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
    LLM_MAX_TOKENS_DEFAULT,
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


def _should_use_gateway(backend_override: str | None = None) -> bool:
    if not backend_override:
        return _use_gateway()
    return backend_override.lower() not in {"ollama", "local"}


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


def _prepend_no_think(system_prompt: str, model: str) -> str:
    """Verhindert bei qwen3 unnötige Reasoning-Prefill-Zeit über den Gateway."""
    if "qwen3" not in model.lower():
        return system_prompt
    if system_prompt.lstrip().startswith("/no_think"):
        return system_prompt
    return f"/no_think\n{system_prompt}"


def _strip_think_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def _sanitize_stream_token(
    token: str,
    think_state: dict[str, object],
) -> str:
    if not token:
        return ""

    buffer = str(think_state.get("buffer", "")) + token
    in_think = bool(think_state.get("in_think", False))
    visible_parts: list[str] = []

    while buffer:
        if in_think:
            end_idx = buffer.find("</think>")
            if end_idx == -1:
                buffer = buffer[-8:]
                break
            buffer = buffer[end_idx + len("</think>"):]
            in_think = False
            continue

        start_idx = buffer.find("<think>")
        if start_idx == -1:
            partial_idx = buffer.rfind("<")
            if partial_idx != -1 and "<think>".startswith(buffer[partial_idx:]):
                visible_parts.append(buffer[:partial_idx])
                buffer = buffer[partial_idx:]
            else:
                visible_parts.append(buffer)
                buffer = ""
            break

        visible_parts.append(buffer[:start_idx])
        buffer = buffer[start_idx + len("<think>"):]
        in_think = True

    think_state["buffer"] = buffer
    think_state["in_think"] = in_think
    return "".join(visible_parts)


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


async def warmup_gateway_model() -> None:
    """Laedt das konfigurierte Gateway-Modell vor, damit der erste Nutzerrequest nicht kalt startet."""
    if not _use_gateway():
        return

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": _prepend_no_think("Antworte kurz auf Deutsch.", MODEL_NAME)},
            {"role": "user", "content": "Antworte nur mit OK."},
        ],
        "stream": False,
        "max_tokens": 8,
        "temperature": 0,
        "workload_type": EGPU_WORKLOAD_TYPE,
    }

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=90)) as client:
            resp = await client.post(
                f"{EGPU_GATEWAY_URL}/api/llm/chat/completions",
                json=payload,
                headers={"X-App-Id": EGPU_GATEWAY_APP_ID},
            )
            resp.raise_for_status()
        log.info(
            "Gateway-Warmup fuer %s erfolgreich in %.1fs.",
            MODEL_NAME,
            time.monotonic() - started,
        )
    except Exception as exc:
        log.warning("Gateway-Warmup fuer %s fehlgeschlagen: %s", MODEL_NAME, exc)


async def _resolve_model(
    preferred_model: str | None = None,
    backend_override: str | None = None,
) -> str:
    """Gibt das erste verfuegbare Modell zurueck."""
    if _should_use_gateway(backend_override):
        return preferred_model or MODEL_NAME

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            available = [m["name"] for m in r.json().get("models", [])]
            candidates = []
            if preferred_model:
                candidates.append(preferred_model)
            candidates.extend(candidate for candidate in FALLBACK_MODELS if candidate != preferred_model)
            for candidate in candidates:
                if any(candidate in a for a in available):
                    if candidate != (preferred_model or MODEL_NAME):
                        log.warning(
                            "Modell-Fallback: %s -> %s",
                            preferred_model or MODEL_NAME,
                            candidate,
                        )
                    return candidate
    except Exception:
        pass
    return preferred_model or MODEL_NAME


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
    max_tokens: int | None = None,
    model_override: str | None = None,
) -> AsyncGenerator[str, None]:
    """Echtes Streaming ueber den egpu-manager LLM Gateway.

    Sendet stream=True an den Gateway, der die Upstream-SSE 1:1 durchreicht.
    Jeder OpenAI-Chunk wird sofort als Workshop-SSE-Event weitergegeben.
    Reasoning-Chunks halten den Stream per Status-Event aktiv, werden aber
    nicht als Antworttext an das UI weitergereicht.
    """
    model = await _resolve_model(model_override, backend_override="gateway")
    full_prompt = _build_prompt(user_prompt, system_prompt, documents)
    t_start = time.monotonic()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _prepend_no_think(system_prompt, model)},
            {"role": "user", "content": full_prompt},
        ],
        "stream": True,
        "max_tokens": max_tokens or LLM_MAX_TOKENS_DEFAULT,
        "temperature": LLM_TEMPERATURE,
        "think": False,
        "workload_type": EGPU_WORKLOAD_TYPE,
    }

    token_count = 0
    model_name = model
    last_status_at = 0.0
    saw_content = False
    think_state: dict[str, object] = {"buffer": "", "in_think": False}

    async def _fallback_non_streaming_answer() -> tuple[str, int | None, str]:
        non_stream_payload = {**payload, "stream": False}
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=300)) as client:
            resp = await client.post(
                f"{EGPU_GATEWAY_URL}/api/llm/chat/completions",
                json=non_stream_payload,
                headers={"X-App-Id": EGPU_GATEWAY_APP_ID},
            )
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(
                    f"Gateway HTTP {resp.status_code}: {body.decode(errors='replace')}"
                )
            data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return (
            _strip_think_tags(message.get("content") or ""),
            usage.get("completion_tokens"),
            data.get("model") or model_name,
        )

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=300)) as client:
                async with client.stream(
                    "POST",
                    f"{EGPU_GATEWAY_URL}/api/llm/chat/completions",
                    json=payload,
                    headers={"X-App-Id": EGPU_GATEWAY_APP_ID},
                ) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        raise RuntimeError(
                            f"Gateway HTTP {resp.status_code}: {body.decode(errors='replace')}"
                        )

                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()  # "data: ..." oder "data:..."
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        model_name = chunk.get("model", model_name)

                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            token = _sanitize_stream_token(delta.get("content") or "", think_state)
                            reasoning = (
                                delta.get("reasoning_content")
                                or delta.get("reasoning")
                                or ""
                            )
                            if token:
                                saw_content = True
                                token_count += 1
                                yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                            elif reasoning:
                                now = time.monotonic()
                                if now - last_status_at >= 2.5:
                                    last_status_at = now
                                    yield "data: {\"type\":\"status\",\"state\":\"thinking\"}\n\n"

                            # Token-Count aus usage im letzten Chunk uebernehmen
                            if choice.get("finish_reason"):
                                usage = chunk.get("usage") or {}
                                if usage.get("completion_tokens"):
                                    token_count = int(usage["completion_tokens"])

                if not saw_content:
                    fallback_text, fallback_completion_tokens, fallback_model_name = await _fallback_non_streaming_answer()
                    if fallback_text:
                        model_name = fallback_model_name or model_name
                        fallback_chunks = _chunk_text(fallback_text)
                        for chunk in fallback_chunks:
                            token_count += 1
                            yield f"data: {json.dumps({'token': chunk, 'done': False})}\n\n"
                        if fallback_completion_tokens:
                            token_count = int(fallback_completion_tokens)

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
    max_tokens: int | None = None,
    backend_override: str | None = None,
    model_override: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streamt eine LLM-Antwort als Server-Sent-Events.

    Yields:
        SSE-Zeilen: 'data: {"token": "...", "done": false}\\n\\n'
        Abschluss:  'data: {"done": true, "token_count": N, "model": "..."}\\n\\n'
        Fehler:     'data: {"error": "...", "done": true}\\n\\n'
    """
    if _should_use_gateway(backend_override):
        async for chunk in _stream_via_gateway(
            user_prompt,
            system_prompt,
            documents or [],
            max_tokens=max_tokens,
            model_override=model_override,
        ):
            yield chunk
        return

    model = await _resolve_model(model_override, backend_override="ollama")
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
            "num_predict": max_tokens or LLM_MAX_TOKENS_DEFAULT,
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
