/**
 * StateAidAuditReportPage — Cross-Register-Auswertung.
 *
 * Pruefer geben Firma + Land + Auftraggeber + Pruefer-Namen ein, sehen eine
 * Live-Vorschau aus drei Datenbanken (State-Aid, Beguenstigtenverzeichnisse,
 * Sanktionslisten) und koennen das Ganze als PDF herunterladen.
 *
 * Wichtige Designvorgaben:
 *  - Keine Risiko-Scores, keine Ampeln, keine Severity-Bewertung.
 *  - Aggregation aus drei oeffentlichen Registern in einem Schritt.
 *  - Auftraggeber und Pruefer-Name sind User-Input und werden via React
 *    automatisch escaped (kein dangerouslySetInnerHTML).
 */
import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowDownToLine,
  Brain,
  ClipboardCheck,
  FileSearch,
  Loader2,
  Plus,
  RefreshCcw,
  Search,
  Sparkles,
  Users,
  X,
} from 'lucide-react';
import {
  downloadAuditReportPdf,
  getAuditReport,
  type AuditPersonInput,
  type AuditReportData,
  type AuditReportParams,
  type AuditReportPdfParams,
} from '../lib/stateAidApi';
import StateAidErrorBoundary from '../components/state_aid/StateAidErrorBoundary';
import AuditReportPreview from '../components/state_aid/AuditReportPreview';
import { Skeleton } from '../components/ui/Skeleton';
import Stat from '../components/ui/Stat';

type CountryFilter = '' | 'DE' | 'AT';

const COUNTRY_OPTIONS: Array<{ value: CountryFilter; label: string }> = [
  { value: '', label: 'Beide (DE + AT)' },
  { value: 'DE', label: 'Deutschland' },
  { value: 'AT', label: 'Österreich' },
];

const EXAMPLE_QUERIES = [
  'Trumpf GmbH',
  'Fraunhofer-Gesellschaft',
  'Volkswagen AG',
  'Bosch Rexroth',
];

const MAX_AUFTRAGGEBER = 120;
const MAX_PRUEFER = 120;

// Personen-Editor: bewusst restriktiv. 200 Zeichen reicht selbst fuer
// Doppelnamen mit Titel; mehr als 20 Personen ist im Pruefbetrieb un-
// realistisch und schuetzt vor Performance-Issues bei der Sanktionsliste.
const MAX_PERSON_NAME = 200;
const MAX_PERSONS = 20;

// Vordefinierte Rollen-Optionen. "Sonstige" ist die Default-Auswahl, weil
// der Pruefer nicht immer entscheiden kann oder will, wie eine Person
// gegenueber dem Begueenstigten steht.
const PERSON_ROLE_OPTIONS = [
  'Geschäftsführer',
  'Gesellschafter',
  'UBO/wirtschaftlich Berechtigter',
  'Aufsichtsrat',
  'Vorstand',
  'Prokurist',
  'Sonstige',
] as const;
const DEFAULT_PERSON_ROLE = 'Sonstige';

/**
 * Generiert einen sicheren Datei-Namen fuer den PDF-Download. Sonderzeichen
 * werden auf Underscores gemappt, damit Browser/Filesysteme nicht stolpern.
 */
function safeFilenamePart(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60);
}

function buildPdfFilename(query: string): string {
  const queryPart = safeFilenamePart(query) || 'auswertung';
  return `auswertung_${queryPart}.pdf`;
}

export default function StateAidAuditReportPage() {
  return (
    <StateAidErrorBoundary scope="audit-report-page">
      <StateAidAuditReportPageInner />
    </StateAidErrorBoundary>
  );
}

/**
 * Liest die `persons`-Parameter aus der URL und baut daraus die initiale
 * Liste fuer das Formular. Erwartet das Format `Name|Rolle`. Eintraege
 * ohne Namen werden verworfen, damit ein leerer URL-Parameter (z.B.
 * `persons=`) keine Geister-Zeile produziert.
 */
function parsePersonsFromSearchParams(sp: URLSearchParams): AuditPersonInput[] {
  const result: AuditPersonInput[] = [];
  for (const raw of sp.getAll('persons')) {
    const sep = raw.indexOf('|');
    const name = (sep >= 0 ? raw.slice(0, sep) : raw).trim();
    const role = sep >= 0 ? raw.slice(sep + 1).trim() : '';
    if (!name) continue;
    result.push({ name, role: role || DEFAULT_PERSON_ROLE });
    if (result.length >= MAX_PERSONS) break;
  }
  return result;
}

function StateAidAuditReportPageInner() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get('q') || '';
  const initialCountry = (searchParams.get('country_code') || '') as CountryFilter;
  const initialAuftraggeber = searchParams.get('auftraggeber') || '';
  const initialPersons = parsePersonsFromSearchParams(searchParams);
  const initialIncludeLlm = searchParams.get('include_llm_verification') === 'true';

  const [query, setQuery] = useState<string>(initialQ);
  const [countryCode, setCountryCode] = useState<CountryFilter>(initialCountry);
  const [auftraggeber, setAuftraggeber] = useState<string>(initialAuftraggeber);
  const [prueferName, setPrueferName] = useState<string>('');
  const [persons, setPersons] = useState<AuditPersonInput[]>(initialPersons);
  // LLM-Verifikation der Querbezuege (~3 Min Wartezeit). Default off, weil
  // der Re-Ranker pro Bericht spuerbar Zeit kostet — der Pruefer schaltet
  // ihn explizit zu.
  const [includeLlmVerification, setIncludeLlmVerification] = useState<boolean>(initialIncludeLlm);
  // Karten-Seite im PDF einbinden (OSM-Tiles + NUTS-Outline + Marker).
  // Default off — die OSM-Tiles werden beim Erstellen einmalig extern
  // geladen; das ist in der UI ein bewusster Klick, kein Default.
  const [includeMap, setIncludeMap] = useState<boolean>(false);
  // Toggle „auch LLM-abgelehnte Querbezuege zeigen" (Default off). Wird an
  // AuditReportPreview/AuditCrossReferences durchgereicht.
  const [showLlmRejected, setShowLlmRejected] = useState<boolean>(false);

  const [report, setReport] = useState<AuditReportData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [pdfBusy, setPdfBusy] = useState<boolean>(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  // Stat-Tiles werden nach jeder Suche aus dem Report-State neu berechnet —
  // damit haben wir keine doppelte Quelle der Wahrheit.
  const stats = useMemo(() => {
    if (!report) {
      return { stateAid: 0, beneficiaries: 0, sanctions: 0 };
    }
    return {
      stateAid: report.state_aid.total_count,
      beneficiaries: report.beneficiaries.total_count,
      sanctions: report.sanctions.total_hits,
    };
  }, [report]);

  /**
   * Filtert die Personen-Liste fuer den Request: leere Namen werden ent-
   * fernt, Rolle auf den Standard-Wert gesetzt, falls nicht ausgefuellt.
   * Trim auf beide Felder. Wir geben einen frischen Array zurueck, damit
   * der State nicht durch Submit-Logik mutiert wird.
   */
  function sanitizePersons(input: AuditPersonInput[]): AuditPersonInput[] {
    return input
      .map((p) => ({
        name: (p.name || '').trim(),
        role: (p.role || '').trim() || DEFAULT_PERSON_ROLE,
      }))
      .filter((p) => p.name.length > 0);
  }

  // Wenn die Seite mit `?q=…` aufgerufen wird (Deep-Link aus dem Beihilfe-
  // Dossier), die Suche automatisch ausfuehren.
  useEffect(() => {
    if (initialQ.trim().length >= 2) {
      void runReport(initialQ, initialCountry, initialAuftraggeber, initialPersons, initialIncludeLlm);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runReport(
    qValue: string,
    country: CountryFilter,
    auftrag: string,
    personList: AuditPersonInput[],
    llmVerify: boolean,
  ): Promise<void> {
    const trimmedQ = qValue.trim();
    if (trimmedQ.length < 2) {
      setError('Bitte mindestens 2 Zeichen für die Firma eingeben.');
      return;
    }
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const params: AuditReportParams = { q: trimmedQ };
      if (country) params.country_code = country;
      if (auftrag.trim()) params.auftraggeber = auftrag.trim();
      const cleanedPersons = sanitizePersons(personList);
      if (cleanedPersons.length > 0) params.persons = cleanedPersons;
      if (llmVerify) params.include_llm_verification = true;
      const data = await getAuditReport(params);
      setReport(data);
      // Query-Parameter aktualisieren, damit die Seite shareable ist.
      const next = new URLSearchParams();
      next.set('q', trimmedQ);
      if (country) next.set('country_code', country);
      if (auftrag.trim()) next.set('auftraggeber', auftrag.trim());
      for (const p of cleanedPersons) {
        next.append('persons', `${p.name}|${p.role || ''}`);
      }
      if (llmVerify) next.set('include_llm_verification', 'true');
      setSearchParams(next, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bericht konnte nicht erstellt werden.');
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent): void {
    e.preventDefault();
    void runReport(query, countryCode, auftraggeber, persons, includeLlmVerification);
  }

  function handleReset(): void {
    setQuery('');
    setCountryCode('');
    setAuftraggeber('');
    setPrueferName('');
    setPersons([]);
    setIncludeLlmVerification(false);
    setIncludeMap(false);
    setShowLlmRejected(false);
    setReport(null);
    setError(null);
    setPdfError(null);
    setSearchParams(new URLSearchParams(), { replace: true });
  }

  // ── Personen-Editor-Helpers ────────────────────────────────────────────────
  function handleAddPerson(): void {
    if (persons.length >= MAX_PERSONS) return;
    setPersons([...persons, { name: '', role: DEFAULT_PERSON_ROLE }]);
  }

  function handleRemovePerson(index: number): void {
    setPersons(persons.filter((_, i) => i !== index));
  }

  function handlePersonNameChange(index: number, value: string): void {
    const next = persons.slice();
    next[index] = { ...next[index], name: value.slice(0, MAX_PERSON_NAME) };
    setPersons(next);
  }

  function handlePersonRoleChange(index: number, value: string): void {
    const next = persons.slice();
    next[index] = { ...next[index], role: value };
    setPersons(next);
  }

  async function handlePdfDownload(): Promise<void> {
    if (!report) return;
    setPdfBusy(true);
    setPdfError(null);
    try {
      const params: AuditReportPdfParams = { q: report.query };
      if (countryCode) params.country_code = countryCode;
      if (auftraggeber.trim()) params.auftraggeber = auftraggeber.trim();
      if (prueferName.trim()) params.pruefer_name = prueferName.trim();
      const cleanedPersons = sanitizePersons(persons);
      if (cleanedPersons.length > 0) params.persons = cleanedPersons;
      if (includeLlmVerification) params.include_llm_verification = true;
      if (includeMap) params.include_map = true;

      const blob = await downloadAuditReportPdf(params);
      const url = URL.createObjectURL(blob);
      try {
        const a = document.createElement('a');
        a.href = url;
        a.download = buildPdfFilename(report.query);
        document.body.appendChild(a);
        a.click();
        a.remove();
      } finally {
        // URL.revokeObjectURL erst im naechsten Tick, damit der Browser den
        // Download wirklich gestartet hat.
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : 'PDF-Download fehlgeschlagen.');
    } finally {
      setPdfBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* ── Hero-Sektion ──────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(15,23,72,0.98),rgba(31,41,128,0.94)_45%,rgba(67,86,198,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-100/80">
                <ClipboardCheck size={13} /> Cross-Register-Auswertung
              </span>
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight lg:text-4xl">
              Cross-Register-Auswertung
            </h1>
            <div className="mt-5 inline-flex max-w-2xl items-start gap-2.5 rounded-[22px] border border-white/15 bg-white/10 px-4 py-3 text-xs leading-5 text-indigo-50/90 backdrop-blur-sm">
              <Sparkles size={14} className="mt-0.5 shrink-0 text-indigo-200" />
              <span>
                Faktische Aggregation aus 3 öffentlichen Registern in einem Schritt — ohne Wertung,
                mit Quellen- und Trefferanhang für die fachliche Nachprüfung.
              </span>
            </div>
          </div>
          <div className="rounded-[28px] border border-white/15 bg-black/15 p-5 backdrop-blur">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/60">Aggregations-Übersicht</div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <Stat label="State-Aid" value={report ? stats.stateAid.toLocaleString('de-DE') : '—'} />
              <Stat label="Begünstigte" value={report ? stats.beneficiaries.toLocaleString('de-DE') : '—'} />
              <Stat label="Sanktionen" value={report ? stats.sanctions.toLocaleString('de-DE') : '—'} />
            </div>
            <div className="mt-4 space-y-1 text-[11px] text-white/70">
              <div className="flex items-center justify-between">
                <span>TAM / nationale Register</span>
                <span className="font-mono">{report ? stats.stateAid.toLocaleString('de-DE') : '—'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Art. 49 Verzeichnisse</span>
                <span className="font-mono">{report ? stats.beneficiaries.toLocaleString('de-DE') : '—'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>EU FSF (neutral)</span>
                <span className="font-mono">{report ? stats.sanctions.toLocaleString('de-DE') : '—'}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Eingabe-Card ─────────────────────────────────────────────── */}
      <form
        onSubmit={handleSubmit}
        className="rounded-[30px] border border-white/70 bg-white/90 p-6 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80"
      >
        <div className="grid gap-4 lg:grid-cols-[1.6fr_0.8fr]">
          <div className="space-y-3">
            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                Firma
              </span>
              <div className="relative mt-1.5">
                <Search size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="z.B. Fraunhofer-Gesellschaft, Trumpf GmbH …"
                  required
                  className="w-full rounded-[20px] border border-slate-200 bg-white py-3 pl-11 pr-4 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100 dark:focus:border-indigo-500 dark:focus:ring-indigo-500/30"
                />
              </div>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                  Auftraggeber <span className="font-normal lowercase tracking-normal text-slate-400">(optional)</span>
                </span>
                <input
                  type="text"
                  value={auftraggeber}
                  onChange={(e) => setAuftraggeber(e.target.value.slice(0, MAX_AUFTRAGGEBER))}
                  maxLength={MAX_AUFTRAGGEBER}
                  placeholder="Hessisches Ministerium der Finanzen, Prüfbehörde EFRE"
                  className="mt-1.5 w-full rounded-[20px] border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100 dark:focus:border-indigo-500 dark:focus:ring-indigo-500/30"
                />
              </label>
              <label className="block">
                <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                  Bearbeiter <span className="font-normal lowercase tracking-normal text-slate-400">(optional, erscheint im PDF)</span>
                </span>
                <input
                  type="text"
                  value={prueferName}
                  onChange={(e) => setPrueferName(e.target.value.slice(0, MAX_PRUEFER))}
                  maxLength={MAX_PRUEFER}
                  placeholder="z.B. Jan Riener"
                  className="mt-1.5 w-full rounded-[20px] border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100 dark:focus:border-indigo-500 dark:focus:ring-indigo-500/30"
                />
              </label>
            </div>
          </div>

          <div className="space-y-3">
            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                Land
              </span>
              <div className="mt-1.5 inline-flex w-full flex-wrap gap-1 rounded-full border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-700 dark:bg-slate-900/60">
                {COUNTRY_OPTIONS.map((opt) => {
                  const active = countryCode === opt.value;
                  return (
                    <button
                      key={opt.value || 'all'}
                      type="button"
                      onClick={() => setCountryCode(opt.value)}
                      className={`flex-1 rounded-full px-3 py-1.5 text-xs font-medium transition ${
                        active
                          ? 'bg-indigo-600 text-white shadow-sm'
                          : 'text-slate-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-800'
                      }`}
                      aria-pressed={active}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </label>

            <div className="flex flex-col gap-2 pt-2">
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-indigo-600 px-5 py-3 text-sm font-medium text-white shadow-md shadow-indigo-600/30 transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? <Loader2 size={14} className="animate-spin" /> : <FileSearch size={14} />}
                Auswertung erstellen
              </button>
              <button
                type="button"
                onClick={handleReset}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <RefreshCcw size={12} /> Eingaben zurücksetzen
              </button>
            </div>
          </div>
        </div>

        {/* ── Personen-Editor ──────────────────────────────────────────── */}
        <div className="mt-5 rounded-[24px] border border-slate-200/70 bg-slate-50/60 p-4 dark:border-slate-800/70 dark:bg-slate-900/40">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Users size={14} className="text-slate-500 dark:text-slate-400" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                Beteiligte Personen
              </span>
              <span className="text-[11px] text-slate-400 dark:text-slate-500">
                (optional, max. {MAX_PERSONS})
              </span>
            </div>
            <button
              type="button"
              onClick={handleAddPerson}
              disabled={persons.length >= MAX_PERSONS}
              className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-indigo-500/30 dark:bg-slate-900 dark:text-indigo-200 dark:hover:bg-indigo-950/40"
            >
              <Plus size={12} /> Person hinzufügen
            </button>
          </div>

          {persons.length === 0 ? (
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
              Geschäftsführer, Gesellschafter oder UBO können bei Bedarf gegen die hinterlegten
              Sanktionslisten abgeglichen werden. Hinweis: Personen-Match ohne Geburtsdatum-
              Abgleich ist nur eine Indikation und ersetzt keine Identitätsprüfung.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {persons.map((p, idx) => {
                const roleValue = p.role && p.role.length > 0 ? p.role : DEFAULT_PERSON_ROLE;
                return (
                  <li
                    key={idx}
                    className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950/60"
                  >
                    <input
                      type="text"
                      value={p.name}
                      onChange={(e) => handlePersonNameChange(idx, e.target.value)}
                      maxLength={MAX_PERSON_NAME}
                      placeholder="Name eingeben (z.B. Max Mustermann)"
                      aria-label={`Name der Person ${idx + 1}`}
                      className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-indigo-500 dark:focus:ring-indigo-500/30"
                    />
                    <select
                      value={roleValue}
                      onChange={(e) => handlePersonRoleChange(idx, e.target.value)}
                      aria-label={`Rolle der Person ${idx + 1}`}
                      className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    >
                      {PERSON_ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => handleRemovePerson(idx)}
                      aria-label={`Person ${idx + 1} entfernen`}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:bg-rose-50 hover:text-rose-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-rose-950/30 dark:hover:text-rose-300"
                    >
                      <X size={14} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {persons.length > 0 && persons.length < MAX_PERSONS && (
            <button
              type="button"
              onClick={handleAddPerson}
              className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-dashed border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-500 transition hover:border-indigo-300 hover:text-indigo-700 dark:border-slate-700 dark:text-slate-400 dark:hover:border-indigo-500/40 dark:hover:text-indigo-200"
            >
              <Plus size={12} /> weitere Person
            </button>
          )}
        </div>

        {/* ── LLM-Verifikation Toggle ───────────────────────────────────── */}
        <div className="mt-5 rounded-[24px] border border-violet-200/70 bg-violet-50/50 p-4 dark:border-violet-500/30 dark:bg-violet-950/20">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={includeLlmVerification}
              onChange={(e) => setIncludeLlmVerification(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-violet-300 text-violet-600 focus:ring-violet-500"
              aria-describedby="llm-verify-hint"
            />
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Brain size={14} className="text-violet-700 dark:text-violet-300" />
                <span className="text-sm font-semibold text-violet-900 dark:text-violet-100">
                  LLM-Verifikation aktivieren
                </span>
                <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/60 dark:text-violet-200">
                  ~3 Min Wartezeit
                </span>
              </div>
              <p id="llm-verify-hint" className="mt-1 text-xs leading-5 text-violet-800/85 dark:text-violet-200/85">
                Ein lokal laufendes Sprachmodell schaut sich die unsicheren Querbezüge noch einmal
                an und urteilt in einem Satz, ob es wirklich um denselben Akteur geht. Die Originaldaten
                bleiben unangetastet — die Bewertung ist eine Zweitmeinung mit kurzer Begründung.
              </p>
            </div>
          </label>
        </div>

        {/* ── Karten-Seite Toggle ───────────────────────────────────────── */}
        <div className="mt-3 rounded-[24px] border border-emerald-200/70 bg-emerald-50/50 p-4 dark:border-emerald-500/30 dark:bg-emerald-950/20">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={includeMap}
              onChange={(e) => setIncludeMap(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-emerald-300 text-emerald-600 focus:ring-emerald-500"
              aria-describedby="map-hint"
            />
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-emerald-900 dark:text-emerald-100">
                  Karten-Seite ins PDF einbinden
                </span>
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-200">
                  OSM + NUTS
                </span>
              </div>
              <p id="map-hint" className="mt-1 text-xs leading-5 text-emerald-800/85 dark:text-emerald-200/85">
                Ergänzt das PDF um eine eigene Seite mit OpenStreetMap als Hintergrund,
                NUTS-1-Bundesländer als Outline und einem roten Marker je Treffer-Region
                (Marker-Zahl = Award-Anzahl). Hinweis: die Hintergrundkacheln werden bei
                Berichterstellung einmalig von tile.openstreetmap.org geladen — der
                Cover-Block des PDFs weist darauf gesondert hin.
              </p>
            </div>
          </label>
        </div>
      </form>

      {/* ── Fehler-State ─────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-3 rounded-[26px] border border-rose-200 bg-rose-50/80 px-5 py-4 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-100">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Bericht konnte nicht erstellt werden.</div>
            <div className="mt-0.5 text-xs">{error}</div>
          </div>
        </div>
      )}

      {/* ── Loading-State (Skeleton) ─────────────────────────────────── */}
      {loading && !report && (
        <div className="space-y-4">
          {includeLlmVerification && (
            <div className="flex items-start gap-3 rounded-[26px] border border-violet-200 bg-violet-50/70 px-5 py-4 text-sm text-violet-900 dark:border-violet-500/30 dark:bg-violet-950/40 dark:text-violet-100">
              <Loader2 size={18} className="mt-0.5 shrink-0 animate-spin" />
              <div>
                <div className="font-semibold">
                  Bericht wird erzeugt … Schritt 3 von 4 (LLM-Verifikation läuft, bitte 3 Min warten)
                </div>
                <p className="mt-0.5 text-xs leading-5 opacity-90">
                  Qwen3-14B prüft die unsicheren Querbezüge auf der GPU. Sie können diese
                  Seite offen lassen — der Bericht erscheint, sobald die Pipeline fertig ist.
                </p>
              </div>
            </div>
          )}
          <Skeleton className="h-32 rounded-[30px]" />
          <Skeleton className="h-64 rounded-[30px]" />
          <Skeleton className="h-48 rounded-[30px]" />
          <Skeleton className="h-40 rounded-[30px]" />
        </div>
      )}

      {/* ── Sticky Section-Nav (nur bei vorhandenem Bericht) ─────────── */}
      {report && !loading && <ReportSectionNav data={report} />}

      {/* ── Live-Vorschau ────────────────────────────────────────────── */}
      {report && !loading && (
        <AuditReportPreview
          data={report}
          showLlmRejected={showLlmRejected}
          onToggleShowLlmRejected={setShowLlmRejected}
        />
      )}

      {/* ── Empty-State (vor erster Suche) ───────────────────────────── */}
      {!report && !loading && !error && (
        <section className="rounded-[30px] border border-dashed border-slate-300 bg-white/80 px-6 py-10 text-center shadow-sm dark:border-slate-700 dark:bg-slate-900/60">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
            <FileSearch size={24} />
          </div>
          <h2 className="mt-4 text-base font-semibold text-slate-900 dark:text-white">
            Geben Sie eine Firma ein, um den Bericht zu erzeugen
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500 dark:text-slate-400">
            Der Bericht aggregiert Treffer aus drei öffentlichen Registern und bleibt dabei
            neutral-faktisch. Eine Bewertung der Faktenlage trifft der Prüfer.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {EXAMPLE_QUERIES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  void runReport(example, countryCode, auftraggeber, persons, includeLlmVerification);
                }}
                className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50/70 px-3 py-1.5 text-xs font-medium text-indigo-700 transition hover:bg-indigo-100 dark:border-indigo-500/30 dark:bg-indigo-950/40 dark:text-indigo-200 dark:hover:bg-indigo-950/70"
              >
                <Sparkles size={12} /> {example}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* ── Sticky Action-Footer ─────────────────────────────────────── */}
      {report && (
        <div className="sticky bottom-4 z-20">
          <div className="mx-auto rounded-[26px] border border-white/70 bg-white/95 p-4 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.5)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="max-w-xl text-xs leading-5 text-slate-500 dark:text-slate-400">
                Der Bericht ist faktisch und enthält keine Bewertung. Die abschließende
                Beurteilung obliegt dem Prüfer.
              </p>
              <div className="flex flex-col items-end gap-1">
                <button
                  type="button"
                  onClick={() => { void handlePdfDownload(); }}
                  disabled={pdfBusy}
                  className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {pdfBusy ? <Loader2 size={16} className="animate-spin" /> : <ArrowDownToLine size={16} />}
                  Als PDF herunterladen
                </button>
                {pdfError && (
                  <span className="max-w-xs text-right text-[11px] text-rose-600 dark:text-rose-300">
                    {pdfError}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Hilfs-Komponente: ReportSectionNav ──────────────────────────────────────
//
// Pill-Style Anker-Navigation analog zur Tab-Bar in `/beihilfen`. Sie ist
// `sticky top-2`, damit sie im Scroll mitwandert. Die Sections in
// `AuditReportPreview` haben passende `id`-Attribute und `scrollMarginTop:80`,
// damit der Header beim Sprung nicht ueberlappt.

interface SectionNavItem {
  href: string;
  label: string;
  /** Wenn null: Section anzeigen, aber ohne Count. */
  count: number | null;
}

function ReportSectionNav({ data }: { data: AuditReportData }) {
  const items: SectionNavItem[] = [
    { href: '#sec-state-aid', label: 'State-Aid', count: data.state_aid.total_count },
    { href: '#sec-beneficiaries', label: 'Begünstigte', count: data.beneficiaries.total_count },
    { href: '#sec-sanctions', label: 'Sanktionen', count: data.sanctions.total_hits },
  ];
  // Personen-Check + Coverage nur einblenden, wenn Backend liefert.
  if (data.persons_check && data.persons_check.total_persons > 0) {
    items.push({
      href: '#sec-persons-check',
      label: 'Personen',
      count: data.persons_check.total_hits,
    });
  }
  items.push(
    { href: '#sec-cross-refs', label: 'Querbezüge', count: data.cross_references.length },
  );
  if (data.llm_verification && data.llm_verification.verdicts.length > 0) {
    items.push({
      href: '#sec-llm-verification',
      label: 'LLM-Verifikation',
      count: data.llm_verification.total_input,
    });
  }
  if (data.coverage && data.coverage.entries.length > 0) {
    items.push({
      href: '#sec-coverage',
      label: 'Coverage',
      count: data.coverage.entries.length,
    });
  }
  items.push(
    { href: '#sec-sources', label: 'Quellen', count: data.sources_explanation?.length ?? 0 },
  );
  return (
    <nav
      aria-label="Berichtsnavigation"
      className="sticky top-2 z-30 -mx-2 overflow-x-auto rounded-full border border-white/70 bg-white/90 px-2 py-1.5 shadow-[0_18px_60px_-32px_rgba(15,23,42,0.45)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/85"
    >
      <ul className="flex flex-nowrap items-center gap-1">
        {items.map((item) => (
          <li key={item.href} className="shrink-0">
            <a
              href={item.href}
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-indigo-50 hover:text-indigo-700 dark:text-slate-300 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-200"
            >
              {item.label}
              {item.count !== null && (
                <span className="rounded-full bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {item.count.toLocaleString('de-DE')}
                </span>
              )}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
