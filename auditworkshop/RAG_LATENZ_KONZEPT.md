# Konzept: Schnellere KB-Recherche-Generierung

## Befund (gemessen)

- Modell **qwen3:14b** ist auf der evo-x2 dauerwarm; am ai-router liefert es mit
  `reasoning_effort:"none"` bei kurzem Prompt das **erste Token in ~0,2 s**.
- Über `POST /api/knowledge/generate` dauert das erste Token aber **~30–60 s**.
- Ursache ist **nicht** Kaltstart oder Reasoning, sondern die **Kontextgröße**:
  `KB_RESEARCH_TOP_K = 6` Fundstellen werden mit dem **vollständigen Chunk-Text**
  in den Prompt gegeben. Chunkgröße: `CHUNK_WORDS = 700` Wörter, Ø **5.407**,
  max **6.270 Zeichen** je Chunk.
  → Kontext ≈ 6 × 5.407 ≈ **32.000 Zeichen ≈ ~8.000 Token**. Das Prefill dieser
  Tokenmenge auf 14b ist die Wartezeit bis zum ersten Token.

Beleg im Code (`routers/knowledge.py`):
```python
documents = [
    f"[{h['source']} · Abschnitt {h['chunk_index'] + 1}]\n{h['text']}"  # voller Chunk
    for h in hits  # hits = top_k = 6
]
```

**Ziel:** Zeit bis erstes Token < ~5 s, ohne Qualitätsverlust bei den Belegen.

---

## Stufe 1 — Sofort (kein Re-Ingest, kein System-Prompt-Eingriff)

Größter Hebel bei kleinstem Aufwand/Risiko.

1. **`top_k` für die Generierung senken:** 6 → **4**
   (`KB_RESEARCH_TOP_K`, per ENV/Config). Die Suche-Anzeige bleibt unberührt.
2. **Kontext pro Chunk fokussieren:** statt des vollen 5.407-Zeichen-Chunks ein
   **Fenster um die Trefferstelle** (~1.200–1.500 Zeichen) in `documents` geben —
   analog zur bestehenden Snippet-Logik der Suche (dort 280 Zeichen), nur etwas
   großzügiger fürs LLM. Reine Code-Änderung in `knowledge.py` (neue Funktion
   `_focus_window(text, query, chars=1400)`), keine DB-Änderung.

**Wirkung (Schätzung):** Kontext von ~8.000 → **~1.500–2.000 Token**
→ Zeit bis erstes Token von ~40 s auf **~5–10 s** (3–6×). Qualität bleibt, da die
relevante Passage erhalten bleibt; die volle Fundstelle ist weiterhin über die
Quellen-Anzeige (Snippet + Abschnittsnummer) nachvollziehbar.

---

## Stufe 2 — Mittel (Qualität bei kleinem Kontext, kein Re-Ingest)

3. **Reranking nutzen.** Der ai-router hat bereits einen `reranker-service`
   (BGE-Reranker-v2-m3, Capability `rerank`). Ablauf: grob **top_k = 12–15**
   per Vektorsuche holen → per Reranker auf die **besten 3–4** sortieren →
   nur diese (fokussiert, Stufe 1) in den Kontext.
   → Bessere Trefferpräzision trotz kleinem Kontext; gleicht das niedrigere
   `top_k` aus. Aufwand: rerank-Aufruf in `knowledge_service.search()` ergänzen.

---

## Stufe 3 — Größer (Re-Ingest aller Quellen)

4. **Feineres Chunking:** `CHUNK_WORDS` 700 → **300**, `CHUNK_OVERLAP` 150 → **60**.
   - Vorteil: präzisere Treffer, kürzerer Kontext, bessere Snippets, weniger
     „Themen-Vermischung" je Chunk.
   - Aufwand: **alle Quellen neu chunken + neu einbetten** (~700 Chunks →
     mehrere Hundert kleinere). Skriptbasiert machbar (vgl.
     `scripts/reingest_vo1060_eurlex.py`), Laufzeit überschaubar.
   - Optional kombinierbar mit erneutem EUR-Lex-/Quellimport.

---

## Querschnitt — wahrgenommene Wartezeit (Frontend)

5. **Status-Anzeige** in `KbResearchPage`: Der Stream sendet bereits
   `{"type":"status","state":"thinking"}`-Events. Statt eines stummen Spinners
   einen sichtbaren Hinweis zeigen: „Suche Fundstellen … / Formuliere Antwort …".
   Senkt die *gefühlte* Wartezeit, unabhängig von der echten Latenz.

---

## Empfehlung & Reihenfolge

1. **Stufe 1 sofort umsetzen** (top_k 4 + Kontext-Fokus 1.400 Zeichen) und an
   3 Beispielfragen messen.
2. Falls die Trefferqualität durch top_k=4 leidet: **Stufe 2 (Reranking)**.
3. **Stufe 3 (feineres Chunking)** nur, wenn nach 1+2 noch Bedarf besteht —
   höchster Aufwand, aber beste Retrieval-Qualität langfristig.
4. **Stufe 5 (Status-UI)** als kleines Begleit-Polish jederzeit.

## Mess-/Abnahmekriterien

Je Beispielfrage vor/nach messen:
- Zeit bis **erstes Token** (Ziel < 5 s),
- **Gesamtzeit** bis Antwortende,
- **Qualität**: stimmen die zitierten Fundstellen, ist die Antwort belegbasiert?

Beispiel-Fragen: „Anforderungen an die Verwaltungsprüfung nach Artikel 74",
„Pflichten bei vereinfachten Kostenoptionen", „Was ist das Besserstellungsverbot?".

## Rückbau

Alle Stufe-1/2-Änderungen sind reine Retrieval-/Kontext-Parameter — per ENV bzw.
kleinem Code-Diff reversibel; System-Prompts bleiben unangetastet.
