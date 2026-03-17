import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { BookOpen, X } from 'lucide-react';

const NOTES: Record<string, { title: string; bullets: string[] }> = {
  '/': {
    title: 'Begrüßung & Überblick',
    bullets: [
      'Vorstellungsrunde falls nötig',
      'Ziel: Praktische Demonstration, keine Theorie-Vorlesung',
      'Alle Daten bleiben lokal -- kein Cloud-LLM',
      'Hardware: NUC 15 mit RTX 5070 Ti, 16 GB VRAM',
      'Modell: Qwen3-14B (lokal, quantisiert)',
    ],
  },
  '/scenario/1': {
    title: 'Dokumentenanalyse',
    bullets: [
      'Demo-Dokument laden oder eigenen Bescheid hochladen',
      'Zeigen: Auflagen werden strukturiert extrahiert',
      'Betonen: KI urteilt NICHT, sie extrahiert nur',
      'Hinweis auf Disclaimer unter jeder Antwort',
      'Nachfragen: Welche Dokumente analysieren Sie regelmäßig?',
    ],
  },
  '/scenario/2': {
    title: 'Checklisten-KI',
    bullets: [
      'Erst Demo-Daten laden (Button auf Startseite)',
      '25 VKO-Prüfpunkte zeigen, einzeln bewerten lassen',
      'Accept/Reject/Edit-Workflow demonstrieren',
      'Dann "Alle bewerten" für Bulk-Assessment',
      'Betonen: Prüfer behält volle Kontrolle',
    ],
  },
  '/scenario/3': {
    title: 'Halluzinations-Demo',
    bullets: [
      'ERST ohne RAG-Kontext fragen -- KI erfindet Artikelnummern!',
      'DANN mit RAG-Kontext -- KI zitiert nur aus Wissensdatenbank',
      'Split-View zeigt den Unterschied deutlich',
      'Kernbotschaft: RAG ist PFLICHT für rechtliche Fragen',
      'Frage ans Publikum: Wo sehen Sie Risiken?',
    ],
  },
  '/scenario/4': {
    title: 'Berichtsentwurf',
    bullets: [
      'Demo-Feststellungen laden',
      'KI formuliert sachlich-verwaltungsrechtlich',
      'Stilregeln: Indikativ, Perfekt, keine wertenden Adjektive',
      'Kopieren-Button für Übernahme in Bericht',
      'Betonen: Entwurf, nicht fertiger Bericht!',
    ],
  },
  '/scenario/5': {
    title: 'Vorab-Upload & RAG',
    bullets: [
      'Eigene Dokumente der Teilnehmer hochladen lassen',
      'Chunking und Embedding dauert wenige Sekunden',
      'Fragen an die eigenen Dokumente stellen',
      'Quellenverweise in der Antwort zeigen',
      'Betonen: Dokumente bleiben lokal!',
    ],
  },
  '/scenario/6': {
    title: 'Begünstigtenverzeichnis',
    bullets: [
      'Hessen-XLSX laden (liegt im Demo-Ordner)',
      'Auto-Erkennung Bundesland + Spalten zeigen',
      'Geocoding-Cache demonstrieren (schnell beim 2. Mal)',
      'Leaflet-Karte mit Filtern zeigen',
      'Optional: Zweites Bundesland parallel laden',
      'LLM-Prompt für statistische Fragen nutzen',
    ],
  },
};

export default function SprechzettelPanel() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const note = NOTES[location.pathname];

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.altKey && e.key === 's') { e.preventDefault(); setOpen(v => !v); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <>
      {/* Toggle-Button -- nur sichtbar wenn Notizen für die aktuelle Seite existieren */}
      {!open && note && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-4 right-4 z-50 rounded-full bg-indigo-600 p-3 text-white shadow-lg hover:bg-indigo-700 transition-transform hover:scale-105"
          aria-label="Sprechzettel öffnen (Alt+S)"
          title="Sprechzettel (Alt+S)"
        >
          <BookOpen size={20} />
        </button>
      )}

      {/* Drawer */}
      {open && (
        <div className="fixed inset-y-0 right-0 z-50 w-80 border-l border-slate-200 bg-white/95 backdrop-blur shadow-2xl dark:border-slate-700 dark:bg-slate-900/95 flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <div className="flex items-center gap-2">
              <BookOpen size={16} className="text-indigo-500" />
              <span className="text-sm font-semibold text-slate-900 dark:text-white">Sprechzettel</span>
            </div>
            <button onClick={() => setOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Schließen">
              <X size={16} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {note ? (
              <>
                <h3 className="text-base font-bold text-slate-900 dark:text-white mb-3">{note.title}</h3>
                <ul className="space-y-2">
                  {note.bullets.map((b, i) => (
                    <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
                      {b}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-sm text-slate-400">Kein Sprechzettel für diese Seite.</p>
            )}
          </div>
          <div className="border-t border-slate-200 px-4 py-2 text-[10px] text-slate-400 dark:border-slate-700">
            Alt+S zum Umschalten
          </div>
        </div>
      )}
    </>
  );
}
