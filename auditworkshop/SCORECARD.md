# Auditworkshop - Qualitäts-Scorecard

**Datum:** 2026-03-19
**Projekt:** FlowWorkshop / Auditworkshop
**Stack:** React 19 + TypeScript + FastAPI + PostgreSQL + Ollama
**Zweck:** Workshop "KI und LLMs in der EFRE-Prüfbehörde"

---

## 📊 **Gesamtbewertung**

| Kategorie | Score | Gewichtung | Gewichtet |
|-----------|-------|------------|-----------|
| 🎨 **UI/UX Design** | 8.2/10 | 25% | 2.05 |
| ⚡ **Performance** | 7.5/10 | 20% | 1.50 |
| 🔒 **Security** | 6.8/10 | 15% | 1.02 |
| ♿ **Accessibility** | 5.5/10 | 15% | 0.83 |
| 🧪 **Code Quality** | 7.8/10 | 15% | 1.17 |
| 📦 **Architecture** | 8.5/10 | 10% | 0.85 |
| **GESAMT** | **7.4/10** | 100% | **7.42** |

### **Interpretation:**
- **9-10:** Excellent (Production Ready)
- **7-8.9:** Good (Minor Improvements)
- **5-6.9:** Adequate (Needs Work) ← **HIER**
- **3-4.9:** Poor (Major Issues)
- **0-2.9:** Critical (Not Usable)

---

## 🎨 **1. UI/UX Design** → 8.2/10 ✅

### ✅ **Stärken:**
- ✅ Konsistentes Tailwind CSS 4 Design-System
- ✅ Dark Mode mit System-Preference-Detection
- ✅ Lucide Icons durchgehend verwendet
- ✅ AppShell-Layout mit Sidebar (264px) + TopBar
- ✅ Responsive Design (Mobile Nav vorhanden)
- ✅ Command Palette (Cmd+K) für Power-User
- ✅ Presenter Toolbar für Workshop-Modus
- ✅ EU-Loader Animation
- ✅ Breadcrumb-Navigation

### ⚠️ **Verbesserungspotenzial:**
- ⚠️ Keine Design-Tokens dokumentiert
- ⚠️ Keine Storybook/Component-Library
- ⚠️ Error-States nicht konsistent (fehlt in einigen Komponenten)
- ⚠️ Loading-States manchmal generisch (EuLoader überall)

### 🎯 **Optimierungsvorschläge:**
1. **Design-Tokens dokumentieren** → `DESIGN_SYSTEM.md`
   ```css
   --color-primary: ...
   --spacing-sidebar: 264px
   --transition-standard: 200ms
   ```

2. **Error-State-Pattern** für alle Komponenten
   ```tsx
   <ErrorBoundary fallback={<ErrorCard />}>
     <YourComponent />
   </ErrorBoundary>
   ```

3. **Skeleton-Loading** statt generischer Spinner
   ```tsx
   {loading ? <CardSkeleton /> : <Card data={data} />}
   ```

### **Score-Breakdown:**
- Layout & Spacing: 9/10
- Color & Typography: 8/10
- Interactive Elements: 8/10
- Consistency: 9/10
- User Flow: 7/10

---

## ⚡ **2. Performance** → 7.5/10 ⚠️

### ✅ **Stärken:**
- ✅ Vite 8 für schnelles HMR
- ✅ React 19 (neueste Version)
- ✅ SSE-Streaming für LLM (kein Polling)
- ✅ pgvector für effiziente Vektorsuche
- ✅ Pool-Pre-Ping für DB-Verbindungen
- ✅ Nginx für statische Dateien

### ⚠️ **Verbesserungspotenzial:**
- ⚠️ Keine Code-Splitting-Strategie
- ⚠️ Keine Lazy-Loading für Routen
- ⚠️ Leaflet-Bundle nicht optimiert
- ⚠️ Keine Image-Optimierung
- ⚠️ FastAPI ohne Caching-Layer

### 🎯 **Optimierungsvorschläge:**
1. **React Lazy + Suspense** für Routen
   ```tsx
   const ScenarioPage = lazy(() => import('./pages/ScenarioPage'));

   <Suspense fallback={<EuLoader />}>
     <ScenarioPage />
   </Suspense>
   ```

2. **Vite Code-Splitting** konfigurieren
   ```ts
   // vite.config.ts
   build: {
     rollupOptions: {
       output: {
         manualChunks: {
           'vendor-react': ['react', 'react-dom', 'react-router-dom'],
           'vendor-leaflet': ['leaflet', 'react-leaflet'],
           'vendor-ui': ['lucide-react']
         }
       }
     }
   }
   ```

3. **FastAPI Response-Caching** für statische Daten
   ```python
   from fastapi_cache import FastAPICache
   from fastapi_cache.backends.inmemory import InMemoryBackend

   @lru_cache(maxsize=128)
   def get_reference_data():
       ...
   ```

4. **Leaflet Dynamic Import**
   ```tsx
   const Map = dynamic(() => import('./BeneficiaryMap'), {
     ssr: false,
     loading: () => <MapSkeleton />
   });
   ```

### **Score-Breakdown:**
- Initial Load: 7/10
- Runtime Performance: 8/10
- Network Efficiency: 7/10
- Bundle Size: 7/10
- Backend Performance: 8/10

---

## 🔒 **3. Security** → 6.8/10 ⚠️

### ✅ **Stärken:**
- ✅ Kein Cloud-LLM (DSGVO-konform)
- ✅ Alle Daten lokal
- ✅ PostgreSQL mit parametrisierten Queries
- ✅ TypeScript strict mode

### ⚠️ **Kritische Punkte:**
- ⚠️ **Kein Auth-System** (OK für Workshop, aber dokumentieren!)
- ⚠️ **CORS nur localhost** (gut, aber nicht flexibel)
- ⚠️ **Keine Rate-Limiting** auf LLM-Endpunkte
- ⚠️ **File-Upload ohne Validierung** (Szenario 5)
- ⚠️ **.env in Git** (⚠️ KRITISCH!)

### 🚨 **KRITISCHE FIXES:**
1. **`.env` aus Git entfernen**
   ```bash
   git rm -r --cached .env
   echo ".env" >> .gitignore
   git commit -m "Remove .env from tracking"
   ```

2. **File-Upload-Validierung**
   ```python
   ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.xlsx'}
   MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

   def validate_upload(file: UploadFile):
       if Path(file.filename).suffix not in ALLOWED_EXTENSIONS:
           raise HTTPException(400, "Invalid file type")
       # Check size, MIME type, etc.
   ```

3. **Rate-Limiting für LLM**
   ```python
   from slowapi import Limiter

   limiter = Limiter(key_func=get_remote_address)

   @app.post("/api/workshop/scenario1")
   @limiter.limit("5/minute")  # Max 5 LLM-Calls pro Minute
   async def scenario1(...):
       ...
   ```

### **Score-Breakdown:**
- Authentication: 3/10 (⚠️ keine)
- Authorization: 4/10
- Data Protection: 8/10
- Input Validation: 6/10
- HTTPS/TLS: N/A (localhost)

---

## ♿ **4. Accessibility (A11y)** → 5.5/10 ⚠️

### ✅ **Stärken:**
- ✅ Semantisches HTML (teilweise)
- ✅ Dark Mode (gut für Augen)

### ❌ **Schwachstellen:**
- ❌ **Keine ARIA-Labels** auf interaktiven Elementen
- ❌ **Keyboard-Navigation** nicht durchgehend
- ❌ **Focus-Indicators** fehlen oft
- ❌ **Screen-Reader-Support** nicht getestet
- ❌ **Color-Contrast** nicht geprüft
- ❌ **No Alt-Text** für Bilder

### 🎯 **Optimierungsvorschläge:**
1. **ARIA-Labels hinzufügen**
   ```tsx
   <button
     aria-label="Open command palette"
     aria-keyshortcuts="Control+K"
   >
     <Search />
   </button>
   ```

2. **Focus Management**
   ```tsx
   <CommandPalette
     role="dialog"
     aria-modal="true"
     aria-labelledby="command-palette-title"
     onKeyDown={(e) => e.key === 'Escape' && close()}
   />
   ```

3. **Keyboard-Navigation** testen
   ```bash
   # Mit Tools wie axe-core
   npm install --save-dev @axe-core/react
   ```

4. **Color-Contrast-Check**
   ```bash
   # Chrome DevTools Lighthouse
   # Oder: https://webaim.org/resources/contrastchecker/
   ```

### **Score-Breakdown:**
- Screen Reader: 4/10
- Keyboard Navigation: 6/10
- Focus Management: 5/10
- ARIA: 4/10
- Color Contrast: 7/10

---

## 🧪 **5. Code Quality** → 7.8/10 ✅

### ✅ **Stärken:**
- ✅ TypeScript strict mode
- ✅ ESLint 9 Flat Config
- ✅ Ruff für Python
- ✅ SQLAlchemy 2.0 (modernes ORM)
- ✅ Pydantic für Validierung
- ✅ Separation of Concerns (Router/Service/Model)
- ✅ Deutsche Kommentare (Konsistenz)
- ✅ Docstrings vorhanden

### ⚠️ **Verbesserungspotenzial:**
- ⚠️ **Keine Tests** (❌ KRITISCH!)
- ⚠️ **Keine Type Coverage** Metriken
- ⚠️ **Keine Pre-Commit Hooks**
- ⚠️ **DRY-Prinzip** teilweise verletzt (Wiederholungen in Routers)

### 🎯 **Optimierungsvorschläge:**
1. **Vitest einrichten** (bereits in package.json!)
   ```bash
   cd frontend
   npm run test
   ```

2. **Pytest für Backend**
   ```bash
   cd backend
   pip install pytest pytest-cov
   pytest tests/ --cov=. --cov-report=html
   ```

3. **Pre-Commit-Hooks**
   ```yaml
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/astral-sh/ruff-pre-commit
       hooks:
         - id: ruff
         - id: ruff-format
     - repo: https://github.com/pre-commit/mirrors-eslint
       hooks:
         - id: eslint
   ```

4. **DRY-Refactoring**
   ```python
   # Shared Response-Builder
   def build_llm_response(scenario: str, prompt: str) -> Generator:
       """Gemeinsame LLM-Response-Logik"""
       ...
   ```

### **Score-Breakdown:**
- Type Safety: 8/10
- Linting: 8/10
- Testing: 2/10 (⚠️)
- Documentation: 7/10
- Maintainability: 9/10

---

## 📦 **6. Architecture** → 8.5/10 ✅

### ✅ **Stärken:**
- ✅ **Klare Trennung** Backend/Frontend
- ✅ **Docker Compose** für einfaches Setup
- ✅ **Service-Layer** (nicht nur Router)
- ✅ **Config-Zentralisierung** (`config.py`)
- ✅ **SSE statt WebSocket** (einfacher)
- ✅ **pgvector statt ChromaDB** (weniger Dependencies)
- ✅ **Ollama auf Host** (stabiler als in Container)

### ⚠️ **Verbesserungspotenzial:**
- ⚠️ **Zwei DB-Zugriffsarten** (SQLAlchemy + raw psycopg2)
- ⚠️ **Port-Inkonsistenzen** (README vs docker-compose)
- ⚠️ **Keine Health-Checks** in docker-compose
- ⚠️ **Keine Secrets-Management** (alle in .env)

### 🎯 **Optimierungsvorschläge:**
1. **Einheitlicher DB-Zugriff**
   ```python
   # pgvector auch über SQLAlchemy
   from pgvector.sqlalchemy import Vector

   class KnowledgeChunk(Base):
       __tablename__ = "knowledge_chunks"
       embedding = Column(Vector(768))
   ```

2. **Docker Health-Checks**
   ```yaml
   services:
     backend:
       healthcheck:
         test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
         interval: 30s
         timeout: 10s
         retries: 3
   ```

3. **Secrets via Docker Secrets**
   ```yaml
   secrets:
     db_password:
       file: ./secrets/db_password.txt
   ```

### **Score-Breakdown:**
- Modularity: 9/10
- Scalability: 7/10
- Maintainability: 9/10
- Dependencies: 8/10
- Documentation: 9/10

---

## 🎯 **Top 10 Prioritäten**

| # | Kategorie | Aktion | Impact | Effort |
|---|-----------|--------|--------|--------|
| 1 | 🔒 Security | `.env` aus Git entfernen | 🔴 HIGH | 5 Min |
| 2 | 🧪 Testing | Vitest + Pytest Setup | 🔴 HIGH | 2h |
| 3 | ⚡ Performance | Code-Splitting einrichten | 🟡 MEDIUM | 1h |
| 4 | 🔒 Security | File-Upload-Validierung | 🔴 HIGH | 30 Min |
| 5 | ♿ A11y | ARIA-Labels hinzufügen | 🟡 MEDIUM | 2h |
| 6 | ⚡ Performance | Lazy-Loading für Routen | 🟡 MEDIUM | 1h |
| 7 | 🔒 Security | Rate-Limiting für LLM | 🟡 MEDIUM | 30 Min |
| 8 | 📦 Architecture | DB-Zugriff vereinheitlichen | 🟢 LOW | 3h |
| 9 | ♿ A11y | Keyboard-Navigation testen | 🟡 MEDIUM | 1h |
| 10 | 🎨 UX | Skeleton-Loading States | 🟢 LOW | 2h |

**Legende:**
- 🔴 HIGH: Muss vor Production-Deployment behoben werden
- 🟡 MEDIUM: Sollte in den nächsten Sprints adressiert werden
- 🟢 LOW: Nice-to-have, kann später kommen

---

## 📈 **Verbesserungs-Roadmap**

### **Sprint 1 (Quick Wins - 1 Tag)**
- [x] `.env` aus Git entfernen (war bereits in .gitignore, nie getrackt)
- [x] File-Upload-Validierung (Extension + Size + Path Traversal in allen Upload-Endpunkten)
- [x] Rate-Limiting für LLM (In-Memory, 10 Req/Min pro IP in workshop.py)
- [x] Docker Health-Checks (bereits in docker-compose.yml für db + backend)

### **Sprint 2 (Testing & Quality - 1 Woche)**
- [ ] Vitest Setup + erste Tests
- [ ] Pytest Setup + Backend-Tests
- [ ] Pre-Commit-Hooks
- [ ] ESLint + Ruff in CI/CD

### **Sprint 3 (Performance - 1 Woche)**
- [x] Code-Splitting (manualChunks: vendor-react, vendor-leaflet, vendor-ui)
- [x] Lazy-Loading (React.lazy + Suspense für 11 geschützte Routen)
- [x] Leaflet Bundle-Optimierung (separater Chunk, nur bei Szenario 6 geladen)
- [ ] Backend-Caching

### **Sprint 4 (Accessibility - 1 Woche)**
- [x] ARIA-Labels (Sidebar, CommandPalette, TopBar, Forms — erweitert)
- [ ] Keyboard-Navigation
- [ ] Focus-Management
- [ ] Color-Contrast-Audit

### **Sprint 5 (Polish - 1 Woche)**
- [ ] Design-Tokens dokumentieren
- [ ] Skeleton-Loading
- [ ] Error-States standardisieren
- [ ] Storybook Setup (optional)

---

## 🔧 **Automatisierte Checks**

### **Installation:**
```bash
cd auditworkshop

# Frontend-Checks
cd frontend
npm install --save-dev @axe-core/react lighthouse
npm install --save-dev vitest @testing-library/react

# Backend-Checks
cd ../backend
pip install pytest pytest-cov bandit safety
```

### **Commands:**
```bash
# Frontend
npm run lint              # ESLint
npm run test              # Vitest
npm run test:coverage     # Coverage-Report
npx lighthouse http://localhost:3004 --view

# Backend
pytest --cov=. --cov-report=html
bandit -r . -f html -o bandit-report.html
safety check

# Docker
docker compose exec backend python -m pytest
```

---

## 📝 **Changelog**

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1.0 | 2026-03-19 | Initial Scorecard erstellt |
| 1.1 | 2026-03-19 | Sprint 1 + Sprint 3 + ARIA umgesetzt (Lazy Loading, Code-Splitting, Rate-Limiting) |

---

**Erstellt von:** Claude Code CLI mit MCP-Unterstützung
**Nächste Review:** Nach Sprint 1 (Quick Wins)
