/**
 * StateAidResultsTable — Trefferliste für das Beihilfe-Register.
 *
 * Plan §9.3: Spalten Begünstigter, Land/Region, Betrag (EUR), Datum,
 * Beihilfeinstrument, SA-Ref, Behörde, Score (mit Confidence-Badge).
 * Klick auf eine Zeile öffnet den Award-Detail-Drawer.
 */
import { useMemo, useState } from 'react';
import { Brain, ClipboardCheck, ExternalLink, FileSearch, Lightbulb, Search } from 'lucide-react';
import { Skeleton } from '../ui/Skeleton';
import {
  safeExternalUrl,
  type StateAidConfidence,
  type StateAidMatchStage,
  type StateAidSearchHit,
} from '../../lib/stateAidApi';

interface Props {
  hits: StateAidSearchHit[];
  onSelect: (hit: StateAidSearchHit) => void;
  loading?: boolean;
}

const CONFIDENCE_BADGE: Record<StateAidConfidence, { label: string; class: string }> = {
  exact: { label: 'exakt', class: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300' },
  high: { label: 'hoch', class: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300' },
  medium: { label: 'mittel', class: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300' },
  low: { label: 'niedrig', class: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' },
};

// ── Pipeline-Stage-Badge ────────────────────────────────────────────────────
// Zweites Badge neben der Confidence-Pille, das anzeigt, aus welcher Stufe
// der 4-Stufen-Hybrid-Pipeline der Treffer kommt. Backend kann das Feld
// `match_stage` an einzelnen Hits liefern; ist es leer, wird kein Badge
// angezeigt (Backward-Compat).

const STAGE_BADGE_STYLES: Record<StateAidMatchStage, string> = {
  fuzzy: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  semantic: 'bg-violet-50 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300',
  'llm-confirmed': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  'llm-rejected': 'bg-rose-50 text-rose-700 line-through decoration-rose-400 dark:bg-rose-950/40 dark:text-rose-300',
};

const STAGE_LABELS: Record<StateAidMatchStage, string> = {
  fuzzy: 'fuzzy',
  semantic: 'semantic',
  'llm-confirmed': 'LLM ✓',
  'llm-rejected': 'LLM ✗',
};

function StageBadge({ stage }: { stage: StateAidMatchStage }) {
  const showBrain = stage === 'llm-confirmed' || stage === 'llm-rejected';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${STAGE_BADGE_STYLES[stage]}`}
      title={`Pipeline-Stufe: ${STAGE_LABELS[stage]}`}
    >
      {showBrain && <Brain size={10} aria-hidden />}
      {STAGE_LABELS[stage]}
    </span>
  );
}

function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(value);
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

function identifierSummary(hit: StateAidSearchHit): string | null {
  const raw = hit.beneficiary_identifier;
  const rawType = hit.beneficiary_identifier_type;
  const type = rawType && /ust|vat/i.test(rawType)
    ? 'USt-ID / Steuernummer'
    : rawType && /handelsregister/i.test(rawType)
      ? 'Handelsregister'
      : rawType;
  const value = hit.beneficiary_identifier_value;
  if (value) return `${type || 'Nationale Kennung'}: ${value}`;
  if (type) return `${type}: keine Nummer veröffentlicht`;
  if (raw) return `Nationale Kennung: ${raw}`;
  return null;
}

function auditReportUrl(hit: StateAidSearchHit): string {
  const params = new URLSearchParams();
  params.set('q', hit.beneficiary_name);
  if (hit.country_code === 'DE' || hit.country_code === 'AT') {
    params.set('country_code', hit.country_code);
  }
  return `/audit-report?${params.toString()}`;
}

export default function StateAidResultsTable({ hits, onSelect, loading }: Props) {
  const [beneficiaryFilter, setBeneficiaryFilter] = useState('');
  const normalizedBeneficiaryFilter = beneficiaryFilter.trim().toLocaleLowerCase('de-DE');
  const filteredHits = useMemo(() => {
    if (!normalizedBeneficiaryFilter) return hits;
    return hits.filter((hit) => {
      const haystack = [
        hit.beneficiary_name,
        hit.beneficiary_identifier,
        hit.beneficiary_identifier_type,
        hit.beneficiary_identifier_value,
      ].filter(Boolean).join(' ').toLocaleLowerCase('de-DE');
      return haystack.includes(normalizedBeneficiaryFilter);
    });
  }, [hits, normalizedBeneficiaryFilter]);

  if (loading) {
    // 5 Skeleton-Zeilen, damit das Layout-Volumen während des Suchlaufs gleich bleibt.
    return (
      <div className="overflow-hidden rounded-[26px] border border-slate-200/80 bg-white shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/75">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-900/60">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <Skeleton className="h-3 w-32" />
            <span aria-hidden>·</span>
            <Skeleton className="h-3 w-20" />
          </div>
        </div>
        <ul className="divide-y divide-slate-100 dark:divide-slate-800" aria-label="Treffer werden geladen">
          {Array.from({ length: 5 }, (_, i) => (
            <li key={i} className="grid grid-cols-[1.6fr_0.9fr_0.9fr_0.7fr_0.6fr] items-center gap-3 px-4 py-3">
              <div className="space-y-1.5">
                <Skeleton className="h-3.5 w-3/4" />
                <Skeleton className="h-2.5 w-1/3" />
              </div>
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="ml-auto h-3 w-1/2" />
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="ml-auto h-5 w-16 rounded-full" />
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (hits.length === 0) {
    return (
      <div className="rounded-[26px] border border-dashed border-slate-300 bg-white/85 px-6 py-10 text-center shadow-[0_18px_60px_-48px_rgba(15,23,42,0.25)] dark:border-slate-700 dark:bg-slate-900/60">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
          <FileSearch size={20} />
        </div>
        <h3 className="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Keine Treffer für die aktuellen Filter
        </h3>
        <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
          Versuchen Sie eine andere Schreibweise oder lockern Sie die Filter, zum Beispiel Zeitraum
          erweitern, NUTS-Filter entfernen oder ein anderes Land wählen.
        </p>
        <div className="mx-auto mt-3 inline-flex items-start gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          <Lightbulb size={11} className="mt-0.5 shrink-0 text-amber-500" />
          <span>Tipp: Akronyme wie „KfW" oder „BMW" werden automatisch expandiert.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[26px] border border-slate-200/80 bg-white shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/75">
      <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/70 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-xs font-semibold text-slate-700 dark:text-slate-200">
            Trefferliste
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
            {filteredHits.length.toLocaleString('de-DE')} von {hits.length.toLocaleString('de-DE')} Treffern sichtbar
          </div>
        </div>
        <label className="relative block w-full sm:max-w-sm">
          <span className="sr-only">Nach Begünstigtem filtern</span>
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={beneficiaryFilter}
            onChange={(event) => setBeneficiaryFilter(event.target.value)}
            className="w-full rounded-full border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-emerald-500 dark:focus:ring-emerald-500/20"
            placeholder="Nach Begünstigtem filtern"
          />
        </label>
      </div>
      <div className="max-h-[1100px] overflow-y-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-700">
          <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-900/60">
            <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              <th className="px-4 py-3">Begünstigter</th>
              <th className="px-3 py-3">Land · Region</th>
              <th className="px-3 py-3 text-right">Betrag (EUR)</th>
              <th className="px-3 py-3">Datum</th>
              <th className="px-3 py-3">Instrument</th>
              <th className="px-3 py-3">SA-Ref.</th>
              <th className="px-3 py-3">Behörde</th>
              <th className="px-3 py-3 text-right">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {filteredHits.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                  Keine Treffer für diesen Begünstigten-Filter.
                </td>
              </tr>
            ) : filteredHits.map((hit) => {
              const badge = CONFIDENCE_BADGE[hit.confidence];
              const region = [hit.country_code, hit.nuts_label || hit.nuts_code].filter(Boolean).join(' · ');
              const identifier = identifierSummary(hit);
              return (
                <tr
                  key={hit.award_id}
                  onClick={() => onSelect(hit)}
                  className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-800/40"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900 dark:text-slate-100">{hit.beneficiary_name}</div>
                    {identifier && (
                      <div className="mt-0.5 text-[11px] text-slate-400">
                        {identifier}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-600 dark:text-slate-300">{region || '—'}</td>
                  <td className="px-3 py-3 text-right font-mono text-xs tabular-nums text-slate-900 dark:text-slate-100">
                    {formatAmount(hit.aid_amount_eur ?? hit.aid_amount)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-xs text-slate-600 dark:text-slate-300">
                    {formatDate(hit.granting_date || hit.publication_date)}
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-600 dark:text-slate-300">{hit.aid_instrument || '—'}</td>
                  <td className="px-3 py-3">
                    {hit.sa_reference ? (() => {
                      // safeExternalUrl filtert javascript:/data:-Schemas raus.
                      // Defense-in-Depth gegen vergiftete TAM-Daten.
                      const safeCase = safeExternalUrl(hit.case_url);
                      return safeCase ? (
                        <a
                          href={safeCase}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 font-mono text-[12px] text-emerald-700 hover:underline dark:text-emerald-300"
                        >
                          {hit.sa_reference} <ExternalLink size={11} />
                        </a>
                      ) : (
                        <span className="font-mono text-[12px] text-slate-700 dark:text-slate-200">{hit.sa_reference}</span>
                      );
                    })() : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-600 dark:text-slate-300">{hit.granting_authority || '—'}</td>
                  <td className="px-3 py-3 text-right">
                    <div className="inline-flex items-center justify-end gap-1.5 whitespace-nowrap">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge.class}`}>
                        {hit.score} · {badge.label}
                      </span>
                      {hit.match_stage && <StageBadge stage={hit.match_stage} />}
                      <a
                        href={auditReportUrl(hit)}
                        onClick={(event) => event.stopPropagation()}
                        title="In Auswertung übernehmen"
                        aria-label="In Auswertung übernehmen"
                        className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[11px] font-medium text-indigo-700 transition hover:border-indigo-300 hover:bg-indigo-100 dark:border-indigo-500/30 dark:bg-indigo-950/30 dark:text-indigo-200 dark:hover:bg-indigo-950/50"
                      >
                        <ClipboardCheck size={11} />
                        In Auswertung
                      </a>
                    </div>
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
