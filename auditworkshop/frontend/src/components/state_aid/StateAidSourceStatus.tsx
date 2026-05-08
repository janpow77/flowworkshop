/**
 * StateAidSourceStatus — Quellen-Karten mit Quality-Ampel.
 *
 * Plan §5.3 + §12: pro Quelle Datenstand, Coverage-Note, Ampel.
 * Admin-Buttons (Trigger Harvest / Loeschen) sind optional sichtbar.
 *
 * Plan §11 (Harvest-Modi):
 *  - smart (Default): nur neue Records, alte bleiben unverändert.
 *  - full-refresh:    vorhandene Records werden überschrieben (TAM-Korrekturen).
 *  - force:           vorhandene Records werden GELÖSCHT und alle neu geladen.
 */
import { useState } from 'react';
import {
  AlertTriangle, CheckCircle2, ExternalLink, Info, Loader2, RefreshCw, Trash2, Database,
} from 'lucide-react';
import { safeExternalUrl, type HarvestMode, type HarvestResult, type StateAidQuality, type StateAidSource } from '../../lib/stateAidApi';

interface Props {
  sources: StateAidSource[];
  isAdmin: boolean;
  onHarvest?: (source: StateAidSource, mode: HarvestMode) => Promise<HarvestResult | void>;
  onDelete?: (source: StateAidSource) => Promise<void>;
}

const QUALITY: Record<NonNullable<StateAidQuality> | 'unknown', { label: string; class: string; dot: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  green: { label: 'gruen — stabile Quelle', class: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200', dot: 'bg-emerald-500', icon: CheckCircle2 },
  yellow: { label: 'gelb — eingeschraenkt', class: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-200', dot: 'bg-amber-400', icon: AlertTriangle },
  red: { label: 'rot — nicht harvestbar', class: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-200', dot: 'bg-rose-500', icon: AlertTriangle },
  unknown: { label: 'unbestimmt', class: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300', dot: 'bg-slate-300', icon: Database },
};

const MODE_OPTIONS: Array<{ value: HarvestMode; label: string; hint: string }> = [
  { value: 'smart', label: 'Smart (Default)', hint: 'nur neue Datensätze laden, alte bleiben unverändert' },
  { value: 'full-refresh', label: 'Full Refresh', hint: 'vorhandene Records überschreiben (TAM-Korrekturen)' },
  { value: 'force', label: 'Force (Reset)', hint: 'alle Records löschen und neu laden — Bestätigung erforderlich' },
];

function formatDateTime(iso: string | null): string {
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

interface RunInfo {
  result: HarvestResult;
  durationMs: number;
}

export default function StateAidSourceStatus({ sources, isAdmin, onHarvest, onDelete }: Props) {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<'harvest' | 'delete' | null>(null);
  const [modeBySource, setModeBySource] = useState<Record<string, HarvestMode>>({});
  const [lastRunBySource, setLastRunBySource] = useState<Record<string, RunInfo>>({});
  const [errorBySource, setErrorBySource] = useState<Record<string, string>>({});

  if (sources.length === 0) {
    return (
      <div className="rounded-[26px] border border-dashed border-slate-300 bg-white/85 px-6 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">
        Noch keine Quellen registriert. Sobald der Harvester laeuft, erscheinen hier
        TAM, nationale Register und manuelle Importe.
      </div>
    );
  }

  function modeFor(key: string): HarvestMode {
    return modeBySource[key] ?? 'smart';
  }

  async function runHarvest(source: StateAidSource) {
    if (!onHarvest) return;
    const mode = modeFor(source.source_key);
    if (mode === 'force') {
      const ok = window.confirm(
        `Achtung: 'Force' löscht alle ${source.record_count.toLocaleString('de-DE')} bestehenden Awards der Quelle "${source.display_name}" und lädt komplett neu. Fortfahren?`,
      );
      if (!ok) return;
    }
    setBusyKey(source.source_key);
    setBusyAction('harvest');
    setErrorBySource((prev) => {
      const next = { ...prev };
      delete next[source.source_key];
      return next;
    });
    const t0 = performance.now();
    try {
      const res = await onHarvest(source, mode);
      const durationMs = performance.now() - t0;
      if (res && typeof res === 'object' && 'records_inserted' in res) {
        setLastRunBySource((prev) => ({
          ...prev,
          [source.source_key]: { result: res as HarvestResult, durationMs },
        }));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Harvest fehlgeschlagen.';
      setErrorBySource((prev) => ({ ...prev, [source.source_key]: msg }));
    } finally {
      setBusyKey(null);
      setBusyAction(null);
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {sources.map((source) => {
        const q = source.quality ? QUALITY[source.quality] : QUALITY.unknown;
        const QIcon = q.icon;
        const currentMode = modeFor(source.source_key);
        const lastRun = lastRunBySource[source.source_key];
        const errMsg = errorBySource[source.source_key];
        const isBusy = busyKey === source.source_key;
        return (
          <div
            key={source.source_key}
            className="flex h-full flex-col rounded-[26px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_18px_60px_-44px_rgba(15,23,42,0.45)] backdrop-blur transition hover:shadow-[0_22px_70px_-44px_rgba(15,23,42,0.55)] dark:border-slate-800 dark:bg-slate-900/75"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${q.dot}`} aria-hidden />
                  <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{source.display_name}</h3>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {source.source_type}
                  </span>
                  {!source.enabled && (
                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">
                      deaktiviert
                    </span>
                  )}
                </div>
                <div className="mt-1 font-mono text-[11px] text-slate-400">{source.source_key}</div>
              </div>
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${q.class}`}>
                <QIcon size={11} />
                {q.label}
              </span>
            </div>

            <dl className="mt-4 space-y-1.5 rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 text-xs dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
              <Row label="Letzter Harvest" value={formatDateTime(source.last_successful_harvest_at)} mono />
              <Row label="Letzter Datensatz" value={formatDateTime(source.last_record_date)} mono />
              <Row
                label="Datensaetze"
                value={source.record_count.toLocaleString('de-DE')}
                mono
              />
              <Row label="Land" value={source.country_code || '—'} />
            </dl>

            {source.coverage_note && (
              <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
                {source.coverage_note}
              </p>
            )}

            {source.enabled && (source.record_count ?? 0) === 0 && (
              <div className="mt-3 inline-flex items-start gap-1.5 rounded-xl border border-amber-200/70 bg-amber-50/80 px-3 py-2 text-[11px] leading-5 text-amber-800 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-200">
                <AlertTriangle size={11} className="mt-0.5 shrink-0" />
                <span>
                  Keine Datensaetze fuer den letzten Lauf — Connector noch nicht
                  implementiert oder TAM-Antwort leer. Bitte den Admin pruefen
                  lassen.
                </span>
              </div>
            )}

            {isAdmin && onHarvest && (
              <p className="mt-3 inline-flex items-start gap-1.5 rounded-xl bg-emerald-50/60 px-3 py-2 text-[11px] leading-5 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
                <Info size={11} className="mt-0.5 shrink-0" />
                <span>Smart-Modus: nur neue Datensätze laden, alte bleiben unverändert.</span>
              </p>
            )}

            <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
              {(() => {
                // safeExternalUrl filtert javascript:/data:-URLs heraus —
                // Defense-in-Depth, falls jemand die Source-Tabelle manipuliert.
                const safeBase = safeExternalUrl(source.base_url);
                return safeBase ? (
                  <a
                    href={safeBase}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-emerald-300 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-emerald-500/40 dark:hover:text-emerald-300"
                  >
                    Quelle <ExternalLink size={11} />
                  </a>
                ) : null;
              })()}
              {isAdmin && onHarvest && (
                <>
                  <div
                    role="group"
                    aria-label="Harvest-Modus"
                    title={MODE_OPTIONS.find((m) => m.value === currentMode)?.hint || ''}
                    className="inline-flex items-center rounded-full border border-slate-200 bg-white p-0.5 text-[11px] dark:border-slate-700 dark:bg-slate-900"
                  >
                    {MODE_OPTIONS.map((opt) => {
                      const active = currentMode === opt.value;
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          disabled={isBusy}
                          onClick={() => setModeBySource((prev) => ({ ...prev, [source.source_key]: opt.value }))}
                          title={opt.hint}
                          className={`rounded-full px-2.5 py-1 font-medium transition disabled:opacity-60 ${
                            active
                              ? 'bg-slate-900 text-white shadow-sm dark:bg-emerald-500 dark:text-slate-950'
                              : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                          }`}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => { void runHarvest(source); }}
                    className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-white transition disabled:opacity-60 ${
                      currentMode === 'force'
                        ? 'bg-rose-600 hover:bg-rose-700'
                        : currentMode === 'full-refresh'
                          ? 'bg-amber-600 hover:bg-amber-700'
                          : 'bg-emerald-600 hover:bg-emerald-700'
                    }`}
                  >
                    {isBusy && busyAction === 'harvest'
                      ? <Loader2 size={12} className="animate-spin" />
                      : <RefreshCw size={12} />}
                    {currentMode === 'force'
                      ? 'Force ausführen'
                      : currentMode === 'full-refresh'
                        ? 'Vollständig erneuern'
                        : 'Smart aktualisieren'}
                  </button>
                </>
              )}
              {isAdmin && onDelete && (
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={async () => {
                    if (!window.confirm(`Awards der Quelle "${source.display_name}" wirklich loeschen?`)) return;
                    setBusyKey(source.source_key);
                    setBusyAction('delete');
                    try { await onDelete(source); }
                    finally { setBusyKey(null); setBusyAction(null); }
                  }}
                  className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-50 disabled:opacity-60 dark:border-rose-500/30 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
                >
                  {isBusy && busyAction === 'delete'
                    ? <Loader2 size={12} className="animate-spin" />
                    : <Trash2 size={12} />}
                  Awards loeschen
                </button>
              )}
            </div>

            {/* Status-Zeile fuer den letzten Lauf */}
            {lastRun && (
              <div className="mt-3 rounded-xl border border-emerald-200/70 bg-emerald-50/60 px-3 py-2 text-[11px] leading-5 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-950/30 dark:text-emerald-100">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={12} />
                  <span>
                    {lastRun.result.records_inserted.toLocaleString('de-DE')} neu,{' '}
                    {lastRun.result.records_skipped.toLocaleString('de-DE')} bereits vorhanden,{' '}
                    {lastRun.result.records_failed.toLocaleString('de-DE')} Fehler — Lauf in{' '}
                    {(lastRun.durationMs / 1000).toFixed(1)}s
                    {lastRun.result.records_updated > 0 && (
                      <> · {lastRun.result.records_updated.toLocaleString('de-DE')} aktualisiert</>
                    )}
                  </span>
                </div>
                {lastRun.result.error && (
                  <div className="mt-1 truncate font-mono text-[10px] text-rose-700 dark:text-rose-300" title={lastRun.result.error}>
                    {lastRun.result.error}
                  </div>
                )}
              </div>
            )}

            {errMsg && (
              <div className="mt-3 flex items-start gap-1.5 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] leading-5 text-rose-800 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-200">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                <span>{errMsg}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start gap-2">
      <dt className="w-32 shrink-0 text-slate-400">{label}</dt>
      <dd className={`flex-1 text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-[11px]' : ''}`}>{value}</dd>
    </div>
  );
}
