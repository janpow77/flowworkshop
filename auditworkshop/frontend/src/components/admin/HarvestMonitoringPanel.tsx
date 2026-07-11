import { useEffect, useState } from 'react';
import { Activity, AlertTriangle, RefreshCw } from 'lucide-react';
import { getWorkshopAuthHeaders } from '../../lib/auth';

type Item = { source: string; status: string; last_run: string | null; age_hours: number | null; records_seen: number; records_inserted: number | null; records_failed: number | null; warning: string | null };
type Report = { generated_at: string; warning_count: number; state_aid: Item[]; beneficiaries: Item[] };

export default function HarvestMonitoringPanel() {
  const [data, setData] = useState<Report | null>(null); const [error, setError] = useState('');
  const load = () => fetch('/api/admin/monitoring/harvests', { headers: getWorkshopAuthHeaders() })
    .then(r => r.ok ? r.json() : Promise.reject(new Error('Monitoring konnte nicht geladen werden.')))
    .then(setData).catch(e => setError(e.message));
  useEffect(() => { load(); }, []);
  const rows = [...(data?.state_aid || []), ...(data?.beneficiaries || [])];
  return <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
    <div className="flex items-center justify-between gap-3"><div><h2 className="flex items-center gap-2 font-semibold"><Activity size={18}/> Datenmonitoring</h2><p className="mt-1 text-sm text-slate-500">Frische, Teilfehler und auffällige Harvest-Läufe.</p></div><button onClick={load} className="rounded-lg border px-3 py-2 text-sm"><RefreshCw size={14} className="inline mr-1"/>Aktualisieren</button></div>
    {data?.warning_count ? <div className="mt-4 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800"><AlertTriangle size={16}/>{data.warning_count} Meldung(en) erfordern Prüfung.</div> : null}
    {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-500"><tr><th>Quelle</th><th>Status</th><th>Letzter Lauf</th><th>Datensätze</th><th>Meldung</th></tr></thead><tbody>{rows.map(r => <tr key={r.source} className="border-t"><td className="py-2 font-medium">{r.source}</td><td>{r.status}</td><td>{r.last_run ? new Date(r.last_run).toLocaleString('de-DE') : '—'}</td><td>{r.records_seen.toLocaleString('de-DE')}</td><td className={r.warning ? 'text-amber-700 font-medium' : 'text-emerald-700'}>{r.warning || 'in Ordnung'}</td></tr>)}</tbody></table></div>}
  </section>;
}
