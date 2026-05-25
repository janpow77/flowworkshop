/**
 * flowworkshop · components/checklist/PresenceBar.tsx
 *
 * Presence-Leiste fuer den Checklisten-Editor: zeigt als Avatar-Reihe (Initialen),
 * wer gerade gleichzeitig in der Checkliste arbeitet. Der eigene Nutzer ist
 * hervorgehoben. Tooltip nennt Name, Organisation und Bundesland. Live ueber die
 * presence-Events des SSE-Streams (siehe useChecklistCollab). Farbwelt Emerald/Cyan.
 */
import { Users, Wifi, WifiOff } from 'lucide-react';
import type { CollabPresenceUser } from '../../lib/api';

interface PresenceBarProps {
  users: CollabPresenceUser[];
  ownUserId: string | null;
  /** Verbindungszustand des SSE-Streams (fuer dezente Status-Anzeige). */
  conn: 'connecting' | 'open' | 'reconnecting';
}

/** Stabile Akzentfarbe je Nutzer (deterministisch aus der user_id abgeleitet). */
const AVATAR_TONES = [
  'bg-emerald-500',
  'bg-cyan-500',
  'bg-violet-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-sky-500',
  'bg-teal-500',
  'bg-fuchsia-500',
];

function toneFor(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i += 1) {
    hash = (hash * 31 + userId.charCodeAt(i)) | 0;
  }
  return AVATAR_TONES[Math.abs(hash) % AVATAR_TONES.length];
}

function initials(name: string | null, fallback: string): string {
  const src = (name || '').trim();
  if (!src) return fallback.slice(0, 2).toUpperCase();
  const parts = src.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function PresenceBar({ users, ownUserId, conn }: PresenceBarProps) {
  // Eigenen Nutzer nach vorne sortieren.
  const sorted = [...users].sort((a, b) => {
    if (a.user_id === ownUserId) return -1;
    if (b.user_id === ownUserId) return 1;
    return (a.name || '').localeCompare(b.name || '');
  });

  const others = sorted.filter((u) => u.user_id !== ownUserId).length;
  const summary = others === 0
    ? 'Nur Sie sind gerade hier.'
    : others === 1
      ? '1 weitere Person ist gerade hier.'
      : `${others} weitere Personen sind gerade hier.`;

  return (
    <div
      className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/70 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-900/70"
      aria-label="Anwesende Bearbeiter"
    >
      <Users size={15} className="shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
      <div className="flex -space-x-2" title={summary}>
        {sorted.map((u) => {
          const isSelf = u.user_id === ownUserId;
          const tip = [
            u.name || 'Unbekannt',
            isSelf ? '(Sie)' : null,
            u.organization,
            u.bundesland,
          ].filter(Boolean).join(' · ');
          return (
            <span
              key={u.user_id}
              title={tip}
              className={`flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-bold text-white shadow-sm ring-2 ${
                isSelf
                  ? 'ring-emerald-500 dark:ring-emerald-400'
                  : 'ring-white dark:ring-slate-900'
              } ${toneFor(u.user_id)}`}
            >
              {initials(u.name, u.user_id)}
            </span>
          );
        })}
        {sorted.length === 0 && (
          <span className="text-xs text-slate-400 dark:text-slate-500">—</span>
        )}
      </div>
      <span className="hidden text-xs text-slate-500 dark:text-slate-400 sm:inline">{summary}</span>
      <span
        className="ml-0.5 shrink-0"
        title={
          conn === 'open'
            ? 'Live verbunden'
            : conn === 'reconnecting'
              ? 'Verbindung wird wiederhergestellt…'
              : 'Verbindung wird aufgebaut…'
        }
        aria-label={conn === 'open' ? 'Live verbunden' : 'Verbindung wird wiederhergestellt'}
      >
        {conn === 'open' ? (
          <Wifi size={14} className="text-emerald-500" />
        ) : (
          <WifiOff size={14} className="animate-pulse text-amber-500" />
        )}
      </span>
    </div>
  );
}
