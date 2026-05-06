import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import {
  AlertTriangle, ArrowUpRight, Banknote, BookOpenCheck, Building2,
  CheckCircle2, Crown, Database, ExternalLink, Globe, Globe2, Landmark,
  Loader2, Mountain, RefreshCw, Search, ShieldAlert, ShieldCheck,
  Sparkles, Target,
} from 'lucide-react';

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

type SearchHit = {
  id: string;
  schema_type: string;
  name: string;
  matched_on: string;
  matched_field: string;
  score: number;
  confidence: 'exact' | 'high' | 'medium' | 'low';
  aliases: string[];
  birth_date: string;
  countries: string;
  addresses: string;
  identifiers: string;
  sanctions: string;
  program_ids: string;
  first_seen: string;
  last_seen: string;
};

type SearchResponse = {
  query: string;
  normalized: string;
  total_hits: number;
  threshold: number;
  method: string;
  hits: SearchHit[];
};

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

type FsfStats = {
  total_entries: number;
  persons: number;
  organizations: number;
  other: number;
  loaded_at: string | null;
  source_mtime: string | null;
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

const CONFIDENCE_STYLES: Record<SearchHit['confidence'], { label: string; ring: string; bg: string; text: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  exact: { label: 'Exakter Treffer', ring: 'ring-rose-300', bg: 'bg-rose-600 text-white', text: 'text-rose-700 dark:text-rose-300', icon: AlertTriangle },
  high: { label: 'Hohe Ähnlichkeit', ring: 'ring-orange-300', bg: 'bg-orange-500 text-white', text: 'text-orange-700 dark:text-orange-300', icon: ShieldAlert },
  medium: { label: 'Mittlere Ähnlichkeit', ring: 'ring-amber-300', bg: 'bg-amber-500 text-white', text: 'text-amber-700 dark:text-amber-300', icon: Search },
  low: { label: 'Niedrige Ähnlichkeit', ring: 'ring-slate-300', bg: 'bg-slate-500 text-white', text: 'text-slate-600 dark:text-slate-300', icon: Search },
};

// ── Formatter ───────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
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

function formatInt(n: number | undefined): string {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('de-DE');
}

// ── Hauptkomponente ─────────────────────────────────────────────────────────

export default function SanktionslistenPage() {
  const [lists, setLists] = useState<SanctionsList[]>([]);
  const [method, setMethod] = useState<MethodInfo | null>(null);
  const [stats, setStats] = useState<FsfStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Suche
  const [query, setQuery] = useState('');
  const [minScore, setMinScore] = useState(70);
  const [schemaFilter, setSchemaFilter] = useState<'' | 'Person' | 'Organization'>('');
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/sanctions/lists').then(r => r.json()).then(d => setLists(d.lists || [])).catch(() => {});
    fetch('/api/sanctions/method').then(r => r.json()).then(setMethod).catch(() => {});
    refreshStats();
  }, []);

  function refreshStats() {
    setStatsLoading(true);
    fetch('/api/sanctions/stats').then(r => r.json()).then(setStats).catch(() => {}).finally(() => setStatsLoading(false));
  }

  async function runSearch(e?: FormEvent, override?: string) {
    e?.preventDefault();
    const q = (override ?? query).trim();
    if (q.length < 2) {
      setSearchError('Bitte mindestens 2 Zeichen eingeben.');
      setSearchResult(null);
      return;
    }
    setSearchError(null);
    setSearchLoading(true);
    try {
      const params = new URLSearchParams({ q, limit: '15', min_score: String(minScore) });
      if (schemaFilter) params.set('schema_filter', schemaFilter);
      const r = await fetch(`/api/sanctions/search?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: SearchResponse = await r.json();
      setSearchResult(data);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Suche fehlgeschlagen.');
      setSearchResult(null);
    } finally {
      setSearchLoading(false);
    }
  }

  const exampleQueries = ['Putin', 'Sechin Igor', 'Wagner', 'Lukashenko', 'Rosneft', 'Gazprom Neft'];

  return (
    <div className="space-y-8">
      {/* ── Hero ───────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(46,16,16,0.98),rgba(120,30,40,0.94)_45%,rgba(190,60,50,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-white/80">
              <ShieldAlert size={13} /> Workshop 5 · Mittwoch 10:00
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight lg:text-4xl">Sanktionslisten</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-white/85 lg:text-base">
              Eine kuratierte Übersicht der wichtigsten Sanktions- und Embargo-Verzeichnisse mit
              Kurzcharakteristik, Empfehlung für den Prüfalltag und Direktlink in das jeweilige
              offizielle Tool. Zusätzlich: lokale Fuzzy-Suche gegen die EU Konsolidierte
              Finanzsanktionsliste (FSF) — voll offline, ohne Daten an Dritte.
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
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/60">Lokaler FSF-Index</div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <Stat label="Einträge" value={formatInt(stats?.total_entries)} />
              <Stat label="Personen" value={formatInt(stats?.persons)} />
              <Stat label="Orgs" value={formatInt(stats?.organizations)} />
            </div>
            <div className="mt-4 space-y-1 text-[11px] text-white/70">
              <div className="flex items-center justify-between">
                <span>Quelle aktualisiert</span>
                <span className="font-mono">{formatDate(stats?.source_mtime || null)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Im Speicher seit</span>
                <span className="font-mono">{formatDate(stats?.loaded_at || null)}</span>
              </div>
            </div>
            <button
              onClick={refreshStats}
              disabled={statsLoading}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-2 text-xs font-medium text-white/90 transition hover:bg-white/20 disabled:opacity-50"
            >
              {statsLoading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              Status aktualisieren
            </button>
          </div>
        </div>
      </section>

      {/* ── Suche ──────────────────────────────────────────────────── */}
      <section id="suche" className="rounded-[34px] border border-rose-200/60 bg-gradient-to-br from-white via-rose-50/60 to-white p-6 shadow-[0_24px_80px_-50px_rgba(190,18,60,0.45)] dark:border-rose-500/20 dark:from-slate-900 dark:via-rose-950/20 dark:to-slate-900 lg:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <div className="lg:w-1/3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-600 text-white shadow-lg shadow-rose-600/30">
                <Search size={22} />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Fuzzy-Suche · EU FSF</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">Lokal, ohne API-Aufruf</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
              Personen oder Organisationen prüfen — die Suche toleriert abweichende Schreibung,
              andere Reihenfolge der Namensteile und Rechtsformsuffixe. Sie läuft komplett im
              Workshop-Container.
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
                  disabled={searchLoading}
                  className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2 text-sm font-medium text-white shadow-md shadow-rose-600/30 transition hover:bg-rose-700 disabled:opacity-50"
                >
                  {searchLoading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                  Prüfen
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-200/70 bg-white/60 px-4 py-3 text-xs dark:border-slate-700/70 dark:bg-slate-900/40">
                <div className="flex items-center gap-2">
                  <span className="text-slate-600 dark:text-slate-300">Schwellenwert</span>
                  <input
                    type="range"
                    min={50}
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

            {searchResult && !searchError && (
              <SearchResults result={searchResult} />
            )}

            {!searchResult && !searchError && !searchLoading && (
              <div className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white/40 px-5 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
                Noch keine Suche durchgeführt. Tippen Sie einen Namen ein oder wählen Sie ein Beispiel.
              </div>
            )}
          </div>
        </div>
      </section>

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
                <p className="text-xs text-slate-500 dark:text-slate-400">Was die Fuzzy-Suche tut — und was nicht</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
              {method?.summary}
            </p>
            {method?.library && (
              <div className="mt-5 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs dark:border-slate-700 dark:bg-slate-900">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Library</div>
                <div className="mt-1 font-mono text-cyan-700 dark:text-cyan-300">{method.library}</div>
              </div>
            )}
            {method?.data_source && (
              <div className="mt-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs dark:border-slate-700 dark:bg-slate-900">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">Datenquelle</div>
                <div className="mt-1 text-slate-700 dark:text-slate-200">{method.data_source.name}</div>
                <a href={method.data_source.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-cyan-700 hover:underline dark:text-cyan-300">
                  CSV öffnen <ExternalLink size={11} />
                </a>
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
              Direkter Zugriff auf die offiziellen Quellen — pro Liste mit Empfehlung für den Prüfalltag.
            </p>
          </div>
          <div className="hidden text-xs text-slate-500 dark:text-slate-400 sm:flex sm:items-center sm:gap-2">
            <Database size={14} /> {lists.length} Verzeichnisse
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {lists.map((list) => <ListCard key={list.key} list={list} />)}
        </div>
      </section>

      {/* ── Pruef-Empfehlung ───────────────────────────────────────── */}
      <section className="rounded-[28px] border border-emerald-200/60 bg-gradient-to-br from-emerald-50 via-white to-white p-6 dark:border-emerald-500/20 dark:from-emerald-950/30 dark:via-slate-900 dark:to-slate-900">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-lg shadow-emerald-600/30">
            <ShieldCheck size={22} />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Empfohlener Workflow im Prüfalltag</h3>
            <ol className="mt-3 space-y-2 text-sm leading-6 text-slate-700 dark:text-slate-200">
              <li className="flex gap-3"><span className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-[10px] font-semibold text-white">1</span>Begünstigte und wirtschaftlich Berechtigte gegen die EU FSF prüfen — hier per lokaler Suche oben möglich.</li>
              <li className="flex gap-3"><span className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-[10px] font-semibold text-white">2</span>Bei Treffer oder Verdacht: Geburtsdatum, Land und Identifier (USt-ID, Registernummer) abgleichen — Namensgleichheiten sind häufig.</li>
              <li className="flex gap-3"><span className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-[10px] font-semibold text-white">3</span>Bei Auslandsbezug (UK, CH, USA) ergänzend OFSI / SECO / OFAC prüfen — die EU FSF ist nicht deckungsgleich.</li>
              <li className="flex gap-3"><span className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-[10px] font-semibold text-white">4</span>Prüfergebnis dokumentieren: geprüfte Liste, Suchbegriff, Datum, Ergebnis. Bei Treffer das offizielle EU-Verzeichnis als Beleg ziehen — die FSF ist die verbindliche Quelle.</li>
            </ol>
          </div>
        </div>
      </section>
    </div>
  );
}

// ── Subkomponenten ──────────────────────────────────────────────────────────

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-2 py-3">
      <div className="text-[10px] uppercase tracking-wider text-white/60">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function ListCard({ list }: { list: SanctionsList }) {
  const Icon = ICONS[list.icon] || Globe2;
  const c = COLORS[list.color] || COLORS.indigo;
  return (
    <div className={`group flex h-full flex-col rounded-3xl border border-slate-200/70 bg-white p-5 shadow-sm ring-1 ${c.ring} transition hover:shadow-lg dark:border-slate-800 dark:bg-slate-900`}>
      <div className="flex items-start justify-between gap-3">
        <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${c.iconBg} ${c.iconText} shadow-sm`}>
          <Icon size={22} />
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${c.tagBg}`}>
          {list.tag}
        </span>
      </div>
      <h3 className="mt-4 text-base font-semibold text-slate-900 dark:text-slate-100">{list.name}</h3>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{list.issuer}</p>
      <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{list.description}</p>

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
        <a
          href={list.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <Globe2 size={13} /> Quelle
        </a>
        <a
          href={list.search_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`inline-flex flex-1 items-center justify-center gap-2 rounded-2xl ${c.tagBg} px-3 py-2 text-xs font-medium shadow-sm transition hover:opacity-90`}
        >
          <Search size={13} /> Online suchen <ArrowUpRight size={13} />
        </a>
      </div>
      {list.is_searchable_locally && (
        <div className="mt-2 inline-flex items-center justify-center gap-1 rounded-full bg-slate-900/5 px-2 py-1 text-[10px] font-medium text-slate-600 dark:bg-white/5 dark:text-slate-300">
          <Sparkles size={10} /> auch lokal abfragbar (oben)
        </div>
      )}
    </div>
  );
}

function SearchResults({ result }: { result: SearchResponse }) {
  const summary = useMemo(() => {
    if (result.total_hits === 0) {
      return { tone: 'green', icon: CheckCircle2, title: 'Kein Treffer', text: `Für „${result.query}" wurde in der EU FSF nichts oberhalb des Schwellenwerts gefunden.` };
    }
    const top = result.hits[0];
    if (top.confidence === 'exact' || top.confidence === 'high') {
      return { tone: 'rose', icon: AlertTriangle, title: 'Treffer — prüfen', text: `Höchster Score ${top.score} (${top.confidence}). Manuelle Abklärung erforderlich.` };
    }
    return { tone: 'amber', icon: ShieldAlert, title: 'Hinweise gefunden', text: `${result.total_hits} Ähnlichkeiten oberhalb ${result.threshold}. Geburtsdatum/Land im Detail abgleichen.` };
  }, [result]);

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
              normalisiert: <span className="font-mono">{result.normalized}</span> · Methode: {result.method}
            </div>
          </div>
        </div>
      </div>

      {result.hits.map((hit) => <HitCard key={hit.id} hit={hit} />)}
    </div>
  );
}

function HitCard({ hit }: { hit: SearchHit }) {
  const cs = CONFIDENCE_STYLES[hit.confidence];
  const HitIcon = cs.icon;
  return (
    <div className={`rounded-2xl border border-slate-200 bg-white p-4 ring-1 ${cs.ring} dark:border-slate-700 dark:bg-slate-900`}>
      <div className="flex flex-wrap items-start gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${cs.bg} shadow-sm`}>
          <HitIcon size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{hit.name}</h4>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {hit.schema_type}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${cs.bg}`}>
              Score {hit.score}
            </span>
            <span className={`text-[11px] font-medium ${cs.text}`}>{cs.label}</span>
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
        {hit.program_ids && <Row label="EU-Programm" value={hit.program_ids} mono />}
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
