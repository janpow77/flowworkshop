/**
 * StateAidExportActions — CSV + PDF Export-Buttons.
 *
 * Plan §9.4: Export muss Suchparameter, Datenstand, Quellenhinweis und
 * Trefferliste enthalten — das wird vom Backend in /export uebernommen.
 * Hier setzen wir nur die URL und triggern einen Download.
 */
import { FileSpreadsheet, FileText } from 'lucide-react';
import { exportUrl, type StateAidSearchParams } from '../../lib/stateAidApi';

interface Props {
  params: StateAidSearchParams;
  disabled?: boolean;
  hitCount?: number;
}

export default function StateAidExportActions({ params, disabled, hitCount }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[26px] border border-slate-200/80 bg-white/90 px-4 py-3 shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
      <div className="text-xs text-slate-500 dark:text-slate-400">
        Pruefnotiz inklusive Suchparameter, Datenstand und Quellenhinweis exportieren
        {typeof hitCount === 'number' && (
          <span className="ml-1 text-slate-400">· {hitCount.toLocaleString('de-DE')} Treffer</span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <a
          href={disabled ? undefined : exportUrl('csv', params)}
          download
          aria-disabled={disabled}
          className={`inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-[0_8px_24px_-12px_rgba(15,23,42,0.2)] transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 ${disabled ? 'pointer-events-none opacity-50' : ''}`}
        >
          <FileSpreadsheet size={14} /> CSV/Excel
        </a>
        <a
          href={disabled ? undefined : exportUrl('pdf', params)}
          download
          aria-disabled={disabled}
          className={`inline-flex items-center gap-2 rounded-full bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-[0_12px_28px_-16px_rgba(5,150,105,0.55)] transition hover:bg-emerald-700 ${disabled ? 'pointer-events-none opacity-50' : ''}`}
        >
          <FileText size={14} /> PDF
        </a>
      </div>
    </div>
  );
}
