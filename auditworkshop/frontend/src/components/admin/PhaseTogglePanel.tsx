import { useEffect, useState } from 'react';
import { Loader2, Archive, Calendar } from 'lucide-react';
import { getWorkshopAuthHeaders } from '../../lib/api';

interface Meta { phase: string; archive_started_at?: string | null; }

export default function PhaseTogglePanel() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const r = await fetch('/api/event/meta');
      if (r.ok) setMeta(await r.json());
    } catch { /* ignore */ }
  };
  useEffect(() => { load(); }, []);

  const setPhase = async (phase: 'live' | 'post') => {
    const confirmText = phase === 'post'
      ? 'Auf ARCHIV-Modus umstellen? Hub-Kacheln werden Startseite, Tagesordnung wird read-only.'
      : 'Zurück auf LIVE-Modus? Sidebar-Szenarien werden wieder Standard.';
    if (!confirm(confirmText)) return;
    setLoading(true);
    setError('');
    try {
      const r = await fetch('/api/event/admin/phase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
        body: JSON.stringify({ phase }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${r.status}`);
      }
      setMeta(await r.json());
      // Hard reload damit App.tsx den neuen Phase-Wert auswertet
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    } finally {
      setLoading(false);
    }
  };

  if (!meta) return <div className="text-sm text-slate-500">Lade Meta…</div>;

  const isPost = meta.phase === 'post';

  return (
    <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 dark:border-slate-800">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Veranstaltungs-Modus</h2>
        <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${
          isPost ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'
                 : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200'
        }`}>
          {isPost ? <><Archive size={12} />Archiv</> : <><Calendar size={12} />Live</>}
        </span>
      </div>

      <div className="p-5 space-y-3 text-sm text-slate-600 dark:text-slate-300">
        {isPost ? (
          <>
            <p>Aktuell läuft die Plattform im <strong>Archiv-Modus</strong>:</p>
            <ul className="list-disc list-inside text-slate-500 space-y-0.5 text-xs">
              <li>Hub-Kacheln sind Startseite</li>
              <li>Tagesordnung ist read-only</li>
              <li>Forum + Dokumente bleiben aktiv</li>
              <li>Demo-Szenarien als Lernumgebung</li>
            </ul>
            {meta.archive_started_at && (
              <p className="text-xs text-slate-400">
                Archiv aktiv seit: {new Date(meta.archive_started_at).toLocaleString('de-DE')}
              </p>
            )}
          </>
        ) : (
          <>
            <p>Aktuell läuft die Plattform im <strong>Live-Modus</strong>:</p>
            <ul className="list-disc list-inside text-slate-500 space-y-0.5 text-xs">
              <li>Sidebar mit Szenarien</li>
              <li>Tagesordnung interaktiv</li>
              <li>Anmeldung offen</li>
              <li>Hub-Kacheln deaktiviert</li>
            </ul>
          </>
        )}

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
            {error}
          </div>
        )}

        <button onClick={() => setPhase(isPost ? 'live' : 'post')} disabled={loading}
          className={`inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-medium ${
            isPost ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
                   : 'bg-amber-600 hover:bg-amber-700 text-white'
          } disabled:opacity-50`}>
          {loading ? <Loader2 size={14} className="animate-spin" />
            : (isPost ? <Calendar size={14} /> : <Archive size={14} />)}
          {isPost ? 'Zurück zu Live-Modus' : 'Auf Archiv-Modus umstellen'}
        </button>
      </div>
    </div>
  );
}
