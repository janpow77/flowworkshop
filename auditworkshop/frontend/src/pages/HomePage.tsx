import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FileSearch, CheckSquare, AlertTriangle, FileText, Upload, MapPin,
  ArrowRight, ShieldCheck, Database, FolderOpen, Building2, Scale,
} from 'lucide-react';
import ScenarioCard from '../components/workshop/ScenarioCard';
import PipelineWidget from '../components/workshop/PipelineWidget';
import {
  getKnowledgeStats, getSystemProfile, listProjects, type SystemProfile,
} from '../lib/api';

const SCENARIOS = [
  { number: 1, title: 'Dokumentenanalyse', description: 'Auflagen und Nachweispflichten aus Förderbescheiden extrahieren', icon: FileSearch, color: 'bg-blue-600' },
  { number: 2, title: 'Checklisten-KI', description: 'VKO-Prüfpunkte mit KI-Unterstützung bewerten', icon: CheckSquare, color: 'bg-indigo-600' },
  { number: 3, title: 'Halluzination', description: 'Risiken ohne vs. mit RAG-Kontext demonstrieren', icon: AlertTriangle, color: 'bg-amber-600' },
  { number: 4, title: 'Berichtsentwurf', description: 'Prüffeststellungen in Berichtpassagen formulieren', icon: FileText, color: 'bg-emerald-600' },
  { number: 5, title: 'Vorab-Upload', description: 'Eigene Dokumente hochladen und per RAG befragen', icon: Upload, color: 'bg-fuchsia-700' },
  { number: 6, title: 'Begünstigte', description: 'Begünstigtenverzeichnis analysieren und kartieren', icon: MapPin, color: 'bg-rose-600' },
];

export default function HomePage() {
  const [projectCount, setProjectCount] = useState<number | null>(null);
  const [knowledgeStats, setKnowledgeStats] = useState<{ documents: number; chunks: number } | null>(null);
  const [profile, setProfile] = useState<SystemProfile | null>(null);

  useEffect(() => {
    listProjects().then((data) => setProjectCount(data.total)).catch(() => setProjectCount(null));
    getKnowledgeStats().then((data) => setKnowledgeStats({ documents: data.documents, chunks: data.chunks })).catch(() => setKnowledgeStats(null));
    getSystemProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1.35fr_0.95fr]">
        <div className="relative overflow-hidden rounded-[32px] border border-white/80 bg-[linear-gradient(135deg,rgba(7,38,54,0.97),rgba(13,74,88,0.94)_45%,rgba(23,95,73,0.9))] px-8 py-9 text-white shadow-[0_40px_120px_-48px_rgba(8,47,73,0.92)]">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.22),rgba(255,255,255,0)_38%)]" />
          <div className="absolute -right-16 top-10 h-40 w-40 rounded-full border border-white/10 bg-white/5" />
          <div className="absolute bottom-[-5rem] left-[-3rem] h-48 w-48 rounded-full border border-white/10 bg-black/10" />
          <div className="relative">
            <div className="mb-5 flex flex-wrap gap-2 text-xs uppercase tracking-[0.22em] text-cyan-100/70">
              <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">Lokales LLM</span>
              <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">EFRE Prüfworkflow</span>
              <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">Live-Demo</span>
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-white lg:text-5xl">
              KI-Unterstützung für Auditoren, ohne die fachliche Kontrolle abzugeben.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-cyan-50/84">
              Der Workshop kombiniert echte Prüfschritte, nachvollziehbare Quellenarbeit und ein Präsentationslayout, das in einer Behördendemonstration belastbar wirkt.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/scenario/1" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-medium text-slate-900 transition hover:bg-cyan-50">
                Workshop starten
                <ArrowRight size={16} />
              </Link>
              <Link to="/projects" className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/15">
                Checklisten öffnen
              </Link>
            </div>
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <div className="rounded-3xl border border-white/10 bg-black/10 p-4">
                <div className="text-[11px] uppercase tracking-[0.2em] text-cyan-100/60">Projekte</div>
                <div className="mt-2 text-3xl font-semibold">{projectCount ?? '—'}</div>
              </div>
              <div className="rounded-3xl border border-white/10 bg-black/10 p-4">
                <div className="text-[11px] uppercase tracking-[0.2em] text-cyan-100/60">Wissensquellen</div>
                <div className="mt-2 text-3xl font-semibold">{knowledgeStats?.documents ?? '—'}</div>
              </div>
              <div className="rounded-3xl border border-white/10 bg-black/10 p-4">
                <div className="text-[11px] uppercase tracking-[0.2em] text-cyan-100/60">Textabschnitte</div>
                <div className="mt-2 text-3xl font-semibold">{knowledgeStats?.chunks ?? '—'}</div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <div className="rounded-[28px] border border-slate-200/80 bg-white/85 p-6 shadow-[0_22px_70px_-44px_rgba(15,23,42,0.65)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
            <div className="mb-4 flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-300">
                <ShieldCheck size={20} />
              </span>
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Workshop-Profil</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">Für Live-Demos mit Prüforientierung gebaut.</p>
              </div>
            </div>
            <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
              <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">
                <span>Datenschutzmodus</span>
                <span className="font-medium text-slate-900 dark:text-white">
                  {profile?.privacy_mode ? 'Lokal erzwingbar' : 'Externe Dienste aktiv'}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">
                <span>Checklistenworkflow</span>
                <span className="font-medium text-slate-900 dark:text-white">Accept / Edit / Reject</span>
              </div>
              <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">
                <span>Datenräume</span>
                <span className="font-medium text-slate-900 dark:text-white">RAG + SQL + Karte</span>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-4">
            <Link to="/knowledge" className="rounded-[28px] border border-slate-200/80 bg-white/85 p-5 transition hover:-translate-y-0.5 hover:shadow-[0_24px_80px_-48px_rgba(6,95,70,0.55)] dark:border-slate-800 dark:bg-slate-900/75">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-50 text-cyan-700 dark:bg-cyan-950/60 dark:text-cyan-300">
                <Database size={20} />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Wissensbasis</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Quellen, Suche und Dokumentenintegration für fundierte Antworten.</p>
            </Link>
            <Link to="/projects" className="rounded-[28px] border border-slate-200/80 bg-white/85 p-5 transition hover:-translate-y-0.5 hover:shadow-[0_24px_80px_-48px_rgba(8,47,73,0.55)] dark:border-slate-800 dark:bg-slate-900/75">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                <FolderOpen size={20} />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Projektarbeitsraum</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Der echte Checklistenfluss für die Workshop-Demo, inklusive Seed und Bulk-Bewertung.</p>
            </Link>
            <Link to="/company-search" className="rounded-[28px] border border-slate-200/80 bg-white/85 p-5 transition hover:-translate-y-0.5 hover:shadow-[0_24px_80px_-48px_rgba(8,145,178,0.5)] dark:border-slate-800 dark:bg-slate-900/75">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300">
                <Building2 size={20} />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Unternehmenssuche</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Notebook-artige Recherche über Unternehmen, Vorhaben und Aktenzeichen auf Basis der geladenen Verzeichnisse.</p>
            </Link>
            <Link to="/ai-act" className="rounded-[28px] border border-slate-200/80 bg-white/85 p-5 transition hover:-translate-y-0.5 hover:shadow-[0_24px_80px_-48px_rgba(109,40,217,0.45)] dark:border-slate-800 dark:bg-slate-900/75">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-violet-700 dark:bg-violet-950/60 dark:text-violet-300">
                <Scale size={20} />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">AI Act</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Eigenes Prüfer-Merkblatt zu roten Linien, Risiken und menschlicher Letztentscheidung.</p>
            </Link>
          </div>
        </div>
      </section>

      <div>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Sechs Workshop-Szenarien</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Klare narrative Abfolge vom Einzelbescheid bis zur raumbezogenen Förderanalyse.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {SCENARIOS.map((s) => (
            <ScenarioCard key={s.number} {...s} />
          ))}
        </div>
      </div>

      <PipelineWidget />
    </div>
  );
}
