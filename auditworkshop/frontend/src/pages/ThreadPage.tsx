import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, MessageSquare, Loader2, Pin, Lock, CheckCircle2,
  ThumbsUp, Lightbulb, HelpCircle, Heart, Trash2, Edit3, Send, AlertTriangle,
} from 'lucide-react';
import { getWorkshopAuthHeaders } from '../lib/api';

interface Post {
  id: string;
  thread_id: string;
  parent_post_id: string | null;
  author_name: string | null;
  author_organization: string | null;
  body_md: string;
  created_at: string | null;
  updated_at: string | null;
  edit_count: number;
  reactions: Record<string, number>;
  user_reactions: string[];
  is_solution: boolean;
  can_edit: boolean;
}

interface ThreadDetail {
  id: string;
  slug: string;
  category: { id: string; slug: string; name: string };
  title: string;
  pinned: boolean;
  locked: boolean;
  solved_post_id: string | null;
  view_count: number;
  posts: Post[];
}

const REACTIONS = [
  { kind: 'helpful', icon: ThumbsUp, label: 'Hilfreich' },
  { kind: 'aha', icon: Lightbulb, label: 'Aha' },
  { kind: 'question', icon: HelpCircle, label: 'Frage' },
  { kind: 'thanks', icon: Heart, label: 'Danke' },
];

function formatDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
}

export default function ThreadPage() {
  const { threadId } = useParams<{ threadId: string }>();
  const navigate = useNavigate();
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reply, setReply] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const role = localStorage.getItem('workshop_role') || '';
  const isLoggedIn = !!localStorage.getItem('workshop_token');
  const isMod = role === 'moderator' || role === 'admin';

  const load = async () => {
    if (!threadId) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/forum/threads/${threadId}`, {
        headers: { ...getWorkshopAuthHeaders() },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setThread(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [threadId]);

  const onReply = async (e: FormEvent) => {
    e.preventDefault();
    if (!reply.trim()) return;
    setSubmitting(true);
    try {
      const r = await fetch(`/api/forum/threads/${threadId}/posts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
        body: JSON.stringify({ body_md: reply }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail || 'Antwort konnte nicht gespeichert werden.');
        return;
      }
      setReply('');
      await load();
    } finally {
      setSubmitting(false);
    }
  };

  const toggleReaction = async (postId: string, kind: string) => {
    if (!isLoggedIn) { setError('Bitte einloggen.'); return; }
    await fetch(`/api/forum/posts/${postId}/react?kind=${kind}`, {
      method: 'POST',
      headers: getWorkshopAuthHeaders(),
    });
    await load();
  };

  const editPost = async (postId: string) => {
    if (!editText.trim()) return;
    await fetch(`/api/forum/posts/${postId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
      body: JSON.stringify({ body_md: editText }),
    });
    setEditing(null);
    await load();
  };

  const deletePost = async (postId: string) => {
    if (!confirm('Beitrag wirklich löschen?')) return;
    await fetch(`/api/forum/posts/${postId}`, {
      method: 'DELETE',
      headers: getWorkshopAuthHeaders(),
    });
    await load();
  };

  const togglePin = async () => {
    await fetch(`/api/forum/threads/${threadId}/pin`, { method: 'POST', headers: getWorkshopAuthHeaders() });
    await load();
  };
  const toggleLock = async () => {
    await fetch(`/api/forum/threads/${threadId}/lock`, { method: 'POST', headers: getWorkshopAuthHeaders() });
    await load();
  };
  const markSolution = async (postId: string) => {
    await fetch(`/api/forum/threads/${threadId}/solve?post_id=${postId}`, {
      method: 'POST', headers: getWorkshopAuthHeaders(),
    });
    await load();
  };

  if (loading) return <div className="text-sm text-slate-500">Lädt…</div>;
  if (!thread) {
    return (
      <div className="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
        Thread nicht gefunden. {error}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link to={`/forum?c=${thread.category.slug}`}
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-cyan-600">
        <ArrowLeft size={16} /> {thread.category.name}
      </Link>

      <div className="rounded-3xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-start gap-3 justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              {thread.pinned && <span className="inline-flex items-center gap-1 text-[11px] text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full dark:text-amber-200 dark:bg-amber-900/40"><Pin size={11} />angepinnt</span>}
              {thread.locked && <span className="inline-flex items-center gap-1 text-[11px] text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full dark:text-slate-200 dark:bg-slate-800"><Lock size={11} />gesperrt</span>}
              {thread.solved_post_id && <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full dark:text-emerald-200 dark:bg-emerald-900/40"><CheckCircle2 size={11} />beantwortet</span>}
            </div>
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">{thread.title}</h1>
            <p className="mt-1 text-xs text-slate-500">{thread.view_count} Aufrufe</p>
          </div>
          {isMod && (
            <div className="flex flex-wrap gap-1">
              <button onClick={togglePin} className="text-xs px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                <Pin size={12} className="inline mr-1" />{thread.pinned ? 'Lösen' : 'Pinnen'}
              </button>
              <button onClick={toggleLock} className="text-xs px-2 py-1 rounded border border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                <Lock size={12} className="inline mr-1" />{thread.locked ? 'Öffnen' : 'Sperren'}
              </button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="space-y-3">
        {thread.posts.map((p, i) => (
          <article key={p.id}
            className={`rounded-2xl border bg-white p-5 dark:bg-slate-900 ${
              p.is_solution
                ? 'border-emerald-300 dark:border-emerald-700'
                : 'border-slate-200 dark:border-slate-800'
            }`}>
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-cyan-100 text-cyan-700 font-semibold dark:bg-cyan-900/40 dark:text-cyan-200">
                {(p.author_name || '?').slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-sm font-semibold text-slate-900 dark:text-white">{p.author_name || 'Anonym'}</span>
                  {p.author_organization && <span className="text-xs text-slate-500">{p.author_organization}</span>}
                  <span className="text-xs text-slate-400 ml-auto">
                    {i === 0 ? 'Eröffnungspost' : `Antwort #${i}`} · {formatDate(p.created_at)}
                    {p.edit_count > 0 && ` · ${p.edit_count}× bearb.`}
                  </span>
                </div>
                {editing === p.id ? (
                  <div className="mt-3 space-y-2">
                    <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={5}
                      className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800" />
                    <div className="flex gap-2">
                      <button onClick={() => editPost(p.id)} className="text-xs px-3 py-1.5 rounded bg-cyan-600 text-white hover:bg-cyan-700">Speichern</button>
                      <button onClick={() => setEditing(null)} className="text-xs px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-50 dark:border-slate-700">Abbrechen</button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 prose prose-sm max-w-none text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {p.body_md}
                  </div>
                )}

                <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
                  {REACTIONS.map(({ kind, icon: Icon, label }) => {
                    const count = p.reactions[kind] || 0;
                    const isActive = p.user_reactions.includes(kind);
                    return (
                      <button key={kind}
                        onClick={() => toggleReaction(p.id, kind)}
                        title={label}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 transition ${
                          isActive
                            ? 'border-cyan-400 bg-cyan-50 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-200'
                            : 'border-slate-200 hover:border-slate-300 text-slate-600 dark:border-slate-700 dark:text-slate-400'
                        }`}>
                        <Icon size={11} />
                        {count > 0 && <span>{count}</span>}
                      </button>
                    );
                  })}
                  <span className="ml-auto inline-flex gap-2">
                    {p.can_edit && (
                      <>
                        <button onClick={() => { setEditing(p.id); setEditText(p.body_md); }}
                          className="text-slate-400 hover:text-cyan-600">
                          <Edit3 size={12} />
                        </button>
                        <button onClick={() => deletePost(p.id)} className="text-slate-400 hover:text-rose-600">
                          <Trash2 size={12} />
                        </button>
                      </>
                    )}
                    {(isMod || (i > 0 && thread.posts[0].author_name === localStorage.getItem('workshop_name'))) && i > 0 && (
                      <button onClick={() => markSolution(p.id)}
                        className={`text-xs px-2 py-0.5 rounded ${
                          p.is_solution ? 'bg-emerald-100 text-emerald-800' : 'border border-slate-300 hover:bg-emerald-50'
                        }`}>
                        <CheckCircle2 size={11} className="inline mr-0.5" />
                        {p.is_solution ? 'Lösung' : 'Als Lösung'}
                      </button>
                    )}
                  </span>
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* Reply-Box */}
      {thread.locked ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          <Lock size={14} className="inline mr-1" /> Dieser Thread ist gesperrt.
        </div>
      ) : isLoggedIn ? (
        <form onSubmit={onReply} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-2 mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
            <MessageSquare size={14} /> Antworten
          </div>
          <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={4}
            placeholder="Ihr Beitrag (Markdown unterstützt)…"
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-200 dark:border-slate-700 dark:bg-slate-800" />
          <div className="mt-2 flex justify-end">
            <button type="submit" disabled={submitting || !reply.trim()}
              className="inline-flex items-center gap-2 rounded-full bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-50">
              {submitting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              Antwort senden
            </button>
          </div>
        </form>
      ) : (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          Zum Mitdiskutieren bitte <button onClick={() => navigate('/login')} className="underline hover:no-underline">anmelden</button> oder
          <button onClick={() => navigate('/signup')} className="underline hover:no-underline ml-1">Konto erstellen</button>.
        </div>
      )}
    </div>
  );
}
