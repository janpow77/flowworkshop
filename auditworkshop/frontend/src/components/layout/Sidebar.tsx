import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Home, FolderOpen, Database, FileSpreadsheet, Building2, Scale,
  CalendarDays, UserPlus, Settings, Upload, User,
} from 'lucide-react';

function isModerator(): boolean {
  return localStorage.getItem('workshop_role') === 'moderator';
}

function useWorkshopMode(): boolean {
  const [mode, setMode] = useState(false);
  useEffect(() => {
    fetch('/api/event/meta').then(r => r.json()).then(d => setMode(d.workshop_mode ?? false)).catch(() => {});
  }, []);
  return mode;
}

const NAV = [
  {
    label: 'Veranstaltung',
    items: [
      { to: '/', label: 'Startseite', icon: Home },
      { to: '/agenda', label: 'Tagesordnung', icon: CalendarDays },
      { to: '/register', label: 'Anmeldung', icon: UserPlus },
    ],
  },
  {
    label: 'Szenarien',
    items: [
      { to: '/scenario/1', label: '1 \u00b7 Dokumentenanalyse', icon: Upload },
      { to: '/scenario/2', label: '2 \u00b7 Checklisten-KI (VKO)', icon: FolderOpen },
      { to: '/scenario/3', label: '3 \u00b7 Halluzinations-Demo', icon: Scale },
      { to: '/scenario/4', label: '4 \u00b7 Berichtsentwurf', icon: FolderOpen },
      { to: '/scenario/5', label: '5 \u00b7 Vorab-Upload & RAG', icon: Upload },
      { to: '/scenario/6', label: '6 \u00b7 Beg\u00fcnstigtenverzeichnis', icon: Building2 },
    ],
    locked: true, // wird dynamisch ueberschrieben
  },
  {
    label: 'Arbeitsr\u00e4ume',
    items: [
      { to: '/projects', label: 'Projekte', icon: FolderOpen },
      { to: '/knowledge', label: 'Wissensbasis', icon: Database },
      { to: '/dataframes', label: 'Datenanalyse', icon: FileSpreadsheet },
      { to: '/company-search', label: 'Unternehmenssuche', icon: Building2 },
      { to: '/ai-act', label: 'AI Act', icon: Scale },
      { to: '/account', label: 'Benutzerkonto', icon: User },
      { to: '/admin', label: 'Verwaltung', icon: Settings },
    ],
  },
];

export default function Sidebar() {
  const workshopMode = useWorkshopMode();
  const scenariosUnlocked = workshopMode || isModerator();

  // Szenarien-Gruppe dynamisch (ent-)sperren
  const nav = NAV.map(g => g.label === 'Szenarien' ? { ...g, locked: !scenariosUnlocked } : g);

  return (
    <aside className="relative z-10 hidden w-80 shrink-0 border-r border-white/60 bg-white/75 backdrop-blur-xl dark:border-slate-800/70 dark:bg-slate-950/70 lg:flex lg:flex-col" aria-label="Hauptnavigation">
      <div className="border-b border-slate-200/70 px-6 py-6 dark:border-slate-800/80">
        <div className="rounded-[28px] border border-white/80 bg-[linear-gradient(145deg,rgba(10,37,64,0.98),rgba(11,79,108,0.94)_45%,rgba(18,119,119,0.85))] p-5 text-white shadow-[0_24px_80px_-40px_rgba(14,116,144,0.9)]">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-100/70">Pr&uuml;ferworkshop 2026</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight">Pr&uuml;fbeh&ouml;rden</h1>
            </div>
            <div className="rounded-2xl border border-white/15 bg-white/10 p-3 flex items-center justify-center">
              <svg width="42" height="28" viewBox="0 0 810 540" aria-label="EU" role="img">
                <rect width="810" height="540" fill="#003399" rx="40"/>
                {[...Array(12)].map((_, i) => {
                  const a = (i * 30 - 90) * Math.PI / 180;
                  const cx = 405 + 130 * Math.cos(a);
                  const cy = 270 + 130 * Math.sin(a);
                  return (
                    <polygon
                      key={i}
                      points={[...Array(5)].map((__, j) => {
                        const sa = (j * 144 - 90) * Math.PI / 180;
                        return `${cx + 22 * Math.cos(sa)},${cy + 22 * Math.sin(sa)}`;
                      }).join(' ')}
                      fill="#FFCC00"
                    />
                  );
                })}
              </svg>
            </div>
          </div>
          <p className="max-w-xs text-sm leading-6 text-cyan-50/85">
            {!scenariosUnlocked
              ? 'Melden Sie sich an, reichen Sie Themen ein und laden Sie Dokumente f\u00fcr den Workshop hoch.'
              : 'Live-Demoumgebung mit lokalem LLM, RAG-Wissensbasis, Checklistenlogik und gesch\u00fctztem Datenfluss.'}
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2">
              <div className="text-cyan-100/60">{!scenariosUnlocked ? 'Modus' : 'Szenarien'}</div>
              <div className="mt-1 text-lg font-semibold">{!scenariosUnlocked ? 'Vorfeld' : '6'}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2">
              <div className="text-cyan-100/60">Betriebsart</div>
              <div className="mt-1 text-lg font-semibold">Lokal</div>
            </div>
          </div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-4 py-5">
        {nav.map((group) => (
          <div key={group.label} className="mb-6">
            <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
              {group.label}
              {group.locked && <span className="ml-2 text-[9px] text-slate-400/60">(am Workshop-Tag)</span>}
            </div>
            <div className="space-y-1">
              {group.items.map(({ to, label, icon: Icon }) => {
                if (group.locked) {
                  return (
                    <div
                      key={to}
                      className="group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm opacity-35 cursor-not-allowed select-none"
                      aria-disabled="true"
                      title="Verfügbar am Workshop-Tag"
                    >
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-400 dark:border-slate-800 dark:bg-slate-900">
                        <Icon size={18} />
                      </span>
                      <span className="flex-1 text-slate-400 dark:text-slate-600">{label}</span>
                    </div>
                  );
                }
                return (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950 ${
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
                );
              })}
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
