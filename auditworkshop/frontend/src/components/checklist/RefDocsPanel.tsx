/**
 * flowworkshop · components/checklist/RefDocsPanel.tsx
 *
 * Referenz-Dokumente eines Knotens (Belegverweise): Liste anzeigen, neuen
 * Eintrag (Name, optional Pfad/Zitat) hinzufuegen (editor+) und loeschen.
 * Endpunkte: GET/POST /{id}/nodes/{nodeId}/refdocs, DELETE /{id}/refdocs/{id}.
 * Live-Aktualisierung via SSE-Events refdoc_added/refdoc_deleted (durch den
 * Inspector ueber das ``refresh``-Signal angestossen).
 */
import { useCallback, useEffect, useState } from 'react';
import { FileText, Plus, Trash2, Loader2, X } from 'lucide-react';
import {
  addNodeRefDoc, deleteNodeRefDoc, getNodeRefDocs, type NodeRefDoc,
} from '../../lib/api';

interface RefDocsPanelProps {
  templateId: string;
  nodeId: string;
  canEdit: boolean;
  /** Wechselt sich bei eingehenden refdoc-SSE-Events, um neu zu laden. */
  refreshSignal: number;
}

export default function RefDocsPanel({
  templateId, nodeId, canEdit, refreshSignal,
}: RefDocsPanelProps) {
  const [docs, setDocs] = useState<NodeRefDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ document_name: '', document_path: '', reference_text: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const rows = await getNodeRefDocs(templateId, nodeId);
      setDocs(rows);
    } catch {
      setError('Referenz-Dokumente konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, [templateId, nodeId]);

  useEffect(() => { void load(); }, [load, refreshSignal]);

  const submit = async () => {
    const name = form.document_name.trim();
    if (!name) return;
    setBusy(true);
    setError('');
    try {
      const created = await addNodeRefDoc(templateId, nodeId, {
        document_name: name,
        document_path: form.document_path.trim() || null,
        reference_text: form.reference_text.trim() || null,
      });
      setDocs((prev) => [...prev, created]);
      setForm({ document_name: '', document_path: '', reference_text: '' });
      setAdding(false);
    } catch {
      setError('Referenz-Dokument konnte nicht hinzugefügt werden.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (doc: NodeRefDoc) => {
    if (!canEdit) return;
    const snapshot = docs;
    setDocs((prev) => prev.filter((d) => d.id !== doc.id));
    try {
      await deleteNodeRefDoc(templateId, doc.id);
    } catch {
      setDocs(snapshot);
      setError('Referenz-Dokument konnte nicht gelöscht werden.');
    }
  };

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
          Referenz-Dokumente
        </span>
        {canEdit && !adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/30"
          >
            <Plus size={12} /> Hinzufügen
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-2 text-xs text-slate-400">
          <Loader2 size={13} className="animate-spin" /> Lädt…
        </div>
      ) : docs.length === 0 && !adding ? (
        <p className="py-1 text-xs italic text-slate-400 dark:text-slate-500">
          Noch keine Referenz-Dokumente hinterlegt.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {docs.map((d) => (
            <li
              key={d.id}
              className="group flex items-start gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-800/60"
            >
              <FileText size={13} className="mt-0.5 shrink-0 text-blue-500 dark:text-blue-400" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-slate-700 dark:text-slate-200">{d.document_name}</div>
                {d.document_path && (
                  <div className="truncate text-[11px] text-slate-400">{d.document_path}</div>
                )}
                {d.reference_text && (
                  <div className="mt-0.5 line-clamp-3 text-[11px] italic text-slate-500 dark:text-slate-400">
                    „{d.reference_text}"
                  </div>
                )}
              </div>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => remove(d)}
                  className="shrink-0 rounded p-1 text-slate-300 hover:bg-red-50 hover:text-red-600 dark:text-slate-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                  aria-label="Referenz-Dokument löschen"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {adding && (
        <div className="mt-2 space-y-1.5 rounded-lg border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-800/60">
          <input
            autoFocus
            value={form.document_name}
            onChange={(e) => setForm((f) => ({ ...f, document_name: e.target.value }))}
            placeholder="Name des Dokuments *"
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          />
          <input
            value={form.document_path}
            onChange={(e) => setForm((f) => ({ ...f, document_path: e.target.value }))}
            placeholder="Pfad / Fundstelle (optional)"
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          />
          <textarea
            value={form.reference_text}
            onChange={(e) => setForm((f) => ({ ...f, reference_text: e.target.value }))}
            placeholder="Zitat / Bezug (optional)"
            rows={2}
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          />
          <div className="flex items-center justify-end gap-1.5">
            <button
              type="button"
              onClick={() => { setAdding(false); setForm({ document_name: '', document_path: '', reference_text: '' }); }}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700"
            >
              <X size={12} /> Abbrechen
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={busy || !form.document_name.trim()}
              className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-blue-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Speichern
            </button>
          </div>
        </div>
      )}

      {error && <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}
