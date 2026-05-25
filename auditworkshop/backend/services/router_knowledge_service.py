"""
Router-basierter Knowledge-Service für Workshop.

Nutzt den ai-router (Port 7849) um auf die zentrale audit_designer
Wissensdatenbank (8000+ Chunks) zuzugreifen, statt lokaler pgvector-RAG.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from config import AI_ROUTER_URL, WORKSHOP_APP_ID

log = logging.getLogger(__name__)


def search(
    query: str,
    limit: int = 5,
    top_k: int | None = None,  # Alias für limit (Kompatibilität)
    enable_reranking: bool = True,
    enable_multi_query: bool = False,
) -> dict[str, Any]:
    """Suche in der Wissensdatenbank via ai-router.

    Args:
        query: Suchbegriff
        limit: Max. Anzahl Ergebnisse
        top_k: Alias für limit (Kompatibilität mit lokalem knowledge_service)
        enable_reranking: Reranking aktivieren
        enable_multi_query: Multi-Query-Expansion

    Returns:
        {
            "query": str,
            "results": [{"chunk_id", "content", "score", "source_id", ...}],
            "total_results": int,
            "processing_time_ms": float
        }
    """
    # top_k hat Vorrang wenn gesetzt (Kompatibilität)
    result_limit = top_k if top_k is not None else limit

    url = f"{AI_ROUTER_URL}/api/knowledge/search"
    payload = {
        "query": query,
        "limit": result_limit,
        "enable_reranking": enable_reranking,
        "enable_multi_query": enable_multi_query,
    }
    headers = {
        "Content-Type": "application/json",
        "X-App-Id": WORKSHOP_APP_ID,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # Mapping audit_designer-Schema auf Workshop-Schema
            # audit_designer: "content" → Workshop: "text"
            if "results" in data:
                for item in data["results"]:
                    if "content" in item and "text" not in item:
                        item["text"] = item["content"]

            log.info(
                "Knowledge-Search via Router: query=%r, results=%d, took=%dms",
                query,
                len(data.get("results", [])),
                int(data.get("processing_time_ms", 0)),
            )
            return data

    except httpx.HTTPError as exc:
        log.error("Router Knowledge-Search fehlgeschlagen: %s", exc)
        return {
            "query": query,
            "results": [],
            "total_results": 0,
            "error": str(exc),
        }


def ask(
    query: str,
    enable_compression: bool = False,
    enable_reranking: bool = True,
) -> dict[str, Any]:
    """RAG-Antwort generieren via ai-router.

    Args:
        query: Frage
        enable_compression: Context-Compression aktivieren
        enable_reranking: Reranking aktivieren

    Returns:
        {
            "answer": str,
            "sources": [{"source_id", "chunk_id", "text", "score"}],
            "took_ms": int
        }
    """
    url = f"{AI_ROUTER_URL}/api/knowledge/ask"
    payload = {
        "query": query,
        "enable_compression": enable_compression,
        "enable_reranking": enable_reranking,
    }
    headers = {
        "Content-Type": "application/json",
        "X-App-Id": WORKSHOP_APP_ID,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            log.info("Knowledge-Ask via Router: took=%dms", data.get("took_ms", 0))
            return data

    except httpx.HTTPError as exc:
        log.error("Router Knowledge-Ask fehlgeschlagen: %s", exc)
        return {
            "answer": f"Fehler beim Abrufen der Antwort: {exc}",
            "sources": [],
            "error": str(exc),
        }


def get_stats() -> dict[str, Any]:
    """Statistiken über Wissensquellen via ai-router.

    Returns:
        {
            "total_chunks": int,
            "total_sources": int,
            "enabled_sources": int,
            ...
        }
    """
    url = f"{AI_ROUTER_URL}/api/knowledge/stats"
    headers = {
        "X-App-Id": WORKSHOP_APP_ID,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPError as exc:
        log.error("Router Knowledge-Stats fehlgeschlagen: %s", exc)
        return {
            "total_chunks": 0,
            "total_sources": 0,
            "error": str(exc),
        }


# Alias für Kompatibilität mit bestehendem Code
search_knowledge = search
ask_question = ask
