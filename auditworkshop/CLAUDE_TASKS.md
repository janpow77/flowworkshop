# Next Steps for Claude Code: Stabilizing the Auditworkshop Tool

This document outlines the remaining high-priority tasks for the `auditworkshop` project. The foundational UI (Glassmorphism, Skeletons, Tailwind v4) and Core-Logics are implemented perfectly. The primary focus now shifts to **Enterprise-Grade Testing**, specifically End-to-End (E2E) UI Tests, and LLM output evaluation.

## 1. Implement Playwright (E2E Tests)
Unit tests for the frontend (`vitest`) and backend (`pytest`) exist. However, E2E tests simulating real auditor workflows are missing. 

**Tasks:**
- [ ] Initialize Playwright in the `frontend` folder (`npm init playwright@latest`).
- [ ] Configure `playwright.config.ts` to spin up the local Vite dev server (port 5173) and handle API mocking where necessary before running tests.

### Core E2E Scenarios to write:
- **Scenario A (Basic Navigation):** Verify that the Sidebar navigation works smoothly, and that all major pages (Home, Scenarios, DataFrame, Info) load without React `<ErrorBoundary>` triggering.
- **Scenario B (Checklist AI Workflow - Szenario 2):** 
  1. Navigate to a project checklist.
  2. Simulate the AI "Bewertung anfordern" (Request AI evaluation) click.
  3. Verify that the `Skeleton` loaders appear correctly during the wait.
  4. Ensure the UI updates to show the `AiRemarkCard` with the AI's proposal.
  5. Click "Übernehmen" (Accept) and verify the form values are updated.
- **Scenario C (Company Search / DataFrame - Szenario 6):** 
  1. Navigate to the `CompanySearchPage` or `DataFramePage`.
  2. Verify that the file upload drag-and-drop zone acts correctly.
  3. Verify search queries correctly trigger the loading state and display results.

## 2. CI/CD Pipeline Configuration
To prevent regressions in the UI or Backend logic during ongoing development:
- [ ] Create a `.github/workflows/test.yml` (or Gitlab equivalent).
- [ ] Add jobs for:
  - `lint`: Run `eslint .` in frontend and `ruff check .` in backend.
  - `test-unit`: Run `vitest` in frontend and `pytest` in backend.
  - `test-e2e`: Install playwright browsers, build the app, and run playwright tests.

## 3. Automated LLM Response Output Testing (Backend)
Since the application relies heavily on `Ollama` for generating contextual answers (RAG):
- [ ] Create a specific test suite `backend/tests/test_llm_quality.py`.
- [ ] Mock the LLM endpoint or use a fast local model setup to verify that standard Prompts strictly adhere to the system prompts (e.g., checking that the response uses the formal "Sie", maintains the correct tone, and blocks prompt injections).

## 4. Final UI / Accessibility Polish (Optional but recommended)
- [ ] Review `DESIGN_SYSTEM.md` and ensure all custom inputs and buttons have the documented `focus-visible:ring-2` accessible states implemented.
- [ ] Ensure 100% test coverage on `App.tsx` global error handling.

---
*Note for Claude: The UI has recently been upgraded to use premium `Skeleton` components instead of generic spinners (`Loader2`). Ensure any tests expecting `Loader2` are updated to detect the skeleton pulse elements instead.*
