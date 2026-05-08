/**
 * BeneficiaryCompanySearch — Volltext-Firmensuche im Begünstigtenverzeichnis.
 *
 * Tab 2 des Begünstigten-Workspace (Szenario 6 / /begünstigte). Ruft
 * /api/beneficiaries/search auf und rendert eine Trefferliste analog zur
 * Beihilfe-Tabelle: pro Zeile Firma, Confidence-Badge, Score, Volumen,
 * Quelle(n) und ein Action-Button "In Auswertung übernehmen", der via
 * Deep-Link die Audit-Report-Seite öffnet (?q=<firma>).
 *
 * Export: XLSX (clientseitig via SheetJS) und CSV (über useExport().toCsv).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Building2,
  ChevronRight,
  ClipboardCheck,
  FileSpreadsheet,
  FileDown,
  Loader2,
  MapPin,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import {
  searchBeneficiaries,
  type BeneficiaryCompanyHit,
  type BeneficiaryMatchConfidence,
  type BeneficiarySearchResponse,
  type CountryCode,
} from '../../lib/api';
import { useExport } from '../../lib/useExport';

interface Props {
  countryCode: CountryCode | '';
  // Wird aufgerufen, wenn sich die Liste der Treffer-Firmennamen ändert.
  // Eltern-Komponente nutzt das, um z.B. die Karte zu filtern.
  onResultsChange?: (companyNames: string[]) => void;
}

// Einheitliche Anzeige "EFRE Bremen" — beide Werte mit Leerzeichen,
// Einzelwert allein, sonst leer.
function formatFondsBl(fonds?: string | null, bundesland?: string | null): string {
  const f = (fonds || '').trim();
  const b = (bundesland || '').trim();
  if (f && b) return `${f} ${b}`;
  return f || b || '';
}

// "EFRE (Berlin, Bayern) · ESF+ (Hessen)" für mehrere Fonds/BL eines Treffers.
// Bei genau einem Fonds und einem BL: "EFRE Berlin" (ohne Klammern).
function formatHitFondsBl(fonds: string[], bundeslaender: string[]): string {
  const f = fonds.filter(Boolean);
  const b = bundeslaender.filter(Boolean);
  if (f.length === 0 && b.length === 0) return '';
  if (f.length === 1 && b.length === 1) return `${f[0]} ${b[0]}`;
  if (f.length === 1 && b.length === 0) return f[0];
  if (f.length === 0 && b.length >= 1) return b.join(', ');
  if (f.length === 1 && b.length > 1) return `${f[0]} (${b.join(', ')})`;
  // Mehrere Fonds: jeden Fonds mit Komma-Liste der BL — der API-Response
  // ordnet BL/Fonds nicht 1:1 zu, also Fallback auf separate Anzeige.
  return `${f.join(' · ')}${b.length ? ` (${b.join(', ')})` : ''}`;
}

const CONFIDENCE_BADGE: Record<BeneficiaryMatchConfidence, { label: string; cls: string }> = {
  exact: { label: 'exakt', cls: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300' },
  high: { label: 'hoch', cls: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300' },
  medium: { label: 'mittel', cls: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300' },
  low: { label: 'niedrig', cls: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' },
};

function formatEur(value: number): string {
  return value.toLocaleString('de-DE', { maximumFractionDigits: 0 }) + ' €';
}

function auditReportUrl(name: string, countryCode: CountryCode | ''): string {
  const params = new URLSearchParams();
  params.set('q', name);
  if (countryCode === 'DE' || countryCode === 'AT') {
    params.set('country_code', countryCode);
  }
  return `/audit-report?${params.toString()}`;
}

export default function BeneficiaryCompanySearch({ countryCode, onResultsChange }: Props) {
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [response, setResponse] = useState<BeneficiarySearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // Welche Treffer auf der Karte angezeigt werden sollen. Initial: alle.
  // Damit kann der Pruefer einzelne Treffer ein-/ausblenden, ohne die Suche
  // neu starten zu muessen.
  const [mapSelected, setMapSelected] = useState<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);
  const exportApi = useExport();

  const runSearch = useCallback(
    async (raw: string) => {
      const trimmed = raw.trim();
      if (trimmed.length < 2) {
        setError('Bitte mindestens 2 Zeichen eingeben.');
        return;
      }
      abortRef.current?.abort();
      setLoading(true);
      setError(null);
      setSubmittedQuery(trimmed);
      try {
        const data = await searchBeneficiaries({
          q: trimmed,
          scope: 'company',
          country_code: countryCode || undefined,
          // limit zaehlt nach Records (vor Company-Gruppierung). Wird er
          // zu klein gewaehlt, fallen unique Firmen mit nur 1-2 Records
          // unter Score-Tail-Records anderer Firmen heraus. Max-Werte des
          // Backend-Endpoints (limit<=200, company_limit<=50) ausschoepfen.
          limit: 200,
          company_limit: 50,
        });
        setResponse(data);
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : 'Suche fehlgeschlagen.');
        setResponse(null);
      } finally {
        setLoading(false);
      }
    },
    [countryCode],
  );

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    void runSearch(query);
  };

  const onReset = () => {
    setQuery('');
    setSubmittedQuery('');
    setResponse(null);
    setError(null);
    setExpanded(new Set());
    setMapSelected(new Set());
  };

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const toggleMapSelection = (name: string) => {
    setMapSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const companies = useMemo(() => response?.companies ?? [], [response]);

  // Bei jeder neuen Trefferliste alle automatisch fuer die Karte aktivieren.
  useEffect(() => {
    setMapSelected(new Set(companies.map((c) => c.company_name)));
  }, [companies]);

  const setAllMapSelection = (on: boolean) => {
    setMapSelected(on ? new Set(companies.map((c) => c.company_name)) : new Set());
  };

  // Aktuell ausgewaehlte Karten-Filter nach oben melden (Workspace -> Map).
  // Beim Unmount: Liste leeren, damit die Karte zum Default zurueckkehrt.
  useEffect(() => {
    onResultsChange?.(Array.from(mapSelected));
  }, [mapSelected, onResultsChange]);
  useEffect(() => {
    return () => {
      onResultsChange?.([]);
    };
  }, [onResultsChange]);

  const totalVolume = useMemo(
    () => companies.reduce((sum, c) => sum + (c.total_kosten || 0), 0),
    [companies],
  );

  const exportRows = useMemo(
    () =>
      companies.map((c) => ({
        Firma: c.company_name,
        Vorhaben: c.project_count,
        Volumen_EUR: Math.round(c.total_kosten || 0),
        Score: c.match_score,
        Konfidenz: c.match_confidence ?? '',
        Bundeslaender: (c.bundeslaender || []).join(', '),
        Fonds: (c.fonds || []).join(', '),
        Standorte: (c.standorte || []).join('; '),
        Quellen: (c.sources || []).join(', '),
      })),
    [companies],
  );

  const handleCsvExport = () => {
    if (exportRows.length === 0) return;
    exportApi.toCsv(exportRows, {
      filename: `unternehmenssuche_${submittedQuery || 'export'}_${new Date().toISOString().slice(0, 10)}`,
    });
  };

  const handleXlsxExport = () => {
    if (!submittedQuery) return;
    // Backend-Export: /api/beneficiaries/export liefert vollständige Records
    // als XLSX. Browser lädt direkt herunter — kein extra Lib im Bundle nötig.
    const params = new URLSearchParams();
    params.set('format', 'xlsx');
    params.set('q', submittedQuery);
    params.set('scope', 'company');
    params.set('limit', '500');
    if (countryCode) params.set('country_code', countryCode);
    window.open(`/api/beneficiaries/export?${params.toString()}`, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="space-y-4">
      {/* Suchfeld */}
      <form
        onSubmit={onSubmit}
        className="rounded-[24px] border border-rose-200/70 bg-white/85 p-4 shadow-[0_18px_60px_-48px_rgba(225,29,72,0.5)] backdrop-blur dark:border-rose-900/60 dark:bg-slate-900/75"
      >
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-rose-700/80 dark:text-rose-300/80">
          Firmenname suchen
        </label>
        <div className="mt-2 flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[260px]">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder='z.B. "Volkswagen", "Stadt Heiligenhaus" oder "Trumpf Laser"'
              className="w-full rounded-full border border-rose-200 bg-white py-2.5 pl-9 pr-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-rose-400 focus:ring-2 focus:ring-rose-200 dark:border-rose-900/70 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-rose-500"
              aria-label="Firmenname suchen"
              autoComplete="off"
            />
          </div>
          <button
            type="submit"
            disabled={loading || query.trim().length < 2}
            className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-rose-600 to-amber-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md transition hover:from-rose-700 hover:to-amber-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
            {loading ? 'Sucht…' : 'Suchen'}
          </button>
          {(submittedQuery || response) && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <X size={12} /> Zurücksetzen
            </button>
          )}
        </div>
        <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
          Fuzzy-Suche über alle geladenen Begünstigtenverzeichnisse
          {countryCode === 'DE' && ' (Deutschland)'}
          {countryCode === 'AT' && ' (Österreich)'}
          {!countryCode && ' (alle Länder)'}. Akronyme und Schreibvarianten werden automatisch berücksichtigt.
        </p>
      </form>

      {/* Fehler */}
      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Empty-State */}
      {!response && !loading && (
        <div className="rounded-[24px] border border-dashed border-slate-300 bg-white/60 px-6 py-10 text-center dark:border-slate-700 dark:bg-slate-900/60">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-500 dark:bg-rose-950/40 dark:text-rose-300">
            <Building2 size={20} />
          </div>
          <h3 className="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
            Geben Sie einen Firmennamen ein
          </h3>
          <p className="mt-1.5 text-xs leading-5 text-slate-500 dark:text-slate-400">
            Die Suche findet Begünstigte über alle Bundesländer und Fonds hinweg, inklusive Schreibvarianten.
          </p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="rounded-[24px] border border-slate-200 bg-white px-6 py-10 text-center dark:border-slate-700 dark:bg-slate-900">
          <Loader2 size={22} className="mx-auto animate-spin text-rose-500" />
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Suche läuft…</p>
        </div>
      )}

      {/* Trefferliste */}
      {response && !loading && (
        <div className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/75">
          {/* Header mit Stats + Export */}
          <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/70 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                {companies.length === 0
                  ? 'Keine Treffer'
                  : `${companies.length.toLocaleString('de-DE')} Begünstigte gefunden`}
              </div>
              {companies.length > 0 && (
                <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                  {response.summary.records_scanned.toLocaleString('de-DE')} Datensätze geprüft · Gesamtvolumen{' '}
                  {formatEur(totalVolume)} · {mapSelected.size} von {companies.length} auf Karte
                </div>
              )}
            </div>
            {companies.length > 0 && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setAllMapSelection(mapSelected.size < companies.length)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-100 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-200 dark:hover:bg-rose-950/50"
                  title="Alle Treffer auf der Karte ein- oder ausblenden"
                >
                  <MapPin size={12} />
                  {mapSelected.size < companies.length ? 'Alle auf Karte' : 'Karte leeren'}
                </button>
                <button
                  type="button"
                  onClick={handleXlsxExport}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                  title="Trefferliste als XLSX exportieren"
                >
                  <FileSpreadsheet size={12} /> XLSX
                </button>
                <button
                  type="button"
                  onClick={handleCsvExport}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                  title="Trefferliste als CSV exportieren"
                >
                  <FileDown size={12} /> CSV
                </button>
              </div>
            )}
          </div>

          {companies.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Keine Begünstigten für „{submittedQuery}"
                {countryCode === 'DE' && ' in Deutschland'}
                {countryCode === 'AT' && ' in Österreich'}.
              </p>
              <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
                Versuchen Sie eine andere Schreibweise oder schalten Sie den Länderfilter auf „Alle".
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {companies.map((c) => (
                <CompanyRow
                  key={`${c.company_name}-${c.sources.join('|')}`}
                  hit={c}
                  countryCode={countryCode}
                  expanded={expanded.has(c.company_name)}
                  onToggle={() => toggleExpand(c.company_name)}
                  onMap={mapSelected.has(c.company_name)}
                  onToggleMap={() => toggleMapSelection(c.company_name)}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

interface RowProps {
  hit: BeneficiaryCompanyHit;
  countryCode: CountryCode | '';
  expanded: boolean;
  onToggle: () => void;
  onMap: boolean;
  onToggleMap: () => void;
}

function CompanyRow({ hit, countryCode, expanded, onToggle, onMap, onToggleMap }: RowProps) {
  const confidence = hit.match_confidence ?? 'low';
  const badge = CONFIDENCE_BADGE[confidence];
  const standortPreview = hit.standorte.slice(0, 2).join(', ');
  const moreLocations = hit.standorte.length - 2;

  return (
    <li className="px-4 py-3 transition hover:bg-slate-50/80 dark:hover:bg-slate-800/40">
      <div className="flex flex-wrap items-start justify-between gap-3">
        {/* Karten-Checkbox */}
        <label
          className="mt-0.5 inline-flex shrink-0 cursor-pointer items-center gap-1.5 self-center rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-medium text-slate-600 transition hover:border-rose-300 hover:bg-rose-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-rose-500/40 dark:hover:bg-rose-950/30"
          title="Auf Karte anzeigen"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={onMap}
            onChange={onToggleMap}
            className="h-3 w-3 cursor-pointer accent-rose-600"
            aria-label={`„${hit.company_name}" auf Karte ${onMap ? 'ausblenden' : 'anzeigen'}`}
          />
          <MapPin size={11} className={onMap ? 'text-rose-600' : 'text-slate-400'} />
        </label>

        {/* Linke Spalte: Firma + Kontextdaten */}
        <button
          type="button"
          onClick={onToggle}
          className="group flex flex-1 min-w-[240px] items-start gap-3 text-left"
          aria-expanded={expanded}
        >
          <ChevronRight
            size={16}
            className={`mt-0.5 shrink-0 text-slate-400 transition-transform ${expanded ? 'rotate-90 text-rose-500' : ''}`}
          />
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-900 group-hover:text-rose-700 dark:text-slate-100 dark:group-hover:text-rose-300">
                {hit.company_name}
              </span>
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge.cls}`}>
                {Math.round(hit.match_score)} · {badge.label}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              <span>
                {hit.project_count} Vorhaben · {hit.total_kosten_label}
              </span>
              {(() => {
                const fb = formatHitFondsBl(hit.fonds, hit.bundeslaender);
                return fb ? <span>{fb}</span> : null;
              })()}
              {standortPreview && (
                <span className="inline-flex items-center gap-1">
                  <MapPin size={10} />
                  {standortPreview}
                  {moreLocations > 0 && ` +${moreLocations}`}
                </span>
              )}
            </div>
          </div>
        </button>

        {/* Rechte Spalte: Action */}
        <Link
          to={auditReportUrl(hit.company_name, countryCode)}
          onClick={(e) => e.stopPropagation()}
          title="In Auswertung übernehmen"
          className="inline-flex shrink-0 items-center gap-1.5 self-center rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[11px] font-medium text-indigo-700 transition hover:border-indigo-300 hover:bg-indigo-100 dark:border-indigo-500/30 dark:bg-indigo-950/30 dark:text-indigo-200 dark:hover:bg-indigo-950/50"
        >
          <ClipboardCheck size={12} />
          In Auswertung übernehmen
        </Link>
      </div>

      {/* Aufgeklappt: Projekt-Liste */}
      {expanded && hit.projects.length > 0 && (
        <ul className="mt-3 space-y-1.5 rounded-2xl bg-slate-50 px-3 py-2.5 text-xs dark:bg-slate-800/40">
          <li className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            <Sparkles size={10} className="text-rose-500" />
            {hit.projects.length} Vorhaben
          </li>
          {hit.projects.map((p, i) => {
            const fondsBl = formatFondsBl(p.fonds, p.bundesland);
            // Land nur zeigen, wenn es vom Filter abweicht — bei AT-Treffern
            // in einem DE-Filter (oder Filter "Alle") relevant.
            const showCountry = !!p.country_name && p.country_code !== countryCode;
            return (
              <li
                key={`${p.project_name}-${i}`}
                className="border-l-2 border-rose-200 pl-3 py-1 text-slate-700 dark:border-rose-900/60 dark:text-slate-300"
              >
                <div className="font-medium leading-snug">{p.project_name || '(ohne Bezeichnung)'}</div>
                {p.aktenzeichen && (
                  <div className="mt-0.5">
                    <code className="rounded bg-slate-200/70 px-1 py-0.5 text-[10px] text-slate-600 dark:bg-slate-700/60 dark:text-slate-300">
                      {p.aktenzeichen}
                    </code>
                  </div>
                )}
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-slate-500 dark:text-slate-400">
                  {p.kosten_label && <span>{p.kosten_label}</span>}
                  {fondsBl && <span>{fondsBl}</span>}
                  {p.location && (
                    <span className="inline-flex items-center gap-0.5">
                      <MapPin size={9} />
                      {p.location}
                    </span>
                  )}
                  {p.periode && <span>{p.periode}</span>}
                  {p.category && (
                    <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-600 dark:bg-slate-700/50 dark:text-slate-300">
                      {p.category}
                    </span>
                  )}
                  {showCountry && (
                    <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[9px] font-medium text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                      {p.country_name}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </li>
  );
}
