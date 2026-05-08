/**
 * AuditReportPreview — Live-Vorschau der Cross-Register-Auswertung.
 *
 * Sektionen (in Reihenfolge):
 *   1. Bericht-Kopf (Query, Erstelldatum, Auftraggeber/Pruefer)
 *   2. State-Aid-Awards (Aggregate + Detail-Tabelle, kollabierbar)
 *   3. Beguenstigtenverzeichnis-Treffer (Aggregate + Detail-Tabelle, kollabierbar)
 *   4. Sanktions-Check (Tabelle mit Confidence-Badges, neutral)
 *   5. Querbezuege (siehe AuditCrossReferences)
 *   6. Quellen und Datenstand (sources_explanation aus dem Backend)
 *   7. Disclaimer / Hinweise zur Anwendung (mehrzeiliger Text aus Backend)
 *
 * Designvorgaben:
 *  - Keine Severity-Marker, keine Ampeln, keine Risiko-Bewertung.
 *  - Detail-Tabellen kollabierbar via <details>, Browser-Vorschau auf 30
 *    Datensaetze begrenzt — der Rest steht im PDF-Bericht.
 *  - Section-Anker (id="sec-…") + scroll-margin-top fuer die sticky Nav
 *    in der Page (siehe StateAidAuditReportPage.tsx).
 */
import {
  Banknote,
  Brain,
  Building2,
  CalendarRange,
  CheckCircle2,
  ChevronDown,
  Coins,
  Database,
  ExternalLink,
  FileSearch,
  GaugeCircle,
  HelpCircle,
  Info,
  Layers,
  Link2,
  MapPin,
  ShieldCheck,
  UserCheck,
  XCircle,
} from 'lucide-react';
import type {
  AuditCoverageEntry,
  AuditCoverageStatus,
  AuditPersonsCheckEntry,
  AuditReportCoverage,
  AuditReportCrossReference,
  AuditReportData,
  AuditReportLlmVerdict,
  AuditReportLlmVerification,
  AuditReportPersonsCheck,
  AuditReportSanctionHit,
} from '../../lib/stateAidApi';
import { safeExternalUrl } from '../../lib/stateAidApi';
import AuditCrossReferences from './AuditCrossReferences';

interface Props {
  data: AuditReportData;
  /**
   * Wenn `true`, werden Querbezuege mit `filtered_by_llm: true` zusaetzlich
   * (ausgegraut) angezeigt. Default `false` blendet sie aus.
   */
  showLlmRejected?: boolean;
  /** Wenn gesetzt, wird ein Toggle „auch LLM-abgelehnte zeigen" gerendert. */
  onToggleShowLlmRejected?: (next: boolean) => void;
}

// Browser-Vorschau zeigt maximal so viele Detail-Treffer pro Sektion. Der
// Rest steht im PDF-Bericht — die UI weist explizit darauf hin.
const PREVIEW_ROW_LIMIT = 30;

// ── Format-Helfer ────────────────────────────────────────────────────────────

function formatEur(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(value);
}

function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('de-DE');
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString('de-DE', { year: 'numeric', month: '2-digit', day: '2-digit' });
  } catch {
    return iso;
  }
}

function pickString(record: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim() !== '') return value;
    if (typeof value === 'number') return String(value);
  }
  return '';
}

function pickNumber(record: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() !== '') {
      const n = Number(value);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

/**
 * Sortiert eine State-Aid-Award-Liste nach `granting_date` absteigend.
 * Datensaetze ohne Datum landen am Ende. Die Originalliste wird nicht
 * mutiert.
 */
function sortAwardsByDateDesc(
  awards: ReadonlyArray<Record<string, unknown>>,
): Array<Record<string, unknown>> {
  return [...awards].sort((a, b) => {
    const da = pickString(a, 'granting_date', 'publication_date');
    const db = pickString(b, 'granting_date', 'publication_date');
    if (!da && !db) return 0;
    if (!da) return 1;
    if (!db) return -1;
    return db.localeCompare(da);
  });
}

// ── Section-Frame ────────────────────────────────────────────────────────────

interface SectionFrameProps {
  id?: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  subtitle?: string;
  freshness?: string;
  children: React.ReactNode;
}

function SectionFrame({ id, icon: Icon, title, subtitle, freshness, children }: SectionFrameProps) {
  return (
    <section
      id={id}
      style={id ? { scrollMarginTop: 80 } : undefined}
      className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
            <Icon size={20} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h3>
            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
            )}
          </div>
        </div>
        {freshness && (
          <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-[11px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-400">
            <CalendarRange size={11} /> Datenstand: {freshness}
          </div>
        )}
      </header>
      <div className="mt-5">{children}</div>
    </section>
  );
}

// ── Confidence-Badge ─────────────────────────────────────────────────────────
// Token-Map analog zu StateAidResultsTable: exact=emerald, high=cyan,
// medium=amber, low=slate. Wir akzeptieren neben den vier Standardwerten
// beliebige Strings (Backend liefert `confidence: string`) und fallen auf
// "low" zurueck, wenn das Label unbekannt ist.

const CONFIDENCE_CLASS: Record<string, string> = {
  exact: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  high: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300',
  medium: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  low: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
};

const CONFIDENCE_LABEL: Record<string, string> = {
  exact: 'exakt',
  high: 'hoch',
  medium: 'mittel',
  low: 'niedrig',
};

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const key = (confidence || '').toLowerCase();
  const className = CONFIDENCE_CLASS[key] ?? CONFIDENCE_CLASS.low;
  const label = CONFIDENCE_LABEL[key] ?? confidence ?? '—';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${className}`}>
      {label}
    </span>
  );
}

// ── Sektion 1: State-Aid ─────────────────────────────────────────────────────

function StateAidSection({ data }: { data: AuditReportData }) {
  const sa = data.state_aid;
  const freshness = data.data_freshness?.state_aid;
  // Sortiert nach granting_date desc, dann auf 30 begrenzen fuer die Vorschau.
  const sortedAwards = sortAwardsByDateDesc(sa.awards);
  const previewAwards = sortedAwards.slice(0, PREVIEW_ROW_LIMIT);
  const remaining = sa.total_count - previewAwards.length;

  return (
    <SectionFrame
      id="sec-state-aid"
      icon={Coins}
      title="Staatliche Beihilfen (TAM / nationale Register)"
      subtitle={`${formatInt(sa.total_count)} Awards · Volumen ${formatEur(sa.total_amount_eur)}`}
      freshness={freshness}
    >
      {sa.total_count === 0 ? (
        <div className="rounded-[22px] border border-dashed border-slate-300 bg-slate-50/70 px-4 py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
          Keine Beihilfe-Awards für diese Anfrage gefunden.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <TopList
              icon={Building2}
              title="Top-Behörden"
              entries={sa.by_authority.slice(0, 3).map((b) => ({
                label: b.authority,
                primary: formatInt(b.count),
                secondary: formatEur(b.sum_eur),
              }))}
            />
            <TopList
              icon={MapPin}
              title="Top-NUTS"
              entries={sa.by_nuts.slice(0, 3).map((b) => ({
                label: `${b.nuts_code}${b.nuts_label ? ' · ' + b.nuts_label : ''}`,
                primary: formatInt(b.count),
                secondary: formatEur(b.sum_eur),
              }))}
            />
            <TopList
              icon={CalendarRange}
              title="Top-Jahre"
              entries={sa.by_year
                .slice()
                .sort((a, b) => b.count - a.count)
                .slice(0, 3)
                .map((y) => ({
                  label: String(y.year),
                  primary: formatInt(y.count),
                  secondary: formatEur(y.sum_eur),
                }))}
            />
          </div>

          {sa.by_instrument.length > 0 && (
            <div className="rounded-[22px] border border-slate-200/80 bg-slate-50/70 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/40">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                Beihilfeinstrumente
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {sa.by_instrument.slice(0, 8).map((inst) => (
                  <span
                    key={inst.instrument}
                    className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-0.5 text-xs text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-200"
                  >
                    <Banknote size={11} className="text-slate-400" />
                    {inst.instrument}
                    <span className="font-mono text-[10px] text-slate-400">{formatInt(inst.count)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Detail-Tabelle: kollabierbar (default offen). Begrenzt auf 30 */}
          {/* Datensaetze in der Browser-Vorschau, Rest steht im PDF.        */}
          <details
            open
            className="group rounded-[26px] border border-slate-200/80 bg-white/70 dark:border-slate-800 dark:bg-slate-900/50"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-[26px] px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-900/70">
              <span className="flex items-center gap-2">
                <FileSearch size={14} className="text-slate-400" />
                Einzelne Treffer (State-Aid)
                <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {formatInt(previewAwards.length)} / {formatInt(sa.total_count)}
                </span>
              </span>
              <ChevronDown
                size={16}
                className="text-slate-400 transition group-open:rotate-180"
              />
            </summary>
            <div className="overflow-hidden rounded-b-[26px] border-t border-slate-200/80 dark:border-slate-800">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                  <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-900/60 dark:text-slate-400">
                    <tr>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Datum</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Begünstigter</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Region</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Behörde</th>
                      <th scope="col" className="px-4 py-2 text-right font-semibold">Betrag (EUR)</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">SA-Ref</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white text-slate-700 dark:divide-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
                    {previewAwards.map((awardRaw, idx) => {
                      const award = awardRaw as Record<string, unknown>;
                      const beneficiary = pickString(award, 'beneficiary_name', 'name');
                      const date = pickString(award, 'granting_date', 'publication_date');
                      const amount = pickNumber(award, 'aid_amount_eur', 'aid_amount');
                      const nutsCode = pickString(award, 'nuts_code');
                      const nutsLabel = pickString(award, 'nuts_label');
                      const authority = pickString(award, 'granting_authority', 'entrusted_entity');
                      const saRef = pickString(award, 'sa_reference', 'measure_reference');
                      const caseUrlRaw = pickString(award, 'case_url', 'decision_url', 'source_url');
                      const safeCaseUrl = safeExternalUrl(caseUrlRaw);
                      const id = pickString(award, 'id', 'source_record_id');
                      // Region kompakt: Code + Label, falls vorhanden.
                      const regionDisplay = nutsCode
                        ? nutsLabel
                          ? `${nutsCode} · ${nutsLabel}`
                          : nutsCode
                        : '—';
                      return (
                        <tr
                          key={id || `${beneficiary}-${idx}`}
                          className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60 dark:odd:bg-slate-950/40 dark:even:bg-slate-900/40 dark:hover:bg-slate-900/70"
                        >
                          <td className="px-4 py-2 font-mono text-xs text-slate-500 dark:text-slate-400">
                            {formatDate(date)}
                          </td>
                          <td className="max-w-[220px] truncate px-4 py-2 font-medium" title={beneficiary || undefined}>
                            {beneficiary || '—'}
                          </td>
                          <td
                            className="px-4 py-2 text-xs text-slate-500 dark:text-slate-400"
                            title={nutsLabel || undefined}
                          >
                            {regionDisplay}
                          </td>
                          <td
                            className="max-w-[200px] truncate px-4 py-2 text-xs text-slate-600 dark:text-slate-300"
                            title={authority || undefined}
                          >
                            {authority || '—'}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs">
                            {amount !== null ? formatAmount(amount) : '—'}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs">
                            {saRef ? (
                              safeCaseUrl ? (
                                <a
                                  href={safeCaseUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-indigo-700 hover:text-indigo-900 dark:text-indigo-300 dark:hover:text-indigo-100"
                                >
                                  {saRef}
                                  <ExternalLink size={11} />
                                </a>
                              ) : (
                                <span className="text-slate-700 dark:text-slate-200">{saRef}</span>
                              )
                            ) : (
                              '—'
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {remaining > 0 && (
                <div className="border-t border-slate-200/80 bg-slate-50/70 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400">
                  … und {formatInt(remaining)} weitere im PDF
                </div>
              )}
            </div>
          </details>
        </div>
      )}
    </SectionFrame>
  );
}

// ── Sektion 2: Beguenstigtenverzeichnis ──────────────────────────────────────

function BeneficiariesSection({ data }: { data: AuditReportData }) {
  const ben = data.beneficiaries;
  const freshness = data.data_freshness?.beneficiaries;
  const previewMatches = ben.matches.slice(0, PREVIEW_ROW_LIMIT);
  const remaining = ben.total_count - previewMatches.length;

  return (
    <SectionFrame
      id="sec-beneficiaries"
      icon={Building2}
      title="Begünstigtenverzeichnisse (Art. 49 VO 2021/1060)"
      subtitle={`${formatInt(ben.total_count)} Treffer · Volumen ${formatEur(ben.total_amount_eur)}`}
      freshness={freshness}
    >
      {ben.total_count === 0 ? (
        <div className="rounded-[22px] border border-dashed border-slate-300 bg-slate-50/70 px-4 py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
          Keine Treffer in den hinterlegten Begünstigtenverzeichnissen.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <TopList
              icon={MapPin}
              title="Verteilung nach Bundesland"
              entries={ben.by_bundesland.slice(0, 5).map((b) => ({
                label: b.bundesland || 'unbekannt',
                primary: formatInt(b.count),
              }))}
            />
            <TopList
              icon={Layers}
              title="Verteilung nach Fonds"
              entries={ben.by_fonds.slice(0, 5).map((b) => ({
                label: b.fonds || 'unbekannt',
                primary: formatInt(b.count),
              }))}
            />
          </div>

          {/* Detail-Tabelle: kollabierbar (default offen). */}
          <details
            open
            className="group rounded-[26px] border border-slate-200/80 bg-white/70 dark:border-slate-800 dark:bg-slate-900/50"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-[26px] px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-900/70">
              <span className="flex items-center gap-2">
                <FileSearch size={14} className="text-slate-400" />
                Einzelne Treffer (Begünstigte)
                <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {formatInt(previewMatches.length)} / {formatInt(ben.total_count)}
                </span>
              </span>
              <ChevronDown
                size={16}
                className="text-slate-400 transition group-open:rotate-180"
              />
            </summary>
            <div className="overflow-hidden rounded-b-[26px] border-t border-slate-200/80 dark:border-slate-800">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                  <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-900/60 dark:text-slate-400">
                    <tr>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Bundesland</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Fonds</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Vorhaben</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Aktenzeichen</th>
                      <th scope="col" className="px-4 py-2 text-right font-semibold">Volumen (EUR)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white text-slate-700 dark:divide-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
                    {previewMatches.map((matchRaw, idx) => {
                      const match = matchRaw as Record<string, unknown>;
                      const project = pickString(match, 'project_name', 'projekt', 'company_name');
                      const company = pickString(match, 'company_name', 'name');
                      const bundesland = pickString(match, 'bundesland');
                      const fonds = pickString(match, 'fonds');
                      const aktenzeichen = pickString(match, 'aktenzeichen', 'foerderkennzeichen');
                      const kosten = pickNumber(match, 'kosten', 'gesamtkosten', 'foerdersumme');
                      return (
                        <tr
                          key={`${project}-${aktenzeichen}-${idx}`}
                          className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60 dark:odd:bg-slate-950/40 dark:even:bg-slate-900/40 dark:hover:bg-slate-900/70"
                        >
                          <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">{bundesland || '—'}</td>
                          <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">{fonds || '—'}</td>
                          <td className="max-w-[260px] px-4 py-2" title={project || undefined}>
                            <div className="truncate font-medium">{project || '—'}</div>
                            {company && company !== project && (
                              <div className="truncate text-[11px] text-slate-500 dark:text-slate-400">{company}</div>
                            )}
                          </td>
                          <td className="px-4 py-2 font-mono text-xs">{aktenzeichen || '—'}</td>
                          <td className="px-4 py-2 text-right font-mono text-xs">
                            {kosten !== null ? formatAmount(kosten) : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {remaining > 0 && (
                <div className="border-t border-slate-200/80 bg-slate-50/70 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400">
                  … und {formatInt(remaining)} weitere im PDF
                </div>
              )}
            </div>
          </details>
        </div>
      )}
    </SectionFrame>
  );
}

// ── Sektion 3: Sanktionen ────────────────────────────────────────────────────

function SanctionsSection({ data }: { data: AuditReportData }) {
  const sanctions = data.sanctions;
  const freshness = data.data_freshness?.sanctions;
  const hasHits = sanctions.total_hits > 0;

  return (
    <SectionFrame
      id="sec-sanctions"
      icon={ShieldCheck}
      title="EU FSF Sanktionsabgleich"
      subtitle={
        hasHits
          ? `${formatInt(sanctions.total_hits)} Listen-Eintrag(e) zum Begünstigten gefunden`
          : 'Kein Listen-Eintrag zum Begünstigten gefunden'
      }
      freshness={freshness}
    >
      {!hasHits ? (
        <div className="flex items-start gap-3 rounded-[22px] border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-100">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-medium">Keine Treffer in der EU FSF.</div>
            <p className="mt-0.5 text-xs leading-5 text-emerald-800/80 dark:text-emerald-200/80">
              Stand der hinterlegten Liste: {freshness ?? 'siehe Datenstand'}.
              {sanctions.listing_sources.length > 0 && (
                <span className="ml-1">Quellen: {sanctions.listing_sources.join(', ')}.</span>
              )}
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="overflow-hidden rounded-[22px] border border-slate-200/80 dark:border-slate-800">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-900/60 dark:text-slate-400">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Listen-Name</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Score</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Konfidenz</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Aliase</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Land</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Programm</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white text-slate-700 dark:divide-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
                  {sanctions.hits.map((hit: AuditReportSanctionHit, idx) => (
                    <tr
                      key={`${hit.name}-${idx}`}
                      className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60 dark:odd:bg-slate-950/40 dark:even:bg-slate-900/40 dark:hover:bg-slate-900/70"
                    >
                      <td className="px-4 py-2 font-medium">{hit.name}</td>
                      <td className="px-4 py-2 text-right font-mono text-xs">{hit.score.toFixed(0)}</td>
                      <td className="px-4 py-2">
                        <ConfidenceBadge confidence={hit.confidence} />
                      </td>
                      <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">
                        {hit.aliases && hit.aliases.length > 0 ? hit.aliases.slice(0, 3).join(', ') : '—'}
                      </td>
                      <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">{hit.countries || '—'}</td>
                      <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">{hit.sanctions || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Hinweis: Die Abgleichsdaten stammen aus der EU FSF. Geburtsdatum, Land und Identifier
            sollten manuell verifiziert werden.
          </p>
        </div>
      )}
    </SectionFrame>
  );
}

// ── Sektion 4: Querbezuege ───────────────────────────────────────────────────

function CrossReferencesSection({
  data,
  showLlmRejected,
  onToggleShowLlmRejected,
}: {
  data: AuditReportData;
  showLlmRejected: boolean;
  onToggleShowLlmRejected?: (next: boolean) => void;
}) {
  // Wenn der Toggle off ist, blenden wir vom LLM verworfene Querbezuege aus.
  // Wenn on, werden sie ausgegraut weiter angezeigt — die Komponente
  // `AuditCrossReferences` rendert dafuer einen `aria-disabled`-Stil.
  const allItems: AuditReportCrossReference[] = data.cross_references || [];
  const rejectedCount = allItems.filter((c) => c.filtered_by_llm).length;
  const visibleItems = showLlmRejected
    ? allItems
    : allItems.filter((c) => !c.filtered_by_llm);

  // Toggle nur anzeigen, wenn ueberhaupt LLM-abgelehnte Eintraege existieren.
  const showToggle = rejectedCount > 0 && onToggleShowLlmRejected !== undefined;

  return (
    <SectionFrame
      id="sec-cross-refs"
      icon={Link2}
      title="Registerübergreifende Beobachtungen"
      subtitle={
        rejectedCount > 0
          ? `Neutrale Faktenlage — ${rejectedCount} vom LLM verworfen${showLlmRejected ? ' (sichtbar)' : ' (ausgeblendet)'}`
          : 'Neutrale Faktenlage — keine Bewertung'
      }
    >
      {showToggle && (
        <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-rose-200 bg-rose-50/70 px-3 py-1.5 text-xs font-medium text-rose-800 transition hover:bg-rose-50 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-200">
            <input
              type="checkbox"
              checked={showLlmRejected}
              onChange={(e) => onToggleShowLlmRejected?.(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-rose-300 text-rose-600 focus:ring-rose-500"
            />
            <Brain size={12} className="opacity-80" />
            auch LLM-abgelehnte zeigen
            <span className="rounded-full bg-rose-100 px-1.5 py-0.5 font-mono text-[10px] text-rose-700 dark:bg-rose-900/60 dark:text-rose-200">
              {rejectedCount.toLocaleString('de-DE')}
            </span>
          </label>
        </div>
      )}
      <AuditCrossReferences items={visibleItems} />
    </SectionFrame>
  );
}

// ── Sektion: LLM-Verifikation (Stufe 4) ──────────────────────────────────────
//
// Re-Ranker-Verdicts vom Qwen3-14B fuer alle unsicheren Querbezuege. Wird nur
// gerendert, wenn das Backend `llm_verification` liefert (Pruefer hat den
// Toggle aktiviert).
//
// Zusammenfassung + Tabelle: Original-Score, LLM-Match (✓/✗/?), Confidence,
// Begruendung. Wir verwenden bewusst den Hinweis „kein Beweis" — die LLM-
// Begruendungen sind Indikationen.

const VERDICT_PILL_CLASS: Record<AuditReportLlmVerdict['match'], string> = {
  yes: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  no: 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
  unknown: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
};

const VERDICT_LABEL: Record<AuditReportLlmVerdict['match'], string> = {
  yes: 'bestätigt',
  no: 'verworfen',
  unknown: 'unklar',
};

function VerdictIcon({ match }: { match: AuditReportLlmVerdict['match'] }) {
  if (match === 'yes') return <CheckCircle2 size={12} aria-hidden />;
  if (match === 'no') return <XCircle size={12} aria-hidden />;
  return <HelpCircle size={12} aria-hidden />;
}

/**
 * Liefert den Original-Score eines Cross-References (sofern vorhanden) aus
 * dem Evidence-Feld. Backend kann `score`, `original_score` oder
 * `match_score` benutzen.
 */
function pickEvidenceScore(item: AuditReportCrossReference | undefined): number | null {
  if (!item) return null;
  const ev = item.evidence || {};
  for (const key of ['score', 'original_score', 'match_score']) {
    const v = (ev as Record<string, unknown>)[key];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string' && v.trim() !== '') {
      const n = Number(v);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

function LlmVerificationSection({ data }: { data: AuditReportData }) {
  const verification: AuditReportLlmVerification | null | undefined = data.llm_verification;
  if (!verification || verification.verdicts.length === 0) return null;

  const verdicts = verification.verdicts;
  const counts = verdicts.reduce(
    (acc, v) => {
      acc[v.match] = (acc[v.match] || 0) + 1;
      return acc;
    },
    { yes: 0, no: 0, unknown: 0 } as Record<AuditReportLlmVerdict['match'], number>,
  );
  const totalDurationSec = Math.round(verification.elapsed_total_ms / 1000);

  return (
    <SectionFrame
      id="sec-llm-verification"
      icon={Brain}
      title="Zweitmeinung des Sprachmodells"
      subtitle="Lokales KI-Modell prüft die unsicheren Querbezüge noch einmal mit Klartext-Begründung"
    >
      {/* Zusammenfassung */}
      <div className="mb-4 rounded-[22px] border border-violet-200/70 bg-violet-50/60 px-4 py-3 text-sm text-violet-900 dark:border-violet-500/30 dark:bg-violet-950/30 dark:text-violet-100">
        <p>
          Von <strong>{formatInt(verification.total_input)}</strong> unsicheren Querbezügen wurden{' '}
          <strong className="text-emerald-700 dark:text-emerald-300">{formatInt(counts.yes)}</strong>{' '}
          vom LLM bestätigt,{' '}
          <strong className="text-rose-700 dark:text-rose-300">{formatInt(counts.no)}</strong>{' '}
          verworfen und{' '}
          <strong className="text-amber-700 dark:text-amber-300">{formatInt(counts.unknown)}</strong>{' '}
          als unklar markiert.
        </p>
        <p className="mt-1 text-xs leading-5 text-violet-800/80 dark:text-violet-200/80">
          Pipeline-Dauer: {totalDurationSec.toLocaleString('de-DE')} Sek
          {verification.skipped_due_to_timeout > 0 && (
            <> · {formatInt(verification.skipped_due_to_timeout)} wegen Timeout übersprungen</>
          )}
          {verification.error && (
            <> · Fehler: <span className="font-mono">{verification.error}</span></>
          )}
        </p>
      </div>

      <div className="overflow-hidden rounded-[22px] border border-slate-200/80 dark:border-slate-800">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-900/60 dark:text-slate-400">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-semibold">Querbezug</th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">Original-Score</th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">LLM-Match</th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">LLM-Confidence</th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">Begründung</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white text-slate-700 dark:divide-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
              {verdicts.map((v, idx) => {
                const crossRef = data.cross_references[v.cross_ref_index];
                const score = pickEvidenceScore(crossRef);
                const pillClass = VERDICT_PILL_CLASS[v.match] || VERDICT_PILL_CLASS.unknown;
                const pillLabel = VERDICT_LABEL[v.match] || v.match;
                return (
                  <tr
                    key={`verdict-${idx}-${v.cross_ref_index}`}
                    className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60 dark:odd:bg-slate-950/40 dark:even:bg-slate-900/40 dark:hover:bg-slate-900/70"
                  >
                    <td className="max-w-[260px] px-4 py-2">
                      {crossRef ? (
                        <>
                          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                            #{v.cross_ref_index + 1}
                          </div>
                          <div className="mt-0.5 truncate text-xs text-slate-700 dark:text-slate-200" title={crossRef.description}>
                            {crossRef.description}
                          </div>
                        </>
                      ) : (
                        <span className="text-xs text-slate-400">#{v.cross_ref_index + 1}</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs">
                      {score !== null ? score.toLocaleString('de-DE') : '—'}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${pillClass}`}>
                        <VerdictIcon match={v.match} />
                        {pillLabel}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs">
                      {Math.round(v.confidence)}
                    </td>
                    <td className="max-w-[420px] px-4 py-2 text-xs leading-5 text-slate-600 dark:text-slate-300">
                      {v.reason || '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-3 flex items-start gap-2 rounded-[20px] border border-amber-200 bg-amber-50/70 px-4 py-3 text-xs leading-5 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span>
          Die LLM-Verifikation prüft die heuristisch gefundenen Querbezüge gegen die
          Datensatz-Inhalte. Die Begründungen sind Hinweise, kein Beweis — der Prüfer entscheidet
          abschließend.
        </span>
      </div>
    </SectionFrame>
  );
}

// ── Sektion: Personen-Sanktionscheck (Item 1) ────────────────────────────────
//
// Wird nur gerendert, wenn der Pruefer beim Bericht-Aufruf mindestens eine
// Person eingegeben hat. Backend liefert pro Person 0..n Treffer; bei 0
// Treffern erscheint die Person trotzdem in der Tabelle, damit der Pruefer
// sieht, dass abgeglichen wurde.

function PersonsCheckSection({ data }: { data: AuditReportData }) {
  const personsCheck: AuditReportPersonsCheck | null | undefined = data.persons_check;
  if (!personsCheck || personsCheck.total_persons === 0) return null;

  const hasAnyHit = personsCheck.total_hits > 0;
  const freshness = data.data_freshness?.sanctions;

  return (
    <SectionFrame
      id="sec-persons-check"
      icon={UserCheck}
      title="Personen-Sanktionscheck"
      subtitle={
        hasAnyHit
          ? `${formatInt(personsCheck.total_hits)} Listen-Treffer für ${formatInt(personsCheck.total_persons)} eingegebene Person(en)`
          : `Keine Treffer für ${formatInt(personsCheck.total_persons)} eingegebene Person(en)`
      }
      freshness={freshness}
    >
      {/* Hinweis-Banner — Personen-Match ohne Geburtsdatum-Abgleich ist nur Indikation. */}
      <div className="mb-3 flex items-start gap-2 rounded-[20px] border border-amber-200 bg-amber-50/70 px-4 py-2.5 text-xs leading-5 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span>
          Personen-Match ohne Geburtsdatum-Abgleich ist nur eine Indikation und ersetzt
          keine Identitätsprüfung. Bei Treffern muss der Prüfer Geburtsdatum, Land und
          Identifier manuell verifizieren.
        </span>
      </div>

      {!hasAnyHit ? (
        <div className="flex items-start gap-3 rounded-[22px] border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-100">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-medium">
              Keine der eingegebenen Personen erscheint in einer der {personsCheck.listing_sources.length || 5} Sanktionslisten.
            </div>
            <p className="mt-0.5 text-xs leading-5 text-emerald-800/80 dark:text-emerald-200/80">
              {personsCheck.listing_sources.length > 0 && (
                <>Quellen: {personsCheck.listing_sources.join(', ')}. </>
              )}
              Stand: {freshness ?? 'siehe Datenstand'}.
            </p>
          </div>
        </div>
      ) : (
        <div className="overflow-hidden rounded-[22px] border border-slate-200/80 dark:border-slate-800">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-900/60 dark:text-slate-400">
                <tr>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">Eingabe</th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">Rolle</th>
                  <th scope="col" className="px-4 py-2 text-center font-semibold">Treffer</th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">Score / Konfidenz</th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">Listen</th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">Aliase</th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">Land</th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">Geburtsdatum</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white text-slate-700 dark:divide-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
                {personsCheck.entries.map((entry, idx) => (
                  <PersonCheckRows key={`${entry.input_name}-${idx}`} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </SectionFrame>
  );
}

/**
 * Rendert pro Eingabe-Person eine oder mehrere Tabellenzeilen. Bei 0
 * Treffern eine schlichte Zeile mit "✗ kein Treffer", bei n Treffern
 * fuer den ersten Hit Eingabe + Rolle + Treffer-Marker, fuer alle
 * weiteren Hits leere Eingabe/Rolle (Sub-Zeilen).
 */
function PersonCheckRows({ entry }: { entry: AuditPersonsCheckEntry }) {
  if (entry.hits.length === 0) {
    return (
      <tr className="hover:bg-slate-100/60 dark:hover:bg-slate-900/70">
        <td className="max-w-[220px] truncate px-4 py-2 font-medium" title={entry.input_name}>
          {entry.input_name || '—'}
        </td>
        <td className="px-4 py-2 text-xs text-slate-500 dark:text-slate-400">
          {entry.input_role || '—'}
        </td>
        <td className="px-4 py-2 text-center" aria-label="Kein Treffer">
          <span
            className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            title="Kein Treffer"
          >
            ✗
          </span>
        </td>
        <td className="px-4 py-2 text-xs text-slate-400 dark:text-slate-500" colSpan={5}>
          Kein Treffer in den hinterlegten Sanktionslisten.
        </td>
      </tr>
    );
  }
  return (
    <>
      {entry.hits.map((hit, hitIdx) => (
        <tr
          key={`${entry.input_name}-${hitIdx}`}
          className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60 dark:odd:bg-slate-950/40 dark:even:bg-slate-900/40 dark:hover:bg-slate-900/70"
        >
          <td className="max-w-[220px] truncate px-4 py-2 font-medium" title={entry.input_name}>
            {hitIdx === 0 ? (
              <>
                {entry.input_name || '—'}
                {hit.name && hit.name !== entry.input_name && (
                  <span className="ml-1 block text-[11px] font-normal text-slate-500 dark:text-slate-400">
                    Treffer: {hit.name}
                  </span>
                )}
              </>
            ) : (
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                ↳ {hit.name}
              </span>
            )}
          </td>
          <td className="px-4 py-2 text-xs text-slate-500 dark:text-slate-400">
            {hitIdx === 0 ? entry.input_role || '—' : ''}
          </td>
          <td className="px-4 py-2 text-center" aria-label="Treffer">
            <span
              className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-100 text-[11px] font-semibold text-amber-700 dark:bg-amber-950/50 dark:text-amber-200"
              title="Treffer"
            >
              ✓
            </span>
          </td>
          <td className="px-4 py-2">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs">{hit.score.toFixed(0)}</span>
              <ConfidenceBadge confidence={hit.confidence} />
            </div>
          </td>
          <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">
            {hit.lists && hit.lists.length > 0 ? hit.lists.join(', ') : '—'}
          </td>
          <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">
            {hit.aliases && hit.aliases.length > 0 ? hit.aliases.slice(0, 3).join(', ') : '—'}
          </td>
          <td className="px-4 py-2 text-xs text-slate-600 dark:text-slate-300">
            {hit.countries || '—'}
          </td>
          <td className="px-4 py-2 font-mono text-xs">
            {hit.birth_date ? formatDate(hit.birth_date) : '—'}
          </td>
        </tr>
      ))}
    </>
  );
}

// ── Sektion: Coverage (Item 5) ───────────────────────────────────────────────
//
// Wartungs-Indikator, NICHT als Risiko-Marker. Die Pill-Farben kennzeichnen
// nur den lokalen Datenbestand: gruen=vollstaendig, gelb=partiell,
// grau=unbekannt.

const COVERAGE_STATUS_CLASS: Record<AuditCoverageStatus, string> = {
  complete: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  partial: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  unknown: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
};

const COVERAGE_STATUS_LABEL: Record<AuditCoverageStatus, string> = {
  complete: 'vollständig',
  partial: 'partiell',
  unknown: 'unbekannt',
};

function CoverageStatusPill({ status }: { status: AuditCoverageStatus }) {
  const cls = COVERAGE_STATUS_CLASS[status] ?? COVERAGE_STATUS_CLASS.unknown;
  const label = COVERAGE_STATUS_LABEL[status] ?? status;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`}>
      {label}
    </span>
  );
}

/**
 * Rechnet die Coverage-Ratio in einen Prozent-String um. Backend liefert
 * Werte zwischen 0 und 1 (oder null wenn unbekannt).
 */
function formatCoveragePercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return '—';
  return `${Math.round(ratio * 100)}%`;
}

function CoverageSection({ data }: { data: AuditReportData }) {
  const coverage: AuditReportCoverage | null | undefined = data.coverage;
  if (!coverage || coverage.entries.length === 0) return null;

  const partialEntries = coverage.entries.filter((e) => e.status === 'partial');

  return (
    <SectionFrame
      id="sec-coverage"
      icon={GaugeCircle}
      title="Datenbestand und Coverage"
      subtitle="Wartungs-Indikator — kein Risiko-Marker"
    >
      <div className="overflow-hidden rounded-[22px] border border-slate-200/80 dark:border-slate-800">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-900/60 dark:text-slate-400">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-semibold">Modul</th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">Quelle</th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">Lokal</th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">Erwartet</th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">Coverage</th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">Letzter Harvest</th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white text-slate-700 dark:divide-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
              {coverage.entries.map((entry, idx) => (
                <CoverageRow key={`${entry.module}-${entry.source}-${idx}`} entry={entry} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Hinweis bei partiellem Bestand. */}
      {partialEntries.length > 0 && (
        <div className="mt-3 flex items-start gap-2 rounded-[20px] border border-amber-200 bg-amber-50/70 px-4 py-3 text-xs leading-5 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
          <Info size={14} className="mt-0.5 shrink-0" />
          <div>
            {partialEntries.length === 1 ? (
              <>
                Lokaler Bestand der Quelle „{partialEntries[0].source}“ deckt nur{' '}
                <strong>{formatCoveragePercent(partialEntries[0].coverage_ratio)}</strong>
                {' '}der Quelldaten ab — vollständige Prüfung erfordert Original-Recherche.
              </>
            ) : (
              <>
                {partialEntries.length} Quellen sind partiell synchronisiert — vollständige
                Prüfung dieser Module erfordert Original-Recherche.
              </>
            )}
          </div>
        </div>
      )}
    </SectionFrame>
  );
}

function CoverageRow({ entry }: { entry: AuditCoverageEntry }) {
  return (
    <tr className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60 dark:odd:bg-slate-950/40 dark:even:bg-slate-900/40 dark:hover:bg-slate-900/70">
      <td className="px-4 py-2 font-medium">{entry.module || '—'}</td>
      <td
        className="max-w-[220px] truncate px-4 py-2 text-xs text-slate-600 dark:text-slate-300"
        title={entry.source || undefined}
      >
        {entry.source || '—'}
        {entry.note && (
          <div className="mt-0.5 truncate text-[11px] text-slate-400 dark:text-slate-500" title={entry.note}>
            {entry.note}
          </div>
        )}
      </td>
      <td className="px-4 py-2 text-right font-mono text-xs">
        {entry.local_count !== null ? formatInt(entry.local_count) : '—'}
      </td>
      <td className="px-4 py-2 text-right font-mono text-xs">
        {entry.expected_count !== null ? formatInt(entry.expected_count) : '—'}
      </td>
      <td className="px-4 py-2 text-right font-mono text-xs">
        {formatCoveragePercent(entry.coverage_ratio)}
      </td>
      <td className="px-4 py-2 text-xs text-slate-500 dark:text-slate-400">
        {formatDate(entry.last_harvest_at)}
      </td>
      <td className="px-4 py-2">
        <CoverageStatusPill status={entry.status} />
      </td>
    </tr>
  );
}

// ── Sektion 5: Quellen und Datenstand ────────────────────────────────────────

function SourcesExplanationSection({ data }: { data: AuditReportData }) {
  const sources = data.sources_explanation || [];
  if (sources.length === 0) return null;

  return (
    <section
      id="sec-sources"
      style={{ scrollMarginTop: 80 }}
      className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75"
    >
      <header className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
          <Database size={20} />
        </div>
        <div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Quellen und Datenstand</h3>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Herkunft der Daten und Stand der hinterlegten Register.
          </p>
        </div>
      </header>
      <div className="mt-4 space-y-3">
        {sources.map((src, idx) => {
          const safeUrl = safeExternalUrl(src.url);
          return (
            <div
              key={`${src.name}-${idx}`}
              className="rounded-[22px] bg-slate-50 p-3 dark:bg-slate-900/60"
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-medium text-slate-900 dark:text-slate-100">{src.name}</span>
                {safeUrl && (
                  <a
                    href={safeUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-cyan-700 underline hover:text-cyan-900 dark:text-cyan-300 dark:hover:text-cyan-100"
                  >
                    {src.url}
                    <ExternalLink size={11} />
                  </a>
                )}
              </div>
              {src.description && (
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{src.description}</p>
              )}
              <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Datenstand: {src.last_data_update ? formatDate(src.last_data_update) : 'unbekannt'}
                {' · '}
                {src.record_count.toLocaleString('de-DE')} Datensätze
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ── Sektion 6: Disclaimer / Hinweise zur Anwendung ───────────────────────────

function DisclaimerSection({ data }: { data: AuditReportData }) {
  const text = (data.disclaimer || '').trim();
  if (!text) return null;
  return (
    <section className="rounded-[26px] border border-amber-200/70 bg-amber-50/70 p-4 text-sm leading-6 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
      <h4 className="font-semibold">Hinweise zur Anwendung</h4>
      <pre className="mt-2 whitespace-pre-wrap font-sans text-[13px]">{text}</pre>
    </section>
  );
}

// ── TopList-Helfer ───────────────────────────────────────────────────────────

interface TopListEntry {
  label: string;
  primary: string;
  secondary?: string;
}

function TopList({
  icon: Icon,
  title,
  entries,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  entries: TopListEntry[];
}) {
  return (
    <div className="rounded-[22px] border border-slate-200/80 bg-slate-50/70 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/40">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
        <Icon size={12} className="text-slate-400" />
        {title}
      </div>
      {entries.length === 0 ? (
        <div className="mt-2 text-xs text-slate-400">Keine Werte.</div>
      ) : (
        <ol className="mt-2 space-y-1.5 text-sm">
          {entries.map((entry, idx) => (
            <li key={`${entry.label}-${idx}`} className="flex items-baseline gap-2">
              <span className="w-4 shrink-0 font-mono text-[11px] text-slate-400">{idx + 1}.</span>
              <span className="flex-1 truncate text-slate-700 dark:text-slate-200" title={entry.label}>
                {entry.label || 'unbekannt'}
              </span>
              <span className="shrink-0 font-mono text-[11px] font-semibold text-slate-700 dark:text-slate-100">
                {entry.primary}
              </span>
              {entry.secondary && (
                <span className="hidden shrink-0 font-mono text-[11px] text-slate-500 sm:inline">
                  {entry.secondary}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ── Hauptkomponente ──────────────────────────────────────────────────────────

export default function AuditReportPreview({
  data,
  showLlmRejected,
  onToggleShowLlmRejected,
}: Props) {
  const issuedAtFormatted = (() => {
    try {
      return new Date(data.issued_at).toLocaleString('de-DE', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    } catch {
      return data.issued_at;
    }
  })();

  return (
    <div className="space-y-5">
      {/* Bericht-Kopf */}
      <section className="rounded-[28px] border border-indigo-200/70 bg-indigo-50/40 px-5 py-4 dark:border-indigo-500/30 dark:bg-indigo-950/30">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-indigo-700 shadow-sm dark:bg-indigo-900/60 dark:text-indigo-200">
              <FileSearch size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-indigo-900 dark:text-indigo-100">
                Bericht zu „{data.query}“
              </h2>
              <p className="mt-0.5 text-xs text-indigo-800/80 dark:text-indigo-200/80">
                Erstellt am {issuedAtFormatted} aus drei öffentlichen Registern.
              </p>
            </div>
          </div>
          <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[max-content_1fr]">
            {data.auftraggeber && (
              <>
                <dt className="text-indigo-700/80 dark:text-indigo-300/80">Auftraggeber:</dt>
                <dd className="text-indigo-900 dark:text-indigo-100">{data.auftraggeber}</dd>
              </>
            )}
            {data.pruefer_name && (
              <>
                <dt className="text-indigo-700/80 dark:text-indigo-300/80">Prüfer:</dt>
                <dd className="text-indigo-900 dark:text-indigo-100">{data.pruefer_name}</dd>
              </>
            )}
          </dl>
        </div>
      </section>

      <StateAidSection data={data} />
      <BeneficiariesSection data={data} />
      <SanctionsSection data={data} />
      <PersonsCheckSection data={data} />
      <CrossReferencesSection
        data={data}
        showLlmRejected={!!showLlmRejected}
        onToggleShowLlmRejected={onToggleShowLlmRejected}
      />
      <LlmVerificationSection data={data} />
      <CoverageSection data={data} />
      <SourcesExplanationSection data={data} />
      <DisclaimerSection data={data} />
    </div>
  );
}
