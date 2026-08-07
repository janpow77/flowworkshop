import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, CheckCheck, Clock, X } from 'lucide-react';
import { getWorkshopAuthHeaders } from '../../lib/api';

interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  created_at: string | null;
  read_at: string | null;
}

function formatRelative(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const min = Math.round((Date.now() - d.getTime()) / 60000);
  if (min < 1) return 'gerade eben';
  if (min < 60) return `vor ${min} Min`;
  const h = Math.round(min / 60);
  if (h < 24) return `vor ${h} Std`;
  const day = Math.round(h / 24);
  return `vor ${day} Tag${day === 1 ? '' : 'en'}`;
}

/**
 * Meldungen, die von selbst als Blase aufgehen sollen. Alles andere wartet
 * geduldig in der Glocke — eine Blase, die bei jeder Kleinigkeit aufpoppt,
 * wird nach zwei Tagen weggeklickt, ohne gelesen zu werden.
 */
const BLASEN_ARTEN = new Set(['admin_harvest_failed', 'admin_pending']);

/** Wie lange die Blase stehen bleibt, bevor sie sich selbst schliesst. */
const BLASE_DAUER_MS = 15_000;

/** Bereits gezeigte Meldungen, damit die Blase nicht im Minutentakt wiederkehrt. */
const GEZEIGT_SPEICHER = 'workshop_blase_gezeigt';

function bereitsGezeigt(): Set<number> {
  try {
    const roh = localStorage.getItem(GEZEIGT_SPEICHER);
    return new Set<number>(roh ? JSON.parse(roh) : []);
  } catch {
    return new Set<number>();
  }
}

function merkeGezeigt(id: number) {
  try {
    const alle = [...bereitsGezeigt(), id].slice(-50);
    localStorage.setItem(GEZEIGT_SPEICHER, JSON.stringify(alle));
  } catch { /* localStorage kann fehlen — dann eben ohne Gedaechtnis */ }
}

const KIND_COLORS: Record<string, string> = {
  forum_reply: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-200',
  forum_mention: 'bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-200',
  admin_pending: 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200',
  admin_harvest_failed: 'bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-200',
  doc_uploaded: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200',
};

export default function NotificationBell() {
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [blase, setBlase] = useState<Notification | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const isLoggedIn = !!localStorage.getItem('workshop_token');

  const load = async () => {
    if (!isLoggedIn) return;
    try {
      const r = await fetch('/api/notifications?limit=20', { headers: getWorkshopAuthHeaders() });
      if (!r.ok) return;
      const d = await r.json();
      const liste: Notification[] = d.items || [];
      setItems(liste);
      setUnread(d.unread_count || 0);

      // Neueste ungelesene Meldung einer relevanten Art als Blase zeigen —
      // aber jede nur einmal.
      const gezeigt = bereitsGezeigt();
      const kandidat = liste.find(
        (n) => !n.read_at && BLASEN_ARTEN.has(n.kind) && !gezeigt.has(n.id),
      );
      if (kandidat) {
        merkeGezeigt(kandidat.id);
        setBlase(kandidat);
      }
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (!isLoggedIn) return;
    load();
    const iv = setInterval(load, 60_000);
    return () => clearInterval(iv);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, []);

  // Blase schliesst sich von selbst; die Glocke behaelt die Meldung.
  useEffect(() => {
    if (!blase) return;
    const t = setTimeout(() => setBlase(null), BLASE_DAUER_MS);
    return () => clearTimeout(t);
  }, [blase]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const markAllRead = async () => {
    await fetch('/api/notifications/mark-all-read', {
      method: 'POST', headers: getWorkshopAuthHeaders(),
    });
    load();
  };

  const markRead = async (id: number) => {
    await fetch(`/api/notifications/${id}/mark-read`, {
      method: 'POST', headers: getWorkshopAuthHeaders(),
    });
    load();
  };

  if (!isLoggedIn) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="relative rounded-2xl border border-slate-200 bg-white/80 p-2.5 text-slate-500 transition-colors hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:bg-slate-800"
        aria-label="Benachrichtigungen"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-rose-500 text-[10px] font-semibold text-white px-1.5">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
      {blase && !open && (
        <div
          role="status"
          aria-live="polite"
          className="absolute right-0 mt-2 w-[340px] rounded-2xl border border-rose-200 bg-white shadow-xl dark:border-rose-900/60 dark:bg-slate-900 z-50 animate-in fade-in slide-in-from-top-1"
        >
          {/* Zeiger zur Glocke, damit die Blase erkennbar dazugehoert */}
          <span className="absolute -top-1.5 right-4 h-3 w-3 rotate-45 border-l border-t border-rose-200 bg-white dark:border-rose-900/60 dark:bg-slate-900" />
          <div className="flex items-start gap-2 p-4">
            <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-rose-500" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {blase.title}
              </div>
              {blase.body && (
                <div className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400 line-clamp-3">
                  {blase.body}
                </div>
              )}
              {blase.link && (
                <Link
                  to={blase.link}
                  onClick={() => { markRead(blase.id); setBlase(null); }}
                  className="mt-2 inline-block text-xs font-medium text-cyan-600 hover:text-cyan-700"
                >
                  Ansehen
                </Link>
              )}
            </div>
            <button
              onClick={() => setBlase(null)}
              aria-label="Hinweis schließen"
              className="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}
      {open && (
        <div className="absolute right-0 mt-2 w-[360px] max-h-[500px] overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900 z-50">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 dark:border-slate-800">
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">Benachrichtigungen</span>
            {unread > 0 && (
              <button onClick={markAllRead}
                className="inline-flex items-center gap-1 text-xs text-cyan-600 hover:text-cyan-700">
                <CheckCheck size={12} />Alle gelesen
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-slate-400">Keine Benachrichtigungen.</div>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {items.map((n) => {
                const cls = KIND_COLORS[n.kind] || 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
                const isUnread = !n.read_at;
                const inner = (
                  <div className={`block px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 ${isUnread ? 'bg-cyan-50/50 dark:bg-cyan-950/20' : ''}`}>
                    <div className="flex items-start gap-2">
                      <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${cls} mt-0.5 shrink-0`}>
                        {n.kind.replace(/_/g, ' ')}
                      </span>
                      {isUnread && <span className="mt-1.5 h-2 w-2 rounded-full bg-cyan-500 shrink-0" />}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-800 dark:text-slate-200 line-clamp-2">{n.title}</div>
                        {n.body && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{n.body}</div>}
                        <div className="text-[11px] text-slate-400 mt-1 inline-flex items-center gap-1">
                          <Clock size={10} />{formatRelative(n.created_at)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
                return (
                  <li key={n.id}>
                    {n.link ? (
                      <Link to={n.link} onClick={() => { markRead(n.id); setOpen(false); }}>
                        {inner}
                      </Link>
                    ) : (
                      <button className="w-full text-left" onClick={() => markRead(n.id)}>{inner}</button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
