/**
 * flowworkshop · components/checklist/treeMeta.ts
 *
 * Gemeinsame Metadaten, Typ-/Rollen-Helfer und Konstanten fuer den
 * Treeview-Editor der KOM-Checklisten. Kein JSX — reine Daten und Funktionen.
 */
import {
  Heading, HelpCircle, GitBranch, Info,
  type LucideIcon,
} from 'lucide-react';
import type {
  MemberRoleName, NodeType, TemplateAnswerType,
} from '../../lib/api';

// ── Rollen / Rechte ───────────────────────────────────────────────────────────

const ROLE_RANK: Record<MemberRoleName, number> = {
  viewer: 1, commenter: 2, editor: 3, owner: 4,
};

export function normRole(raw: string | null | undefined): MemberRoleName | null {
  const r = (raw || '').toLowerCase();
  if (r === 'owner' || r === 'editor' || r === 'commenter' || r === 'viewer') return r;
  return null;
}

/** Mindestens editor — darf Struktur und alle Felder aendern. */
export function canEdit(role: MemberRoleName | null): boolean {
  return !!role && ROLE_RANK[role] >= ROLE_RANK.editor;
}

/** Mindestens commenter — darf oeffentliche Bemerkungen pflegen. */
export function canComment(role: MemberRoleName | null): boolean {
  return !!role && ROLE_RANK[role] >= ROLE_RANK.commenter;
}

/** owner — darf Mitglieder/Eigentuemerschaft verwalten (hier read-only genutzt). */
export function isOwner(role: MemberRoleName | null): boolean {
  return role === 'owner';
}

export const ROLE_LABEL: Record<MemberRoleName, string> = {
  owner: 'Eigentümer',
  editor: 'Bearbeiter',
  commenter: 'Kommentator',
  viewer: 'Leser',
};

// ── Knotentypen ───────────────────────────────────────────────────────────────

export interface NodeTypeMeta {
  label: string;
  icon: LucideIcon;
  /** Tailwind-Klassen fuer Badge (Text-/Hintergrundton). */
  badge: string;
  /** Akzentfarbe fuer Icon-Glyph (auf getoentem Chip-Hintergrund). */
  accent: string;
  /** Getoenter Hintergrund fuer den Icon-Chip (w-6 h-6 rounded). */
  iconBg: string;
}

export const NODE_TYPE_META: Record<NodeType, NodeTypeMeta> = {
  HEADING: {
    label: 'Überschrift',
    icon: Heading,
    accent: 'text-emerald-600 dark:text-emerald-400',
    iconBg: 'bg-emerald-50 dark:bg-emerald-900/30',
    badge: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  },
  QUESTION: {
    label: 'Frage',
    icon: HelpCircle,
    accent: 'text-sky-600 dark:text-sky-400',
    iconBg: 'bg-sky-50 dark:bg-sky-900/30',
    badge: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
  },
  DECISION: {
    label: 'Entscheidung',
    icon: GitBranch,
    accent: 'text-violet-600 dark:text-violet-400',
    iconBg: 'bg-violet-50 dark:bg-violet-900/30',
    badge: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
  },
  HINT: {
    label: 'Hinweis',
    icon: Info,
    accent: 'text-amber-600 dark:text-amber-400',
    iconBg: 'bg-amber-50 dark:bg-amber-900/30',
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  },
};

export const NODE_TYPE_ORDER: NodeType[] = ['HEADING', 'QUESTION', 'DECISION', 'HINT'];

// ── Antworttypen ──────────────────────────────────────────────────────────────

export const ANSWER_TYPE_LABEL: Record<TemplateAnswerType, string> = {
  BOOLEAN: 'Ja/Nein/Teilweise/Entfällt',
  BOOLEAN_JN: 'Ja/Nein',
  CURRENCY: 'Betrag',
  DATE: 'Datum',
  CUSTOM_ENUM: 'Auswahl (Antwortset)',
  TEXT: 'Freitext / nur Bemerkung',
};

export const ANSWER_TYPE_ORDER: TemplateAnswerType[] = [
  'BOOLEAN', 'BOOLEAN_JN', 'CURRENCY', 'DATE', 'CUSTOM_ENUM', 'TEXT',
];

// eingabetyp (QChess FRAGENTYPID): 0=Auswahl, 1=Freitext, 2=Betrag, 4=Datum
export const EINGABETYP_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0, label: '0 · Auswahl (Dropdown)' },
  { value: 1, label: '1 · Freitext' },
  { value: 2, label: '2 · Betrag' },
  { value: 4, label: '4 · Datum' },
];
