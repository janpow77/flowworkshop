/**
 * flowworkshop · components/checklist/PackageImportDialog.tsx
 *
 * Import einer Checkliste aus einem vollstaendigen Paket (.checklist.json) — mit
 * Validierungs-Vorschau und „existiert schon?"-Pruefung. Akzeptiert auch
 * audit_designer-Pakete (Cross-Repo, Adapter im Backend). Gespiegelt zum
 * audit_designer-Dashboard-Import.
 */
import { useRef, useState } from 'react';
import { AlertTriangle, FileWarning, Loader2, Package, Upload, X } from 'lucide-react';
import {
  validateChecklistPackage,
  importChecklistPackage,
  type ChecklistPackagePreview,
  type ChecklistImportResult,
} from '../../lib/api';

interface PackageImportDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: (result: ChecklistImportResult) => void;
}

function fmtDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function PackageImportDialog({ open, onClose, onImported }: PackageImportDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ChecklistPackagePreview | null>(null);
  const [title, setTitle] = useState('');
  const [validating, setValidating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const reset = () => {
    setFile(null); setPreview(null); setTitle(''); setError('');
    setValidating(false); setImporting(false);
  };
  const close = () => { reset(); onClose(); };

  const onFile = async (f: File | null) => {
    if (!f) return;
    setFile(f); setError(''); setPreview(null); setValidating(true);
    try {
      const p = await validateChecklistPackage(f);
      setPreview(p);
      setTitle(p.template?.title || f.name.replace(/\.(checklist\.)?json$/i, ''));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Validierung fehlgeschlagen.');
    } finally {
      setValidating(false);
    }
  };

  const doImport = async () => {
    if (!file || !preview?.valid) return;
    setImporting(true); setError('');
    try {
      const res = await importChecklistPackage(file, { title: title.trim() || undefined });
      onImported(res);
      reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen.');
    } finally {
      setImporting(false);
    }
  };

  const c = preview?.counts || {};
  const exists = preview?.exists;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}
    >
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5 dark:border-slate-700">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 dark:text-white">
            <Package size={18} className="text-emerald-600 dark:text-emerald-400" />
            Checkliste importieren
          </h2>
          <button type="button" onClick={close} aria-label="Schließen"
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <input
            ref={inputRef}
            type="file"
            accept=".json,.checklist.json"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0] ?? null)}
          />

          {!file && (
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-slate-300 py-10 text-slate-500 hover:border-emerald-400 hover:text-emerald-600 dark:border-slate-600 dark:text-slate-400"
            >
              <Upload size={28} />
              <span className="text-sm font-medium">Paketdatei (.checklist.json) wählen</span>
              <span className="text-xs">akzeptiert auch audit_designer-Pakete</span>
            </button>
          )}

          {file && (
            <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800">
              <span className="truncate text-slate-700 dark:text-slate-200">{file.name}</span>
              <button type="button" onClick={() => inputRef.current?.click()}
                className="shrink-0 text-xs text-emerald-600 hover:underline dark:text-emerald-400">
                ändern
              </button>
            </div>
          )}

          {validating && (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Datei wird geprüft…
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}

          {preview && (
            <>
              {/* Existenz-Warnung */}
              {exists && exists.by_name.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm dark:border-amber-800 dark:bg-amber-950/30">
                  <div className="flex items-center gap-2 font-medium text-amber-800 dark:text-amber-300">
                    <FileWarning size={16} />
                    Eine Checkliste mit diesem Titel existiert bereits
                    {exists.identical && <span className="rounded bg-amber-200 px-1.5 py-0.5 text-xs text-amber-900 dark:bg-amber-800 dark:text-amber-100">inhaltlich identisch</span>}
                  </div>
                  <ul className="mt-1 list-inside list-disc text-amber-700 dark:text-amber-300/90">
                    {exists.by_name.map((e) => (
                      <li key={e.id}>{e.title} <span className="text-xs">(geändert {fmtDate(e.updated_at)})</span></li>
                    ))}
                  </ul>
                  <p className="mt-1 text-xs text-amber-700 dark:text-amber-300/80">
                    Es wird eine <strong>neue</strong> Checkliste angelegt. Bei Bedarf unten umbenennen.
                  </p>
                </div>
              )}

              {/* Kennzahlen */}
              <div className="grid grid-cols-3 gap-2 text-center">
                {([
                  ['Knoten', c.nodes], ['Fragen', c.questions], ['Entscheidungen', c.decisions],
                  ['Antwortsets', c.answer_sets], ['Diskussionen', c.discussions], ['Historie', c.history],
                ] as Array<[string, number | undefined]>).map(([label, val]) => (
                  <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 dark:border-slate-700 dark:bg-slate-800/50">
                    <div className="text-base font-bold text-slate-900 dark:text-white">{val ?? 0}</div>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400">{label}</div>
                  </div>
                ))}
              </div>

              {/* Antwortsets */}
              {preview.answer_sets && preview.answer_sets.length > 0 && (
                <div>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Antwortsets</h4>
                  <ul className="space-y-1 text-sm">
                    {preview.answer_sets.map((a, i) => (
                      <li key={i} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-1.5 dark:bg-slate-800">
                        <span className="truncate text-slate-700 dark:text-slate-200">{a.name} <span className="text-xs text-slate-400">({a.option_count})</span></span>
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${a.exists_by_name ? 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'}`}>
                          {a.exists_by_name ? 'wird wiederverwendet' : 'wird neu angelegt'}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Fehler / Warnungen */}
              {preview.errors.length > 0 && (
                <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
                  <div className="font-medium">Import nicht möglich</div>
                  <ul className="list-inside list-disc">{preview.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
                </div>
              )}
              {preview.warnings.length > 0 && (
                <ul className="list-inside list-disc rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
                  {preview.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}

              {/* Titel */}
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Titel der neuen Checkliste</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                />
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3.5 dark:border-slate-700">
          <button type="button" onClick={close} disabled={importing}
            className="rounded-lg px-3.5 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-300 dark:hover:bg-slate-800">
            Abbrechen
          </button>
          <button
            type="button"
            onClick={doImport}
            disabled={!preview?.valid || importing || validating}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            {importing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
            Importieren
          </button>
        </div>
      </div>
    </div>
  );
}
