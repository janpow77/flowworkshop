import { lazy, Suspense, useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AppShell from './components/layout/AppShell';
import EuLoader from './components/layout/EuLoader';
import ErrorBoundary from './components/layout/ErrorBoundary';

// Oeffentliche Routen (sofort geladen)
import AgendaPage from './pages/AgendaPage';
import RegisterPage from './pages/RegisterPage';
import LoginPage from './pages/LoginPage';
import VorstellungsrundePage from './pages/VorstellungsrundePage';

// Geschuetzte Routen (lazy loaded)
const AgendaForumPage = lazy(() => import('./pages/AgendaForumPage'));
const HomePage = lazy(() => import('./pages/HomePage'));
const ScenarioPage = lazy(() => import('./pages/ScenarioPage'));
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'));
const ChecklistPage = lazy(() => import('./pages/ChecklistPage'));
const KnowledgePage = lazy(() => import('./pages/KnowledgePage'));
const DataFramePage = lazy(() => import('./pages/DataFramePage'));
const CompanySearchPage = lazy(() => import('./pages/CompanySearchPage'));
const AiActPage = lazy(() => import('./pages/AiActPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<EuLoader />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

export default function App() {
  const [authToken, setAuthToken] = useState<string | null>(localStorage.getItem('workshop_token'));

  const handleLogin = (token: string, user: { name: string; organization: string; role: string }) => {
    localStorage.setItem('workshop_token', token);
    localStorage.setItem('workshop_role', user.role);
    setAuthToken(token);
  };

  return (
    <BrowserRouter>
      <Routes>
        {/* Oeffentliche Routen ohne Login */}
        <Route element={<AppShell />}>
          <Route path="/agenda" element={<AgendaPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/vorstellungsrunde" element={<VorstellungsrundePage />} />
          <Route path="/agenda/forum/:itemId" element={<LazyPage><AgendaForumPage /></LazyPage>} />
        </Route>

        {authToken ? (
          <Route element={<AppShell />}>
            <Route index element={<LazyPage><HomePage /></LazyPage>} />
            <Route path="/scenario/:id" element={<LazyPage><ScenarioPage /></LazyPage>} />
            <Route path="/projects" element={<LazyPage><ProjectsPage /></LazyPage>} />
            <Route path="/projects/:projectId" element={<LazyPage><ProjectDetailPage /></LazyPage>} />
            <Route path="/projects/:projectId/checklists/:checklistId" element={<LazyPage><ChecklistPage /></LazyPage>} />
            <Route path="/knowledge" element={<LazyPage><KnowledgePage /></LazyPage>} />
            <Route path="/dataframes" element={<LazyPage><DataFramePage /></LazyPage>} />
            <Route path="/company-search" element={<LazyPage><CompanySearchPage /></LazyPage>} />
            <Route path="/ai-act" element={<LazyPage><AiActPage /></LazyPage>} />
            <Route path="/admin" element={<LazyPage><AdminPage /></LazyPage>} />
            <Route path="*" element={<LazyPage><NotFoundPage /></LazyPage>} />
          </Route>
        ) : (
          <Route path="*" element={<LoginPage onLogin={handleLogin} />} />
        )}
      </Routes>
    </BrowserRouter>
  );
}
