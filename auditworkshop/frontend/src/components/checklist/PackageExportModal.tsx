/**
 * flowworkshop · components/checklist/PackageExportModal.tsx
 *
 * Auswahlmenue fuer den Export einer Checkliste als vollstaendiges Paket
 * (.checklist.json). Kernstruktur (Knoten + Antwortsets + Kategorien) ist immer
 * enthalten; waehlbar zusaetzlich Diskussionen, Knoten-Historie und Versions-
 * Snapshots. Gespiegelt zum audit_designer-Export-Dialog.
 */
import { useState } from 'react';
import { Loader2, Package, X } from 'lucide-react';
import { exportChecklistPackage } from '../../lib/api';

interface PackageExportModalProps {
  templateId: string;
  open: boolean;
  onClose: () => void;
  onError?: (msg: string) => void;
}

export default function PackageExportModal({
  templateId, open, onClose, onError,
}: PackageExportModalProps) {
  const [discussions, setDiscussions] = useState(true);
  const [history, setHistory] = useState(false);
  const [versions, setVersions] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const handleExport = async () => {
    setBusy(true);
    try {
      await exportChecklistPackage(templateId, { discussions, history, versions });
      onClose();
    } catch {
      onError?.('Paket-Export fehlgeschlagen — bitte erneut versuchen.');
    } finally {
      setBusy(false);
    }
  };

  const optionCls =
    'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800 cursor-pointer';

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5 dark:border-slate-700">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-white">
            <Package size={18} className="text-emerald-600 dark:text-emerald-400" />
            Checkliste als Paket exportieren
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
            aria-label="Schließen"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div>
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Optionen
            </h3>
            <div className="space-y-1">
              <label className={optionCls}>
                <input
                  type="checkbox"
                  checked={discussions}
                  onChange={(e) => setDiscussions(e.target.checked)}
                  className="rounded text-emerald-600 focus:ring-emerald-500"
                />
                <span>Diskussionen (Knoten-Kommentare)</span>
              </label>
              <label className={optionCls}>
                <input
                  type="checkbox"
                  checked={history}
                  onChange={(e) => setHistory(e.target.checked)}
                  className="rounded text-emerald-600 focus:ring-emerald-500"
                />
                <span>Knoten-Historie</span>
              </label>
              <label className={optionCls}>
                <input
                  type="checkbox"
                  checked={versions}
                  onChange={(e) => setVersions(e.target.checked)}
                  className="rounded text-emerald-600 focus:ring-emerald-500"
                />
                <span>Versions-Snapshots</span>
              </label>
              <div className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-400 dark:text-slate-500">
                <input type="checkbox" checked disabled className="rounded" />
                <span>Antwortsets &amp; Kategorien <span className="text-xs italic">(immer enthalten)</span></span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3.5 dark:border-slate-700">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg px-3.5 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={handleExport}
            disabled={busy}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Package size={15} />}
            Exportieren
          </button>
        </div>
      </div>
    </div>
  );
}
