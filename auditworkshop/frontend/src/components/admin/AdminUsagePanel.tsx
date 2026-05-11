/**
 * AdminUsagePanel — LLM-Nutzungs-Statistiken fuer Prompt-Optimierung.
 *
 * Datenquelle: workshop_llm_call_log (ein Eintrag pro abgeschlossenem
 * LLM-Call). Erfasst sowohl SSE-Streaming-Endpoints (Szenarien 1-6) als
 * auch synchrone Endpoints (State-Aid-Berichte).
 *
 * Endpoints:
 *   GET /api/admin/access/llm/summary?pin=...&since_hours=24
 *   GET /api/admin/access/llm/by-model?pin=...&since_hours=24
 *   GET /api/admin/access/llm/by-route?pin=...&since_hours=24
 *   GET /api/admin/access/llm/latency-buckets?pin=...&since_hours=24
 *   GET /api/admin/access/llm/recent?pin=...&limit=100
 */
import { useEffect, useState } from 'react';
import { Loader2, RefreshCw, Cpu, Clock, Hash, AlertTriangle } from 'lucide-react';

interface Summary {
  total_calls: number;
  prompt_tokens_sum: number;
  completion_tokens_sum: number;
  total_tokens: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
  total_duration_ms: number;
  by_status: Record<string, number>;
}

interface ByModelItem {
  model: string | null;
  backend: string | null;
  calls: number;
  prompt_tokens_sum: number;
  completion_tokens_sum: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
  errors: number;
}

interface ByRouteItem {
  route: string;
  calls: number;
  prompt_tokens_sum: number;
  completion_tokens_sum: number;
  total_tokens: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
}

interface Bucket { label: string; count: number; }

interface RecentItem {
  id: number;
  created_at: string | null;
  route: string | null;
  model: string | null;
  backend: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  duration_ms: number;
  status: string;
  error: string | null;
}

interface Props { pin: string; }

const SINCE_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: '1h' },
  { value: 6, label: '6h' },
  { value: 24, label: '24h' },
  { value: 24 * 7, label: '7d' },
  { value: 24 * 30, label: '30d' },
];

function fmt(n: number | null | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString('de-DE');
}

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export default function AdminUsagePanel({ pin }: Props) {
  const [sinceHours, setSinceHours] = useState<number>(24);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [byModel, setByModel] = useState<ByModelItem[]>([]);
  const [byRoute, setByRoute] = useState<ByRouteItem[]>([]);
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [recent, setRecent] = useState<RecentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    const qs = `pin=${encodeURIComponent(pin)}&since_hours=${sinceHours}`;
    try {
      const [s, m, r, b, rc] = await Promise.all([
        fetch(`/api/admin/access/llm/summary?${qs}`).then((r) => r.json()),
        fetch(`/api/admin/access/llm/by-model?${qs}`).then((r) => r.json()),
        fetch(`/api/admin/access/llm/by-route?${qs}`).then((r) => r.json()),
        fetch(`/api/admin/access/llm/latency-buckets?${qs}`).then((r) => r.json()),
        fetch(`/api/admin/access/llm/recent?pin=${encodeURIComponent(pin)}&limit=100`).then((r) => r.json()),
      ]);
      if (s.detail) throw new Error(s.detail);
      setSummary(s);
      setByModel(m.items || []);
      setByRoute(r.items || []);
      setBuckets(b.buckets || []);
      setRecent(rc.items || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [sinceHours]);

  const maxBucket = Math.max(1, ...buckets.map((b) => b.count));

  return (
    <div className="rounded-[28px] border border-slate-200 bg-white/90 p-6 dark:border-slate-800 dark:bg-slate-900/80 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">LLM-Nutzung & Optimierung</h2>
          <p className="text-xs text-slate-500 mt-1">
            Pro abgeschlossenem LLM-Call: Modell, Tokens, Dauer. Quelle: <code>workshop_llm_call_log</code>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
            {SINCE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setSinceHours(opt.value)}
                className={`px-3 py-1.5 text-xs rounded-lg transition ${
                  sinceHours === opt.value
                    ? 'bg-white text-slate-900 shadow dark:bg-slate-700 dark:text-white'
                    : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
              >{opt.label}</button>
            ))}
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300"
            aria-label="Aktualisieren"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Reload
          </button>
        </div>
      </div>

      {err && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-950/30 dark:text-red-300">
          {err}
        </div>
      )}

      {/* KPIs */}
      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi icon={Hash} label="LLM-Calls" value={fmt(summary.total_calls)} />
          <Kpi icon={Cpu} label="Tokens gesamt" value={fmt(summary.total_tokens)} hint={`prompt ${fmt(summary.prompt_tokens_sum)} / completion ${fmt(summary.completion_tokens_sum)}`} />
          <Kpi icon={Clock} label="Ø Dauer" value={fmtMs(summary.avg_duration_ms)} hint={`p95 ${fmtMs(summary.p95_duration_ms)}`} />
          <Kpi icon={AlertTriangle} label="Fehler" value={fmt((summary.by_status?.error || 0) + (summary.by_status?.timeout || 0))} hint={Object.entries(summary.by_status).map(([k,v]) => `${k}: ${v}`).join(' · ')} />
        </div>
      )}

      {/* Latenz-Histogramm */}
      <div>
        <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Latenz-Histogramm</h3>
        <div className="space-y-1.5">
          {buckets.map((b) => (
            <div key={b.label} className="flex items-center gap-3">
              <span className="text-xs font-mono w-20 text-slate-500">{b.label}</span>
              <div className="flex-1 h-5 bg-slate-100 rounded overflow-hidden dark:bg-slate-800">
                <div
                  className="h-full bg-indigo-500/80 dark:bg-indigo-400/70"
                  style={{ width: `${(b.count / maxBucket) * 100}%` }}
                  aria-label={`${b.count} Calls`}
                />
              </div>
              <span className="text-xs font-mono w-12 text-right text-slate-600 dark:text-slate-400">{fmt(b.count)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* By-Model + By-Route */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Nach Modell</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="text-left py-1.5">Modell</th>
                  <th className="text-right py-1.5">Calls</th>
                  <th className="text-right py-1.5">Tokens</th>
                  <th className="text-right py-1.5">Ø ms</th>
                  <th className="text-right py-1.5">p95</th>
                  <th className="text-right py-1.5">Err</th>
                </tr>
              </thead>
              <tbody>
                {byModel.map((m, i) => (
                  <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 font-mono text-[11px] text-slate-900 dark:text-slate-100">
                      {m.model || '—'}{m.backend ? <span className="text-slate-400"> · {m.backend}</span> : null}
                    </td>
                    <td className="text-right tabular-nums">{fmt(m.calls)}</td>
                    <td className="text-right tabular-nums">{fmt(m.prompt_tokens_sum + m.completion_tokens_sum)}</td>
                    <td className="text-right tabular-nums">{fmtMs(m.avg_duration_ms)}</td>
                    <td className="text-right tabular-nums">{fmtMs(m.p95_duration_ms)}</td>
                    <td className="text-right tabular-nums text-red-600 dark:text-red-400">{m.errors > 0 ? fmt(m.errors) : '—'}</td>
                  </tr>
                ))}
                {byModel.length === 0 && (
                  <tr><td colSpan={6} className="py-3 text-center text-slate-400">Keine Daten</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Nach Endpoint (Top)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="text-left py-1.5">Route</th>
                  <th className="text-right py-1.5">Calls</th>
                  <th className="text-right py-1.5">Tokens</th>
                  <th className="text-right py-1.5">Ø ms</th>
                </tr>
              </thead>
              <tbody>
                {byRoute.map((r, i) => (
                  <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 font-mono text-[10px] text-slate-900 dark:text-slate-100">{r.route}</td>
                    <td className="text-right tabular-nums">{fmt(r.calls)}</td>
                    <td className="text-right tabular-nums">{fmt(r.total_tokens)}</td>
                    <td className="text-right tabular-nums">{fmtMs(r.avg_duration_ms)}</td>
                  </tr>
                ))}
                {byRoute.length === 0 && (
                  <tr><td colSpan={4} className="py-3 text-center text-slate-400">Keine Daten</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Recent */}
      <div>
        <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Letzte Calls (max 100)</h3>
        <div className="overflow-x-auto max-h-96 overflow-y-auto border border-slate-200 rounded-xl dark:border-slate-700">
          <table className="w-full text-xs">
            <thead className="text-slate-500 bg-slate-50 dark:bg-slate-800 sticky top-0">
              <tr>
                <th className="text-left py-1.5 px-2">Zeit</th>
                <th className="text-left py-1.5 px-2">Route</th>
                <th className="text-left py-1.5 px-2">Modell</th>
                <th className="text-right py-1.5 px-2">P-Tok</th>
                <th className="text-right py-1.5 px-2">C-Tok</th>
                <th className="text-right py-1.5 px-2">Dauer</th>
                <th className="text-left py-1.5 px-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-1 px-2 font-mono text-[10px] text-slate-500">
                    {c.created_at ? new Date(c.created_at).toLocaleTimeString('de-DE') : '—'}
                  </td>
                  <td className="py-1 px-2 font-mono text-[10px] text-slate-900 dark:text-slate-100 max-w-xs truncate">{c.route || '—'}</td>
                  <td className="py-1 px-2 font-mono text-[10px]">{c.model || '—'}</td>
                  <td className="text-right tabular-nums px-2">{fmt(c.prompt_tokens)}</td>
                  <td className="text-right tabular-nums px-2">{fmt(c.completion_tokens)}</td>
                  <td className="text-right tabular-nums px-2">{fmtMs(c.duration_ms)}</td>
                  <td className="px-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      c.status === 'ok' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                    }`}>{c.status}</span>
                  </td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr><td colSpan={7} className="py-4 text-center text-slate-400">Keine Calls</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, hint }: {
  icon: typeof Cpu;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/50">
      <div className="flex items-center gap-2 text-slate-500 mb-1">
        <Icon size={14} />
        <span className="text-[11px] uppercase tracking-wide">{label}</span>
      </div>
      <div className="text-xl font-semibold text-slate-900 dark:text-white tabular-nums">{value}</div>
      {hint && <div className="text-[10px] text-slate-500 mt-0.5">{hint}</div>}
    </div>
  );
}
