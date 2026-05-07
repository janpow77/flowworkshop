import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  MessageSquare, MessagesSquare, Plus, Pin, Lock, CheckCircle2,
  Clock, User2, Search, Sparkles, Calendar, Calculator, Scale, Wrench,
} from 'lucide-react';

interface Category {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  thread_count: number;
  post_count: number;
  last_post_at: string | null;
}

interface ThreadSummary {
  id: string;
  slug: string;
  category_slug: string;
  category_name: string;
  title: string;
  author_name: string | null;
  author_organization: string | null;
  created_at: string | null;
  last_post_at: string | null;
  post_count: number;
  view_count: number;
  pinned: boolean;
  locked: boolean;
  solved: boolean;
}

const ICON_MAP: Record<string, typeof MessageSquare> = {
  MessagesSquare, Calendar, Sparkles, Calculator, Scale, Wrench,
};

const COLOR_MAP: Record<string, string> = {
  slate: 'from-slate-500/15 to-slate-500/5 border-slate-200 text-slate-700 dark:text-slate-200 dark:border-slate-700',
  cyan: 'from-cyan-500/15 to-cyan-500/5 border-cyan-200 text-cyan-700 dark:text-cyan-200 dark:border-cyan-800',
  violet: 'from-violet-500/15 to-violet-500/5 border-violet-200 text-violet-700 dark:text-violet-200 dark:border-violet-800',
  emerald: 'from-emerald-500/15 to-emerald-500/5 border-emerald-200 text-emerald-700 dark:text-emerald-200 dark:border-emerald-800',
  amber: 'from-amber-500/15 to-amber-500/5 border-amber-200 text-amber-700 dark:text-amber-200 dark:border-amber-800',
  indigo: 'from-indigo-500/15 to-indigo-500/5 border-indigo-200 text-indigo-700 dark:text-indigo-200 dark:border-indigo-800',
  rose: 'from-rose-500/15 to-rose-500/5 border-rose-200 text-rose-700 dark:text-rose-200 dark:border-rose-800',
};

function formatRelative(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const min = Math.round((Date.now() - d.getTime()) / 60000);
  if (min < 1) return 'gerade eben';
  if (min < 60) return `vor ${min} Min`;
  const h = Math.round(min / 60);
  if (h < 24) return `vor ${h} Std`;
  const day = Math.round(h / 24);
  if (day < 30) return `vor ${day} Tag${day === 1 ? '' : 'en'}`;
  return d.toLocaleDateString('de-DE');
}

export default function ForumPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [categories, setCategories] = useState<Category[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState<'latest' | 'top' | 'unanswered'>('latest');
  const activeCategory = params.get('c') || '';
  const isLoggedIn = !!localStorage.getItem('workshop_token');

  useEffect(() => {
    setLoading(true);
    const url = activeCategory
      ? `/api/forum/threads?category=${activeCategory}&sort=${sort}`
      : `/api/forum/threads?sort=${sort}`;
    Promise.all([
      fetch('/api/forum/categories').then((r) => r.ok ? r.json() : []),
      fetch(url).then((r) => r.ok ? r.json() : []),
    ]).then(([cats, ths]) => {
      setCategories(cats);
      setThreads(ths);
    }).finally(() => setLoading(false));
  }, [activeCategory, sort]);

  const visibleThreads = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter((t) =>
      t.title.toLowerCase().includes(q)
      || (t.author_name || '').toLowerCase().includes(q)
      || (t.category_name || '').toLowerCase().includes(q),
    );
  }, [threads, filter]);

  const totalPosts = useMemo(
    () => categories.reduce((acc, c) => acc + c.post_count, 0),
    [categories],
  );

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[28px] border border-white/70 bg-[linear-gradient(135deg,rgba(8,47,73,0.98),rgba(14,116,144,0.94)_45%,rgba(14,165,233,0.85))] px-7 py-7 text-white shadow-[0_24px_80px_-50px_rgba(15,23,42,0.95)]">
        <div className="flex flex-wrap items-center gap-4 justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-100/70">
              <MessagesSquare size={11} className="inline mr-1" /> Forum
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Diskussion</h1>
            <p className="mt-2 text-sm text-white/80">
              {categories.length} Kategorien · {totalPosts} Beiträge gesamt
            </p>
          </div>
          {isLoggedIn && (
            <button
              onClick={() => navigate(`/forum/new${activeCategory ? `?c=${activeCategory}` : ''}`)}
              className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50">
              <Plus size={14} /> Neuer Thread
            </button>
          )}
        </div>
      </section>

      {/* Kategorien-Auswahl */}
      <section>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <button
            onClick={() => setParams({})}
            className={`text-left rounded-2xl border bg-gradient-to-br p-4 transition hover:shadow-md ${
              !activeCategory ? 'ring-2 ring-cyan-400 ' : ''
            } ${COLOR_MAP.slate}`}
          >
            <div className="flex items-center gap-2 mb-1">
              <MessagesSquare size={16} />
              <span className="text-sm font-semibold">Alle Stränge</span>
            </div>
            <div className="text-xs opacity-70">{threads.length} sichtbar</div>
          </button>
          {categories.map((c) => {
            const Icon = (c.icon && ICON_MAP[c.icon]) || MessageSquare;
            const cls = COLOR_MAP[c.color || 'slate'] || COLOR_MAP.slate;
            return (
              <button
                key={c.id}
                onClick={() => setParams({ c: c.slug })}
                className={`text-left rounded-2xl border bg-gradient-to-br p-4 transition hover:shadow-md ${
                  activeCategory === c.slug ? 'ring-2 ring-cyan-400 ' : ''
                } ${cls}`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <Icon size={16} />
                  <span className="text-sm font-semibold">{c.name}</span>
                </div>
                {c.description && <p className="text-xs opacity-70 line-clamp-2 mb-1">{c.description}</p>}
                <div className="text-xs opacity-70">
                  {c.thread_count} Stränge · {c.post_count} Beiträge
                  {c.last_post_at && ` · ${formatRelative(c.last_post_at)}`}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Filter */}
      <section className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input type="search" value={filter} onChange={(e) => setFilter(e.target.value)}
            placeholder="Titel, Autor, Kategorie suchen…"
            className="w-full rounded-2xl border border-slate-200 bg-white py-2.5 pl-9 pr-4 text-sm shadow-sm focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-200 dark:border-slate-700 dark:bg-slate-900" />
        </div>
        <div className="flex items-center gap-1 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
          {(['latest', 'top', 'unanswered'] as const).map((s) => (
            <button key={s} onClick={() => setSort(s)}
              className={`text-xs px-3 py-1.5 rounded-xl ${
                sort === s ? 'bg-white text-cyan-700 shadow dark:bg-slate-700 dark:text-cyan-300' : 'text-slate-600 dark:text-slate-300'
              }`}>
              {s === 'latest' ? 'Neueste' : s === 'top' ? 'Top' : 'Unbeantwortet'}
            </button>
          ))}
        </div>
      </section>

      {/* Thread-Liste */}
      <section className="space-y-2">
        {loading && <div className="text-sm text-slate-500">Lädt…</div>}
        {!loading && visibleThreads.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40">
            Keine Stränge gefunden.
          </div>
        )}
        {visibleThreads.map((t) => (
          <Link
            key={t.id}
            to={`/forum/t/${t.id}`}
            className="block rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-cyan-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-cyan-700"
          >
            <div className="flex items-start gap-3">
              <div className="flex flex-col items-center justify-center min-w-[60px] text-center">
                <div className="text-2xl font-bold text-slate-700 dark:text-slate-200">{t.post_count}</div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400">Beiträge</div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-400">
                  {t.pinned && <Pin size={10} className="text-amber-500" />}
                  {t.locked && <Lock size={10} className="text-slate-500" />}
                  {t.solved && <CheckCircle2 size={10} className="text-emerald-500" />}
                  <span>{t.category_name}</span>
                </div>
                <h3 className="mt-1 text-base font-semibold text-slate-900 dark:text-white line-clamp-1">
                  {t.title}
                </h3>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <User2 size={11} />
                  <span>{t.author_name || 'Anonym'}</span>
                  {t.author_organization && <span className="opacity-70">· {t.author_organization}</span>}
                  <span className="opacity-50">·</span>
                  <Clock size={11} />
                  <span>{formatRelative(t.last_post_at || t.created_at)}</span>
                </div>
              </div>
              <div className="text-right text-[10px] text-slate-400 hidden sm:block">
                {t.view_count} Aufrufe
              </div>
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
