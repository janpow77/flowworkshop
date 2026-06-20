import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, ArrowLeft, ArrowUpRight, Banknote, BookOpenCheck, Building2,
  CheckCircle2, Crown, Database, Download, ExternalLink, Filter, Globe, Globe2, Landmark,
  Layers, Loader2, Mountain, RefreshCw, Search, ShieldAlert,
  Sparkles, Target,
} from 'lucide-react';
import { useExport } from '../lib/useExport';
import ExportButtons, { type ExportFormat } from '../components/ui/ExportButtons';
import Stat from '../components/ui/Stat';
import {
  getSanctionsSources,
  refreshSanctionsSource,
  searchSanctions,
  sourceShortLabel,
  formatRelativeTime,
  SOURCE_BADGE_STYLES,
  SOURCE_BADGE_FALLBACK,
  type SanctionsHit,
  type SanctionsSearchResponse,
  type SanctionsSourceInfo,
  type SanctionsSourceKey,
  type SanctionsStatsResponse,
} from '../lib/sanctionsApi';
import { safeExternalUrl } from '../lib/stateAidApi';

// ── Typen ────────────────────────────────────────────────────────────────────

type SanctionsList = {
  key: string;
  name: string;
  issuer: string;
  scope: string;
  description: string;
  url: string;
  search_url: string;
  data_format: string;
  update_frequency: string;
  language: string;
  color: string;
  icon: string;
  tag: string;
  use_in_audit: string;
  is_searchable_locally: boolean;
};

// Einheitlicher Default-Schwellenwert — deckungsgleich mit dem Backend-Default
// (SANCTIONS_DEFAULT_MIN_SCORE in routers/sanctions.py) und der in den
// DSGVO-Texten genannten Schwelle. Der Slider beginnt bewusst nicht unterhalb
// dieses Werts, damit UI und Begründung konsistent bleiben (Befund 7).
const SANCTIONS_MIN_SCORE_DEFAULT = 70;

type MethodStep = { title: string; text: string };
type MethodInfo = {
  title: string;
  summary: string;
  steps: MethodStep[];
  library: string;
  source_pattern: string;
  data_source: { name: string; url: string; license: string; update_frequency: string };
  limits: string[];
};

// ── Mapping: statischer ListCard-Key -> Backend-source_key ──────────────────

/**
 * Die statische Liste in /api/sanctions/lists nutzt eigene Slugs (z.B. "eu_fsf",
 * "un_sc"). Wenn das Backend einen passenden source_key in /api/sanctions/sources
 * meldet, koppeln wir die Karten daran, damit "lokal durchsuchbar"-Status,
 * Eintragszahlen und Refresh-Buttons aus den Live-Daten kommen.
 */
const LIST_KEY_TO_SOURCE_KEY: Record<string, SanctionsSourceKey> = {
  eu_fsf: 'eu_fsf',
  un_sc: 'un_sc',
  ofac_sdn: 'us_ofac_sdn',
  uk_ofsi: 'gb_hmt_sanctions',
  ch_seco: 'ch_seco',
};

// ── Icon-Mapping ────────────────────────────────────────────────────────────

const ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  ShieldAlert, Globe2, Globe, Banknote, Building2, Landmark, Crown, Mountain,
};

// Tailwind-sichere Farb-Klassen (nicht dynamisch, weil Tailwind sonst purged)
const COLORS: Record<string, { ring: string; chip: string; iconBg: string; iconText: string; tagBg: string; tagText: string }> = {
  rose: {
    ring: 'ring-rose-200/60 dark:ring-rose-500/30',
    chip: 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-200',
    iconBg: 'bg-gradient-to-br from-rose-100 to-rose-200/70 dark:from-rose-950/50 dark:to-rose-900/30',
    iconText: 'text-rose-700 dark:text-rose-200',
    tagBg: 'bg-rose-600 text-white',
    tagText: 'text-rose-700 dark:text-rose-300',
  },
  indigo: {
    ring: 'ring-indigo-200/60 dark:ring-indigo-500/30',
    chip: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-200',
    iconBg: 'bg-gradient-to-br from-indigo-100 to-indigo-200/70 dark:from-indigo-950/50 dark:to-indigo-900/30',
    iconText: 'text-indigo-700 dark:text-indigo-200',
    tagBg: 'bg-indigo-600 text-white',
    tagText: 'text-indigo-700 dark:text-indigo-300',
  },
  sky: {
    ring: 'ring-sky-200/60 dark:ring-sky-500/30',
    chip: 'bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-200',
    iconBg: 'bg-gradient-to-br from-sky-100 to-sky-200/70 dark:from-sky-950/50 dark:to-sky-900/30',
    iconText: 'text-sky-700 dark:text-sky-200',
    tagBg: 'bg-sky-600 text-white',
    tagText: 'text-sky-700 dark:text-sky-300',
  },
  amber: {
    ring: 'ring-amber-200/60 dark:ring-amber-500/30',
    chip: 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200',
    iconBg: 'bg-gradient-to-br from-amber-100 to-amber-200/70 dark:from-amber-950/50 dark:to-amber-900/30',
    iconText: 'text-amber-700 dark:text-amber-200',
    tagBg: 'bg-amber-600 text-white',
    tagText: 'text-amber-700 dark:text-amber-300',
  },
  emerald: {
    ring: 'ring-emerald-200/60 dark:ring-emerald-500/30',
    chip: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200',
    iconBg: 'bg-gradient-to-br from-emerald-100 to-emerald-200/70 dark:from-emerald-950/50 dark:to-emerald-900/30',
    iconText: 'text-emerald-700 dark:text-emerald-200',
    tagBg: 'bg-emerald-600 text-white',
    tagText: 'text-emerald-700 dark:text-emerald-300',
  },
  teal: {
    ring: 'ring-teal-200/60 dark:ring-teal-500/30',
    chip: 'bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-200',
    iconBg: 'bg-gradient-to-br from-teal-100 to-teal-200/70 dark:from-teal-950/50 dark:to-teal-900/30',
    iconText: 'text-teal-700 dark:text-teal-200',
    tagBg: 'bg-teal-600 text-white',
    tagText: 'text-teal-700 dark:text-teal-300',
  },
  violet: {
    ring: 'ring-violet-200/60 dark:ring-violet-500/30',
    chip: 'bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-200',
    iconBg: 'bg-gradient-to-br from-violet-100 to-violet-200/70 dark:from-violet-950/50 dark:to-violet-900/30',
    iconText: 'text-violet-700 dark:text-violet-200',
    tagBg: 'bg-violet-600 text-white',
    tagText: 'text-violet-700 dark:text-violet-300',
  },
};

// ── Konfidenz-Styling ───────────────────────────────────────────────────────

const CONFIDENCE_STYLES: Record<SanctionsHit['confidence'], { label: string; ring: string; bg: string; text: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  exact: { label: 'Exakter Treffer', ring: 'ring-rose-300', bg: 'bg-rose-600 text-white', text: 'text-rose-700 dark:text-rose-300', icon: AlertTriangle },
  high: { label: 'Hohe Ähnlichkeit', ring: 'ring-orange-300', bg: 'bg-orange-500 text-white', text: 'text-orange-700 dark:text-orange-300', icon: ShieldAlert },
  medium: { label: 'Mittlere Ähnlichkeit', ring: 'ring-amber-300', bg: 'bg-amber-500 text-white', text: 'text-amber-700 dark:text-amber-300', icon: Search },
  low: { label: 'Niedrige Ähnlichkeit', ring: 'ring-slate-300', bg: 'bg-slate-500 text-white', text: 'text-slate-600 dark:text-slate-300', icon: Search },
};

// ── Formatter ───────────────────────────────────────────────────────────────

function formatInt(n: number | undefined | null): string {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('de-DE');
}

function fileSafe(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9äöüß]+/gi, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60) || 'suche';
}

function isAdminUser(): boolean {
  const role = localStorage.getItem('workshop_role');
  return role === 'moderator' || role === 'admin';
}

/**
 * Fallback-Liste fuer den Fall, dass /api/sanctions/sources noch nicht
 * deployed ist. Nur EU FSF gilt dann als "loaded". Die statische
 * /api/sanctions/lists liefert den Rest (Tag, Beschreibung, Icon).
 */
function fallbackSources(): SanctionsSourceInfo[] {
  const now = new Date().toISOString();
  return [
    {
      source_key: 'eu_fsf',
      display_name: 'EU FSF (Konsolidierte Finanzsanktionsliste)',
      issuer: 'Europäische Kommission',
      loaded: true,
      total_entries: 0,
      persons: 0,
      organizations: 0,
      loaded_at: now,
      source_url: 'https://webgate.ec.europa.eu/fsd/fsf',
      download_url: 'https://data.opensanctions.org/datasets/latest/eu_fsf/',
      license: 'CC-BY 4.0',
    },
    {
      source_key: 'un_sc',
      display_name: 'UN Security Council Consolidated Sanctions List',
      issuer: 'Vereinte Nationen',
      loaded: false,
      total_entries: 0,
      persons: 0,
      organizations: 0,
      loaded_at: null,
      source_url: 'https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list',
      download_url: 'https://data.opensanctions.org/datasets/latest/un_sc/',
      license: 'public',
    },
    {
      source_key: 'us_ofac_sdn',
      display_name: 'US OFAC SDN List',
      issuer: 'U.S. Department of the Treasury',
      loaded: false,
      total_entries: 0,
      persons: 0,
      organizations: 0,
      loaded_at: null,
      source_url: 'https://sanctionssearch.ofac.treas.gov/',
      download_url: 'https://data.opensanctions.org/datasets/latest/us_ofac_sdn/',
      license: 'public',
    },
    {
      source_key: 'gb_hmt_sanctions',
      display_name: 'UK OFSI Sanctions List',
      issuer: 'HM Treasury (OFSI)',
      loaded: false,
      total_entries: 0,
      persons: 0,
      organizations: 0,
      loaded_at: null,
      source_url: 'https://www.gov.uk/government/publications/the-uk-sanctions-list',
      download_url: 'https://data.opensanctions.org/datasets/latest/gb_hmt_sanctions/',
      license: 'OGL v3.0',
    },
    {
      source_key: 'ch_seco',
      display_name: 'CH SECO Sanktionsliste',
      issuer: 'Staatssekretariat für Wirtschaft (SECO)',
      loaded: false,
      total_entries: 0,
      persons: 0,
      organizations: 0,
      loaded_at: null,
      source_url: 'https://www.seco.admin.ch/seco/de/home/Aussenwirtschaftspolitik_Wirtschaftliche_Zusammenarbeit/Wirtschaftsbeziehungen/exportkontrollen-und-sanktionen/sanktionen-embargos.html',
      download_url: 'https://data.opensanctions.org/datasets/latest/ch_seco/',
      license: 'public',
    },
  ];
}

// ── Hauptkomponente ─────────────────────────────────────────────────────────

export default function SanktionslistenPage() {
  const [lists, setLists] = useState<SanctionsList[]>([]);
  const [method, setMethod] = useState<MethodInfo | null>(null);
  const [stats, setStats] = useState<SanctionsStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Multi-Source-State
  const [sources, setSources] = useState<SanctionsSourceInfo[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [sourcesFallback, setSourcesFallback] = useState(false);
  const [activeSources, setActiveSources] = useState<SanctionsSourceKey[]>([]);
  const [refreshingSource, setRefreshingSource] = useState<SanctionsSourceKey | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  // Suche
  const [query, setQuery] = useState('');
  const [minScore, setMinScore] = useState(SANCTIONS_MIN_SCORE_DEFAULT);
  const [schemaFilter, setSchemaFilter] = useState<'' | 'Person' | 'Organization'>('');
  const [searchResult, setSearchResult] = useState<SanctionsSearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<'pdf' | 'csv' | null>(null);

  // Clientseitiger Source-Filter auf Treffern
  const [resultSourceFilter, setResultSourceFilter] = useState<SanctionsSourceKey[]>([]);

  const resultRef = useRef<HTMLDivElement>(null);
  const exportApi = useExport();
  const isAdmin = useMemo(() => isAdminUser(), []);

  // ── Initiales Laden ──────────────────────────────────────────────────────
  useEffect(() => {
    fetch('/api/sanctions/lists').then(r => r.json()).then(d => setLists(d.lists || [])).catch(() => {});
    fetch('/api/sanctions/method').then(r => r.json()).then(setMethod).catch(() => {});
    void loadSources();
    refreshStats();
  }, []);

  async function loadSources() {
    setSourcesLoading(true);
    try {
      const data = await getSanctionsSources();
      setSources(data);
      setSourcesFallback(false);
      // Default-Auswahl: alle loaded=true.
      const loadedKeys = data.filter((s) => s.loaded).map((s) => s.source_key);
      setActiveSources(loadedKeys.length > 0 ? loadedKeys : data.slice(0, 1).map((s) => s.source_key));
    } catch {
      // Backend liefert 404 oder Netzwerkfehler -> Fallback.
      const fb = fallbackSources();
      setSources(fb);
      setSourcesFallback(true);
      setActiveSources(fb.filter((s) => s.loaded).map((s) => s.source_key));
    } finally {
      setSourcesLoading(false);
    }
  }

  function refreshStats() {
    setStatsLoading(true);
    fetch('/api/sanctions/stats')
      .then(r => r.json())
      .then((data: SanctionsStatsResponse) => setStats(data))
      .catch(() => {})
      .finally(() => setStatsLoading(false));
  }

  function toggleSource(key: SanctionsSourceKey) {
    setActiveSources((prev) => {
      if (prev.includes(key)) {
        // Mindestens eine Source muss aktiv bleiben.
        if (prev.length <= 1) return prev;
        return prev.filter((k) => k !== key);
      }
      return [...prev, key];
    });
  }

  function toggleResultFilter(key: SanctionsSourceKey) {
    setResultSourceFilter((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  async function handleRefreshSource(key: SanctionsSourceKey | null) {
    setRefreshingSource(key ?? '__all__');
    setRefreshMessage(null);
    try {
      const res = await refreshSanctionsSource(key);
      setRefreshMessage(
        res.message
          ?? `Aktualisiert: ${res.refreshed?.toLocaleString?.('de-DE') ?? '—'} Einträge${res.source_key ? ` (${sourceShortLabel(res.source_key)})` : ''}.`,
      );
      // Sources neu laden, damit "loaded_at" und Counts frisch sind.
      await loadSources();
      refreshStats();
    } catch (err) {
      setRefreshMessage(
        err instanceof Error ? `Refresh fehlgeschlagen: ${err.message}` : 'Refresh fehlgeschlagen.',
      );
    } finally {
      setRefreshingSource(null);
    }
  }

  async function runSearch(e?: FormEvent, override?: string) {
    e?.preventDefault();
    const q = (override ?? query).trim();
    if (q.length < 2) {
      setSearchError('Bitte mindestens 2 Zeichen eingeben.');
      setSearchResult(null);
      return;
    }
    if (activeSources.length === 0) {
      setSearchError('Mindestens eine Liste auswählen.');
      setSearchResult(null);
      return;
    }
    setSearchError(null);
    setSearchLoading(true);
    setResultSourceFilter([]);
    try {
      const data = await searchSanctions({
        q,
        limit: 15,
        min_score: minScore,
        sources: activeSources,
        schema_filter: schemaFilter || undefined,
      });
      setSearchResult(data);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Suche fehlgeschlagen.');
      setSearchResult(null);
    } finally {
      setSearchLoading(false);
    }
  }

  const exampleQueries = ['Putin', 'Sechin Igor', 'Wagner', 'Lukashenko', 'Rosneft', 'Gazprom Neft'];
  const searchFilename = searchResult
    ? `sanktionspruefung_${fileSafe(searchResult.query)}_${new Date().toISOString().slice(0, 10)}`
    : 'sanktionspruefung';

  // Gefilterte Treffer fuer Anzeige + Export.
  const filteredHits = useMemo<SanctionsHit[]>(() => {
    if (!searchResult) return [];
    if (resultSourceFilter.length === 0) return searchResult.hits;
    return searchResult.hits.filter((h) => resultSourceFilter.includes(h.source_key));
  }, [searchResult, resultSourceFilter]);

  // Set der Sources, die in den aktuellen Treffern vorkommen — fuer Result-Filter-Pills.
  const hitSourceKeys = useMemo<SanctionsSourceKey[]>(() => {
    if (!searchResult) return [];
    const seen = new Set<SanctionsSourceKey>();
    for (const h of searchResult.hits) seen.add(h.source_key);
    return Array.from(seen);
  }, [searchResult]);

  // Fuer Stats-Hero: Gesamtzahl ueber alle loaded Sources.
  const totalEntriesAllSources = useMemo(() => {
    if (stats?.total_entries) return stats.total_entries;
    return sources.filter((s) => s.loaded).reduce((acc, s) => acc + s.total_entries, 0);
  }, [stats, sources]);

  const loadedSourceCount = sources.filter((s) => s.loaded).length;

  /**
   * Server-seitiger Export der Sanctions-Suche (CSV / XLSX / PDF).
   *
   * Bevorzugt das Backend-Endpoint /api/sanctions/export — der liefert das
   * korrekte XLSX und PDF mit Pflichthinweis. Fuer den clientseitigen
   * Result-Filter (resultSourceFilter) faellt der Export auf den lokalen
   * Renderer zurueck, weil das Backend keinen Filter pro Hit kennt.
   */
  async function handleExport(format: ExportFormat) {
    if (!searchResult) return;
    if (format === 'png' || format === 'geojson') return; // nicht unterstuetzt
    setExporting(format === 'pdf' ? 'pdf' : 'csv');
    try {
      const useClientFilter = resultSourceFilter.length > 0;
      if (!useClientFilter) {
        // Server-Pfad: vollstaendiger Export inkl. Pflichthinweis-Sheet.
        const params = new URLSearchParams({
          format,
          q: searchResult.query,
          limit: '500',
          min_score: String(searchResult.threshold),
        });
        if (schemaFilter) params.set('schema_filter', schemaFilter);
        if (activeSources.length > 0) params.set('sources', activeSources.join(','));
        const url = `/api/sanctions/export?${params.toString()}`;
        const a = document.createElement('a');
        a.href = url;
        a.rel = 'noopener noreferrer';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        return;
      }

      // Clientseitiger Filter aktiv → lokaler Export auf gefilterten Hits.
      if (format === 'pdf') {
        await exportApi.toPdf(resultRef.current, {
          title: `Sanktionsprüfung: ${searchResult.query}`,
          subtitle: `Multi-Source · Schwelle ${searchResult.threshold} · ${filteredHits.length} angezeigte Treffer · Listen: ${activeSources.map(sourceShortLabel).join(', ')}`,
          filename: searchFilename,
        });
        return;
      }
      // CSV oder XLSX clientseitig — wir liefern CSV in beiden Faellen,
      // weil resultSourceFilter ohnehin nur ein Subset ist und Excel
      // CSV mit Komma-Trenner und BOM problemlos oeffnet.
      const meta = {
        suchbegriff: searchResult.query,
        normalisiert: searchResult.normalized,
        schwellenwert: searchResult.threshold,
        typfilter: schemaFilter || 'Alle',
        listen_aktiv: activeSources.map(sourceShortLabel).join(' | '),
        listen_filter_clientseitig: resultSourceFilter.map(sourceShortLabel).join(' | '),
        exportiert_am: new Date().toISOString(),
      };
      const rows = filteredHits.length > 0
        ? filteredHits.map((hit) => ({
            ...meta,
            id: hit.id,
            quelle_key: hit.source_key,
            quelle: hit.source_display_name,
            typ: hit.schema_type,
            name: hit.name,
            score: hit.score,
            konfidenz: hit.confidence,
            trefferquelle: hit.matched_field,
            matched_on: hit.matched_on,
            aliase: hit.aliases.join(' | '),
            geburtsdatum: hit.birth_date,
            laender: hit.countries,
            adressen: hit.addresses,
            identifier: hit.identifiers,
            rechtsakt: hit.sanctions,
            programm: hit.program_ids,
            erstmals_gelistet: hit.first_seen,
            zuletzt_bestaetigt: hit.last_seen,
          }))
        : [{ ...meta, id: '', name: 'Kein Treffer oberhalb des Schwellenwerts' }];
      exportApi.toCsv(rows, { filename: searchFilename });
    } finally {
      setExporting(null);
    }
  }

  return (
    <div className="space-y-8">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600">
        <ArrowLeft size={16} /> Zurück
      </Link>

      {/* ── Hero ───────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(46,16,16,0.98),rgba(120,30,40,0.94)_45%,rgba(190,60,50,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight lg:text-4xl">Sanktionslisten</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-white/85 lg:text-base">
              Eine kuratierte Übersicht der wichtigsten Sanktions- und Embargo-Verzeichnisse mit
              Kurzcharakteristik und Direktlink in das jeweilige offizielle Tool. Zusätzlich:
              lokale Fuzzy-Suche gegen mehrere Listen (EU FSF, UN, OFAC, OFSI, SECO) — voll
              offline, ohne Daten an Dritte.
            </p>
            <div className="mt-6 flex flex-wrap gap-3 text-xs">
              <a href="#suche" className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 font-medium text-rose-700 transition hover:bg-rose-50">
                <Search size={14} /> Direkt zur Suche
              </a>
              <a href="#methode" className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-4 py-2 font-medium text-white transition hover:bg-white/20">
                <BookOpenCheck size={14} /> Methode verstehen
              </a>
              <a href="#listen" className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-4 py-2 font-medium text-white transition hover:bg-white/20">
                <Globe2 size={14} /> Alle Listen
              </a>
            </div>
          </div>

          <div className="rounded-[28px] border border-white/15 bg-black/15 p-5 backdrop-blur">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/60">Lokaler Multi-Source-Index</div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <Stat label="Einträge gesamt" value={formatInt(totalEntriesAllSources)} />
              <Stat label="Listen lokal" value={formatInt(loadedSourceCount)} />
              <Stat label="Treffer (Suche)" value={searchResult ? formatInt(searchResult.total_hits) : '—'} />
            </div>
            <div className="mt-4 space-y-1 text-[11px] text-white/70">
              {sources.filter((s) => s.loaded).slice(0, 3).map((s) => (
                <div key={s.source_key} className="flex items-center justify-between">
                  <span>{sourceShortLabel(s.source_key)}</span>
                  <span className="font-mono">{formatInt(s.total_entries)}</span>
                </div>
              ))}
              {loadedSourceCount > 3 && (
                <div className="text-white/50">+{loadedSourceCount - 3} weitere Listen</div>
              )}
            </div>
            <div className="mt-3 flex gap-2">
              <button
                onClick={refreshStats}
                disabled={statsLoading}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-2 text-xs font-medium text-white/90 transition hover:bg-white/20 disabled:opacity-50"
              >
                {statsLoading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                Status
              </button>
              {isAdmin && !sourcesFallback && (
                <button
                  onClick={() => handleRefreshSource(null)}
                  disabled={refreshingSource !== null}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-white/90 px-3 py-2 text-xs font-medium text-rose-700 shadow-sm transition hover:bg-white disabled:opacity-50"
                  title="Alle Listen neu laden (Admin)"
                >
                  {refreshingSource === '__all__' ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />}
                  Alle laden
                </button>
              )}
            </div>
            {refreshMessage && (
              <div className="mt-3 rounded-xl border border-white/20 bg-white/10 px-3 py-2 text-[11px] text-white/85">
                {refreshMessage}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── DSGVO-Hinweis: Suche nur fuer Admins ──────────────────── */}
      {!isAdmin && (
        <section
          id="suche"
          className="rounded-[34px] border border-amber-300/70 bg-gradient-to-br from-amber-50 via-white to-amber-50/40 p-6 shadow-sm dark:border-amber-500/30 dark:from-amber-950/30 dark:via-slate-900 dark:to-amber-950/10 lg:p-8"
        >
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-amber-500 text-white shadow-lg shadow-amber-500/30">
              <ShieldAlert size={22} />
            </div>
            <div className="space-y-3 text-sm leading-6 text-slate-700 dark:text-slate-200">
              <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
                Sanktionssuche aus Datenschutzgründen deaktiviert
              </h2>
              <p>
                Die Fuzzy-Suche über die unten dokumentierten Sanktionslisten ist auf dieser
                Schulungs- und Demonstrationsplattform <strong>nicht freigeschaltet</strong>.
                Die Listen enthalten personenbezogene Daten, und die hier eingesetzte
                Ähnlichkeitssuche (Schwelle 70 %) erzeugt nicht selten Treffer für unbeteiligte
                Namensvettern. Eine Verarbeitung dieser Daten außerhalb einer konkreten,
                rechtlich gestützten Sanktionsprüfung wäre nicht durch die Zweckbindung nach
                Art. 5 Abs. 1 lit. b DSGVO gedeckt.
              </p>
              <p>
                Die offiziellen Listen können jederzeit direkt bei den Herausgebern recherchiert
                werden — die Verlinkungen finden Sie weiter unten unter „Sanktionslisten im
                Überblick". Für die offizielle sanktionsrechtliche Prüfung im Rahmen einer
                Verwaltungskontrolle nutzen Sie bitte ausschließlich die dort verlinkten
                Original-Suchmasken der Herausgeber.
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Details zur Datenverarbeitung in der{' '}
                <Link to="/datenschutz" className="text-rose-700 underline-offset-4 hover:underline dark:text-rose-300">
                  Datenschutzerklärung
                </Link>.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* ── Suche ──────────────────────────────────────────────────── */}
      {isAdmin && (
      <section id="suche" className="rounded-[34px] border border-rose-200/60 bg-gradient-to-br from-white via-rose-50/60 to-white p-6 shadow-[0_24px_80px_-50px_rgba(190,18,60,0.45)] dark:border-rose-500/20 dark:from-slate-900 dark:via-rose-950/20 dark:to-slate-900 lg:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <div className="lg:w-1/3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-600 text-white shadow-lg shadow-rose-600/30">
                <Search size={22} />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Fuzzy-Suche · Multi-Source</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">Lokal, ohne API-Aufruf</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
              Personen oder Organisationen prüfen — die Suche toleriert abweichende Schreibung,
              andere Reihenfolge der Namensteile und Rechtsformsuffixe. Sie läuft komplett im
              Workshop-Container und durchsucht alle aktivierten Listen.
            </p>
            <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
              <span className="text-slate-500 dark:text-slate-400">Beispiele:</span>
              {exampleQueries.map((ex) => (
                <button
                  key={ex}
                  onClick={() => { setQuery(ex); runSearch(undefined, ex); }}
                  className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-600 transition hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-rose-500/50 dark:hover:bg-rose-950/40"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1">
            <form onSubmit={runSearch} className="space-y-3">
              <div className="relative">
                <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Name eingeben — z. B. ‚Sechin Igor‘ oder ‚Rosneft Oil Company‘"
                  className="w-full rounded-2xl border border-slate-200 bg-white py-4 pl-12 pr-32 text-sm text-slate-900 shadow-sm outline-none ring-rose-200 transition focus:border-rose-400 focus:ring-2 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:ring-rose-500/30 dark:focus:border-rose-500"
                />
                <button
                  type="submit"
                  disabled={searchLoading || activeSources.length === 0}
                  className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2 text-sm font-medium text-white shadow-md shadow-rose-600/30 transition hover:bg-rose-700 disabled:opacity-50"
                >
                  {searchLoading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                  Prüfen
                </button>
              </div>

              {/* Source-Auswahl-Pills */}
              <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200/70 bg-white/60 px-4 py-3 text-xs dark:border-slate-700/70 dark:bg-slate-900/40">
                <span className="inline-flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                  <Layers size={13} /> Listen durchsuchen:
                </span>
                {sourcesLoading ? (
                  <span className="inline-flex items-center gap-1.5 text-slate-400">
                    <Loader2 size={12} className="animate-spin" /> lädt …
                  </span>
                ) : sources.filter((s) => s.loaded).length === 0 ? (
                  <span className="text-amber-600 dark:text-amber-300">
                    Keine Liste lokal verfügbar — bitte Admin zum Refresh kontaktieren.
                  </span>
                ) : (
                  sources.filter((s) => s.loaded).map((s) => {
                    const active = activeSources.includes(s.source_key);
                    return (
                      <button
                        key={s.source_key}
                        type="button"
                        onClick={() => toggleSource(s.source_key)}
                        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
                          active
                            ? 'bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900'
                            : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800'
                        }`}
                        title={`${s.display_name} · ${s.issuer}`}
                      >
                        {active ? <CheckCircle2 size={12} /> : null}
                        {sourceShortLabel(s.source_key)}
                        <span className={`opacity-60 ${active ? '' : 'text-slate-500 dark:text-slate-400'}`}>
                          ({s.total_entries.toLocaleString('de-DE')})
                        </span>
                      </button>
                    );
                  })
                )}
                {activeSources.length === 0 && !sourcesLoading && sources.filter((s) => s.loaded).length > 0 && (
                  <span className="text-rose-600 dark:text-rose-300">Mindestens eine Liste auswählen</span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-200/70 bg-white/60 px-4 py-3 text-xs dark:border-slate-700/70 dark:bg-slate-900/40">
                <div className="flex items-center gap-2">
                  <span className="text-slate-600 dark:text-slate-300">Schwellenwert</span>
                  <input
                    type="range"
                    min={SANCTIONS_MIN_SCORE_DEFAULT}
                    max={100}
                    step={5}
                    value={minScore}
                    onChange={(e) => setMinScore(Number(e.target.value))}
                    className="accent-rose-600"
                  />
                  <span className="w-10 text-right font-mono font-semibold text-rose-700 dark:text-rose-300">{minScore}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-slate-600 dark:text-slate-300">Typ</span>
                  {[
                    { v: '', label: 'Alle' },
                    { v: 'Person', label: 'Personen' },
                    { v: 'Organization', label: 'Orgs' },
                  ].map((opt) => (
                    <button
                      key={opt.v}
                      type="button"
                      onClick={() => setSchemaFilter(opt.v as typeof schemaFilter)}
                      className={`rounded-full px-3 py-1 transition ${
                        schemaFilter === opt.v
                          ? 'bg-rose-600 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </form>

            {searchError && (
              <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200">
                {searchError}
              </div>
            )}

            {searchLoading && (
              <div className="mt-4 space-y-2">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-20 animate-pulse rounded-2xl bg-slate-200/60 dark:bg-slate-800/60"
                  />
                ))}
              </div>
            )}

            {searchResult && !searchError && !searchLoading && (
              <div className="mt-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/75 px-4 py-3 dark:border-slate-700 dark:bg-slate-900/55">
                  <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <Download size={14} />
                    Prüfnotiz exportieren · Pflichthinweis und Datenstand sind im Export enthalten
                    {resultSourceFilter.length > 0 && (
                      <span className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-950/60 dark:text-amber-200">
                        Clientseitiger Filter aktiv — Export ohne Server-Pflichthinweis-Sheet
                      </span>
                    )}
                  </div>
                  <ExportButtons
                    formats={['csv', 'xlsx', 'pdf']}
                    onExport={handleExport}
                    disabled={!!exporting}
                  />
                </div>

                {/* Result-Filter (clientseitig) */}
                {hitSourceKeys.length > 1 && (
                  <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white/75 px-4 py-3 text-xs dark:border-slate-700 dark:bg-slate-900/55">
                    <span className="inline-flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                      <Filter size={12} /> Treffer filtern:
                    </span>
                    {hitSourceKeys.map((key) => {
                      const active = resultSourceFilter.includes(key);
                      const count = searchResult.hits.filter((h) => h.source_key === key).length;
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => toggleResultFilter(key)}
                          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition ${
                            active
                              ? `${SOURCE_BADGE_STYLES[key] ?? SOURCE_BADGE_FALLBACK} ring-1 ring-current`
                              : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800'
                          }`}
                        >
                          {sourceShortLabel(key)} <span className="opacity-70">({count})</span>
                        </button>
                      );
                    })}
                    {resultSourceFilter.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setResultSourceFilter([])}
                        className="rounded-full px-2.5 py-1 text-[11px] text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                      >
                        Filter zurücksetzen
                      </button>
                    )}
                  </div>
                )}

                <div ref={resultRef}>
                  <SearchResults
                    result={searchResult}
                    visibleHits={filteredHits}
                    activeSources={activeSources}
                  />
                </div>
              </div>
            )}

            {!searchResult && !searchError && !searchLoading && (
              <div className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white/40 px-5 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
                Noch keine Suche durchgeführt. Tippen Sie einen Namen ein oder wählen Sie ein Beispiel.
              </div>
            )}
          </div>
        </div>
      </section>
      )}

      {/* ── Methode ────────────────────────────────────────────────── */}
      <section id="methode" className="rounded-[34px] border border-slate-200/70 bg-gradient-to-br from-slate-50 via-white to-cyan-50/30 p-6 shadow-[0_24px_80px_-50px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-cyan-950/20 lg:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <div className="lg:w-1/3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-700 text-white shadow-lg shadow-cyan-700/30">
                <BookOpenCheck size={22} />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{method?.title || 'Methode'}</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">Wie die Multi-Source-Suche arbeitet</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
              {method?.summary}
            </p>
            <div className="mt-4 rounded-2xl border border-cyan-200/70 bg-cyan-50/60 p-4 text-sm leading-6 text-cyan-900 dark:border-cyan-500/30 dark:bg-cyan-950/30 dark:text-cyan-100">
              <div className="flex items-center gap-2 font-semibold">
                <Sparkles size={14} /> Multi-Source-Logik
              </div>
              <ul className="mt-2 space-y-1.5 text-[13px]">
                <li>Eingabe wird gegen Namen und Aliase <strong>aller aktivierten Listen</strong> geprüft.</li>
                <li>Treffer aus EU FSF, UN, OFAC, OFSI und SECO werden zusammengeführt und nach Score sortiert.</li>
                <li>Jeder Treffer zeigt deutlich seine Herkunfts-Liste — Mehrfachnennungen sind möglich.</li>
              </ul>
            </div>
            {method?.library && (
              <div className="mt-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs dark:border-slate-700 dark:bg-slate-900">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Library</div>
                <div className="mt-1 font-mono text-cyan-700 dark:text-cyan-300">{method.library}</div>
              </div>
            )}
            {method?.data_source && (
              <div className="mt-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs dark:border-slate-700 dark:bg-slate-900">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Datenquelle</div>
                <div className="mt-1 text-slate-700 dark:text-slate-200">{method.data_source.name}</div>
                {(() => {
                  const safe = safeExternalUrl(method.data_source.url);
                  return safe ? (
                    <a href={safe} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-cyan-700 hover:underline dark:text-cyan-300">
                      CSV öffnen <ExternalLink size={11} />
                    </a>
                  ) : null;
                })()}
                <div className="mt-1 text-slate-500 dark:text-slate-400">Lizenz: {method.data_source.license} · {method.data_source.update_frequency}</div>
              </div>
            )}
          </div>

          <div className="flex-1">
            <ol className="space-y-3">
              {(method?.steps || []).map((step, idx) => (
                <li key={step.title} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md dark:border-slate-700 dark:bg-slate-900">
                  <div className="flex items-start gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-cyan-700 text-sm font-semibold text-white">
                      {idx + 1}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{step.title.replace(/^\d+\.\s*/, '')}</div>
                      <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{step.text}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ol>

            {method?.limits && method.limits.length > 0 && (
              <div className="mt-5 rounded-2xl border border-amber-200/70 bg-amber-50/60 p-4 text-sm dark:border-amber-500/30 dark:bg-amber-950/30">
                <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200">
                  <AlertTriangle size={16} />
                  <span className="font-semibold">Grenzen der Methode</span>
                </div>
                <ul className="mt-2 space-y-1.5 text-amber-900/90 dark:text-amber-100/90">
                  {method.limits.map((l, i) => (
                    <li key={i} className="flex gap-2 leading-6">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-amber-700 dark:bg-amber-300" />
                      <span>{l}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Listen-Cards ─────────────────────────────────────────── */}
      <section id="listen" className="space-y-4">
        <div className="flex items-end justify-between gap-4 px-1">
          <div>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Die wichtigsten Sanktionslisten</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Direkter Zugriff auf die offiziellen Quellen — mit Live-Status zur lokalen Verfügbarkeit.
            </p>
          </div>
          <div className="hidden text-xs text-slate-500 dark:text-slate-400 sm:flex sm:items-center sm:gap-2">
            <Database size={14} /> {lists.length} Verzeichnisse · {loadedSourceCount} lokal indiziert
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {lists.map((list) => {
            const sourceKey = LIST_KEY_TO_SOURCE_KEY[list.key];
            const sourceInfo = sourceKey ? sources.find((s) => s.source_key === sourceKey) : undefined;
            return (
              <ListCard
                key={list.key}
                list={list}
                sourceInfo={sourceInfo}
                isAdmin={isAdmin && !sourcesFallback}
                onRefresh={(key) => handleRefreshSource(key)}
                refreshing={refreshingSource}
              />
            );
          })}
        </div>
      </section>

    </div>
  );
}

// ── Subkomponenten ──────────────────────────────────────────────────────────

interface ListCardProps {
  list: SanctionsList;
  sourceInfo?: SanctionsSourceInfo;
  isAdmin: boolean;
  onRefresh: (key: SanctionsSourceKey) => void;
  refreshing: SanctionsSourceKey | null;
}

function ListCard({ list, sourceInfo, isAdmin, onRefresh, refreshing }: ListCardProps) {
  const Icon = ICONS[list.icon] || Globe2;
  const c = COLORS[list.color] || COLORS.indigo;
  // Live-Status ueberschreibt das statische Flag aus /api/sanctions/lists.
  const isLoaded = sourceInfo ? sourceInfo.loaded : list.is_searchable_locally;
  const totalEntries = sourceInfo?.total_entries ?? 0;
  const loadedAt = sourceInfo?.loaded_at ?? null;
  const safeQuelle = safeExternalUrl(list.url);
  const safeOnline = safeExternalUrl(list.search_url);
  const isThisRefreshing = sourceInfo ? refreshing === sourceInfo.source_key : false;

  return (
    <div className={`group flex h-full flex-col rounded-3xl border border-slate-200/70 bg-white p-5 shadow-sm ring-1 ${c.ring} transition hover:shadow-lg dark:border-slate-800 dark:bg-slate-900`}>
      <div className="flex items-start justify-between gap-3">
        <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${c.iconBg} ${c.iconText} shadow-sm`}>
          <Icon size={22} />
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${c.tagBg}`}>
            {list.tag}
          </span>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
              isLoaded
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
            }`}
            title={isLoaded ? 'Lokal indiziert und durchsuchbar' : 'Nur Verlinkung — keine lokale Fuzzy-Suche'}
          >
            {isLoaded ? <CheckCircle2 size={10} /> : <Globe size={10} />}
            {isLoaded ? 'lokal durchsuchbar' : 'nur Verlinkung'}
          </span>
        </div>
      </div>
      <h3 className="mt-4 text-base font-semibold text-slate-900 dark:text-slate-100">{list.name}</h3>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{list.issuer}</p>
      <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{list.description}</p>

      {isLoaded && sourceInfo && (
        <div className="mt-4 grid grid-cols-2 gap-2 rounded-2xl border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950/50">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Einträge</div>
            <div className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">
              {totalEntries.toLocaleString('de-DE')}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Letzte Aktualisierung</div>
            <div className="text-sm text-slate-700 dark:text-slate-200">
              {formatRelativeTime(loadedAt)}
            </div>
          </div>
        </div>
      )}

      <dl className="mt-4 space-y-1.5 text-xs">
        <div className="flex items-start gap-2">
          <dt className="w-20 shrink-0 text-slate-400">Umfang</dt>
          <dd className="text-slate-700 dark:text-slate-200">{list.scope}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-20 shrink-0 text-slate-400">Format</dt>
          <dd className="text-slate-700 dark:text-slate-200">{list.data_format}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-20 shrink-0 text-slate-400">Update</dt>
          <dd className="text-slate-700 dark:text-slate-200">{list.update_frequency}</dd>
        </div>
        <div className="flex items-start gap-2">
          <dt className="w-20 shrink-0 text-slate-400">Sprache</dt>
          <dd className="text-slate-700 dark:text-slate-200">{list.language}</dd>
        </div>
      </dl>

      <div className={`mt-4 rounded-2xl ${c.chip} px-3 py-2 text-xs leading-5`}>
        <div className="font-semibold uppercase tracking-wider text-[10px] mb-1 flex items-center gap-1">
          <Target size={10} /> Im Audit
        </div>
        {list.use_in_audit}
      </div>

      <div className="mt-auto pt-4 flex items-center justify-between gap-2">
        {safeQuelle ? (
          <a
            href={safeQuelle}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <Globe2 size={13} /> Quelle
          </a>
        ) : (
          <span className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500">
            <Globe2 size={13} /> Quelle
          </span>
        )}
        {safeOnline ? (
          <a
            href={safeOnline}
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-flex flex-1 items-center justify-center gap-2 rounded-2xl ${c.tagBg} px-3 py-2 text-xs font-medium shadow-sm transition hover:opacity-90`}
          >
            <Search size={13} /> Online suchen <ArrowUpRight size={13} />
          </a>
        ) : (
          <span className={`inline-flex flex-1 items-center justify-center gap-2 rounded-2xl ${c.tagBg} px-3 py-2 text-xs font-medium opacity-60`}>
            <Search size={13} /> Online suchen
          </span>
        )}
      </div>
      {isLoaded && (
        <div className="mt-2 inline-flex items-center justify-center gap-1 rounded-full bg-slate-900/5 px-2 py-1 text-[10px] font-medium text-slate-600 dark:bg-white/5 dark:text-slate-300">
          <Sparkles size={10} /> auch lokal abfragbar (oben)
        </div>
      )}
      {isAdmin && sourceInfo && (
        <button
          type="button"
          onClick={() => onRefresh(sourceInfo.source_key)}
          disabled={isThisRefreshing}
          className="mt-2 inline-flex items-center justify-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {isThisRefreshing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          Jetzt aktualisieren
        </button>
      )}
    </div>
  );
}

interface SearchResultsProps {
  result: SanctionsSearchResponse;
  visibleHits: SanctionsHit[];
  activeSources: SanctionsSourceKey[];
}

function SearchResults({ result, visibleHits, activeSources }: SearchResultsProps) {
  const summary = useMemo(() => {
    if (visibleHits.length === 0) {
      return {
        tone: 'green',
        icon: CheckCircle2,
        title: 'Kein Treffer',
        text: result.total_hits === 0
          ? `Für „${result.query}" wurde in den gewählten Listen nichts oberhalb des Schwellenwerts gefunden. Score senken oder weitere Listen aktivieren.`
          : `Für „${result.query}" gibt es zwar Treffer, aber keiner passt zum aktuellen Filter — Filter zurücksetzen oder andere Listen anzeigen.`,
      };
    }
    const top = visibleHits[0];
    if (top.confidence === 'exact' || top.confidence === 'high') {
      return {
        tone: 'rose',
        icon: AlertTriangle,
        title: 'Treffer — prüfen',
        text: `Höchster Score ${top.score} (${top.confidence}) aus ${top.source_display_name}. Manuelle Abklärung erforderlich.`,
      };
    }
    return {
      tone: 'amber',
      icon: ShieldAlert,
      title: 'Hinweise gefunden',
      text: `${visibleHits.length} Ähnlichkeiten oberhalb ${result.threshold} (Quellen: ${
        Array.from(new Set(visibleHits.map((h) => sourceShortLabel(h.source_key)))).join(', ')
      }). Geburtsdatum/Land im Detail abgleichen.`,
    };
  }, [result, visibleHits]);

  const SummaryIcon = summary.icon;
  const toneClass: Record<string, string> = {
    green: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-200',
    rose: 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200',
    amber: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-200',
  };

  return (
    <div className="mt-4 space-y-3">
      <div className={`rounded-2xl border px-4 py-3 ${toneClass[summary.tone]}`}>
        <div className="flex items-start gap-3">
          <SummaryIcon size={18} className="mt-0.5" />
          <div>
            <div className="font-semibold">{summary.title}</div>
            <div className="text-sm opacity-90">{summary.text}</div>
            <div className="mt-1 text-[11px] opacity-70">
              normalisiert: <span className="font-mono">{result.normalized}</span> · Methode: {result.method} · durchsucht: {activeSources.map(sourceShortLabel).join(', ')}
            </div>
          </div>
        </div>
      </div>

      {visibleHits.map((hit) => <HitCard key={`${hit.source_key}:${hit.id}`} hit={hit} />)}
    </div>
  );
}

function HitCard({ hit }: { hit: SanctionsHit }) {
  const cs = CONFIDENCE_STYLES[hit.confidence];
  const HitIcon = cs.icon;
  const sourceBadgeClass = SOURCE_BADGE_STYLES[hit.source_key] ?? SOURCE_BADGE_FALLBACK;
  return (
    <div className={`rounded-2xl border border-slate-200 bg-white p-4 ring-1 ${cs.ring} dark:border-slate-700 dark:bg-slate-900`}>
      <div className="flex flex-wrap items-start gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${cs.bg} shadow-sm`}>
          <HitIcon size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{hit.name}</h4>
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${sourceBadgeClass}`}>
              {sourceShortLabel(hit.source_key)}
            </span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {hit.schema_type}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${cs.bg}`}>
              Score {hit.score}
            </span>
            <span className={`text-[11px] font-medium ${cs.text}`}>{cs.label}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Listenherkunft: <span className="font-medium text-slate-700 dark:text-slate-200">{hit.source_display_name}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Trefferquelle: <span className="font-medium text-slate-700 dark:text-slate-200">{hit.matched_field === 'alias' ? 'Alias' : 'Hauptname'}</span>
            {' · '}
            <span className="italic">„{hit.matched_on}"</span>
          </div>
        </div>
      </div>

      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        {hit.birth_date && <Row label="Geburtsdatum" value={hit.birth_date} />}
        {hit.countries && <Row label="Land" value={hit.countries} />}
        {hit.identifiers && <Row label="Identifier" value={hit.identifiers} mono />}
        {hit.program_ids && <Row label="Programm" value={hit.program_ids} mono />}
        {hit.addresses && <Row label="Adresse" value={hit.addresses} />}
        {hit.sanctions && <Row label="Rechtsakt" value={hit.sanctions} mono />}
        {hit.first_seen && <Row label="Erstmals gelistet" value={hit.first_seen.split('T')[0]} />}
        {hit.last_seen && <Row label="Zuletzt bestätigt" value={hit.last_seen.split('T')[0]} />}
      </dl>

      {hit.aliases.length > 0 && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-950/50">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Aliase ({hit.aliases.length})
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
            {hit.aliases.map((a, i) => (
              <span key={i} className="rounded-md bg-white px-2 py-0.5 text-slate-700 dark:bg-slate-800 dark:text-slate-200">{a}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start gap-2">
      <dt className="w-28 shrink-0 text-slate-400">{label}</dt>
      <dd className={`flex-1 text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-[11px]' : ''}`}>{value}</dd>
    </div>
  );
}
