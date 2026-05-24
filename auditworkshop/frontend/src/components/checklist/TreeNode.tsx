/**
 * flowworkshop · components/checklist/TreeNode.tsx
 *
 * Rekursive Darstellung eines Checklisten-Knotens im audit_designer-Stil, jedoch
 * in der Workshop-Farbwelt (Emerald/Cyan). Auswahl als linke Akzentkante,
 * Icon-Chip pro Typ, animiertes Chevron, hierarchische Nummerierung. DECISION-
 * Kinder werden nach Zweig (JA/NEIN) in farbig umrandete Bereiche gruppiert.
 * Strukturaenderung per nativem HTML5-Drag&Drop und Rechtsklick-Kontextmenue.
 */
import { ChevronRight, Scale, FileText, Lock } from 'lucide-react';
import type { ChecklistNodeTree, CollabNodeLock, NodeBranch } from '../../lib/api';
import { NODE_TYPE_META } from './treeMeta';

export type DropPosition = 'before' | 'after' | 'inside';

export interface DragState {
  /** Gezogener Knoten. */
  dragId: string | null;
  /** Aktuelles Drop-Ziel. */
  overId: string | null;
  position: DropPosition;
  /** true, wenn der aktuelle Hover ein verbotener Zyklus waere. */
  invalid: boolean;
}

export interface TreeNodeActions {
  onSelect: (nodeId: string) => void;
  onToggle: (nodeId: string) => void;
  onContextMenu: (e: React.MouseEvent, node: ChecklistNodeTree) => void;
  // native HTML5-Drag&Drop
  onDragStart: (e: React.DragEvent, node: ChecklistNodeTree) => void;
  onDragOverNode: (e: React.DragEvent, node: ChecklistNodeTree) => void;
  onDropNode: (e: React.DragEvent, node: ChecklistNodeTree) => void;
  onDragEnd: () => void;
  // Drop in einen DECISION-Zweig (leerer Bereich)
  onDropBranch: (e: React.DragEvent, decision: ChecklistNodeTree, branch: NodeBranch) => void;
  onAddChildBranch: (decision: ChecklistNodeTree, branch: NodeBranch) => void;
}

interface TreeNodeProps extends TreeNodeActions {
  node: ChecklistNodeTree;
  depth: number;
  /** Hierarchische Nummer dieses Knotens, z. B. "1", "1.2". */
  number: string;
  selectedId: string | null;
  expanded: Set<string>;
  query: string;
  canEdit: boolean;
  drag: DragState;
  /** node_id → Lock-Halter (NUR Locks ANDERER Nutzer). */
  locks: Map<string, CollabNodeLock>;
}

function matchesQuery(node: ChecklistNodeTree, q: string): boolean {
  if (!q) return false;
  const hay = `${node.title ?? ''} ${node.legal_reference ?? ''} ${node.public_remark ?? ''}`.toLowerCase();
  return hay.includes(q);
}

export default function TreeNode(props: TreeNodeProps) {
  const {
    node, depth, number, selectedId, expanded, query, canEdit, drag, locks,
    onSelect, onToggle, onContextMenu,
    onDragStart, onDragOverNode, onDropNode, onDragEnd,
  } = props;

  // Lock eines ANDEREN Nutzers auf diesen Knoten (oder undefined).
  const lock = locks.get(node.id);

  const meta = NODE_TYPE_META[node.node_type] ?? NODE_TYPE_META.QUESTION;
  const Icon = meta.icon;
  const isDecision = node.node_type === 'DECISION';
  const isOpen = expanded.has(node.id);
  const isSelected = selectedId === node.id;
  const isHint = node.node_type === 'HINT';
  const isHeading = node.node_type === 'HEADING';
  const isHit = matchesQuery(node, query);

  // Kinder nach Zweig aufteilen (nur fuer DECISION relevant).
  const jaChildren = isDecision ? node.children.filter((c) => c.branch === 'JA') : [];
  const neinChildren = isDecision ? node.children.filter((c) => c.branch === 'NEIN') : [];
  const regularChildren = isDecision
    ? node.children.filter((c) => c.branch !== 'JA' && c.branch !== 'NEIN')
    : node.children;
  const hasChildren = node.children.length > 0;

  // Auswahl als linke Akzentkante statt Ring.
  const rowBase = isSelected
    ? 'bg-emerald-50 border-l-2 border-emerald-500 dark:bg-emerald-900/20'
    : isHit
      ? 'bg-amber-50 border-l-2 border-transparent dark:bg-amber-950/20'
      : 'border-l-2 border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/60';

  // Drop-Indicator-Status fuer diesen Knoten.
  const isDropTarget = drag.overId === node.id;
  const showBefore = isDropTarget && drag.position === 'before' && !drag.invalid;
  const showAfter = isDropTarget && drag.position === 'after' && !drag.invalid;
  const showInside = isDropTarget && drag.position === 'inside' && !drag.invalid;
  const showInvalid = isDropTarget && drag.invalid;

  const indent = depth * 18;

  return (
    <li>
      {/* Drop-Indicator „davor" */}
      <div
        className={`h-0.5 rounded-full transition-colors ${showBefore ? 'bg-emerald-500' : 'bg-transparent'}`}
        style={{ marginLeft: indent + 8 }}
        aria-hidden="true"
      />

      <div
        className={`group flex items-center gap-2 rounded-xl py-1.5 pr-2 transition-colors ${rowBase} ${
          showInside ? 'ring-1 ring-emerald-400 dark:ring-emerald-600' : ''
        } ${showInvalid ? 'ring-1 ring-red-400' : ''} ${
          drag.dragId === node.id ? 'opacity-40' : ''
        }`}
        style={{ marginLeft: indent }}
        draggable={canEdit}
        onDragStart={(e) => onDragStart(e, node)}
        onDragOver={(e) => onDragOverNode(e, node)}
        onDrop={(e) => onDropNode(e, node)}
        onDragEnd={onDragEnd}
        onContextMenu={(e) => onContextMenu(e, node)}
      >
        {/* Animiertes Chevron */}
        {hasChildren ? (
          <button
            type="button"
            onClick={() => onToggle(node.id)}
            className="ml-1 shrink-0 rounded p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-700"
            aria-label={isOpen ? 'Einklappen' : 'Ausklappen'}
          >
            <ChevronRight size={15} className={`transition-transform duration-150 ${isOpen ? 'rotate-90' : ''}`} />
          </button>
        ) : (
          <span className="ml-1 inline-block w-[22px] shrink-0" aria-hidden="true" />
        )}

        {/* Hierarchische Nummer */}
        <span className="shrink-0 font-mono text-[10px] text-slate-400 tabular-nums">{number}</span>

        {/* Icon-Chip pro Knotentyp */}
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded ${meta.iconBg}`}>
          <Icon size={14} className={meta.accent} />
        </span>

        {/* Titel + Metadaten */}
        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <span
            className={`truncate text-sm ${
              isHeading
                ? 'font-semibold text-slate-800 dark:text-slate-100'
                : isHint
                  ? 'italic text-amber-800 dark:text-amber-300'
                  : 'text-slate-700 dark:text-slate-200'
            }`}
          >
            {node.title || <span className="italic text-slate-400">(ohne Titel)</span>}
          </span>
          {node.legal_reference && (
            <Scale size={12} className="hidden shrink-0 text-slate-400 lg:inline" aria-label="Rechtsgrundlage hinterlegt" />
          )}
          {Array.isArray(node.relevant_documents_json) && node.relevant_documents_json.length > 0 && (
            <FileText size={12} className="hidden shrink-0 text-slate-400 lg:inline" aria-label="Belege hinterlegt" />
          )}
        </button>

        {/* Lock-Badge: wird von einer ANDEREN Person bearbeitet */}
        {lock && (
          <span
            className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
            title={`Wird von ${lock.locked_by_name || 'einer anderen Person'} bearbeitet`}
            aria-label={`Wird von ${lock.locked_by_name || 'einer anderen Person'} bearbeitet`}
          >
            <Lock size={11} />
            <span className="hidden max-w-[120px] truncate sm:inline">{lock.locked_by_name || 'gesperrt'}</span>
          </span>
        )}
      </div>

      {/* Drop-Indicator „danach" */}
      <div
        className={`h-0.5 rounded-full transition-colors ${showAfter ? 'bg-emerald-500' : 'bg-transparent'}`}
        style={{ marginLeft: indent + 8 }}
        aria-hidden="true"
      />

      {/* Regulaere Kinder (Nicht-DECISION oder zweiglose Kinder) */}
      {isOpen && regularChildren.length > 0 && (
        <ul>
          {regularChildren.map((child, i) => (
            <TreeNode
              key={child.id}
              {...props}
              node={child}
              depth={depth + 1}
              number={`${number}.${i + 1}`}
            />
          ))}
        </ul>
      )}

      {/* DECISION-Zweige als farbig umrandete Bereiche */}
      {isOpen && isDecision && (
        <div className="mt-1 space-y-1.5" style={{ marginLeft: indent + 24 }}>
          <BranchArea
            branch="JA"
            label={node.ja_label || 'Wenn ja'}
            childrenNodes={jaChildren}
            parentNumber={number}
            decision={node}
            {...props}
            depth={depth + 1}
          />
          <BranchArea
            branch="NEIN"
            label={node.nein_label || 'Wenn nein'}
            childrenNodes={neinChildren}
            parentNumber={number}
            decision={node}
            {...props}
            depth={depth + 1}
          />
        </div>
      )}
    </li>
  );
}

// ── Zweig-Bereich (JA/NEIN) ─────────────────────────────────────────────────────

interface BranchAreaProps extends TreeNodeProps {
  branch: NodeBranch;
  label: string;
  childrenNodes: ChecklistNodeTree[];
  parentNumber: string;
  decision: ChecklistNodeTree;
}

function BranchArea(props: BranchAreaProps) {
  const {
    branch, label, childrenNodes, parentNumber, decision, canEdit, drag,
    onDropBranch, onAddChildBranch,
  } = props;
  const isJa = branch === 'JA';
  const edge = isJa ? 'border-emerald-400 dark:border-emerald-600' : 'border-red-400 dark:border-red-600';
  const badgeBg = isJa ? 'bg-emerald-500' : 'bg-red-500';
  const headTone = isJa
    ? 'text-emerald-700 dark:text-emerald-400'
    : 'text-red-700 dark:text-red-400';
  const branchTag = isJa ? 'J' : 'N';
  const subNum = isJa ? `${parentNumber}.J` : `${parentNumber}.N`;

  // Highlight, wenn auf den leeren Zweig-Bereich gedroppt wird.
  const dropHere = drag.overId === `${decision.id}:${branch}` && !drag.invalid;

  return (
    <div
      className={`rounded-r-xl border-l-2 pl-2 ${edge} ${dropHere ? 'bg-emerald-50/60 dark:bg-emerald-900/10' : ''}`}
      onDragOver={(e) => { if (canEdit) { e.preventDefault(); } }}
      onDrop={(e) => onDropBranch(e, decision, branch)}
    >
      <div className={`flex items-center gap-2 py-1 text-xs font-medium ${headTone}`}>
        <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white ${badgeBg}`}>
          {branchTag}
        </span>
        {label}
      </div>

      {childrenNodes.length > 0 ? (
        <ul>
          {childrenNodes.map((child, i) => (
            <TreeNode
              key={child.id}
              {...props}
              node={child}
              depth={props.depth}
              number={`${subNum}${i + 1}`}
            />
          ))}
        </ul>
      ) : (
        <p className="py-1 text-[11px] italic text-slate-400">Noch keine Knoten in diesem Zweig.</p>
      )}

      {canEdit && (
        <button
          type="button"
          onClick={() => onAddChildBranch(decision, branch)}
          className="mb-1 ml-1 mt-0.5 inline-flex items-center gap-1 rounded text-[11px] text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400"
        >
          + Knoten im {isJa ? 'JA' : 'NEIN'}-Zweig
        </button>
      )}
    </div>
  );
}
