import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Calendar, User2, MessageSquare, FolderArchive,
  ChevronDown, ChevronUp, FileText, Download,
} from 'lucide-react';
import { getWorkshopAuthHeaders } from '../lib/api';

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
  scenario_id: number | null;
  page_url: string | null;
}

interface MaterialThread {
  id: string;
  title: string;
  post_count: number;
  view_count: number;
  last_post_at: string | null;
  solved: boolean;
  pinned: boolean;
}

interface MaterialFile {
  id: string;
  name: string;
  mime_type: string | null;
  size_bytes: number;
  uploaded_at: string | null;
  uploader_name: string | null;
  folder_name: string;
  folder_slug: string;
}

interface Material {
  item_id: string;
  threads: MaterialThread[];
  files: MaterialFile[];
  notes_md: string;
}

function formatBytes(b: number): string {
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

const DAY_NAMES = ['', 'Tag 1 — Dienstag', 'Tag 2 — Mittwoch', 'Tag 3 — Donnerstag'];

export default function AgendaArchivePage() {
  const [items, setItems] = useState<AgendaItem[]>([]);
  const [materials, setMaterials] = useState<Record<string, Material>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/event/agenda')
      .then((r) => r.ok ? r.json() : [])
      .then((d) => setItems(d))
      .finally(() => setLoading(false));
  }, []);

  const toggleItem = async (id: string) => {
    const next = new Set(expanded);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
      if (!materials[id]) {
        try {
          const r = await fetch(`/api/event/agenda/${id}/material`, {
            headers: getWorkshopAuthHeaders(),
          });
          if (r.ok) {
            const m = await r.json();
            setMaterials((prev) => ({ ...prev, [id]: m }));
          }
        } catch { /* ignore */ }
      }
    }
    setExpanded(next);
  };

  const byDay = items.reduce<Record<number, AgendaItem[]>>((acc, it) => {
    (acc[it.day] = acc[it.day] || []).push(it);
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <section className="rounded-[28px] border border-white/70 bg-[linear-gradient(135deg,rgba(15,23,42,0.97),rgba(30,41,59,0.93)_45%,rgba(51,65,85,0.85))] px-7 py-6 text-white shadow-[0_28px_80px_-50px_rgba(15,23,42,0.95)]">
        <div className="text-[11px] uppercase tracking-[0.22em] text-slate-300/70">
          <Calendar size={11} className="inline mr-1" /> Programm-Archiv
        </div>
        <h1 className="mt-2 text-2xl font-semibold">Tagesordnung 2026</h1>
        <p className="mt-2 text-sm text-white/80">
          Alles, was lief — mit verknüpften Forum-Diskussionen und Dokumenten.
          Klick auf einen Programmpunkt zeigt das Material.
        </p>
      </section>

      {loading ? (
        <div className="text-sm text-slate-500">Lädt…</div>
      ) : (
        Object.entries(byDay).sort(([a], [b]) => Number(a) - Number(b)).map(([day, dayItems]) => (
          <section key={day} className="space-y-2">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white px-1">
              {DAY_NAMES[Number(day)] || `Tag ${day}`}
            </h2>
            <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
              {dayItems.map((it, i) => {
                const isOpen = expanded.has(it.id);
                const m = materials[it.id];
                return (
                  <div key={it.id} className={i > 0 ? 'border-t border-slate-200 dark:border-slate-800' : ''}>
                    <button onClick={() => toggleItem(it.id)}
                      className="w-full text-left px-5 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition flex items-center gap-3">
                      <div className="flex flex-col items-center min-w-[60px] text-center">
                        <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{it.time}</div>
                        <div className="text-[10px] text-slate-400">{it.duration_minutes} Min</div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-slate-900 dark:text-white">{it.title}</div>
                        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 mt-0.5">
                          {it.speaker && <span className="inline-flex items-center gap-1"><User2 size={10} />{it.speaker}</span>}
                          <span className="opacity-60">· {it.category}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-500 shrink-0">
                        {m && <>
                          <span className="inline-flex items-center gap-1"><MessageSquare size={11} />{m.threads.length}</span>
                          <span className="inline-flex items-center gap-1"><FolderArchive size={11} />{m.files.length}</span>
                        </>}
                        {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                      </div>
                    </button>
                    {isOpen && (
                      <div className="px-5 pb-4 bg-slate-50 dark:bg-slate-800/40 border-t border-slate-200 dark:border-slate-800">
                        {it.note && <p className="text-sm text-slate-600 dark:text-slate-400 my-3 italic">{it.note}</p>}
                        {it.page_url && (
                          <Link to={it.page_url}
                            className="inline-flex items-center gap-1 text-xs text-cyan-600 hover:text-cyan-700 mb-3">
                            → Zur Seite des Programmpunkts
                          </Link>
                        )}
                        {!m ? (
                          <div className="text-xs text-slate-400 my-3">Lädt Material…</div>
                        ) : (
                          <div className="grid md:grid-cols-2 gap-3 mt-3">
                            <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                              <div className="flex items-center gap-1 text-xs font-semibold text-slate-700 dark:text-slate-200 mb-2">
                                <MessageSquare size={12} /> Diskussionen
                              </div>
                              {m.threads.length === 0 ? (
                                <div className="text-xs text-slate-400">Keine verknüpften Threads.</div>
                              ) : (
                                <ul className="space-y-1.5">
                                  {m.threads.map((t) => (
                                    <li key={t.id}>
                                      <Link to={`/forum/t/${t.id}`}
                                        className="block text-sm text-cyan-700 hover:underline dark:text-cyan-300">
                                        {t.title}
                                      </Link>
                                      <div className="text-[10px] text-slate-400">
                                        {t.post_count} Beiträge · {t.view_count} Aufrufe
                                        {t.solved && ' · ✓ gelöst'}
                                      </div>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                              <div className="flex items-center gap-1 text-xs font-semibold text-slate-700 dark:text-slate-200 mb-2">
                                <FolderArchive size={12} /> Dokumente
                              </div>
                              {m.files.length === 0 ? (
                                <div className="text-xs text-slate-400">Keine verknüpften Dateien.</div>
                              ) : (
                                <ul className="space-y-1.5">
                                  {m.files.map((f) => (
                                    <li key={f.id} className="flex items-center gap-2 text-sm">
                                      <FileText size={12} className="text-slate-400" />
                                      <span className="text-slate-700 dark:text-slate-200 line-clamp-1 flex-1">{f.name}</span>
                                      <span className="text-[10px] text-slate-400">{formatBytes(f.size_bytes)}</span>
                                      <a href={`/api/docs/files/${f.id}/download`}
                                        className="text-slate-500 hover:text-cyan-600">
                                        <Download size={12} />
                                      </a>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          </div>
                        )}
                        {m?.notes_md && (
                          <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 whitespace-pre-wrap">
                            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Notizen</div>
                            {m.notes_md}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
