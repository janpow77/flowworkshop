import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';

interface Props {
  number: number;
  title: string;
  description: string;
  icon: LucideIcon;
  color: string;
}

export default function ScenarioCard({ number, title, description, icon: Icon, color }: Props) {
  return (
    <Link
      to={`/scenario/${number}`}
      className="group relative block overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/90 p-6 shadow-[0_18px_60px_-42px_rgba(15,23,42,0.6)] transition-all duration-300 hover:-translate-y-1 hover:border-slate-300 hover:shadow-[0_24px_90px_-42px_rgba(8,47,73,0.68)] dark:border-slate-800 dark:bg-slate-900/75 dark:hover:border-slate-700"
    >
      <div className="absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
        <div className="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-cyan-200/30 blur-3xl dark:bg-cyan-500/10" />
        <div className="absolute bottom-0 left-0 h-24 w-24 rounded-full bg-amber-200/20 blur-2xl dark:bg-amber-400/10" />
      </div>
      <div className="relative">
        <div className="mb-5 flex items-center justify-between">
          <span className={`flex h-12 w-12 items-center justify-center rounded-2xl text-sm font-bold text-white shadow-lg ${color}`}>
            {number}
          </span>
          <span className="rounded-full border border-slate-200 bg-white/80 p-2 text-slate-400 transition-colors group-hover:text-cyan-600 dark:border-slate-800 dark:bg-slate-950/80 dark:group-hover:text-cyan-300">
            <Icon size={18} />
          </span>
        </div>
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
          Workshop-Szenario
        </div>
        <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">{title}</h3>
        <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{description}</p>
        <div className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-slate-700 transition-colors group-hover:text-cyan-700 dark:text-slate-300 dark:group-hover:text-cyan-300">
          Öffnen
          <span className="transition-transform duration-300 group-hover:translate-x-1">→</span>
        </div>
      </div>
    </Link>
  );
}
