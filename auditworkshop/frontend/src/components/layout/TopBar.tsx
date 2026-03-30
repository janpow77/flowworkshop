import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Moon, Sun, Cpu, Wifi, WifiOff, ShieldCheck, AlertTriangle, LogOut, User } from 'lucide-react';
import { getOllamaStatus, getSystemProfile, type SystemProfile } from '../../lib/api';

interface Props {
  dark: boolean;
  onToggleDark: () => void;
}

export default function TopBar({ dark, onToggleDark }: Props) {
  const [ollama, setOllama] = useState<{ ok: boolean; models?: string[] } | null>(null);
  const [profile, setProfile] = useState<SystemProfile | null>(null);

  useEffect(() => {
    getOllamaStatus().then(setOllama).catch(() => setOllama({ ok: false }));
    getSystemProfile().then(setProfile).catch(() => setProfile(null));
    const iv = setInterval(() => {
      getOllamaStatus().then(setOllama).catch(() => setOllama({ ok: false }));
    }, 30_000);
    return () => clearInterval(iv);
  }, []);

  const handleLogout = async () => {
    const token = localStorage.getItem('workshop_token');
    try {
      if (token) {
        await fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
      }
    } catch {
      // bewusst ignoriert, lokaler Logout muss trotzdem funktionieren
    } finally {
      localStorage.removeItem('workshop_token');
      localStorage.removeItem('workshop_role');
      window.location.href = '/';
    }
  };

  return (
    <header className="sticky top-0 z-20 border-b border-white/60 bg-white/65 backdrop-blur-xl dark:border-slate-800/80 dark:bg-slate-950/60">
      <div className="flex min-h-16 items-center justify-between gap-4 px-5 lg:px-8">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 text-slate-600 shadow-sm dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300">
            <Cpu size={15} />
            <span className="font-medium">Ollama</span>
            {ollama === null ? (
              <span className="text-slate-400">prüfe…</span>
            ) : ollama.ok ? (
              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <Wifi size={14} />
                verbunden
              </span>
            ) : (
              <span className="flex items-center gap-1 text-rose-500">
                <WifiOff size={14} />
                offline
              </span>
            )}
            {ollama?.ok && ollama.models?.[0] && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                {ollama.models[0]}
              </span>
            )}
          </div>

          {ollama !== null && !ollama.ok && (
            <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs text-amber-700 dark:bg-amber-950/30 dark:border-amber-800 dark:text-amber-400">
              <AlertTriangle size={14} />
              <span>KI-Modell nicht verfuegbar — Szenarien ohne LLM-Antworten. Bitte <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-[10px] dark:bg-amber-900/40">ollama serve</code> starten.</span>
            </div>
          )}

          {profile && (
            <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium uppercase tracking-[0.2em] ${
              profile.privacy_mode
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/80 dark:bg-emerald-950/60 dark:text-emerald-300'
                : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/80 dark:bg-amber-950/60 dark:text-amber-300'
            }`}>
              <ShieldCheck size={14} />
              {profile.privacy_mode ? 'Nur lokaler Betrieb' : 'Externe Dienste aktiv'}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden rounded-full border border-slate-200 bg-white/75 px-3 py-1.5 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 md:block">
            Workshop 5
          </div>
          <div className="hidden rounded-full border border-slate-200 bg-white/75 px-3 py-1.5 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 lg:block">
            Cmd/Ctrl + K
          </div>
          <button
            onClick={onToggleDark}
            className="rounded-2xl border border-slate-200 bg-white/80 p-2.5 text-slate-500 transition-colors hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label={dark ? 'Helles Design aktivieren' : 'Dunkles Design aktivieren'}
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          {localStorage.getItem('workshop_token') && (
            <Link
              to="/account"
              className="rounded-2xl border border-slate-200 bg-white/80 p-2.5 text-slate-500 transition-colors hover:bg-cyan-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-cyan-900/40"
              aria-label="Benutzerkonto"
              title="Benutzerkonto"
            >
              <User size={18} />
            </Link>
          )}
          {localStorage.getItem('workshop_token') && (
            <button
              onClick={handleLogout}
              className="rounded-2xl border border-slate-200 bg-white/80 p-2.5 text-slate-500 transition-colors hover:bg-red-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-red-900/40"
              aria-label="Abmelden"
              title="Abmelden"
            >
              <LogOut size={18} />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
