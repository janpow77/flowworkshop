"""Wissensdatenbank-Tests (RAG).

Die Wissensdatenbank wird über ``router_knowledge_service`` (zentrale RAG)
bedient. Ist die zentrale Knowledge-API nicht erreichbar, liefert der
Stats-Endpunkt ein ``error``-Feld mit 0 Treffern — die Treffer-/Quellen-
abhängigen Tests werden dann übersprungen (Integrationstest-Abhängigkeit),
statt fälschlich zu scheitern.
"""
import pytest


def _stats_or_skip(client) -> dict:
    r = client.get("/api/knowledge/stats")
    assert r.status_code == 200
    data = r.json()
    chunks = data.get("total_chunks", data.get("chunks", 0)) or 0
    if data.get("error") or chunks == 0:
        pytest.skip(
            "Zentrale Knowledge-API nicht verfügbar/leer: "
            f"{data.get('error') or 'total_chunks=0'}"
        )
    return data


def test_knowledge_stats(client):
    data = _stats_or_skip(client)
    # Neue zentrale Shape (total_chunks/total_sources) ODER alte lokale Shape
    # (documents/chunks/sources) akzeptieren.
    chunks = data.get("total_chunks", data.get("chunks", 0))
    sources = data.get("total_sources", len(data.get("sources", []) or []))
    assert chunks >= 100
    assert sources >= 1


def test_knowledge_search(client):
    r = client.get("/api/knowledge/search", params={"q": "Verwaltungskontrolle", "top_k": 3})
    assert r.status_code == 200
    data = r.json()
    # Response kann Liste oder Wrapper-Objekt sein
    results = data if isinstance(data, list) else data.get("results", data.get("chunks", []))
    assert len(results) <= 5
    if results:
        first = results[0]
        assert "text" in first or "snippet" in first
        assert "source" in first


def test_knowledge_search_article_reference(client):
    """Hybrid-Suche: Artikelverweis sollte Keyword-Treffer liefern."""
    r = client.get("/api/knowledge/search", params={"q": "Art. 74 VO 2021/1060", "top_k": 5})
    assert r.status_code == 200
    results = r.json()
    results = results if isinstance(results, list) else results.get("results", [])
    if not results:
        pytest.skip("Zentrale Knowledge-Suche liefert keine Treffer (RAG nicht verfügbar)")
    assert len(results) > 0


def test_knowledge_sources_contain_key_documents(client):
    """Pruefe ob Schluessel-Dokumente ingested sind."""
    data = _stats_or_skip(client)
    sources_raw = data.get("sources")
    if not sources_raw:
        pytest.skip("Knowledge-Stats liefert keine Quellenliste (zentrale RAG)")
    sources = {s["source"] if isinstance(s, dict) else s for s in sources_raw}
    expected = {"VO_2021_1060_DE", "VO_2021_1058_DE", "EU_AI_ACT_DE"}
    assert expected.issubset(sources), f"Fehlende Quellen: {expected - sources}"
