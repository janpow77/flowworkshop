import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Plus, Trash2, ClipboardList, Loader2, Pencil } from 'lucide-react';
import {
  getProject, listChecklists, createChecklist, deleteChecklist, updateProject,
  listDemoTemplates, type Project, type Checklist, type DemoTemplate,
} from '../lib/api';
import Breadcrumb from '../components/layout/Breadcrumb';

type ProjectFormState = {
  aktenzeichen: string;
  geschaeftsjahr: string;
  projekttitel: string;
  zuwendungsempfaenger: string;
  foerdersumme: string;
  gesamtkosten: string;
  bewilligungszeitraum: string;
  foerderkennzeichen: string;
  program: string;
  foerderphase: Exclude<Project['foerderphase'], null> | '';
};

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [checklists, setChecklists] = useState<Checklist[]>([]);
  const [templates, setTemplates] = useState<DemoTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [error, setError] = useState('');
  const [formName, setFormName] = useState('');
  const [formTemplate, setFormTemplate] = useState('');
  const [projectForm, setProjectForm] = useState<ProjectFormState>({
    aktenzeichen: '',
    geschaeftsjahr: '',
    projekttitel: '',
    zuwendungsempfaenger: '',
    foerdersumme: '',
    gesamtkosten: '',
    bewilligungszeitraum: '',
    foerderkennzeichen: '',
    program: '',
    foerderphase: '',
  });

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [p, cl, t] = await Promise.all([
        getProject(projectId),
        listChecklists(projectId),
        listDemoTemplates(),
      ]);
      setProject(p);
      setChecklists(cl);
      setTemplates(t.templates);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  // ESC-Handler fuer Modals
  useEffect(() => {
    if (!showForm && !showEditForm) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setShowForm(false); setShowEditForm(false); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [showForm, showEditForm]);

  const handleCreate = async () => {
    if (!projectId || !formName) return;
    setError('');
    try {
      const result = await createChecklist(projectId, {
        name: formName,
        template_id: formTemplate || undefined,
      });
      setShowForm(false);
      setFormName('');
      setFormTemplate('');
      navigate(`/projects/${projectId}/checklists/${result.id}`);
    } catch {
      setError('Fehler beim Erstellen der Checkliste.');
    }
  };

  const openEditForm = () => {
    if (!project) return;
    setProjectForm({
      aktenzeichen: project.aktenzeichen,
      geschaeftsjahr: project.geschaeftsjahr,
      projekttitel: project.projekttitel || '',
      zuwendungsempfaenger: project.zuwendungsempfaenger || '',
      foerdersumme: project.foerdersumme || '',
      gesamtkosten: project.gesamtkosten || '',
      bewilligungszeitraum: project.bewilligungszeitraum || '',
      foerderkennzeichen: project.foerderkennzeichen || '',
      program: project.program || '',
      foerderphase: project.foerderphase || '',
    });
    setShowEditForm(true);
  };

  const handleUpdateProject = async () => {
    if (!projectId || !projectForm.aktenzeichen || !projectForm.geschaeftsjahr) return;
    setError('');
    try {
    await updateProject(projectId, {
      aktenzeichen: projectForm.aktenzeichen,
      geschaeftsjahr: projectForm.geschaeftsjahr,
      projekttitel: projectForm.projekttitel || null,
      zuwendungsempfaenger: projectForm.zuwendungsempfaenger || null,
      foerdersumme: projectForm.foerdersumme || null,
      gesamtkosten: projectForm.gesamtkosten || null,
      bewilligungszeitraum: projectForm.bewilligungszeitraum || null,
      foerderkennzeichen: projectForm.foerderkennzeichen || null,
      program: projectForm.program || null,
      foerderphase: projectForm.foerderphase || null,
    });
    setShowEditForm(false);
    await load();
    } catch {
      setError('Fehler beim Aktualisieren des Projekts.');
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-indigo-500" size={24} /></div>;
  if (!project) return <p className="text-slate-400">Projekt nicht gefunden.</p>;

  return (
    <div className="max-w-4xl mx-auto">
      <Breadcrumb items={[
        { label: 'Home', to: '/' },
        { label: 'Projekte', to: '/projects' },
        { label: project.projekttitel || project.aktenzeichen },
      ]} />

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400 mb-4">
          {error}
        </div>
      )}

      {/* Project info */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-mono text-lg font-bold text-indigo-600 dark:text-indigo-400">{project.aktenzeichen}</span>
              <span className="text-sm text-slate-400">GJ {project.geschaeftsjahr}</span>
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-1">{project.projekttitel || 'Ohne Titel'}</h1>
          </div>
          <button
            onClick={openEditForm}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <Pencil size={14} />
            Bearbeiten
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4 text-sm text-slate-600 dark:text-slate-400">
          {project.zuwendungsempfaenger && <div><span className="text-slate-400">Empfänger:</span> {project.zuwendungsempfaenger}</div>}
          {project.foerdersumme && <div><span className="text-slate-400">Fördersumme:</span> {project.foerdersumme}</div>}
          {project.gesamtkosten && <div><span className="text-slate-400">Gesamtkosten:</span> {project.gesamtkosten}</div>}
          {project.bewilligungszeitraum && <div><span className="text-slate-400">Zeitraum:</span> {project.bewilligungszeitraum}</div>}
          {project.foerderphase && <div><span className="text-slate-400">Phase:</span> {project.foerderphase}</div>}
          {project.foerderkennzeichen && <div><span className="text-slate-400">FKZ:</span> {project.foerderkennzeichen}</div>}
        </div>
      </div>

      {showEditForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowEditForm(false)}>
          <div role="dialog" aria-modal="true" className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl dark:bg-slate-800" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-lg font-semibold text-slate-900 dark:text-white">Projekt bearbeiten</h3>
            <div className="grid gap-3 md:grid-cols-2">
              <input value={projectForm.aktenzeichen} onChange={(e) => setProjectForm({ ...projectForm, aktenzeichen: e.target.value })} placeholder="Aktenzeichen *" aria-label="Aktenzeichen" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <input value={projectForm.geschaeftsjahr} onChange={(e) => setProjectForm({ ...projectForm, geschaeftsjahr: e.target.value })} placeholder="Geschäftsjahr *" aria-label="Geschäftsjahr" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <input value={projectForm.projekttitel} onChange={(e) => setProjectForm({ ...projectForm, projekttitel: e.target.value })} placeholder="Projekttitel" aria-label="Projekttitel" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700 md:col-span-2" />
              <input value={projectForm.zuwendungsempfaenger} onChange={(e) => setProjectForm({ ...projectForm, zuwendungsempfaenger: e.target.value })} placeholder="Zuwendungsempfänger" aria-label="Zuwendungsempfänger" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <input value={projectForm.program} onChange={(e) => setProjectForm({ ...projectForm, program: e.target.value })} placeholder="Programm" aria-label="Programm" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <input value={projectForm.foerdersumme} onChange={(e) => setProjectForm({ ...projectForm, foerdersumme: e.target.value })} placeholder="Fördersumme" aria-label="Fördersumme" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <input value={projectForm.gesamtkosten} onChange={(e) => setProjectForm({ ...projectForm, gesamtkosten: e.target.value })} placeholder="Gesamtkosten" aria-label="Gesamtkosten" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <input value={projectForm.bewilligungszeitraum} onChange={(e) => setProjectForm({ ...projectForm, bewilligungszeitraum: e.target.value })} placeholder="Bewilligungszeitraum" aria-label="Bewilligungszeitraum" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <input value={projectForm.foerderkennzeichen} onChange={(e) => setProjectForm({ ...projectForm, foerderkennzeichen: e.target.value })} placeholder="Förderkennzeichen" aria-label="Förderkennzeichen" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700" />
              <select value={projectForm.foerderphase} onChange={(e) => setProjectForm({ ...projectForm, foerderphase: (e.target.value || '') as ProjectFormState['foerderphase'] })} aria-label="Förderphase" className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700">
                <option value="">Förderphase</option>
                <option value="2014-2020">2014-2020</option>
                <option value="2021-2027">2021-2027</option>
              </select>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowEditForm(false)} className="rounded-lg px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700">Abbrechen</button>
              <button onClick={handleUpdateProject} disabled={!projectForm.aktenzeichen || !projectForm.geschaeftsjahr} className="rounded-full bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:disabled:bg-slate-700">Speichern</button>
            </div>
          </div>
        </div>
      )}

      {/* Checklists */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Checklisten</h2>
        <button onClick={() => setShowForm(true)} className="flex items-center gap-2 px-3 py-2 text-sm rounded-full bg-slate-900 text-white hover:bg-slate-800 dark:bg-indigo-500 dark:hover:bg-indigo-400">
          <Plus size={16} /> Neue Checkliste
        </button>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowForm(false)}>
          <div role="dialog" aria-modal="true" className="bg-white dark:bg-slate-800 rounded-xl p-6 w-full max-w-md shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-4 text-slate-900 dark:text-white">Neue Checkliste</h3>
            <div className="space-y-3">
              <input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Name der Checkliste *" aria-label="Name der Checkliste" className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm" />
              {templates.length > 0 && (
                <select value={formTemplate} onChange={(e) => { setFormTemplate(e.target.value); if (e.target.value && !formName) { const t = templates.find(t => t.template_id === e.target.value); if (t) setFormName(t.name); } }} aria-label="Vorlage" className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm">
                  <option value="">Ohne Vorlage</option>
                  {templates.map((t) => (
                    <option key={t.template_id} value={t.template_id}>{t.name} ({t.question_count} Fragen)</option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">Abbrechen</button>
              <button onClick={handleCreate} disabled={!formName} className="px-4 py-2 text-sm rounded-full bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:disabled:bg-slate-700">Erstellen</button>
            </div>
          </div>
        </div>
      )}

      {checklists.length === 0 ? (
        <div className="text-center py-12 text-slate-400 border border-dashed border-slate-300 dark:border-slate-600 rounded-xl">
          <ClipboardList size={40} className="mx-auto mb-2" />
          <p>Keine Checklisten vorhanden.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {checklists.map((cl) => (
            <Link
              key={cl.id}
              to={`/projects/${projectId}/checklists/${cl.id}`}
              className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 hover:border-indigo-300 dark:hover:border-indigo-600 transition-colors group"
            >
              <div>
                <h3 className="font-medium text-slate-900 dark:text-white text-sm">{cl.name}</h3>
                {cl.description && <p className="text-xs text-slate-500 mt-0.5">{cl.description}</p>}
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span>{cl.question_count} Fragen</span>
                {cl.ai_assessed_count > 0 && (
                  <span className="text-indigo-500">{cl.ai_assessed_count} KI-bewertet</span>
                )}
                <button
                  onClick={(e) => { e.preventDefault(); if (confirm('Checkliste löschen?')) deleteChecklist(projectId!, cl.id).then(load); }}
                  className="p-1 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100"
                  aria-label="Löschen"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
