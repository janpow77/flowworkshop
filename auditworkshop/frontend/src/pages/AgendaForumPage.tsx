import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, MessageSquare, Send, Trash2 } from 'lucide-react';

interface AgendaItem {
  id: string;
  day: number;
  time: string;
  duration_minutes: number;
  item_type: string;
  title: string;
  speaker: string | null;
  note: string | null;
  category: string;
  status: string;
  scenario_id: number | null;
  page_url: string | null;
}

interface ForumPost {
  id: string;
  agenda_item_id: string;
  author_registration_id: string | null;
  title: string;
  body: string;
  author_name: string;
  author_organization: string | null;
  author_role: string;
  created_at: string | null;
}

interface ForumThread {
  item: AgendaItem;
  post_count: number;
  posts: ForumPost[];
}

interface MeResponse {
  user_id?: string;
  name: string;
  organization: string;
  role: string;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('workshop_token') || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function formatDateTime(value: string | null): string {
  if (!value) return 'gerade eben';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
}

export default function AgendaForumPage() {
  const { itemId } = useParams<{ itemId: string }>();
  const [thread, setThread] = useState<ForumThread | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const loadThread = async () => {
    if (!itemId) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/event/agenda/${itemId}/forum`);
      if (!res.ok) throw new Error('Forum konnte nicht geladen werden.');
      setThread(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Forum konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadThread();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId]);

  useEffect(() => {
    const token = localStorage.getItem('workshop_token');
    if (!token) return;
    fetch('/api/auth/me', { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setMe(data))
      .catch(() => setMe(null));
  }, []);

  const handleSubmit = async () => {
    if (!itemId || !title.trim() || !body.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const res = await fetch(`/api/event/agenda/${itemId}/forum/posts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
        body: JSON.stringify({
          title: title.trim(),
          body: body.trim(),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setTitle('');
      setBody('');
      await loadThread();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Beitrag konnte nicht erstellt werden.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (postId: string) => {
    if (!itemId) return;
    if (!window.confirm('Beitrag wirklich löschen?')) return;
    try {
      const res = await fetch(`/api/event/agenda/${itemId}/forum/posts/${postId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await res.text());
      await loadThread();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Beitrag konnte nicht gelöscht werden.');
    }
  };

  const canPost = Boolean(localStorage.getItem('workshop_token'));

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link to="/agenda" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600">
        <ArrowLeft size={16} /> Zur Tagesordnung
      </Link>

      {loading && (
        <div className="rounded-3xl border border-slate-200 bg-white/90 p-8 text-sm text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900/80">
          Diskussion wird geladen…
        </div>
      )}

      {!loading && !thread && error && (
        <div className="rounded-3xl border border-red-200 bg-red-50/90 p-8 text-sm text-red-700 shadow-sm dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      )}

      {!loading && thread && (
        <>
          <section className="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-[0_28px_80px_-56px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/80">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-600/80 dark:text-cyan-300/70">
                  Diskussionsraum zum Programmpunkt
                </div>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
                  {thread.item.title}
                </h1>
                <div className="text-sm text-slate-500 dark:text-slate-400">
                  {thread.item.time} · {thread.item.duration_minutes} Minuten
                  {thread.item.speaker ? ` · ${thread.item.speaker}` : ''}
                </div>
                <div className="text-xs text-slate-400 dark:text-slate-500">
                  Beiträge bleiben am Programmpunkt erhalten, auch wenn Uhrzeit oder Reihenfolge später geändert werden.
                </div>
                {thread.item.note && (
                  <p className="max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                    {thread.item.note}
                  </p>
                )}
              </div>
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
                <div className="font-medium">{thread.post_count} Beiträge</div>
                <div className="text-xs opacity-80">Bindung an Programmpunkt-ID, nicht an Uhrzeit</div>
              </div>
            </div>
          </section>

          <section className="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-[0_28px_80px_-56px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/80">
            <div className="mb-4 flex items-center gap-2 text-slate-900 dark:text-white">
              <MessageSquare size={18} />
              <h2 className="text-lg font-semibold">Beitrag verfassen</h2>
            </div>

            {!canPost ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                Zum Schreiben bitte zuerst über die Workshop-Anmeldung einloggen.
              </div>
            ) : (
              <div className="space-y-3">
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Kurzer Titel für Ihren Beitrag"
                  className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
                />
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder="Ihre Frage, Ihr Hinweis oder Ihr Erfahrungsbeitrag zum Programmpunkt"
                  rows={6}
                  className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
                />
                <div className="flex items-center justify-between gap-3">
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    Sichtbar für eingeloggte Workshop-Teilnehmer und Moderatoren.
                  </div>
                  <button
                    type="button"
                    disabled={submitting || !title.trim() || !body.trim()}
                    onClick={handleSubmit}
                    className="inline-flex items-center gap-2 rounded-full bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Send size={15} />
                    {submitting ? 'Sende…' : 'Beitrag veröffentlichen'}
                  </button>
                </div>
              </div>
            )}

            {error && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>
            )}
          </section>

          <section className="space-y-4">
            {thread.posts.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-slate-300 bg-white/80 p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/70">
                Noch keine Beiträge zu diesem Programmpunkt.
              </div>
            ) : (
              thread.posts.map((post) => {
                const canDelete =
                  me?.role === 'moderator' ||
                  (me?.user_id && me.user_id === post.author_registration_id);

                return (
                  <article key={post.id} className="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-[0_24px_70px_-58px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/80">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{post.title}</h3>
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                          {post.author_name}
                          {post.author_organization ? ` · ${post.author_organization}` : ''}
                          {post.author_role === 'moderator' ? ' · Moderator' : ''}
                          {' · '}
                          {formatDateTime(post.created_at)}
                        </div>
                      </div>
                      {canDelete && (
                        <button
                          type="button"
                          onClick={() => handleDelete(post.id)}
                          className="rounded-full border border-red-200 px-3 py-1.5 text-xs text-red-600 transition hover:bg-red-50 dark:border-red-900/60 dark:text-red-400 dark:hover:bg-red-950/20"
                        >
                          <span className="inline-flex items-center gap-1">
                            <Trash2 size={12} />
                            Löschen
                          </span>
                        </button>
                      )}
                    </div>
                    <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-700 dark:text-slate-200">
                      {post.body}
                    </p>
                  </article>
                );
              })
            )}
          </section>
        </>
      )}
    </div>
  );
}
