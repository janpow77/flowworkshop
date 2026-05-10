# Migrations-Sitzungs-Log — auditworkshop

Laufendes Log der Workshop-Migration. Format pro Eintrag laut Master-
Dokument Abschnitt 12. Einträge werden später in den Cockpit-Tracker
übernommen, sobald dieser läuft.

## Beobachtungen für Plan-Anpassung

Sammlung von Punkten, die in einer separaten Konversation in das
Master-Dokument oder die vier Plan-Dokumente einfließen sollen. Keine
unmittelbare Änderung der Plan-Dokumente.

1. **Parallelisierung der Phasen 0–5.** Der Eigentümer hebt die strikte
   Sequenzierung des Master-Dokuments (Abschnitt 4) auf und baut
   Tracker, CCX23-Grundlage, Cockpit-Foundations und Workshop-
   Migration parallel. Master-Dokument sollte einen optionalen
   Parallelisierungs-Pfad als zweite Variante neben der sequenziellen
   Standard-Reihenfolge dokumentieren.

2. **Hub auf CCX23 statt NUC.** Eigentümer-Entscheidung verlegt
   `egpu-manager-hub` und `llm-router` in den Docker-Stack auf CCX23.
   GPU_LLM_PREPARATION.md sollte diese Topologie-Variante als
   gleichwertige Alternative zur NUC-Hub-Variante dokumentieren,
   inkl. Trade-off-Tabelle (zentrale Steuerung vs. Latenz-Aufschlag).

3. **Desktop als GPU-Host.** Master-Dokument Abschnitt 1 listet den
   Desktop-PC nur als Konfigurations-/Build-Host und möglichen Host
   für private Workloads. Der Eigentümer nutzt den Desktop mit
   RTX 5070 und RTX 5060 zusätzlich als GPU-Spoke für
   `egpu-manager`. Master-Dokument und GPU_LLM_PREPARATION.md sollten
   den Desktop als optionalen dritten GPU-Host aufnehmen, mit zwei
   GPU-Slots.

4. **Geocode-Cache-Größe in Workshop-CLAUDE.md.** Die
   `auditworkshop/CLAUDE.md` und `flowworkshop/CLAUDE.md` (Workshop-
   Constraints) erwähnen 5.200+ Geocode-Einträge. Tatsächlich liegen
   im Repository **3.177 Einträge**. Korrektur sollte beim nächsten
   CLAUDE.md-Update einfließen.

5. **Embedding-Modell-Inkonsistenz in Workshop-CLAUDE.md.** Workshop-
   CLAUDE.md nennt `paraphrase-multilingual-mpnet-base-v2` (768 Dim.).
   Compose-ENV setzt `bge-m3` (1024 Dim.) — letzteres ist zur
   Laufzeit aktiv. Workshop-CLAUDE.md sollte beim nächsten Update
   bge-m3 als aktuelles Modell ausweisen.

6. **JSON-Logging-Formatter als Cockpit-internes Paket.** Im
   Workshop-Workstream wird der JSON-Formatter projekt-lokal
   eingerichtet. Sobald die zweite Anwendung (audit_designer in
   Phase 6) migriert wird, sollte der Formatter inklusive Request-ID-
   Middleware in ein internes Python-Paket extrahiert werden
   (`cockpit-logging` o.ä.).

7. **Rust für neue Komponenten.** Eigentümer-Wunsch: wo möglich Rust.
   Workshop-Backend bleibt Python/FastAPI (zu hoher Risiko/Nutzen-
   Faktor für Umschreibung). Rust ist sinnvoll und vorgesehen für:
   Cockpit-Realtime (Workstream C), `llm-router` (Workstream E) und
   `egpu-manager-hub` (Workstream E). Lifecycle-Hooks bleiben Bash,
   GitHub-Workflows YAML.

## Sitzungs-Einträge

### YYYY-MM-DD: Phase 5 / Workstream D — Repository-Konventionen

(Erster Eintrag wird beim Abschluss von Workstream D gesetzt. Erwartetes
Format:)

```
- Dauer: <Stunden>
- Behandelte Aufgaben: Inventur, migration-plan, compose.yaml, lifecycle/,
  caddy/, backup.yaml, GitHub-Workflows, Health-Endpoint, JSON-Logging.
- Resultat: Workshop-Repository erfüllt die Cockpit-Konventionen aus
  Master-Dokument Abschnitt 7.
- Nächster Schritt: Workstreams A, B, C, E starten, sobald
  Hetzner-Zugangsdaten verfügbar sind. Stufe 8.2 (Daten-Snapshot)
  sobald S1, S2, S3 erreicht sind.
- Offene Punkte: Quell-Host und Pfad final bestätigen; produktive
  Workshop-URL festlegen; Tracker-Tresor-IDs für Geheimnisse vergeben.
- Beobachtungen für Plan-Anpassung: siehe oben Abschnitt
  „Beobachtungen für Plan-Anpassung".
```
