import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import CommandPalette from './CommandPalette';
import MobileNav from './MobileNav';
import PresenterToolbar from './PresenterToolbar';
import SprechzettelPanel from './SprechzettelPanel';
import ErrorBoundary from './ErrorBoundary';
import { useDarkMode } from '../../hooks/useDarkMode';

export default function AppShell() {
  const [dark, setDark] = useDarkMode();

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-[var(--app-bg)] text-slate-900 dark:text-slate-100">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-20 top-0 h-72 w-72 rounded-full bg-cyan-300/20 blur-3xl animate-float-slow dark:bg-cyan-500/10" />
        <div className="absolute right-[-7rem] top-24 h-80 w-80 rounded-full bg-amber-300/20 blur-3xl animate-float-slower dark:bg-amber-400/10" />
        <div className="absolute bottom-[-6rem] left-1/3 h-96 w-96 rounded-full bg-emerald-300/15 blur-3xl animate-float-slow dark:bg-emerald-500/10" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.78),rgba(255,255,255,0)_48%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,41,59,0.5),rgba(2,6,23,0)_45%)]" />
      </div>
      <Sidebar />
      <div className="relative z-10 flex flex-1 min-w-0 flex-col">
        <TopBar dark={dark} onToggleDark={() => setDark(!dark)} />
        <PresenterToolbar />
        <MobileNav />
        <main className="flex-1 overflow-auto px-5 pb-8 pt-6 lg:px-8">
          <div className="mx-auto w-full max-w-7xl animate-enter">
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
        <CommandPalette />
        <SprechzettelPanel />
      </div>
    </div>
  );
}
