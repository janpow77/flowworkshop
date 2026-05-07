import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, CheckCheck, Clock } from 'lucide-react';
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
  const ref = useRef<HTMLDivElement>(null);
  const isLoggedIn = !!localStorage.getItem('workshop_token');

  const load = async () => {
    if (!isLoggedIn) return;
    try {
      const r = await fetch('/api/notifications?limit=20', { headers: getWorkshopAuthHeaders() });
      if (!r.ok) return;
      const d = await r.json();
      setItems(d.items || []);
      setUnread(d.unread_count || 0);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (!isLoggedIn) return;
    load();
    const iv = setInterval(load, 60_000);
    return () => clearInterval(iv);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, []);

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
