/**
 * flowworkshop · components/checklist/NodeInspector.tsx
 *
 * Editor-Panel fuer einen ausgewaehlten Knoten. Editoren bearbeiten alle Felder;
 * Kommentatoren duerfen ausschliesslich public_remark pflegen; Leser sehen alles
 * schreibgeschuetzt. Speichern via PUT (update_node).
 */
import { useEffect, useState } from 'react';
import { Save, X, Loader2, AlertCircle, Lock } from 'lucide-react';
import type {
  ChecklistAnswerSet, ChecklistNodeTree, ChecklistTemplateCategory,
  CollabLockConflict, NodeType, NodeUpdatePayload, TemplateAnswerType,
} from '../../lib/api';
import {
  ANSWER_TYPE_LABEL, ANSWER_TYPE_ORDER, EINGABETYP_OPTIONS,
  NODE_TYPE_META, NODE_TYPE_ORDER,
} from './treeMeta';

interface NodeInspectorProps {
  node: ChecklistNodeTree;
  answerSets: ChecklistAnswerSet[];
  categories: ChecklistTemplateCategory[];
  canEdit: boolean;
  canComment: boolean;
  onSave: (nodeId: string, patch: NodeUpdatePayload) => Promise<void>;
  onClose: () => void;
  /**
   * Belegt, wenn der Knoten gerade von einer ANDEREN Person bearbeitet wird
   * (Lock konnte nicht erworben werden). Dann ist das Formular schreibgeschuetzt
   * und das Speichern blockiert.
   */
  lockedByOther?: CollabLockConflict | null;
  /** True, solange der Lock erworben/geprueft wird (kurzes Sperren des Speichern-Buttons). */
  lockPending?: boolean;
}

interface FormState {
  title: string;
  node_type: NodeType;
  answer_type: TemplateAnswerType | '';
  eingabetyp: number | '';
  answer_set_id: string;
  category_id: string;
  legal_reference: string;
  relevant_documents: string;
  public_remark: string;
  ja_label: string;
  nein_label: string;
}

function toForm(node: ChecklistNodeTree): FormState {
  const docs = Array.isArray(node.relevant_documents_json)
    ? (node.relevant_documents_json as unknown[]).map((d) => String(d)).join('\n')
    : '';
  return {
    title: node.title ?? '',
    node_type: node.node_type,
    answer_type: node.answer_type ?? '',
    eingabetyp: node.eingabetyp ?? '',
    answer_set_id: node.answer_set_id ?? '',
    category_id: node.category_id ?? '',
    legal_reference: node.legal_reference ?? '',
    relevant_documents: docs,
    public_remark: node.public_remark ?? '',
    ja_label: node.ja_label ?? '',
    nein_label: node.nein_label ?? '',
  };
}

const fieldCls =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:bg-slate-50 disabled:text-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:disabled:bg-slate-900';
const labelCls =
  'mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500';

export default function NodeInspector(props: NodeInspectorProps) {
  const {
    node, answerSets, categories, canEdit, canComment, onSave, onClose,
    lockedByOther, lockPending,
  } = props;
  const [form, setForm] = useState<FormState>(() => toForm(node));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setForm(toForm(node));
    setDirty(false);
    setError('');
  }, [node]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  };

  // Lock eines anderen Nutzers macht das Formular vollstaendig schreibgeschuetzt.
  const locked = !!lockedByOther;
  // Kommentator darf nur die oeffentliche Bemerkung aendern.
  const remarkOnly = canComment && !canEdit && !locked;
  const readOnly = (!canEdit && !canComment) || locked;
  // Effektives „darf Strukturfelder bearbeiten" — durch Lock blockierbar.
  const fieldsEditable = canEdit && !locked;
  const isDecision = form.node_type === 'DECISION';

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      let patch: NodeUpdatePayload;
      if (remarkOnly) {
        patch = { public_remark: form.public_remark || null };
      } else {
        const docs = form.relevant_documents
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean);
        patch = {
          title: form.title || null,
          node_type: form.node_type,
          answer_type: form.answer_type || null,
          eingabetyp: form.eingabetyp === '' ? null : form.eingabetyp,
          answer_set_id: form.answer_set_id || null,
          category_id: form.category_id || null,
          legal_reference: form.legal_reference || null,
          relevant_documents_json: docs.length ? docs : null,
          public_remark: form.public_remark || null,
          ja_label: isDecision ? (form.ja_label || null) : null,
          nein_label: isDecision ? (form.nein_label || null) : null,
        };
      }
      await onSave(node.id, patch);
      setDirty(false);
    } catch (e) {
      const msg = String(e);
      setError(
        msg.includes('403')
          ? 'Keine Berechtigung — Ihre Rolle erlaubt diese Änderung nicht.'
          : 'Speichern fehlgeschlagen. Bitte erneut versuchen.',
      );
    } finally {
      setSaving(false);
    }
  };

  const meta = NODE_TYPE_META[form.node_type] ?? NODE_TYPE_META.QUESTION;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <meta.icon size={16} className={meta.accent} />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Knoten bearbeiten</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
          aria-label="Schließen"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {locked && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
            <Lock size={14} />
            Wird gerade von {lockedByOther?.locked_by_name || 'einer anderen Person'} bearbeitet — schreibgeschützt.
          </div>
        )}
        {readOnly && !locked && (
          <div className="flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <AlertCircle size={14} /> Nur-Lese-Ansicht — Ihre Rolle erlaubt keine Änderungen.
          </div>
        )}
        {remarkOnly && (
          <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">
            <AlertCircle size={14} /> Als Kommentator können Sie nur die öffentliche Bemerkung bearbeiten.
          </div>
        )}

        <div>
          <label className={labelCls} htmlFor="ni-title">Titel</label>
          <textarea
            id="ni-title"
            rows={2}
            className={fieldCls}
            value={form.title}
            disabled={!fieldsEditable}
            onChange={(e) => set('title', e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls} htmlFor="ni-type">Knotentyp</label>
            <select
              id="ni-type"
              className={fieldCls}
              value={form.node_type}
              disabled={!fieldsEditable}
              onChange={(e) => set('node_type', e.target.value as NodeType)}
            >
              {NODE_TYPE_ORDER.map((t) => (
                <option key={t} value={t}>{NODE_TYPE_META[t].label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ni-answertype">Antworttyp</label>
            <select
              id="ni-answertype"
              className={fieldCls}
              value={form.answer_type}
              disabled={!fieldsEditable}
              onChange={(e) => set('answer_type', e.target.value as TemplateAnswerType | '')}
            >
              <option value="">—</option>
              {ANSWER_TYPE_ORDER.map((t) => (
                <option key={t} value={t}>{ANSWER_TYPE_LABEL[t]}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls} htmlFor="ni-eingabetyp">Eingabetyp</label>
            <select
              id="ni-eingabetyp"
              className={fieldCls}
              value={form.eingabetyp}
              disabled={!fieldsEditable}
              onChange={(e) => set('eingabetyp', e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">—</option>
              {EINGABETYP_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="ni-answerset">Antwortset</label>
            <select
              id="ni-answerset"
              className={fieldCls}
              value={form.answer_set_id}
              disabled={!fieldsEditable}
              onChange={(e) => set('answer_set_id', e.target.value)}
            >
              <option value="">— keines —</option>
              {answerSets.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}{s.template_id ? '' : ' (Bibliothek)'}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className={labelCls} htmlFor="ni-category">Kategorie</label>
          <select
            id="ni-category"
            className={fieldCls}
            value={form.category_id}
            disabled={!fieldsEditable}
            onChange={(e) => set('category_id', e.target.value)}
          >
            <option value="">— keine —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        {isDecision && (
          <div className="grid grid-cols-1 gap-3 rounded-lg border border-violet-200 bg-violet-50/50 p-3 dark:border-violet-900/50 dark:bg-violet-950/20">
            <div>
              <label className={labelCls} htmlFor="ni-ja">Aussage JA-Zweig</label>
              <textarea
                id="ni-ja"
                rows={2}
                className={fieldCls}
                value={form.ja_label}
                disabled={!fieldsEditable}
                onChange={(e) => set('ja_label', e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="ni-nein">Aussage NEIN-Zweig</label>
              <textarea
                id="ni-nein"
                rows={2}
                className={fieldCls}
                value={form.nein_label}
                disabled={!fieldsEditable}
                onChange={(e) => set('nein_label', e.target.value)}
              />
            </div>
          </div>
        )}

        <div>
          <label className={labelCls} htmlFor="ni-legal">KOM-Rechtsgrundlage</label>
          <textarea
            id="ni-legal"
            rows={2}
            className={fieldCls}
            value={form.legal_reference}
            disabled={!fieldsEditable}
            placeholder="z. B. Art. 74 Abs. 2 lit. a VO (EU) 2021/1060"
            onChange={(e) => set('legal_reference', e.target.value)}
          />
        </div>

        <div>
          <label className={labelCls} htmlFor="ni-docs">Relevante Belege (je Zeile ein Eintrag)</label>
          <textarea
            id="ni-docs"
            rows={3}
            className={fieldCls}
            value={form.relevant_documents}
            disabled={!fieldsEditable}
            placeholder={'Förderbescheid\nVerwendungsnachweis\n…'}
            onChange={(e) => set('relevant_documents', e.target.value)}
          />
        </div>

        <div>
          <label className={labelCls} htmlFor="ni-remark">Öffentliche Bemerkung</label>
          <textarea
            id="ni-remark"
            rows={3}
            className={fieldCls}
            value={form.public_remark}
            disabled={readOnly}
            onChange={(e) => set('public_remark', e.target.value)}
          />
        </div>
      </div>

      {!readOnly && (
        <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
          {error && (
            <div className="mb-2 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-400">
              <AlertCircle size={14} /> {error}
            </div>
          )}
          {lockPending && (
            <div className="mb-2 flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              <Loader2 size={14} className="animate-spin" /> Bearbeitungssperre wird gesetzt…
            </div>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !dirty || lockPending}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            {saving ? 'Speichern…' : 'Speichern'}
          </button>
        </div>
      )}
    </div>
  );
}
