/**
 * AuditCrossReferences — Liste neutraler Querbezuege zwischen den drei
 * Registern (State-Aid, Beguenstigtenverzeichnis, Sanktionslisten).
 *
 * Wichtige Designvorgaben (siehe Plan-Hinweis im Task):
 *  - KEINE Severity-Farben oder Risiko-Ampeln.
 *  - Jede Beobachtung ist neutral-faktisch in einer schlichten Karte.
 *  - Evidence wird als Definition-List rendered, damit der Pruefer die
 *    konkreten Felder sieht, auf die sich der Querbezug stuetzt.
 */
import { Brain, Link2 } from 'lucide-react';
import type { AuditReportCrossReference } from '../../lib/stateAidApi';

interface Props {
  items: AuditReportCrossReference[];
}

/**
 * Konvertiert einen technischen Type-String (`beneficiary_identifier_match`,
 * `sa_reference_seen_in_beneficiary`, ...) in ein menschenlesbares Label. Wenn
 * der Backend-Type unbekannt ist, fallen wir auf eine Title-Case-Variante des
 * Strings zurueck.
 */
function formatType(type: string): string {
  const known: Record<string, string> = {
    beneficiary_identifier_match: 'Beneficiary-Identifier in mehreren Registern',
    name_match_state_aid_beneficiaries: 'Namens-Treffer State-Aid und Begünstigtenverzeichnis',
    sa_reference_seen_in_beneficiary: 'SA-Referenz auch im Begünstigtenverzeichnis',
    sanctions_listed_beneficiary: 'Begünstigter steht in einer Sanktionsliste',
    same_authority_multiple_awards: 'Mehrere Awards von derselben Behörde',
    same_nuts_concentration: 'Konzentration auf einer NUTS-Region',
  };
  if (known[type]) return known[type];
  // Fallback: snake_case → Title Case
  return type
    .split('_')
    .map((part) => (part.length > 0 ? part[0].toUpperCase() + part.slice(1) : part))
    .join(' ');
}

/**
 * Rendert einen Evidence-Wert als String. Objekte werden als JSON dargestellt,
 * Arrays kommagetrennt; primitive Werte direkt. Leere Werte erscheinen als
 * "—" damit das Layout nicht kollabiert.
 */
function formatEvidenceValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) {
    return value.map((v) => formatEvidenceValue(v)).join(', ');
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export default function AuditCrossReferences({ items }: Props) {
  if (!items || items.length === 0) {
    return (
      <div className="rounded-[22px] border border-dashed border-slate-300 bg-slate-50/70 px-4 py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
        Keine registerübergreifenden Beobachtungen für diese Suche.
      </div>
    );
  }

  return (
    <ul className="space-y-3">
      {items.map((item, idx) => {
        const evidenceEntries = Object.entries(item.evidence || {});
        const rejected = !!item.filtered_by_llm;
        // Vom LLM verworfene Eintraege werden ausgegraut + Brain-Icon-Hinweis;
        // Defense-in-Depth: aria-disabled fuer Screenreader.
        return (
          <li
            key={`${item.type}-${idx}`}
            aria-disabled={rejected || undefined}
            className={`rounded-[22px] px-4 py-3 ${
              rejected
                ? 'bg-slate-50/60 opacity-60 dark:bg-slate-900/30'
                : 'bg-slate-50 dark:bg-slate-900/60'
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full shadow-sm ${
                  rejected
                    ? 'bg-rose-50 text-rose-500 dark:bg-rose-950/40 dark:text-rose-300'
                    : 'bg-white text-slate-500 dark:bg-slate-800 dark:text-slate-300'
                }`}
                aria-hidden
              >
                {rejected ? <Brain size={13} /> : <Link2 size={13} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                  {formatType(item.type)}
                  {rejected && (
                    <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-medium normal-case tracking-normal text-rose-700 dark:bg-rose-950/50 dark:text-rose-200">
                      LLM verworfen
                    </span>
                  )}
                </div>
                <p
                  className={`mt-1 text-sm leading-6 ${
                    rejected
                      ? 'text-slate-600 line-through decoration-slate-400 dark:text-slate-300'
                      : 'text-slate-800 dark:text-slate-100'
                  }`}
                >
                  {item.description}
                </p>
                {evidenceEntries.length > 0 && (
                  <dl className="mt-3 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[max-content_1fr]">
                    {evidenceEntries.map(([key, value]) => (
                      <div
                        key={key}
                        className="contents"
                      >
                        <dt className="font-mono text-slate-500 dark:text-slate-400">{key}</dt>
                        <dd className="break-words text-slate-700 dark:text-slate-200">
                          {formatEvidenceValue(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
