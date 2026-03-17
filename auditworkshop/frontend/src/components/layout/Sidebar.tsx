import { NavLink } from 'react-router-dom';
import {
  Home, FileSearch, CheckSquare, AlertTriangle, FileText,
  Upload, MapPin, FolderOpen, Database, FileSpreadsheet, Sparkles, Building2, Scale,
  CalendarDays, UserPlus, Settings,
} from 'lucide-react';

const NAV = [
  {
    label: 'Workshop',
    items: [
      { to: '/', label: 'Home', icon: Home },
      { to: '/scenario/1', label: '1 · Dokumentenanalyse', icon: FileSearch },
      { to: '/scenario/2', label: '2 · Checklisten-KI', icon: CheckSquare },
      { to: '/scenario/3', label: '3 · Halluzination', icon: AlertTriangle },
      { to: '/scenario/4', label: '4 · Berichtsentwurf', icon: FileText },
      { to: '/scenario/5', label: '5 · Vorab-Upload', icon: Upload },
      { to: '/scenario/6', label: '6 · Begünstigte', icon: MapPin },
    ],
  },
  {
    label: 'Arbeitsräume',
    items: [
      { to: '/projects', label: 'Projekte', icon: FolderOpen },
      { to: '/knowledge', label: 'Wissensbasis', icon: Database },
      { to: '/company-search', label: 'Unternehmenssuche', icon: Building2 },
      { to: '/ai-act', label: 'AI Act', icon: Scale },
      { to: '/dataframes', label: 'Datenanalyse', icon: FileSpreadsheet },
    ],
  },
  {
    label: 'Veranstaltung',
    items: [
      { to: '/agenda', label: 'Tagesordnung', icon: CalendarDays },
      { to: '/register', label: 'Anmeldung', icon: UserPlus },
      { to: '/admin', label: 'Verwaltung', icon: Settings },
    ],
  },
];

export default function Sidebar() {
  return (
    <aside className="relative z-10 hidden w-80 shrink-0 border-r border-white/60 bg-white/75 backdrop-blur-xl dark:border-slate-800/70 dark:bg-slate-950/70 lg:flex lg:flex-col" aria-label="Hauptnavigation">
      <div className="border-b border-slate-200/70 px-6 py-6 dark:border-slate-800/80">
        <div className="rounded-[28px] border border-white/80 bg-[linear-gradient(145deg,rgba(10,37,64,0.98),rgba(11,79,108,0.94)_45%,rgba(18,119,119,0.85))] p-5 text-white shadow-[0_24px_80px_-40px_rgba(14,116,144,0.9)]">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-100/70">Auditworkshop</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight">EFRE Intelligence Desk</h1>
            </div>
            <div className="rounded-2xl border border-white/15 bg-white/10 p-3">
              <Sparkles size={18} className="text-cyan-100" />
            </div>
          </div>
          <p className="max-w-xs text-sm leading-6 text-cyan-50/85">
            Live-Demoumgebung für Prüfer mit lokalem LLM, RAG, Checklistenlogik und geschütztem Datenfluss.
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2">
              <div className="text-cyan-100/60">Szenarien</div>
              <div className="mt-1 text-lg font-semibold">6</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2">
              <div className="text-cyan-100/60">Betriebsart</div>
              <div className="mt-1 text-lg font-semibold">Lokal</div>
            </div>
          </div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-4 py-5">
        {NAV.map((group) => (
          <div key={group.label} className="mb-6">
            <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
              {group.label}
            </div>
            <div className="space-y-1">
              {group.items.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm transition-all duration-200 ${
                      isActive
                        ? 'bg-slate-900 text-white shadow-[0_18px_36px_-24px_rgba(15,23,42,0.85)] dark:bg-cyan-400/15 dark:text-cyan-100'
                        : 'text-slate-600 hover:bg-white/80 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900/70 dark:hover:text-slate-100'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span className={`flex h-10 w-10 items-center justify-center rounded-2xl border transition-colors ${
                        isActive
                          ? 'border-white/15 bg-white/10 text-cyan-100 dark:border-cyan-400/20 dark:bg-cyan-400/10'
                          : 'border-slate-200 bg-white text-slate-500 group-hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400'
                      }`}>
                        <Icon size={18} />
                      </span>
                      <span className="flex-1">{label}</span>
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="mt-auto border-t border-slate-200 dark:border-slate-800 px-4 py-3">
        <p className="text-[10px] text-slate-400 space-y-0.5">
          <span className="block"><kbd className="px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono text-[9px]">Alt+P</kbd> Presenter-Modus</span>
          <span className="block"><kbd className="px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono text-[9px]">Alt+S</kbd> Sprechzettel</span>
          <span className="block"><kbd className="px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-mono text-[9px]">Ctrl+K</kbd> Schnellzugriff</span>
        </p>
      </div>
    </aside>
  );
}
