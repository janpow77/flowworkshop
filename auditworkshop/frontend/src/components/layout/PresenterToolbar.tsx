import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Presentation, Timer, Keyboard, X } from 'lucide-react';

const STEPS = [
  { path: '/', label: 'Startseite' },
  { path: '/scenario/1', label: 'Szenario 1: Dokumentenanalyse' },
  { path: '/scenario/2', label: 'Szenario 2: Checklisten-KI' },
  { path: '/scenario/3', label: 'Szenario 3: Halluzinations-Demo' },
  { path: '/scenario/4', label: 'Szenario 4: Berichtsentwurf' },
  { path: '/scenario/5', label: 'Szenario 5: Vorab-Upload & RAG' },
  { path: '/scenario/6', label: 'Szenario 6: Begünstigtenverzeichnis' },
];

export default function PresenterToolbar() {
  const [visible, setVisible] = useState(false);
  const [lastLatency, setLastLatency] = useState<number | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const currentIndex = STEPS.findIndex(s => s.path === location.pathname);

  const goTo = useCallback((dir: -1 | 1) => {
    const next = currentIndex + dir;
    if (next >= 0 && next < STEPS.length) navigate(STEPS[next].path);
  }, [currentIndex, navigate]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.altKey && e.key === 'p') { e.preventDefault(); setVisible(v => !v); }
      if (!visible) return;
      if (e.altKey && e.key >= '1' && e.key <= '6') {
        e.preventDefault();
        navigate(`/scenario/${e.key}`);
      }
      if (e.altKey && e.key === 'ArrowRight') { e.preventDefault(); goTo(1); }
      if (e.altKey && e.key === 'ArrowLeft') { e.preventDefault(); goTo(-1); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, navigate, goTo]);

  // Auf Latenz-Events von LLM-Antworten lauschen
  useEffect(() => {
    const handler = ((e: CustomEvent) => setLastLatency(e.detail)) as EventListener;
    window.addEventListener('llm-latency', handler);
    return () => window.removeEventListener('llm-latency', handler);
  }, []);

  if (!visible) return null;

  return (
    <div className="sticky top-0 z-40 flex items-center gap-3 border-b border-indigo-200 bg-indigo-50/95 px-4 py-2 backdrop-blur dark:border-indigo-800 dark:bg-indigo-950/95">
      <Presentation size={16} className="text-indigo-500" />
      <span className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">PRESENTER</span>

      <div className="mx-2 h-4 w-px bg-indigo-200 dark:bg-indigo-700" />

      {/* Navigation */}
      <button onClick={() => goTo(-1)} disabled={currentIndex <= 0}
        className="rounded-lg p-1 text-indigo-400 hover:bg-indigo-100 disabled:opacity-30 dark:hover:bg-indigo-900"
        aria-label="Vorheriger Schritt">
        <ChevronLeft size={16} />
      </button>
      <span className="min-w-[200px] text-center text-xs font-medium text-indigo-900 dark:text-indigo-200">
        {currentIndex >= 0 ? `${currentIndex + 1}/${STEPS.length}: ${STEPS[currentIndex].label}` : location.pathname}
      </span>
      <button onClick={() => goTo(1)} disabled={currentIndex >= STEPS.length - 1}
        className="rounded-lg p-1 text-indigo-400 hover:bg-indigo-100 disabled:opacity-30 dark:hover:bg-indigo-900"
        aria-label="Nächster Schritt">
        <ChevronRight size={16} />
      </button>

      <div className="flex-1" />

      {/* Latenz-Anzeige */}
      {lastLatency !== null && (
        <div className="flex items-center gap-1 text-xs text-indigo-500">
          <Timer size={12} />
          <span>{lastLatency}ms</span>
        </div>
      )}

      {/* Shortcut-Hinweise */}
      <div className="hidden xl:flex items-center gap-1 text-[10px] text-indigo-400">
        <Keyboard size={12} />
        <span>Alt+1-6 Szenarien | Alt+←→ Nav | Alt+P Toggle</span>
      </div>

      <button onClick={() => setVisible(false)} className="rounded-lg p-1 text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-900" aria-label="Presenter-Modus schließen">
        <X size={14} />
      </button>
    </div>
  );
}
