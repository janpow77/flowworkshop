import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  Building2,
  FileDown,
  FileSpreadsheet,
  FileText,
  MapPinned,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { Skeleton } from '../ui/Skeleton';
import {
  analyzeBeneficiaries,
  listBeneficiarySources,
  type BeneficiaryAnalyticsResponse,
  type BeneficiaryAnalysisMode,
  type BeneficiarySource,
  type CountryCode,
} from '../../lib/api';
import { useExport } from '../../lib/useExport';

const REGION_LABEL_BY_COUNTRY: Record<string, string> = {
  DE: 'Bundesland',
  AT: 'Bundesland',
};

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
  {
    value: 'region_project_counts',
    label: 'Vorhaben je Bundesland',
    description: 'Wie viele Vorhaben werden pro Bundesland gefoerdert? Mit Aufschluesselung nach Quelle (Bundes- vs. Landesprogramme).',
  },
  {
    value: 'top_sectors',
    label: 'Wirtschaftszweige / Interventionsbereiche',
    description: 'Welche Sektoren bündeln das höchste Fördervolumen?',
  },
  {
    value: 'multi_state_beneficiaries',
    label: 'Begünstigte über mehrere Bundesländer',
    description: 'Welche Träger erhalten Förderung in mehr als einem Bundesland?',
  },
  {
    value: 'kreis_project_counts',
    label: 'Vorhaben je Kreis (NUTS-3)',
    description: 'Wie viele Vorhaben werden pro Landkreis bzw. kreisfreier Stadt gefördert?',
  },
];

function formatInt(value: number): string {
  return value.toLocaleString('de-DE');
}

/**
 * Schreibt das Backend-Label fuer „Bund"-Eintraege um, damit klar wird,
 * dass es sich um ein Bundesprogramm handelt und nicht um ein Bundesland.
 * Beispiel: „Bund · AMIF" -> „Bundesprogramm · AMIF (national)".
 */
function rewriteAnalyticsLabel(item: { label: string; bundesland?: string | null; fonds?: string | null }): string {
  const bl = (item.bundesland || '').trim();
  if (bl.toLowerCase() === 'bund') {
    const fonds = (item.fonds || '').trim();
    return fonds ? `Bundesprogramm · ${fonds}` : 'Bundesprogramm';
  }
  return item.label;
}

function rewriteAnalyticsSublabel(item: { sublabel?: string; bundesland?: string | null }): string | undefined {
  const bl = (item.bundesland || '').trim();
  const baseSub = item.sublabel || '';
  if (bl.toLowerCase() === 'bund') {
    return baseSub ? `${baseSub} · national/föderal` : 'national/föderal';
  }
  return baseSub || undefined;
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
    case 'region_project_counts':
      return `Wie viele Vorhaben werden pro Bundesland gefördert? Schlüssele die Anzahl nach Quelle (Bundes- vs. Landesprogramme) auf.${suffix}`;
    case 'top_sectors':
      return `Welche Wirtschaftszweige bzw. Interventionsbereiche bündeln das höchste Fördervolumen?${suffix}`;
    case 'multi_state_beneficiaries':
      return `Welche Träger erhalten Förderung in mehr als einem Bundesland und wie verteilt sich das Volumen?${suffix}`;
    default:
      return `Analysiere die geladenen Begünstigtenverzeichnisse.${suffix}`;
  }
}

type BeneficiaryAnalyticsPanelProps = {
  className?: string;
  onSelectPrompt?: (prompt: string) => void;
  countryCode?: CountryCode | '';
};

export default function BeneficiaryAnalyticsPanel(
  { className, onSelectPrompt, countryCode = 'DE' }: BeneficiaryAnalyticsPanelProps,
) {
  const [sources, setSources] = useState<BeneficiarySource[]>([]);
  const [mode, setMode] = useState<BeneficiaryAnalysisMode>('top_beneficiaries');
  const [bundesland, setBundesland] = useState('');
  const [fonds, setFonds] = useState('');
  const [analysis, setAnalysis] = useState<BeneficiaryAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState<'xlsx' | 'csv' | 'pdf' | null>(null);
  const exportApi = useExport();
  // Ziel fuer den PDF-Export: das gerenderte Trefferlisten-Panel.
  const exportTargetRef = useRef<HTMLDivElement | null>(null);

  const regionLabel = countryCode ? REGION_LABEL_BY_COUNTRY[countryCode] || 'Region/Bundesland' : 'Region/Bundesland';

  // Bei Wechsel des Landes Filter zurücksetzen, damit AT keinen DE-Bundesland-Filter erbt.
  useEffect(() => {
    setBundesland('');
  }, [countryCode]);

  useEffect(() => {
    let cancelled = false;
    async function loadSources() {
      try {
        const response = await listBeneficiarySources(countryCode || undefined);
        if (!cancelled) setSources(response.sources || []);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Quellen konnten nicht geladen werden.');
      }
    }
    loadSources();
    return () => { cancelled = true; };
  }, [countryCode]);

  useEffect(() => {
    if (!sources.length) {
      setAnalysis(null);
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
          // Aggregations-Modes brauchen alle Kombinationen sichtbar:
          //   state_fund_totals: 16 BL × ≤5 Fonds = bis ~50 Items (DE)
          //   region_project_counts: 16 BL + Bund = bis 17 Items (DE)
          // Default 10 ist zu wenig fuer beide. Andere Modes (Top-N) -> 10.
          limit: mode === 'state_fund_totals' ? 50
            : mode === 'region_project_counts' ? 50
            : 10,
          country_code: countryCode || undefined,
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
  }, [sources, mode, bundesland, fonds, countryCode]);

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
        country_code: countryCode || undefined,
      });
      setAnalysis(response);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analyse fehlgeschlagen.');
    } finally {
      setRefreshing(false);
    }
  };

  // Tabellarische Repraesentation der aktuell sichtbaren Auswertung.
  // Wird von XLSX und CSV-Export genutzt; Spaltenreihenfolge ist hier
  // verbindlich (SheetJS wuerde sonst Object.keys-Reihenfolge nehmen).
  const exportRows = useMemo(
    () => (analysis?.items ?? []).map((it) => ({
      Rang: it.rank,
      Bezeichnung: it.label,
      Untertitel: it.sublabel ?? '',
      Wert: typeof it.value === 'number' ? Math.round(it.value) : it.value,
      Wert_formatiert: it.value_label,
      Vorhaben: it.project_count ?? '',
      Bundesland: it.bundesland ?? '',
      Fonds: it.fonds ?? '',
      Quellen_Anzahl: it.source_count ?? '',
      Quellen_Breakdown: (it.sources_breakdown ?? [])
        .map((sb) => `${sb.fonds ?? sb.source}: ${sb.count}`)
        .join(', '),
    })),
    [analysis],
  );

  const exportFilenameBase = useMemo(
    () => `auswertung_${mode}_${countryCode || 'all'}_${new Date().toISOString().slice(0, 10)}`,
    [mode, countryCode],
  );

  const canExport = (analysis?.items?.length ?? 0) > 0 && !loading;

  const handleExport = async (format: 'xlsx' | 'csv' | 'pdf') => {
    if (!canExport || exporting) return;
    setExporting(format);
    try {
      if (format === 'csv') {
        exportApi.toCsv(exportRows, { filename: exportFilenameBase });
      } else if (format === 'xlsx') {
        await exportApi.toXlsx(exportRows, {
          filename: exportFilenameBase,
          sheetName: currentOption?.label ?? 'Auswertung',
        });
      } else if (format === 'pdf') {
        const target = exportTargetRef.current;
        if (target) {
          await exportApi.toPdf(target, {
            filename: exportFilenameBase,
            title: analysis?.title ?? 'Begünstigten-Auswertung',
            subtitle: `Stand ${new Date().toLocaleDateString('de-DE')} · ${analysis?.summary?.total_volume_label ?? ''}`,
          });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export fehlgeschlagen.');
    } finally {
      setExporting(null);
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
          <span className="text-slate-500 dark:text-slate-400">{regionLabel}</span>
          <select
            value={bundesland}
            onChange={(event) => setBundesland(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-rose-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          >
            <option value="">{`Alle ${regionLabel === 'Bundesland' ? 'Bundesländer' : `${regionLabel}e`}`}</option>
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
        <div className="flex flex-wrap items-center justify-end gap-2 self-end">
          <button
            onClick={() => handleExport('xlsx')}
            disabled={!canExport || Boolean(exporting)}
            title="Trefferliste als Excel-Datei exportieren"
            className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-900/40"
          >
            <FileSpreadsheet size={13} className={exporting === 'xlsx' ? 'animate-pulse' : ''} />
            XLSX
          </button>
          <button
            onClick={() => handleExport('csv')}
            disabled={!canExport || Boolean(exporting)}
            title="Trefferliste als CSV exportieren"
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <FileText size={13} className={exporting === 'csv' ? 'animate-pulse' : ''} />
            CSV
          </button>
          <button
            onClick={() => handleExport('pdf')}
            disabled={!canExport || Boolean(exporting)}
            title="Trefferliste als PDF exportieren"
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <FileDown size={13} className={exporting === 'pdf' ? 'animate-pulse' : ''} />
            PDF
          </button>
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 dark:bg-rose-500 dark:hover:bg-rose-400 dark:disabled:bg-slate-700"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Neu laden
          </button>
        </div>
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
          <div ref={exportTargetRef} className="mt-5 rounded-[28px] border border-slate-200/80 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-950/50">
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
                            <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">{rewriteAnalyticsLabel(item)}</div>
                            {(() => {
                              const sub = rewriteAnalyticsSublabel(item);
                              return sub ? (
                                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{sub}</div>
                              ) : null;
                            })()}
                            {item.sources_breakdown && item.sources_breakdown.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {item.sources_breakdown.map((sb, i) => {
                                  // Wenn ein Bundesland mehrere Sources mit
                                  // gleichem Fonds hat (z.B. Brandenburg
                                  // EFRE 2014-2020 + EFRE 2021-2027), die
                                  // Foerderperiode aus dem source-Key
                                  // (Suffix nach Fonds) ableiten und im Tag
                                  // anzeigen, sonst sind die Tags
                                  // ununterscheidbar.
                                  const fondsLabel = sb.fonds ?? sb.source;
                                  const sameFondsCount = (item.sources_breakdown || [])
                                    .filter((x) => x.fonds === sb.fonds).length;
                                  let suffix = '';
                                  if (sameFondsCount > 1 && sb.fonds) {
                                    const periodMatch = sb.source.match(/(\d{4})[_-](\d{4})/);
                                    if (periodMatch) {
                                      suffix = ` ${periodMatch[1].slice(2)}-${periodMatch[2].slice(2)}`;
                                    }
                                  }
                                  return (
                                    <span
                                      key={`${sb.source}-${i}`}
                                      className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                                      title={`${sb.value_label} aus Quelle ${sb.source}`}
                                    >
                                      {fondsLabel}{suffix}: {sb.count.toLocaleString('de-DE')}
                                    </span>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                        {/*
                          Die Balkenbreite skaliert mit item.value — dessen
                          Einheit wechselt je nach Modus zwischen Euro
                          (Fördervolumen) und Anzahl (Vorhaben). Per
                          aria-label/title kenntlich machen, damit der
                          Einheitswechsel nicht stillschweigend bleibt.
                        */}
                        <div
                          className="mt-3 h-3 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"
                          role="img"
                          aria-label={`Anteil am Maximalwert (${analysis.metric_label}): ${item.value_label}`}
                          title={`Balken skaliert nach ${analysis.metric_label}`}
                        >
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

            {/* Summen-Footer am Ende der Liste */}
            {(() => {
              const totalProjects = analysis.items.reduce(
                (sum, it) => sum + (typeof it.project_count === 'number' ? it.project_count : 0),
                0,
              );
              // data_source ist (noch) nicht im API-Typ deklariert — optional
              // auslesen, damit die Datenquelle (zentrale Tabelle vs.
              // Verzeichnislisten) für den Prüfer transparent ist.
              const dataSource = (analysis.summary as { data_source?: string } | undefined)?.data_source;
              return (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/80 px-4 py-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300">
                  <span>
                    <strong className="font-semibold text-slate-900 dark:text-white">
                      {formatInt(analysis.items.length)}
                    </strong>
                    {' '}{analysis.items.length === 1 ? 'Eintrag' : 'Einträge'} angezeigt
                    {typeof analysis.summary?.records_scanned === 'number' && (
                      <>
                        {' '}· Datengrundlage{' '}
                        <strong className="font-semibold text-slate-900 dark:text-white">
                          {formatInt(analysis.summary.records_scanned)}
                        </strong>{' '}Datensätze
                      </>
                    )}
                    {dataSource && (
                      <span className="text-slate-400 dark:text-slate-500"> · Quelle: {dataSource}</span>
                    )}
                  </span>
                  <span className="flex flex-wrap items-center gap-x-4">
                    {totalProjects > 0 && (
                      <span>
                        Vorhaben:{' '}
                        <strong className="font-mono text-sm font-semibold text-slate-900 dark:text-white">
                          {formatInt(totalProjects)}
                        </strong>
                      </span>
                    )}
                    {analysis.summary?.total_volume_label && (
                      <span>
                        {/*
                          Bei Zähl-Modi (metric_label === 'Vorhaben') ist die
                          Primärkennzahl die Vorhaben-Anzahl (oben). Das globale
                          Euro-Volumen daher klar als „zugehöriges Fördervolumen"
                          ausweisen statt als blankes „Summe" — sonst liest es
                          sich wie eine Spaltensumme der Anzahl.
                        */}
                        {analysis.metric_label === 'Vorhaben'
                          ? 'zugehöriges Fördervolumen: '
                          : 'Summe: '}
                        <strong className="font-mono text-sm font-semibold text-slate-900 dark:text-white">
                          {analysis.summary.total_volume_label}
                        </strong>
                      </span>
                    )}
                  </span>
                </div>
              );
            })()}
          </div>
        </>
      )}
    </div>
  );
}
