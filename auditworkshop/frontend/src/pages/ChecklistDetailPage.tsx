import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, ClipboardCheck, FileText, Languages, Users, AlertCircle, Wrench, Hash,
} from 'lucide-react';
import { getChecklistTemplate, type ChecklistTemplateDetail } from '../lib/api';
import { Skeleton } from '../components/ui/Skeleton';

function normStatus(raw: string): 'draft' | 'published' | 'archived' {
  const s = (raw || '').toLowerCase();
  if (s.includes('publish')) return 'published';
  if (s.includes('archiv')) return 'archived';
  return 'draft';
}

const STATUS_META: Record<'draft' | 'published' | 'archived', { label: string; cls: string }> = {
  draft: { label: 'Entwurf', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' },
  published: { label: 'Veröffentlicht', cls: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' },
  archived: { label: 'Archiviert', cls: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300' },
};

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function Prop({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">{label}</div>
      <div className="mt-1 text-sm text-slate-800 dark:text-slate-100">{children}</div>
    </div>
  );
}

export default function ChecklistDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tpl, setTpl] = useState<ChecklistTemplateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getChecklistTemplate(id)
      .then((r) => { if (!cancelled) { setTpl(r); setError(''); } })
      .catch(() => { if (!cancelled) setError('Diese Checkliste konnte nicht geladen werden.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  return (
    <div className="max-w-4xl mx-auto">
      <button
        type="button"
        onClick={() => navigate('/checklisten')}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
      >
        <ArrowLeft size={16} /> Zurück zur Übersicht
      </button>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-4 w-3/4" />
          <div className="grid gap-3 sm:grid-cols-2">
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
          </div>
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
          <AlertCircle size={16} />
          {error}
        </div>
      ) : tpl ? (
        <>
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 dark:text-white">
                <ClipboardCheck size={24} className="text-indigo-600 dark:text-indigo-400" />
                {tpl.title}
              </h1>
              {tpl.description && (
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">{tpl.description}</p>
              )}
            </div>
            <span className={`inline-flex shrink-0 items-center rounded-full px-3 py-1 text-xs font-medium ${STATUS_META[normStatus(tpl.status)].cls}`}>
              {STATUS_META[normStatus(tpl.status)].label}
            </span>
          </div>

          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Prop label="Quellsprache → Zielsprache">
              <span className="inline-flex items-center gap-1.5">
                <Languages size={14} className="text-slate-400" />
                {(tpl.source_language || '–').toUpperCase()} → {(tpl.target_language || '–').toUpperCase()}
              </span>
            </Prop>
            <Prop label="Knoten">
              <span className="inline-flex items-center gap-1.5">
                <Hash size={14} className="text-slate-400" />
                {tpl.node_count}
              </span>
            </Prop>
            <Prop label="Mitglieder">
              <span className="inline-flex items-center gap-1.5">
                <Users size={14} className="text-slate-400" />
                {tpl.members.length}
              </span>
            </Prop>
            {tpl.source_document_name && (
              <Prop label="Quelldokument">
                <span className="inline-flex items-center gap-1.5">
                  <FileText size={14} className="text-slate-400" />
                  <span className="truncate">{tpl.source_document_name}</span>
                </span>
              </Prop>
            )}
            {tpl.my_role && <Prop label="Meine Rolle">{tpl.my_role}</Prop>}
            <Prop label="Kategorien">{tpl.categories.length}</Prop>
            <Prop label="Erstellt">{formatDate(tpl.created_at)}</Prop>
            <Prop label="Zuletzt geändert">{formatDate(tpl.updated_at)}</Prop>
          </div>

          {tpl.categories.length > 0 && (
            <div className="mb-6">
              <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Kategorien</h2>
              <div className="flex flex-wrap gap-2">
                {tpl.categories.map((c) => (
                  <span key={c.id} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {c.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-dashed border-indigo-200 bg-indigo-50/50 px-5 py-8 text-center dark:border-indigo-900/50 dark:bg-indigo-950/20">
            <Wrench size={32} className="mx-auto mb-3 text-indigo-400 dark:text-indigo-500" />
            <p className="font-medium text-slate-700 dark:text-slate-200">Editor folgt</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">
              Der gemeinsame Treeview-Editor zum Bearbeiten und Diskutieren der Checklisten-Knoten
              wird in einer späteren Ausbaustufe ergänzt.
            </p>
          </div>
        </>
      ) : null}
    </div>
  );
}
