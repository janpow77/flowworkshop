/**
 * flowworkshop · components/checklist/CategoryManager.tsx
 *
 * Modal zur Verwaltung der Fragenkategorien einer Checkliste (anlegen,
 * umbenennen, loeschen). Zuweisung an einen Knoten erfolgt im NodeInspector.
 */
import { useEffect, useState } from 'react';
import { X, Plus, Trash2, Loader2, AlertCircle, Tags } from 'lucide-react';
import {
  createChecklistCategory, deleteChecklistCategory, listChecklistCategories,
  updateChecklistCategory, type ChecklistTemplateCategory,
} from '../../lib/api';

interface CategoryManagerProps {
  templateId: string;
  canEdit: boolean;
  onClose: () => void;
  onChanged: (cats: ChecklistTemplateCategory[]) => void;
}

export default function CategoryManager({ templateId, canEdit, onClose, onChanged }: CategoryManagerProps) {
  const [cats, setCats] = useState<ChecklistTemplateCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    try {
      const list = await listChecklistCategories(templateId);
      setCats(list);
      onChanged(list);
      setError('');
    } catch {
      setError('Kategorien konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      await createChecklistCategory(templateId, { name: newName.trim() });
      setNewName('');
      await reload();
    } catch {
      setError('Kategorie konnte nicht angelegt werden.');
    } finally {
      setBusy(false);
    }
  };

  const handleRename = async (cat: ChecklistTemplateCategory, name: string) => {
    if (!name.trim() || name === cat.name) return;
    setBusy(true);
    try {
      await updateChecklistCategory(templateId, cat.id, { name: name.trim() });
      await reload();
    } catch {
      setError('Kategorie konnte nicht umbenannt werden.');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (cat: ChecklistTemplateCategory) => {
    if (!confirm(`Kategorie „${cat.name}" löschen? Zugeordnete Knoten behalten ihren Inhalt.`)) return;
    setBusy(true);
    try {
      await deleteChecklistCategory(templateId, cat.id);
      await reload();
    } catch {
      setError('Kategorie konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[80vh] w-full max-w-md flex-col rounded-2xl bg-white shadow-xl dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-slate-100">
            <Tags size={18} className="text-emerald-500" /> Kategorien verwalten
          </h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Schließen">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
              <AlertCircle size={15} /> {error}
            </div>
          )}

          {canEdit && (
            <div className="flex items-end gap-2">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); }}
                placeholder="Neue Kategorie…"
                className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              />
              <button
                type="button"
                onClick={handleCreate}
                disabled={busy || !newName.trim()}
                className="flex items-center gap-1.5 rounded-full bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
              >
                <Plus size={15} /> Anlegen
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Lädt…
            </div>
          ) : cats.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 px-3 py-4 text-center text-sm text-slate-400 dark:border-slate-700">
              Noch keine Kategorien angelegt.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {cats.map((cat) => (
                <li key={cat.id} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
                  <input
                    defaultValue={cat.name}
                    disabled={!canEdit || busy}
                    className="flex-1 rounded border border-transparent bg-transparent px-1 py-1 text-sm text-slate-700 hover:border-slate-300 focus:border-emerald-500 focus:outline-none dark:text-slate-200 dark:hover:border-slate-600"
                    onBlur={(e) => handleRename(cat, e.target.value)}
                  />
                  {canEdit && (
                    <button type="button" onClick={() => handleDelete(cat)} disabled={busy} className="rounded p-1 text-slate-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/40" aria-label="Kategorie löschen">
                      <Trash2 size={14} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
