import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AppShell from './components/layout/AppShell';
import HomePage from './pages/HomePage';
import ScenarioPage from './pages/ScenarioPage';
import ProjectsPage from './pages/ProjectsPage';
import ProjectDetailPage from './pages/ProjectDetailPage';
import ChecklistPage from './pages/ChecklistPage';
import KnowledgePage from './pages/KnowledgePage';
import DataFramePage from './pages/DataFramePage';
import CompanySearchPage from './pages/CompanySearchPage';
import AiActPage from './pages/AiActPage';
import AgendaPage from './pages/AgendaPage';
import RegisterPage from './pages/RegisterPage';
import AdminPage from './pages/AdminPage';
import NotFoundPage from './pages/NotFoundPage';
import LoginPage from './pages/LoginPage';

export default function App() {
  const [authToken, setAuthToken] = useState<string | null>(localStorage.getItem('workshop_token'));

  const handleLogin = (token: string, _user: { name: string; organization: string; role: string }) => {
    localStorage.setItem('workshop_token', token);
    setAuthToken(token);
  };

  return (
    <BrowserRouter>
      <Routes>
        {/* Oeffentliche Routen ohne Login */}
        <Route element={<AppShell />}>
          <Route path="/agenda" element={<AgendaPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        {authToken ? (
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="/scenario/:id" element={<ScenarioPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="/projects/:projectId/checklists/:checklistId" element={<ChecklistPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/dataframes" element={<DataFramePage />} />
            <Route path="/company-search" element={<CompanySearchPage />} />
            <Route path="/ai-act" element={<AiActPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        ) : (
          <Route path="*" element={<LoginPage onLogin={handleLogin} />} />
        )}
      </Routes>
    </BrowserRouter>
  );
}
