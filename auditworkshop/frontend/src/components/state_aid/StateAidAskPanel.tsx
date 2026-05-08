/**
 * StateAidAskPanel — KI-Suche fuer das Beihilfe-Transparenzregister.
 *
 * Backend-Endpoint: POST /api/state-aid/ask (SSE-Stream).
 * Streamt vier Event-Typen: filter, results, summary_token, done.
 *
 * UX-Konzept:
 *  - Grosses Texteingabe-Feld („Frag in einem Satz …").
 *  - Beispiel-Chips fuellen das Feld bei Klick.
 *  - Stop-Button waehrend des Streams; Frage stellen-Button sonst.
 *  - Drei Sektionen: Erkannte Filter, Treffer-Tabelle (max. 10), Zusammenfassung
 *    mit Streaming-Cursor.
 *  - Pflicht-Hinweis: „Filter vom LLM, Treffer und Betraege aus der DB."
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  AlertTriangle, BrainCircuit, ExternalLink, Filter as FilterIcon, Loader2, Send,
  Sparkles, StopCircle, Wand2,
} from 'lucide-react';
import {
  askStateAid,
  type AskController,
  type AskResultsPayload,
  type StateAidSearchHit,
} from '../../lib/stateAidApi';
import type { StateAidFilterState } from './stateAidFilters';

interface Props {
  countryCode: string;
  /**
   * Wird aufgerufen, wenn der Nutzer die erkannten Filter in den Treffer-Tab
   * uebernehmen will. Die Page setzt damit die Filter und wechselt den Tab.
   */
  onApplyFilters: (patch: Partial<StateAidFilterState>) => void;
}

const EXAMPLE_QUESTIONS: string[] = [
  'Alle Beihilfen über 1 Mio. EUR aus Bayern für Maschinenbau im Jahr 2022',
  'Welche Fördersummen erhielt die Robert Bosch GmbH in den letzten drei Jahren?',
  'Top 10 Empfänger in Sachsen seit 2021',
  'Beihilfen mit Bürgschaft als Instrument in Hessen',
  'Alle Awards mit SA-Referenz aus 2023',
  'Welche Behörde hat 2024 in Berlin am meisten ausgezahlt?',
];

function formatEur(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value);
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

/**
 * Heuristik: Welche LLM-Filter koennen direkt in den Suchpanel-State uebernommen
 * werden? Strings/Numbers werden 1:1 gemappt; unbekannte Schluessel ignoriert.
 */
function filterToPatch(filter: Record<string, unknown>): Partial<StateAidFilterState> {
  const patch: Partial<StateAidFilterState> = {};
  const setStr = (key: keyof StateAidFilterState, raw: unknown) => {
    if (typeof raw === 'string' && raw.trim()) {
      // min_score erwartet number, alle anderen string — daher hier nur Strings.
      (patch as Record<string, string>)[key] = raw.trim();
    }
  };
  setStr('q', filter.q);
  setStr('country_code', filter.country_code);
  setStr('nuts_code', filter.nuts_code);
  setStr('since', filter.since);
  setStr('until', filter.until);
  setStr('aid_instrument', filter.aid_instrument);
  setStr('aid_objective', filter.aid_objective);
  setStr('granting_authority', filter.granting_authority);
  setStr('sa_reference', filter.sa_reference);
  setStr('source_key', filter.source_key);
  setStr('nace', filter.nace);
  if (typeof filter.min_amount === 'number') patch.min_amount = String(filter.min_amount);
  if (typeof filter.max_amount === 'number') patch.max_amount = String(filter.max_amount);
  return patch;
}

export default function StateAidAskPanel({ countryCode, onApplyFilters }: Props) {
  const [question, setQuestion] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [filters, setFilters] = useState<Record<string, unknown> | null>(null);
  const [results, setResults] = useState<AskResultsPayload | null>(null);
  const [summary, setSummary] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const controllerRef = useRef<AskController | null>(null);

  // Beim Unmount laufenden Stream abbrechen.
  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  function reset() {
    setFilters(null);
    setResults(null);
    setSummary('');
    setError(null);
    setElapsedMs(null);
  }

  function start(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 3) return;
    controllerRef.current?.abort();
    reset();
    setStreaming(true);
    const ctrl = askStateAid(
      {
        question: trimmed,
        country_code: countryCode || undefined,
        locale: 'de',
        limit: 50,
      },
      {
        onFilter: (f) => setFilters(f),
        onResults: (r) => setResults(r),
        onSummaryToken: (t) => setSummary((prev) => prev + t),
        onDone: (d) => {
          setElapsedMs(d.elapsed_ms);
          setStreaming(false);
        },
        onError: (msg) => {
          setError(msg);
          setStreaming(false);
        },
      },
    );
    controllerRef.current = ctrl;
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    start(question);
  }

  function handleStop() {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setStreaming(false);
  }

  const submitDisabled = streaming || question.trim().length < 3;
  const previewHits = useMemo(() => results?.hits.slice(0, 10) ?? [], [results]);

  // Sortierte Filter-Eintraege fuer die Anzeige.
  const filterEntries = useMemo(() => {
    if (!filters) return [] as Array<[string, unknown]>;
    return Object.entries(filters).filter(([, v]) => {
      if (v === null || v === undefined) return false;
      if (typeof v === 'string' && !v.trim()) return false;
      return true;
    });
  }, [filters]);

  function handleApplyAndJump() {
    if (!filters) return;
    onApplyFilters(filterToPatch(filters));
  }

  return (
    <section className="space-y-4">
      {/* ── Eingabe-Card ─────────────────────────────────────────────── */}
      <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
            <BrainCircuit size={20} />
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold text-slate-900 dark:text-white">KI-Suche</div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Frag in einem Satz — die KI extrahiert Filter, die Datenbank liefert die Treffer.
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div className="rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] p-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Frag in einem Satz: alle Beihilfen über 1 Mio. EUR aus Bayern für Maschinenbau 2022"
              rows={3}
              className="w-full resize-none rounded-[20px] border border-slate-200 bg-white/90 px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100 dark:focus:border-emerald-500 dark:focus:ring-emerald-500/30"
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {streaming ? (
                <button
                  type="button"
                  onClick={handleStop}
                  className="inline-flex items-center gap-2 rounded-full bg-rose-600 px-5 py-2.5 text-sm font-medium text-white shadow-md shadow-rose-600/30 transition hover:bg-rose-700"
                >
                  <StopCircle size={14} /> Stop
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={submitDisabled}
                  className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white shadow-md shadow-emerald-600/30 transition hover:bg-emerald-700 disabled:opacity-50"
                >
                  <Send size={14} /> Frage stellen
                </button>
              )}
              {streaming && (
                <span className="inline-flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <Loader2 size={12} className="animate-spin" /> Streaming …
                </span>
              )}
              {!streaming && elapsedMs !== null && (
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  Fertig in {(elapsedMs / 1000).toFixed(1)} s
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Beispiele
            </span>
            {EXAMPLE_QUESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => {
                  setQuestion(q);
                  if (!streaming) start(q);
                }}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 transition hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-emerald-500/40 dark:hover:bg-emerald-950/30 dark:hover:text-emerald-200"
              >
                {q}
              </button>
            ))}
          </div>
        </form>
      </div>

      {/* ── Pflichthinweis ──────────────────────────────────────────── */}
      <div className="flex items-start gap-2 rounded-[22px] border border-slate-200/70 bg-slate-50/70 px-4 py-2 text-[11px] leading-5 text-slate-500 dark:border-slate-700/70 dark:bg-slate-900/40 dark:text-slate-400">
        <Sparkles size={12} className="mt-0.5 shrink-0 text-emerald-500" />
        <span>
          Die Filter werden vom LLM ermittelt. Treffer und Beträge stammen direkt
          aus der Datenbank, nicht vom LLM.
        </span>
      </div>

      {/* ── Fehler ──────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-2 rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── Erkannte Filter ─────────────────────────────────────────── */}
      {filters && (
        <div className="rounded-[26px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                <FilterIcon size={16} />
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white">Erkannte Filter</div>
                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  Vom LLM aus der Frage extrahiert.
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={handleApplyAndJump}
              disabled={filterEntries.length === 0}
              className="inline-flex items-center gap-1 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
              title="Filter übernehmen und zum Treffer-Tab wechseln"
            >
              <Wand2 size={12} /> In Treffer-Tab übernehmen
            </button>
          </div>
          {filterEntries.length === 0 ? (
            <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
              Keine spezifischen Filter erkannt — die Suche läuft über das aktuelle Land.
            </p>
          ) : (
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {filterEntries.map(([k, v]) => (
                <li
                  key={k}
                  className="flex items-start justify-between gap-3 rounded-[18px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-3 py-2 text-xs dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]"
                >
                  <span className="font-mono uppercase tracking-wider text-[10px] text-slate-500 dark:text-slate-400">
                    {k}
                  </span>
                  <span className="font-medium text-slate-800 dark:text-slate-100">
                    {String(v)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── Treffer-Vorschau ────────────────────────────────────────── */}
      {results && (
        <div className="rounded-[26px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                <Sparkles size={16} />
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white">
                  Treffer · {results.total_hits.toLocaleString('de-DE')}
                </div>
                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  Vorschau auf max. 10 Einträge.
                </div>
              </div>
            </div>
            {results.total_hits > previewHits.length && (
              <button
                type="button"
                onClick={handleApplyAndJump}
                className="inline-flex items-center gap-1 rounded-full border border-emerald-300 bg-white px-3 py-1.5 text-xs font-medium text-emerald-800 transition hover:bg-emerald-50 dark:border-emerald-500/40 dark:bg-slate-900 dark:text-emerald-200 dark:hover:bg-emerald-950/30"
              >
                Weitere ansehen <ExternalLink size={11} />
              </button>
            )}
          </div>

          {previewHits.length === 0 ? (
            <div className="mt-4 rounded-[20px] border border-amber-200 bg-amber-50/70 px-4 py-4 text-xs leading-5 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
              <div className="flex items-start gap-2">
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-300" />
                <div className="flex-1">
                  <div className="font-semibold">
                    Keine Treffer für die erkannten Filter
                  </div>
                  <p className="mt-1 text-amber-800/90 dark:text-amber-100/85">
                    LLM-Filter waren zu spezifisch — versuche es mit weniger
                    Stichworten oder ohne Zeitraum. Beispiele:
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {EXAMPLE_QUESTIONS.slice(0, 3).map((q) => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => {
                          setQuestion(q);
                          if (!streaming) start(q);
                        }}
                        className="rounded-full border border-amber-300 bg-white px-3 py-1 text-[11px] font-medium text-amber-800 transition hover:border-amber-400 hover:bg-amber-100/80 dark:border-amber-500/40 dark:bg-slate-900 dark:text-amber-200 dark:hover:bg-amber-950/40"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-4 overflow-hidden rounded-[20px] border border-slate-200/80 dark:border-slate-800">
              <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
                <thead className="bg-slate-50 dark:bg-slate-900/60">
                  <tr className="text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <th className="px-3 py-2">Begünstigter</th>
                    <th className="px-3 py-2">Land · Region</th>
                    <th className="px-3 py-2 text-right">Betrag</th>
                    <th className="px-3 py-2">Datum</th>
                    <th className="px-3 py-2">Instrument</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {previewHits.map((hit: StateAidSearchHit) => {
                    const region = [hit.country_code, hit.nuts_label || hit.nuts_code].filter(Boolean).join(' · ');
                    return (
                      <tr key={hit.award_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                        <td className="px-3 py-2">
                          <div className="font-medium text-slate-900 dark:text-slate-100">{hit.beneficiary_name}</div>
                          {hit.beneficiary_identifier && (
                            <div className="mt-0.5 font-mono text-[10px] text-slate-400">{hit.beneficiary_identifier}</div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{region || '—'}</td>
                        <td className="px-3 py-2 text-right font-mono text-slate-900 dark:text-slate-100">
                          {formatEur(hit.aid_amount_eur ?? hit.aid_amount)}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-slate-600 dark:text-slate-300">
                          {formatDate(hit.granting_date || hit.publication_date)}
                        </td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{hit.aid_instrument || '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Zusammenfassung ─────────────────────────────────────────── */}
      {(summary || streaming) && (
        <div className="rounded-[26px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
              <BrainCircuit size={16} />
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-900 dark:text-white">Zusammenfassung</div>
              <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                Klartext-Antwort des LLM.
              </div>
            </div>
          </div>
          <div className="mt-4 rounded-[20px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
            {summary ? (
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-700 dark:text-slate-200">
                {summary}
                {streaming && (
                  <span className="ml-0.5 inline-block h-4 w-2 animate-cursor rounded-sm bg-emerald-500 align-middle dark:bg-emerald-400" />
                )}
              </pre>
            ) : (
              <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                <Loader2 size={14} className="animate-spin" />
                Warte auf Antwort …
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
