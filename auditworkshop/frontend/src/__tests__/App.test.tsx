import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from '../App';

// Mock alle Page-Komponenten, damit keine tiefen Abhaengigkeiten geladen werden
vi.mock('../pages/HomePage', () => ({ default: () => <div>HomePage</div> }));
vi.mock('../pages/ScenarioPage', () => ({ default: () => <div>ScenarioPage</div> }));
vi.mock('../pages/ProjectsPage', () => ({ default: () => <div>ProjectsPage</div> }));
vi.mock('../pages/ProjectDetailPage', () => ({ default: () => <div>ProjectDetailPage</div> }));
vi.mock('../pages/ChecklistPage', () => ({ default: () => <div>ChecklistPage</div> }));
vi.mock('../pages/KnowledgePage', () => ({ default: () => <div>KnowledgePage</div> }));
vi.mock('../pages/DataFramePage', () => ({ default: () => <div>DataFramePage</div> }));
vi.mock('../pages/CompanySearchPage', () => ({ default: () => <div>CompanySearchPage</div> }));
vi.mock('../pages/AiActPage', () => ({ default: () => <div>AiActPage</div> }));
vi.mock('../pages/AgendaPage', () => ({ default: () => <div>AgendaPage</div> }));
vi.mock('../pages/RegisterPage', () => ({ default: () => <div>RegisterPage</div> }));
vi.mock('../pages/AdminPage', () => ({ default: () => <div>AdminPage</div> }));
vi.mock('../pages/NotFoundPage', () => ({ default: () => <div>NotFoundPage</div> }));
vi.mock('../pages/LoginPage', () => ({
  default: () => <div>LoginPage</div>,
}));
vi.mock('../components/layout/AppShell', async () => {
  const { Outlet } = await import('react-router-dom');
  return { default: () => <div data-testid="app-shell"><Outlet /></div> };
});

beforeEach(() => {
  localStorage.clear();
});

describe('App', () => {
  it('rendert ohne Crash', () => {
    render(<App />);
    // App rendert entweder LoginPage oder eine andere Seite
    expect(document.body).toBeDefined();
  });

  it('zeigt LoginPage wenn kein Token vorhanden', () => {
    localStorage.removeItem('workshop_token');
    render(<App />);
    expect(screen.getByText('LoginPage')).toBeInTheDocument();
  });
});
