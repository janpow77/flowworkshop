/**
 * flowworkshop · components/checklist/NodeInspector.tsx
 *
 * Zwei-Zonen-Inspector fuer einen ausgewaehlten Knoten — im audit_designer-Stil,
 * Workshop-Farbwelt Blau (primary).
 *
 *   • Zone „Bericht" (hell): fachliche Felder — Titel/Fragetext, Antworttyp,
 *     Eingabetyp, Antwortset, Kategorie, Rechtsgrundlage, Belege, Bemerkung,
 *     JA/NEIN-Labels (bei DECISION).
 *   • Zone „Team (intern)" (gelblicher Tint): Workflow-Status, Team-Diskussion
 *     und Referenz-Dokumente.
 *
 * AUTO-SAVE: Die Bericht-Felder werden mit Debounce (~1,7 s) automatisch via PUT
 * gespeichert. Ein dezenter Indikator zeigt „speichere… / gespeichert / Fehler".
 * Beim Knotenwechsel/Unmount wird ein ausstehender Speichervorgang sofort
 * geflusht (kein Datenverlust). Kommentatoren duerfen ausschliesslich die
 * oeffentliche Bemerkung pflegen; Leser sehen alles schreibgeschuetzt.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  X, Loader2, AlertCircle, Lock, Check, CloudOff, FileText, Users,
} from 'lucide-react';
import type {
  ChecklistAnswerSet, ChecklistNodeTree, ChecklistTemplateCategory,
  CollabLockConflict, NodeStatus, NodeType, NodeUpdatePayload, TemplateAnswerType,
} from '../../lib/api';
import {
  ANSWER_TYPE_LABEL, ANSWER_TYPE_ORDER, EINGABETYP_OPTIONS,
  NODE_TYPE_META, NODE_TYPE_ORDER,
} from './treeMeta';
import StatusButtons from './StatusButtons';
import NodeDiscussion from './NodeDiscussion';
import RefDocsPanel from './RefDocsPanel';

interface NodeInspectorProps {
  templateId: string;
  node: ChecklistNodeTree;
  answerSets: ChecklistAnswerSet[];
  categories: ChecklistTemplateCategory[];
  canEdit: boolean;
  canComment: boolean;
  /** Eigene Nutzerkennung — fuer Edit/Delete eigener Diskussionsbeitraege. */
  ownUserId: string | null;
  onSave: (nodeId: string, patch: NodeUpdatePayload) => Promise<void>;
  onClose: () => void;
  /** Optimistisches Status-Update im Baum (fuer den Status-Punkt). */
  onStatusChanged: (nodeId: string, status: NodeStatus) => void;
  /** Live-Signal: wechselt bei Diskussions-SSE-Events fuer DIESEN Knoten. */
  discussionSignal: number;
  /** Live-Signal: wechselt bei Referenz-SSE-Events fuer DIESEN Knoten. */
  refdocSignal: number;
  /**
   * Belegt, wenn der Knoten gerade von einer ANDEREN Person bearbeitet wird
   * (Lock konnte nicht erworben werden). Dann ist das Formular schreibgeschuetzt.
   */
  lockedByOther?: CollabLockConflict | null;
  /** True, solange der Lock erworben/geprueft wird. */
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

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

// Debounce-Verzoegerung fuer das automatische Speichern (1,7 s).
const AUTOSAVE_MS = 1700;

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
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:bg-slate-50 disabled:text-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:disabled:bg-slate-900';
const labelCls =
  'mb-1 block text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500';

export default function NodeInspector(props: NodeInspectorProps) {
  const {
    templateId, node, answerSets, categories, canEdit, canComment, ownUserId,
    onSave, onClose, onStatusChanged, discussionSignal, refdocSignal,
    lockedByOther, lockPending,
  } = props;

  const [form, setForm] = useState<FormState>(() => toForm(node));
  const [saveState, setSaveState] = useState<SaveState>('idle');

  // Lock eines anderen Nutzers macht das Formular vollstaendig schreibgeschuetzt.
  const locked = !!lockedByOther;
  const remarkOnly = canComment && !canEdit && !locked;
  const readOnly = (!canEdit && !canComment) || locked;
  const fieldsEditable = canEdit && !locked;
  const isDecision = form.node_type === 'DECISION';

  // Referenzen fuer Auto-Save-Flush bei Knotenwechsel/Unmount.
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const formRef = useRef(form);
  formRef.current = form;
  const dirtyRef = useRef(false);
  const nodeIdRef = useRef(node.id);

  /** Baut den PUT-Payload aus dem aktuellen Formularzustand. */
  const buildPatch = useCallback((f: FormState): NodeUpdatePayload => {
    if (remarkOnly) {
      return { public_remark: f.public_remark || null };
    }
    const docs = f.relevant_documents
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    return {
      title: f.title || null,
      node_type: f.node_type,
      answer_type: f.answer_type || null,
      eingabetyp: f.eingabetyp === '' ? null : f.eingabetyp,
      answer_set_id: f.answer_set_id || null,
      category_id: f.category_id || null,
      legal_reference: f.legal_reference || null,
      relevant_documents_json: docs.length ? docs : null,
      public_remark: f.public_remark || null,
      ja_label: f.node_type === 'DECISION' ? (f.ja_label || null) : null,
      nein_label: f.node_type === 'DECISION' ? (f.nein_label || null) : null,
    };
  }, [remarkOnly]);

  /** Fuehrt das Speichern aus (von Debounce ODER Flush angestossen). */
  const flush = useCallback(async (nodeId: string) => {
    if (!dirtyRef.current) return;
    dirtyRef.current = false;
    setSaveState('saving');
    try {
      await onSave(nodeId, buildPatch(formRef.current));
      setSaveState('saved');
    } catch {
      setSaveState('error');
    }
  }, [onSave, buildPatch]);

  // Formular bei Knotenwechsel neu setzen; vorherigen Knoten flushen.
  useEffect(() => {
    const prevNodeId = nodeIdRef.current;
    if (prevNodeId !== node.id) {
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
      if (dirtyRef.current) void flush(prevNodeId);
      nodeIdRef.current = node.id;
    }
    setForm(toForm(node));
    dirtyRef.current = false;
    setSaveState('idle');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node.id]);

  // Beim Unmount ausstehende Aenderung sichern.
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (dirtyRef.current) void flush(nodeIdRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Feldaenderung: State setzen + Auto-Save-Debounce neu anstossen. */
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    if (readOnly) return;
    setForm((f) => ({ ...f, [key]: value }));
    dirtyRef.current = true;
    setSaveState('idle');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => { void flush(nodeIdRef.current); }, AUTOSAVE_MS);
  };

  const meta = NODE_TYPE_META[form.node_type] ?? NODE_TYPE_META.QUESTION;
  const currentStatus: NodeStatus = (node.status ?? 'pending') as NodeStatus;

  return (
    <div className="flex flex-col">
      {/* Kopf */}
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
        <div className="flex min-w-0 items-center gap-2">
          <meta.icon size={16} className={meta.accent} />
          <h3 className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
            Eigenschaften
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {!readOnly && <SaveIndicator state={saveState} />}
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
            aria-label="Schließen"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1">
        {/* Statushinweise */}
        <div className="space-y-2 px-4 pt-4">
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
          {lockPending && (
            <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              <Loader2 size={14} className="animate-spin" /> Bearbeitungssperre wird gesetzt…
            </div>
          )}
        </div>

        {/* ── Zone „Bericht" ─────────────────────────────────────────────── */}
        <section className="px-4 py-4">
          <div className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">
            <FileText size={13} /> Bericht
          </div>

          <div className="space-y-4">
            <div>
              <label className={labelCls} htmlFor="ni-title">Titel / Fragetext</label>
              <textarea
                id="ni-title"
                rows={6}
                className={`${fieldCls} min-h-[8rem] resize-y leading-6`}
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
              <label className={labelCls} htmlFor="ni-legal">Rechtsgrundlage</label>
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
        </section>

        {/* ── Zone „Team (intern)" — gelblicher Tint ──────────────────────── */}
        <section className="border-t border-amber-200/70 bg-amber-50/60 px-4 py-4 dark:border-amber-900/40 dark:bg-amber-950/15">
          <div className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
            <Users size={13} /> Team (intern)
          </div>

          <div className="space-y-5">
            {/* (a) Status */}
            <div>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                Status
              </div>
              <StatusButtons
                templateId={templateId}
                nodeId={node.id}
                value={currentStatus}
                canEdit={fieldsEditable}
                onChanged={(s) => onStatusChanged(node.id, s)}
              />
            </div>

            {/* (b) Team-Diskussion */}
            <NodeDiscussion
              templateId={templateId}
              nodeId={node.id}
              ownUserId={ownUserId}
              canComment={canComment && !locked}
              liveSignal={discussionSignal}
            />

            {/* (c) Referenz-Dokumente */}
            <RefDocsPanel
              templateId={templateId}
              nodeId={node.id}
              canEdit={fieldsEditable}
              refreshSignal={refdocSignal}
            />
          </div>
        </section>
      </div>
    </div>
  );
}

// ── Speicher-Indikator ──────────────────────────────────────────────────────

function SaveIndicator({ state }: { state: SaveState }) {
  if (state === 'saving') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
        <Loader2 size={12} className="animate-spin" /> speichere…
      </span>
    );
  }
  if (state === 'saved') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-green-600 dark:text-green-400">
        <Check size={12} /> gespeichert
      </span>
    );
  }
  if (state === 'error') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-red-600 dark:text-red-400">
        <CloudOff size={12} /> Fehler
      </span>
    );
  }
  return null;
}
