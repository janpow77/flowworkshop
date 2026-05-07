import { lazy, Suspense, useEffect, useState } from 'react';
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
const AccountPage = lazy(() => import('./pages/AccountPage'));
const HomePage = lazy(() => import('./pages/HomePage'));
const HubPage = lazy(() => import('./pages/HubPage'));
const ScenarioPage = lazy(() => import('./pages/ScenarioPage'));
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'));
const ChecklistPage = lazy(() => import('./pages/ChecklistPage'));
const KnowledgePage = lazy(() => import('./pages/KnowledgePage'));
const DataFramePage = lazy(() => import('./pages/DataFramePage'));
const CompanySearchPage = lazy(() => import('./pages/CompanySearchPage'));
const AiActPage = lazy(() => import('./pages/AiActPage'));
const SanktionslistenPage = lazy(() => import('./pages/SanktionslistenPage'));
const ForumPage = lazy(() => import('./pages/ForumPage'));
const ThreadPage = lazy(() => import('./pages/ThreadPage'));
const NewThreadPage = lazy(() => import('./pages/NewThreadPage'));
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'));
const AgendaArchivePage = lazy(() => import('./pages/AgendaArchivePage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const SignUpPage = lazy(() => import('./pages/SignUpPage'));
const SetupPasswordPage = lazy(() => import('./pages/SetupPasswordPage'));

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<EuLoader />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

export default function App() {
  const [authToken, setAuthToken] = useState<string | null>(localStorage.getItem('workshop_token'));
  const [phase, setPhase] = useState<'live' | 'post'>('live');

  useEffect(() => {
    fetch('/api/event/meta')
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d?.phase) setPhase(d.phase); })
      .catch(() => {});
  }, []);

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
          <Route path="/agenda" element={
            phase === 'post'
              ? <LazyPage><AgendaArchivePage /></LazyPage>
              : <AgendaPage />
          } />
          <Route path="/agenda/archiv" element={<LazyPage><AgendaArchivePage /></LazyPage>} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/vorstellungsrunde" element={<VorstellungsrundePage />} />
          <Route path="/forum" element={<LazyPage><ForumPage /></LazyPage>} />
          <Route path="/forum/t/:threadId" element={<LazyPage><ThreadPage /></LazyPage>} />
          <Route path="/forum/new" element={<LazyPage><NewThreadPage /></LazyPage>} />
          <Route path="/agenda/forum/:itemId" element={<LazyPage><AgendaForumPage /></LazyPage>} />
          {/* Plan v3.2 §5.5: Begünstigtenkarte + Sanktionslisten sind nach
              Art. 49 VO (EU) 2021/1060 öffentlich. */}
          <Route path="/scenario/6" element={<LazyPage><ScenarioPage /></LazyPage>} />
          <Route path="/sanktionslisten" element={<LazyPage><SanktionslistenPage /></LazyPage>} />
        </Route>

        {/* Auth-Pages außerhalb AppShell (kein Sidebar) */}
        <Route path="/signup" element={<LazyPage><SignUpPage /></LazyPage>} />
        <Route path="/account/setup-password" element={<LazyPage><SetupPasswordPage /></LazyPage>} />

        {authToken ? (
          <Route element={<AppShell />}>
            {/* Startseite je nach Phase */}
            <Route index element={
              phase === 'post'
                ? <LazyPage><HubPage /></LazyPage>
                : <LazyPage><HomePage /></LazyPage>
            } />
            <Route path="/account" element={<LazyPage><AccountPage /></LazyPage>} />
            <Route path="/scenario/:id" element={<LazyPage><ScenarioPage /></LazyPage>} />
            <Route path="/projects" element={<LazyPage><ProjectsPage /></LazyPage>} />
            <Route path="/projects/:projectId" element={<LazyPage><ProjectDetailPage /></LazyPage>} />
            <Route path="/projects/:projectId/checklists/:checklistId" element={<LazyPage><ChecklistPage /></LazyPage>} />
            <Route path="/knowledge" element={<LazyPage><KnowledgePage /></LazyPage>} />
            <Route path="/dataframes" element={<LazyPage><DataFramePage /></LazyPage>} />
            <Route path="/company-search" element={<LazyPage><CompanySearchPage /></LazyPage>} />
            <Route path="/ai-act" element={<LazyPage><AiActPage /></LazyPage>} />
            <Route path="/sanktionslisten" element={<LazyPage><SanktionslistenPage /></LazyPage>} />
            <Route path="/docs" element={<LazyPage><DocumentsPage /></LazyPage>} />
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
