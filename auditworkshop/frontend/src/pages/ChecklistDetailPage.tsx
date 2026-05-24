import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, ClipboardCheck, FileText, Users, AlertCircle, Hash,
  Eye, Pencil, MessageSquare, Download,
} from 'lucide-react';
import { getChecklistTemplate, getMe, downloadSourceDocument, type ChecklistTemplateDetail } from '../lib/api';
import { Skeleton } from '../components/ui/Skeleton';
import TreeEditor from '../components/checklist/TreeEditor';
import { canComment, canEdit, normRole, ROLE_LABEL } from '../components/checklist/treeMeta';

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
  const [ownUserId, setOwnUserId] = useState<string | null>(null);
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

  // Eigene Nutzerkennung — fuer Presence-Markierung und Filterung eigener
  // SSE-Events (verhindert doppelte Anwendung optimistischer Updates).
  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((s) => { if (!cancelled) setOwnUserId(s.user_id); })
      .catch(() => { if (!cancelled) setOwnUserId(null); });
    return () => { cancelled = true; };
  }, []);

  const role = normRole(tpl?.my_role);
  const editable = canEdit(role);
  const commentable = canComment(role);

  const RoleIcon = editable ? Pencil : commentable ? MessageSquare : Eye;
  const roleHint = editable
    ? 'Sie können Struktur und Inhalte bearbeiten.'
    : commentable
      ? 'Sie können nur öffentliche Bemerkungen pflegen.'
      : 'Schreibgeschützte Ansicht.';

  return (
    <div className="max-w-6xl mx-auto">
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
          <Skeleton className="h-64 w-full" />
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
                <ClipboardCheck size={24} className="text-blue-600 dark:text-blue-400" />
                {tpl.title}
              </h1>
              {tpl.description && (
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">{tpl.description}</p>
              )}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${STATUS_META[normStatus(tpl.status)].cls}`}>
                {STATUS_META[normStatus(tpl.status)].label}
              </span>
              {role && (
                <span
                  title={roleHint}
                  className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                >
                  <RoleIcon size={13} /> {ROLE_LABEL[role]}
                </span>
              )}
            </div>
          </div>

          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
            <Prop label="Kategorien">{tpl.categories.length}</Prop>
            {tpl.source_document_name && (
              <Prop label="Quelldokument">
                <button
                  type="button"
                  onClick={() => { if (id) downloadSourceDocument(id).catch(() => {}); }}
                  className="inline-flex max-w-full items-center gap-1.5 text-blue-700 hover:underline dark:text-blue-400"
                  title="Quelldokument herunterladen"
                >
                  <FileText size={14} className="shrink-0" />
                  <span className="truncate">{tpl.source_document_name}</span>
                  <Download size={13} className="shrink-0" />
                </button>
              </Prop>
            )}
          </div>

          {tpl.members.length > 0 && (
            <div className="mb-6">
              <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
                <Users size={15} /> Mitglieder &amp; Rollen
              </h2>
              <div className="flex flex-wrap gap-2">
                {tpl.members.map((m) => {
                  const r = normRole(m.role);
                  return (
                    <span
                      key={m.id}
                      className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      title={[m.user_email, m.organization, m.bundesland].filter(Boolean).join(' · ')}
                    >
                      <span className="font-medium">{m.user_name || m.user_email || m.user_id}</span>
                      <span className="text-slate-400">·</span>
                      <span className="text-slate-500 dark:text-slate-400">{r ? ROLE_LABEL[r] : m.role}</span>
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {id && (
            <TreeEditor
              templateId={id}
              canEdit={editable}
              canComment={commentable}
              ownUserId={ownUserId}
              initialAnswerSets={tpl.answer_sets}
              initialCategories={tpl.categories}
            />
          )}
        </>
      ) : null}
    </div>
  );
}
