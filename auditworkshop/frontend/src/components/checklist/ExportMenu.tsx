/**
 * flowworkshop · components/checklist/ExportMenu.tsx
 *
 * Download-Menue fuer den Checklisten-Designer: exportiert die Checkliste als
 * Word (DOCX), Excel (XLSX) oder PDF. Optionaler Umschalter „leer/befuellt"
 * (mode=blank|filled, Default blank). Der eigentliche Download laeuft ueber
 * ``exportChecklist`` (Blob + temporaerer <a>-Link, keine neue Abhaengigkeit).
 *
 * Export ist auch fuer Leser erlaubt (read-only-Recht reicht serverseitig).
 */
import { useEffect, useRef, useState } from 'react';
import {
  Download, FileText, FileType, Loader2, MessagesSquare, Sheet,
} from 'lucide-react';
import { exportChecklist, exportDiscussion, type ExportFormat, type ExportMode } from '../../lib/api';

type DiscussionFormat = 'docx' | 'pdf';

interface ExportMenuProps {
  templateId: string;
  /** Meldet Fehler nach aussen (Toast/Hinweis). */
  onError?: (msg: string) => void;
}

const FORMATS: Array<{ format: ExportFormat; label: string; icon: typeof FileText }> = [
  { format: 'word', label: 'Word (.docx)', icon: FileText },
  { format: 'excel', label: 'Excel (.xlsx)', icon: Sheet },
  { format: 'pdf', label: 'PDF (.pdf)', icon: FileType },
];

const DISCUSSION_FORMATS: Array<{ format: DiscussionFormat; label: string; icon: typeof FileText }> = [
  { format: 'docx', label: 'Diskussion als Word (.docx)', icon: FileText },
  { format: 'pdf', label: 'Diskussion als PDF (.pdf)', icon: FileType },
];

export default function ExportMenu({ templateId, onError }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<ExportMode>('blank');
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null);
  const [busyDiscussion, setBusyDiscussion] = useState<DiscussionFormat | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const busy = busyFormat !== null || busyDiscussion !== null;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const handleExport = async (format: ExportFormat) => {
    setBusyFormat(format);
    try {
      await exportChecklist(templateId, format, mode);
      setOpen(false);
    } catch {
      onError?.('Export fehlgeschlagen — bitte erneut versuchen.');
    } finally {
      setBusyFormat(null);
    }
  };

  const handleDiscussionExport = async (format: DiscussionFormat) => {
    setBusyDiscussion(format);
    try {
      await exportDiscussion(templateId, format);
      setOpen(false);
    } catch {
      onError?.('Diskussionsprotokoll-Export fehlgeschlagen — bitte erneut versuchen.');
    } finally {
      setBusyDiscussion(null);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Download size={14} /> Export
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1.5 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900"
        >
          {/* Modus-Umschalter (optional) */}
          <div className="mb-2 flex rounded-lg bg-slate-100 p-0.5 text-[11px] dark:bg-slate-800">
            {(['blank', 'filled'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`flex-1 rounded-md px-2 py-1 font-medium transition-colors ${
                  mode === m
                    ? 'bg-white text-emerald-700 shadow-sm dark:bg-slate-700 dark:text-emerald-300'
                    : 'text-slate-500 dark:text-slate-400'
                }`}
              >
                {m === 'blank' ? 'Leer' : 'Befüllt'}
              </button>
            ))}
          </div>

          <ul className="space-y-0.5">
            {FORMATS.map(({ format, label, icon: Icon }) => (
              <li key={format}>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => handleExport(format)}
                  disabled={busy}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {busyFormat === format
                    ? <Loader2 size={15} className="animate-spin text-emerald-500" />
                    : <Icon size={15} className="text-emerald-500" />}
                  {label}
                </button>
              </li>
            ))}
          </ul>

          {/* Abgesetzter Abschnitt: Diskussionsprotokoll */}
          <div className="my-2 border-t border-slate-200 dark:border-slate-700" />
          <div className="mb-1 flex items-center gap-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            <MessagesSquare size={12} /> Diskussionsprotokoll
          </div>
          <ul className="space-y-0.5">
            {DISCUSSION_FORMATS.map(({ format, label, icon: Icon }) => (
              <li key={format}>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => handleDiscussionExport(format)}
                  disabled={busy}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {busyDiscussion === format
                    ? <Loader2 size={15} className="animate-spin text-indigo-500" />
                    : <Icon size={15} className="text-indigo-500" />}
                  {label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
