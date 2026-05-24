import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ClipboardCheck, Search, FileText, AlertCircle, Users, Languages,
} from 'lucide-react';
import { listChecklistTemplates, type ChecklistTemplate } from '../lib/api';
import { Skeleton } from '../components/ui/Skeleton';

type StatusFilter = 'all' | 'draft' | 'published' | 'archived';
type SortKey = 'updated' | 'title' | 'status';

// Status-Normalisierung (Backend liefert Lowercase-Strings, ggf. Enum-Form)
function normStatus(raw: string): 'draft' | 'published' | 'archived' {
  const s = (raw || '').toLowerCase();
  if (s.includes('publish')) return 'published';
  if (s.includes('archiv')) return 'archived';
  return 'draft';
}

const STATUS_META: Record<'draft' | 'published' | 'archived', { label: string; cls: string }> = {
  draft: {
    label: 'Entwurf',
    cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  },
  published: {
    label: 'Veröffentlicht',
    cls: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  },
  archived: {
    label: 'Archiviert',
    cls: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  },
};

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[normStatus(status)];
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function ChecklistsPage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<ChecklistTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [langFilter, setLangFilter] = useState<string>('all');
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('updated');

  useEffect(() => {
    let cancelled = false;
    listChecklistTemplates()
      .then((r) => { if (!cancelled) setTemplates(r); })
      .catch(() => { if (!cancelled) setError('Die Checklisten konnten nicht geladen werden.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // Verfügbare Quellsprachen aus den geladenen Templates
  const languages = useMemo(() => {
    const set = new Set<string>();
    templates.forEach((t) => { if (t.source_language) set.add(t.source_language.toLowerCase()); });
    return Array.from(set).sort();
  }, [templates]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const result = templates.filter((t) => {
      if (statusFilter !== 'all' && normStatus(t.status) !== statusFilter) return false;
      if (langFilter !== 'all' && (t.source_language || '').toLowerCase() !== langFilter) return false;
      if (q) {
        const hay = `${t.title} ${t.description ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    const sorted = [...result];
    if (sortKey === 'title') {
      sorted.sort((a, b) => a.title.localeCompare(b.title, 'de'));
    } else if (sortKey === 'status') {
      sorted.sort((a, b) => normStatus(a.status).localeCompare(normStatus(b.status)));
    } else {
      // updated_at absteigend (neueste zuerst), null ans Ende
      sorted.sort((a, b) => {
        const av = a.updated_at ? Date.parse(a.updated_at) : 0;
        const bv = b.updated_at ? Date.parse(b.updated_at) : 0;
        return bv - av;
      });
    }
    return sorted;
  }, [templates, statusFilter, langFilter, query, sortKey]);

  const selectCls =
    'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200';

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 dark:text-white">
            <ClipboardCheck size={24} className="text-indigo-600 dark:text-indigo-400" />
            Checklisten
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Musterchecklisten verwalten, gemeinsam bearbeiten und diskutieren.
          </p>
        </div>
      </div>

      {/* Filterleiste */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Titel oder Beschreibung suchen…"
            aria-label="Checklisten durchsuchen"
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          aria-label="Status filtern"
          className={selectCls}
        >
          <option value="all">Alle Status</option>
          <option value="draft">Entwurf</option>
          <option value="published">Veröffentlicht</option>
          <option value="archived">Archiviert</option>
        </select>

        <select
          value={langFilter}
          onChange={(e) => setLangFilter(e.target.value)}
          aria-label="Quellsprache filtern"
          className={selectCls}
        >
          <option value="all">Alle Sprachen</option>
          {languages.map((l) => (
            <option key={l} value={l}>{l.toUpperCase()}</option>
          ))}
        </select>

        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          aria-label="Sortierung"
          className={selectCls}
        >
          <option value="updated">Zuletzt geändert</option>
          <option value="title">Titel (A–Z)</option>
          <option value="status">Status</option>
        </select>
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
              <Skeleton className="mb-3 h-5 w-2/3" />
              <Skeleton className="mb-2 h-3 w-full" />
              <Skeleton className="mb-4 h-3 w-4/5" />
              <Skeleton className="h-3 w-24" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 py-16 text-center text-slate-400 dark:border-slate-700">
          <ClipboardCheck size={48} className="mx-auto mb-3" />
          {templates.length === 0 ? (
            <>
              <p className="text-slate-500 dark:text-slate-400">Noch keine Checklisten vorhanden.</p>
              <p className="mt-1 text-sm">
                Sobald Musterchecklisten angelegt oder mit Ihnen geteilt werden, erscheinen sie hier.
              </p>
            </>
          ) : (
            <>
              <p className="text-slate-500 dark:text-slate-400">Keine Treffer für die gewählten Filter.</p>
              <p className="mt-1 text-sm">Passen Sie Suche oder Filter an.</p>
            </>
          )}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {filtered.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => navigate(`/checklisten/${t.id}`)}
              className="group flex flex-col rounded-2xl border border-slate-200 bg-white p-5 text-left transition-colors hover:border-indigo-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-indigo-600"
            >
              <div className="mb-2 flex items-start justify-between gap-3">
                <h3 className="text-base font-semibold text-slate-900 group-hover:text-indigo-700 dark:text-white dark:group-hover:text-indigo-300">
                  {t.title}
                </h3>
                <StatusBadge status={t.status} />
              </div>

              <p className="mb-4 line-clamp-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
                {t.description || 'Keine Beschreibung hinterlegt.'}
              </p>

              <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400 dark:text-slate-500">
                {t.source_document_name && (
                  <span className="inline-flex items-center gap-1" title={t.source_document_name}>
                    <FileText size={13} />
                    <span className="max-w-[140px] truncate">{t.source_document_name}</span>
                  </span>
                )}
                <span className="inline-flex items-center gap-1">
                  <Languages size={13} />
                  {(t.source_language || '–').toUpperCase()} → {(t.target_language || '–').toUpperCase()}
                </span>
                {t.node_count > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <ClipboardCheck size={13} />
                    {t.node_count} Knoten
                  </span>
                )}
                {t.my_role && (
                  <span className="inline-flex items-center gap-1">
                    <Users size={13} />
                    {t.my_role}
                  </span>
                )}
                <span className="ml-auto">{formatDate(t.updated_at)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
