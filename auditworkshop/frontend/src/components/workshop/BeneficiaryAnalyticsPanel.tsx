import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Building2, MapPinned, RefreshCw, Sparkles } from 'lucide-react';
import { Skeleton } from '../ui/Skeleton';
import {
  analyzeBeneficiaries,
  listBeneficiarySources,
  type BeneficiaryAnalyticsResponse,
  type BeneficiaryAnalysisMode,
  type BeneficiarySource,
} from '../../lib/api';

const ANALYSIS_OPTIONS: Array<{
  value: BeneficiaryAnalysisMode;
  label: string;
  description: string;
}> = [
  {
    value: 'top_beneficiaries',
    label: 'Top Begünstigte',
    description: 'Welche Träger erhalten das höchste Fördervolumen?',
  },
  {
    value: 'repeat_beneficiaries',
    label: 'Mehrere Vorhaben',
    description: 'Welche Begünstigten tauchen mit mehreren Vorhaben auf?',
  },
  {
    value: 'state_fund_totals',
    label: 'Bundesland × Fonds',
    description: 'Wie verteilt sich das Volumen pro Bundesland und Fonds?',
  },
  {
    value: 'top_locations',
    label: 'Top Standorte',
    description: 'Welche Orte bündeln das höchste Fördervolumen?',
  },
];

function formatInt(value: number): string {
  return value.toLocaleString('de-DE');
}

function buildPrompt(mode: BeneficiaryAnalysisMode, bundesland: string, fonds: string): string {
  const filterText = [bundesland || '', fonds || ''].filter(Boolean).join(' / ');
  const suffix = filterText ? ` Berücksichtige nur ${filterText}.` : '';
  switch (mode) {
    case 'top_beneficiaries':
      return `Zeige mir die größten Begünstigten nach Fördervolumen.${suffix}`;
    case 'repeat_beneficiaries':
      return `Welche Begünstigten haben mehrere Vorhaben und welche Muster fallen dabei auf?${suffix}`;
    case 'state_fund_totals':
      return `Stelle das Fördervolumen pro Bundesland und pro Fonds übersichtlich dar.${suffix}`;
    case 'top_locations':
      return `Welche Standorte bündeln das höchste Fördervolumen und welche Träger dominieren dort?${suffix}`;
    default:
      return `Analysiere die geladenen Begünstigtenverzeichnisse.${suffix}`;
  }
}

export default function BeneficiaryAnalyticsPanel(
  { className, onSelectPrompt }: { className?: string; onSelectPrompt?: (prompt: string) => void },
) {
  const [sources, setSources] = useState<BeneficiarySource[]>([]);
  const [mode, setMode] = useState<BeneficiaryAnalysisMode>('top_beneficiaries');
  const [bundesland, setBundesland] = useState('');
  const [fonds, setFonds] = useState('');
  const [analysis, setAnalysis] = useState<BeneficiaryAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function loadSources() {
      try {
        const response = await listBeneficiarySources();
        if (!cancelled) setSources(response.sources || []);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Quellen konnten nicht geladen werden.');
      }
    }
    loadSources();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!sources.length) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    async function loadAnalysis() {
      setLoading(true);
      setError('');
      try {
        const response = await analyzeBeneficiaries({
          mode,
          bundesland: bundesland || undefined,
          fonds: fonds || undefined,
          limit: 10,
        });
        if (!cancelled) setAnalysis(response);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Analyse fehlgeschlagen.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadAnalysis();
    return () => { cancelled = true; };
  }, [sources, mode, bundesland, fonds]);

  const bundeslaender = useMemo(
    () => [...new Set(sources.map((item) => item.bundesland).filter(Boolean))].sort() as string[],
    [sources],
  );
  const fondsOptions = useMemo(
    () => [...new Set(sources.map((item) => item.fonds).filter(Boolean))].sort() as string[],
    [sources],
  );
  const maxValue = Math.max(...(analysis?.items.map((item) => item.value) || [0]), 1);
  const currentOption = ANALYSIS_OPTIONS.find((item) => item.value === mode);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const response = await analyzeBeneficiaries({
        mode,
        bundesland: bundesland || undefined,
        fonds: fonds || undefined,
        limit: 10,
      });
      setAnalysis(response);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analyse fehlgeschlagen.');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className={`rounded-[26px] border border-slate-200/80 bg-white/90 p-5 shadow-[0_22px_80px_-52px_rgba(15,23,42,0.7)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80 ${className || ''}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-white">
            <BarChart3 size={16} className="text-rose-500" />
            Strukturierte Schnellauswertung
          </div>
          <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
            Wähle eine typische Frage aus. Die Liste und Balkengrafik werden direkt aus den geladenen Verzeichnissen berechnet.
          </p>
        </div>
        {onSelectPrompt && (
          <button
            onClick={() => onSelectPrompt(buildPrompt(mode, bundesland, fonds))}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <Sparkles size={14} />
            Als Prompt übernehmen
          </button>
        )}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[1.5fr_1fr_1fr_auto]">
        <label className="space-y-1 text-sm">
          <span className="text-slate-500 dark:text-slate-400">Frageauswahl</span>
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value as BeneficiaryAnalysisMode)}
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-rose-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          >
            {ANALYSIS_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-slate-500 dark:text-slate-400">Bundesland</span>
          <select
            value={bundesland}
            onChange={(event) => setBundesland(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-rose-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          >
            <option value="">Alle Länder</option>
            {bundeslaender.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-slate-500 dark:text-slate-400">Fonds</span>
          <select
            value={fonds}
            onChange={(event) => setFonds(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-rose-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          >
            <option value="">Alle Fonds</option>
            {fondsOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <button
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className="inline-flex items-center justify-center gap-2 self-end rounded-full bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 dark:bg-rose-500 dark:hover:bg-rose-400 dark:disabled:bg-slate-700"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Neu laden
        </button>
      </div>

      {currentOption && (
        <div className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          {currentOption.description}
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="mt-4 space-y-3">
          <Skeleton className="h-20 rounded-3xl" />
          <Skeleton className="h-24 rounded-3xl" />
          <Skeleton className="h-24 rounded-3xl" />
        </div>
      ) : !analysis || !analysis.items.length ? (
        <div className="mt-4 rounded-3xl border border-dashed border-slate-300 px-5 py-8 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          Für diese Auswahl liegen aktuell keine auswertbaren Datensätze vor.
        </div>
      ) : (
        <>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <div className="rounded-3xl bg-gradient-to-br from-rose-50 to-orange-50 px-4 py-4 dark:from-rose-950/40 dark:to-orange-950/30">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Volumen</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{analysis.summary.total_volume_label}</div>
            </div>
            <div className="rounded-3xl bg-gradient-to-br from-sky-50 to-cyan-50 px-4 py-4 dark:from-sky-950/40 dark:to-cyan-950/30">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Quellen</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{formatInt(analysis.summary.sources_considered)}</div>
            </div>
            <div className="rounded-3xl bg-gradient-to-br from-amber-50 to-yellow-50 px-4 py-4 dark:from-amber-950/40 dark:to-yellow-950/30">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Datensätze</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{formatInt(analysis.summary.records_scanned)}</div>
            </div>
          </div>

          <div className="mt-5 rounded-[28px] border border-slate-200/80 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-950/50">
            <div className="mb-4 flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-white">
              {mode === 'top_locations' ? <MapPinned size={16} className="text-cyan-500" /> : <Building2 size={16} className="text-rose-500" />}
              {analysis.title}
            </div>
            <div className="space-y-3">
              {analysis.items.map((item) => {
                const width = Math.max(8, Math.round((item.value / maxValue) * 100));
                return (
                  <div key={`${item.rank}-${item.label}`} className="rounded-3xl border border-white/80 bg-white px-4 py-4 shadow-[0_14px_40px_-32px_rgba(15,23,42,0.7)] dark:border-slate-800 dark:bg-slate-900">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3">
                          <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white dark:bg-rose-500">
                            {item.rank}
                          </span>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">{item.label}</div>
                            {item.sublabel && (
                              <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{item.sublabel}</div>
                            )}
                          </div>
                        </div>
                        <div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-rose-500 via-orange-500 to-amber-400"
                            style={{ width: `${width}%` }}
                          />
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="text-base font-semibold text-slate-900 dark:text-white">{item.value_label}</div>
                        {typeof item.project_count === 'number' && (
                          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                            {formatInt(item.project_count)} Vorhaben
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
