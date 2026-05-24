/**
 * flowworkshop · components/checklist/TreeEditor.tsx
 *
 * Rekursiver Treeview-Editor fuer eine KOM-Checkliste im audit_designer-Stil
 * (Workshop-Farbwelt Emerald/Cyan). Haelt den Knotenbaum, Auswahl/Expand-Zustand,
 * Volltextsuche sowie den Drag&Drop- und Kontextmenue-Zustand. Strukturaktionen
 * laufen ueber /nodes und /move. Rechte werden ueber die Rolle reflektiert
 * (Editor = voll, Kommentator = nur Bemerkung, Leser = read-only).
 *
 * Interaktionsmodell:
 *  - Rechtsklick auf einen Knoten oeffnet ein Kontextmenue (Bearbeiten, Kind/
 *    Geschwister hinzufuegen, Duplizieren, Loeschen).
 *  - Natives HTML5-Drag&Drop verschiebt Knoten (vor/nach/hinein) mit Drop-
 *    Indikatoren; Zyklen (Drop auf eigene Nachfahren) werden verhindert.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Plus, Search, ChevronsDownUp, ChevronsUpDown, ListChecks, Tags,
  Loader2, AlertCircle, FolderTree, RefreshCw,
} from 'lucide-react';
import {
  createChecklistNode, deleteChecklistNode, getChecklistTree, moveChecklistNode,
  updateChecklistNode,
  type ChecklistAnswerSet, type ChecklistNodeTree, type ChecklistTemplateCategory,
  type NodeBranch, type NodeCreatePayload, type NodeType, type NodeUpdatePayload,
} from '../../lib/api';
import TreeNode, { type DragState, type DropPosition } from './TreeNode';
import NodeInspector from './NodeInspector';
import AnswerSetManager from './AnswerSetManager';
import CategoryManager from './CategoryManager';
import NodeContextMenu from './NodeContextMenu';
import {
  allNodeIds, countNodes, findContext, findNode, insertNode, isDescendantOrSelf,
  moveNodeLocal, nextSortOrder, removeNode, replaceNode,
} from './treeOps';
import { NODE_TYPE_META, NODE_TYPE_ORDER } from './treeMeta';

interface TreeEditorProps {
  templateId: string;
  canEdit: boolean;
  canComment: boolean;
  initialAnswerSets: ChecklistAnswerSet[];
  initialCategories: ChecklistTemplateCategory[];
}

interface MenuState {
  node: ChecklistNodeTree;
  x: number;
  y: number;
}

const EMPTY_DRAG: DragState = { dragId: null, overId: null, position: 'before', invalid: false };

export default function TreeEditor({
  templateId, canEdit, canComment, initialAnswerSets, initialCategories,
}: TreeEditorProps) {
  const [tree, setTree] = useState<ChecklistNodeTree[]>([]);
  const [answerSets, setAnswerSets] = useState<ChecklistAnswerSet[]>(initialAnswerSets);
  const [categories, setCategories] = useState<ChecklistTemplateCategory[]>(initialCategories);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Transienter Hinweis (z. B. nach Rollback einer optimistischen Aktion).
  const [notice, setNotice] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [newType, setNewType] = useState<NodeType>('QUESTION');
  const [busy, setBusy] = useState(false);
  const [showAnswerSets, setShowAnswerSets] = useState(false);
  const [showCategories, setShowCategories] = useState(false);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [drag, setDrag] = useState<DragState>(EMPTY_DRAG);
  // Snapshot des aktuellen Baums fuer die Zyklenpruefung waehrend des Ziehens.
  const treeRef = useRef<ChecklistNodeTree[]>([]);
  treeRef.current = tree;
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Zeigt einen kurzen, selbst-verschwindenden Hinweis (Fehler-Rollback). */
  const flashNotice = (msg: string) => {
    setNotice(msg);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(''), 4000);
  };

  /** Vollstaendiges (Erst-)Laden des Baums — nur initial bzw. auf Wunsch. */
  const loadTree = async (preserveSelection = true) => {
    try {
      const data = await getChecklistTree(templateId);
      setTree(data);
      setExpanded((prev) => (prev.size === 0 ? new Set(allNodeIds(data)) : prev));
      if (!preserveSelection) setSelectedId(null);
      setError('');
    } catch (e) {
      setError(String(e).includes('403')
        ? 'Kein Zugriff auf diese Checkliste.'
        : 'Der Knotenbaum konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTree();
    return () => { if (noticeTimer.current) clearTimeout(noticeTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId]);

  const q = query.trim().toLowerCase();
  const selectedNode = useMemo(
    () => (selectedId ? findNode(tree, selectedId) : null),
    [tree, selectedId],
  );
  const total = useMemo(() => countNodes(tree), [tree]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const expandAll = () => setExpanded(new Set(allNodeIds(tree)));
  const collapseAll = () => setExpanded(new Set());

  // ── Struktur-Aktionen ────────────────────────────────────────────────────────

  const runCreate = async (payload: NodeCreatePayload, expandParent?: string | null) => {
    if (!canEdit) return;
    setBusy(true);
    try {
      // Der API-Call liefert den fertigen Knoten zurueck — wir fuegen ihn
      // optimistisch in den lokalen Baum ein, ohne den ganzen Baum neu zu laden.
      const created = await createChecklistNode(templateId, payload);
      const node: ChecklistNodeTree = { ...created, children: [] };
      setTree((prev) => insertNode(prev, payload.parent_id ?? null, node));
      if (expandParent) setExpanded((prev) => new Set(prev).add(expandParent));
      setSelectedId(created.id);
    } catch {
      flashNotice('Knoten konnte nicht angelegt werden.');
    } finally {
      setBusy(false);
    }
  };

  /** Wurzelknoten (Toolbar) anlegen. */
  const handleAddRoot = () =>
    runCreate({
      parent_id: null,
      node_type: newType,
      title: '',
      sort_order: nextSortOrder(tree, null),
    });

  /** Kind anlegen — bei DECISION-Eltern in den gewuenschten Zweig. */
  const handleAddChild = (parent: ChecklistNodeTree, type: NodeType, branch?: NodeBranch | null) =>
    runCreate({
      parent_id: parent.id,
      node_type: type,
      branch: branch ?? null,
      decision_parent_id: branch ? parent.id : null,
      title: '',
      sort_order: nextSortOrder(tree, parent.id),
    }, parent.id);

  /** Geschwister anlegen — gleicher Eltern-/Zweig-Kontext wie der Bezugsknoten. */
  const handleAddSibling = (node: ChecklistNodeTree) =>
    runCreate({
      parent_id: node.parent_id,
      node_type: node.node_type === 'DECISION' ? 'QUESTION' : node.node_type,
      branch: node.branch,
      decision_parent_id: node.decision_parent_id,
      title: '',
      sort_order: nextSortOrder(tree, node.parent_id),
    }, node.parent_id);

  /** Duplizieren — neuer Knoten mit gleichen Feldern direkt hinter dem Original. */
  const handleDuplicate = (node: ChecklistNodeTree) =>
    runCreate({
      parent_id: node.parent_id,
      node_type: node.node_type,
      branch: node.branch,
      decision_parent_id: node.decision_parent_id,
      title: node.title ? `${node.title} (Kopie)` : '',
      public_remark: node.public_remark,
      eingabetyp: node.eingabetyp,
      answer_type: node.answer_type,
      answer_set_id: node.answer_set_id,
      category_id: node.category_id,
      legal_reference: node.legal_reference,
      relevant_documents_json: node.relevant_documents_json,
      ja_label: node.ja_label,
      nein_label: node.nein_label,
      sort_order: (node.sort_order ?? 0) + 1,
    }, node.parent_id);

  const handleDelete = async (node: ChecklistNodeTree) => {
    if (!canEdit) return;
    const kids = node.children.length;
    const msg = kids
      ? `Knoten „${node.title || '(ohne Titel)'}" und ${kids} untergeordnete Knoten löschen?`
      : `Knoten „${node.title || '(ohne Titel)'}" löschen?`;
    if (!confirm(msg)) return;
    // Optimistisch entfernen, bei Fehler den vorherigen Baum wiederherstellen.
    const snapshot = treeRef.current;
    setBusy(true);
    setTree((prev) => removeNode(prev, node.id));
    if (selectedId === node.id) setSelectedId(null);
    try {
      await deleteChecklistNode(templateId, node.id);
    } catch {
      setTree(snapshot);
      flashNotice('Knoten konnte nicht gelöscht werden — Änderung zurückgenommen.');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveNode = async (nodeId: string, patch: NodeUpdatePayload) => {
    // Optimistisch im lokalen Baum patchen; der API-Call liefert den
    // kanonischen Knoten zurueck, mit dem wir den Eintrag final ersetzen.
    const snapshot = treeRef.current;
    setTree((prev) => replaceNode(prev, nodeId, patch as Partial<ChecklistNodeTree>));
    try {
      const updated = await updateChecklistNode(templateId, nodeId, patch);
      setTree((prev) => replaceNode(prev, nodeId, updated as Partial<ChecklistNodeTree>));
    } catch (e) {
      setTree(snapshot);
      flashNotice('Änderung konnte nicht gespeichert werden — zurückgenommen.');
      throw e; // NodeInspector zeigt den Fehler im Formular an
    }
  };

  // ── Drag & Drop (nativ HTML5) ──────────────────────────────────────────────────

  const onDragStart = (e: React.DragEvent, node: ChecklistNodeTree) => {
    if (!canEdit) return;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', node.id);
    setDrag({ ...EMPTY_DRAG, dragId: node.id });
  };

  const computePosition = (e: React.DragEvent): DropPosition => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const ratio = (e.clientY - rect.top) / rect.height;
    if (ratio < 0.28) return 'before';
    if (ratio > 0.72) return 'after';
    return 'inside';
  };

  const onDragOverNode = (e: React.DragEvent, node: ChecklistNodeTree) => {
    if (!canEdit || !drag.dragId) return;
    e.preventDefault();
    e.stopPropagation();
    const position = computePosition(e);
    // Zielelter ermitteln, um Zyklen zu pruefen.
    const targetParent = position === 'inside'
      ? node.id
      : node.parent_id;
    const invalid = drag.dragId === node.id
      || isDescendantOrSelf(treeRef.current, drag.dragId, node.id)
      || (position === 'inside' && isDescendantOrSelf(treeRef.current, drag.dragId, targetParent));
    e.dataTransfer.dropEffect = invalid ? 'none' : 'move';
    setDrag((d) => (d.overId === node.id && d.position === position && d.invalid === invalid
      ? d
      : { ...d, overId: node.id, position, invalid }));
  };

  const onDropNode = async (e: React.DragEvent, node: ChecklistNodeTree) => {
    e.preventDefault();
    e.stopPropagation();
    const dragId = drag.dragId;
    setDrag(EMPTY_DRAG);
    if (!canEdit || !dragId || dragId === node.id) return;
    const position = computePosition(e);

    let parent_id: string | null;
    let sort_order: number;
    let branch: NodeBranch | null = null;
    let decision_parent_id: string | null = null;

    if (position === 'inside') {
      if (isDescendantOrSelf(treeRef.current, dragId, node.id)) return;
      parent_id = node.id;
      sort_order = nextSortOrder(treeRef.current, node.id);
      // Beim Drop in eine DECISION „hinein" gibt es keinen Zweig — wir legen ihn
      // als zweiglosen Kindknoten ab; der Nutzer kann ihn spaeter einsortieren.
    } else {
      const ctx = findContext(treeRef.current, node.id);
      if (!ctx) return;
      parent_id = node.parent_id;
      branch = node.branch;
      decision_parent_id = node.decision_parent_id;
      if (parent_id && isDescendantOrSelf(treeRef.current, dragId, parent_id)) return;
      const delta = position === 'before' ? -1 : 1;
      sort_order = (node.sort_order ?? ctx.index) + delta * 0.5;
    }
    await runMove(dragId, { parent_id, sort_order, branch, decision_parent_id });
  };

  const onDropBranch = async (e: React.DragEvent, decision: ChecklistNodeTree, branch: NodeBranch) => {
    e.preventDefault();
    e.stopPropagation();
    const dragId = drag.dragId;
    setDrag(EMPTY_DRAG);
    if (!canEdit || !dragId) return;
    if (isDescendantOrSelf(treeRef.current, dragId, decision.id)) return;
    await runMove(dragId, {
      parent_id: decision.id,
      sort_order: nextSortOrder(treeRef.current, decision.id),
      branch,
      decision_parent_id: decision.id,
    });
  };

  const runMove = async (
    nodeId: string,
    target: { parent_id: string | null; sort_order: number; branch: NodeBranch | null; decision_parent_id: string | null },
  ) => {
    // Optimistisch sofort verschieben; bei Fehler den Schnappschuss zuruecksetzen.
    const snapshot = treeRef.current;
    setBusy(true);
    setTree((prev) => moveNodeLocal(prev, nodeId, {
      parent_id: target.parent_id,
      sort_order: target.sort_order,
      branch: target.branch,
      decision_parent_id: target.decision_parent_id,
    }));
    if (target.parent_id) setExpanded((prev) => new Set(prev).add(target.parent_id!));
    try {
      // branch/decision_parent_id via update setzen (move kennt nur parent/sort).
      if (target.branch !== undefined) {
        await updateChecklistNode(templateId, nodeId, {
          branch: target.branch,
          decision_parent_id: target.decision_parent_id,
        });
      }
      await moveChecklistNode(templateId, nodeId, {
        parent_id: target.parent_id,
        sort_order: target.sort_order,
      });
    } catch {
      setTree(snapshot);
      flashNotice('Verschieben fehlgeschlagen — Änderung zurückgenommen.');
    } finally {
      setBusy(false);
    }
  };

  const onDragEnd = () => setDrag(EMPTY_DRAG);

  // ── Kontextmenue ───────────────────────────────────────────────────────────────

  const onContextMenu = (e: React.MouseEvent, node: ChecklistNodeTree) => {
    if (!canEdit) return;
    e.preventDefault();
    setMenu({ node, x: e.clientX, y: e.clientY });
  };

  const nodeActions = {
    onSelect: setSelectedId,
    onToggle: toggle,
    onContextMenu,
    onDragStart,
    onDragOverNode,
    onDropNode,
    onDragEnd,
    onDropBranch,
    onAddChildBranch: (decision: ChecklistNodeTree, branch: NodeBranch) =>
      handleAddChild(decision, 'QUESTION', branch),
  };

  return (
    <div className="relative grid gap-4 lg:grid-cols-[1fr_360px]">
      {/* Transienter Rollback-Hinweis (selbst-verschwindend) */}
      {notice && (
        <div
          role="status"
          className="animate-slide-up fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 shadow-lg dark:border-amber-800 dark:bg-amber-950/80 dark:text-amber-200"
        >
          <AlertCircle size={16} /> {notice}
        </div>
      )}

      {/* Baum-Spalte */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <div className="relative min-w-[180px] flex-1">
            <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Knoten durchsuchen…"
              aria-label="Knoten durchsuchen"
              className="w-full rounded-lg border border-slate-300 bg-white py-1.5 pl-8 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            />
          </div>
          <button type="button" onClick={expandAll} title="Alle ausklappen" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800" aria-label="Alle ausklappen">
            <ChevronsUpDown size={16} />
          </button>
          <button type="button" onClick={collapseAll} title="Alle einklappen" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800" aria-label="Alle einklappen">
            <ChevronsDownUp size={16} />
          </button>
          <button type="button" onClick={() => loadTree()} title="Neu laden" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800" aria-label="Neu laden">
            <RefreshCw size={15} />
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2 text-sm dark:border-slate-800">
          {canEdit && (
            <>
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value as NodeType)}
                aria-label="Typ des neuen Wurzelknotens"
                className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                {NODE_TYPE_ORDER.map((t) => (
                  <option key={t} value={t}>{NODE_TYPE_META[t].label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleAddRoot}
                disabled={busy}
                className="flex items-center gap-1.5 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
              >
                <Plus size={14} /> Wurzelknoten
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => setShowAnswerSets(true)}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ListChecks size={14} /> Antwortsets
          </button>
          <button
            type="button"
            onClick={() => setShowCategories(true)}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <Tags size={14} /> Kategorien
          </button>
          <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-slate-400">
            {busy && <Loader2 size={13} className="animate-spin" />}
            {total} Knoten
          </span>
        </div>

        <div className="max-h-[60vh] overflow-y-auto px-2 py-2">
          {error && (
            <div className="mx-2 mb-2 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
              <AlertCircle size={15} /> {error}
            </div>
          )}
          {canEdit && tree.length > 0 && (
            <p className="mb-1 px-2 text-[11px] text-slate-400">
              Rechtsklick öffnet das Kontextmenü · Knoten lassen sich per Ziehen umsortieren.
            </p>
          )}
          {loading ? (
            <div className="flex items-center gap-2 px-4 py-10 text-sm text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Lädt Knotenbaum…
            </div>
          ) : tree.length === 0 ? (
            <div className="px-4 py-12 text-center text-slate-400">
              <FolderTree size={40} className="mx-auto mb-3" />
              <p className="text-sm text-slate-500 dark:text-slate-400">Diese Checkliste hat noch keine Knoten.</p>
              {canEdit && (
                <p className="mt-1 text-xs">Legen Sie oben einen Wurzelknoten an, um zu beginnen.</p>
              )}
            </div>
          ) : (
            <ul>
              {tree.map((node, i) => (
                <TreeNode
                  key={node.id}
                  node={node}
                  depth={0}
                  number={`${i + 1}`}
                  selectedId={selectedId}
                  expanded={expanded}
                  query={q}
                  canEdit={canEdit}
                  drag={drag}
                  {...nodeActions}
                />
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Inspector — Desktop: zweite Spalte. */}
      <div className="hidden rounded-xl border border-slate-200 bg-white transition-shadow dark:border-slate-700 dark:bg-slate-900 lg:block lg:min-h-[400px]">
        {selectedNode ? (
          <NodeInspector
            key={selectedNode.id}
            node={selectedNode}
            answerSets={answerSets}
            categories={categories}
            canEdit={canEdit}
            canComment={canComment}
            onSave={handleSaveNode}
            onClose={() => setSelectedId(null)}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-6 py-12 text-center text-slate-400">
            <FolderTree size={36} className="mb-3" />
            <p className="text-sm">Wählen Sie einen Knoten aus, um seine Details zu bearbeiten.</p>
          </div>
        )}
      </div>

      {/* Inspector — schmaler Viewport: Off-Canvas-Drawer von rechts. */}
      {selectedNode && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Inspector schließen"
            onClick={() => setSelectedId(null)}
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
          />
          <div className="absolute right-0 top-0 flex h-full w-[92%] max-w-md animate-slide-in flex-col overflow-y-auto border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <NodeInspector
              key={selectedNode.id}
              node={selectedNode}
              answerSets={answerSets}
              categories={categories}
              canEdit={canEdit}
              canComment={canComment}
              onSave={handleSaveNode}
              onClose={() => setSelectedId(null)}
            />
          </div>
        </div>
      )}

      {menu && (
        <NodeContextMenu
          node={menu.node}
          x={menu.x}
          y={menu.y}
          canEdit={canEdit}
          onEdit={() => setSelectedId(menu.node.id)}
          onAddChild={(type, branch) => handleAddChild(menu.node, type, branch)}
          onAddSibling={() => handleAddSibling(menu.node)}
          onDuplicate={() => handleDuplicate(menu.node)}
          onDelete={() => handleDelete(menu.node)}
          onClose={() => setMenu(null)}
        />
      )}

      {showAnswerSets && (
        <AnswerSetManager
          templateId={templateId}
          canEdit={canEdit}
          onChanged={setAnswerSets}
          onClose={() => setShowAnswerSets(false)}
        />
      )}
      {showCategories && (
        <CategoryManager
          templateId={templateId}
          canEdit={canEdit}
          onChanged={setCategories}
          onClose={() => setShowCategories(false)}
        />
      )}
    </div>
  );
}
