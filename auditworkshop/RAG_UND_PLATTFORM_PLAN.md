# Gesamtplan: Standard-RAG + Plattform verbessern

> **Geltungsbereich:** Die RAG (pgvector + bge-m3 + ai-router) ist die **Standard-
> Pipeline für alle Projekte** (audit_designer, flowinvoice, krypto, auditworkshop).
> Alle RAG-Änderungen werden daher **zentral, konfigurierbar (ENV/Config), rückwärts-
> kompatibel und messbar** umgesetzt — nicht projektlokal geforkt.

## Leitprinzipien
- **Messen vor/nach** jeder Änderung (gleiche Fragen, beide Modi).
- **Konfigurierbar** statt hartkodiert (top_k, Kontextlänge, Reranking an/aus, Modell).
- **Keine System-Prompt-Änderung** ohne Absprache (Workshop-kritisch).
- **Idempotente, per-Quelle Re-Ingest-Skripte** (kein Voll-Reset).

---

## A · RAG-Performance (Latenz)  — P0

Ist (gemessen): qwen3:14b warm, Router-Direktcall 0,2 s; über `/generate` aber
30–60 s, weil 6 volle Chunks (Ø ~5.300 Zeichen) ≈ ~8.000 Token Prefill.

1. **Kontext-Fokus (größter Hebel, kein Re-Ingest):** statt vollem Chunk ein
   **Fenster ~1.400 Zeichen** um die Trefferstelle in `documents`. Neue Funktion
   `_focus_window(text, query)`. → Kontext ~8.000 → ~1.500–2.000 Token.
2. **`KB_RESEARCH_TOP_K` 6 → 4** (ENV).
3. **Reranking** (Router hat `reranker-service`, BGE-Reranker-v2-m3): grob top_k
   12–15 holen → auf beste 3–4 reranken → fokussiert in den Kontext. Gleicht
   kleineres top_k qualitativ aus. Zentral in `knowledge_service.search()`.
4. **Status-UI** in `KbResearchPage`: vorhandene SSE-`status`-Events anzeigen
   („Suche Fundstellen … / Formuliere Antwort …") statt stummem Spinner.
- Ziel: erstes Token < 5 s.

## B · RAG-Qualität (Retrieval)  — P1

5. **Feineres Chunking als Standard:** `CHUNK_WORDS` 700 → ~300, Overlap 150 → 60.
   Präzisere Treffer, kürzerer Kontext, bessere Snippets. **Erfordert Re-Ingest
   aller Quellen** (alle Projekte!) → zentral, versioniert ausrollen.
6. **Hybrid-Retrieval ausbauen:** Vektor + bestehendes `_keyword_search` /
   `_article_search` (Artikel-Erkennung) sauber fusionieren (Reciprocal Rank
   Fusion) statt „erstes Match gewinnt".
7. **Contextual Retrieval / HyDE** (optional, projektweit testbar): Chunk-Präfix
   mit Kurzkontext beim Ingest bzw. hypothetische Antwort als Query-Expansion.
8. **Metadaten** je Chunk anreichern: Artikel-/Abschnittsnummer, Dokumenttyp,
   Förderperiode → gezielte Filter + bessere Quellenanzeige.
9. **Eval-Harness (Pflicht für „Standard-RAG"):** Set aus ~20–30 QA-Paaren je
   Domäne, automatisierte **Recall@k / Antwort-Treffer**-Messung als Skript;
   Vorher/Nachher bei jeder B-Änderung. (Vgl. Skill `rag-knowledge-base`.)

## C · Wissensbasis-Inhalt & Ingest-Robustheit  — P1

10. **Parser-Fix (Ursache des Rückwärts-Bugs):** pdfplumber lieferte bei
    VO 2021/1060 zeichen-reversierte Seiten. → Ingest-Pipeline: **PyMuPDF als
    primärer Extraktor** bzw. **Reversal-Detektor** (deutscher Stoppwort-Score)
    als Guard, der reversierte Extraktion ablehnt/korrigiert. Verhindert das
    Problem projektweit dauerhaft. (Repair-Skript existiert bereits.)
11. **Saubere Quellen bevorzugen:** EUR-Lex-Konsolidierungsfassungen (HTML) statt
    PDF, wo verfügbar (1060 erledigt; 1058/1059/Beihilfe-VOs nachziehen).
    Browser-Fetch wegen AWS-WAF (Playwright) als dokumentierter Weg.
12. **Ingest-CLI vereinheitlichen:** ein idempotenter Befehl je Quelle
    (`delete_source` + `ingest`), Quellenregister mit Stand/Datum.

## D · LLM-Generierung  — P0 (Kern erledigt)

13. ✅ Generierung auf **qwen3:14b + `reasoning_effort:"none"`** (kein Timeout mehr).
14. ✅ **14b dauerwarm** auf evo-x2 (per `/api/ps` bestätigt).
15. Token-Budgets `_LENGTH_TOKENS` an reale Antwortlängen feinjustieren.
16. **Abstention** (keine Belege → keine Aussage) ist vorhanden — beibehalten/testen.

## E · ai-router / Infrastruktur  — P1

17. ✅ **Anfrage-Limit** `auditworkshop` 120/6 → **600/32**.
18. Limits/Keep-Warm-Policy **für alle Consumer** prüfen (audit_designer etc.),
    die dieselbe RAG nutzen.
19. **Reranker im Router** als Standard-Capability in die Pipeline einbinden (B-3).
20. **Metriken/Monitoring** (Router hat `metrics.db`): Latenz p50/p95 je Consumer,
    429-Rate, Spoke-Auslastung sichtbar machen.

## F · Checklisten-Designer  — P1

21. ✅ Editor-Politur: Sidebar weg, 50/50 verschiebbar, Page-Scroll, „+"-Menü,
    Anleitung, Export im Header, Übersicht-Ansichten, Umbenennung, Label-Fix.
22. **Neue Checklisten** (recherchiert, priorisiert): zuerst **Vergabe,
    Beihilfen, Vorhabenprüfung/Belegprüfung (Art. 79)**; dann KA1/KA3/KA6;
    danach Publizität, DNSH, Querschnittsziele, Rechnungslegung. Als
    Seed-Vorlagen/Gerüste anlegen.
23. **Mobile & Barrierefreiheit** des Editors (Tastatur, ARIA, Fokus) prüfen.

## G · Frontend/UX  — P2

24. Generierungs-/Lade-Status durchgängig (B-4), Fehlerzustände einheitlich.
25. Landing/Login (erledigt: gated Tiles, Recherche inline, Icon-Fix) — Konsistenz-Pass.

## H · Robustheit & Tests  — P1 (offener Punkt!)

26. **E2E-Tests fehlen komplett** (dokumentierter offener Punkt): Playwright-Smoke
    für Login → Landing → Checklisten → Recherche → Export.
27. **RAG-Eval als CI-Schritt** (B-9) — verhindert stille Qualitätsregression.
28. ✅ Session-Self-Heal bei 401 (Token stale → Re-Login) vorhanden.
29. Backend-Smoke (`workshop_smoke.sh`) nach jeder Backend-Änderung — beibehalten.

## I · Deployment & Prozess  — P1

30. **Commit** des Branches `feat/checklist-designer` (Frontend-Umbau, RAG-Repair-
    Skripte, EUR-Lex-Reingest, config 14b) — derzeit alles uncommittet.
31. **ai-router-Config** (Limits) in Prod (CCX23) nachziehen, nicht nur NUC.
32. **Backend-Image neu bauen** beim Deploy (nicht nur `restart`) — sonst greifen
    Codeänderungen wie `reasoning_effort` nicht.
33. **memory-bridge / Kira-RAG-Sync**: Architektur-Entscheidungen dieser Session
    (14b-Umstellung, Reversal-Fix-Mechanismus, Standard-RAG-Parameter) ablegen.

---

## Empfohlene Reihenfolge

1. **P0 sofort:** A-1/A-2 (Fokus-Fenster + top_k=4) → messen (beide Modi, 3 Fragen).
2. **P1 Qualität:** A-3 Reranking → A-4 Status-UI → B-5 feineres Chunking (zentral,
   Re-Ingest aller Projekte) → B-9 Eval-Harness.
3. **P1 Robustheit:** C-10 Parser-Guard, H-26 E2E-Tests, I-30 Commit.
4. **P2/laufend:** Inhalte (F-22), Monitoring (E-20), UX-Feinschliff.

## Messprotokoll (für jede RAG-Änderung)

Beide Modi, je 3 Fragen, vorher/nachher:
- **Fundstellensuche** (`/search`): Zeit, Trefferzahl, Top-Score, Relevanz.
- **Texterstellung** (`/generate`): Zeit bis 1. Token, Gesamtzeit, Antwortlänge,
  Beleg-Korrektheit, Abstention bei fehlenden Belegen.
- Fragen: „Verwaltungsprüfung Art. 74", „Pflichten bei VKO", „Besserstellungsverbot".
</content>
