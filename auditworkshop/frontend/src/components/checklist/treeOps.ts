/**
 * flowworkshop · components/checklist/treeOps.ts
 *
 * Reine Baum-Hilfsfunktionen: Knoten finden, Eltern/Geschwister ermitteln und
 * Move-Aktionen (hoch/runter, ein-/ausruecken) in parent_id + sort_order
 * uebersetzen. Keine Seiteneffekte — der TreeEditor ruft daraus die /move-API.
 */
import type { ChecklistNodeTree } from '../../lib/api';

export interface MoveTarget {
  parent_id: string | null;
  sort_order: number;
}

/** Liefert Eltern-Knoten (oder null = Wurzel) und die Geschwisterliste. */
export function findContext(
  roots: ChecklistNodeTree[],
  nodeId: string,
): { parent: ChecklistNodeTree | null; siblings: ChecklistNodeTree[]; index: number } | null {
  const visit = (
    list: ChecklistNodeTree[],
    parent: ChecklistNodeTree | null,
  ): { parent: ChecklistNodeTree | null; siblings: ChecklistNodeTree[]; index: number } | null => {
    const idx = list.findIndex((n) => n.id === nodeId);
    if (idx >= 0) return { parent, siblings: list, index: idx };
    for (const n of list) {
      const found = visit(n.children, n);
      if (found) return found;
    }
    return null;
  };
  return visit(roots, null);
}

export function findNode(roots: ChecklistNodeTree[], nodeId: string): ChecklistNodeTree | null {
  for (const n of roots) {
    if (n.id === nodeId) return n;
    const found = findNode(n.children, nodeId);
    if (found) return found;
  }
  return null;
}

/** Move-Ziel fuer „nach oben" — tauscht Position mit dem Vorgaenger-Geschwister. */
export function moveUpTarget(roots: ChecklistNodeTree[], nodeId: string): MoveTarget | null {
  const ctx = findContext(roots, nodeId);
  if (!ctx || ctx.index === 0) return null;
  const prev = ctx.siblings[ctx.index - 1];
  return { parent_id: ctx.parent?.id ?? null, sort_order: (prev.sort_order ?? 0) - 1 };
}

/** Move-Ziel fuer „nach unten" — tauscht Position mit dem Nachfolger-Geschwister. */
export function moveDownTarget(roots: ChecklistNodeTree[], nodeId: string): MoveTarget | null {
  const ctx = findContext(roots, nodeId);
  if (!ctx || ctx.index >= ctx.siblings.length - 1) return null;
  const next = ctx.siblings[ctx.index + 1];
  return { parent_id: ctx.parent?.id ?? null, sort_order: (next.sort_order ?? 0) + 1 };
}

/** Move-Ziel fuer „einruecken" — wird letztes Kind des Vorgaenger-Geschwisters. */
export function indentTarget(roots: ChecklistNodeTree[], nodeId: string): MoveTarget | null {
  const ctx = findContext(roots, nodeId);
  if (!ctx || ctx.index === 0) return null;
  const prev = ctx.siblings[ctx.index - 1];
  const lastChildOrder = prev.children.length
    ? Math.max(...prev.children.map((c) => c.sort_order ?? 0))
    : -1;
  return { parent_id: prev.id, sort_order: lastChildOrder + 1 };
}

/** Move-Ziel fuer „ausruecken" — wird Geschwister des bisherigen Elternknotens. */
export function outdentTarget(roots: ChecklistNodeTree[], nodeId: string): MoveTarget | null {
  const ctx = findContext(roots, nodeId);
  if (!ctx || !ctx.parent) return null;
  const grand = findContext(roots, ctx.parent.id);
  return {
    parent_id: grand?.parent?.id ?? null,
    sort_order: (ctx.parent.sort_order ?? 0) + 1,
  };
}

/** Naechste freie sort_order unter einem Elternknoten (oder Wurzel). */
export function nextSortOrder(roots: ChecklistNodeTree[], parentId: string | null): number {
  const siblings = parentId
    ? findNode(roots, parentId)?.children ?? []
    : roots;
  return siblings.length ? Math.max(...siblings.map((s) => s.sort_order ?? 0)) + 1 : 0;
}

/** Alle Knoten-IDs (fuer „alle ausklappen"). */
export function allNodeIds(roots: ChecklistNodeTree[]): string[] {
  const ids: string[] = [];
  const walk = (list: ChecklistNodeTree[]) => {
    for (const n of list) { ids.push(n.id); walk(n.children); }
  };
  walk(roots);
  return ids;
}

/** Anzahl aller Knoten im Baum. */
export function countNodes(roots: ChecklistNodeTree[]): number {
  return roots.reduce((sum, n) => sum + 1 + countNodes(n.children), 0);
}

/** Liefert die Menge aller Nachfahren-IDs (inkl. des Knotens selbst). */
export function descendantIds(node: ChecklistNodeTree): Set<string> {
  const ids = new Set<string>();
  const walk = (n: ChecklistNodeTree) => {
    ids.add(n.id);
    n.children.forEach(walk);
  };
  walk(node);
  return ids;
}

/**
 * Prueft, ob ein Drop des Knotens `dragId` auf das Ziel `targetId` einen Zyklus
 * erzeugen wuerde (Ziel ist der Knoten selbst oder einer seiner Nachfahren).
 */
export function isDescendantOrSelf(
  roots: ChecklistNodeTree[],
  dragId: string,
  targetId: string | null,
): boolean {
  if (targetId === null) return false;
  if (dragId === targetId) return true;
  const node = findNode(roots, dragId);
  if (!node) return false;
  return descendantIds(node).has(targetId);
}
