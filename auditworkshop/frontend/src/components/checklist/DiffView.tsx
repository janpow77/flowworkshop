/**
 * flowworkshop · components/checklist/DiffView.tsx
 *
 * Diff-Ansicht eines einzelnen Verlaufseintrags. Zeigt bei ``updated`` die
 * geaenderten Felder als Tabelle (Feld | vorher | nachher, alt rot / neu gruen),
 * bei ``created``/``deleted``/``restored`` den vollstaendigen Knoten-Snapshot,
 * und bei ``moved`` die Verschiebungs-Felder (Eltern/Position).
 *
 * Reines Anzeige-Bauteil ohne eigenen Datenfluss — der Aufrufer reicht das
 * ``HistoryDetail`` herein. Farbwelt Emerald/Cyan + Dark Mode.
 */
import { ArrowRight, FileJson, Loader2, MoveRight } from 'lucide-react';
import type { HistoryDetail } from '../../lib/api';
import { FIELD_LABELS } from './treeMeta';

interface DiffViewProps {
  detail: HistoryDetail | null;
  loading: boolean;
  error: string;
}

/** Menschenlesbare Darstellung eines (ggf. komplexen) Feldwerts. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '(leer)';
  if (typeof value === 'boolean') return value ? 'ja' : 'nein';
  if (Array.isArray(value)) {
    if (value.length === 0) return '(leer)';
    return value.map((v, i) => `${i + 1}. ${formatValue(v)}`).join('\n');
  }
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

export default function DiffView({ detail, loading, error }: DiffViewProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 px-4 py-10 text-sm text-slate-400">
        <Loader2 size={16} className="animate-spin" /> Lädt Details…
      </div>
    );
  }
  if (error) {
    return (
      <div className="mx-1 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
        {error}
      </div>
    );
  }
  if (!detail) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 py-12 text-center text-slate-400">
        <FileJson size={32} className="mb-3" />
        <p className="text-sm">Wählen Sie links einen Verlaufseintrag, um die Änderung anzuzeigen.</p>
      </div>
    );
  }

  const changed = detail.changed_fields;
  const hasFieldDiff = changed && Object.keys(changed).length > 0;
  const snapshot = detail.node_snapshot;
  const isMove = detail.old_parent_id !== null
    || detail.new_parent_id !== null
    || detail.old_position !== null
    || detail.new_position !== null;

  return (
    <div className="space-y-4">
      {/* Begruendung/Zusammenfassung */}
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300">
        <span className="font-medium">{detail.summary}</span>
        {detail.change_reason && (
          <span className="mt-1 block text-slate-500 dark:text-slate-400">{detail.change_reason}</span>
        )}
      </div>

      {/* Feld-Diff (bei updated) */}
      {hasFieldDiff && (
        <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
          <div className="grid grid-cols-[minmax(90px,1fr)_1fr_1fr] bg-slate-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <span>Feld</span>
            <span>vorher</span>
            <span>nachher</span>
          </div>
          {Object.entries(changed!).map(([field, change]) => (
            <div
              key={field}
              className="grid grid-cols-[minmax(90px,1fr)_1fr_1fr] items-stretch border-t border-slate-100 text-xs dark:border-slate-800"
            >
              <div className="px-3 py-2 font-medium text-slate-600 dark:text-slate-300">
                {fieldLabel(field)}
              </div>
              <div className="border-l border-slate-100 bg-red-50/50 px-3 py-2 text-red-800 dark:border-slate-800 dark:bg-red-900/10 dark:text-red-300">
                <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-sans">{formatValue(change.old)}</pre>
              </div>
              <div className="border-l border-slate-100 bg-emerald-50/60 px-3 py-2 text-emerald-800 dark:border-slate-800 dark:bg-emerald-900/15 dark:text-emerald-300">
                <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-sans">{formatValue(change.new)}</pre>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Verschiebung (bei moved) */}
      {isMove && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-1.5 border-b border-slate-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:border-slate-800 dark:text-slate-400">
            <MoveRight size={13} /> Verschiebung
          </div>
          <div className="space-y-1 px-3 py-2 text-xs text-slate-600 dark:text-slate-300">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400">Eltern:</span>
              <span className="font-mono text-[11px]">{detail.old_parent_id ?? '(Wurzel)'}</span>
              <ArrowRight size={12} className="text-slate-400" />
              <span className="font-mono text-[11px]">{detail.new_parent_id ?? '(Wurzel)'}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400">Position:</span>
              <span>{detail.old_position ?? '–'}</span>
              <ArrowRight size={12} className="text-slate-400" />
              <span>{detail.new_position ?? '–'}</span>
            </div>
          </div>
        </div>
      )}

      {/* Voll-Snapshot (bei created/deleted/restored bzw. wenn kein Feld-Diff) */}
      {!hasFieldDiff && snapshot && Object.keys(snapshot).length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
          <div className="border-b border-slate-100 bg-slate-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-400">
            Knoten-Snapshot
          </div>
          <dl className="divide-y divide-slate-100 text-xs dark:divide-slate-800">
            {Object.entries(snapshot)
              .filter(([, v]) => v !== null && v !== undefined && v !== '')
              .map(([field, value]) => (
                <div key={field} className="grid grid-cols-[minmax(90px,1fr)_2fr] gap-2 px-3 py-1.5">
                  <dt className="font-medium text-slate-500 dark:text-slate-400">{fieldLabel(field)}</dt>
                  <dd className="text-slate-700 dark:text-slate-200">
                    <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words font-sans">{formatValue(value)}</pre>
                  </dd>
                </div>
              ))}
          </dl>
        </div>
      )}
    </div>
  );
}
