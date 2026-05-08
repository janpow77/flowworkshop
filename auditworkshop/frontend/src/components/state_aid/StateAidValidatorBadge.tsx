/**
 * StateAidValidatorBadge — Self-Check-Status fuer das State-Aid-Modul.
 *
 * Pollt /api/state-aid/validation/last alle 60 Sekunden und zeigt:
 *  - status=ok        → gruenes Badge "Self-Check HH:MM ✓"
 *  - status=warnings  → gelbes Badge mit Tooltip-Liste
 *  - status=failed    → rotes Badge prominent
 *
 * Klick oeffnet ein Modal mit allen Findings.
 */
import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ShieldCheck, X } from 'lucide-react';
import {
  getValidationLast,
  type ValidationFinding,
  type ValidationReport,
  type ValidationStatus,
} from '../../lib/stateAidApi';

interface Props {
  /** Polling-Intervall in Millisekunden (Default 60.000 = 60s). */
  intervalMs?: number;
}

interface BadgeStyle {
  label: string;
  className: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
}

const BADGE_STYLES: Record<ValidationStatus | 'loading' | 'idle', BadgeStyle> = {
  ok: {
    label: 'OK',
    className:
      'bg-emerald-500/15 text-emerald-100 border-emerald-300/30 hover:bg-emerald-500/25',
    Icon: CheckCircle2,
  },
  warnings: {
    label: 'Hinweise',
    className:
      'bg-amber-400/20 text-amber-100 border-amber-300/40 hover:bg-amber-400/30',
    Icon: AlertTriangle,
  },
  failed: {
    label: 'Fehler',
    className:
      'bg-rose-500/25 text-rose-50 border-rose-300/50 ring-1 ring-rose-300/40 hover:bg-rose-500/40',
    Icon: AlertTriangle,
  },
  loading: {
    label: 'laedt …',
    className:
      'bg-white/10 text-emerald-50/80 border-white/15 hover:bg-white/15',
    Icon: ShieldCheck,
  },
  idle: {
    label: 'noch nicht ausgefuehrt',
    className:
      'bg-white/10 text-emerald-50/70 border-white/15 hover:bg-white/15',
    Icon: ShieldCheck,
  },
};

const SEVERITY_BADGE: Record<ValidationFinding['severity'], string> = {
  error: 'bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200',
  info: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-950/40 dark:text-cyan-200',
};

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleTimeString('de-DE', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function StateAidValidatorBadge({ intervalMs = 60000 }: Props) {
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchOnce() {
      try {
        const res = await getValidationLast();
        if (cancelled) return;
        setReport(res.report);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Self-Check-Status nicht abrufbar.');
      } finally {
        if (!cancelled) setLoaded(true);
      }
    }
    void fetchOnce();
    const id = window.setInterval(() => { void fetchOnce(); }, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [intervalMs]);

  const status: ValidationStatus | 'loading' | 'idle' = useMemo(() => {
    if (!loaded) return 'loading';
    if (!report) return 'idle';
    return report.status;
  }, [loaded, report]);

  const style = BADGE_STYLES[status];
  const StatusIcon = style.Icon;
  const time = report ? formatTime(report.started_at) : null;

  const tooltip = useMemo(() => {
    if (!report) return error || 'Noch kein Self-Check ausgefuehrt.';
    if (report.status === 'ok') {
      return `Alle ${report.checks_total} Checks bestanden.`;
    }
    const lines: string[] = [];
    for (const f of report.findings.slice(0, 5)) {
      lines.push(`• [${f.severity.toUpperCase()}] ${f.code}: ${f.message}`);
    }
    if (report.findings.length > 5) {
      lines.push(`… und ${report.findings.length - 5} weitere.`);
    }
    return lines.join('\n');
  }, [report, error]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={tooltip}
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium transition ${style.className}`}
        aria-label="Self-Check Details anzeigen"
      >
        <StatusIcon size={12} />
        <span className="font-semibold uppercase tracking-[0.18em]">Self-Check</span>
        {time && <span className="font-mono opacity-90">{time}</span>}
        <span className="hidden sm:inline">{style.label}</span>
        {report && report.findings.length > 0 && (
          <span className="rounded-full bg-white/20 px-1.5 py-0.5 text-[10px] font-bold">
            {report.findings.length}
          </span>
        )}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-[2000] flex items-center justify-center bg-slate-900/60 px-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-[26px] border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                  Self-Check für State-Aid-Modul
                </h2>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Letzter Lauf: {report ? formatDateTime(report.started_at) : '—'} ·
                  Dauer: {report ? `${report.duration_ms} ms` : '—'} ·
                  Modul: {report?.module || '—'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-full p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label="Schliessen"
              >
                <X size={16} />
              </button>
            </div>

            {error && (
              <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {!report && !error && (
              <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
                Noch kein Self-Check ausgeführt. Die Prüfung läuft täglich
                automatisch nach dem Harvest oder kann von Admins manuell ausgelöst
                werden.
              </div>
            )}

            {report && (
              <>
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Stat label="Checks gesamt" value={report.checks_total} />
                  <Stat label="Bestanden" value={report.checks_passed} accent="emerald" />
                  <Stat label="Hinweise" value={report.checks_warned} accent="amber" />
                  <Stat label="Fehler" value={report.checks_failed} accent="rose" />
                </div>

                <div className="mt-5">
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                    Findings ({report.findings.length})
                  </h3>
                  {report.findings.length === 0 ? (
                    <p className="mt-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-950/30 dark:text-emerald-200">
                      Alles in Ordnung — keine Auffaelligkeiten in diesem Lauf.
                    </p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {report.findings.map((f, idx) => (
                        <li
                          key={`${f.code}-${idx}`}
                          className="rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-800/40"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${SEVERITY_BADGE[f.severity]}`}
                            >
                              {f.severity}
                            </span>
                            <span className="font-mono text-[10px] text-slate-500 dark:text-slate-400">
                              {f.code}
                            </span>
                          </div>
                          <p className="mt-1 text-slate-700 dark:text-slate-200">
                            {f.message}
                          </p>
                          {f.detail && (
                            <details className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                              <summary className="cursor-pointer hover:text-slate-700 dark:hover:text-slate-200">
                                Details
                              </summary>
                              <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-slate-900 p-2 font-mono text-[10px] text-emerald-200">
                                {JSON.stringify(f.detail, null, 2)}
                              </pre>
                            </details>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: 'emerald' | 'amber' | 'rose';
}) {
  const colorClass =
    accent === 'emerald'
      ? 'text-emerald-700 dark:text-emerald-300'
      : accent === 'amber'
        ? 'text-amber-700 dark:text-amber-300'
        : accent === 'rose'
          ? 'text-rose-700 dark:text-rose-300'
          : 'text-slate-900 dark:text-white';
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className={`mt-0.5 text-xl font-semibold ${colorClass}`}>
        {value.toLocaleString('de-DE')}
      </div>
    </div>
  );
}
