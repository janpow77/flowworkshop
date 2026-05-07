import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  MessageSquare, MessagesSquare, ArrowRight, Search, Clock, User2, Sparkles,
} from 'lucide-react';

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

interface ForumSummaryEntry {
  agenda_item_id: string;
  post_count: number;
  last_post_at: string | null;
}

interface ForumPostPreview {
  id: string;
  title: string;
  body: string;
  author_name: string;
  author_organization: string | null;
  created_at: string | null;
  agenda_item_id: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  workshop1: 'Workshop 1 · Methodenüberblick',
  workshop2: 'Workshop 2 · Auditmanagement',
  workshop3: 'Workshop 3 · KI in der Verwaltung',
  workshop4: 'Workshop 4 · Datenschutz',
  workshop5: 'Workshop 5 · KI für EFRE-Prüfung',
  workshop6: 'Workshop 6 · Praxisbeispiele',
  rahmen: 'Rahmenprogramm',
  diskussion: 'Diskussion',
  vortrag: 'Vortrag',
};

function formatRelative(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diffMs = Date.now() - d.getTime();
  const min = Math.round(diffMs / 60000);
  if (min < 1) return 'gerade eben';
  if (min < 60) return `vor ${min} Min`;
  const h = Math.round(min / 60);
  if (h < 24) return `vor ${h} Std`;
  const day = Math.round(h / 24);
  if (day < 30) return `vor ${day} Tag${day === 1 ? '' : 'en'}`;
  return d.toLocaleDateString('de-DE');
}

function categoryColor(cat: string): string {
  const palette: Record<string, string> = {
    workshop1: 'from-sky-500/15 to-sky-500/5 border-sky-200 text-sky-700 dark:text-sky-200 dark:border-sky-800',
    workshop2: 'from-violet-500/15 to-violet-500/5 border-violet-200 text-violet-700 dark:text-violet-200 dark:border-violet-800',
    workshop3: 'from-emerald-500/15 to-emerald-500/5 border-emerald-200 text-emerald-700 dark:text-emerald-200 dark:border-emerald-800',
    workshop4: 'from-amber-500/15 to-amber-500/5 border-amber-200 text-amber-700 dark:text-amber-200 dark:border-amber-800',
    workshop5: 'from-cyan-500/15 to-cyan-500/5 border-cyan-200 text-cyan-700 dark:text-cyan-200 dark:border-cyan-800',
    workshop6: 'from-rose-500/15 to-rose-500/5 border-rose-200 text-rose-700 dark:text-rose-200 dark:border-rose-800',
    diskussion: 'from-indigo-500/15 to-indigo-500/5 border-indigo-200 text-indigo-700 dark:text-indigo-200 dark:border-indigo-800',
    rahmen: 'from-slate-500/15 to-slate-500/5 border-slate-200 text-slate-700 dark:text-slate-200 dark:border-slate-700',
    vortrag: 'from-fuchsia-500/15 to-fuchsia-500/5 border-fuchsia-200 text-fuchsia-700 dark:text-fuchsia-200 dark:border-fuchsia-800',
  };
  return palette[cat] || 'from-slate-500/10 to-slate-500/5 border-slate-200 text-slate-700 dark:text-slate-200 dark:border-slate-700';
}

export default function ForumPage() {
  const [items, setItems] = useState<AgendaItem[]>([]);
  const [summary, setSummary] = useState<ForumSummaryEntry[]>([]);
  const [latestPosts, setLatestPosts] = useState<ForumPostPreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [showOnlyWithPosts, setShowOnlyWithPosts] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [agendaRes, summaryRes] = await Promise.all([
          fetch('/api/event/agenda'),
          fetch('/api/event/forum/summary'),
        ]);
        if (!agendaRes.ok) throw new Error('Tagesordnung konnte nicht geladen werden.');
        if (!summaryRes.ok) throw new Error('Forum-Übersicht konnte nicht geladen werden.');
        const agenda = (await agendaRes.json()) as AgendaItem[];
        const sum = (await summaryRes.json()) as { items: ForumSummaryEntry[] };
        if (cancelled) return;
        setItems(agenda);
        setSummary(sum.items || []);

        // Letzte Beiträge: Top-5 nach last_post_at sammeln (eine Anfrage pro Top-Item)
        const top5 = [...(sum.items || [])]
          .filter((s) => s.post_count > 0)
          .sort((a, b) => (b.last_post_at || '').localeCompare(a.last_post_at || ''))
          .slice(0, 5);
        const previews: ForumPostPreview[] = [];
        for (const entry of top5) {
          try {
            const r = await fetch(`/api/event/agenda/${entry.agenda_item_id}/forum`);
            if (!r.ok) continue;
            const t = await r.json();
            const last = (t.posts || [])[t.posts.length - 1];
            if (last) previews.push({ ...last, agenda_item_id: entry.agenda_item_id });
          } catch { /* einzelner Fehler stoppt nicht die Übersicht */ }
        }
        if (!cancelled) setLatestPosts(previews);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Forum konnte nicht geladen werden.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  const summaryById = useMemo(() => {
    const map = new Map<string, ForumSummaryEntry>();
    for (const s of summary) map.set(s.agenda_item_id, s);
    return map;
  }, [summary]);

  const totalPosts = summary.reduce((acc, s) => acc + s.post_count, 0);
  const activeThreads = summary.filter((s) => s.post_count > 0).length;

  // Filter: Suche im Titel + nur Items mit Beiträgen (optional)
  const visibleItems = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return items.filter((it) => {
      if (it.item_type === 'pause') return false;
      const sum = summaryById.get(it.id);
      if (showOnlyWithPosts && (!sum || sum.post_count === 0)) return false;
      if (!q) return true;
      const haystack = [it.title, it.speaker, it.note, CATEGORY_LABELS[it.category] || it.category]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [items, summaryById, showOnlyWithPosts, filter]);

  // Gruppierung nach Tag
  const byDay = useMemo(() => {
    const groups = new Map<number, AgendaItem[]>();
    for (const it of visibleItems) {
      const arr = groups.get(it.day) || [];
      arr.push(it);
      groups.set(it.day, arr);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a - b);
  }, [visibleItems]);

  const itemsById = useMemo(() => {
    const m = new Map<string, AgendaItem>();
    for (const it of items) m.set(it.id, it);
    return m;
  }, [items]);

  return (
    <div className="space-y-8">
      {/* ── Hero ────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(8,47,73,0.98),rgba(14,116,144,0.94)_45%,rgba(14,165,233,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.4fr_0.6fr]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-white/80">
              <MessagesSquare size={13} /> Diskussion · Workshop 2026
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight lg:text-4xl">Forum</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-white/85 lg:text-base">
              Fragen, Erfahrungsberichte und offene Punkte zu jedem Programmpunkt der Tagesordnung.
              Alle Beiträge sind an die Programmpunkt-ID gebunden — Verschiebungen oder Umstellungen
              ändern nichts an der Zuordnung.
            </p>
          </div>
          <div className="rounded-[28px] border border-white/15 bg-black/15 p-5 backdrop-blur">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/60">Aktivität</div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-center">
              <div className="rounded-2xl border border-white/10 bg-white/5 px-2 py-3">
                <div className="text-[10px] uppercase tracking-wider text-white/60">Stränge</div>
                <div className="mt-1 text-2xl font-semibold">{activeThreads}</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-2 py-3">
                <div className="text-[10px] uppercase tracking-wider text-white/60">Beiträge</div>
                <div className="mt-1 text-2xl font-semibold">{totalPosts}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Letzte Beiträge ──────────────────────────────────────── */}
      {latestPosts.length > 0 && (
        <section className="rounded-[28px] border border-slate-200/70 bg-white/85 p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
            <Sparkles size={16} className="text-cyan-500" />
            Letzte Beiträge
          </div>
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {latestPosts.map((p) => {
              const item = itemsById.get(p.agenda_item_id);
              return (
                <Link key={p.id}
                  to={`/agenda/forum/${p.agenda_item_id}`}
                  className="group block rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-cyan-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-cyan-700"
                >
                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    <Clock size={11} />
                    {formatRelative(p.created_at)}
                    {item?.title && (
                      <span className="ml-auto truncate text-slate-500 normal-case font-normal" title={item.title}>
                        {item.title.slice(0, 36)}{item.title.length > 36 ? '…' : ''}
                      </span>
                    )}
                  </div>
                  <h3 className="mt-2 text-sm font-semibold text-slate-900 line-clamp-2 dark:text-white group-hover:text-cyan-700 dark:group-hover:text-cyan-300">
                    {p.title || '(ohne Titel)'}
                  </h3>
                  <p className="mt-1 text-xs leading-5 text-slate-600 line-clamp-3 dark:text-slate-400">
                    {p.body}
                  </p>
                  <div className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                    <User2 size={11} />
                    <span className="font-medium">{p.author_name}</span>
                    {p.author_organization && <span className="opacity-70">· {p.author_organization}</span>}
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Filter-Leiste ────────────────────────────────────────── */}
      <section className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Programmpunkt, Sprecher oder Thema suchen…"
            className="w-full rounded-2xl border border-slate-200 bg-white/85 py-2.5 pl-9 pr-4 text-sm shadow-sm outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-200 dark:border-slate-700 dark:bg-slate-900 dark:focus:ring-cyan-900"
          />
        </div>
        <label className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white/85 px-3 py-2 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
          <input type="checkbox" checked={showOnlyWithPosts}
            onChange={(e) => setShowOnlyWithPosts(e.target.checked)}
            className="accent-cyan-600" />
          Nur Stränge mit Beiträgen
        </label>
      </section>

      {/* ── Threads pro Tag ──────────────────────────────────────── */}
      {loading && (
        <section className="rounded-3xl border border-slate-200 bg-white/85 p-8 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900/70">
          Forum wird geladen…
        </section>
      )}
      {error && !loading && (
        <section className="rounded-3xl border border-red-200 bg-red-50/90 p-6 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </section>
      )}

      {!loading && !error && byDay.length === 0 && (
        <section className="rounded-3xl border border-dashed border-slate-300 bg-white/60 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40">
          {showOnlyWithPosts
            ? 'Noch keine Beiträge — entferne den Filter, um alle Programmpunkte zu sehen.'
            : 'Keine passenden Programmpunkte.'}
        </section>
      )}

      {!loading && byDay.map(([day, dayItems]) => (
        <section key={day} className="space-y-3">
          <div className="flex items-end justify-between gap-3 px-1">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              Tag {day}
            </h2>
            <div className="text-xs text-slate-400">
              {dayItems.length} Programmpunkt{dayItems.length === 1 ? '' : 'e'}
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {dayItems.map((item) => {
              const sum = summaryById.get(item.id);
              const count = sum?.post_count || 0;
              const cat = categoryColor(item.category);
              return (
                <Link key={item.id} to={`/agenda/forum/${item.id}`}
                  className={`group block rounded-2xl border bg-gradient-to-br p-4 transition hover:shadow-md ${cat}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider opacity-80">
                        <Clock size={11} /> {item.time} · {item.duration_minutes} Min
                        <span className="opacity-70">· {CATEGORY_LABELS[item.category] || item.category}</span>
                      </div>
                      <h3 className="mt-2 text-base font-semibold leading-snug text-slate-900 group-hover:text-slate-800 dark:text-white dark:group-hover:text-slate-100 line-clamp-2">
                        {item.title}
                      </h3>
                      {item.speaker && (
                        <div className="mt-1 inline-flex items-center gap-1 text-xs opacity-80">
                          <User2 size={11} /> {item.speaker}
                        </div>
                      )}
                      {item.note && (
                        <p className="mt-2 text-xs leading-5 text-slate-600 line-clamp-2 dark:text-slate-300">
                          {item.note}
                        </p>
                      )}
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="inline-flex items-center gap-1 rounded-full border border-current/30 bg-white/60 px-2.5 py-1 text-xs font-semibold backdrop-blur-sm dark:bg-slate-900/40">
                        <MessageSquare size={12} />
                        {count}
                      </div>
                      {sum?.last_post_at && (
                        <div className="mt-1 text-[10px] opacity-70">
                          {formatRelative(sum.last_post_at)}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-slate-700 transition group-hover:gap-2 dark:text-slate-200">
                    {count > 0 ? 'Diskussion lesen' : 'Diskussion starten'}
                    <ArrowRight size={13} />
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
