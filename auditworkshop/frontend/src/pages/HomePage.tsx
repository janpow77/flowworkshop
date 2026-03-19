import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, ShieldCheck, Database,
  MessageCircle, QrCode, Users, Upload, CalendarDays, UserPlus,
} from 'lucide-react';
import PipelineWidget from '../components/workshop/PipelineWidget';
import {
  getKnowledgeStats, getSystemProfile, listProjects, type SystemProfile,
} from '../lib/api';

function isModerator(): boolean {
  return localStorage.getItem('workshop_role') === 'moderator';
}

export default function HomePage() {
  const [projectCount, setProjectCount] = useState<number | null>(null);
  const [knowledgeStats, setKnowledgeStats] = useState<{ documents: number; chunks: number } | null>(null);
  const [profile, setProfile] = useState<SystemProfile | null>(null);
  const [workshopMode, setWorkshopMode] = useState(false);

  const showScenarios = workshopMode || isModerator();

  useEffect(() => {
    listProjects().then((data) => setProjectCount(data.total)).catch(() => setProjectCount(null));
    getKnowledgeStats().then((data) => setKnowledgeStats({ documents: data.documents, chunks: data.chunks })).catch(() => setKnowledgeStats(null));
    getSystemProfile().then(setProfile).catch(() => setProfile(null));
    fetch('/api/event/meta').then(r => r.json()).then(d => setWorkshopMode(d.workshop_mode ?? false)).catch(() => {});
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
              <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">EFRE-Pr&uuml;fworkflow</span>
              <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1">DSGVO-konform</span>
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-white lg:text-5xl">
              Pr&uuml;ferworkshop der Pr&uuml;fbeh&ouml;rden 2026
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-cyan-50/84">
              {!showScenarios
                ? 'Willkommen zur Vorbereitungsphase. Melden Sie sich an, reichen Sie Themenvorschl\u00e4ge ein und laden Sie Dokumente f\u00fcr den Workshop hoch. Alle Daten bleiben lokal auf dem Veranstaltungsger\u00e4t.'
                : 'Sechs Live-Szenarien mit lokalem LLM, RAG-Wissensbasis und vollwertigem Checklistensystem. Alle Daten bleiben auf dem Ger\u00e4t \u2014 kein Cloud-Dienst, keine Daten\u00fcbertragung.'}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              {!showScenarios ? (
                <>
                  <Link to="/register" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-medium text-slate-900 transition hover:bg-cyan-50">
                    <UserPlus size={16} />
                    Jetzt anmelden
                  </Link>
                  <Link to="/agenda" className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/15">
                    <CalendarDays size={16} />
                    Tagesordnung ansehen
                  </Link>
                </>
              ) : (
                <>
                  <Link to="/scenario/1" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-medium text-slate-900 transition hover:bg-cyan-50">
                    Workshop starten
                    <ArrowRight size={16} />
                  </Link>
                  <Link to="/projects" className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-sm font-medium text-white transition hover:bg-white/15">
                    Checklisten &ouml;ffnen
                  </Link>
                </>
              )}
            </div>
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <div className="rounded-3xl border border-white/10 bg-black/10 p-4">
                <div className="text-[11px] uppercase tracking-[0.2em] text-cyan-100/60">Anmeldungen</div>
                <div className="mt-2 text-3xl font-semibold">{projectCount ?? '\u2014'}</div>
              </div>
              <div className="rounded-3xl border border-white/10 bg-black/10 p-4">
                <div className="text-[11px] uppercase tracking-[0.2em] text-cyan-100/60">Wissensquellen</div>
                <div className="mt-2 text-3xl font-semibold">{knowledgeStats?.documents ?? '\u2014'}</div>
              </div>
              <div className="rounded-3xl border border-white/10 bg-black/10 p-4">
                <div className="text-[11px] uppercase tracking-[0.2em] text-cyan-100/60">Textabschnitte</div>
                <div className="mt-2 text-3xl font-semibold">{knowledgeStats?.chunks ?? '\u2014'}</div>
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
                <p className="text-sm text-slate-500 dark:text-slate-400">F&uuml;r Pr&uuml;fer, von Pr&uuml;fern.</p>
              </div>
            </div>
            <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
              <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">
                <span>Datenschutz</span>
                <span className="font-medium text-slate-900 dark:text-white">
                  {profile?.privacy_mode ? 'Nur lokaler Betrieb' : 'Externe Dienste aktiv'}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">
                <span>Checklistenworkflow</span>
                <span className="font-medium text-slate-900 dark:text-white">Akzeptieren / Bearbeiten / Ablehnen</span>
              </div>
              <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">
                <span>Datenr&auml;ume</span>
                <span className="font-medium text-slate-900 dark:text-white">RAG + SQL + Karte</span>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Link to="/knowledge" className="rounded-[28px] border border-slate-200/80 bg-white/85 p-5 transition hover:-translate-y-0.5 hover:shadow-[0_24px_80px_-48px_rgba(6,95,70,0.55)] dark:border-slate-800 dark:bg-slate-900/75">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-50 text-cyan-700 dark:bg-cyan-950/60 dark:text-cyan-300">
                <Database size={20} />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Wissensbasis</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Dokumente hochladen, durchsuchen und per KI befragen.</p>
            </Link>
            <Link to="/register" className="rounded-[28px] border border-slate-200/80 bg-white/85 p-5 transition hover:-translate-y-0.5 hover:shadow-[0_24px_80px_-48px_rgba(8,47,73,0.55)] dark:border-slate-800 dark:bg-slate-900/75">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                <UserPlus size={20} />
              </div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Anmeldung</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Registrieren Sie sich und reichen Sie Ihren Themenvorschlag ein.</p>
            </Link>
          </div>
        </div>
      </section>

      {/* Teilnehmer-Hinweis: Mitmachen */}
      <section className="rounded-[28px] border border-cyan-200/80 bg-gradient-to-br from-cyan-50/80 via-white/90 to-emerald-50/60 p-6 shadow-[0_20px_70px_-46px_rgba(6,182,212,0.4)] dark:border-cyan-800/50 dark:from-cyan-950/30 dark:via-slate-900/80 dark:to-emerald-950/20">
        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-100 text-cyan-700 dark:bg-cyan-950/60 dark:text-cyan-300">
            <Users size={20} />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">So k&ouml;nnen Sie mitmachen</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Drei Wege, den Workshop aktiv mitzugestalten</p>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-cyan-200/60 bg-white/80 p-4 dark:border-cyan-800/40 dark:bg-slate-900/60">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-cyan-700 dark:text-cyan-300">
              <Upload size={16} />
              Dokumente hochladen
            </div>
            <p className="text-xs leading-5 text-slate-600 dark:text-slate-400">
              In der <strong>Wissensbasis</strong> k&ouml;nnen Sie eigene PDFs, XLSX oder DOCX hochladen.
              Die KI beantwortet Fragen ausschlie&szlig;lich auf Basis Ihrer Unterlagen &mdash;
              nichts verl&auml;sst das Ger&auml;t.
            </p>
          </div>
          <div className="rounded-2xl border border-amber-200/60 bg-white/80 p-4 dark:border-amber-800/40 dark:bg-slate-900/60">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-300">
              <MessageCircle size={16} />
              Themen vorschlagen &amp; voten
            </div>
            <p className="text-xs leading-5 text-slate-600 dark:text-slate-400">
              &Uuml;ber die <strong>Anmeldung</strong> k&ouml;nnen Sie Themenvorschl&auml;ge einreichen.
              Auf der <strong>Tagesordnung</strong> sehen Sie eingereichte Themen und k&ouml;nnen
              per Klick daf&uuml;r abstimmen &mdash; die beliebtesten werden im Workshop behandelt.
            </p>
          </div>
          <div className="rounded-2xl border border-emerald-200/60 bg-white/80 p-4 dark:border-emerald-800/40 dark:bg-slate-900/60">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-emerald-700 dark:text-emerald-300">
              <QrCode size={16} />
              QR-Code f&uuml;r Schnellzugang
            </div>
            <p className="text-xs leading-5 text-slate-600 dark:text-slate-400">
              Scannen Sie den QR-Code in der Einladung oder am Veranstaltungsort, um direkt
              auf die Anmeldeseite zu gelangen. Dort k&ouml;nnen Sie sich registrieren, Themen
              einreichen und Dokumente bereitstellen.
            </p>
          </div>
        </div>
      </section>

      {showScenarios && <PipelineWidget />}
    </div>
  );
}
