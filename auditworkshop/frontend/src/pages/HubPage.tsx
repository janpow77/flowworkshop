import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  MessagesSquare, FolderArchive, CalendarDays, MapPin, ShieldAlert, BookOpen,
  FlaskConical, Users, Bell, ListChecks, Sparkles, ArrowRight,
} from 'lucide-react';

interface HubStats {
  forum_threads?: number;
  forum_posts_unread?: number;
  documents?: number;
  documents_latest?: string;
  beneficiaries_total?: number;
  sanctions_updated?: string;
  participants?: number;
  notifications_unread?: number;
}

const TILES = [
  {
    key: 'forum',
    title: 'Forum',
    description: 'Diskussionen, Fragen, Antworten',
    icon: MessagesSquare,
    href: '/forum',
    gradient: 'from-cyan-500/15 to-cyan-500/5 border-cyan-200 text-cyan-700 dark:border-cyan-900 dark:text-cyan-200',
    indicator: (s: HubStats) => s.forum_posts_unread ? `${s.forum_posts_unread} ungelesen` : `${s.forum_threads ?? 0} Stränge`,
  },
  {
    key: 'docs',
    title: 'Dokumente',
    description: 'Geteilte Dateien, Templates',
    icon: FolderArchive,
    href: '/docs',
    gradient: 'from-amber-500/15 to-amber-500/5 border-amber-200 text-amber-700 dark:border-amber-900 dark:text-amber-200',
    indicator: (s: HubStats) => s.documents != null ? `${s.documents} Dateien` : 'Material',
  },
  {
    key: 'archiv',
    title: 'Tagesordnung (Archiv)',
    description: 'Was lief wann, mit Material',
    icon: CalendarDays,
    href: '/agenda',
    gradient: 'from-slate-500/15 to-slate-500/5 border-slate-200 text-slate-700 dark:border-slate-700 dark:text-slate-200',
    indicator: () => '2 Tage · 16 Punkte',
  },
  {
    key: 'beneficiaries',
    title: 'Begünstigtenverzeichnisse',
    description: 'EFRE/ESF/JTF/ISF/AMIF',
    icon: MapPin,
    href: '/scenario/6',
    gradient: 'from-emerald-500/15 to-emerald-500/5 border-emerald-200 text-emerald-700 dark:border-emerald-900 dark:text-emerald-200',
    indicator: (s: HubStats) => s.beneficiaries_total != null ? `${(s.beneficiaries_total/1000).toFixed(0)}k Vorhaben` : 'Karte',
  },
  {
    key: 'sanctions',
    title: 'Sanktionslisten',
    description: 'EU FSF, OFAC, OFSI, SECO …',
    icon: ShieldAlert,
    href: '/sanktionslisten',
    gradient: 'from-rose-500/15 to-rose-500/5 border-rose-200 text-rose-700 dark:border-rose-900 dark:text-rose-200',
    indicator: (s: HubStats) => s.sanctions_updated ? `Stand ${s.sanctions_updated}` : 'EU FSF',
  },
  {
    key: 'checklisten',
    title: 'Checklisten',
    description: 'Musterchecklisten verwalten, gemeinsam bearbeiten und diskutieren',
    icon: ListChecks,
    href: '/checklisten',
    gradient: 'from-teal-500/15 to-teal-500/5 border-teal-200 text-teal-700 dark:border-teal-900 dark:text-teal-200',
    indicator: () => 'Vorlagen',
  },
  {
    key: 'wissen',
    title: 'Wissensbasis',
    description: 'Verordnungen + RAG',
    icon: BookOpen,
    href: '/knowledge',
    gradient: 'from-indigo-500/15 to-indigo-500/5 border-indigo-200 text-indigo-700 dark:border-indigo-900 dark:text-indigo-200',
    indicator: () => 'RAG-Suche',
  },
  {
    key: 'szenarien',
    title: 'Demo-Szenarien',
    description: 'Lernumgebung 1–7',
    icon: FlaskConical,
    href: '/scenario/1',
    gradient: 'from-violet-500/15 to-violet-500/5 border-violet-200 text-violet-700 dark:border-violet-900 dark:text-violet-200',
    indicator: () => '7 Szenarien',
  },
  {
    key: 'teilnehmer',
    title: 'Teilnehmer',
    description: 'Mitglieder & Konten',
    icon: Users,
    href: '/account',
    gradient: 'from-sky-500/15 to-sky-500/5 border-sky-200 text-sky-700 dark:border-sky-900 dark:text-sky-200',
    indicator: (s: HubStats) => s.participants != null ? `${s.participants} aktiv` : 'Mitglieder',
  },
  {
    key: 'updates',
    title: 'Mitteilungen',
    description: 'Neuigkeiten zur Plattform',
    icon: Bell,
    href: '/notifications',
    gradient: 'from-fuchsia-500/15 to-fuchsia-500/5 border-fuchsia-200 text-fuchsia-700 dark:border-fuchsia-900 dark:text-fuchsia-200',
    indicator: (s: HubStats) => s.notifications_unread ? `${s.notifications_unread} neu` : '—',
  },
];

export default function HubPage() {
  const [stats, setStats] = useState<HubStats>({});

  useEffect(() => {
    const load = async () => {
      const out: HubStats = {};
      try {
        const f = await fetch('/api/event/forum/summary');
        if (f.ok) {
          const j = await f.json();
          out.forum_threads = (j.items || []).length;
        }
      } catch { /* ignore */ }
      try {
        // Schlanke Kennzahl statt des vollen ~27-MB-Map-Payloads — die
        // HomePage braucht nur die Gesamtzahl.
        const b = await fetch('/api/beneficiaries/summary?country_code=DE');
        if (b.ok) {
          const j = await b.json();
          out.beneficiaries_total = j.count;
        }
      } catch { /* ignore */ }
      try {
        const s = await fetch('/api/sanctions/stats');
        if (s.ok) {
          const j = await s.json();
          if (j.source_mtime) {
            out.sanctions_updated = new Date(j.source_mtime).toLocaleDateString('de-DE');
          }
        }
      } catch { /* ignore */ }
      setStats(out);
    };
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="rounded-[28px] border border-white/70 bg-[linear-gradient(135deg,rgba(8,47,73,0.98),rgba(14,116,144,0.94)_45%,rgba(14,165,233,0.85))] px-7 py-8 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-100/70">Plattform · Archiv-Modus</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Prüferworkshop 2026</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-white/85">
          Forum, Dokumente, Auswertungen und das Programm-Archiv der Veranstaltung.
          Wählen Sie einen Bereich.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map((tile) => {
          const Icon = tile.icon;
          return (
            <Link
              key={tile.key}
              to={tile.href}
              className={`group block rounded-3xl border bg-gradient-to-br p-6 transition hover:shadow-lg ${tile.gradient}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/70 shadow-sm dark:bg-slate-900/40">
                  <Icon size={22} />
                </div>
                <div className="text-[11px] font-semibold uppercase tracking-wider opacity-70">
                  {tile.indicator(stats)}
                </div>
              </div>
              <h3 className="mt-5 text-lg font-semibold text-slate-900 dark:text-white">
                {tile.title}
              </h3>
              <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300 line-clamp-2">
                {tile.description}
              </p>
            </Link>
          );
        })}
      </div>

      {/* Breite Recherche-Kachel — eigene Zeile unter dem Kachelgrid */}
      <Link
        to="/recherche"
        className="group relative block overflow-hidden rounded-[28px] border border-emerald-200/70 bg-[linear-gradient(120deg,rgba(6,78,59,0.97),rgba(13,116,144,0.92)_55%,rgba(16,185,129,0.85))] px-7 py-7 text-white shadow-[0_30px_100px_-56px_rgba(6,95,70,0.9)] transition hover:shadow-[0_36px_120px_-52px_rgba(6,95,70,0.95)] dark:border-emerald-900/50"
      >
        <div className="absolute -right-12 -top-10 h-44 w-44 rounded-full bg-white/10 blur-2xl" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white/15 shadow-inner backdrop-blur">
              <Sparkles size={26} />
            </span>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-100/80">
                KI-gestützt · belegbasiert
              </div>
              <h3 className="mt-1 text-2xl font-semibold tracking-tight">Wissens-Recherche</h3>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-white/85">
                Verordnungen und Dokumente semantisch durchsuchen &mdash; oder aus den
                Fundstellen einen belegbasierten Text erzeugen lassen. Die Generierung
                nutzt das stärkere Reasoning-Modell über den lokalen ai-router.
              </p>
            </div>
          </div>
          <span className="inline-flex shrink-0 items-center gap-2 rounded-full bg-white/15 px-5 py-3 text-sm font-medium backdrop-blur transition group-hover:bg-white/25">
            Recherche öffnen
            <ArrowRight size={16} className="transition group-hover:translate-x-0.5" />
          </span>
        </div>
      </Link>
    </div>
  );
}
