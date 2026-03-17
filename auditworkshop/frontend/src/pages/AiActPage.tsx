import { Link } from 'react-router-dom';
import {
  ArrowLeft, Ban, Bot, CalendarDays, FileWarning, Scale, ShieldAlert, ShieldCheck, UserRoundCheck,
} from 'lucide-react';

const TIMELINE = [
  { date: '1. August 2024', label: 'AI Act in Kraft getreten' },
  { date: '2. Februar 2025', label: 'Verbote und AI-Literacy-Pflichten anwendbar' },
  { date: '2. August 2025', label: 'Regeln für GPAI-Modelle und Governance anwendbar' },
  { date: '2. August 2026', label: 'AI Act grundsätzlich anwendbar' },
  { date: '2. August 2027', label: 'Sonderfrist für bestimmte High-Risk-Systeme in regulierten Produkten' },
];

const PROHIBITIONS = [
  'Menschen gezielt manipulieren oder Schwächen ausnutzen, sodass wesentliche Verhaltensentscheidungen verzerrt werden.',
  'Social Scoring von Personen für öffentliche oder private Zwecke.',
  'Individuelle predictive policing-Entscheidungen, die ausschließlich auf Profiling beruhen.',
  'Ungezieltes Scraping von Internet- oder CCTV-Bildern zum Aufbau von Gesichtsdatenbanken.',
];

const AUDITOR_GUARDRAILS = [
  'Keine negative Entscheidung allein aus einem Modelltreffer ableiten. Der Mensch bleibt die entscheidende Instanz.',
  'Treffer aus Sanktionslisten, State-Aid- oder Cohesio-Abgleichen immer als Hinweis behandeln und fachlich nachprüfen.',
  'Datenherkunft, Aktualität, Modellgrenzen und Suchlogik dokumentieren, damit Feststellungen revisionsfest bleiben.',
  'Generative KI-Ausgaben nie ungeprüft in Berichte oder Prüfbewertungen übernehmen.',
];

const NOT_SIMPLE = [
  'Keine automatisierte Freigabe oder Sperre eines Unternehmens ohne prüferische Nachsicht.',
  'Kein verdeckter KI-Einsatz bei sensiblen Bewertungen ohne interne Transparenz und Rollenklärung.',
  'Kein unkritisches Zusammenführen heterogener Registertreffer ohne Dubletten- und Qualitätsprüfung.',
  'Keine Vermischung von bloßen Indizien mit belastbaren Feststellungen im Prüfbericht.',
];

export default function AiActPage() {
  return (
    <div className="space-y-6">
      <Link to="/company-search" className="inline-flex items-center gap-2 text-sm text-slate-500 transition hover:text-cyan-700 dark:text-slate-400 dark:hover:text-cyan-300">
        <ArrowLeft size={16} />
        Zur Unternehmenssuche
      </Link>

      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(36,23,61,0.98),rgba(87,41,117,0.95)_48%,rgba(175,78,47,0.88))] px-7 py-8 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.96)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.18),rgba(255,255,255,0)_32%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-white/70">AI Act für Prüfer</div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight lg:text-4xl">Rote Linien und Vorsichtspunkte für den KI-Einsatz</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-white/85 lg:text-base">
              Diese Seite ist ein kompaktes Prüfer-Merkblatt für den Workshop. Sie fasst die wesentlichen Verbote,
              Übergangsfristen und praktischen Leitplanken zusammen. Sie ist als Orientierung gedacht, nicht als Rechtsgutachten.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/company-search" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-medium text-slate-900 transition hover:bg-slate-100">
                <Scale size={16} />
                Zur Suche mit Registerimport
              </Link>
            </div>
          </div>

          <div className="rounded-[28px] border border-white/15 bg-black/10 p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-white">
                <ShieldCheck size={20} />
              </div>
              <div>
                <div className="text-sm font-semibold">Kurzfassung</div>
                <div className="mt-1 text-sm text-white/70">Was man als Prüfer nicht einfach tun sollte</div>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {NOT_SIMPLE.map((item) => (
                <div key={item} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm leading-6 text-white/85">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <div className="rounded-[28px] border border-red-200 bg-red-50/90 p-5 shadow-[0_20px_70px_-48px_rgba(127,29,29,0.45)] dark:border-red-900/70 dark:bg-red-950/40">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-red-100 text-red-700 dark:bg-red-950/70 dark:text-red-300">
              <Ban size={18} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Verboten</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">Unacceptable-risk-Praktiken nach AI-Act-Systematik.</p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {PROHIBITIONS.map((item) => (
              <div key={item} className="rounded-2xl bg-white/80 px-4 py-3 text-sm leading-6 text-slate-700 dark:bg-slate-950/45 dark:text-slate-200">
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[28px] border border-amber-200 bg-amber-50/90 p-5 shadow-[0_20px_70px_-48px_rgba(146,64,14,0.35)] dark:border-amber-900/70 dark:bg-amber-950/35">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300">
              <ShieldAlert size={18} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Nicht blind übernehmen</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">Für Prüfbehörden besonders kritisch im Alltag.</p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {AUDITOR_GUARDRAILS.map((item) => (
              <div key={item} className="rounded-2xl bg-white/80 px-4 py-3 text-sm leading-6 text-slate-700 dark:bg-slate-950/45 dark:text-slate-200">
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[28px] border border-cyan-200 bg-cyan-50/90 p-5 shadow-[0_20px_70px_-48px_rgba(8,145,178,0.35)] dark:border-cyan-900/70 dark:bg-cyan-950/35">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-100 text-cyan-700 dark:bg-cyan-950/70 dark:text-cyan-300">
              <UserRoundCheck size={18} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Prüferische Leitplanke</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">Menschliche Letztentscheidung und Nachvollziehbarkeit.</p>
            </div>
          </div>
          <div className="mt-4 rounded-[24px] bg-white/85 p-4 dark:bg-slate-950/45">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-white">
              <Bot size={15} className="text-cyan-700 dark:text-cyan-300" />
              KI ist Assistenz, nicht Entscheidungsträger
            </div>
            <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
              Für den Workshop bedeutet das: Treffer, Scores und KI-Formulierungen dürfen den Prüfer entlasten,
              aber weder die Beweiswürdigung noch die behördliche Verantwortung ersetzen.
            </p>
          </div>
          <div className="mt-3 rounded-[24px] bg-white/85 p-4 dark:bg-slate-950/45">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-white">
              <FileWarning size={15} className="text-cyan-700 dark:text-cyan-300" />
              Dokumentation zählt
            </div>
            <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
              Halten Sie Datenquelle, Suchstand, Modellgrenzen, manuelle Plausibilisierung und die finale menschliche
              Entscheidung schriftlich fest.
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-[30px] border border-slate-200/80 bg-white/88 p-6 shadow-[0_22px_76px_-52px_rgba(15,23,42,0.58)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
            <CalendarDays size={18} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Zeitstrahl</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Stand für den Workshop: März 2026.</p>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {TIMELINE.map((item) => (
            <div key={item.date} className="rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-950/45">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{item.date}</div>
              <div className="mt-2 text-sm font-medium leading-6 text-slate-900 dark:text-white">{item.label}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
