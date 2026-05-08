/**
 * frontend - lib/sanctionsApi.ts
 *
 * Multi-Source-Sanctions-API.
 *
 * Backend liefert ueber /api/sanctions/sources eine Liste aller bekannten
 * Sanktionslisten (EU FSF, UN SC, OFAC SDN, UK OFSI, CH SECO). Pro Source
 * gibt es einen "loaded"-Flag, der angibt, ob die Liste lokal indiziert ist
 * und damit ueber /api/sanctions/search durchsucht werden kann.
 *
 * /api/sanctions/refresh stoesst einen erneuten Datenimport aus OpenSanctions
 * an (Admin-only). Der Body { source_key } steuert, ob nur eine einzelne
 * Liste oder alle aktivierten Listen aktualisiert werden.
 */
import { getWorkshopAuthHeaders } from './api';

const BASE = '/api';

// ── Typen ────────────────────────────────────────────────────────────────────

/**
 * Schluessel der bekannten Sanktionslisten. Wird vom Backend als Quelle
 * der Wahrheit geliefert; das Frontend nutzt den String-Typ um Tippfehler
 * im Source-Auswahl-UI auszuschliessen.
 */
export type SanctionsSourceKey =
  | 'eu_fsf'
  | 'un_sc'
  | 'us_ofac_sdn'
  | 'gb_hmt_sanctions'
  | 'ch_seco'
  | string;

export interface SanctionsSourceInfo {
  source_key: SanctionsSourceKey;
  key?: SanctionsSourceKey;
  display_name: string;
  issuer: string;
  loaded: boolean;
  total_entries: number;
  persons: number;
  organizations: number;
  loaded_at: string | null;
  source_url: string;
  download_url: string;
  license: string;
}

export interface SanctionsHit {
  id: string;
  schema_type: string;
  name: string;
  matched_on: string;
  matched_field: string;
  score: number;
  confidence: 'exact' | 'high' | 'medium' | 'low';
  aliases: string[];
  birth_date: string;
  countries: string;
  addresses: string;
  identifiers: string;
  sanctions: string;
  program_ids: string;
  first_seen: string;
  last_seen: string;
  source_key: SanctionsSourceKey;
  source_display_name: string;
}

export interface SanctionsSearchResponse {
  query: string;
  normalized: string;
  total_hits: number;
  threshold: number;
  method: string;
  hits: SanctionsHit[];
}

export interface SanctionsPerSourceStats {
  source_key: SanctionsSourceKey;
  loaded: boolean;
  total: number;
  persons: number;
  organizations: number;
  loaded_at: string | null;
}

export interface SanctionsStatsResponse {
  total_entries: number;
  per_source: SanctionsPerSourceStats[];
  // Legacy-Felder (nur EU FSF) — bleiben erhalten, damit bestehende UI-Stellen,
  // die source_mtime/loaded_at lesen, weiter funktionieren.
  persons?: number;
  organizations?: number;
  other?: number;
  loaded_at?: string | null;
  source_mtime?: string | null;
}

export interface SanctionsRefreshResult {
  status: string;
  source_key?: SanctionsSourceKey | null;
  refreshed: number;
  message?: string;
}

export interface SanctionsSearchParams {
  q: string;
  limit?: number;
  min_score?: number;
  sources?: SanctionsSourceKey[];
  schema_filter?: 'Person' | 'Organization' | '';
}

// ── HTTP-Helper ──────────────────────────────────────────────────────────────

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── API-Funktionen ───────────────────────────────────────────────────────────

/**
 * Holt die Liste aller bekannten Sanctions-Sources (loaded + nicht-loaded).
 * Wirft bei 404 oder Netzwerkfehler — die Page faellt dann auf statische
 * _SANCTIONS_LISTS zurueck.
 */
export async function getSanctionsSources(): Promise<SanctionsSourceInfo[]> {
  const data = await getJson<{ sources: SanctionsSourceInfo[] } | SanctionsSourceInfo[]>(
    '/sanctions/sources',
  );
  const sources = Array.isArray(data) ? data : data.sources ?? [];
  return sources.map((source) => ({
    ...source,
    source_key: source.source_key ?? source.key ?? 'unknown',
  }));
}

/**
 * Suchanfrage gegen alle (oder explizit ausgewaehlte) Sources.
 */
export async function searchSanctions(
  params: SanctionsSearchParams,
): Promise<SanctionsSearchResponse> {
  const query = new URLSearchParams();
  query.set('q', params.q);
  if (typeof params.limit === 'number') query.set('limit', String(params.limit));
  if (typeof params.min_score === 'number') query.set('min_score', String(params.min_score));
  if (params.schema_filter) query.set('schema_filter', params.schema_filter);
  if (params.sources && params.sources.length > 0) {
    query.set('sources', params.sources.join(','));
  }
  return getJson<SanctionsSearchResponse>(`/sanctions/search?${query.toString()}`);
}

/**
 * Aktualisiert eine einzelne Source (source_key gesetzt) oder alle (null).
 * Admin-only — das Backend prueft den Workshop-Token.
 */
export async function refreshSanctionsSource(
  sourceKey: SanctionsSourceKey | null,
): Promise<SanctionsRefreshResult> {
  return postJson<SanctionsRefreshResult>('/sanctions/refresh', {
    source_key: sourceKey ?? null,
  });
}

/**
 * Per-Source-Breakdown.
 */
export async function getSanctionsStats(): Promise<SanctionsStatsResponse> {
  return getJson<SanctionsStatsResponse>('/sanctions/stats');
}

// ── UI-Helper ────────────────────────────────────────────────────────────────

/**
 * Kurz-Label fuer Source-Pills und Treffer-Badges.
 * Unbekannte Keys werden uppercase ausgegeben, damit neue Sources, die
 * spaeter im Backend registriert werden, nicht zu undefined fuehren.
 */
export function sourceShortLabel(key: SanctionsSourceKey | string | null | undefined): string {
  if (!key) return '—';
  switch (key) {
    case 'eu_fsf':
      return 'EU FSF';
    case 'un_sc':
      return 'UN SC';
    case 'us_ofac_sdn':
      return 'OFAC SDN';
    case 'gb_hmt_sanctions':
      return 'UK OFSI';
    case 'ch_seco':
      return 'CH SECO';
    default:
      return String(key).toUpperCase().replace(/_/g, ' ');
  }
}

/**
 * Tailwind-sichere Akzent-Klassen pro Source. Statisch deklariert (kein
 * dynamischer Klassenname), damit Tailwind nicht aussortiert.
 */
export const SOURCE_BADGE_STYLES: Record<string, string> = {
  eu_fsf: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
  un_sc: 'bg-sky-50 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300',
  us_ofac_sdn: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  gb_hmt_sanctions: 'bg-violet-50 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300',
  ch_seco: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
};

export const SOURCE_BADGE_FALLBACK = 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';

/**
 * Relative Zeitangabe ("vor 2 Stunden") fuer "Letzte Aktualisierung".
 * Faellt auf locale-Datum zurueck, wenn die Zeitspanne > 30 Tage ist.
 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return 'noch nie';
  let date: Date;
  try {
    date = new Date(iso);
    if (isNaN(date.getTime())) return iso;
  } catch {
    return iso;
  }
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffSec = Math.round(diffMs / 1000);
  const absSec = Math.abs(diffSec);
  if (absSec < 60) return 'gerade eben';
  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60) {
    return diffMin === 1 ? 'vor 1 Minute' : `vor ${Math.abs(diffMin)} Minuten`;
  }
  const diffH = Math.round(diffMin / 60);
  if (Math.abs(diffH) < 24) {
    return diffH === 1 ? 'vor 1 Stunde' : `vor ${Math.abs(diffH)} Stunden`;
  }
  const diffD = Math.round(diffH / 24);
  if (Math.abs(diffD) <= 30) {
    return diffD === 1 ? 'vor 1 Tag' : `vor ${Math.abs(diffD)} Tagen`;
  }
  return date.toLocaleDateString('de-DE', { year: 'numeric', month: '2-digit', day: '2-digit' });
}
