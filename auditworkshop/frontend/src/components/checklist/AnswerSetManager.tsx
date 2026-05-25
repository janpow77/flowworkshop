/**
 * flowworkshop · components/checklist/AnswerSetManager.tsx
 *
 * Modal zur Verwaltung der Antwortsets: checklistenspezifische Sets und die
 * globale Bibliothek anlegen/bearbeiten/loeschen samt Optionen (name, sort_order,
 * is_standard, is_entfaellt, value_number, threshold, bemerkung).
 */
import { useEffect, useState } from 'react';
import {
  X, Plus, Trash2, Loader2, AlertCircle, Library, ListChecks, ChevronDown, ChevronRight,
} from 'lucide-react';
import {
  addAnswerOption, createGlobalAnswerSet, createTemplateAnswerSet,
  deleteAnswerOption, deleteAnswerSet, listGlobalAnswerSets, listTemplateAnswerSets,
  updateAnswerOption,
  type AnswerOptionPayload, type ChecklistAnswerOption, type ChecklistAnswerSet,
} from '../../lib/api';

interface AnswerSetManagerProps {
  templateId: string;
  canEdit: boolean;
  onClose: () => void;
  onChanged: (sets: ChecklistAnswerSet[]) => void;
}

export default function AnswerSetManager({ templateId, canEdit, onClose, onChanged }: AnswerSetManagerProps) {
  const [templateSets, setTemplateSets] = useState<ChecklistAnswerSet[]>([]);
  const [globalSets, setGlobalSets] = useState<ChecklistAnswerSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState('');
  const [newScope, setNewScope] = useState<'template' | 'global'>('template');

  const reload = async () => {
    try {
      const [tpl, glob] = await Promise.all([
        listTemplateAnswerSets(templateId),
        listGlobalAnswerSets(),
      ]);
      setTemplateSets(tpl);
      setGlobalSets(glob);
      onChanged([...tpl, ...glob]);
      setError('');
    } catch {
      setError('Antwortsets konnten nicht geladen werden.');
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

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleCreateSet = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    setError('');
    try {
      if (newScope === 'global') {
        await createGlobalAnswerSet({ name: newName.trim() });
      } else {
        await createTemplateAnswerSet(templateId, { name: newName.trim() });
      }
      setNewName('');
      await reload();
    } catch {
      setError('Antwortset konnte nicht angelegt werden.');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteSet = async (set: ChecklistAnswerSet) => {
    if (!confirm(`Antwortset „${set.name}" samt Optionen löschen?`)) return;
    setBusy(true);
    try {
      await deleteAnswerSet(set.id);
      await reload();
    } catch {
      setError('Antwortset konnte nicht gelöscht werden (evtl. noch zugewiesen).');
    } finally {
      setBusy(false);
    }
  };

  const handleAddOption = async (setId: string, name: string) => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await addAnswerOption(setId, { name: name.trim() });
      await reload();
    } catch {
      setError('Option konnte nicht hinzugefügt werden.');
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateOption = async (optionId: string, patch: Partial<AnswerOptionPayload>) => {
    setBusy(true);
    try {
      await updateAnswerOption(optionId, patch);
      await reload();
    } catch {
      setError('Option konnte nicht geändert werden.');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteOption = async (optionId: string) => {
    setBusy(true);
    try {
      await deleteAnswerOption(optionId);
      await reload();
    } catch {
      setError('Option konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-xl dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-slate-100">
            <ListChecks size={18} className="text-emerald-500" /> Antwortsets verwalten
          </h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Schließen">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
              <AlertCircle size={15} /> {error}
            </div>
          )}

          {canEdit && (
            <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/50">
              <div className="flex-1 min-w-[160px]">
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-400" htmlFor="as-new-name">Neues Antwortset</label>
                <input
                  id="as-new-name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Name"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                />
              </div>
              <select
                value={newScope}
                onChange={(e) => setNewScope(e.target.value as 'template' | 'global')}
                aria-label="Geltungsbereich"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                <option value="template">Diese Checkliste</option>
                <option value="global">Globale Bibliothek</option>
              </select>
              <button
                type="button"
                onClick={handleCreateSet}
                disabled={busy || !newName.trim()}
                className="flex items-center gap-1.5 rounded-full bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
              >
                <Plus size={15} /> Anlegen
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 py-8 text-sm text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Lädt…
            </div>
          ) : (
            <>
              <SetGroup
                title="Antwortsets dieser Checkliste"
                icon={<ListChecks size={14} className="text-emerald-500" />}
                sets={templateSets}
                emptyHint="Noch keine checklistenspezifischen Antwortsets."
                {...{ expanded, toggle, busy, canEdit, handleDeleteSet, handleAddOption, handleUpdateOption, handleDeleteOption }}
              />
              <SetGroup
                title="Globale Bibliothek"
                icon={<Library size={14} className="text-slate-400" />}
                sets={globalSets}
                emptyHint="Die globale Bibliothek ist leer."
                {...{ expanded, toggle, busy, canEdit, handleDeleteSet, handleAddOption, handleUpdateOption, handleDeleteOption }}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

interface SetGroupProps {
  title: string;
  icon: React.ReactNode;
  sets: ChecklistAnswerSet[];
  emptyHint: string;
  expanded: Set<string>;
  toggle: (id: string) => void;
  busy: boolean;
  canEdit: boolean;
  handleDeleteSet: (set: ChecklistAnswerSet) => void;
  handleAddOption: (setId: string, name: string) => void;
  handleUpdateOption: (optionId: string, patch: Partial<AnswerOptionPayload>) => void;
  handleDeleteOption: (optionId: string) => void;
}

function SetGroup(props: SetGroupProps) {
  const { title, icon, sets, emptyHint, expanded, toggle, busy, canEdit } = props;
  return (
    <section>
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {icon} {title}
      </h3>
      {sets.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-200 px-3 py-3 text-sm text-slate-400 dark:border-slate-700">{emptyHint}</p>
      ) : (
        <ul className="space-y-2">
          {sets.map((set) => (
            <li key={set.id} className="rounded-xl border border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2 px-3 py-2">
                <button type="button" onClick={() => toggle(set.id)} className="rounded p-0.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200" aria-label="Optionen ein-/ausklappen">
                  {expanded.has(set.id) ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                </button>
                <span className="flex-1 text-sm font-medium text-slate-700 dark:text-slate-200">{set.name}</span>
                <span className="text-xs text-slate-400">{set.options.length} Optionen</span>
                {canEdit && (
                  <button type="button" onClick={() => props.handleDeleteSet(set)} disabled={busy} className="rounded p-1 text-slate-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/40" aria-label="Antwortset löschen">
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
              {expanded.has(set.id) && (
                <OptionList set={set} {...props} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OptionList(props: SetGroupProps & { set: ChecklistAnswerSet }) {
  const { set, busy, canEdit } = props;
  const [optName, setOptName] = useState('');
  return (
    <div className="border-t border-slate-100 px-3 py-2 dark:border-slate-800">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-slate-400">
            <th className="py-1 font-medium">Name</th>
            <th className="py-1 font-medium">Std.</th>
            <th className="py-1 font-medium">Entf.</th>
            <th className="py-1 font-medium">Wert</th>
            <th className="py-1 font-medium">Schwelle</th>
            <th className="py-1 font-medium">Bemerkung</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {set.options.map((opt) => (
            <OptionRow key={opt.id} opt={opt} {...props} />
          ))}
        </tbody>
      </table>
      {canEdit && (
        <div className="mt-2 flex items-center gap-2">
          <input
            value={optName}
            onChange={(e) => setOptName(e.target.value)}
            placeholder="Neue Option…"
            className="flex-1 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            onKeyDown={(e) => {
              if (e.key === 'Enter') { props.handleAddOption(set.id, optName); setOptName(''); }
            }}
          />
          <button
            type="button"
            onClick={() => { props.handleAddOption(set.id, optName); setOptName(''); }}
            disabled={busy || !optName.trim()}
            className="flex items-center gap-1 rounded-full bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:bg-slate-300 dark:bg-emerald-600 dark:hover:bg-emerald-500 dark:disabled:bg-slate-700"
          >
            <Plus size={13} /> Option
          </button>
        </div>
      )}
    </div>
  );
}

function OptionRow({
  opt, canEdit, busy, handleUpdateOption, handleDeleteOption,
}: SetGroupProps & { opt: ChecklistAnswerOption }) {
  const numCls = 'w-16 rounded border border-slate-300 bg-white px-1.5 py-1 text-xs dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 disabled:opacity-60';
  return (
    <tr className="border-t border-slate-100 dark:border-slate-800">
      <td className="py-1 pr-2">
        <input
          defaultValue={opt.name}
          disabled={!canEdit || busy}
          className="w-full rounded border border-transparent bg-transparent px-1 py-1 text-slate-700 hover:border-slate-300 focus:border-emerald-500 focus:outline-none dark:text-slate-200 dark:hover:border-slate-600"
          onBlur={(e) => { if (e.target.value.trim() && e.target.value !== opt.name) handleUpdateOption(opt.id, { name: e.target.value.trim() }); }}
        />
      </td>
      <td className="py-1 pr-2">
        <input type="checkbox" checked={opt.is_standard} disabled={!canEdit || busy} onChange={(e) => handleUpdateOption(opt.id, { is_standard: e.target.checked })} />
      </td>
      <td className="py-1 pr-2">
        <input type="checkbox" checked={opt.is_entfaellt} disabled={!canEdit || busy} onChange={(e) => handleUpdateOption(opt.id, { is_entfaellt: e.target.checked })} />
      </td>
      <td className="py-1 pr-2">
        <input
          type="number" step="any" defaultValue={opt.value_number ?? ''} disabled={!canEdit || busy} className={numCls}
          onBlur={(e) => { const v = e.target.value === '' ? null : Number(e.target.value); if (v !== (opt.value_number ?? null)) handleUpdateOption(opt.id, { value_number: v }); }}
        />
      </td>
      <td className="py-1 pr-2">
        <input
          type="number" step="any" defaultValue={opt.threshold ?? ''} disabled={!canEdit || busy} className={numCls}
          onBlur={(e) => { const v = e.target.value === '' ? null : Number(e.target.value); if (v !== (opt.threshold ?? null)) handleUpdateOption(opt.id, { threshold: v }); }}
        />
      </td>
      <td className="py-1 pr-2">
        <input
          defaultValue={opt.bemerkung ?? ''} disabled={!canEdit || busy}
          className="w-full rounded border border-transparent bg-transparent px-1 py-1 text-slate-600 hover:border-slate-300 focus:border-emerald-500 focus:outline-none dark:text-slate-300 dark:hover:border-slate-600"
          onBlur={(e) => { const v = e.target.value.trim() || null; if (v !== (opt.bemerkung ?? null)) handleUpdateOption(opt.id, { bemerkung: v }); }}
        />
      </td>
      <td className="py-1 text-right">
        {canEdit && (
          <button type="button" onClick={() => handleDeleteOption(opt.id)} disabled={busy} className="rounded p-1 text-slate-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/40" aria-label="Option löschen">
            <Trash2 size={13} />
          </button>
        )}
      </td>
    </tr>
  );
}
