/**
 * ExportButtons — wiederverwendbare Export-Action-Bar.
 *
 * Konsistenter Look fuer alle Listen-/Karten-Exporte:
 * - State-Aid-Suche, -Auswertung, -Karte
 * - Sanktionssuche
 * - Beneficiaries-Suche
 * - Audit-Trail
 *
 * Verwendung:
 *   <ExportButtons
 *     formats={['csv', 'xlsx', 'pdf']}
 *     onExport={(fmt) => downloadCsv(fmt)}
 *     disabled={hits.length === 0}
 *   />
 *
 * Die Komponente uebernimmt das Loading-State-Handling: solange
 * `onExport` ein Promise zurueckliefert, ist nur der gerade gedrueckte
 * Knopf disabled (mit Spinner) — die anderen bleiben klickbar.
 */
import { useCallback, useState } from 'react';
import {
  FileImage,
  FileSpreadsheet,
  FileText,
  Globe,
  Loader2,
} from 'lucide-react';

export type ExportFormat = 'csv' | 'xlsx' | 'pdf' | 'png' | 'geojson';

type Props = {
  /** Reihenfolge bestimmt die Anordnung der Buttons. */
  formats: ExportFormat[];
  onExport: (format: ExportFormat) => void | Promise<void>;
  disabled?: boolean;
  /** "compact" = Pills, "full" = breitere Buttons mit Beschriftung. */
  variant?: 'compact' | 'full';
  /** Optionaler Titel/Hinweis links neben den Buttons. */
  hint?: string;
  /** Optionaler Trefferzaehler — wird neben dem Hint klein angezeigt. */
  hitCount?: number;
  /** Optionaler className-Override fuer den Container. */
  className?: string;
};

const FORMAT_LABEL: Record<ExportFormat, string> = {
  csv: 'CSV',
  xlsx: 'Excel',
  pdf: 'PDF',
  png: 'PNG',
  geojson: 'GeoJSON',
};

const FORMAT_ICON: Record<ExportFormat, React.ComponentType<{ size?: number; className?: string }>> = {
  csv: FileSpreadsheet,
  xlsx: FileSpreadsheet,
  pdf: FileText,
  png: FileImage,
  geojson: Globe,
};

const PRIMARY_FORMATS: ExportFormat[] = ['xlsx', 'pdf'];

export default function ExportButtons({
  formats,
  onExport,
  disabled,
  variant = 'compact',
  hint,
  hitCount,
  className,
}: Props) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);

  const handleClick = useCallback(
    async (format: ExportFormat) => {
      if (disabled || busy) return;
      const result = onExport(format);
      if (result instanceof Promise) {
        setBusy(format);
        try {
          await result;
        } finally {
          setBusy(null);
        }
      }
    },
    [busy, disabled, onExport],
  );

  if (formats.length === 0) return null;

  const containerClass =
    className
    ?? (variant === 'compact'
      ? 'inline-flex flex-wrap gap-2'
      : 'flex flex-wrap items-center justify-between gap-3 rounded-[26px] border border-slate-200/80 bg-white/90 px-4 py-3 shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75');

  const baseButtonClass =
    'inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 disabled:opacity-50';
  const primaryButtonClass = `${baseButtonClass} bg-emerald-600 text-white hover:bg-emerald-700 shadow-[0_8px_22px_-14px_rgba(5,150,105,0.55)] dark:bg-emerald-500 dark:hover:bg-emerald-400`;
  const secondaryButtonClass = `${baseButtonClass} border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800`;

  const buttons = (
    <div className="inline-flex flex-wrap gap-2">
      {formats.map((format) => {
        const Icon = FORMAT_ICON[format];
        const isPrimary = PRIMARY_FORMATS.includes(format);
        const isBusy = busy === format;
        return (
          <button
            key={format}
            type="button"
            onClick={() => void handleClick(format)}
            disabled={Boolean(disabled) || Boolean(busy)}
            aria-disabled={Boolean(disabled) || Boolean(busy)}
            title={`Export als ${FORMAT_LABEL[format]}`}
            className={isPrimary ? primaryButtonClass : secondaryButtonClass}
          >
            {isBusy ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />}
            {FORMAT_LABEL[format]}
          </button>
        );
      })}
    </div>
  );

  if (variant === 'compact') {
    return <div className={containerClass}>{buttons}</div>;
  }

  return (
    <div className={containerClass}>
      <div className="text-xs text-slate-500 dark:text-slate-400">
        {hint ?? 'Export inklusive Datenstand und Pflichthinweis.'}
        {typeof hitCount === 'number' && (
          <span className="ml-1 text-slate-400">
            · {hitCount.toLocaleString('de-DE')} Treffer
          </span>
        )}
      </div>
      {buttons}
    </div>
  );
}
