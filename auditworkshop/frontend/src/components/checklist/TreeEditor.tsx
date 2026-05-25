/**
 * flowworkshop · components/checklist/TreeEditor.tsx
 *
 * Rekursiver Treeview-Editor fuer eine KOM-Checkliste im audit_designer-Stil
 * (Workshop-Farbwelt BLAU als primary). Haelt den Knotenbaum, Auswahl/Expand-
 * Zustand, Volltextsuche sowie den Drag&Drop- und Kontextmenue-Zustand.
 *
 * Layout: verschiebbarer Split-View — links Baum (Breite in %), Divider
 * (ResizeHandle), rechts Zwei-Zonen-Inspector. Die Breite wird in
 * localStorage('checklistSplitPosition') persistiert (clamp 20–80 %). Auf
 * schmalen Viewports erscheint der Inspector als Off-Canvas-Drawer.
 *
 * Kollaboration: optimistische Tree-Updates, SSE-Presence/Locks sowie Live-
 * Diskussions-/Referenz-Events aus ``useChecklistCollab``. Undo/Redo arbeitet
 * lokal ueber Snapshot-Stacks (max. 50) mit Strg+Z / Strg+Shift+Z; die
 * Server-Synchronisation erfolgt vereinfachend per Neuladen.
 *
 * Interaktionsmodell:
 *  - Rechtsklick auf einen Knoten oeffnet ein Kontextmenue.
 *  - Natives HTML5-Drag&Drop verschiebt Knoten (vor/nach/hinein).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Plus, Search, ChevronsDownUp, ChevronsUpDown, ListChecks, Tags,
  Loader2, AlertCircle, FolderTree, RefreshCw, History, CheckCircle2,
  Undo2, Redo2,
} from 'lucide-react';
import {
  acquireNodeLock, createChecklistNode, deleteChecklistNode, getChecklistTree,
  getUnreadCounts, moveChecklistNode, releaseNodeLock, updateChecklistNode,
  LockConflictError,
  type ChecklistAnswerSet, type ChecklistNode, type ChecklistNodeTree,
  type ChecklistTemplateCategory, type CollabLockConflict,
  type NodeBranch, type NodeCreatePayload, type NodeStatus, type NodeType,
  type NodeUpdatePayload,
} from '../../lib/api';
import TreeNode, { type DragState, type DropPosition } from './TreeNode';
import NodeInspector from './NodeInspector';
import ResizeHandle from './ResizeHandle';
import AnswerSetManager from './AnswerSetManager';
import CategoryManager from './CategoryManager';
import NodeContextMenu from './NodeContextMenu';
import PresenceBar from './PresenceBar';
import HistoryPanel from './HistoryPanel';
import ExportMenu from './ExportMenu';
import VersionsMenu from './VersionsMenu';
import {
  useChecklistCollab, type RemoteDiscussionEvent, type RemoteNodeEvent,
} from './useChecklistCollab';
import {
  allNodeIds, countNodes, findContext, findNode, insertNode, isDescendantOrSelf,
  moveNodeLocal, nextSortOrder, removeNode, replaceNode,
} from './treeOps';
import { NODE_TYPE_META, NODE_TYPE_ORDER } from './treeMeta';

interface TreeEditorProps {
  templateId: string;
  canEdit: boolean;
  canComment: boolean;
  /** Eigene Nutzerkennung — fuer Presence-Markierung und Event-Filterung. */
  ownUserId: string | null;
  initialAnswerSets: ChecklistAnswerSet[];
  initialCategories: ChecklistTemplateCategory[];
}

// Lock-Erneuerung: alle 40s, sicher unterhalb der 60s-TTL des Backends.
const LOCK_RENEW_MS = 40000;

// Split-View
const SPLIT_KEY = 'checklistSplitPosition';
const SPLIT_MIN = 20;
const SPLIT_MAX = 80;

// Undo/Redo
const UNDO_LIMIT = 50;

interface MenuState {
  node: ChecklistNodeTree;
  x: number;
  y: number;
}

const EMPTY_DRAG: DragState = { dragId: null, overId: null, position: 'before', invalid: false };

function loadSplit(): number {
  const raw = parseFloat(localStorage.getItem(SPLIT_KEY) ?? '');
  if (Number.isNaN(raw)) return 62;
  return Math.min(Math.max(raw, SPLIT_MIN), SPLIT_MAX);
}

/** Ersten QUESTION-Knoten in Tiefensuche finden (Vorauswahl). */
function firstQuestionId(roots: ChecklistNodeTree[]): string | null {
  for (const n of roots) {
    if (n.node_type === 'QUESTION') return n.id;
    const found = firstQuestionId(n.children);
    if (found) return found;
  }
  return null;
}

export default function TreeEditor({
  templateId, canEdit, canComment, ownUserId, initialAnswerSets, initialCategories,
}: TreeEditorProps) {
  const [tree, setTree] = useState<ChecklistNodeTree[]>([]);
  const [answerSets, setAnswerSets] = useState<ChecklistAnswerSet[]>(initialAnswerSets);
  const [categories, setCategories] = useState<ChecklistTemplateCategory[]>(initialCategories);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [newType, setNewType] = useState<NodeType>('QUESTION');
  const [busy, setBusy] = useState(false);
  const [showAnswerSets, setShowAnswerSets] = useState(false);
  const [showCategories, setShowCategories] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [success, setSuccess] = useState('');
  const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [drag, setDrag] = useState<DragState>(EMPTY_DRAG);
  const treeRef = useRef<ChecklistNodeTree[]>([]);
  treeRef.current = tree;
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Split-View ────────────────────────────────────────────────────────────
  const [splitPct, setSplitPct] = useState<number>(() => loadSplit());
  const [resizing, setResizing] = useState(false);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);

  // ── Unread-Counts (Diskussion) ─────────────────────────────────────────────
  const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({});

  // ── Live-Signale fuer den geoeffneten Inspector (Diskussion/Referenz) ────────
  const [discussionSignal, setDiscussionSignal] = useState(0);
  const [refdocSignal, setRefdocSignal] = useState(0);

  // ── Undo/Redo (lokale Snapshot-Stacks) ──────────────────────────────────────
  const undoStack = useRef<ChecklistNodeTree[][]>([]);
  const redoStack = useRef<ChecklistNodeTree[][]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const refreshUndoFlags = () => {
    setCanUndo(undoStack.current.length > 0);
    setCanRedo(redoStack.current.length > 0);
  };
  /** Legt den aktuellen Baum als Undo-Schnappschuss ab (vor einer Strukturaktion). */
  const pushUndo = useCallback(() => {
    undoStack.current.push(treeRef.current);
    if (undoStack.current.length > UNDO_LIMIT) undoStack.current.shift();
    redoStack.current = [];
    refreshUndoFlags();
  }, []);

  // ── Kollaboration: Lock-Zustand ──────────────────────────────────────────────
  const [lockConflict, setLockConflict] = useState<CollabLockConflict | null>(null);
  const [lockPending, setLockPending] = useState(false);
  const heldLockRef = useRef<string | null>(null);

  const applyRemoteNode = useCallback((ev: RemoteNodeEvent) => {
    setTree((prev) => {
      switch (ev.type) {
        case 'node_created': {
          const n = ev.node as ChecklistNode;
          if (findNode(prev, n.id)) {
            return replaceNode(prev, n.id, n as Partial<ChecklistNodeTree>);
          }
          const tn: ChecklistNodeTree = { ...n, children: [] };
          return insertNode(prev, n.parent_id ?? null, tn);
        }
        case 'node_updated': {
          const n = ev.node as ChecklistNode;
          if (!findNode(prev, n.id)) return prev;
          const { ...patch } = n;
          return replaceNode(prev, n.id, patch as Partial<ChecklistNodeTree>);
        }
        case 'node_moved': {
          const n = ev.node as ChecklistNode;
          if (!findNode(prev, n.id)) return prev;
          if (n.parent_id) {
            setExpanded((exp) => (exp.has(n.parent_id!) ? exp : new Set(exp).add(n.parent_id!)));
          }
          return moveNodeLocal(prev, n.id, {
            parent_id: n.parent_id ?? null,
            sort_order: n.sort_order ?? 0,
            branch: n.branch,
            decision_parent_id: n.decision_parent_id ?? null,
          });
        }
        case 'node_deleted': {
          if (!findNode(prev, ev.node_id)) return prev;
          return removeNode(prev, ev.node_id);
        }
        default:
          return prev;
      }
    });
  }, []);

  // Live-Diskussions-/Referenz-Events: betroffenen Knoten-Thread neu laden +
  // Unread-Counts aktualisieren.
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;
  const applyRemoteDiscussion = useCallback((ev: RemoteDiscussionEvent) => {
    const open = selectedIdRef.current === ev.node_id;
    if (ev.type === 'comment_added' || ev.type === 'comment_updated' || ev.type === 'comment_deleted') {
      if (open) setDiscussionSignal((v) => v + 1);
      // Unread-Counts (best-effort) frisch ziehen.
      getUnreadCounts(templateId).then(setUnreadCounts).catch(() => { /* unkritisch */ });
    } else {
      if (open) setRefdocSignal((v) => v + 1);
    }
  }, [templateId]);

  const { presence, locks, conn } = useChecklistCollab({
    templateId,
    ownUserId,
    enabled: !!ownUserId,
    onRemoteNode: applyRemoteNode,
    onRemoteDiscussion: applyRemoteDiscussion,
  });

  const flashNotice = (msg: string) => {
    setNotice(msg);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(''), 4000);
  };

  const flashSuccess = (msg: string) => {
    setSuccess(msg);
    if (successTimer.current) clearTimeout(successTimer.current);
    successTimer.current = setTimeout(() => setSuccess(''), 4000);
  };

  /** Vollstaendiges (Erst-)Laden des Baums. Selektiert optional den ersten Frage-Knoten. */
  const loadTree = async (opts?: { preselect?: boolean; preserveSelection?: boolean }) => {
    const preselect = opts?.preselect ?? false;
    const preserveSelection = opts?.preserveSelection ?? true;
    try {
      const data = await getChecklistTree(templateId);
      setTree(data);
      setExpanded((prev) => (prev.size === 0 ? new Set(allNodeIds(data)) : prev));
      if (!preserveSelection) setSelectedId(null);
      else if (preselect) {
        const fq = firstQuestionId(data);
        if (fq) setSelectedId(fq);
      }
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
    void loadTree({ preselect: true });
    getUnreadCounts(templateId).then(setUnreadCounts).catch(() => { /* unkritisch */ });
    return () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
      if (successTimer.current) clearTimeout(successTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId]);

  // ── Split-Resize via document-mousemove ─────────────────────────────────────
  const onResizeStart = useCallback(() => {
    setResizing(true);
    const move = (e: MouseEvent) => {
      const rect = splitContainerRef.current?.getBoundingClientRect();
      if (!rect || rect.width === 0) return;
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setSplitPct(Math.min(Math.max(pct, SPLIT_MIN), SPLIT_MAX));
    };
    const up = () => {
      setResizing(false);
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', up);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      setSplitPct((p) => { localStorage.setItem(SPLIT_KEY, String(p)); return p; });
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  // ── Lock-Lebenszyklus ────────────────────────────────────────────────────────
  useEffect(() => {
    setLockConflict(null);
    setLockPending(false);
    if (!selectedId || !canEdit || !ownUserId) return;
    const nodeId = selectedId;
    let cancelled = false;
    let renewTimer: ReturnType<typeof setInterval> | null = null;

    const acquire = async (initial: boolean) => {
      try {
        await acquireNodeLock(templateId, nodeId);
        if (cancelled) return;
        heldLockRef.current = nodeId;
        setLockConflict(null);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof LockConflictError) {
          setLockConflict(e.conflict);
          heldLockRef.current = null;
        } else if (initial) {
          heldLockRef.current = null;
        }
      } finally {
        if (!cancelled && initial) setLockPending(false);
      }
    };

    setLockPending(true);
    void acquire(true);
    renewTimer = setInterval(() => void acquire(false), LOCK_RENEW_MS);

    return () => {
      cancelled = true;
      if (renewTimer) clearInterval(renewTimer);
      if (heldLockRef.current === nodeId) {
        heldLockRef.current = null;
        void releaseNodeLock(templateId, nodeId).catch(() => { /* idempotent */ });
      }
    };
  }, [selectedId, canEdit, ownUserId, templateId]);

  useEffect(() => {
    if (!lockConflict || !selectedId || !canEdit || !ownUserId) return;
    if (locks.has(selectedId)) return;
    let cancelled = false;
    setLockPending(true);
    acquireNodeLock(templateId, selectedId)
      .then(() => { if (!cancelled) { heldLockRef.current = selectedId; setLockConflict(null); } })
      .catch((e) => { if (!cancelled && e instanceof LockConflictError) setLockConflict(e.conflict); })
      .finally(() => { if (!cancelled) setLockPending(false); });
    return () => { cancelled = true; };
  }, [locks, lockConflict, selectedId, canEdit, ownUserId, templateId]);

  const q = query.trim().toLowerCase();
  const selectedNode = useMemo(
    () => (selectedId ? findNode(tree, selectedId) : null),
    [tree, selectedId],
  );
  const total = useMemo(() => countNodes(tree), [tree]);

  const selectedConflict: CollabLockConflict | null = useMemo(() => {
    if (lockConflict) return lockConflict;
    if (!selectedId) return null;
    const lk = locks.get(selectedId);
    if (!lk) return null;
    return {
      message: 'Knoten wird gerade von einer anderen Person bearbeitet.',
      locked_by_id: lk.locked_by_id,
      locked_by_name: lk.locked_by_name,
      organization: lk.organization ?? null,
      bundesland: lk.bundesland ?? null,
      expires_at: lk.expires_at,
    };
  }, [lockConflict, selectedId, locks]);

  // Beim Oeffnen eines Knotens lokal als „gelesen" markieren (Badge sofort weg);
  // der Server-Request laeuft in NodeDiscussion.
  useEffect(() => {
    if (!selectedId) return;
    setUnreadCounts((prev) => {
      if (!prev[selectedId]) return prev;
      const next = { ...prev };
      delete next[selectedId];
      return next;
    });
  }, [selectedId]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const expandAll = () => setExpanded(new Set(allNodeIds(tree)));
  const collapseAll = () => setExpanded(new Set());

  // ── Undo / Redo ──────────────────────────────────────────────────────────────
  const handleUndo = useCallback(() => {
    if (undoStack.current.length === 0) return;
    const prev = undoStack.current.pop()!;
    redoStack.current.push(treeRef.current);
    if (redoStack.current.length > UNDO_LIMIT) redoStack.current.shift();
    setTree(prev);
    refreshUndoFlags();
    flashNotice('Schritt rückgängig gemacht (lokal). Bei Bedarf neu laden, um den Serverstand abzugleichen.');
  }, []);

  const handleRedo = useCallback(() => {
    if (redoStack.current.length === 0) return;
    const next = redoStack.current.pop()!;
    undoStack.current.push(treeRef.current);
    if (undoStack.current.length > UNDO_LIMIT) undoStack.current.shift();
    setTree(next);
    refreshUndoFlags();
    flashNotice('Schritt wiederhergestellt (lokal).');
  }, []);

  // Tastatur: Strg+Z / Strg+Shift+Z (bzw. Cmd auf macOS).
  useEffect(() => {
    if (!canEdit) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z') return;
      // In Eingabefeldern dem Browser die native Undo-Funktion lassen.
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      e.preventDefault();
      if (e.shiftKey) handleRedo(); else handleUndo();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canEdit, handleUndo, handleRedo]);

  // ── Struktur-Aktionen ────────────────────────────────────────────────────────

  const runCreate = async (payload: NodeCreatePayload, expandParent?: string | null) => {
    if (!canEdit) return;
    pushUndo();
    setBusy(true);
    try {
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

  const handleAddRoot = () =>
    runCreate({
      parent_id: null,
      node_type: newType,
      title: '',
      sort_order: nextSortOrder(tree, null),
    });

  const handleAddChild = (parent: ChecklistNodeTree, type: NodeType, branch?: NodeBranch | null) =>
    runCreate({
      parent_id: parent.id,
      node_type: type,
      branch: branch ?? null,
      decision_parent_id: branch ? parent.id : null,
      title: '',
      sort_order: nextSortOrder(tree, parent.id),
    }, parent.id);

  const handleAddSibling = (node: ChecklistNodeTree) =>
    runCreate({
      parent_id: node.parent_id,
      node_type: node.node_type === 'DECISION' ? 'QUESTION' : node.node_type,
      branch: node.branch,
      decision_parent_id: node.decision_parent_id,
      title: '',
      sort_order: nextSortOrder(tree, node.parent_id),
    }, node.parent_id);

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
    pushUndo();
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
    const snapshot = treeRef.current;
    setTree((prev) => replaceNode(prev, nodeId, patch as Partial<ChecklistNodeTree>));
    try {
      const updated = await updateChecklistNode(templateId, nodeId, patch);
      setTree((prev) => replaceNode(prev, nodeId, updated as Partial<ChecklistNodeTree>));
    } catch (e) {
      setTree(snapshot);
      flashNotice('Änderung konnte nicht gespeichert werden — zurückgenommen.');
      throw e;
    }
  };

  /** Optimistisches Status-Update im Baum (PUT erfolgt in StatusButtons). */
  const handleStatusChanged = (nodeId: string, status: NodeStatus) => {
    setTree((prev) => replaceNode(prev, nodeId, { status }));
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
    const targetParent = position === 'inside' ? node.id : node.parent_id;
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
    pushUndo();
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

  const inspector = selectedNode ? (
    <NodeInspector
      key={selectedNode.id}
      templateId={templateId}
      node={selectedNode}
      answerSets={answerSets}
      categories={categories}
      canEdit={canEdit}
      canComment={canComment}
      ownUserId={ownUserId}
      onSave={handleSaveNode}
      onClose={() => setSelectedId(null)}
      onStatusChanged={handleStatusChanged}
      discussionSignal={discussionSignal}
      refdocSignal={refdocSignal}
      lockedByOther={selectedConflict}
      lockPending={lockPending}
    />
  ) : null;

  return (
    <div className="relative space-y-4">
      {/* Transienter Rollback-Hinweis */}
      {notice && (
        <div
          role="status"
          className="animate-slide-up fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 shadow-lg dark:border-amber-800 dark:bg-amber-950/80 dark:text-amber-200"
        >
          <AlertCircle size={16} /> {notice}
        </div>
      )}
      {success && (
        <div
          role="status"
          className="animate-slide-up fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-800 shadow-lg dark:border-green-800 dark:bg-green-950/80 dark:text-green-200"
        >
          <CheckCircle2 size={16} /> {success}
        </div>
      )}

      {/* Presence-Leiste */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PresenceBar users={presence} ownUserId={ownUserId} conn={conn} />
      </div>

      {/* ── Split-View: Baum | Divider | Inspector ────────────────────────── */}
      <div ref={splitContainerRef} className="flex items-stretch gap-0 lg:gap-0">
        {/* Baum-Spalte */}
        <div
          className="flex min-w-0 flex-col rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900 lg:rounded-r-none"
          style={{ width: `${splitPct}%` }}
        >
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <div className="relative min-w-[180px] flex-1">
              <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Knoten durchsuchen…"
                aria-label="Knoten durchsuchen"
                className="w-full rounded-lg border border-slate-300 bg-white py-1.5 pl-8 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
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
                  className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                >
                  {NODE_TYPE_ORDER.map((t) => (
                    <option key={t} value={t}>{NODE_TYPE_META[t].label}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleAddRoot}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-full bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
                >
                  <Plus size={14} /> Wurzelknoten
                </button>
                {/* Undo/Redo */}
                <div className="flex items-center gap-0.5">
                  <button
                    type="button"
                    onClick={handleUndo}
                    disabled={!canUndo}
                    title="Rückgängig (Strg+Z)"
                    aria-label="Rückgängig"
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 disabled:hover:bg-transparent dark:hover:bg-slate-800"
                  >
                    <Undo2 size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={handleRedo}
                    disabled={!canRedo}
                    title="Wiederholen (Strg+Umschalt+Z)"
                    aria-label="Wiederholen"
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 disabled:hover:bg-transparent dark:hover:bg-slate-800"
                  >
                    <Redo2 size={15} />
                  </button>
                </div>
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
            <button
              type="button"
              onClick={() => setShowHistory(true)}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <History size={14} /> Verlauf
            </button>
            <VersionsMenu
              templateId={templateId}
              canEdit={canEdit}
              onNotify={flashSuccess}
              onError={flashNotice}
              onRestored={() => { void loadTree(); }}
            />
            <ExportMenu templateId={templateId} onError={flashNotice} />
            <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-slate-400">
              {busy && <Loader2 size={13} className="animate-spin" />}
              {total} Knoten
            </span>
          </div>

          <div className="max-h-[64vh] flex-1 overflow-y-auto px-2 py-2">
            {error && (
              <div className="mx-2 mb-2 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
                <AlertCircle size={15} /> {error}
              </div>
            )}
            {canEdit && tree.length > 0 && (
              <p className="mb-1 px-2 text-[11px] text-slate-400">
                Rechtsklick öffnet das Kontextmenü · Knoten lassen sich per Ziehen umsortieren · Strg+Z macht rückgängig.
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
                    locks={locks}
                    unreadCounts={unreadCounts}
                    {...nodeActions}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Divider — nur Desktop */}
        <div className="hidden lg:flex">
          <ResizeHandle resizing={resizing} onResizeStart={onResizeStart} />
        </div>

        {/* Inspector — Desktop */}
        <div
          className="hidden min-w-0 flex-1 rounded-xl rounded-l-none border border-l-0 border-slate-200 bg-white transition-shadow dark:border-slate-700 dark:bg-slate-900 lg:block lg:min-h-[400px]"
        >
          {inspector ?? (
            <div className="flex h-full flex-col items-center justify-center px-6 py-12 text-center text-slate-400">
              <FolderTree size={36} className="mb-3" />
              <p className="text-sm">Wählen Sie einen Knoten aus, um seine Details zu bearbeiten.</p>
            </div>
          )}
        </div>
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
            {inspector}
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
      {showHistory && (
        <HistoryPanel
          templateId={templateId}
          canRestore={canEdit}
          onClose={() => setShowHistory(false)}
          onRestored={(msg) => { flashSuccess(msg); void loadTree(); }}
        />
      )}
    </div>
  );
}
