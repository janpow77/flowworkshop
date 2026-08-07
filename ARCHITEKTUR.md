# Architektur — Workshop

_Automatisch generiert von graphify-kira aus dem Code-Graphen. Nicht von Hand editieren — wird beim nächsten Lauf überschrieben._

**Umfang:** 5089 Knoten, 11934 Kanten, 20 größere Module, 1 zirkuläre Abhängigkeiten.

## Modulkarte

- **Community 0** (120): `AnswerSetManager.tsx`, `CategoryManager.tsx`, `NodeDiscussion.tsx`, `RefDocsPanel.tsx`, `Breadcrumb.tsx`
- **Community 1** (96): `state_aid.py`, `sanctions_service.py`, `state_aid_audit_report.py`, `state_aid_harvester.py`, `test_audit_report_polish_v3.py`
- **Community 2** (88): `entities.py`, `rebuild_entity_resolution.py`, `entity_resolution.py`, `test_entity_resolution.py`
- **Community 3** (87): `audit_log.py`, `registration.py`, `session.py`, `auth.py`
- **Community 4** (87): `BeneficiaryAnalyticsPanel.tsx`, `BeneficiaryCompanySearch.tsx`, `BeneficiaryMap.tsx`, `BeneficiaryWorkspace.tsx`, `api.ts`
- **Community 5** (81): `HelpPanel.tsx`, `NodeContextMenu.tsx`, `PresenceBar.tsx`, `ResizeHandle.tsx`, `TreeEditor.tsx`
- **Community 6** (79): `state_aid_audit_map.py`, `state_aid_audit_pdf.py`, `test_corporate_registry.py`
- **Community 7** (77): `state_aid_llm.py`, `test_state_aid_llm.py`
- **Community 8** (73): `beneficiaries.py`, `country_profiles.py`, `dataframe_service.py`, `geocoding_service.py`
- **Community 9** (73): `event.py`
- **Community 10** (67): `audit_match_verifier.py`, `test_audit_match_verifier.py`
- **Community 11** (67): `architecture.py`, `http_probe.py`, `ports.py`, `tls.py`, `version_cve.py`
- **Community 12** (66): `checklist_template.py`, `checklist_versions.py`
- **Community 13** (65): `state_aid.py`, `excel_export.py`
- **Community 14** (62): `state_aid.py`, `harvest_state_aid.py`, `state_aid_harvester.py`, `test_state_aid_smart_mode.py`
- **Community 15** (61): `AdminMailTemplatesPanel.tsx`, `AdminUsersPanel.tsx`, `PhaseTogglePanel.tsx`, `api.ts`, `stateAidApi.ts`
- **Community 16** (59): `AnswerSetManager.tsx`, `CategoryManager.tsx`, `DiffView.tsx`, `HistoryPanel.tsx`, `NodeInspector.tsx`
- **Community 17** (54): `entities.py`, `entity_embeddings.py`, `entity_match_llm_run.py`, `entity_match_llm_batch.py`, `entity_match_llm_verifier.py`
- **Community 19** (53): `AuditCrossReferences.tsx`, `AuditReportPreview.tsx`, `stateAidApi.ts`
- **Community 18** (53): `checklist_package.py`, `checklist_package_service.py`, `Exception`, `test_checklist_package_unit.py`

## Zentrale Bausteine (God Nodes)

_Hohe Zentralität ist nicht automatisch ein Defekt (zentrale Stores/Modelle sind oft legitim). Konkrete Refactoring-Prioritäten siehe Optimierungs-Report._

- `BaseModel` — Grad 127 (ein 127/aus 0)
- `_Base (auditworkshop/backend/cockpit_common/migration.py)` — Grad 70 (ein 69/aus 1)
- `api.ts (auditworkshop/frontend/src/lib/api.ts)` — Grad 263 (ein 56/aus 207)
- `Registration (auditworkshop/backend/models/registration.py)` — Grad 164 (ein 163/aus 1)
- `ChecklistTemplate (auditworkshop/backend/models/checklist_template.py)` — Grad 113 (ein 112/aus 1)
- `MemberRole (auditworkshop/backend/models/checklist_template.py)` — Grad 115 (ein 114/aus 1)
- `TemplateStatus (auditworkshop/backend/models/checklist_template.py)` — Grad 111 (ein 110/aus 1)
- `ChecklistTemplateNode (auditworkshop/backend/models/checklist_template.py)` — Grad 107 (ein 106/aus 1)
- `request() (auditworkshop/frontend/src/lib/api.ts)` — Grad 92 (ein 89/aus 3)
- `ChecklistMember (auditworkshop/backend/models/checklist_template.py)` — Grad 102 (ein 101/aus 1)

## Schnittstellen / Brücken (Betweenness)

- `auth.py (auditworkshop/backend/routers/auth.py)` — Betweenness 0.001
- `api.ts (auditworkshop/frontend/src/lib/api.ts)` — Betweenness 0.000
- `state_aid_audit_pdf.py (auditworkshop/backend/services/state_aid_audit_pdf.py)` — Betweenness 0.000
- `state_aid_audit_report.py (auditworkshop/backend/services/state_aid_audit_report.py)` — Betweenness 0.000
- `checklist_discussion.py (auditworkshop/backend/routers/checklist_discussion.py)` — Betweenness 0.000
- `routers/security_scan.py (auditworkshop/backend/routers/security_scan.py)` — Betweenness 0.000
- `get_multi_service() (auditworkshop/backend/services/sanctions_service.py)` — Betweenness 0.000
- `MultiSanctionsService (auditworkshop/backend/services/sanctions_service.py)` — Betweenness 0.000
- `SanctionsListIndex (auditworkshop/backend/services/sanctions_service.py)` — Betweenness 0.000
- `FastAPI (auditworkshop/backend/main.py)` — Betweenness 0.000

## Zirkuläre Abhängigkeiten

Es gibt **1** nicht-triviale Zyklen (starke Zusammenhangskomponenten) — Kandidaten zum Auflösen (Dependency-Inversion).

## Empfohlene Spezialisten

Passend zu Stack/Domäne dieses Projekts (Claude-Code-Agents/Skills):

`/deutsche-formulierung`, `@git-workflow`, `/auto-verify`, `/workshop-trainer`, `@alembic-migrator`, `/db-migration-helper`, `@e2e-browser-tester`, `/modern-gui-builder`, `/ux-completeness-check`, `@memory-bridge`, `/rag-knowledge-base`.

## Hinweis für Änderungen

Vor dem Ändern eines zentralen Bausteins die Abhängigen prüfen — am schnellsten über den **graphify-MCP** (globaler Graph): „Was hängt an `<datei>`?". Brücken-Knoten stabil halten.

