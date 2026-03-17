---
name: frontend
description: "Automatisch aktiv bei Aenderungen an React-Frontend: Pages, Components, Routing, Styling. Triggert bei TSX/TS-Dateien in auditworkshop/frontend/src/, bei 'component', 'page', 'route', 'UI', 'Tailwind', 'dark mode'."
tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---

# Frontend Agent — React / TypeScript / Tailwind

## Fokus-Verzeichnisse
- `auditworkshop/frontend/src/pages/` — Seiten-Komponenten (14 Pages)
- `auditworkshop/frontend/src/components/layout/` — AppShell, Sidebar, TopBar
- `auditworkshop/frontend/src/components/workshop/` — PipelineWidget, LlmResponsePanel, etc.
- `auditworkshop/frontend/src/components/checklist/` — AiRemarkCard, EvidenceCard, StatusBadge
- `auditworkshop/frontend/src/App.tsx` — Routing und Auth-Gate
- `auditworkshop/frontend/src/index.css` — Tailwind-Imports

## Gesperrte Dateien (nur nach Absprache)
- `auditworkshop/frontend/package.json` — Dependency-Aenderungen bestaetigen
- `auditworkshop/frontend/vite.config.ts` — Build-Konfiguration

## Regeln
- React 19, funktionale Komponenten, Hooks (useState/useEffect)
- TypeScript strict mode
- Tailwind CSS 4 via `@tailwindcss/vite` Plugin (keine tailwind.config.js)
- Dark Mode: `dark:` Klassen, System-Preference-Detection
- Routing: `react-router-dom` v7, BrowserRouter
- Auth-Gate in App.tsx: oeffentliche Routen (Agenda, Register) vs. geschuetzte
- Icons: `lucide-react` — keine anderen Icon-Libraries
- Kein State-Management (Redux, Zustand etc.) — nur useState/useEffect
- Neue Pages muessen in `App.tsx` registriert und in der Sidebar verlinkt werden
- Design-System: Indigo (primary), Green (accepted), Red (rejected), Amber (draft), Blue (edited)

## Standard-Checks nach Aenderungen
```bash
cd auditworkshop/frontend

# TypeScript-Check
npx tsc -b

# Lint
npm run lint

# Produktions-Build
npm run build
```
