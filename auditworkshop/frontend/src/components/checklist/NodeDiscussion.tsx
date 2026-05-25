/**
 * flowworkshop · components/checklist/NodeDiscussion.tsx
 *
 * Team-Diskussion pro Knoten (Team-Zone des Inspectors): Thread aus
 * GET /{id}/nodes/{nodeId}/comments — Wurzelbeitraege mit genau einer
 * Antwort-Ebene (eingerueckt). Neue Beitraege/Antworten via POST, eigene
 * Beitraege via PUT/DELETE bearbeiten/loeschen. Beim Oeffnen werden die
 * Kommentare als gelesen markiert (mark-read).
 *
 * Live: Der Inspector reicht SSE-Events (comment_added/updated/deleted) als
 * ``liveSignal`` durch — der Thread wird dann neu geladen.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  MessageSquare, Send, Loader2, CornerDownRight, Pencil, Trash2, X, Check,
} from 'lucide-react';
import {
  addComment, deleteComment, editComment, getNodeComments, markNodeRead,
  type NodeComment,
} from '../../lib/api';

interface NodeDiscussionProps {
  templateId: string;
  nodeId: string;
  /** Eigene Nutzerkennung — fuer Edit/Delete-Rechte am eigenen Beitrag. */
  ownUserId: string | null;
  /** Mindestens Kommentator — darf Beitraege verfassen. */
  canComment: boolean;
  /** Wechselt bei eingehenden comment-SSE-Events, loest Neuladen aus. */
  liveSignal: number;
}

function formatTs(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

export default function NodeDiscussion({
  templateId, nodeId, ownUserId, canComment, liveSignal,
}: NodeDiscussionProps) {
  const [comments, setComments] = useState<NodeComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState('');
  // Aktiver Antwort-/Editier-Zustand.
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [replyText, setReplyText] = useState('');
  const [editId, setEditId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');

  const load = useCallback(async () => {
    try {
      const rows = await getNodeComments(templateId, nodeId);
      setComments(rows);
      setError('');
    } catch {
      setError('Diskussion konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, [templateId, nodeId]);

  // Initial + bei Live-Signal neu laden.
  useEffect(() => { void load(); }, [load, liveSignal]);

  // Beim Oeffnen eines Knotens als gelesen markieren (best-effort).
  const markedRef = useRef<string | null>(null);
  useEffect(() => {
    if (markedRef.current === nodeId) return;
    markedRef.current = nodeId;
    markNodeRead(templateId, nodeId).catch(() => { /* unkritisch */ });
  }, [templateId, nodeId]);

  const postRoot = async () => {
    const msg = draft.trim();
    if (!msg) return;
    setPosting(true);
    setError('');
    try {
      const created = await addComment(templateId, nodeId, msg);
      setComments((prev) => [...prev, created]);
      setDraft('');
    } catch {
      setError('Beitrag konnte nicht gespeichert werden.');
    } finally {
      setPosting(false);
    }
  };

  const postReply = async (parentId: string) => {
    const msg = replyText.trim();
    if (!msg) return;
    setPosting(true);
    setError('');
    try {
      const created = await addComment(templateId, nodeId, msg, parentId);
      setComments((prev) => prev.map((c) =>
        c.id === parentId ? { ...c, replies: [...c.replies, created] } : c,
      ));
      setReplyText('');
      setReplyTo(null);
    } catch {
      setError('Antwort konnte nicht gespeichert werden.');
    } finally {
      setPosting(false);
    }
  };

  const saveEdit = async (commentId: string) => {
    const msg = editText.trim();
    if (!msg) return;
    setPosting(true);
    try {
      const updated = await editComment(templateId, commentId, msg);
      setComments((prev) => prev.map((c) => {
        if (c.id === commentId) return { ...c, ...updated, replies: c.replies };
        return { ...c, replies: c.replies.map((r) => (r.id === commentId ? { ...r, ...updated, replies: [] } : r)) };
      }));
      setEditId(null);
      setEditText('');
    } catch {
      setError('Änderung konnte nicht gespeichert werden.');
    } finally {
      setPosting(false);
    }
  };

  const removeComment = async (commentId: string) => {
    if (!confirm('Diesen Beitrag löschen?')) return;
    try {
      await deleteComment(templateId, commentId);
      await load();
    } catch {
      setError('Beitrag konnte nicht gelöscht werden.');
    }
  };

  const renderComment = (c: NodeComment, isReply: boolean) => {
    const mine = !!ownUserId && c.author_id === ownUserId && !c.is_deleted;
    const editing = editId === c.id;
    return (
      <div
        key={c.id}
        className={`rounded-lg border px-2.5 py-2 ${
          c.is_deleted
            ? 'border-slate-200 bg-slate-50 dark:border-slate-700/60 dark:bg-slate-800/40'
            : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800/70'
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-[11px] font-semibold text-slate-600 dark:text-slate-300">
            {c.is_deleted ? '—' : (c.author_name || 'Unbekannt')}
          </span>
          <span className="shrink-0 text-[10px] text-slate-400">
            {formatTs(c.created_at)}{c.edited_at ? ' · bearb.' : ''}
          </span>
        </div>

        {editing ? (
          <div className="mt-1.5 space-y-1.5">
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            />
            <div className="flex items-center justify-end gap-1.5">
              <button
                type="button"
                onClick={() => { setEditId(null); setEditText(''); }}
                className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11px] text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <X size={11} /> Abbrechen
              </button>
              <button
                type="button"
                onClick={() => saveEdit(c.id)}
                disabled={posting || !editText.trim()}
                className="inline-flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-blue-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
              >
                <Check size={11} /> Speichern
              </button>
            </div>
          </div>
        ) : (
          <p className={`mt-1 whitespace-pre-wrap break-words text-xs ${
            c.is_deleted ? 'italic text-slate-400' : 'text-slate-700 dark:text-slate-200'
          }`}>
            {c.message}
          </p>
        )}

        {!c.is_deleted && !editing && (
          <div className="mt-1 flex items-center gap-2">
            {canComment && !isReply && (
              <button
                type="button"
                onClick={() => { setReplyTo(c.id); setReplyText(''); }}
                className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-blue-600 dark:hover:text-blue-400"
              >
                <CornerDownRight size={11} /> Antworten
              </button>
            )}
            {mine && (
              <>
                <button
                  type="button"
                  onClick={() => { setEditId(c.id); setEditText(c.message); }}
                  className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-blue-600 dark:hover:text-blue-400"
                >
                  <Pencil size={11} /> Bearbeiten
                </button>
                <button
                  type="button"
                  onClick={() => removeComment(c.id)}
                  className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-red-600 dark:hover:text-red-400"
                >
                  <Trash2 size={11} /> Löschen
                </button>
              </>
            )}
          </div>
        )}

        {/* Antwort-Eingabe (nur fuer Wurzelbeitraege) */}
        {replyTo === c.id && (
          <div className="mt-2 space-y-1.5">
            <textarea
              autoFocus
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              rows={2}
              placeholder="Antwort verfassen…"
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            />
            <div className="flex items-center justify-end gap-1.5">
              <button
                type="button"
                onClick={() => { setReplyTo(null); setReplyText(''); }}
                className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11px] text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <X size={11} /> Abbrechen
              </button>
              <button
                type="button"
                onClick={() => postReply(c.id)}
                disabled={posting || !replyText.trim()}
                className="inline-flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-blue-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
              >
                <Send size={11} /> Senden
              </button>
            </div>
          </div>
        )}

        {/* Antworten (eine Ebene, eingerueckt) */}
        {c.replies.length > 0 && (
          <div className="mt-2 space-y-1.5 border-l-2 border-slate-200 pl-2.5 dark:border-slate-700">
            {c.replies.map((r) => renderComment(r, true))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
        <MessageSquare size={12} /> Team-Diskussion
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-2 text-xs text-slate-400">
          <Loader2 size={13} className="animate-spin" /> Lädt…
        </div>
      ) : comments.length === 0 ? (
        <p className="py-1 text-xs italic text-slate-400 dark:text-slate-500">
          Noch keine Beiträge — starten Sie die Abstimmung.
        </p>
      ) : (
        <div className="space-y-1.5">
          {comments.map((c) => renderComment(c, false))}
        </div>
      )}

      {canComment && (
        <div className="mt-2 space-y-1.5">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder="Neuen Beitrag verfassen…"
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={postRoot}
              disabled={posting || !draft.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:bg-slate-300 dark:disabled:bg-slate-700"
            >
              {posting ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} Beitrag senden
            </button>
          </div>
        </div>
      )}

      {error && <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}
