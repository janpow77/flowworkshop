/**
 * flowworkshop · components/checklist/useChecklistCollab.ts
 *
 * Hook fuer die Hybrid-Kollaboration des Checklisten-Designers:
 *   • Presence — wer ist gerade in der Checkliste (live ueber presence-Events).
 *   • Node-Locking — Map node_id → Halter, gepflegt aus init/lock_acquired/
 *     lock_released. Eigene Locks werden NICHT als „fremd" angezeigt.
 *   • Live-Updates — node_created/updated/deleted/moved von ANDEREN Nutzern
 *     werden ueber ``onRemoteNode`` an den TreeEditor durchgereicht; EIGENE
 *     Events (user_id == eigener Nutzer) werden gefiltert, damit die
 *     optimistischen Updates aus Phase 6 nicht doppelt angewandt werden.
 *
 * SSE-Robustheit: ``EventSource`` reconnectet von sich aus, eskaliert aber bei
 * harten Fehlern (z. B. 401) zu ``readyState === CLOSED``. In diesem Fall baut
 * der Hook die Verbindung mit exponentiellem Backoff (1s → 2s → … → max 30s)
 * neu auf. Beim Unmount/Templatewechsel wird die Verbindung sauber geschlossen.
 *
 * Single-Worker-Annahme des Brokers: siehe backend/services/checklist_events.py.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  openChecklistEvents,
  type ChecklistNode,
  type CollabNodeLock,
  type CollabPresenceUser,
} from '../../lib/api';

/** Live-Knoten-Event aus dem SSE-Stream (von einem ANDEREN Nutzer). */
export type RemoteNodeEvent =
  | { type: 'node_created'; node: ChecklistNode }
  | { type: 'node_updated'; node: ChecklistNode; changed_fields?: string[] }
  | { type: 'node_deleted'; node_id: string }
  | {
      type: 'node_moved';
      node: ChecklistNode;
      old_parent_id: string | null;
      new_parent_id: string | null;
    };

/**
 * Live-Diskussions-/Referenz-Event aus dem SSE-Stream (von ANDEREN Nutzern).
 * Der Inspector laedt bei diesen Events den betroffenen Knoten-Thread bzw. die
 * Referenz-Dokumente neu. Eigene Events werden vom Hook herausgefiltert.
 */
export type RemoteDiscussionEvent =
  | { type: 'comment_added'; node_id: string }
  | { type: 'comment_updated'; node_id: string }
  | { type: 'comment_deleted'; node_id: string }
  | { type: 'refdoc_added'; node_id: string }
  | { type: 'refdoc_deleted'; node_id: string };

type ConnState = 'connecting' | 'open' | 'reconnecting';

interface UseChecklistCollabOptions {
  templateId: string;
  /** Eigene Nutzerkennung — zum Herausfiltern eigener Events/Locks. */
  ownUserId: string | null;
  /**
   * Aktiv? (z. B. erst, wenn der Token/own user_id geladen sind). Solange false,
   * wird keine Verbindung aufgebaut.
   */
  enabled: boolean;
  /** Wird fuer FREMDE Knoten-Events aufgerufen (nicht fuer eigene). */
  onRemoteNode: (event: RemoteNodeEvent) => void;
  /**
   * Wird fuer FREMDE Diskussions-/Referenz-Events aufgerufen (nicht fuer eigene).
   * Optional — der TreeEditor reicht es nur durch, wenn ein Knoten offen ist.
   */
  onRemoteDiscussion?: (event: RemoteDiscussionEvent) => void;
}

interface UseChecklistCollabResult {
  /** Aktuell verbundene Nutzer (inkl. eigenem). */
  presence: CollabPresenceUser[];
  /** node_id → Lock-Halter (NUR Locks ANDERER Nutzer). */
  locks: Map<string, CollabNodeLock>;
  /** Verbindungszustand fuer eine dezente UI-Anzeige. */
  conn: ConnState;
}

// Backoff-Grenzen fuer den Reconnect.
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

interface InitEvent {
  type: 'init';
  users: CollabPresenceUser[];
  locks: CollabNodeLock[];
}
interface PresenceEvent {
  type: 'presence';
  event: 'join' | 'leave';
  user_id: string;
  users: CollabPresenceUser[];
}
interface LockAcquiredEvent extends CollabNodeLock {
  type: 'lock_acquired';
  user_id: string;
}
interface LockReleasedEvent {
  type: 'lock_released';
  node_id: string;
  user_id: string;
}

export function useChecklistCollab({
  templateId,
  ownUserId,
  enabled,
  onRemoteNode,
  onRemoteDiscussion,
}: UseChecklistCollabOptions): UseChecklistCollabResult {
  const [presence, setPresence] = useState<CollabPresenceUser[]>([]);
  const [locks, setLocks] = useState<Map<string, CollabNodeLock>>(new Map());
  const [conn, setConn] = useState<ConnState>('connecting');

  // Stabile Referenzen, damit der Verbindungs-Effekt nicht bei jedem Render neu
  // aufgebaut wird (der TreeEditor reicht hier ggf. eine inline-Funktion durch).
  // Ref-Updates erfolgen in einem Effekt (nicht waehrend des Renderns).
  const onRemoteNodeRef = useRef(onRemoteNode);
  const onRemoteDiscussionRef = useRef(onRemoteDiscussion);
  const ownUserIdRef = useRef(ownUserId);
  useEffect(() => {
    onRemoteNodeRef.current = onRemoteNode;
    onRemoteDiscussionRef.current = onRemoteDiscussion;
    ownUserIdRef.current = ownUserId;
  });

  /** Setzt einen Lock in die Map — aber nur, wenn er einem ANDEREN gehoert. */
  const upsertForeignLock = useCallback((lock: CollabNodeLock) => {
    setLocks((prev) => {
      const next = new Map(prev);
      if (lock.locked_by_id && lock.locked_by_id === ownUserIdRef.current) {
        // Eigener Lock — nicht als „fremd" markieren.
        next.delete(lock.node_id);
      } else {
        next.set(lock.node_id, lock);
      }
      return next;
    });
  }, []);

  const removeLock = useCallback((nodeId: string) => {
    setLocks((prev) => {
      if (!prev.has(nodeId)) return prev;
      const next = new Map(prev);
      next.delete(nodeId);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!enabled || !templateId) return;

    let closed = false;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const scheduleReconnect = () => {
      if (closed) return;
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
      attempt += 1;
      setConn('reconnecting');
      reconnectTimer = setTimeout(connect, delay);
    };

    const handleEvent = (raw: string) => {
      let data: unknown;
      try {
        data = JSON.parse(raw);
      } catch {
        return; // ungueltiges JSON ignorieren
      }
      if (!data || typeof data !== 'object') return;
      const ev = data as { type?: string };

      switch (ev.type) {
        case 'init': {
          const e = data as InitEvent;
          setPresence(e.users ?? []);
          const map = new Map<string, CollabNodeLock>();
          for (const lk of e.locks ?? []) {
            if (lk.locked_by_id && lk.locked_by_id !== ownUserIdRef.current) {
              map.set(lk.node_id, lk);
            }
          }
          setLocks(map);
          break;
        }
        case 'presence': {
          const e = data as PresenceEvent;
          setPresence(e.users ?? []);
          break;
        }
        case 'lock_acquired': {
          upsertForeignLock(data as LockAcquiredEvent);
          break;
        }
        case 'lock_released': {
          removeLock((data as LockReleasedEvent).node_id);
          break;
        }
        case 'node_created':
        case 'node_updated':
        case 'node_moved':
        case 'node_deleted': {
          const e = data as { user_id?: string } & RemoteNodeEvent;
          // Eigene Events NICHT erneut anwenden (optimistische Updates liegen
          // bereits vor) — nur fremde Aenderungen durchreichen.
          if (e.user_id && e.user_id === ownUserIdRef.current) break;
          onRemoteNodeRef.current(e);
          break;
        }
        case 'comment_added':
        case 'comment_updated':
        case 'comment_deleted':
        case 'refdoc_added':
        case 'refdoc_deleted': {
          const e = data as { user_id?: string; node_id?: string } & RemoteDiscussionEvent;
          // Eigene Diskussions-Events ueberspringen (lokal bereits angewandt).
          if (e.user_id && e.user_id === ownUserIdRef.current) break;
          if (e.node_id) onRemoteDiscussionRef.current?.(e);
          break;
        }
        default:
          break;
      }
    };

    const connect = () => {
      if (closed) return;
      setConn(attempt === 0 ? 'connecting' : 'reconnecting');
      const es = openChecklistEvents(templateId);
      source = es;

      es.onopen = () => {
        attempt = 0;
        setConn('open');
      };
      es.onmessage = (msg: MessageEvent<string>) => {
        // Heartbeat-Kommentare (": ping") liefert EventSource nicht als message
        // aus — sie werden vom Browser verworfen. Hier kommen nur data-Events an.
        handleEvent(msg.data);
      };
      es.onerror = () => {
        // EventSource versucht bei transienten Fehlern selbst zu reconnecten
        // (readyState CONNECTING). Nur bei hartem Abbruch (CLOSED) greifen wir
        // mit eigenem Backoff ein.
        if (es.readyState === EventSource.CLOSED) {
          es.close();
          if (source === es) source = null;
          scheduleReconnect();
        } else {
          setConn('reconnecting');
        }
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (source) source.close();
      // Beim Templatewechsel/Disable den Zustand verwerfen (Cleanup, nicht
      // Render) — das init-Event der naechsten Verbindung fuellt ihn neu.
      setPresence([]);
      setLocks(new Map());
      setConn('connecting');
    };
  }, [templateId, enabled, upsertForeignLock, removeLock]);

  return { presence, locks, conn };
}
