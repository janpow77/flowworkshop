import { Link, Outlet, useLocation } from 'react-router-dom';
import { Banknote, ClipboardCheck, LogIn, Map as MapIcon, Shield, ArrowLeft } from 'lucide-react';
import ErrorBoundary from './ErrorBoundary';
import { useDarkMode } from '../../hooks/useDarkMode';

export default function PublicShell() {
  const [dark] = useDarkMode();
  const loc = useLocation();
  const isLoggedIn = !!localStorage.getItem('workshop_token');

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-[var(--app-bg)] text-slate-900 dark:text-slate-100">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-20 top-0 h-72 w-72 rounded-full bg-cyan-300/20 blur-3xl dark:bg-cyan-500/10" />
        <div className="absolute right-[-7rem] top-24 h-80 w-80 rounded-full bg-amber-300/20 blur-3xl dark:bg-amber-400/10" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.78),rgba(255,255,255,0)_48%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,41,59,0.5),rgba(2,6,23,0)_45%)]" />
      </div>
      <header className="relative z-10 border-b border-slate-200/60 bg-white/70 backdrop-blur-md dark:border-slate-800/60 dark:bg-slate-950/60">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-5 py-3 lg:px-8">
          <Link to="/" className="flex items-center gap-3 text-slate-700 dark:text-slate-200">
            <span className="text-2xl">🇪🇺</span>
            <div className="leading-tight">
              <div className="text-sm font-semibold">Prüferworkshop 2026</div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400">
                Registerabgleich für Prüfbehörden
              </div>
            </div>
          </Link>
          <nav className="hidden items-center gap-1 sm:flex">
            <Link
              to="/scenario/6"
              className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm transition-colors ${
                loc.pathname === '/scenario/6'
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <MapIcon size={14} /> Begünstigtenverzeichnisse
            </Link>
            <Link
              to="/beihilfen"
              className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm transition-colors ${
                loc.pathname === '/beihilfen'
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <Banknote size={14} /> Beihilfe-Register
            </Link>
            <Link
              to="/audit-report"
              className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm transition-colors ${
                loc.pathname === '/audit-report'
                  ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-200'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <ClipboardCheck size={14} /> Auswertung
            </Link>
            <Link
              to="/sanktionslisten"
              className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm transition-colors ${
                loc.pathname === '/sanktionslisten'
                  ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <Shield size={14} /> Sanktionslisten
            </Link>
          </nav>
          <div className="flex items-center gap-2">
            {isLoggedIn ? (
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                <ArrowLeft size={14} /> Zurück
              </Link>
            ) : (
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-cyan-700"
              >
                <LogIn size={14} /> Anmelden
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="relative z-10 flex-1 overflow-auto px-5 pb-8 pt-6 lg:px-8">
        <div className="mx-auto w-full max-w-[1600px] animate-enter">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>
      <footer className="relative z-10 border-t border-slate-200/60 bg-white/60 px-5 py-3 text-center text-[11px] text-slate-500 backdrop-blur-md dark:border-slate-800/60 dark:bg-slate-950/40 dark:text-slate-400 lg:px-8">
        Daten nach Art. 49 VO (EU) 2021/1060 · Sanktionslisten EU FSF / OFAC / OFSI · {dark ? 'Dark' : 'Hell'}-Modus aktiv
      </footer>
    </div>
  );
}
