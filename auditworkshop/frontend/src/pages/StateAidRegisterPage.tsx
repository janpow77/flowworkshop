/**
 * StateAidRegisterPage — EU-Beihilfe-Transparenzregister.
 *
 * Plan §9: Tabs Treffer | Karte | Auswertung | Quellen | Dossier.
 * Pflichthinweis (Plan §13) ueber dem ersten Tab. Filter sind in der
 * Search-Panel-Komponente; Dossier kombiniert Beguenstigte, Beihilfen
 * und Sanktionen registeruebergreifend.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, BadgeCheck, BarChart3, Banknote, BrainCircuit, Building2,
  CheckCircle2, ClipboardCheck, Coins, Database, FileSearch, Globe2, Info, Layers, Layers3, Loader2,
  MapPin, Search, ShieldAlert, Sparkles, X,
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
import StateAidSourceStatus from '../components/state_aid/StateAidSourceStatus';
import StateAidExportActions from '../components/state_aid/StateAidExportActions';
import StateAidAskPanel from '../components/state_aid/StateAidAskPanel';
import StateAidValidatorBadge from '../components/state_aid/StateAidValidatorBadge';
import StateAidErrorBoundary from '../components/state_aid/StateAidErrorBoundary';
import {
  deleteSource as apiDeleteSource,
  getDossier,
  getSources,
  getStats,
  getStatus,
  search as searchAwards,
  triggerHarvest,
  type HarvestMode,
  type HarvestResult,
  type StateAidAward,
  type StateAidDossierResponse,
  type StateAidSearchHit,
  type StateAidSearchResponse,
  type StateAidSource,
  type StateAidStatsResponse,
  type StateAidStatus,
} from '../lib/stateAidApi';

type TabKey = 'hits' | 'map' | 'stats' | 'sources' | 'dossier' | 'ask';

const TABS: Array<{ key: TabKey; label: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = [
  { key: 'hits', label: 'Treffer', icon: FileSearch },
  { key: 'map', label: 'Karte', icon: MapPin },
  { key: 'stats', label: 'Auswertung', icon: BarChart3 },
  { key: 'sources', label: 'Quellen', icon: Database },
  { key: 'dossier', label: 'Dossier', icon: Building2 },
  { key: 'ask', label: 'KI-Suche', icon: BrainCircuit },
];

const INFO_DISMISSED_KEY = 'state-aid-info-dismissed';

function readInfoDismissed(): boolean {
  try {
    return localStorage.getItem(INFO_DISMISSED_KEY) === 'true';
  } catch {
    return false;
  }
}

function persistInfoDismissed(): void {
  try {
    localStorage.setItem(INFO_DISMISSED_KEY, 'true');
  } catch {
    /* localStorage in iframe blockiert — Banner bleibt halt sichtbar. */
  }
}

function isAdminUser(): boolean {
  const role = localStorage.getItem('workshop_role');
  return role === 'moderator' || role === 'admin';
}

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
  const [infoDismissed, setInfoDismissed] = useState<boolean>(() => readInfoDismissed());

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

  const [dossierQuery, setDossierQuery] = useState('');
  const [dossier, setDossier] = useState<StateAidDossierResponse | null>(null);
  const [dossierBusy, setDossierBusy] = useState(false);
  const [dossierError, setDossierError] = useState<string | null>(null);

  const isAdmin = isAdminUser();

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

  /** Klick auf Schliess-Button im Info-Banner — Auswahl persistent ablegen. */
  function handleDismissInfo() {
    setInfoDismissed(true);
    persistInfoDismissed();
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

  async function runDossier(e?: FormEvent) {
    e?.preventDefault();
    const q = dossierQuery.trim();
    if (q.length < 2) {
      setDossierError('Bitte mindestens 2 Zeichen eingeben.');
      setDossier(null);
      return;
    }
    setDossierBusy(true);
    setDossierError(null);
    try {
      const res = await getDossier(q);
      setDossier(res);
    } catch (err) {
      setDossierError(err instanceof Error ? err.message : 'Dossier-Abfrage fehlgeschlagen.');
      setDossier(null);
    } finally {
      setDossierBusy(false);
    }
  }

  async function handleHarvest(source: StateAidSource, mode: HarvestMode): Promise<HarvestResult> {
    // Hinweis: Fehler nicht abfangen — die Komponente zeigt sie inline statt via alert().
    const result = await triggerHarvest({
      country: source.country_code || filters.country_code || 'DE',
      regions: [],
      source_key: source.source_key,
      mode,
    });
    await refreshStatus();
    return result;
  }

  async function handleDeleteSource(source: StateAidSource) {
    try {
      await apiDeleteSource(source.source_key);
      await refreshStatus();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Loeschen fehlgeschlagen.';
      alert(msg);
    }
  }

  return (
    <div className="space-y-6">
      {/* ── Hero ────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(7,46,40,0.98),rgba(16,94,82,0.94)_45%,rgba(45,160,130,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-100/80">
                <Coins size={13} /> EU-Beihilfe-Transparenzregister
              </span>
              <StateAidValidatorBadge />
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight lg:text-4xl">Beihilfe-Register</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-emerald-50/85 lg:text-base">
              Lokal gespeicherte, oeffentlich zugaengliche Beihilfe-Transparenzdaten —
              Suche, Karte, Auswertung. Verlinkt SA-Referenzen auf die Competition
              Cases Search. Faellt das Internet aus, bleibt die Suche verfuegbar.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
            <div className="rounded-[26px] border border-white/15 bg-black/10 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-emerald-100/60">Awards</div>
              <div className="mt-2 text-2xl font-semibold">{status?.total_awards.toLocaleString('de-DE') ?? '—'}</div>
              <div className="mt-1 text-sm text-emerald-50/70">Lokale Beihilfe-Transparenzdaten im Workshop-Index.</div>
            </div>
            <div className="rounded-[26px] border border-white/15 bg-black/10 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-emerald-100/60">Aktive Quellen</div>
              <div className="mt-2 text-2xl font-semibold">{status?.sources_enabled ?? '—'}</div>
              <div className="mt-1 text-sm text-emerald-50/70">{status?.total_runs ?? 0} Harvest-Laeufe insgesamt.</div>
            </div>
            <div className="rounded-[26px] border border-white/15 bg-black/10 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-emerald-100/60">Letzter Harvest</div>
              <div className="mt-2 text-base font-semibold font-mono">{formatDateTime(status?.last_harvest_at ?? null)}</div>
              <div className="mt-1 text-sm text-emerald-50/70">Aktualitaet je Quelle siehe Tab „Quellen".</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Pflicht-Hinweis (Plan §13) ──────────────────────────────── */}
      <section className="rounded-[28px] border border-amber-200/70 bg-amber-50/80 px-5 py-4 shadow-[0_20px_70px_-48px_rgba(180,83,9,0.35)] dark:border-amber-500/30 dark:bg-amber-950/30">
        <div className="flex items-start gap-3 text-sm leading-6 text-amber-900 dark:text-amber-100">
          <Info size={18} className="mt-0.5 shrink-0" />
          <p>
            Dieses Register bildet lokal gespeicherte, oeffentlich zugaengliche
            Beihilfe-Transparenzdaten ab. Die Vollstaendigkeit haengt vom
            Veroeffentlichungsweg der Mitgliedstaaten und vom letzten
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
        <section className="grid gap-4 xl:grid-cols-[1.18fr_0.82fr]">
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

            {!infoDismissed && (
              <div className="relative rounded-[26px] border border-cyan-200/70 bg-cyan-50/60 px-5 py-4 text-sm leading-6 text-cyan-900 shadow-[0_18px_60px_-48px_rgba(8,145,178,0.45)] dark:border-cyan-500/30 dark:bg-cyan-950/30 dark:text-cyan-100">
                <div className="flex items-start gap-3 pr-8">
                  <Info size={18} className="mt-0.5 shrink-0 text-cyan-600 dark:text-cyan-300" />
                  <div className="space-y-1">
                    <div className="font-semibold">Eine Suche, alle Koerperschaften</div>
                    <p className="text-[13px] leading-6 text-cyan-800/90 dark:text-cyan-100/85">
                      Anders als das EU-TAM-Portal musst du hier nicht erst die
                      bewilligende Stelle (Bund / Land / Foerderbank) auswaehlen — eine
                      Eingabe nach Unternehmen oder NUTS-Region zeigt automatisch alle
                      Treffer aus saemtlichen Koerperschaften zusammen.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleDismissInfo}
                  className="absolute right-3 top-3 inline-flex h-7 w-7 items-center justify-center rounded-full text-cyan-700/70 transition hover:bg-cyan-100/70 hover:text-cyan-900 dark:text-cyan-200/70 dark:hover:bg-cyan-900/40 dark:hover:text-cyan-100"
                  aria-label="Hinweis schliessen"
                  title="Hinweis schliessen"
                >
                  <X size={14} />
                </button>
              </div>
            )}

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
                <div className="text-slate-500 dark:text-slate-400">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    {searchResult.total_hits.toLocaleString('de-DE')}
                  </span>{' '}
                  Treffer
                  {searchResult.threshold > 0 && <span> · Schwelle {searchResult.threshold}</span>}
                  {searchResult.normalized && (
                    <span> · normalisiert: <span className="font-mono">{searchResult.normalized}</span></span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(searchResult.filters_applied).map(([k, v]) => (
                    <span key={k} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {k}: <span className="font-medium">{v}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <StateAidResultsTable
              hits={searchResult?.hits ?? []}
              onSelect={(hit: StateAidSearchHit) => setSelectedAward(hit)}
              loading={searchBusy}
            />

            {searchResult && searchResult.hits.length > 0 && (
              <div className="flex items-start gap-2 rounded-[22px] border border-slate-200/70 bg-slate-50/70 px-4 py-2 text-[11px] leading-5 text-slate-500 dark:border-slate-700/70 dark:bg-slate-900/40 dark:text-slate-400">
                <Sparkles size={12} className="mt-0.5 shrink-0 text-emerald-500" />
                <span>
                  Fuzzy-Methode: <span className="font-mono">rapidfuzz token_set_ratio</span>
                  {' '}(Casefold + Akzente weg + Rechtsformsuffixe ignoriert).
                </span>
              </div>
            )}

            {searchResult && searchResult.hits.length > 0 && (
              <section className="rounded-[26px] border border-cyan-200/70 bg-cyan-50/60 p-4 text-sm leading-6 text-cyan-900 dark:border-cyan-500/30 dark:bg-cyan-950/30 dark:text-cyan-100">
                <h4 className="font-semibold flex items-center gap-2">
                  <Layers3 className="h-4 w-4" />
                  4-Stufen-Such-Pipeline
                </h4>
                <p className="mt-1">
                  Diese Suche kombiniert vier Verfahren — schnell wo möglich, präzise wo nötig:
                </p>
                <ol className="mt-2 space-y-1 text-sm">
                  <li>
                    <strong>1. Trigram-Index (pg_trgm)</strong> — SQL-Vorfilter über 170k+ Records, ~5 ms
                  </li>
                  <li>
                    <strong>2. rapidfuzz Multi-Algo</strong> — Levenshtein, Jaro-Winkler, token_set, partial; mit Coverage-Penalty gegen False-Positives, ~10 ms
                  </li>
                  <li>
                    <strong>3. bge-m3 Embedding</strong> — semantische Nähe (1024-dim Vektoren); findet auch ohne Token-Overlap, ~100 ms
                  </li>
                  <li>
                    <strong>4. Qwen3-14B LLM</strong> — re-ranked unsichere Matches im Audit-Report (Score 75–89), strukturiertes JSON-Verdict, ~3 Min für Top-20
                  </li>
                </ol>
                <p className="mt-2 text-xs">
                  Daten lokal in PostgreSQL, alle KI-Schritte auf der GPU im Workshop-Stack — kein Cloud-Versand.
                </p>
              </section>
            )}

            <StateAidExportActions
              params={searchParams}
              disabled={!searchResult || searchResult.hits.length === 0}
              hitCount={searchResult?.total_hits}
            />
          </div>

          {/* Rechte Spalte: Datenstand-Sidebar + Quick-Filter */}
          <div className="space-y-4">
            <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                  <Database size={20} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-slate-900 dark:text-white">Datenstand</div>
                  <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Aktuelle Indexgroesse und Quellen-Health auf einen Blick.
                  </div>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Total Awards</span>
                  <span className="font-mono text-sm font-semibold text-slate-900 dark:text-white">
                    {status?.total_awards.toLocaleString('de-DE') ?? '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Quellen aktiv</span>
                  <span className="font-mono text-sm font-semibold text-slate-900 dark:text-white">
                    {status?.sources_enabled ?? '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Letzter Harvest</span>
                  <span className="font-mono text-[11px] font-semibold text-slate-900 dark:text-white">
                    {formatDateTime(status?.last_harvest_at ?? null)}
                  </span>
                </div>
              </div>
              {sources.length > 0 && (
                <div className="mt-4 space-y-2">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                    Quellen-Health
                  </div>
                  <ul className="space-y-1.5">
                    {sources.slice(0, 6).map((s) => {
                      const dot = s.quality === 'green' ? 'bg-emerald-500'
                        : s.quality === 'yellow' ? 'bg-amber-400'
                        : s.quality === 'red' ? 'bg-rose-500'
                        : 'bg-slate-300';
                      return (
                        <li key={s.source_key} className="flex items-center gap-2 text-xs">
                          <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${dot}`} aria-hidden />
                          <span className="flex-1 truncate text-slate-700 dark:text-slate-200" title={s.display_name}>
                            {s.display_name}
                          </span>
                          <span className="font-mono text-[11px] text-slate-400">{s.record_count.toLocaleString('de-DE')}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>

            <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                  <Globe2 size={20} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-slate-900 dark:text-white">Schnellzugriff</div>
                  <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Land oder Jahr direkt aktivieren.
                  </div>
                </div>
              </div>
              <div className="mt-4 rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Land</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(['DE', 'AT', ''] as const).map((code) => {
                    const label = code === '' ? 'Alle Laender' : code === 'DE' ? 'DE Deutschland' : 'AT Oesterreich';
                    const active = filters.country_code === code;
                    return (
                      <button
                        key={code || 'all'}
                        type="button"
                        onClick={() => {
                          const next = { ...filters, country_code: code };
                          setFilters(next);
                          runSearch(next);
                        }}
                        className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                          active
                            ? 'bg-emerald-600 text-white shadow-sm'
                            : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="mt-3 rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Jahr</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(() => {
                    const now = new Date().getFullYear();
                    const years = [now, now - 1, now - 2, now - 3];
                    return (
                      <>
                        {years.map((y) => {
                          const since = `${y}-01-01`;
                          const until = `${y}-12-31`;
                          const active = filters.since === since && filters.until === until;
                          return (
                            <button
                              key={y}
                              type="button"
                              onClick={() => {
                                const next = { ...filters, since, until };
                                setFilters(next);
                                runSearch(next);
                              }}
                              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                                active
                                  ? 'bg-emerald-600 text-white shadow-sm'
                                  : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
                              }`}
                            >
                              {y}
                            </button>
                          );
                        })}
                        <button
                          type="button"
                          onClick={() => {
                            const next = { ...filters, since: '', until: '' };
                            setFilters(next);
                            runSearch(next);
                          }}
                          className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                            !filters.since && !filters.until
                              ? 'bg-emerald-600 text-white shadow-sm'
                              : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
                          }`}
                        >
                          Alle
                        </button>
                      </>
                    );
                  })()}
                </div>
              </div>
            </div>
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
                <div className="text-sm font-semibold text-slate-900 dark:text-white">Geo-Verteilung der Awards</div>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  NUTS-Aggregation als Kreise oder Choropleth-Flaechen.
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
        <StatsTab loading={statsLoading} error={statsError} stats={stats} />
      )}

      {activeTab === 'sources' && (
        <section className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
              <Database size={20} />
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-slate-900 dark:text-white">Quellen &amp; Harvest-Status</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Pro Quelle: Datenstand, Coverage-Note, Quality-Ampel.
              </div>
            </div>
          </div>
          {!isAdmin && (
            <div className="mb-4 rounded-[24px] border border-slate-200/80 bg-slate-50/80 px-4 py-3 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-400">
              Detaillierte Fehlermeldungen und Aktionen sind dem Admin-/Moderator-Konto vorbehalten.
            </div>
          )}
          <StateAidSourceStatus
            sources={sources}
            isAdmin={isAdmin}
            onHarvest={isAdmin ? handleHarvest : undefined}
            onDelete={isAdmin ? handleDeleteSource : undefined}
          />
        </section>
      )}

      {activeTab === 'dossier' && (
        <DossierTab
          query={dossierQuery}
          onQueryChange={setDossierQuery}
          onSubmit={runDossier}
          dossier={dossier}
          busy={dossierBusy}
          error={dossierError}
          onPickAward={setSelectedAward}
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

function StatsTab({ loading, error, stats }: { loading: boolean; error: string | null; stats: StateAidStatsResponse | null }) {
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
      <BucketCard title="Top-Beguenstigte" subtitle="Hauptempfaenger der Beihilfen" buckets={stats.top_beneficiaries} icon={Building2} />
      <BucketCard title="Top-Behoerden" subtitle="Bewilligende Stellen" buckets={stats.top_authorities} icon={Layers} />
      <BucketCard title="Top-Beihilfeziele" subtitle="Foerderzwecke und Programme" buckets={stats.top_objectives} icon={Sparkles} />
      <BucketCard title="Top-Beihilfeinstrumente" subtitle="Zuschuss, Darlehen, Buergschaft …" buckets={stats.top_instruments} icon={Banknote} />
      {stats.by_year && stats.by_year.length > 0 && (
        <div className="lg:col-span-2 rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
              <BarChart3 size={16} />
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-900 dark:text-white">Jahresverteilung</div>
              <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                Anzahl Awards pro Bewilligungsjahr · Volumen rechts.
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
  buckets,
  icon: Icon,
}: {
  title: string;
  subtitle?: string;
  buckets?: Array<{ label: string; count: number; total_eur: number | null }>;
  icon: React.ComponentType<{ size?: number; className?: string }>;
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
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Keine Daten fuer den aktuellen Filter.</p>
      </div>
    );
  }
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
      <ol className="mt-4 space-y-1.5 text-sm">
        {buckets.slice(0, 10).map((b, idx) => (
          <li key={`${b.label}-${idx}`} className="flex items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/50">
            <span className="w-5 shrink-0 text-right font-mono text-xs text-slate-400">{idx + 1}</span>
            <span className="flex-1 truncate text-slate-700 dark:text-slate-200" title={b.label}>{b.label}</span>
            <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200">
              {b.count.toLocaleString('de-DE')}
            </span>
            <span className="hidden w-28 shrink-0 text-right font-mono text-[11px] text-slate-500 md:inline">
              {formatEur(b.total_eur)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

interface DossierProps {
  query: string;
  onQueryChange: (v: string) => void;
  onSubmit: (e?: FormEvent) => void;
  dossier: StateAidDossierResponse | null;
  busy: boolean;
  error: string | null;
  onPickAward: (a: StateAidAward) => void;
}

function DossierTab({ query, onQueryChange, onSubmit, dossier, busy, error, onPickAward }: DossierProps) {
  return (
    <section className="space-y-4">
      <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <div className="rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] p-4 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
              <FileSearch size={20} />
            </div>
            <div className="flex-1">
              <div className="text-sm font-medium text-slate-900 dark:text-white">Registeruebergreifendes Dossier</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Foerdervorhaben, Beihilfen und Sanktionen in einer Ansicht.
              </div>
            </div>
          </div>
          <form onSubmit={onSubmit} className="mt-4 flex flex-wrap items-center gap-2">
            <div className="relative min-w-[280px] flex-1">
              <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => onQueryChange(e.target.value)}
                placeholder="Unternehmensname fuer das Dossier — registeruebergreifend …"
                className="w-full rounded-[24px] border border-slate-200 bg-white/90 py-3 pl-11 pr-4 text-sm text-slate-900 shadow-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100 dark:focus:border-emerald-500 dark:focus:ring-emerald-500/30"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-3 text-sm font-medium text-white shadow-md shadow-emerald-600/30 transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              Dossier abrufen
            </button>
          </form>
        </div>

        {/* Cross-Register-Pruefbericht: prominenter Sprung mit aktueller Query */}
        <Link
          to={query.trim() ? `/audit-report?q=${encodeURIComponent(query.trim())}` : '/audit-report'}
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-[26px] border border-indigo-200 bg-[linear-gradient(135deg,rgba(238,242,255,0.9),rgba(224,231,255,0.7))] px-5 py-4 shadow-[0_18px_60px_-44px_rgba(67,56,202,0.45)] transition hover:border-indigo-300 hover:bg-indigo-50/90 dark:border-indigo-500/30 dark:bg-[linear-gradient(135deg,rgba(30,27,75,0.6),rgba(49,46,129,0.5))] dark:hover:bg-indigo-950/40"
        >
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white text-indigo-700 shadow-sm dark:bg-indigo-900/60 dark:text-indigo-200">
              <ClipboardCheck size={18} />
            </div>
            <div>
              <div className="text-sm font-semibold text-indigo-900 dark:text-indigo-100">
                Ausführlichen Prüfbericht erstellen
              </div>
              <p className="mt-0.5 text-xs leading-5 text-indigo-800/80 dark:text-indigo-200/80">
                Faktische Aggregation aus drei Registern als PDF — neutral, ohne Bewertung.
              </p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-600 px-4 py-2 text-xs font-medium text-white shadow-sm transition group-hover:bg-indigo-700">
            Bericht öffnen <ArrowRight size={12} />
          </span>
        </Link>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {dossier && dossier.summary.has_sanctions_hit && (
        <div className="flex items-start gap-3 rounded-[26px] border border-rose-300 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-800 dark:border-rose-500/40 dark:bg-rose-950/50 dark:text-rose-100">
          <ShieldAlert size={18} className="mt-0.5 shrink-0" />
          <div>
            <div>Sanktionslisten-Treffer fuer „{dossier.query}“ gefunden.</div>
            <div className="mt-1 text-xs font-normal opacity-90">
              Manuell pruefen — Geburtsdatum, Land und Identifier abgleichen.
            </div>
          </div>
        </div>
      )}

      {dossier && (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <SummaryCard
              icon={BadgeCheck}
              tone="emerald"
              label="Foerdervorhaben"
              count={dossier.beneficiaries.count}
              hint="Begünstigtenverzeichnis"
            />
            <SummaryCard
              icon={Coins}
              tone="emerald"
              label="Beihilfe-Awards"
              count={dossier.state_aid.count}
              hint={`Summe: ${formatEur(dossier.state_aid.total_eur)}`}
            />
            <SummaryCard
              icon={ShieldAlert}
              tone={dossier.sanctions.count > 0 ? 'rose' : 'slate'}
              label="Sanktionen"
              count={dossier.sanctions.count}
              hint={dossier.sanctions.count > 0 ? 'Treffer pruefen' : 'kein Treffer'}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <DossierColumn
              icon={Coins}
              title="Beihilfe-Awards"
              subtitle="Lokales State-Aid-Register"
              accent="emerald"
              empty="Keine Beihilfe-Treffer."
            >
              {dossier.state_aid.hits.slice(0, 12).map((a) => (
                <button
                  key={a.id}
                  onClick={() => onPickAward(a)}
                  className="block w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-left transition hover:border-emerald-300 hover:bg-emerald-50/50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-emerald-950/20"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">{a.beneficiary_name}</div>
                    <div className="shrink-0 font-mono text-[11px] text-emerald-700 dark:text-emerald-300">
                      {formatEur(a.aid_amount_eur ?? a.aid_amount)}
                    </div>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                    {[a.country_code, a.nuts_label, a.aid_instrument, a.granting_authority].filter(Boolean).join(' · ')}
                  </div>
                  {a.sa_reference && (
                    <div className="mt-0.5 font-mono text-[11px] text-cyan-700 dark:text-cyan-300">{a.sa_reference}</div>
                  )}
                </button>
              ))}
            </DossierColumn>

            <DossierColumn
              icon={ShieldAlert}
              title="Sanktionen"
              subtitle="OpenSanctions-Spiegel"
              accent={dossier.sanctions.count > 0 ? 'rose' : 'slate'}
              empty="Kein Sanktionslisten-Treffer."
            >
              {dossier.sanctions.hits.slice(0, 12).map((h, i) => (
                <DossierRow
                  key={i}
                  primary={String((h as { name?: string }).name || '—')}
                  secondary={[
                    String((h as { schema_type?: string }).schema_type || ''),
                    String((h as { countries?: string }).countries || ''),
                  ].filter(Boolean).join(' · ')}
                />
              ))}
            </DossierColumn>

            <DossierColumn
              icon={BadgeCheck}
              title="Foerdervorhaben"
              subtitle="Beguenstigtenverzeichnisse"
              accent="cyan"
              empty="Keine Treffer im Beguenstigtenverzeichnis."
            >
              {dossier.beneficiaries.hits.slice(0, 12).map((h, i) => (
                <DossierRow
                  key={i}
                  primary={String((h as { company_name?: string; project_name?: string }).company_name || (h as { project_name?: string }).project_name || '—')}
                  secondary={[
                    String((h as { aktenzeichen?: string }).aktenzeichen || ''),
                    String((h as { location?: string }).location || ''),
                    String((h as { source?: string }).source || ''),
                  ].filter(Boolean).join(' · ')}
                />
              ))}
            </DossierColumn>
          </div>

          <div className="rounded-[24px] border border-slate-200/80 bg-slate-50/70 px-4 py-3 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
            <div className="flex items-center gap-2">
              <Globe2 size={13} />
              <span>
                Register-Treffer gesamt: <span className="font-semibold text-slate-700 dark:text-slate-200">{dossier.summary.register_count.toLocaleString('de-DE')}</span>
                {' · '}
                Beihilfevolumen: <span className="font-mono">{formatEur(dossier.summary.total_eur)}</span>
              </span>
            </div>
          </div>
        </>
      )}

      {!dossier && !busy && !error && (
        <div className="rounded-[24px] border border-dashed border-slate-300 bg-white/80 px-6 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">
          Geben Sie einen Unternehmensnamen ein, um ein registeruebergreifendes Dossier
          zu erzeugen — Foerdervorhaben, Beihilfen, Sanktionen.
        </div>
      )}
    </section>
  );
}

function SummaryCard({
  icon: Icon,
  tone,
  label,
  count,
  hint,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone: 'emerald' | 'rose' | 'slate';
  label: string;
  count: number;
  hint: string;
}) {
  const TONES: Record<typeof tone, string> = {
    emerald: 'border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-100',
    rose: 'border-rose-200 bg-rose-50/70 text-rose-900 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-100',
    slate: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200',
  };
  return (
    <div className={`rounded-[26px] border px-4 py-4 shadow-[0_18px_60px_-44px_rgba(15,23,42,0.45)] ${TONES[tone]}`}>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider opacity-80">
        <Icon size={14} /> {label}
      </div>
      <div className="mt-2 text-2xl font-semibold">{count.toLocaleString('de-DE')}</div>
      <div className="mt-1 text-xs opacity-80">{hint}</div>
    </div>
  );
}

function DossierColumn({
  icon: Icon,
  title,
  subtitle,
  empty,
  accent = 'slate',
  children,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  subtitle?: string;
  empty: string;
  accent?: 'emerald' | 'rose' | 'cyan' | 'slate';
  children?: React.ReactNode;
}) {
  const hasChildren = !!(children && (Array.isArray(children) ? children.length > 0 : true));
  const accentMap: Record<typeof accent, string> = {
    emerald: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
    rose: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
    cyan: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300',
    slate: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  };
  return (
    <div className="flex h-full flex-col rounded-[26px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
      <div className="flex items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-2xl ${accentMap[accent]}`}>
          <Icon size={16} />
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white">{title}</div>
          {subtitle && <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>}
        </div>
      </div>
      <div className="mt-4 flex-1 space-y-2">
        {hasChildren ? (
          children
        ) : (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-400">
            {empty}
          </div>
        )}
      </div>
    </div>
  );
}

function DossierRow({ primary, secondary }: { primary: string; secondary?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900">
      <div className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">{primary}</div>
      {secondary && <div className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">{secondary}</div>}
    </div>
  );
}

// Reservierte Lucide-Icons fuer den Plan-Hinweis (haelt den Bundler bei Tree-Shaking happy)
void [CheckCircle2, Database, Banknote, Layers, Sparkles, Globe2, Building2];
