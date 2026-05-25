/**
 * flowworkshop · components/landing/toolTilesData.ts
 *
 * Reine Daten/Konstanten der Landing-Kacheln (kein JSX) — getrennt von den
 * Render-Komponenten in ToolTiles.tsx, damit React-Fast-Refresh sauber bleibt.
 */
import type { LucideIcon } from 'lucide-react';
import { ListChecks, Sparkles, GraduationCap, ShieldAlert, MapPinned } from 'lucide-react';

// Statische Akzent-Klassenkarten — bewusst ausgeschrieben, damit Tailwind die
// Klassen beim Build erfasst (dynamische `bg-${x}` werden nicht erkannt).
export const ACCENT = {
  amber:   { hover: 'hover:bg-amber-500/10',   bullet: 'text-amber-400',   foot: 'text-amber-300/80',   iconBg: 'bg-amber-500/20',   iconText: 'text-amber-300' },
  indigo:  { hover: 'hover:bg-indigo-500/10',  bullet: 'text-indigo-400',  foot: 'text-indigo-300/80',  iconBg: 'bg-indigo-500/20',  iconText: 'text-indigo-300' },
  emerald: { hover: 'hover:bg-emerald-500/10', bullet: 'text-emerald-400', foot: 'text-emerald-300/80', iconBg: 'bg-emerald-500/20', iconText: 'text-emerald-300' },
  rose:    { hover: 'hover:bg-rose-500/10',    bullet: 'text-rose-400',    foot: 'text-rose-300/80',    iconBg: 'bg-rose-500/20',    iconText: 'text-rose-300' },
  blue:    { hover: 'hover:bg-blue-500/10',    bullet: 'text-blue-400',    foot: 'text-blue-300/80',    iconBg: 'bg-blue-500/20',    iconText: 'text-blue-300' },
  teal:    { hover: 'hover:bg-teal-500/10',    bullet: 'text-teal-400',    foot: 'text-teal-300/80',    iconBg: 'bg-teal-500/20',    iconText: 'text-teal-300' },
  cyan:    { hover: 'hover:bg-cyan-500/10',    bullet: 'text-cyan-400',    foot: 'text-cyan-300/80',    iconBg: 'bg-cyan-500/20',    iconText: 'text-cyan-300' },
} as const;

export interface ToolTile {
  key: string;
  title: string;
  route: string;
  accent: keyof typeof ACCENT;
  description: string;
  bullets: string[];
  footnote: string;
  emoji?: string;
  icon?: LucideIcon;
  /** Volle Breite (zwei Spalten) statt halber Kachel. */
  wide?: boolean;
  /** Feature verlangt eine Session (ausgeloggt nicht nutzbar). */
  gated?: boolean;
}

/** Die sechs Werkzeugkacheln. Reihenfolge = 2×2 halbe Kacheln, dann zwei breite. */
export const TOOL_TILES: ToolTile[] = [
  {
    key: 'beihilfen',
    title: 'Beihilfe-Register',
    route: '/beihilfen',
    accent: 'amber',
    emoji: '💰',
    description: 'EU-Transparency-Aid-Module (TAM) lokal indiziert — alle veröffentlichungspflichtigen Beihilfen aus DE und AT seit 2014.',
    bullets: [
      '349.135 Beihilfen (DE 253.731 + AT 95.404)',
      'NUTS-Karte mit Aggregation auf Bundesland/Kreis',
      'Hybrid-Suche (Trigram + Fuzzy-Match + LLM-Verifikation)',
      'KI-Suche mit Klartext-Fragen',
    ],
    footnote: 'Veröffentlicht nach Art. 9 Abs. 1 lit. c) VO (EU) 651/2014',
  },
  {
    key: 'cross-register',
    title: 'Cross-Register-Auswertung',
    route: '/audit-report',
    accent: 'indigo',
    emoji: '📄',
    description: 'Eine Eingabe (Firma + Personen) → ein PDF aus drei Registern. Faktisch, ohne Risiko-Bewertung.',
    bullets: [
      'State-Aid + Begünstigte + Sanktionen aggregiert',
      'Personen-Sanctions-Check (Geschäftsführer/UBO)',
      'Konzernverbund via GLEIF',
      'Mehrseitiger PDF-Download',
    ],
    footnote: 'Registerübergreifende Prüfnotiz mit Quellen- und Trefferanhang',
  },
  {
    key: 'beneficiaries',
    title: 'Begünstigtenverzeichnisse',
    route: '/scenario/6',
    accent: 'emerald',
    icon: MapPinned,
    description: 'Konsolidiertes Begünstigtenverzeichnis aus EFRE, ESF+, JTF, ISF und AMIF für Deutschland und Österreich.',
    bullets: [
      'Interaktive Karte mit Geocoding aller Standorte',
      'Volltextsuche, Filter nach Land und Förderhöhe',
      'LLM-Auswertung von Auffälligkeiten',
      'Export als PNG oder PDF',
    ],
    footnote: 'Öffentlich nach Art. 49 VO (EU) 2021/1060',
  },
  {
    key: 'sanctions',
    title: 'Sanktionslisten',
    route: '/sanktionslisten',
    accent: 'rose',
    icon: ShieldAlert,
    description: 'Konsolidierte Personen- und Organisations-Sanktionslisten der EU, USA, UK und Schweiz.',
    bullets: [
      'EU FSF, UN, OFAC, OFSI, SECO',
      'Lokale Fuzzy-Suche (kein Datenabfluss)',
      '39.000+ Einträge inkl. Aliase und Schreibvarianten',
      'Täglich automatisch aktualisiert',
    ],
    footnote: 'Für Begünstigten-Screening nach Art. 73 VO 2021/1060',
  },
  {
    key: 'checklisten',
    title: 'Checklisten-Designer',
    route: '/checklisten',
    accent: 'blue',
    icon: ListChecks,
    wide: true,
    gated: true,
    description: 'Eigene Prüfchecklisten im Team entwerfen, abstimmen und versionieren — für die Verwaltungs- und Vorhabenprüfung nach Artikel 74 und 79 der Verordnung (EU) 2021/1060, mit nachvollziehbar dokumentierten Abweichungen gegenüber den Ausgangsvorlagen.',
    bullets: [
      'Prüflogik als Entscheidungsbaum abbilden und je Prüfschritt fachlich im Team klären',
      'Jede Änderung nachvollziehen und Freigabestände revisionssicher gegenüberstellen',
      'Fertige Checklisten als ausfüllbare Word-, Excel- und PDF-Vorlagen ausgeben',
      'Bei Bedarf mit den Musterchecklisten der Kommission als Ausgangsfassung starten',
    ],
    footnote: 'Eine gemeinsame Werkbank für die Prüfungsmethodik statt verstreuter Insellösungen',
  },
  {
    key: 'recherche',
    title: 'Wissens-Recherche',
    route: '/recherche',
    accent: 'teal',
    icon: Sparkles,
    wide: true,
    gated: true,
    description: 'Verordnungen und eigene Dokumente semantisch durchsuchen — oder aus den Fundstellen einen belegbasierten Text erzeugen lassen (RAG).',
    bullets: [
      'Semantische Suche über pgvector (bge-m3)',
      'Belegbasierte Textgenerierung mit Quellenangabe',
      'Lokales Reasoning-Modell über den ai-router',
      'Kein Datenabfluss — alles auf eigener Hardware',
    ],
    footnote: 'KI-gestützte, belegbasierte Recherche in der Wissensbasis',
  },
];

/** Die Prüferworkshop-Kachel (nur eingeloggt, fuehrt zur Workshop-Plattform). */
export const WORKSHOP_TILE: ToolTile = {
  key: 'workshop',
  title: 'Prüferworkshop',
  route: '/hub',
  accent: 'cyan',
  icon: GraduationCap,
  wide: true,
  description: 'Forum, Dokumente, Tagesordnungs-Archiv, Demo-Szenarien und Teilnehmer der Veranstaltung.',
  bullets: [
    'Forum & Diskussionen zur Veranstaltung',
    'Geteilte Dokumente und Materialien',
    'Tagesordnungs-Archiv beider Workshop-Tage',
    'Sieben Demo-Szenarien zum Ausprobieren',
  ],
  footnote: 'Die Workshop-Plattform — Programm, Austausch und Lernumgebung',
};
