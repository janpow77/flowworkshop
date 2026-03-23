import { useState, useEffect, useReducer } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Trash2, FolderOpen, Sparkles, RotateCcw } from 'lucide-react';
import { listProjects, createProject, deleteProject, seedDemoData, resetDemoData, type Project } from '../lib/api';
import { Skeleton } from '../components/ui/Skeleton';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ aktenzeichen: '', geschaeftsjahr: '', projekttitel: '', zuwendungsempfaenger: '', foerdersumme: '' });
  const [reloadKey, triggerReload] = useReducer((x: number) => x + 1, 0);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((r) => { if (!cancelled) setProjects(r.projects); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [reloadKey]);

  const load = () => { setLoading(true); triggerReload(); };

  // ESC-Handler fuer Modal
  useEffect(() => {
    if (!showForm) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setShowForm(false); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [showForm]);

  const handleCreate = async () => {
    if (!form.aktenzeichen || !form.geschaeftsjahr) return;
    setError('');
    try {
      await createProject(form);
      setShowForm(false);
      setForm({ aktenzeichen: '', geschaeftsjahr: '', projekttitel: '', zuwendungsempfaenger: '', foerdersumme: '' });
      load();
    } catch {
      setError('Fehler beim Erstellen des Projekts.');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Projekt und alle Checklisten löschen?')) return;
    setError('');
    try {
      await deleteProject(id);
      load();
    } catch {
      setError('Fehler beim Löschen des Projekts.');
    }
  };

  const handleSeed = async () => {
    await seedDemoData();
    load();
  };

  const handleReset = async () => {
    if (!confirm('Alle Projekte, Checklisten und Fragen löschen?')) return;
    await resetDemoData();
    load();
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Projekte</h1>
        <div className="flex gap-2">
          {projects.length > 0 && (
            <button onClick={handleReset} className="flex items-center gap-2 px-3 py-2 text-sm bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors">
              <RotateCcw size={16} /> Zurücksetzen
            </button>
          )}
          <button onClick={handleSeed} className="flex items-center gap-2 px-3 py-2 text-sm bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors">
            <Sparkles size={16} /> Demo-Daten
          </button>
          <button onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 text-sm rounded-full bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 transition-colors">
            <Plus size={16} /> Neues Projekt
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400 mb-4">
          {error}
        </div>
      )}

      {/* Create form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowForm(false)}>
          <div role="dialog" aria-modal="true" className="bg-white dark:bg-slate-800 rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Neues Projekt</h2>
            <div className="space-y-3">
              <input value={form.aktenzeichen} onChange={(e) => setForm({ ...form, aktenzeichen: e.target.value })} placeholder="Aktenzeichen *" aria-label="Aktenzeichen" className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm" />
              <input value={form.geschaeftsjahr} onChange={(e) => setForm({ ...form, geschaeftsjahr: e.target.value })} placeholder="Geschäftsjahr *" aria-label="Geschäftsjahr" className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm" />
              <input value={form.projekttitel} onChange={(e) => setForm({ ...form, projekttitel: e.target.value })} placeholder="Projekttitel" aria-label="Projekttitel" className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm" />
              <input value={form.zuwendungsempfaenger} onChange={(e) => setForm({ ...form, zuwendungsempfaenger: e.target.value })} placeholder="Zuwendungsempfänger" aria-label="Zuwendungsempfänger" className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm" />
              <input value={form.foerdersumme} onChange={(e) => setForm({ ...form, foerdersumme: e.target.value })} placeholder="Fördersumme" aria-label="Fördersumme" className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm" />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">Abbrechen</button>
              <button onClick={handleCreate} disabled={!form.aktenzeichen || !form.geschaeftsjahr} className="px-4 py-2 text-sm rounded-full bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:disabled:bg-slate-700">Erstellen</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-3 w-16" />
                  </div>
                  <Skeleton className="h-5 w-48 mb-1" />
                  <Skeleton className="h-3 w-64" />
                </div>
                <div className="flex items-center gap-3">
                  <Skeleton className="h-3 w-20" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          <FolderOpen size={48} className="mx-auto mb-3" />
          <p>Keine Projekte vorhanden.</p>
          <p className="text-sm mt-1">Erstellen Sie ein neues Projekt oder laden Sie Demo-Daten.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              to={`/projects/${p.id}`}
              className="block rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 hover:border-indigo-300 dark:hover:border-indigo-600 transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm font-medium text-indigo-600 dark:text-indigo-400">{p.aktenzeichen}</span>
                    <span className="text-xs text-slate-400">GJ {p.geschaeftsjahr}</span>
                    {p.foerderphase && <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500">{p.foerderphase}</span>}
                  </div>
                  <h3 className="text-sm font-medium text-slate-900 dark:text-white">{p.projekttitel || 'Ohne Titel'}</h3>
                  {p.zuwendungsempfaenger && <p className="text-xs text-slate-500 mt-0.5">{p.zuwendungsempfaenger}</p>}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">{p.checklist_count} Checkliste(n)</span>
                  <button
                    onClick={(e) => { e.preventDefault(); handleDelete(p.id); }}
                    className="p-1.5 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                    aria-label="Projekt löschen"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
