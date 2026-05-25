/**
 * flowworkshop · components/checklist/NodeContextMenu.tsx
 *
 * Rechtsklick-Kontextmenue fuer einen Baum-Knoten (ohne Fremd-Abhaengigkeit).
 * Wird absolut an der Cursor-Position gerendert und ueber ein Overlay wieder
 * geschlossen. Untermenue „Kind hinzufuegen" bietet die vier Knotentypen.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Pencil, Plus, CornerDownRight, Copy, Trash2, ChevronRight,
} from 'lucide-react';
import type { ChecklistNodeTree, NodeBranch, NodeType } from '../../lib/api';
import { NODE_TYPE_META, NODE_TYPE_ORDER } from './treeMeta';

export interface NodeContextMenuProps {
  node: ChecklistNodeTree;
  x: number;
  y: number;
  canEdit: boolean;
  /** DECISION-Kind in einen bestimmten Zweig anlegen (sonst null). */
  onEdit: () => void;
  onAddChild: (type: NodeType, branch?: NodeBranch | null) => void;
  onAddSibling: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onClose: () => void;
}

const itemCls =
  'flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-sm text-slate-700 hover:bg-emerald-50 hover:text-emerald-700 dark:text-slate-200 dark:hover:bg-emerald-900/20 dark:hover:text-emerald-300';

export default function NodeContextMenu(props: NodeContextMenuProps) {
  const {
    node, x, y, canEdit, onEdit, onAddChild, onAddSibling, onDuplicate, onDelete, onClose,
  } = props;
  const [submenu, setSubmenu] = useState(false);
  const isDecision = node.node_type === 'DECISION';

  // Innerhalb des Viewports halten (rechter/unterer Rand) — per Ref-Callback,
  // damit kein setState im Effekt noetig ist. Wir korrigieren die Position
  // direkt am DOM-Element nach dem Mounten/Messen.
  const measureRef = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (x + rect.width > window.innerWidth) {
      el.style.left = `${Math.max(8, window.innerWidth - rect.width - 8)}px`;
    }
    if (y + rect.height > window.innerHeight) {
      el.style.top = `${Math.max(8, window.innerHeight - rect.height - 8)}px`;
    }
  }, [x, y]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!canEdit) return null;

  return (
    <div className="fixed inset-0 z-50" onClick={onClose} onContextMenu={(e) => { e.preventDefault(); onClose(); }}>
      <div
        ref={measureRef}
        role="menu"
        className="absolute min-w-[200px] rounded-lg border border-slate-200 bg-white py-1 shadow-xl dark:border-slate-700 dark:bg-slate-800"
        style={{ left: x, top: y }}
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" role="menuitem" className={itemCls} onClick={() => { onEdit(); onClose(); }}>
          <Pencil size={15} className="text-slate-400" /> Bearbeiten
        </button>

        {/* Kind hinzufuegen — Untermenue mit Typen (bzw. Zweigen bei DECISION) */}
        <div
          className="relative"
          onMouseEnter={() => setSubmenu(true)}
          onMouseLeave={() => setSubmenu(false)}
        >
          <button type="button" role="menuitem" className={`${itemCls} justify-between`}>
            <span className="flex items-center gap-2.5">
              <Plus size={15} className="text-emerald-500" /> Kind hinzufügen
            </span>
            <ChevronRight size={14} className="text-slate-400" />
          </button>
          {submenu && (
            <div className="absolute left-full top-0 ml-1 min-w-[200px] rounded-lg border border-slate-200 bg-white py-1 shadow-xl dark:border-slate-700 dark:bg-slate-800">
              {isDecision ? (
                <>
                  <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">In Zweig</div>
                  <button type="button" className={itemCls} onClick={() => { onAddChild('QUESTION', 'JA'); onClose(); }}>
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-bold text-white">J</span>
                    Frage im JA-Zweig
                  </button>
                  <button type="button" className={itemCls} onClick={() => { onAddChild('QUESTION', 'NEIN'); onClose(); }}>
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">N</span>
                    Frage im NEIN-Zweig
                  </button>
                </>
              ) : (
                NODE_TYPE_ORDER.map((t) => {
                  const M = NODE_TYPE_META[t];
                  return (
                    <button key={t} type="button" className={itemCls} onClick={() => { onAddChild(t); onClose(); }}>
                      <M.icon size={15} className={M.accent} /> {M.label}
                    </button>
                  );
                })
              )}
            </div>
          )}
        </div>

        <button type="button" role="menuitem" className={itemCls} onClick={() => { onAddSibling(); onClose(); }}>
          <CornerDownRight size={15} className="text-slate-400" /> Geschwister hinzufügen
        </button>

        <div className="my-1 border-t border-slate-100 dark:border-slate-700" />

        <button type="button" role="menuitem" className={itemCls} onClick={() => { onDuplicate(); onClose(); }}>
          <Copy size={15} className="text-slate-400" /> Duplizieren
        </button>

        <div className="my-1 border-t border-slate-100 dark:border-slate-700" />

        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
          onClick={() => { onDelete(); onClose(); }}
        >
          <Trash2 size={15} /> Löschen
        </button>
      </div>
    </div>
  );
}
