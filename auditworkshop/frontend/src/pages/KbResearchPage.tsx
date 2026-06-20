import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, Sparkles, X, Loader2, ExternalLink, AlertTriangle, Cpu,
  Database, ShieldCheck, ListOrdered, ChevronDown,
} from 'lucide-react';
import {
  searchKnowledge,
  streamKbGenerate,
  getKnowledgeStats,
  getKnowledgeGroups,
  type SearchResult,
  type KbGeneratedSource,
  type KbTextType,
  type KbTextLength,
  type KnowledgeSource,
} from '../lib/api';

type Mode = 'search' | 'generate';

const MODE_OPTIONS: { value: Mode; label: string }[] = [
  { value: 'search', label: 'Fundstellen suchen' },
  { value: 'generate', label: 'Text generieren' },
];

const TEXT_TYPE_OPTIONS: { value: KbTextType; label: string }[] = [
  { value: 'analyse', label: 'Analyse' },
  { value: 'zusammenfassung', label: 'Kurzantwort' },
  { value: 'stellungnahme', label: 'Stellungnahme' },
  { value: 'vermerk', label: 'Vermerk' },
  { value: 'pruefbericht', label: 'Prüfbericht' },
];

const LENGTH_OPTIONS: { value: KbTextLength; label: string }[] = [
  { value: 'kurz', label: 'Kurz' },
  { value: 'mittel', label: 'Mittel' },
  { value: 'lang', label: 'Lang' },
];

const SUGGESTIONS = [
  'Was ist das Besserstellungsverbot?',
  'Welche Auflagen gelten bei vereinfachten Kostenoptionen?',
  'Art. 74 Verwaltungskontrolle',
  'Anforderungen an die Belegprüfung',
  'Was sind Querschnittsziele?',
  'Natura 2000 — FFH-Verträglichkeit im Huckepackverfahren',
];

const MIN_RELEVANCE = 0.1;
const ABSTENTION = 'die wissensbasis enthält keine belege zu dieser frage.';

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function highlightQuery(text: string, query: string): string {
  if (!query.trim()) return escapeHtml(text);
  const escaped = escapeHtml(text);
  const words = query.trim().split(/\s+/).filter((w) => w.length >= 3);
  if (!words.length) return escaped;
  const pattern = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const regex = new RegExp(`(${pattern})`, 'gi');
  return escaped.replace(regex, '<mark>$1</mark>');
}

function getSnippet(content: string, query: string, contextChars = 160): string {
  if (!query.trim() || !content) return content.slice(0, contextChars * 2);
  const words = query.trim().split(/\s+/).filter((w) => w.length >= 3);
  if (!words.length) return content.slice(0, contextChars * 2);
  let bestPos = -1;
  for (const word of words) {
    const idx = content.toLowerCase().indexOf(word.toLowerCase());
    if (idx !== -1) { bestPos = idx; break; }
  }
  if (bestPos === -1) return content.slice(0, contextChars * 2);
  const start = Math.max(0, bestPos - contextChars);
  const end = Math.min(content.length, bestPos + contextChars);
  let snippet = content.slice(start, end);
  if (start > 0) snippet = '…' + snippet;
  if (end < content.length) snippet = snippet + '…';
  return snippet;
}

export default function KbResearchPage() {
  const [mode, setMode] = useState<Mode>('search');
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('');
  const [textType, setTextType] = useState<KbTextType>('analyse');
  const [length, setLength] = useState<KbTextLength>('mittel');
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [groups, setGroups] = useState<Record<string, string[]>>({});
  const [showHelp, setShowHelp] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState('');

  // Suche
  const [results, setResults] = useState<SearchResult[]>([]);
  // Generierung
  const [generatedText, setGeneratedText] = useState('');
  const [genSources, setGenSources] = useState<KbGeneratedSource[]>([]);
  const [genModel, setGenModel] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    getKnowledgeStats().then((s) => setSources(s.sources ?? [])).catch(() => setSources([]));
    // Quellen-Gruppen laden und die Standard-Auswahl (z. B. „Grundlagen
    // Strukturfonds") als Vorbelegung des Quellen-Filters setzen.
    getKnowledgeGroups()
      .then((g) => { setGroups(g.groups ?? {}); if (g.default_source) setSource(g.default_source); })
      .catch(() => { /* ignore */ });
    return () => abortRef.current?.abort();
  }, []);

  const filteredResults = useMemo(
    () => results.filter((r) => (typeof r.score === 'number' ? r.score >= MIN_RELEVANCE : true)),
    [results],
  );
  const hiddenLowRelevance = results.length - filteredResults.length;

  const isAbstention = useMemo(() => {
    const t = generatedText.trim().toLowerCase();
    return !!t && t.startsWith(ABSTENTION);
  }, [generatedText]);

  function reset() {
    setResults([]);
    setGeneratedText('');
    setGenSources([]);
    setGenModel(null);
    setError('');
  }

  function clearAll() {
    abortRef.current?.abort();
    setQuery('');
    reset();
    setHasSearched(false);
    setIsLoading(false);
  }

  async function runSearch() {
    const q = query.trim();
    if (!q || isLoading) return;
    abortRef.current?.abort();
    setIsLoading(true);
    setHasSearched(true);
    reset();

    if (mode === 'search') {
      try {
        const res = await searchKnowledge(q, 12);
        const all = res.results || [];
        // `source` kann ein Gruppenname (z. B. „Grundlagen Strukturfonds") oder
        // eine Einzelquelle sein. Bei einer Gruppe nach ihren Mitglieds-Quellen
        // filtern, bei einer Einzelquelle exakt, sonst alle Treffer zeigen.
        const members = groups[source];
        const filtered = !source
          ? all
          : members
            ? all.filter((r) => members.includes(r.source))
            : all.filter((r) => r.source === source);
        setResults(filtered);
      } catch {
        setError('Die Fundstellensuche ist fehlgeschlagen.');
      } finally {
        setIsLoading(false);
      }
      return;
    }

    // Generieren — SSE-Stream
    abortRef.current = streamKbGenerate(
      { query: q, text_type: textType, length, source: source || undefined },
      (token) => setGeneratedText((prev) => prev + token),
      (src) => setGenSources(src),
      (info) => { setGenModel(info.model ?? null); setIsLoading(false); },
      (err) => { setError(err || 'Die Textgenerierung ist fehlgeschlagen.'); setIsLoading(false); },
    );
  }

  function applySuggestion(s: string) {
    setQuery(s);
    setTimeout(runSearch, 0);
  }

  const showEmpty = hasSearched && !isLoading && !error
    && (mode === 'search' ? results.length === 0 : !generatedText);

  return (
    <div className="space-y-6">
      {/* Kopf */}
      <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/85 shadow-[0_22px_70px_-44px_rgba(15,23,42,0.65)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <div className="relative px-6 py-7 sm:px-8">
          <div className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.18),transparent_55%),radial-gradient(circle_at_top_right,rgba(59,130,246,0.15),transparent_45%)]" />
          <div className="relative space-y-6">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl">
                <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                  <Sparkles size={13} /> Wissens-Recherche
                </div>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
                  Recherche in der Wissensbasis
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-400 sm:text-base">
                  Durchsuchen Sie die eingelesenen Verordnungen und Dokumente semantisch
                  &mdash; oder lassen Sie aus den Fundstellen einen belegbasierten Text
                  erzeugen. Die Generierung nutzt Qwen3 14B lokal &uuml;ber den
                  ai-router (Reasoning f&uuml;r schnelle Antworten abgeschaltet).
                </p>
              </div>

              <div className="inline-flex rounded-2xl bg-slate-100 p-1 shadow-inner dark:bg-slate-800">
                {MODE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`rounded-[14px] px-4 py-2.5 text-sm font-medium transition-all ${
                      mode === opt.value
                        ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white'
                        : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                    }`}
                    onClick={() => { setMode(opt.value); reset(); setHasSearched(false); }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Suchzeile */}
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
              <div className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyUp={(e) => e.key === 'Enter' && runSearch()}
                  type="text"
                  placeholder={mode === 'generate'
                    ? 'z. B. Fasse die Anforderungen an die Verwaltungskontrolle zusammen.'
                    : 'z. B. Besserstellungsverbot · Art. 74 · vereinfachte Kostenoptionen'}
                  className="w-full rounded-[22px] border border-slate-200 bg-slate-50 px-5 py-8 pl-12 text-base text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-100 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:placeholder:text-slate-500 dark:focus:border-emerald-500 dark:focus:bg-slate-700 dark:focus:ring-emerald-900/40 sm:text-lg"
                />
                {query && (
                  <button
                    className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700"
                    onClick={clearAll}
                    aria-label="Leeren"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>

              <button
                disabled={!query.trim() || isLoading}
                onClick={runSearch}
                className="inline-flex items-center justify-center gap-2 rounded-[20px] bg-slate-900 px-6 py-8 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none dark:bg-emerald-600 dark:hover:bg-emerald-700 dark:disabled:bg-slate-700"
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : (mode === 'generate' ? <Sparkles size={16} /> : <Search size={16} />)}
                {mode === 'generate' ? 'Text generieren' : 'Fundstellen suchen'}
              </button>
            </div>

            {/* Filter / Optionen */}
            <div className="flex flex-wrap items-end gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Quelle</span>
                <select
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  className="rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 shadow-sm outline-none transition focus:border-emerald-400 focus:ring-4 focus:ring-emerald-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:focus:border-emerald-500 dark:focus:ring-emerald-900/40"
                >
                  {Object.keys(groups).length > 0 && (
                    <optgroup label="Themengruppen">
                      {Object.keys(groups).map((g) => (
                        <option key={g} value={g}>{g}</option>
                      ))}
                    </optgroup>
                  )}
                  <option value="">Alle Quellen</option>
                  <optgroup label="Einzelquellen">
                    {sources.map((s) => (
                      <option key={s.source} value={s.source}>{s.source} ({s.chunks})</option>
                    ))}
                  </optgroup>
                </select>
              </label>

              {mode === 'generate' && (
                <>
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Textart</span>
                    <select
                      value={textType}
                      onChange={(e) => setTextType(e.target.value as KbTextType)}
                      className="rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 shadow-sm outline-none transition focus:border-emerald-400 focus:ring-4 focus:ring-emerald-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:focus:border-emerald-500 dark:focus:ring-emerald-900/40"
                    >
                      {TEXT_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Länge</span>
                    <select
                      value={length}
                      onChange={(e) => setLength(e.target.value as KbTextLength)}
                      className="rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 shadow-sm outline-none transition focus:border-emerald-400 focus:ring-4 focus:ring-emerald-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:focus:border-emerald-500 dark:focus:ring-emerald-900/40"
                    >
                      {LENGTH_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </label>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Startzustand mit Vorschlägen — vor der Erläuterung */}
      {!hasSearched && !isLoading && (
        <section className="rounded-[24px] border border-dashed border-slate-300 bg-white/90 px-6 py-10 text-center shadow-sm dark:border-slate-700 dark:bg-slate-900/80">
          <h3 className="text-xl font-semibold text-slate-900 dark:text-white">
            Recherche starten
          </h3>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">
            Stellen Sie eine Frage oder w&auml;hlen Sie einen Vorschlag. Im Modus
            &bdquo;Text generieren&ldquo; wird die Antwort ausschlie&szlig;lich aus den
            in der Datenbank gespeicherten Chunks generiert. Ohne ein entsprechendes
            Dokument wird auch kein Text generiert.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => applySuggestion(s)}
                className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-700 transition hover:border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {s}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Hilfetext: So funktioniert die Recherche (RAG · LLM · Vorgehen) */}
      <section className="overflow-hidden rounded-[24px] border border-slate-200/80 bg-white/85 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <button
          onClick={() => setShowHelp((v) => !v)}
          className="flex w-full items-center justify-between gap-3 px-6 py-4 text-left"
        >
          <span className="text-sm font-semibold text-slate-900 dark:text-white">
            So funktioniert die Recherche
          </span>
          <ChevronDown
            size={18}
            className={`text-slate-400 transition-transform ${showHelp ? 'rotate-180' : ''}`}
          />
        </button>
        {showHelp && (
          <div className="space-y-5 border-t border-slate-100 px-6 py-5 dark:border-slate-800">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-cyan-700 dark:text-cyan-300">
                <Database size={16} /> 1 · Wissensbasis (RAG)
              </div>
              <p className="text-xs leading-6 text-slate-600 dark:text-slate-400">
                Ihre Frage wird zunächst in eine Vektorrepräsentation übersetzt
                (Embedding-Modell <strong>bge-m3</strong>) und anschließend semantisch
                gegen die eingelesenen Verordnungen und Dokumente abgeglichen. Diese
                sind zuvor in inhaltlich zusammenhängende Abschnitte zerlegt, einzeln
                vektorisiert und in einer PostgreSQL-Datenbank mit der Erweiterung
                <strong> pgvector</strong> hinterlegt worden. Die Auswahl der
                Fundstellen erfolgt über die Kosinus-Ähnlichkeit zwischen dem
                Frage-Vektor und den Abschnitts-Vektoren; nur die thematisch
                nächstliegenden Treffer werden an die nächste Stufe übergeben, nicht
                der gesamte Datenbestand. Dieses Verfahren ist unter dem Begriff
                <em> Retrieval-Augmented Generation (RAG)</em> etabliert.
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                <Cpu size={16} /> 2 · Lokales Sprachmodell
              </div>
              <p className="text-xs leading-6 text-slate-600 dark:text-slate-400">
                Im Modus &bdquo;Text generieren&ldquo; formuliert das Sprachmodell
                <strong> Qwen3 14B</strong> (Reasoning für schnelle Antworten
                abgeschaltet) auf Grundlage der zuvor abgerufenen Belegstellen einen
                Antwortentwurf. Die Ausführung erfolgt vollständig auf eigener
                Hardware über den lokalen ai-router, der die Last auf einen Verbund
                lokaler GPUs (u.&nbsp;a. NVIDIA RTX 5070 Ti, GMKtec EVO-X2) verteilt. Das Modell ist durch den Systemprompt
                darauf verpflichtet, ausschließlich aus den übergebenen Fundstellen zu
                antworten; lässt sich eine Aussage nicht durch eine Belegstelle decken,
                weist es ausdrücklich darauf hin, anstatt frei zu formulieren.
                Halluzinationen werden auf diese Weise architektonisch eingedämmt und
                nicht erst nachträglich herausgefiltert.
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-violet-700 dark:text-violet-300">
                <ListOrdered size={16} /> 3 · Vorgehen und Quellen
              </div>
              <p className="text-xs leading-6 text-slate-600 dark:text-slate-400">
                Sie haben die Wahl zwischen &bdquo;Fundstellen suchen&ldquo;, einer
                reinen Trefferliste mit Relevanzwert, und &bdquo;Text generieren&ldquo;,
                bei dem ein formulierter Entwurf erzeugt wird. In beiden Fällen werden
                die zugrunde liegenden Fundstellen mit ausgewiesen, sodass jede Aussage
                nachvollziehbar bleibt. Die rechtliche und sachliche Würdigung verbleibt
                bei der Prüferin oder dem Prüfer; das System leistet Vorarbeit, ersetzt
                jedoch keine Bewertung.
              </p>
            </div>
            <div className="flex items-start gap-2 rounded-2xl bg-emerald-50/70 px-4 py-3 text-xs leading-6 text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">
              <ShieldCheck size={15} className="mt-0.5 shrink-0" />
              <span>
                <strong>Datenschutz und Rechtsgrundlagen.</strong> Diese Anwendung ist
                eine private Anwendung des Verfassers. Embedding-Erzeugung, Vektorsuche
                und Textgenerierung laufen ausschließlich auf eigener Hardware; eine
                Übermittlung von Anfragen oder Inhalten an Cloud-Dienste oder externe
                Anbieter findet nicht statt. Damit ist den Grundsätzen der
                Datenminimierung gemäß Artikel 5 Absatz 1 Buchstabe c
                Datenschutz-Grundverordnung sowie den Anforderungen an die Sicherheit
                der Verarbeitung gemäß Artikel 32 Datenschutz-Grundverordnung Rechnung
                getragen; eine Übermittlung in Drittländer im Sinne der Artikel 44 ff.
                Datenschutz-Grundverordnung findet strukturbedingt nicht statt.
              </span>
            </div>
          </div>
        )}
      </section>

      {/* Fehler */}
      {error && (
        <section className="rounded-[24px] border border-rose-200 bg-rose-50 px-6 py-4 text-sm text-rose-700 shadow-sm dark:border-rose-800 dark:bg-rose-900/30 dark:text-rose-300">
          {error}
        </section>
      )}

      {/* Generierter Text */}
      {mode === 'generate' && (generatedText || isLoading) && (
        <section className="space-y-5">
          <div className={`rounded-[24px] border px-6 py-6 shadow-sm ${
            isAbstention
              ? 'border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20'
              : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800'
          }`}>
            {isAbstention ? (
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-amber-600 dark:text-amber-400" />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-700 dark:text-amber-400">
                    Keine Belege in der Wissensbasis
                  </p>
                  <p className="mt-2 text-sm leading-6 text-amber-800 dark:text-amber-300">{generatedText}</p>
                  <p className="mt-3 text-xs text-amber-700/80 dark:text-amber-400/80">
                    Tipp: Frage neu formulieren, Quelle wechseln oder eigene Dokumente
                    in der Wissensbasis hochladen.
                  </p>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-3 border-b border-slate-100 pb-4 dark:border-slate-700 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-400">
                      Generierter Text
                    </p>
                    <h3 className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{query}</h3>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <span className="rounded-full bg-slate-100 px-3 py-1 dark:bg-slate-700">
                      {TEXT_TYPE_OPTIONS.find((o) => o.value === textType)?.label}
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 dark:bg-slate-700">
                      {LENGTH_OPTIONS.find((o) => o.value === length)?.label}
                    </span>
                    {genModel && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 dark:bg-slate-700">
                        <Cpu size={11} /> {genModel}
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-6 whitespace-pre-wrap text-[15px] leading-7 text-slate-700 dark:text-slate-300">
                  {generatedText}
                  {isLoading && <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-emerald-500 align-middle" />}
                </div>
              </>
            )}
          </div>

          {/* Verwendete Quellen */}
          {!isAbstention && genSources.length > 0 && (
            <div className="rounded-[24px] border border-slate-200 bg-white px-6 py-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                Verwendete Fundstellen
              </p>
              <div className="mt-4 space-y-3">
                {genSources.map((s, i) => (
                  <article key={`${s.source}-${s.chunk_index}-${i}`} className="rounded-[18px] border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-slate-700/40">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h4 className="text-sm font-semibold text-slate-900 dark:text-white">{s.source}</h4>
                      <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                        <span className="rounded-full bg-white px-2.5 py-0.5 dark:bg-slate-800">Abschnitt {s.chunk_index + 1}</span>
                        <span className="rounded-full bg-white px-2.5 py-0.5 dark:bg-slate-800">{Math.round(s.score * 100)}%</span>
                      </div>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-400">{s.snippet}</p>
                  </article>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Suchergebnisse */}
      {mode === 'search' && isLoading && (
        <section className="space-y-4">
          {[1, 2, 3].map((n) => (
            <div key={n} className="animate-pulse rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
              <div className="h-5 w-2/3 rounded bg-slate-200 dark:bg-slate-700" />
              <div className="mt-3 space-y-2">
                <div className="h-4 w-full rounded bg-slate-100 dark:bg-slate-700/60" />
                <div className="h-4 w-5/6 rounded bg-slate-100 dark:bg-slate-700/60" />
              </div>
            </div>
          ))}
        </section>
      )}

      {mode === 'search' && hasSearched && !isLoading && filteredResults.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-end justify-between">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
              {filteredResults.length} Treffer
            </h3>
            {hiddenLowRelevance > 0 && (
              <span className="text-xs text-slate-400 dark:text-slate-500">
                {hiddenLowRelevance} unter 10% Relevanz ausgeblendet
              </span>
            )}
          </div>

          {filteredResults.map((r) => (
            <article
              key={`${r.source}-${r.chunk_index}`}
              className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-slate-700 dark:bg-slate-800"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                      {r.source}
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                      Abschnitt {r.chunk_index + 1}
                    </span>
                  </div>
                  <p
                    className="kb-snippet mt-3 text-sm leading-6 text-slate-600 dark:text-slate-400"
                    dangerouslySetInnerHTML={{ __html: highlightQuery(getSnippet(r.text, query), query) }}
                  />
                  {r.filename && (
                    <div className="mt-3 inline-flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
                      <ExternalLink size={12} /> {r.filename}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2 lg:flex-col lg:items-end">
                  <div className="h-2 w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                    <div
                      className={`h-full rounded-full ${r.score >= 0.65 ? 'bg-emerald-500' : r.score >= 0.4 ? 'bg-amber-500' : 'bg-slate-400'}`}
                      style={{ width: `${Math.round(r.score * 100)}%` }}
                    />
                  </div>
                  <span className={`text-xs font-semibold tabular-nums ${r.score >= 0.65 ? 'text-emerald-700 dark:text-emerald-400' : r.score >= 0.4 ? 'text-amber-700 dark:text-amber-400' : 'text-slate-500'}`}>
                    {Math.round(r.score * 100)}%
                  </span>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}

      {/* Leerzustand */}
      {showEmpty && (
        <section className="rounded-[24px] border border-dashed border-slate-300 bg-white px-6 py-12 text-center shadow-sm dark:border-slate-700 dark:bg-slate-800">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Keine passenden Ergebnisse</h3>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500 dark:text-slate-400">
            Für diese Anfrage wurden keine belastbaren Treffer gefunden. Versuchen Sie
            eine andere Formulierung oder wählen Sie eine andere Quelle.
          </p>
        </section>
      )}

      <style>{`
        .kb-snippet mark { background: #fef08a; color: inherit; padding: 0 2px; border-radius: 2px; }
        :root.dark .kb-snippet mark, .dark .kb-snippet mark { background: rgba(202,138,4,0.35); }
      `}</style>
    </div>
  );
}
