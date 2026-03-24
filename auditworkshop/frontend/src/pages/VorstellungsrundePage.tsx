import { useState, useEffect, useCallback } from 'react';
import {
  Users, Building2, Briefcase, Cpu, Target, ChevronRight,
  Timer, ArrowLeft, Plus, Pencil, Trash2, Save, X,
  ArrowUp, ArrowDown, MessageCircle, Lightbulb, Heart,
  Star, Zap, Globe, BookOpen, Award,
} from 'lucide-react';
import { Link } from 'react-router-dom';

// Alle verfuegbaren Icons fuer die Auswahl
const ICON_MAP: Record<string, typeof Users> = {
  Users, Building2, Briefcase, Cpu, Target, MessageCircle,
  Lightbulb, Heart, Star, Zap, Globe, BookOpen, Award,
};

const COLOR_STYLES: Record<string, { text: string; bg: string; ring: string }> = {
  blue:    { text: 'text-blue-600 dark:text-blue-400',    bg: 'bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800',       ring: 'ring-blue-500' },
  emerald: { text: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800', ring: 'ring-emerald-500' },
  amber:   { text: 'text-amber-600 dark:text-amber-400',  bg: 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800',   ring: 'ring-amber-500' },
  violet:  { text: 'text-violet-600 dark:text-violet-400', bg: 'bg-violet-50 dark:bg-violet-950/40 border-violet-200 dark:border-violet-800', ring: 'ring-violet-500' },
  rose:    { text: 'text-rose-600 dark:text-rose-400',    bg: 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-800',       ring: 'ring-rose-500' },
  sky:     { text: 'text-sky-600 dark:text-sky-400',      bg: 'bg-sky-50 dark:bg-sky-950/40 border-sky-200 dark:border-sky-800',           ring: 'ring-sky-500' },
  indigo:  { text: 'text-indigo-600 dark:text-indigo-400', bg: 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-200 dark:border-indigo-800', ring: 'ring-indigo-500' },
  teal:    { text: 'text-teal-600 dark:text-teal-400',    bg: 'bg-teal-50 dark:bg-teal-950/40 border-teal-200 dark:border-teal-800',       ring: 'ring-teal-500' },
};

const AVAILABLE_COLORS = Object.keys(COLOR_STYLES);
const AVAILABLE_ICONS = Object.keys(ICON_MAP);

interface IcebreakerQ {
  id: string;
  label: string;
  hint: string | null;
  icon_name: string;
  color: string;
  sort_order: number;
}

function modFetch(url: string, options?: RequestInit): Promise<Response> {
  const token = localStorage.getItem('workshop_token') || '';
  return fetch(url, {
    ...options,
    headers: { ...options?.headers, Authorization: `Bearer ${token}` },
  });
}

export default function VorstellungsrundePage() {
  const [questions, setQuestions] = useState<IcebreakerQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeQ, setActiveQ] = useState(0);
  const [autoPlay, setAutoPlay] = useState(false);
  const [isAdmin] = useState(() => localStorage.getItem('workshop_role') === 'moderator');

  // Edit-State
  const [editId, setEditId] = useState<string | null>(null);
  const [editData, setEditData] = useState({ label: '', hint: '', icon_name: 'Users', color: 'blue' });
  const [showAdd, setShowAdd] = useState(false);
  const [newData, setNewData] = useState({ label: '', hint: '', icon_name: 'Users', color: 'blue' });

  const loadQuestions = useCallback(() => {
    fetch('/api/event/icebreaker').then(r => r.json()).then(data => {
      setQuestions(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => { loadQuestions(); }, [loadQuestions]);

  // Auto-Rotation
  useEffect(() => {
    if (!autoPlay || questions.length === 0) return;
    const t = setInterval(() => {
      setActiveQ((prev) => (prev + 1) % questions.length);
    }, 8000);
    return () => clearInterval(t);
  }, [autoPlay, questions.length]);

  const startEdit = (q: IcebreakerQ) => {
    setEditId(q.id);
    setEditData({ label: q.label, hint: q.hint || '', icon_name: q.icon_name, color: q.color });
  };

  const saveEdit = async () => {
    if (!editId) return;
    await modFetch(`/api/event/admin/icebreaker/${editId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editData),
    });
    setEditId(null);
    loadQuestions();
  };

  const addQuestion = async () => {
    if (!newData.label) return;
    await modFetch('/api/event/admin/icebreaker', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newData),
    });
    setNewData({ label: '', hint: '', icon_name: 'Users', color: 'blue' });
    setShowAdd(false);
    loadQuestions();
  };

  const deleteQuestion = async (id: string) => {
    await modFetch(`/api/event/admin/icebreaker/${id}`, { method: 'DELETE' });
    loadQuestions();
  };

  const moveQuestion = async (id: string, direction: -1 | 1) => {
    const idx = questions.findIndex(q => q.id === id);
    if (idx < 0) return;
    const swapIdx = idx + direction;
    if (swapIdx < 0 || swapIdx >= questions.length) return;
    const order = questions.map(q => q.id);
    [order[idx], order[swapIdx]] = [order[swapIdx], order[idx]];
    await modFetch('/api/event/admin/icebreaker/reorder', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(order),
    });
    loadQuestions();
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-20 text-center text-slate-400">Laden...</div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link
          to="/agenda"
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
        >
          <ArrowLeft size={16} /> Zurueck zur Tagesordnung
        </Link>
        <button
          onClick={() => setAutoPlay(!autoPlay)}
          className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all ${
            autoPlay
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
          }`}
        >
          <Timer size={14} />
          {autoPlay ? 'Auto-Rotation aktiv' : 'Auto-Rotation'}
        </button>
      </div>

      {/* Titel-Bereich */}
      <section className="relative overflow-hidden rounded-[32px] border border-white/70 bg-gradient-to-br from-indigo-900 via-blue-900 to-cyan-900 px-8 py-10 text-white shadow-[0_40px_120px_-48px_rgba(30,27,75,0.9)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.12),transparent_40%)]" />
        <div className="relative text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-white/80 mb-4">
            <Users size={14} /> Workshop 5
          </div>
          <h1 className="text-4xl font-bold tracking-tight lg:text-5xl">Vorstellungsrunde</h1>
          <p className="mt-3 text-lg text-blue-100/80">
            Bitte stellen Sie sich kurz vor — orientieren Sie sich an den folgenden Punkten.
          </p>
        </div>
      </section>

      {/* Fragen-Karten */}
      <section className="space-y-4">
        {questions.map((q, i) => {
          const Icon = ICON_MAP[q.icon_name] || Users;
          const colors = COLOR_STYLES[q.color] || COLOR_STYLES.blue;
          const isActive = i === activeQ;
          const isEditing = editId === q.id;

          return (
            <div key={q.id}>
              <button
                onClick={() => { if (!isEditing) { setActiveQ(i); setAutoPlay(false); } }}
                className={`w-full text-left rounded-2xl border-2 p-5 transition-all duration-500 ease-out ${colors.bg} ${
                  isActive && !isEditing
                    ? `scale-[1.02] shadow-lg ring-2 ring-offset-2 ring-offset-white dark:ring-offset-slate-950 ${colors.ring}`
                    : isEditing ? 'ring-2 ring-indigo-400' : 'opacity-60 hover:opacity-80'
                }`}
              >
                <div className="flex items-start gap-4">
                  <div className={`shrink-0 mt-0.5 transition-transform duration-500 ${isActive && !isEditing ? 'scale-125' : ''}`}>
                    <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${
                      isActive ? 'bg-white/90 dark:bg-slate-800 shadow-md' : 'bg-white/60 dark:bg-slate-800/60'
                    }`}>
                      <Icon size={24} className={colors.text} />
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <span className={`text-sm font-bold ${colors.text}`}>{i + 1}.</span>
                      <h3 className={`text-xl font-semibold transition-all duration-300 ${
                        isActive ? 'text-slate-900 dark:text-white' : 'text-slate-700 dark:text-slate-300'
                      }`}>
                        {q.label}
                      </h3>
                      {isActive && !isEditing && <ChevronRight size={18} className={`${colors.text} animate-pulse`} />}
                    </div>
                    <p className={`mt-1 transition-all duration-500 ${
                      isActive && !isEditing
                        ? 'text-base text-slate-600 dark:text-slate-400 max-h-20 opacity-100'
                        : 'text-sm text-slate-500 max-h-0 opacity-0 overflow-hidden'
                    }`}>
                      {q.hint}
                    </p>
                  </div>
                  {/* Admin-Buttons */}
                  {isAdmin && !isEditing && (
                    <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <button onClick={(e) => { e.stopPropagation(); moveQuestion(q.id, -1); }} className="p-1 rounded text-slate-400 hover:bg-white/60 hover:text-slate-600 transition-colors" title="Nach oben"><ArrowUp size={13} /></button>
                      <button onClick={(e) => { e.stopPropagation(); moveQuestion(q.id, 1); }} className="p-1 rounded text-slate-400 hover:bg-white/60 hover:text-slate-600 transition-colors" title="Nach unten"><ArrowDown size={13} /></button>
                      <button onClick={(e) => { e.stopPropagation(); startEdit(q); }} className="p-1 rounded text-slate-400 hover:bg-white/60 hover:text-indigo-600 transition-colors" title="Bearbeiten"><Pencil size={13} /></button>
                      <button onClick={(e) => { e.stopPropagation(); if (confirm('Frage loeschen?')) deleteQuestion(q.id); }} className="p-1 rounded text-slate-400 hover:bg-white/60 hover:text-red-600 transition-colors" title="Loeschen"><Trash2 size={13} /></button>
                    </div>
                  )}
                </div>
              </button>

              {/* Inline Edit */}
              {isEditing && isAdmin && (
                <div className="mt-2 rounded-xl border-2 border-indigo-400 bg-white dark:bg-slate-900 p-4 space-y-3">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <input value={editData.label} onChange={(e) => setEditData({ ...editData, label: e.target.value })} placeholder="Frage / Label *" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
                    <input value={editData.hint} onChange={(e) => setEditData({ ...editData, hint: e.target.value })} placeholder="Hinweis / Erlaeuterung" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Icon</label>
                      <div className="flex flex-wrap gap-1">
                        {AVAILABLE_ICONS.map(name => {
                          const I = ICON_MAP[name];
                          return (
                            <button key={name} onClick={() => setEditData({ ...editData, icon_name: name })}
                              className={`p-1.5 rounded-lg border transition-all ${editData.icon_name === name ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40' : 'border-slate-200 dark:border-slate-700 hover:border-slate-400'}`}
                              title={name}>
                              <I size={16} className={editData.icon_name === name ? 'text-indigo-600' : 'text-slate-400'} />
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Farbe</label>
                      <div className="flex flex-wrap gap-1">
                        {AVAILABLE_COLORS.map(c => (
                          <button key={c} onClick={() => setEditData({ ...editData, color: c })}
                            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
                              editData.color === c
                                ? `${COLOR_STYLES[c].bg} ${COLOR_STYLES[c].text} border-current`
                                : 'border-slate-200 dark:border-slate-700 text-slate-500 hover:border-slate-400'
                            }`}>
                            {c}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={saveEdit} className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700"><Save size={12} /> Speichern</button>
                    <button onClick={() => setEditId(null)} className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-400"><X size={12} /> Abbrechen</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* Neue Frage hinzufuegen */}
        {isAdmin && (
          showAdd ? (
            <div className="rounded-xl border-2 border-dashed border-emerald-400 bg-emerald-50/50 dark:bg-emerald-950/20 dark:border-emerald-700 p-4 space-y-3">
              <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">Neue Frage hinzufuegen</p>
              <div className="grid gap-2 sm:grid-cols-2">
                <input value={newData.label} onChange={(e) => setNewData({ ...newData, label: e.target.value })} placeholder="Frage / Label *" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
                <input value={newData.hint} onChange={(e) => setNewData({ ...newData, hint: e.target.value })} placeholder="Hinweis / Erlaeuterung" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Icon</label>
                  <div className="flex flex-wrap gap-1">
                    {AVAILABLE_ICONS.map(name => {
                      const I = ICON_MAP[name];
                      return (
                        <button key={name} onClick={() => setNewData({ ...newData, icon_name: name })}
                          className={`p-1.5 rounded-lg border transition-all ${newData.icon_name === name ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40' : 'border-slate-200 dark:border-slate-700 hover:border-slate-400'}`}
                          title={name}>
                          <I size={16} className={newData.icon_name === name ? 'text-indigo-600' : 'text-slate-400'} />
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Farbe</label>
                  <div className="flex flex-wrap gap-1">
                    {AVAILABLE_COLORS.map(c => (
                      <button key={c} onClick={() => setNewData({ ...newData, color: c })}
                        className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
                          newData.color === c
                            ? `${COLOR_STYLES[c].bg} ${COLOR_STYLES[c].text} border-current`
                            : 'border-slate-200 dark:border-slate-700 text-slate-500 hover:border-slate-400'
                        }`}>
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={addQuestion} disabled={!newData.label} className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700 disabled:bg-slate-300"><Plus size={12} /> Hinzufuegen</button>
                <button onClick={() => setShowAdd(false)} className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-400"><X size={12} /> Abbrechen</button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-2 rounded-xl border-2 border-dashed border-slate-300 dark:border-slate-700 px-5 py-3 text-sm text-slate-400 hover:border-emerald-400 hover:text-emerald-600 hover:bg-emerald-50/50 dark:hover:bg-emerald-950/20 transition-all w-full"
            >
              <Plus size={16} /> Frage hinzufuegen
            </button>
          )
        )}
      </section>

      {/* Fortschritts-Dots */}
      {questions.length > 0 && (
        <div className="flex justify-center gap-2 pb-4">
          {questions.map((q, i) => (
            <button
              key={q.id}
              onClick={() => { setActiveQ(i); setAutoPlay(false); }}
              className={`h-2.5 rounded-full transition-all duration-300 ${
                i === activeQ ? 'w-8 bg-indigo-500' : 'w-2.5 bg-slate-300 dark:bg-slate-700 hover:bg-slate-400'
              }`}
              aria-label={`Frage ${i + 1}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
