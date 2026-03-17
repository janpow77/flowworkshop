"""Wissensdatenbank-Tests (pgvector RAG)."""


def test_knowledge_stats(client):
    r = client.get("/api/knowledge/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["documents"] >= 20
    assert data["chunks"] >= 500
    assert isinstance(data["sources"], list)


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
    assert len(results) > 0


def test_knowledge_sources_contain_key_documents(client):
    """Pruefe ob Schluessel-Dokumente ingested sind."""
    r = client.get("/api/knowledge/stats")
    sources = {s["source"] for s in r.json()["sources"]}
    expected = {"VO_2021_1060_DE", "VO_2021_1058_DE", "EU_AI_ACT_DE"}
    assert expected.issubset(sources), f"Fehlende Quellen: {expected - sources}"
