import { NavLink } from 'react-router-dom';
import {
  Home, FileSearch, CheckSquare, AlertTriangle, FileText, Upload, MapPin,
  Database, FolderOpen, Building2, Scale, FileSpreadsheet,
  CalendarDays, UserPlus, Settings,
} from 'lucide-react';

const NAV_GROUPS = [
  {
    label: 'Szenarien',
    items: [
      { to: '/', label: 'Home', icon: Home },
      { to: '/scenario/1', label: 'Dokumente', icon: FileSearch },
      { to: '/scenario/2', label: 'Checklisten', icon: CheckSquare },
      { to: '/scenario/3', label: 'Halluzination', icon: AlertTriangle },
      { to: '/scenario/4', label: 'Bericht', icon: FileText },
      { to: '/scenario/5', label: 'Upload', icon: Upload },
      { to: '/scenario/6', label: 'Karte', icon: MapPin },
    ],
  },
  {
    label: 'Arbeit',
    items: [
      { to: '/projects', label: 'Projekte', icon: FolderOpen },
      { to: '/knowledge', label: 'Wissen', icon: Database },
      { to: '/company-search', label: 'Firmen', icon: Building2 },
      { to: '/ai-act', label: 'AI Act', icon: Scale },
      { to: '/dataframes', label: 'Daten', icon: FileSpreadsheet },
    ],
  },
  {
    label: 'Event',
    items: [
      { to: '/agenda', label: 'Agenda', icon: CalendarDays },
      { to: '/register', label: 'Anmeldung', icon: UserPlus },
      { to: '/admin', label: 'Admin', icon: Settings },
    ],
  },
];

export default function MobileNav() {
  return (
    <div className="lg:hidden border-b border-white/60 bg-white/55 px-4 pb-3 backdrop-blur-xl dark:border-slate-800/80 dark:bg-slate-950/55">
      <div className="flex gap-3 overflow-x-auto pb-1">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex shrink-0 gap-1 items-center">
            <span className="text-[10px] uppercase tracking-wider text-slate-400 dark:text-slate-500 mr-1">{group.label}</span>
            {group.items.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-xs transition-colors ${
                    isActive
                      ? 'border-slate-900 bg-slate-900 text-white dark:border-cyan-400/30 dark:bg-cyan-400/15 dark:text-cyan-100'
                      : 'border-slate-200 bg-white/80 text-slate-600 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300'
                  }`
                }
              >
                <Icon size={12} />
                {label}
              </NavLink>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
