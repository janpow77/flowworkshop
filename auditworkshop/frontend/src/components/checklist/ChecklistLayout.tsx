/**
 * flowworkshop · components/checklist/ChecklistLayout.tsx
 *
 * Schlankes, eigenstaendiges Layout fuer den Checklisten-Designer. Bewusst
 * OHNE Workshop-Sidebar (Pruefbehoerden/Szenarien/Arbeitsraeume) und ohne die
 * grosse Workshop-TopBar. Eigene schmale Kopfzeile (Titel, Dark-Mode-Toggle,
 * Benutzer/Logout) plus eine optionale, rein checklistenbezogene Navigationsleiste
 * (Liste der eigenen Checklisten + „Zurueck zum Workshop"). Volle Breite,
 * saubere Breakpoints. Farbwelt Emerald/Cyan, Dark Mode beibehalten.
 */
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';
import {
  ArrowLeft, ClipboardCheck, LogOut, Menu, Moon, Sun, User, X,
} from 'lucide-react';
import { listChecklistTemplates, type ChecklistTemplate } from '../../lib/api';
import { useDarkMode } from '../../hooks/useDarkMode';
import ErrorBoundary from '../layout/ErrorBoundary';
import { Skeleton } from '../ui/Skeleton';

function normStatus(raw: string): 'draft' | 'published' | 'archived' {
  const s = (raw || '').toLowerCase();
  if (s.includes('publish')) return 'published';
  if (s.includes('archiv')) return 'archived';
  return 'draft';
}

const STATUS_DOT: Record<'draft' | 'published' | 'archived', string> = {
  draft: 'bg-amber-400',
  published: 'bg-emerald-500',
  archived: 'bg-slate-400',
};

function handleLogout() {
  const token = localStorage.getItem('workshop_token');
  const done = () => {
    localStorage.removeItem('workshop_token');
    localStorage.removeItem('workshop_role');
    window.location.href = '/';
  };
  if (token) {
    fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      .catch(() => { /* lokaler Logout muss trotzdem greifen */ })
      .finally(done);
  } else {
    done();
  }
}

export default function ChecklistLayout() {
  const [dark, setDark] = useDarkMode();
  const [templates, setTemplates] = useState<ChecklistTemplate[] | null>(null);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listChecklistTemplates()
      .then((r) => { if (!cancelled) setTemplates(r); })
      .catch(() => { if (!cancelled) setTemplates([]); });
    return () => { cancelled = true; };
  }, []);

  const loggedIn = !!localStorage.getItem('workshop_token');

  return (
    <div className="relative flex min-h-screen flex-col bg-[var(--app-bg)] text-slate-900 dark:text-slate-100">
      {/* ── Schlanke Kopfzeile ──────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/80 backdrop-blur-xl dark:border-slate-800/70 dark:bg-slate-950/70">
        <div className="flex min-h-14 items-center justify-between gap-3 px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setNavOpen((v) => !v)}
              className="rounded-xl border border-slate-200 bg-white/80 p-2 text-slate-500 transition-colors hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-slate-800 lg:hidden"
              aria-label="Checklisten-Navigation umschalten"
            >
              {navOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
            <Link to="/checklisten" className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-cyan-600 text-white shadow-sm">
                <ClipboardCheck size={18} />
              </span>
              <div className="leading-tight">
                <div className="text-sm font-semibold text-slate-900 dark:text-white">Checklisten-Designer</div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400">Musterchecklisten verwalten</div>
              </div>
            </Link>
          </div>

          <div className="flex items-center gap-2">
            <Link
              to="/hub"
              className="hidden items-center gap-1.5 rounded-xl border border-slate-200 bg-white/80 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300 dark:hover:bg-slate-800 sm:inline-flex"
            >
              <ArrowLeft size={14} /> Zur Übersicht
            </Link>
            <button
              onClick={() => setDark(!dark)}
              className="rounded-xl border border-slate-200 bg-white/80 p-2 text-slate-500 transition-colors hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-slate-800"
              aria-label={dark ? 'Helles Design aktivieren' : 'Dunkles Design aktivieren'}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            {loggedIn && (
              <Link
                to="/account"
                className="rounded-xl border border-slate-200 bg-white/80 p-2 text-slate-500 transition-colors hover:bg-cyan-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-cyan-900/40"
                aria-label="Benutzerkonto"
                title="Benutzerkonto"
              >
                <User size={18} />
              </Link>
            )}
            {loggedIn && (
              <button
                onClick={handleLogout}
                className="rounded-xl border border-slate-200 bg-white/80 p-2 text-slate-500 transition-colors hover:bg-red-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-red-900/40"
                aria-label="Abmelden"
                title="Abmelden"
              >
                <LogOut size={18} />
              </button>
            )}
          </div>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* ── Schmale Checklisten-Navigation (Desktop) ──────────────────── */}
        <ChecklistNav templates={templates} variant="desktop" />

        {/* ── Off-Canvas-Navigation (mobile) ────────────────────────────── */}
        {navOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button
              type="button"
              aria-label="Navigation schliessen"
              onClick={() => setNavOpen(false)}
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
            />
            <div className="absolute left-0 top-0 h-full w-72 max-w-[85%] animate-slide-in border-r border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-950">
              <ChecklistNav templates={templates} variant="mobile" onNavigate={() => setNavOpen(false)} />
            </div>
          </div>
        )}

        {/* ── Inhalt (volle Breite) ─────────────────────────────────────── */}
        <main className="flex-1 min-w-0 overflow-x-hidden px-4 pb-10 pt-6 lg:px-8">
          <div className="mx-auto w-full max-w-6xl animate-enter">
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <footer className="border-t border-slate-200/60 bg-white/50 px-4 py-2 text-center text-[11px] text-slate-500 backdrop-blur-md dark:border-slate-800/60 dark:bg-slate-950/30 dark:text-slate-400 lg:px-8">
        <Link to="/impressum" className="hover:underline">Impressum</Link>
        <span className="mx-2">·</span>
        <Link to="/datenschutz" className="hover:underline">Datenschutz</Link>
      </footer>
    </div>
  );
}

// ── Checklisten-Navigationsleiste (rein checklistenbezogen) ─────────────────────

function ChecklistNav({
  templates, variant, onNavigate,
}: { templates: ChecklistTemplate[] | null; variant: 'desktop' | 'mobile'; onNavigate?: () => void }) {
  const aside =
    variant === 'desktop'
      ? 'hidden w-64 shrink-0 border-r border-slate-200/70 bg-white/60 backdrop-blur-xl dark:border-slate-800/70 dark:bg-slate-950/40 lg:flex lg:flex-col'
      : 'flex h-full flex-col';

  return (
    <aside className={aside} aria-label="Checklisten-Navigation">
      <div className="flex items-center justify-between px-4 py-3">
        <Link
          to="/hub"
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <ArrowLeft size={13} /> Zurück zur Übersicht
        </Link>
      </div>
      <div className="px-4 pb-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
        Meine Checklisten
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {templates === null ? (
          <div className="space-y-2 px-2">
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-9 w-full" />)}
          </div>
        ) : templates.length === 0 ? (
          <p className="px-2 py-4 text-xs text-slate-400 dark:text-slate-500">
            Noch keine Checklisten vorhanden.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {templates.map((t) => (
              <li key={t.id}>
                <NavLink
                  to={`/checklisten/${t.id}`}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                      isActive
                        ? 'bg-emerald-50 font-medium text-emerald-700 dark:bg-emerald-900/25 dark:text-emerald-200'
                        : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/70'
                    }`
                  }
                >
                  <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[normStatus(t.status)]}`} aria-hidden="true" />
                  <span className="truncate">{t.title}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </nav>
      <div className="border-t border-slate-200/70 px-2 py-2 dark:border-slate-800/70">
        <NavLink
          to="/checklisten"
          end
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors ${
              isActive
                ? 'bg-slate-900 text-white dark:bg-cyan-400/15 dark:text-cyan-100'
                : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/70'
            }`
          }
        >
          <ClipboardCheck size={15} /> Alle Checklisten
        </NavLink>
      </div>
    </aside>
  );
}
