# Architektur — Workshop

_Automatisch generiert von graphify-kira aus dem Code-Graphen. Nicht von Hand editieren — wird beim nächsten Lauf überschrieben._

**Umfang:** 4823 Knoten, 11253 Kanten, 20 größere Module, 1 zirkuläre Abhängigkeiten.

## Modulkarte

- **Community 0** (147): `__init__.py`, `docs.py`, `forum.py`, `registration.py`, `event.py`
- **Community 1** (116): `AnswerSetManager.tsx`, `CategoryManager.tsx`, `EvidenceCard.tsx`, `NodeDiscussion.tsx`, `RefDocsPanel.tsx`
- **Community 2** (113): `audit_log.py`, `registration.py`, `session.py`, `auth.py`, `mail_templates.py`
- **Community 3** (90): `sanctions_entries.py`, `entities.py`, `rebuild_entity_resolution.py`, `entity_resolution.py`, `test_entity_resolution.py`
- **Community 4** (88): `entity_embeddings.py`, `embeddings.py`, `rebuild_embeddings.py`, `test_entity_embeddings.py`, `test_entity_resolution.py`
- **Community 5** (84): `state_aid_llm.py`, `test_state_aid_llm.py`
- **Community 6** (76): `audit_match_verifier.py`, `entity_match_llm_verifier.py`, `test_entity_match_llm_batch.py`
- **Community 7** (74): `automation.py`, `checklist_template.py`, `registration.py`, `checklist_export.py`, `checklist_history.py`
- **Community 8** (72): `checklist_template.py`, `checklist_discussion.py`
- **Community 9** (68): `sanctions_service.py`, `state_aid_audit_report.py`, `test_audit_report_polish_v3.py`
- **Community 10** (66): `BeneficiaryAnalyticsPanel.tsx`, `BeneficiaryCompanySearch.tsx`, `BeneficiaryMap.tsx`, `BeneficiaryWorkspace.tsx`, `api.ts`
- **Community 11** (63): `checklist_export_service.py`
- **Community 12** (62): `AnswerSetManager.tsx`, `CategoryManager.tsx`, `NodeContextMenu.tsx`, `NodeInspector.tsx`, `StatusButtons.tsx`
- **Community 13** (61): `state_aid.py`, `excel_export.py`
- **Community 14** (61): `dataframe_service.py`, `test_beneficiary_search.py`
- **Community 15** (59): `checklist_template.py`, `checklist_versions.py`
- **Community 16** (57): `backfill_state_aid_identifiers.py`, `harvest_state_aid.py`, `state_aid_harvester.py`
- **Community 17** (56): `entities.py`, `state_aid.py`, `entity_embeddings.py`, `entity_match_llm_verifier.py`, `state_aid_audit_report.py`
- **Community 18** (54): `state_aid_service.py`, `test_state_aid_search_quality.py`
- **Community 19** (50): `str`, `BaseModel`, `checklist_template.py`, `checklist_collab.py`, `checklist_history.py`

## Zentrale Bausteine (God Nodes)

_Hohe Zentralität ist nicht automatisch ein Defekt (zentrale Stores/Modelle sind oft legitim). Konkrete Refactoring-Prioritäten siehe Optimierungs-Report._

- `BaseModel` — Grad 125 (ein 125/aus 0)
- `_Base (auditworkshop/backend/cockpit_common/migration.py)` — Grad 70 (ein 69/aus 1)
- `api.ts (auditworkshop/frontend/src/lib/api.ts)` — Grad 228 (ein 52/aus 176)
- `Registration (auditworkshop/backend/models/registration.py)` — Grad 164 (ein 163/aus 1)
- `ChecklistTemplate (auditworkshop/backend/models/checklist_template.py)` — Grad 113 (ein 112/aus 1)
- `MemberRole (auditworkshop/backend/models/checklist_template.py)` — Grad 115 (ein 114/aus 1)
- `TemplateStatus (auditworkshop/backend/models/checklist_template.py)` — Grad 111 (ein 110/aus 1)
- `ChecklistTemplateNode (auditworkshop/backend/models/checklist_template.py)` — Grad 107 (ein 106/aus 1)
- `ChecklistMember (auditworkshop/backend/models/checklist_template.py)` — Grad 102 (ein 101/aus 1)
- `stateAidApi.ts (auditworkshop/frontend/src/lib/stateAidApi.ts)` — Grad 107 (ein 16/aus 91)

## Schnittstellen / Brücken (Betweenness)

- `api.ts (auditworkshop/frontend/src/lib/api.ts)` — Betweenness 0.000
- `auth.py (auditworkshop/backend/routers/auth.py)` — Betweenness 0.000
- `state_aid_audit_pdf.py (auditworkshop/backend/services/state_aid_audit_pdf.py)` — Betweenness 0.000
- `checklist_discussion.py (auditworkshop/backend/routers/checklist_discussion.py)` — Betweenness 0.000
- `MultiSanctionsService (auditworkshop/backend/services/sanctions_service.py)` — Betweenness 0.000
- `state_aid_audit_report.py (auditworkshop/backend/services/state_aid_audit_report.py)` — Betweenness 0.000
- `stateAidApi.ts (auditworkshop/frontend/src/lib/stateAidApi.ts)` — Betweenness 0.000
- `ollama_service.py (auditworkshop/backend/services/ollama_service.py)` — Betweenness 0.000
- `get_multi_service() (auditworkshop/backend/services/sanctions_service.py)` — Betweenness 0.000
- `StateAidMap.tsx (auditworkshop/frontend/src/components/state_aid/StateAidMap.tsx)` — Betweenness 0.000

## Zirkuläre Abhängigkeiten

Es gibt **1** nicht-triviale Zyklen (starke Zusammenhangskomponenten) — Kandidaten zum Auflösen (Dependency-Inversion).

## Empfohlene Spezialisten

Passend zu Stack/Domäne dieses Projekts (Claude-Code-Agents/Skills):

`/deutsche-formulierung`, `@git-workflow`, `/auto-verify`, `@alembic-migrator`, `/db-migration-helper`, `@e2e-browser-tester`, `/modern-gui-builder`, `/ux-completeness-check`, `@memory-bridge`, `/rag-knowledge-base`.

## Hinweis für Änderungen

Vor dem Ändern eines zentralen Bausteins die Abhängigen prüfen — am schnellsten über den **graphify-MCP** (globaler Graph): „Was hängt an `<datei>`?". Brücken-Knoten stabil halten.

