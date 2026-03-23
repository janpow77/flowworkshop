import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  Calendar, Clock, MapPin, Building2, Mic2, MessageSquare,
  Wrench, Coffee, ClipboardCheck, UserPlus, ThumbsUp,
  ChevronDown, Cpu, Play, CheckCircle2, SkipForward,
  RotateCcw, Beaker, ExternalLink, Timer, TimerReset,
  Eye, EyeOff, ArrowUp, ArrowDown,
} from 'lucide-react';
import { Skeleton } from '../components/ui/Skeleton';

interface Meta {
  title: string;
  subtitle: string;
  date: string;
  time: string;
  location_short: string;
  location_full: string;
  organizer: string;
  registration_deadline: string;
}

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
  started_at: string | null;
  scenario_id: number | null;
  sort_order: number;
  visible: boolean;
}

interface DayGroup {
  day: number;
  label: string;
  items: AgendaItem[];
}

interface Topic {
  id: string;
  topic: string;
  question: string | null;
  organization: string | null;
  votes: number;
}

const TYPE_STYLES: Record<string, { icon: typeof Mic2; color: string; bg: string; border: string }> = {
  vortrag: { icon: Mic2, color: 'text-blue-700 dark:text-blue-300', bg: 'bg-blue-50 dark:bg-blue-950/40', border: 'border-blue-200 dark:border-blue-800' },
  diskussion: { icon: MessageSquare, color: 'text-sky-700 dark:text-sky-300', bg: 'bg-sky-50 dark:bg-sky-950/40', border: 'border-sky-200 dark:border-sky-800' },
  workshop: { icon: Wrench, color: 'text-amber-700 dark:text-amber-300', bg: 'bg-amber-50 dark:bg-amber-950/40', border: 'border-amber-200 dark:border-amber-800' },
  pause: { icon: Coffee, color: 'text-slate-400', bg: 'bg-slate-50 dark:bg-slate-900/40', border: 'border-slate-200 dark:border-slate-800' },
  organisation: { icon: ClipboardCheck, color: 'text-emerald-700 dark:text-emerald-300', bg: 'bg-emerald-50 dark:bg-emerald-950/40', border: 'border-emerald-200 dark:border-emerald-800' },
};

const STATUS_STYLES: Record<string, { label: string; dot: string }> = {
  pending: { label: 'Offen', dot: 'bg-slate-300 dark:bg-slate-600' },
  active: { label: 'Aktiv', dot: 'bg-green-500 animate-pulse' },
  done: { label: 'Erledigt', dot: 'bg-emerald-500' },
  skipped: { label: 'Uebersprungen', dot: 'bg-slate-400' },
};

const SCENARIO_LABELS: Record<number, string> = {
  1: 'Dokumentenanalyse',
  2: 'Checklisten-KI',
  3: 'RAG / Halluzination',
  4: 'Berichtsentwurf',
  5: 'Vorab-Upload',
  6: 'Beguenstigtenverzeichnis',
};

type ViewMode = 'plenary' | 'workshop5';

// Countdown-Hook: berechnet verbleibende Zeit ab started_at
function useCountdown(activeItem: AgendaItem | undefined): string {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  if (!activeItem || !activeItem.started_at) return '';

  const startMs = new Date(activeItem.started_at + 'Z').getTime();
  const endMs = startMs + activeItem.duration_minutes * 60_000;
  const remainMs = endMs - now.getTime();

  if (remainMs <= 0) {
    const overMs = Math.abs(remainMs);
    const overMin = Math.floor(overMs / 60_000);
    const overSec = Math.floor((overMs % 60_000) / 1000);
    return `+${overMin}:${String(overSec).padStart(2, '0')}`;
  }

  const remainMin = Math.floor(remainMs / 60_000);
  const remainSec = Math.floor((remainMs % 60_000) / 1000);

  if (remainMin < 1) return `${remainSec}s`;
  return `${remainMin}:${String(remainSec).padStart(2, '0')}`;
}

function countdownFraction(activeItem: AgendaItem | undefined): number {
  if (!activeItem || !activeItem.started_at) return 0;
  const now = new Date();
  const startMs = new Date(activeItem.started_at + 'Z').getTime();
  const totalMs = activeItem.duration_minutes * 60_000;
  const elapsed = now.getTime() - startMs;
  return Math.max(0, Math.min(1, elapsed / totalMs));
}

function modFetch(url: string, options?: RequestInit): Promise<Response> {
  const token = localStorage.getItem('workshop_token') || '';
  return fetch(url, {
    ...options,
    headers: { ...options?.headers, Authorization: `Bearer ${token}` },
  });
}

export default function AgendaPage() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [days, setDays] = useState<DayGroup[]>([]);
  const [ws5Days, setWs5Days] = useState<DayGroup[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [votedIds, setVotedIds] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>('plenary');
  const [expandedDays, setExpandedDays] = useState<Set<number>>(new Set([1, 2, 3]));
  const [isAdmin] = useState(() => localStorage.getItem('workshop_role') === 'moderator');
  const [prevActiveId, setPrevActiveId] = useState<string | null>(null);
  const [transitioningIds, setTransitioningIds] = useState<Record<string, string>>({});

  const activeItemRef = useRef<HTMLDivElement>(null);

  const activeDays = viewMode === 'workshop5' ? ws5Days : days;
  const activeItem = activeDays.flatMap((d) => d.items).find((i) => i.status === 'active');

  const countdown = useCountdown(activeItem);
  const elapsed = countdownFraction(activeItem);

  const loadAgenda = useCallback(() => {
    const hiddenParam = isAdmin ? 'show_hidden=true' : '';
    const plenaryUrl = hiddenParam ? `/api/event/agenda/days?${hiddenParam}` : '/api/event/agenda/days';
    const ws5Url = `/api/event/agenda/days?category=workshop5${hiddenParam ? `&${hiddenParam}` : ''}`;
    Promise.all([
      fetch(plenaryUrl).then((r) => r.json()),
      fetch(ws5Url).then((r) => r.json()),
    ]).then(([d, w]) => {
      setDays(d);
      setWs5Days(w);
    });
  }, [isAdmin]);

  useEffect(() => {
    const hiddenParam = isAdmin ? 'show_hidden=true' : '';
    const plenaryUrl = hiddenParam ? `/api/event/agenda/days?${hiddenParam}` : '/api/event/agenda/days';
    const ws5Url = `/api/event/agenda/days?category=workshop5${hiddenParam ? `&${hiddenParam}` : ''}`;
    Promise.all([
      fetch('/api/event/meta').then((r) => r.json()),
      fetch(plenaryUrl).then((r) => r.json()),
      fetch(ws5Url).then((r) => r.json()),
      fetch('/api/event/topics').then((r) => r.json()),
    ]).then(([m, d, w, t]) => {
      setMeta(m);
      setDays(d);
      setWs5Days(w);
      setTopics(t);
    }).finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-Refresh alle 15 Sekunden
  useEffect(() => {
    const interval = setInterval(loadAgenda, 15000);
    return () => clearInterval(interval);
  }, [loadAgenda]);

  // Smooth scroll zum aktiven Punkt wenn er sich aendert
  useEffect(() => {
    if (activeItem && activeItem.id !== prevActiveId) {
      setPrevActiveId(activeItem.id);
      // Transition-Klasse setzen
      setTransitioningIds((prev) => ({ ...prev, [activeItem.id]: 'activate' }));
      setTimeout(() => {
        setTransitioningIds((prev) => {
          const next = { ...prev };
          delete next[activeItem.id];
          return next;
        });
      }, 600);
      // Scroll mit kurzer Verzoegerung (nach Animation)
      setTimeout(() => {
        activeItemRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 200);
    }
    // Vorheriger aktiver Punkt bekommt 'complete' Animation
    if (prevActiveId && activeItem?.id !== prevActiveId) {
      setTransitioningIds((prev) => ({ ...prev, [prevActiveId]: 'complete' }));
      setTimeout(() => {
        setTransitioningIds((prev) => {
          const next = { ...prev };
          delete next[prevActiveId!];
          return next;
        });
      }, 700);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- prevActiveId wird bewusst nicht als Dep genommen (wuerde Loop verursachen)
  }, [activeItem?.id]);

  const handleVote = async (topicId: string) => {
    if (votedIds.has(topicId)) return;
    await fetch(`/api/event/topics/${topicId}/vote`, { method: 'POST' });
    setVotedIds((prev) => new Set(prev).add(topicId));
    setTopics((prev) => prev.map((t) => t.id === topicId ? { ...t, votes: t.votes + 1 } : t));
  };

  const toggleDay = (day: number) => {
    setExpandedDays((prev) => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  };

  const setItemStatus = async (itemId: string, action: 'start' | 'done' | 'skip') => {
    // Sofortige visuelle Transition
    const anim = action === 'start' ? 'activate' : action === 'done' ? 'complete' : 'skip';
    setTransitioningIds((prev) => ({ ...prev, [itemId]: anim }));

    if (action === 'start') {
      await modFetch(`/api/event/admin/agenda/${itemId}/start`, { method: 'POST' });
    } else {
      const status = action === 'done' ? 'done' : 'skipped';
      await modFetch(`/api/event/admin/agenda/${itemId}/status?status=${status}`, { method: 'PUT' });
    }
    // Daten nachladen und Transition entfernen
    await loadAgenda();
    setTimeout(() => {
      setTransitioningIds((prev) => {
        const next = { ...prev };
        delete next[itemId];
        return next;
      });
    }, 600);
  };

  const adjustTime = async (itemId: string, minutes: number) => {
    await modFetch(`/api/event/admin/agenda/${itemId}/adjust-time?minutes=${minutes}`, { method: 'POST' });
    loadAgenda();
  };

  const resetTimer = async (itemId: string) => {
    await modFetch(`/api/event/admin/agenda/${itemId}/reset-timer`, { method: 'POST' });
    loadAgenda();
  };

  const resetStatus = async (category?: string) => {
    const catParam = category ? `?category=${category}` : '';
    await modFetch(`/api/event/admin/agenda/reset-status${catParam}`, { method: 'POST' });
    loadAgenda();
  };

  const toggleVisible = async (itemId: string) => {
    await modFetch(`/api/event/admin/agenda/${itemId}/toggle-visible`, { method: 'POST' });
    loadAgenda();
  };

  const moveItem = async (itemId: string, direction: -1 | 1) => {
    const allItems = activeDays.flatMap((d) => d.items);
    const idx = allItems.findIndex((i) => i.id === itemId);
    if (idx < 0) return;
    const swapIdx = idx + direction;
    if (swapIdx < 0 || swapIdx >= allItems.length) return;
    const order = allItems.map((i) => i.id);
    [order[idx], order[swapIdx]] = [order[swapIdx], order[idx]];
    await modFetch('/api/event/admin/agenda/reorder', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(order),
    });
    loadAgenda();
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto space-y-8 py-8">
        <Skeleton className="h-48 w-full rounded-[32px]" />
        <div className="space-y-4 pt-4">
          <Skeleton className="h-16 w-full rounded-2xl" />
          <Skeleton className="h-16 w-full rounded-2xl" />
          <Skeleton className="h-16 w-full rounded-2xl" />
        </div>
      </div>
    );
  }

  const totalItems = activeDays.reduce((s, d) => s + d.items.length, 0);
  const doneItems = activeDays.reduce((s, d) => s + d.items.filter((i) => i.status === 'done').length, 0);

  return (
    <div className="max-w-3xl mx-auto space-y-8 agenda-scroll-container">
      {/* Header */}
      {meta && (
        <section className="relative overflow-hidden rounded-[32px] border border-white/70 bg-gradient-to-br from-slate-900 via-cyan-900 to-emerald-900 px-8 py-10 text-white shadow-[0_40px_120px_-48px_rgba(8,47,73,0.9)]">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.15),transparent_40%)]" />
          <div className="relative">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-200/70">{meta.organizer}</div>
            <h1 className="text-3xl font-semibold tracking-tight lg:text-4xl">{meta.title}</h1>
            {meta.subtitle && <p className="mt-2 text-base text-cyan-50/80">{meta.subtitle}</p>}
            <div className="mt-6 flex flex-wrap gap-4 text-sm text-cyan-100/90">
              {meta.date && <span className="flex items-center gap-1.5"><Calendar size={15} /> {meta.date}</span>}
              {meta.time && <span className="flex items-center gap-1.5"><Clock size={15} /> {meta.time}</span>}
              {meta.location_short && <span className="flex items-center gap-1.5"><MapPin size={15} /> {meta.location_short}</span>}
            </div>
            {meta.location_full && <p className="mt-2 text-xs text-cyan-100/60">{meta.location_full}</p>}
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/register" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-slate-900 hover:bg-cyan-50 transition-colors">
                <UserPlus size={16} /> Anmelden
              </Link>
              {meta.registration_deadline && (
                <span className="inline-flex items-center rounded-full border border-white/20 bg-white/10 px-4 py-2.5 text-xs text-white/80">
                  Anmeldeschluss: {meta.registration_deadline}
                </span>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Live-Banner fuer aktiven Punkt */}
      {activeItem && (
        <div className="animate-live-banner-in rounded-2xl border-2 border-green-400/50 bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/20 p-4 relative overflow-hidden">
          {/* Shimmer-Overlay */}
          <div className="absolute inset-0 animate-shimmer pointer-events-none" />
          <div className="relative flex items-center gap-4">
            <div className="relative shrink-0">
              <div className="h-4 w-4 rounded-full bg-green-500 animate-glow-pulse" />
              <div className="absolute inset-0 h-4 w-4 rounded-full bg-green-400 animate-ping opacity-20" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-green-600 dark:text-green-400">Aktuell</p>
              <p className="font-medium text-slate-900 dark:text-white truncate">{activeItem.title}</p>
              {activeItem.speaker && <p className="text-xs text-slate-500">{activeItem.speaker}</p>}
            </div>
            {/* Countdown */}
            <div className="shrink-0 flex flex-col items-center gap-1">
              <div className="flex items-center gap-1.5 text-sm font-mono font-bold text-green-700 dark:text-green-300">
                <Timer size={14} />
                <span className={elapsed > 1 ? 'text-red-500 animate-pulse' : ''}>{countdown}</span>
              </div>
              {/* Mini-Fortschrittsbalken */}
              <div className="w-20 h-1 rounded-full bg-green-200 dark:bg-green-900 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-1000 ease-linear"
                  style={{
                    width: `${Math.max(0, (1 - elapsed)) * 100}%`,
                    backgroundColor: elapsed > 1 ? '#ef4444' : elapsed > 0.85 ? '#ef4444' : elapsed > 0.7 ? '#f59e0b' : '#22c55e',
                  }}
                />
              </div>
              {/* Timer-Controls fuer Moderator */}
              {isAdmin && (
                <div className="flex items-center gap-0.5 mt-0.5">
                  <button onClick={() => adjustTime(activeItem.id, -5)} className="px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-500 hover:bg-red-100 hover:text-red-600 transition-colors" title="-5 Minuten">-5</button>
                  <button onClick={() => resetTimer(activeItem.id)} className="p-0.5 rounded text-slate-400 hover:bg-amber-100 hover:text-amber-600 transition-colors" title="Timer neu starten"><TimerReset size={12} /></button>
                  <button onClick={() => adjustTime(activeItem.id, 5)} className="px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-500 hover:bg-green-100 hover:text-green-600 transition-colors" title="+5 Minuten">+5</button>
                  <button onClick={() => adjustTime(activeItem.id, 10)} className="px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-500 hover:bg-green-100 hover:text-green-600 transition-colors" title="+10 Minuten">+10</button>
                </div>
              )}
            </div>
            {activeItem.scenario_id && (
              <Link
                to={`/scenarios/${activeItem.scenario_id}`}
                className="shrink-0 flex items-center gap-1.5 rounded-full bg-amber-100 dark:bg-amber-900/40 px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-300 hover:bg-amber-200 transition-colors"
              >
                <Beaker size={13} /> Szenario {activeItem.scenario_id}
                <ExternalLink size={11} />
              </Link>
            )}
          </div>
        </div>
      )}

      {/* View-Toggle + Admin */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setViewMode('plenary')}
          className={`flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-all duration-300 ${
            viewMode === 'plenary'
              ? 'bg-slate-900 text-white dark:bg-indigo-500 shadow-lg shadow-slate-900/25'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'
          }`}
        >
          <Calendar size={15} /> Gesamtprogramm
        </button>
        <button
          onClick={() => setViewMode('workshop5')}
          className={`flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-all duration-300 ${
            viewMode === 'workshop5'
              ? 'bg-amber-600 text-white shadow-lg shadow-amber-600/25'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'
          }`}
        >
          <Cpu size={15} /> Workshop 5
        </button>
        <div className="flex-1" />
        {isAdmin && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600">Moderator</span>
            <button
              onClick={() => resetStatus(viewMode === 'workshop5' ? 'workshop5' : undefined)}
              className="flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 px-2 py-1.5 text-xs text-slate-500 hover:bg-slate-200 transition-colors"
              title="Alle Status zuruecksetzen"
            >
              <RotateCcw size={12} /> Reset
            </button>
          </div>
        )}
      </div>

      {/* Fortschrittsbalken */}
      {doneItems > 0 && (
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-slate-400">
            <span>{doneItems} von {totalItems} Punkten erledigt</span>
            <span>{Math.round((doneItems / totalItems) * 100)}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-green-400 animate-progress-fill transition-all duration-700 ease-out"
              style={{ width: `${(doneItems / totalItems) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Programm nach Tagen */}
      <section>
        <div className="mb-4">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
            {viewMode === 'workshop5' ? 'Workshop 5 — KI und Digitalisierung' : 'Programm'}
          </h2>
          <p className="text-sm text-slate-500">
            {activeDays.length} Tage · {totalItems} Programmpunkte
          </p>
        </div>

        {activeDays.length === 0 && (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white/85 dark:bg-slate-900/75 p-8 text-center">
            <p className="text-slate-500">Noch keine Programmpunkte fuer diese Ansicht vorhanden.</p>
          </div>
        )}

        <div className="space-y-6">
          {activeDays.map((dayGroup) => {
            const dayDone = dayGroup.items.filter((i) => i.status === 'done').length;
            const dayTotal = dayGroup.items.length;

            return (
              <div key={dayGroup.day} className="space-y-3">
                <button
                  onClick={() => toggleDay(dayGroup.day)}
                  className="flex w-full items-center gap-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-900/80 px-5 py-3.5 text-left hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-all duration-200"
                >
                  <div className={`transition-transform duration-300 ${expandedDays.has(dayGroup.day) ? 'rotate-0' : '-rotate-90'}`}>
                    <ChevronDown size={18} className="text-slate-400" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-slate-900 dark:text-white">{dayGroup.label}</h3>
                    <p className="text-xs text-slate-500">{dayGroup.items.length} Punkte{dayDone > 0 ? ` · ${dayDone}/${dayTotal} erledigt` : ''}</p>
                  </div>
                  {dayDone > 0 && dayDone < dayTotal && (
                    <div className="w-20 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                      <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-green-400 transition-all duration-700" style={{ width: `${(dayDone / dayTotal) * 100}%` }} />
                    </div>
                  )}
                  {dayDone === dayTotal && dayTotal > 0 && (
                    <CheckCircle2 size={16} className="text-emerald-500" />
                  )}
                </button>

                {/* Animated collapse */}
                <div className={`overflow-hidden transition-all duration-500 ease-in-out ${expandedDays.has(dayGroup.day) ? 'max-h-[5000px] opacity-100' : 'max-h-0 opacity-0'}`}>
                  <div className="relative space-y-3 pl-2">
                    <div className="absolute left-[72px] top-0 bottom-0 w-px bg-slate-200 dark:bg-slate-800" />

                    {dayGroup.items.map((item, i) => {
                      const style = TYPE_STYLES[item.item_type] || TYPE_STYLES.vortrag;
                      const Icon = style.icon;
                      const isPause = item.item_type === 'pause';
                      const statusStyle = STATUS_STYLES[item.status] || STATUS_STYLES.pending;
                      const isActive = item.status === 'active';
                      const isDone = item.status === 'done';
                      const isSkipped = item.status === 'skipped';
                      const transition = transitioningIds[item.id];

                      return (
                        <div
                          key={item.id}
                          ref={isActive ? activeItemRef : undefined}
                          className={`relative flex gap-4 transition-all duration-500 ease-out
                            ${isPause && !isActive ? 'opacity-60' : ''}
                            ${isDone && !transition ? 'opacity-40' : ''}
                            ${isSkipped && !transition ? 'opacity-30' : ''}
                            ${item.visible === false ? 'opacity-30 border-dashed' : ''}
                            ${transition === 'activate' ? 'animate-agenda-activate' : ''}
                            ${transition === 'complete' ? 'animate-agenda-complete' : ''}
                            ${transition === 'skip' ? 'animate-agenda-skip' : ''}
                          `}
                          style={{ animationDelay: `${i * 60}ms`, animationFillMode: 'backwards' }}
                        >
                          {/* Uhrzeit */}
                          <div className="w-16 shrink-0 pt-3 text-right">
                            <span className={`text-sm font-mono font-semibold transition-colors duration-300 ${isActive ? 'text-green-600 dark:text-green-400' : 'text-slate-700 dark:text-slate-300'}`}>{item.time}</span>
                            <div className="text-[10px] text-slate-400">{item.duration_minutes} min</div>
                          </div>

                          {/* Zeitlinien-Punkt */}
                          <div className="relative z-10 mt-3.5">
                            <div className={`h-3 w-3 rounded-full border-2 transition-all duration-500 ${
                              isActive
                                ? 'border-green-500 bg-green-400 shadow-[0_0_12px_rgba(34,197,94,0.6)] scale-125'
                                : isDone
                                  ? 'border-emerald-500 bg-emerald-400 scale-100'
                                  : isPause
                                    ? 'border-slate-300 bg-slate-100 dark:border-slate-700 dark:bg-slate-800'
                                    : 'border-cyan-500 bg-white dark:bg-slate-900 shadow-[0_0_8px_rgba(6,182,212,0.5)]'
                            }`} />
                            {isActive && (
                              <div className="absolute -inset-1 rounded-full border-2 border-green-400/40 animate-ping" />
                            )}
                          </div>

                          {/* Karte */}
                          <div className={`flex-1 rounded-2xl border transition-all duration-500 ${
                            isActive
                              ? 'border-green-400/50 ring-2 ring-green-400/20 shadow-lg shadow-green-500/10'
                              : style.border
                          } ${style.bg} p-4 ${isPause ? 'py-3' : ''} relative overflow-hidden`}>
                            {/* Countdown-Bar fuer aktiven Punkt */}
                            {isActive && (
                              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-green-200/50 dark:bg-green-900/30">
                                <div
                                  className="h-full transition-all duration-1000 ease-linear"
                                  style={{
                                    width: `${(1 - elapsed) * 100}%`,
                                    backgroundColor: elapsed > 0.85 ? '#ef4444' : elapsed > 0.7 ? '#f59e0b' : '#22c55e',
                                  }}
                                />
                              </div>
                            )}

                            <div className="flex items-start gap-3">
                              <span className={`mt-0.5 transition-all duration-300 ${isActive ? 'scale-110' : ''} ${style.color}`}>
                                <Icon size={isPause ? 14 : 16} />
                              </span>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <h3 className={`font-medium transition-all duration-300 ${
                                    isPause ? 'text-sm text-slate-500'
                                    : isDone ? 'line-through text-slate-400 dark:text-slate-500'
                                    : isActive ? 'text-green-800 dark:text-green-100'
                                    : 'text-slate-900 dark:text-white'
                                  }`}>
                                    {item.title}
                                  </h3>
                                  {isActive && <span className="shrink-0 h-2 w-2 rounded-full bg-green-500 animate-pulse" />}
                                </div>
                                {item.speaker && (
                                  <p className="text-xs text-slate-500 mt-0.5">{item.speaker}</p>
                                )}
                                {item.note && (
                                  <p className="text-xs text-slate-400 mt-1">{item.note}</p>
                                )}
                                {/* Szenario-Badge */}
                                {item.scenario_id && (
                                  <Link
                                    to={`/scenarios/${item.scenario_id}`}
                                    className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all duration-300 ${
                                      isActive
                                        ? 'bg-amber-200 dark:bg-amber-800/60 text-amber-800 dark:text-amber-200 shadow-md scale-105'
                                        : 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-800/50'
                                    }`}
                                  >
                                    <Beaker size={12} />
                                    Szenario {item.scenario_id}: {SCENARIO_LABELS[item.scenario_id] || ''}
                                    <ExternalLink size={10} />
                                  </Link>
                                )}
                              </div>
                              <div className="flex items-center gap-1.5 shrink-0">
                                {/* Status-Badge mit Animation */}
                                {item.status !== 'pending' && (
                                  <span className={`animate-status-badge-in flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                                    isActive ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                    : isDone ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
                                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800'
                                  }`}>
                                    <span className={`h-1.5 w-1.5 rounded-full ${statusStyle.dot}`} />
                                    {statusStyle.label}
                                  </span>
                                )}
                                {/* Sichtbarkeits-Toggle fuer Moderatoren */}
                                {isAdmin && (
                                  <button
                                    onClick={() => toggleVisible(item.id)}
                                    className={`p-1.5 rounded-lg transition-all duration-200 hover:scale-110 active:scale-95 ${
                                      item.visible === false
                                        ? 'text-slate-300 hover:bg-slate-100 dark:text-slate-600 dark:hover:bg-slate-800'
                                        : 'text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-900/30'
                                    }`}
                                    title={item.visible === false ? 'Einblenden' : 'Ausblenden'}
                                  >
                                    {item.visible === false ? <EyeOff size={13} /> : <Eye size={13} />}
                                  </button>
                                )}
                                {/* Moderator-Controls */}
                                {isAdmin && !isPause && (
                                  <div className="flex gap-0.5 ml-1">
                                    {!isActive && !isDone && (
                                      <button
                                        onClick={() => setItemStatus(item.id, 'start')}
                                        className="p-1.5 rounded-lg text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 transition-all duration-200 hover:scale-110 active:scale-95"
                                        title="Starten"
                                      >
                                        <Play size={13} />
                                      </button>
                                    )}
                                    {isActive && (
                                      <>
                                        <button onClick={() => adjustTime(item.id, -5)} className="px-1 py-0.5 rounded text-[10px] font-mono text-slate-400 hover:bg-red-100 hover:text-red-600 transition-colors" title="-5 Min">-5</button>
                                        <button onClick={() => adjustTime(item.id, 5)} className="px-1 py-0.5 rounded text-[10px] font-mono text-slate-400 hover:bg-green-100 hover:text-green-600 transition-colors" title="+5 Min">+5</button>
                                        <button
                                          onClick={() => resetTimer(item.id)}
                                          className="p-1.5 rounded-lg text-amber-500 hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-all duration-200 hover:scale-110 active:scale-95"
                                          title="Timer zuruecksetzen"
                                        >
                                          <TimerReset size={13} />
                                        </button>
                                        <button
                                          onClick={() => setItemStatus(item.id, 'done')}
                                          className="p-1.5 rounded-lg text-emerald-600 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 transition-all duration-200 hover:scale-110 active:scale-95"
                                          title="Erledigt"
                                        >
                                          <CheckCircle2 size={13} />
                                        </button>
                                      </>
                                    )}
                                    {!isDone && !isSkipped && (
                                      <button
                                        onClick={() => setItemStatus(item.id, 'skip')}
                                        className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all duration-200 hover:scale-110 active:scale-95"
                                        title="Ueberspringen"
                                      >
                                        <SkipForward size={13} />
                                      </button>
                                    )}
                                  </div>
                                )}
                                {/* Reorder-Buttons fuer Moderatoren */}
                                {isAdmin && !isPause && (
                                  <div className="flex flex-col gap-0.5 ml-1">
                                    <button onClick={() => moveItem(item.id, -1)} className="p-0.5 rounded text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors" title="Nach oben"><ArrowUp size={11} /></button>
                                    <button onClick={() => moveItem(item.id, 1)} className="p-0.5 rounded text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors" title="Nach unten"><ArrowDown size={11} /></button>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Adressen-Infobox */}
      <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white/85 dark:bg-slate-900/75 p-5">
        <h3 className="font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2">
          <MapPin size={16} className="text-emerald-600" /> Wichtige Adressen
        </h3>
        <div className="grid gap-3 sm:grid-cols-2 text-sm text-slate-600 dark:text-slate-400">
          <div>
            <p className="font-medium text-slate-800 dark:text-slate-200">Hannover Congress Centrum</p>
            <p>Theodor-Heuss-Platz 1-3, 30175 Hannover</p>
            <p className="text-xs text-slate-400 mt-0.5">Veranstaltungsort Di–Do</p>
          </div>
          <div>
            <p className="font-medium text-slate-800 dark:text-slate-200">Neues Rathaus (Gartensaal)</p>
            <p>Platz d. Menschenrechte 2, 30159 Hannover</p>
            <p className="text-xs text-slate-400 mt-0.5">Abendveranstaltung Mi 19:00</p>
          </div>
        </div>
      </section>

      {/* Themenboard */}
      {topics.length > 0 && (
        <section>
          <h2 className="mb-4 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
            Eingereichte Themen
          </h2>
          <div className="space-y-2">
            {topics.map((t) => (
              <div key={t.id} className="flex items-center gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white/85 dark:bg-slate-900/75 p-4 transition-all duration-200 hover:shadow-md">
                <button
                  onClick={() => handleVote(t.id)}
                  disabled={votedIds.has(t.id)}
                  className={`flex flex-col items-center gap-0.5 rounded-xl px-3 py-2 text-xs transition-all duration-300 ${
                    votedIds.has(t.id)
                      ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400 scale-105'
                      : 'bg-slate-100 text-slate-500 hover:bg-indigo-50 hover:text-indigo-600 dark:bg-slate-800 dark:hover:bg-indigo-900/20 hover:scale-110 active:scale-95'
                  }`}
                  aria-label={`Fuer "${t.topic}" stimmen`}
                >
                  <ThumbsUp size={14} />
                  <span className="font-bold">{t.votes}</span>
                </button>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-slate-900 dark:text-white text-sm">{t.topic}</h3>
                  {t.question && <p className="text-xs text-slate-500 mt-0.5">{t.question}</p>}
                </div>
                {t.organization && (
                  <span className="shrink-0 flex items-center gap-1 text-xs text-slate-400">
                    <Building2 size={12} /> {t.organization}
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
