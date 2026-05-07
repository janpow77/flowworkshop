import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Send, Loader2, AlertTriangle } from 'lucide-react';
import { getWorkshopAuthHeaders } from '../lib/api';

interface Category { slug: string; name: string; description: string | null; }

export default function NewThreadPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [categories, setCategories] = useState<Category[]>([]);
  const [categorySlug, setCategorySlug] = useState(params.get('c') || '');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/forum/categories').then((r) => r.ok ? r.json() : []).then(setCategories);
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!categorySlug || !title.trim() || !body.trim()) {
      setError('Bitte alle Felder ausfüllen.');
      return;
    }
    setSubmitting(true);
    try {
      const r = await fetch('/api/forum/threads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
        body: JSON.stringify({
          category_slug: categorySlug,
          title: title.trim(),
          body_md: body.trim(),
        }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail || 'Thread konnte nicht erstellt werden.');
        return;
      }
      const t = await r.json();
      navigate(`/forum/t/${t.id}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link to="/forum" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-cyan-600">
        <ArrowLeft size={16} /> Zurück zum Forum
      </Link>
      <div className="rounded-3xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Neuer Thread</h1>
        <p className="text-sm text-slate-500 mt-1">Stelle eine Frage, teile eine Erfahrung oder eröffne eine Diskussion.</p>

        {error && (
          <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-start gap-2 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
            <AlertTriangle size={16} className="mt-0.5" /><span>{error}</span>
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Kategorie *</label>
            <select value={categorySlug} onChange={(e) => setCategorySlug(e.target.value)} required
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800">
              <option value="">— wählen —</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>{c.name}</option>
              ))}
            </select>
            {categorySlug && (
              <p className="mt-1 text-[11px] text-slate-500">
                {categories.find((c) => c.slug === categorySlug)?.description}
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Titel *</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200}
              placeholder="Aussagekräftiger Titel"
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Beitrag *</label>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={10} required
              placeholder="Beschreiben Sie Ihre Frage / Erfahrung. Markdown wird unterstützt."
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-mono dark:border-slate-700 dark:bg-slate-800" />
            <p className="mt-1 text-[11px] text-slate-400">Markdown: **fett**, *kursiv*, `code`, &gt; Zitat, - Liste</p>
          </div>
          <div className="pt-2">
            <button type="submit" disabled={submitting}
              className="inline-flex items-center gap-2 rounded-full bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-50">
              {submitting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              Thread erstellen
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
