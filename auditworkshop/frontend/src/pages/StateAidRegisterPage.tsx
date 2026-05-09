/**
 * StateAidRegisterPage — EU-Beihilfe-Transparenzregister.
 *
 * Plan §9: Tabs Treffer | Karte | Auswertung | KI-Suche.
 * Pflichthinweis (Plan §13) ueber dem ersten Tab. Filter sind in der
 * Search-Panel-Komponente.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, BarChart3, Banknote, BrainCircuit, Building2,
  ChevronDown, ChevronRight, FileDown, FileSearch, FileSpreadsheet, FileText, Info, Layers, Loader2,
  MapPin, Sparkles, X,
} from 'lucide-react';
import StateAidSearchPanel from '../components/state_aid/StateAidSearchPanel';
import {
  DEFAULT_FILTERS,
  clearFilterField,
  filtersToParams,
  getActiveFilterChips,
  type StateAidFilterState,
} from '../components/state_aid/stateAidFilters';
import StateAidResultsTable from '../components/state_aid/StateAidResultsTable';
import StateAidAwardDetail from '../components/state_aid/StateAidAwardDetail';
import StateAidMap, {
  type StateAidRegionClickPayload,
} from '../components/state_aid/StateAidMap';
import StateAidAskPanel from '../components/state_aid/StateAidAskPanel';
import StateAidErrorBoundary from '../components/state_aid/StateAidErrorBoundary';
import {
  exportUrl,
  getSources,
  getStats,
  getStatus,
  search as searchAwards,
  statsExportUrl,
  type StateAidAward,
  type StateAidSearchHit,
  type StateAidSearchResponse,
  type StateAidSource,
  type StateAidStatsResponse,
  type StateAidStatus,
} from '../lib/stateAidApi';
import ExportButtons from '../components/ui/ExportButtons';
import Stat from '../components/ui/Stat';

type TabKey = 'hits' | 'map' | 'stats' | 'ask';

const TABS: Array<{ key: TabKey; label: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = [
  { key: 'hits', label: 'Treffer', icon: FileSearch },
  { key: 'map', label: 'Karte', icon: MapPin },
  { key: 'stats', label: 'Auswertung', icon: BarChart3 },
  { key: 'ask', label: 'KI-Suche', icon: BrainCircuit },
];

function formatEur(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value);
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('de-DE', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function StateAidRegisterPage() {
  return (
    <StateAidErrorBoundary scope="register-page">
      <StateAidRegisterPageInner />
    </StateAidErrorBoundary>
  );
}

function StateAidRegisterPageInner() {
  const [activeTab, setActiveTab] = useState<TabKey>('hits');

  const [filters, setFilters] = useState<StateAidFilterState>(DEFAULT_FILTERS);
  const [searchResult, setSearchResult] = useState<StateAidSearchResponse | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedAward, setSelectedAward] = useState<StateAidAward | null>(null);
  // Klar lesbares Label fuer den NUTS-Code-Chip („DE7 (Hessen)") — nur gesetzt,
  // wenn die Region per Karten-Klick uebernommen wurde.
  const [nutsLabel, setNutsLabel] = useState<string | null>(null);

  const [status, setStatus] = useState<StateAidStatus | null>(null);
  const [sources, setSources] = useState<StateAidSource[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);

  const [stats, setStats] = useState<StateAidStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const [statusRes, sourcesRes] = await Promise.all([
        getStatus().catch(() => null),
        getSources().catch(() => ({ sources: [] as StateAidSource[] })),
      ]);
      setStatus(statusRes);
      setSources(sourcesRes.sources || []);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  // Initialer Default-Search auf Land-Filter (DE).
  useEffect(() => {
    runSearch(DEFAULT_FILTERS);
  }, []);

  async function runSearch(state: StateAidFilterState) {
    setSearchBusy(true);
    setSearchError(null);
    try {
      const params = filtersToParams(state);
      params.limit = params.limit ?? 100;
      const res = await searchAwards(params);
      setSearchResult(res);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Suche fehlgeschlagen.');
      setSearchResult(null);
    } finally {
      setSearchBusy(false);
    }
  }

  /**
   * Plan §8.3 Modus 3: Karten-Klick → NUTS-Filter setzen, Treffer-Tab
   * aktivieren und Suche neu ausloesen.
   */
  function handleMapRegionClick(point: StateAidRegionClickPayload) {
    const next: StateAidFilterState = {
      ...filters,
      nuts_code: point.nuts_code,
    };
    setFilters(next);
    setNutsLabel(point.nuts_label || null);
    setActiveTab('hits');
    runSearch(next);
  }

  /** Entfernt einen Filter-Chip und triggert Re-Submit. */
  function handleRemoveFilter(key: keyof StateAidFilterState) {
    const next = clearFilterField(filters, key);
    setFilters(next);
    if (key === 'nuts_code') setNutsLabel(null);
    runSearch(next);
  }

  /**
   * Uebernimmt LLM-extrahierte Filter aus der KI-Suche, wechselt zum
   * Treffer-Tab und triggert die regulaere Suche.
   */
  function handleApplyAskFilters(patch: Partial<StateAidFilterState>) {
    const next: StateAidFilterState = { ...filters, ...patch };
    setFilters(next);
    // NUTS-Label vom Karten-Klick ist nicht mehr passend, wenn der LLM einen
    // anderen Code erkennt.
    if (typeof patch.nuts_code === 'string') setNutsLabel(null);
    setActiveTab('hits');
    runSearch(next);
  }

  const searchParams = useMemo(() => filtersToParams(filters), [filters]);
  const activeChips = useMemo(() => getActiveFilterChips(filters, nutsLabel), [filters, nutsLabel]);

  // Stats laden, sobald Tab oder Land-Filter wechselt.
  useEffect(() => {
    if (activeTab !== 'stats') return;
    let cancelled = false;
    setStatsLoading(true);
    setStatsError(null);
    getStats({
      country_code: filters.country_code || undefined,
      since: filters.since || undefined,
      until: filters.until || undefined,
    })
      .then((res) => { if (!cancelled) setStats(res); })
      .catch((err: unknown) => {
        if (!cancelled) setStatsError(err instanceof Error ? err.message : 'Auswertung konnte nicht geladen werden.');
      })
      .finally(() => { if (!cancelled) setStatsLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab, filters.country_code, filters.since, filters.until]);

  return (
    <div className="space-y-6">
      {/* ── Hero ────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(7,46,40,0.98),rgba(16,94,82,0.94)_45%,rgba(45,160,130,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight lg:text-4xl">Beihilfe-Register</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-emerald-50/85 lg:text-base">
              Lokal gespeicherte, öffentlich zugängliche Beihilfe-Transparenzdaten —
              Suche, Karte, Auswertung. Verlinkt SA-Referenzen auf die Competition
              Cases Search. Fällt das Internet aus, bleibt die Suche verfügbar.
            </p>
          </div>
          <div className="rounded-[28px] border border-white/15 bg-black/15 p-5 backdrop-blur">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/60">Lokaler Workshop-Index</div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <Stat label="Beihilfen" value={status?.total_awards.toLocaleString('de-DE') ?? '—'} />
              <Stat label="Aktive Quellen" value={status?.sources_enabled ?? '—'} />
              <Stat label="Harvest-Läufe" value={status?.total_runs ?? '—'} />
            </div>
            {sources.filter((s) => (s.record_count ?? 0) > 0).length > 0 && (
              <div className="mt-4 space-y-1 text-[11px] text-white/70">
                {sources.filter((s) => (s.record_count ?? 0) > 0).slice(0, 3).map((s) => (
                  <div key={s.source_key} className="flex items-center justify-between">
                    <span className="truncate" title={s.display_name}>{s.display_name}</span>
                    <span className="font-mono">{s.record_count.toLocaleString('de-DE')}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-3 text-[10px] uppercase tracking-[0.18em] text-white/50">
              Letzter Harvest <span className="ml-1 font-mono normal-case tracking-normal text-white/70">{formatDateTime(status?.last_harvest_at ?? null)}</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Pflicht-Hinweis (Plan §13) ──────────────────────────────── */}
      <section className="rounded-[28px] border border-amber-200/70 bg-amber-50/80 px-5 py-4 shadow-[0_20px_70px_-48px_rgba(180,83,9,0.35)] dark:border-amber-500/30 dark:bg-amber-950/30">
        <div className="flex items-start gap-3 text-sm leading-6 text-amber-900 dark:text-amber-100">
          <Info size={18} className="mt-0.5 shrink-0" />
          <p>
            Dieses Register bildet lokal gespeicherte, öffentlich zugängliche
            Beihilfe-Transparenzdaten ab. Die Vollständigkeit hängt vom
            Veröffentlichungsweg der Mitgliedstaaten und vom letzten
            Harvest-Zeitpunkt ab.
            {status?.coverage_note ? <span className="ml-1 opacity-80">{status.coverage_note}</span> : null}
          </p>
        </div>
      </section>

      {/* ── Tabs (Pill-Bar) ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex flex-wrap gap-1 rounded-full border border-slate-200 bg-white p-1 shadow-[0_18px_60px_-44px_rgba(15,23,42,0.45)] dark:border-slate-700 dark:bg-slate-900">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition ${
                  active
                    ? 'bg-slate-900 text-white shadow-[0_12px_28px_-18px_rgba(15,23,42,0.8)] dark:bg-emerald-500 dark:text-slate-950'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                }`}
                aria-pressed={active}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
        {statusLoading && <Loader2 size={14} className="animate-spin text-slate-400" />}
      </div>

      {/* ── Tab-Inhalt ──────────────────────────────────────────────── */}
      {activeTab === 'hits' && (
        <section className="grid gap-4">
          {/* Linke Spalte: Suche + Filter-Chips + Trefferliste + Methodik + Export */}
          <div className="space-y-4">
            <StateAidSearchPanel
              value={filters}
              onChange={(next) => {
                // Wenn der NUTS-Code manuell geaendert wird, das menschliche
                // Label aus dem Karten-Klick verwerfen — sonst bleibt im Chip
                // ein veraltetes "DE7 (Hessen)" stehen.
                if (next.nuts_code !== filters.nuts_code) setNutsLabel(null);
                setFilters(next);
              }}
              onSubmit={runSearch}
              onReset={() => {
                setFilters(DEFAULT_FILTERS);
                setNutsLabel(null);
                runSearch(DEFAULT_FILTERS);
              }}
              sources={sources}
              busy={searchBusy}
            />

            <SearchHelpBox />

            {activeChips.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 rounded-[26px] border border-emerald-200/70 bg-emerald-50/70 px-4 py-3 text-xs dark:border-emerald-500/30 dark:bg-emerald-950/30">
                <span className="font-medium text-emerald-700 dark:text-emerald-300">Aktive Filter:</span>
                {activeChips.map((chip) => (
                  <button
                    key={`${chip.key}-${chip.value}`}
                    type="button"
                    onClick={() => handleRemoveFilter(chip.key)}
                    className="group inline-flex items-center gap-1 rounded-full border border-emerald-300 bg-white px-2.5 py-0.5 font-medium text-emerald-800 shadow-sm transition hover:border-emerald-400 hover:bg-emerald-50 dark:border-emerald-500/40 dark:bg-slate-900 dark:text-emerald-200 dark:hover:bg-slate-800"
                    title="Filter entfernen"
                    aria-label={`Filter ${chip.label} entfernen`}
                  >
                    <span className="flex flex-col items-start leading-tight">
                      <span>{chip.label}: <span className="font-semibold">{chip.value}</span></span>
                      {chip.hint && (
                        <span className="text-[10px] font-normal text-emerald-600/80 dark:text-emerald-300/70">
                          {chip.hint}
                        </span>
                      )}
                    </span>
                    <X size={12} className="opacity-60 group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            )}

            {searchError && (
              <div className="flex items-start gap-2 rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <span>{searchError}</span>
              </div>
            )}

            {searchResult && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-[26px] border border-slate-200/80 bg-white/90 px-4 py-3 text-xs shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] dark:border-slate-700 dark:bg-slate-900/75">
                <div className="flex flex-wrap items-center gap-2 text-slate-500 dark:text-slate-400">
                  <span>
                    <span className="font-semibold text-slate-700 dark:text-slate-200">
                      {searchResult.total_hits.toLocaleString('de-DE')}
                    </span>{' '}
                    Treffer
                    {searchResult.threshold > 0 && <span> · Schwelle {searchResult.threshold}</span>}
                    {searchResult.normalized && (
                      <span> · normalisiert: <span className="font-mono">{searchResult.normalized}</span></span>
                    )}
                  </span>
                  {Object.entries(searchResult.filters_applied).map(([k, v]) => (
                    <span key={k} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {k}: <span className="font-medium">{v}</span>
                    </span>
                  ))}
                </div>
                <ResultsExportButtons
                  params={searchParams}
                  disabled={searchResult.hits.length === 0}
                />
              </div>
            )}

            <StateAidResultsTable
              hits={searchResult?.hits ?? []}
              onSelect={(hit: StateAidSearchHit) => setSelectedAward(hit)}
              loading={searchBusy}
            />
          </div>

        </section>
      )}

      {activeTab === 'map' && (
        <section className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                <MapPin size={20} />
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white">Räumliche Verteilung der Beihilfen</div>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  NUTS-Aggregation als Kreise oder Choropleth-Flächen.
                </div>
              </div>
            </div>
            <div className="inline-flex flex-wrap gap-1 rounded-full border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
              {([
                { code: 'DE', label: 'DE' },
                { code: 'AT', label: 'AT' },
                { code: '', label: 'EU' },
              ] as const).map((opt) => {
                const active = filters.country_code === opt.code;
                return (
                  <button
                    key={opt.code || 'all'}
                    type="button"
                    onClick={() => setFilters({ ...filters, country_code: opt.code })}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                      active
                        ? 'bg-emerald-600 text-white shadow-sm'
                        : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
          <StateAidMap
            countryCode={filters.country_code}
            since={filters.since || undefined}
            until={filters.until || undefined}
            onRegionClick={handleMapRegionClick}
          />
        </section>
      )}

      {activeTab === 'stats' && (
        <StatsTab
          loading={statsLoading}
          error={statsError}
          stats={stats}
          filters={filters}
          onDrillDown={(query) => {
            const next: StateAidFilterState = { ...filters, q: query };
            setFilters(next);
            setActiveTab('hits');
            runSearch(next);
          }}
        />
      )}

      {activeTab === 'ask' && (
        <StateAidAskPanel
          countryCode={filters.country_code}
          onApplyFilters={handleApplyAskFilters}
        />
      )}

      <StateAidAwardDetail award={selectedAward} onClose={() => setSelectedAward(null)} />
    </div>
  );
}

// ── Hilfskomponenten ─────────────────────────────────────────────────────────

function StatsTab({ loading, error, stats, filters, onDrillDown }: { loading: boolean; error: string | null; stats: StateAidStatsResponse | null; filters: StateAidFilterState; onDrillDown?: (query: string) => void }) {
  const exportParams = useMemo(() => filtersToParams(filters), [filters]);
  const handleStatsExport = useCallback(() => {
    const url = statsExportUrl(exportParams);
    const a = document.createElement('a');
    a.href = url;
    a.rel = 'noopener noreferrer';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, [exportParams]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-[30px] border border-slate-200/80 bg-white/88 px-6 py-10 text-sm text-slate-500 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75 dark:text-slate-400">
        <Loader2 size={16} className="animate-spin" /> Lade Auswertung …
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }
  if (!stats) return null;

  const yearMax = (stats.by_year || []).reduce((m, y) => Math.max(m, y.count), 0) || 1;

  return (
    <section className="grid gap-4 lg:grid-cols-2">
      <div className="lg:col-span-2 flex flex-wrap items-center justify-between gap-3 rounded-[26px] border border-slate-200/80 bg-white/90 px-4 py-3 shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <div className="text-xs text-slate-500 dark:text-slate-400">
          Statistiken als Excel-Datei mit fünf Sheets exportieren (Behörden, Begünstigte, NUTS, Instrumente, Jahre).
        </div>
        <ExportButtons
          formats={['xlsx']}
          onExport={handleStatsExport}
        />
      </div>
      <BucketCard
        title="Top Begünstigte"
        subtitle="Hauptempfänger der Beihilfen"
        labelHeader="Begünstigter"
        buckets={stats.top_beneficiaries}
        icon={Building2}
        onPick={onDrillDown}
        drillHint="In der Trefferliste anzeigen"
      />
      <BucketCard
        title="Top Behörden"
        subtitle="Bewilligende Stellen"
        labelHeader="Behörde"
        buckets={stats.top_authorities}
        icon={Layers}
        onPick={onDrillDown}
        drillHint="In der Trefferliste anzeigen"
      />
      <BucketCard
        title="Top Beihilfeziele"
        subtitle="Förderzwecke und Programme"
        labelHeader="Beihilfeziel"
        buckets={stats.top_objectives}
        icon={Sparkles}
      />
      <BucketCard
        title="Top Beihilfeinstrumente"
        subtitle="Zuschuss, Darlehen, Bürgschaft …"
        labelHeader="Instrument"
        buckets={stats.top_instruments}
        icon={Banknote}
      />
      {stats.by_year && stats.by_year.length > 0 && (
        <div className="lg:col-span-2 rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
              <BarChart3 size={16} />
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-900 dark:text-white">Jahresverteilung</div>
              <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                Anzahl Beihilfen pro Bewilligungsjahr · Volumen rechts.
              </div>
            </div>
          </div>
          <div className="rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
            <div className="space-y-2">
              {stats.by_year.map((y) => {
                const w = (y.count / yearMax) * 100;
                return (
                  <div key={y.year} className="flex items-center gap-3 text-xs">
                    <div className="w-12 shrink-0 font-mono text-slate-500 dark:text-slate-400">{y.year}</div>
                    <div className="relative flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                      <div
                        className="h-2 rounded-full bg-emerald-500"
                        style={{ width: `${Math.max(w, 2)}%` }}
                      />
                    </div>
                    <div className="w-20 shrink-0 text-right font-mono text-slate-600 dark:text-slate-300">
                      {y.count.toLocaleString('de-DE')}
                    </div>
                    <div className="hidden w-32 shrink-0 text-right font-mono text-slate-500 md:block">
                      {formatEur(y.total_eur)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function BucketCard({
  title,
  subtitle,
  labelHeader,
  buckets,
  icon: Icon,
  onPick,
  drillHint,
}: {
  title: string;
  subtitle?: string;
  labelHeader: string;
  buckets?: Array<{ label: string; count: number; total_eur: number | null }>;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  onPick?: (query: string) => void;
  drillHint?: string;
}) {
  if (!buckets || buckets.length === 0) {
    return (
      <div className="rounded-[26px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
            <Icon size={16} />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900 dark:text-white">{title}</div>
            {subtitle && <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>}
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Keine Daten für den aktuellen Filter.</p>
      </div>
    );
  }
  const clickable = !!onPick;
  return (
    <div className="rounded-[26px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
          <Icon size={16} />
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white">{title}</div>
          {subtitle && <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>}
        </div>
      </div>
      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-900/60">
            <tr className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <th scope="col" className="w-10 px-2 py-2 text-right">Rang</th>
              <th scope="col" className="px-3 py-2 text-left">{labelHeader}</th>
              <th scope="col" className="w-20 px-2 py-2 text-right">Anzahl</th>
              <th scope="col" className="hidden w-32 px-2 py-2 text-right md:table-cell">Volumen (EUR)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {buckets.slice(0, 10).map((b, idx) => {
              const handleClick = () => { if (onPick && b.label) onPick(b.label); };
              return (
                <tr
                  key={`${b.label}-${idx}`}
                  className={clickable
                    ? 'cursor-pointer transition hover:bg-emerald-50/60 dark:hover:bg-emerald-950/20'
                    : 'transition hover:bg-slate-50 dark:hover:bg-slate-800/50'}
                  onClick={clickable ? handleClick : undefined}
                  onKeyDown={clickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick(); } } : undefined}
                  role={clickable ? 'button' : undefined}
                  tabIndex={clickable ? 0 : undefined}
                  title={clickable ? (drillHint || 'In der Trefferliste anzeigen') : b.label}
                >
                  <td className="px-2 py-2 text-right align-top font-mono text-xs text-slate-400">{idx + 1}</td>
                  <td className="px-3 py-2 align-top">
                    <span className="block whitespace-normal break-words text-slate-800 dark:text-slate-100">
                      {b.label || <span className="italic text-slate-400">— ohne Bezeichnung —</span>}
                    </span>
                    {clickable && (
                      <span className="mt-0.5 block text-[10px] text-emerald-700/80 dark:text-emerald-300/70">
                        {drillHint || 'Klicken: in der Trefferliste anzeigen'}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right align-top font-mono text-[12px] text-slate-700 dark:text-slate-200">
                    {b.count.toLocaleString('de-DE')}
                  </td>
                  <td className="hidden px-2 py-2 text-right align-top font-mono text-[11px] text-slate-500 md:table-cell">
                    {formatEur(b.total_eur)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * SearchHelpBox — einklappbarer Hilfs-Hinweis am Sucheingabe-Feld.
 *
 * Zwei Themen:
 *   1. Wie die Anfrage Treffer priorisiert (statt der frueheren Methodik-Sektion).
 *   2. Wie die Schreibweise vor dem Vergleich vereinheitlicht wird (Normalisierung).
 *
 * Verwaltungssprache, kein Tech-Jargon ("rapidfuzz", "token_set_ratio",
 * "Workshop-Stack" wurden bewusst entfernt — der Pruefer interessiert das
 * Ergebnis, nicht die Implementierung).
 */
function SearchHelpBox() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-[26px] border border-cyan-200/70 bg-cyan-50/60 px-5 py-3 text-sm leading-6 text-cyan-900 shadow-[0_18px_60px_-48px_rgba(8,145,178,0.45)] dark:border-cyan-500/30 dark:bg-cyan-950/30 dark:text-cyan-100">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 text-left"
        aria-expanded={open}
      >
        <Info size={18} className="shrink-0 text-cyan-600 dark:text-cyan-300" />
        <div className="flex-1">
          <div className="font-semibold">Hinweise zur Suche</div>
          <p className="text-[12px] leading-5 text-cyan-800/85 dark:text-cyan-100/80">
            Wie das System Treffer findet und Schreibweisen ausgleicht — bei Bedarf einblenden.
          </p>
        </div>
        {open
          ? <ChevronDown size={16} className="shrink-0 text-cyan-700/80 dark:text-cyan-200/80" />
          : <ChevronRight size={16} className="shrink-0 text-cyan-700/80 dark:text-cyan-200/80" />}
      </button>
      {open && (
        <div className="mt-3 space-y-3 border-t border-cyan-200/60 pt-3 text-[13px] leading-6 dark:border-cyan-500/20">
          <section>
            <h4 className="font-semibold">Wie sucht das System?</h4>
            <p className="mt-1 text-cyan-900/90 dark:text-cyan-50/85">
              Eine Anfrage durchsucht den Begünstigten-Namen und die Bewilligungsstelle aller
              geladenen öffentlichen Quellen gleichzeitig. Sie müssen nicht zuerst Bund, Land
              oder Förderbank auswählen.
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-cyan-900/90 dark:text-cyan-50/85">
              <li>Treffer mit identischer Schreibweise stehen vorn.</li>
              <li>
                Danach folgen ähnliche Schreibweisen — etwa kleinere Tippfehler, abweichende
                Wortreihenfolge oder andere Rechtsformzusätze.
              </li>
              <li>
                Datum, Land und NUTS-Region grenzen die Treffer zusätzlich ein, sobald
                Sie die entsprechenden Filter setzen.
              </li>
            </ul>
          </section>
          <section>
            <h4 className="font-semibold">Schreibweise wird vereinheitlicht</h4>
            <p className="mt-1 text-cyan-900/90 dark:text-cyan-50/85">
              Anfrage und Datensatz werden vor dem Vergleich in eine einfache Form gebracht:
              Großbuchstaben, Akzente und Sonderzeichen werden weggelassen, Rechtsformzusätze
              wie GmbH, AG oder e. V. bleiben unberücksichtigt. So findet die Suche
              „Müller-Schmidt GmbH" auch dann, wenn der Datensatz „MUELLER SCHMIDT" lautet.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

/**
 * ResultsExportButtons — kompakte Export-Buttons (CSV/XLSX/PDF) im Trefferzaehler-Header,
 * analog zur Begünstigtensuche. Nutzt direkt die Backend-Export-URL.
 */
function ResultsExportButtons({ params, disabled }: { params: Parameters<typeof exportUrl>[1]; disabled?: boolean }) {
  function trigger(format: 'csv' | 'xlsx' | 'pdf') {
    if (disabled) return;
    const url = exportUrl(format, params);
    const a = document.createElement('a');
    a.href = url;
    a.rel = 'noopener noreferrer';
    a.target = '_self';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => trigger('xlsx')}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
        title="Trefferliste als XLSX exportieren"
      >
        <FileSpreadsheet size={12} /> XLSX
      </button>
      <button
        type="button"
        onClick={() => trigger('csv')}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
        title="Trefferliste als CSV exportieren"
      >
        <FileDown size={12} /> CSV
      </button>
      <button
        type="button"
        onClick={() => trigger('pdf')}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
        title="Trefferliste als PDF exportieren"
      >
        <FileText size={12} /> PDF
      </button>
    </div>
  );
}
