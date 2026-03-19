import {
  startTransition, useDeferredValue, useEffect, useRef, useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight, Building2, Database, FileSearch, FolderOpen, Keyboard, MapPin, Scale, Search, Sparkles,
} from 'lucide-react';
import { seedDemoData } from '../../lib/api';

interface Command {
  id: string;
  label: string;
  description: string;
  keywords: string;
  icon: typeof Search;
  action: () => Promise<void> | void;
}

export default function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());

  const commands: Command[] = [
    {
      id: 'home',
      label: 'Home öffnen',
      description: 'Zur Startübersicht mit Pipeline und Szenarien',
      keywords: 'start home dashboard',
      icon: Sparkles,
      action: () => navigate('/'),
    },
    {
      id: 'scenario-1',
      label: 'Szenario 1: Dokumentenanalyse',
      description: 'Bescheide strukturieren und Auflagen extrahieren',
      keywords: 'dokument bescheid analyse auflagen',
      icon: FileSearch,
      action: () => navigate('/scenario/1'),
    },
    {
      id: 'demo-checklist',
      label: 'Demo-Checkliste öffnen',
      description: 'Seedet Demo-Daten und springt direkt in die Checkliste',
      keywords: 'demo checklist projekt seed vko',
      icon: FolderOpen,
      action: async () => {
        const result = await seedDemoData();
        if (result.project_id && result.checklist_id) {
          navigate(`/projects/${result.project_id}/checklists/${result.checklist_id}`);
          return;
        }
        navigate('/projects');
      },
    },
    {
      id: 'projects',
      label: 'Projektarbeitsraum öffnen',
      description: 'Projekte, Checklisten und Demo-Daten verwalten',
      keywords: 'projekt checklist arbeitsraum',
      icon: FolderOpen,
      action: () => navigate('/projects'),
    },
    {
      id: 'knowledge',
      label: 'Wissensbasis öffnen',
      description: 'Quellen verwalten, semantisch suchen, RAG testen',
      keywords: 'wissen rag suche dokumente',
      icon: Database,
      action: () => navigate('/knowledge'),
    },
    {
      id: 'beneficiaries',
      label: 'Begünstigtenanalyse öffnen',
      description: 'Karte, Upload und Statistikfragen für Transparenzlisten',
      keywords: 'begünstigte karte transparenzliste statistik',
      icon: MapPin,
      action: () => navigate('/scenario/6'),
    },
    {
      id: 'company-search',
      label: 'Unternehmenssuche öffnen',
      description: 'Unternehmen, Vorhaben und Aktenzeichen über geladene Verzeichnisse durchsuchen',
      keywords: 'unternehmen vorhaben aktenzeichen suche recherchieren',
      icon: Building2,
      action: () => navigate('/company-search'),
    },
    {
      id: 'ai-act',
      label: 'AI Act öffnen',
      description: 'Prüfer-Merkblatt zu roten Linien, Risiken und Leitplanken beim KI-Einsatz',
      keywords: 'ai act recht risiko verbote prüfer compliance',
      icon: Scale,
      action: () => navigate('/ai-act'),
    },
  ];

  const filteredCommands = deferredQuery
    ? commands.filter((command) => {
        const haystack = `${command.label} ${command.description} ${command.keywords}`.toLowerCase();
        return haystack.includes(deferredQuery);
      })
    : commands;

  const close = () => { setQuery(''); setOpen(false); };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((current) => {
          const next = !current;
          if (!next) setQuery('');
          return next;
        });
      }
      if (event.key === 'Escape') {
        setQuery('');
        setOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const prevOpenRef = useRef(open);
  useEffect(() => {
    if (open && !prevOpenRef.current) {
      inputRef.current?.focus();
    }
    prevOpenRef.current = open;
  }, [open]);

  const runCommand = async (command: Command) => {
    await command.action();
    close();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/45 px-4 pt-[12vh] backdrop-blur-sm" onClick={() => close()} role="presentation">
      <div role="dialog" aria-modal="true" aria-label="Schnellzugriff" onKeyDown={(e) => { if (e.key === 'Escape') close(); }} className="w-full max-w-2xl overflow-hidden rounded-[28px] border border-white/80 bg-white/92 shadow-[0_32px_120px_-56px_rgba(15,23,42,0.85)] backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/88" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-300">
            <Search size={18} />
          </div>
          <div className="flex-1">
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => startTransition(() => setQuery(event.target.value))}
              placeholder="Befehl oder Bereich suchen…"
              className="w-full bg-transparent text-base text-slate-900 outline-none placeholder:text-slate-400 dark:text-slate-100"
              aria-label="Befehlspalette"
            />
            <div className="mt-1 text-xs text-slate-400">Cmd/Ctrl + K für Schnellnavigation</div>
          </div>
          <div className="hidden items-center gap-1 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400 md:inline-flex">
            <Keyboard size={12} />
            Esc
          </div>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-3">
          {filteredCommands.length === 0 ? (
            <div className="rounded-2xl bg-slate-50 px-4 py-6 text-sm text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              Kein passender Befehl gefunden.
            </div>
          ) : (
            <div className="space-y-2">
              {filteredCommands.map((command) => {
                const Icon = command.icon;
                return (
                  <button
                    key={command.id}
                    onClick={() => { void runCommand(command); }}
                    className="flex w-full items-center gap-4 rounded-2xl border border-transparent px-4 py-3 text-left transition hover:border-slate-200 hover:bg-slate-50 dark:hover:border-slate-800 dark:hover:bg-slate-900"
                  >
                    <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                      <Icon size={18} />
                    </span>
                    <span className="flex-1">
                      <span className="block text-sm font-medium text-slate-900 dark:text-slate-100">{command.label}</span>
                      <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{command.description}</span>
                    </span>
                    <ArrowRight size={16} className="text-slate-300 dark:text-slate-600" />
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
