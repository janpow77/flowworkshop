/**
 * frontend · lib/stateAidApi.ts
 *
 * Typen + Helper fuer das EU-Beihilfe-Transparenzregister.
 * Backend-Prefix: /api/state-aid (siehe docs/eu-state-aid-register-plan.md §10)
 *
 * Alle Endpunkte werden per fetch() angesprochen. Lese-Endpoints sind
 * oeffentlich, Harvest/Delete erwarten den Workshop-Auth-Token (Admin).
 */
import { getWorkshopAuthHeaders } from './api';

const BASE = '/api/state-aid';

// ── URL-Sicherheit ───────────────────────────────────────────────────────────
// Defense-in-Depth: TAM/national-Quellen liefern URLs, die wir als `href`
// rendern. Bei einem boesartigen Datensatz (z.B. `case_url=javascript:alert(1)`)
// wuerde ein Klick JavaScript ausfuehren. Daher: nur http(s) durchlassen,
// alles andere (javascript:, data:, vbscript:, file:, ...) wird auf undefined
// gemappt — der Link verschwindet einfach.

/**
 * Liefert die URL zurueck, wenn sie ein sicheres http/https-Schema hat,
 * sonst `undefined`. Erwartet absolute URLs (TAM/Competition Cases sind
 * immer absolut). Relative Pfade ("/...") werden unveraendert durchgereicht.
 */
export function safeExternalUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  const trimmed = String(url).trim();
  if (!trimmed) return undefined;
  // Relative Pfade (eigener Origin) sind erlaubt.
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) return trimmed;
  // Absolut: nur http(s) zulassen — alles andere ist unsicher (javascript:, data:, ...).
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.toString();
    }
  } catch {
    // ungueltige URL → unsicher, drop.
  }
  return undefined;
}

// ── Award/Hits ───────────────────────────────────────────────────────────────

export interface StateAidAward {
  id: string;
  source_key: string;
  source_record_id: string;
  source_url: string | null;
  beneficiary_name: string;
  beneficiary_identifier: string | null;
  beneficiary_type: string | null;
  country_code: string | null;
  country_name: string | null;
  nuts_code: string | null;
  nuts_label: string | null;
  nuts_level: number | null;
  nace_label: string | null;
  aid_amount: number | null;
  aid_currency: string | null;
  aid_amount_eur: number | null;
  aid_instrument: string | null;
  aid_objective: string | null;
  aid_measure_title: string | null;
  granting_authority: string | null;
  entrusted_entity: string | null;
  granting_date: string | null;
  publication_date: string | null;
  measure_reference: string | null;
  sa_reference: string | null;
  case_url: string | null;
  decision_url: string | null;
}

export type StateAidConfidence = 'exact' | 'high' | 'medium' | 'low';

/**
 * Pipeline-Stage des Treffers in der 4-Stufen-Hybrid-Suche.
 *  - `fuzzy`         — Trigram-Index + rapidfuzz Multi-Algo (Default)
 *  - `semantic`      — bge-m3 Embedding (1024-dim Cosine-Aehnlichkeit)
 *  - `llm-confirmed` — Qwen3-14B hat den Querbezug bestaetigt
 *  - `llm-rejected`  — Qwen3-14B hat den Querbezug verworfen (filtered_by_llm)
 *
 * Optional. Backend-Responses ohne dieses Feld bleiben gueltig — Badge wird
 * dann einfach nicht gerendert (Backward-Compat).
 */
export type StateAidMatchStage = 'fuzzy' | 'semantic' | 'llm-confirmed' | 'llm-rejected';

export interface StateAidSearchHit extends StateAidAward {
  award_id: string;
  score: number;
  confidence: StateAidConfidence;
  matched_field: string;
  /** Optional: Pipeline-Stage des Treffers. */
  match_stage?: StateAidMatchStage;
  /** Optional: vom LLM verworfen (Filter-Flag fuer den Audit-Report). */
  filtered_by_llm?: boolean;
}

export interface StateAidSearchResponse {
  query: string;
  normalized: string;
  total_hits: number;
  threshold: number;
  hits: StateAidSearchHit[];
  filters_applied: Record<string, string>;
}

// ── Status / Sources ─────────────────────────────────────────────────────────

export interface StateAidCountrySummary {
  country_code: string;
  count: number;
  total_eur: number | null;
}

export interface StateAidStatus {
  total_awards: number;
  total_runs: number;
  sources_enabled: number;
  last_harvest_at: string | null;
  by_country: StateAidCountrySummary[];
  coverage_note: string;
  /** Self-Check (validator) — nur gefuellt, wenn mindestens 1 Lauf existiert. */
  last_validation_at: string | null;
  last_validation_status: ValidationStatus | null;
  last_validation_findings_count: number | null;
}

// ── Validator (Self-Check) ───────────────────────────────────────────────────

export type ValidationStatus = 'ok' | 'warnings' | 'failed';
export type ValidationSeverity = 'info' | 'warning' | 'error';

export interface ValidationFinding {
  severity: ValidationSeverity;
  code: string;
  message: string;
  detail: Record<string, unknown> | null;
}

export interface ValidationReport {
  id?: number;
  started_at: string | null;
  finished_at: string | null;
  module: string;
  status: ValidationStatus;
  duration_ms: number;
  checks_total: number;
  checks_passed: number;
  checks_warned: number;
  checks_failed: number;
  findings: ValidationFinding[];
}

export interface ValidationLastResponse {
  module: string;
  report: ValidationReport | null;
}

export type StateAidSourceType = 'tam' | 'national' | 'cases' | 'manual';
export type StateAidQuality = 'green' | 'yellow' | 'red' | null;

export interface StateAidSource {
  source_key: string;
  display_name: string;
  source_type: StateAidSourceType;
  country_code: string | null;
  base_url: string | null;
  last_successful_harvest_at: string | null;
  last_record_date: string | null;
  record_count: number;
  coverage_note: string | null;
  quality: StateAidQuality;
  enabled: boolean;
}

export interface StateAidSourcesResponse {
  sources: StateAidSource[];
}

// ── Karten-Daten ─────────────────────────────────────────────────────────────

export interface StateAidMapPoint {
  nuts_code: string;
  nuts_label: string;
  nuts_level: number | null;
  country_code: string | null;
  lat: number;
  lon: number;
  count: number;
  total_eur: number | null;
}

export interface StateAidMapResponse {
  points: StateAidMapPoint[];
  total_records: number;
  unmappable: number;
  by_level: Record<string, number>;
  filters: {
    country_code: string | null;
    since: string | null;
    until: string | null;
    aggregate_level?: number | null;
  };
}

// ── Auswertung ───────────────────────────────────────────────────────────────

export interface StateAidStatsBucket {
  label: string;
  count: number;
  total_eur: number | null;
}

export interface StateAidStatsByYear {
  year: string;
  count: number;
  total_eur: number | null;
}

export interface StateAidStatsResponse {
  top_beneficiaries?: StateAidStatsBucket[];
  top_authorities?: StateAidStatsBucket[];
  top_objectives?: StateAidStatsBucket[];
  top_instruments?: StateAidStatsBucket[];
  by_year?: StateAidStatsByYear[];
  by_country?: StateAidCountrySummary[];
}

// ── Dossier ──────────────────────────────────────────────────────────────────

export interface StateAidDossierResponse {
  query: string;
  state_aid: {
    count: number;
    total_eur: number | null;
    hits: StateAidAward[];
  };
  sanctions: {
    count: number;
    hits: Array<Record<string, unknown>>;
  };
  beneficiaries: {
    count: number;
    hits: Array<Record<string, unknown>>;
  };
  summary: {
    register_count: number;
    total_eur: number | null;
    has_sanctions_hit: boolean;
  };
}

// ── Suchparameter ────────────────────────────────────────────────────────────

export interface StateAidSearchParams {
  q?: string;
  country_code?: string;
  nuts_code?: string;
  since?: string;
  until?: string;
  min_amount?: number;
  max_amount?: number;
  aid_instrument?: string;
  aid_objective?: string;
  granting_authority?: string;
  sa_reference?: string;
  source_key?: string;
  limit?: number;
  min_score?: number;
}

export interface StateAidMapParams {
  country_code?: string;
  since?: string;
  until?: string;
  /** Aggregations-Level: 0=Land, 1=NUTS-1 (Bundesland), 2=NUTS-2 (Bezirk), 3=NUTS-3 (Kreis). */
  level?: number;
}

export type HarvestMode = 'smart' | 'full-refresh' | 'force';

export interface HarvestResult {
  run_id: string;
  status: string;
  records_seen: number;
  records_inserted: number;
  records_updated: number;
  records_failed: number;
  records_skipped: number;
  pages_fetched: number;
  error: string | null;
}

export interface StateAidHarvestRequest {
  country: string;
  regions?: string[];
  since?: string | null;
  until?: string | null;
  limit?: number;
  source_key?: string;
  mode?: HarvestMode;
  /** @deprecated use `mode` instead — kept for backward-compat. */
  force?: boolean;
}

// ── HTTP-Hilfen ──────────────────────────────────────────────────────────────

function buildQuery(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (typeof value === 'string' && value === '') continue;
    sp.set(key, String(value));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { ...getWorkshopAuthHeaders() },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`${res.status}: ${body || res.statusText}`);
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
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ── API-Funktionen ───────────────────────────────────────────────────────────

export function getStatus(): Promise<StateAidStatus> {
  return getJson<StateAidStatus>('/status');
}

export function getSources(): Promise<StateAidSourcesResponse> {
  return getJson<StateAidSourcesResponse>('/sources');
}

export function search(params: StateAidSearchParams): Promise<StateAidSearchResponse> {
  return getJson<StateAidSearchResponse>(`/search${buildQuery(params as Record<string, unknown>)}`);
}

export function getAward(id: string): Promise<StateAidAward> {
  return getJson<StateAidAward>(`/award/${encodeURIComponent(id)}`);
}

export function getMap(params: StateAidMapParams): Promise<StateAidMapResponse> {
  return getJson<StateAidMapResponse>(`/map${buildQuery(params as Record<string, unknown>)}`);
}

export function getStats(params: StateAidMapParams = {}): Promise<StateAidStatsResponse> {
  return getJson<StateAidStatsResponse>(`/stats${buildQuery(params as Record<string, unknown>)}`);
}

export function getDossier(q: string): Promise<StateAidDossierResponse> {
  return getJson<StateAidDossierResponse>(`/company-dossier${buildQuery({ q })}`);
}

export function triggerHarvest(req: StateAidHarvestRequest): Promise<HarvestResult> {
  // Body-Defaults: regions=[] (Backend erwartet die Liste), mode='smart'.
  const body = {
    regions: [],
    mode: 'smart' as HarvestMode,
    ...req,
  };
  return postJson<HarvestResult>('/harvest', body);
}

export async function deleteSource(sourceKey: string): Promise<{ status: string; deleted: number }> {
  const res = await fetch(`${BASE}/awards/${encodeURIComponent(sourceKey)}`, {
    method: 'DELETE',
    headers: { ...getWorkshopAuthHeaders() },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export function exportUrl(format: 'csv' | 'pdf', params: StateAidSearchParams): string {
  const all: Record<string, unknown> = { ...(params as Record<string, unknown>), format };
  return `${BASE}/export${buildQuery(all)}`;
}

// ── Validator-API ────────────────────────────────────────────────────────────

export function getValidationLast(): Promise<ValidationLastResponse> {
  return getJson<ValidationLastResponse>('/validation/last');
}

// ── Cross-Register-Pruefbericht ──────────────────────────────────────────────

/**
 * Aggregierter Pruefbericht aus drei oeffentlichen Registern.
 *
 * Das Schema folgt dem Backend-Endpunkt `/api/state-aid/audit-report` und ist
 * bewusst neutral: keine Risiko-Scores, keine Severity-Einstufung, keine
 * Ampeln. Der Pruefer beurteilt selbst.
 */
export interface AuditReportStateAidByYear {
  year: number;
  count: number;
  sum_eur: number;
}

export interface AuditReportStateAidByAuthority {
  authority: string;
  count: number;
  sum_eur: number;
}

export interface AuditReportStateAidByNuts {
  nuts_code: string;
  nuts_label: string;
  count: number;
  sum_eur: number;
}

export interface AuditReportStateAidByInstrument {
  instrument: string;
  count: number;
}

export interface AuditReportStateAid {
  total_count: number;
  total_amount_eur: number;
  awards: Array<Record<string, unknown>>;
  by_year: AuditReportStateAidByYear[];
  by_authority: AuditReportStateAidByAuthority[];
  by_nuts: AuditReportStateAidByNuts[];
  by_instrument: AuditReportStateAidByInstrument[];
  sa_references: string[];
  case_urls: string[];
}

export interface AuditReportBeneficiariesByBundesland {
  bundesland: string;
  count: number;
}

export interface AuditReportBeneficiariesByFonds {
  fonds: string;
  count: number;
}

export interface AuditReportBeneficiaries {
  total_count: number;
  total_amount_eur: number;
  matches: Array<Record<string, unknown>>;
  by_bundesland: AuditReportBeneficiariesByBundesland[];
  by_fonds: AuditReportBeneficiariesByFonds[];
}

export interface AuditReportSanctionHit {
  name: string;
  score: number;
  confidence: string;
  aliases: string[];
  countries: string;
  sanctions: string;
}

export interface AuditReportSanctions {
  total_hits: number;
  hits: AuditReportSanctionHit[];
  listing_sources: string[];
}

export interface AuditReportCrossReference {
  type: string;
  description: string;
  evidence: Record<string, unknown>;
  /**
   * Optional: Querbezug wurde vom LLM-Verifier verworfen. UI kann ihn
   * ausgrauen oder ausblenden (Toggle „auch LLM-abgelehnte zeigen").
   */
  filtered_by_llm?: boolean;
}

/**
 * Einzel-Verdict aus dem LLM-Re-Ranker (Stufe 4 der Hybrid-Pipeline). Pro
 * unsicherem Querbezug (Score 75–89) liefert das Backend eine strukturierte
 * JSON-Bewertung mit Begruendung.
 */
export interface AuditReportLlmVerdict {
  /** Index in `cross_references` (Backend-Reihenfolge). */
  cross_ref_index: number;
  match: 'yes' | 'no' | 'unknown';
  /** 0..100 — Confidence-Wert des LLM. */
  confidence: number;
  /** Kurzbegruendung in deutscher Sprache (max ~2 Saetze). */
  reason: string;
  /** Ausfuehrungszeit fuer diesen einzelnen Verdict. */
  elapsed_ms: number;
}

/**
 * LLM-Verifikation aller unsicheren Querbezuege (optional, nur wenn der
 * Pruefer den Toggle `include_llm_verification=true` aktiviert hat).
 *
 * Achtung: Dauer typischerweise 2–4 Minuten fuer 20 Eintraege.
 */
export interface AuditReportLlmVerification {
  /** Anzahl Querbezuege, die dem LLM uebergeben wurden. */
  total_input: number;
  verdicts: AuditReportLlmVerdict[];
  /** Gesamtdauer der LLM-Schleife in Millisekunden. */
  elapsed_total_ms: number;
  /** Anzahl Eintraege, die durch ein Timeout uebersprungen wurden. */
  skipped_due_to_timeout: number;
  /** Backend-Fehler (Ollama down, Modell nicht geladen, ...) oder null. */
  error: string | null;
}

export interface AuditReportSourceExplanation {
  name: string;
  url: string;
  description: string;
  /** ISO-Datum (YYYY-MM-DD oder ISO-Datetime) oder null wenn unbekannt. */
  last_data_update: string | null;
  record_count: number;
}

// ── Personen-Sanktionscheck (Item 1) ─────────────────────────────────────────

/**
 * Eingegebene Person aus dem Pruefbericht-Formular.
 *
 * `role` ist optional — wenn leer (oder `null`) wird im Formular die
 * Standard-Rolle "Sonstige" beibehalten. Beide Felder sind reine
 * User-Inputs, React rendert sie automatisch escaped.
 */
export interface AuditPersonInput {
  name: string;
  role: string | null;
}

/**
 * Treffer eines Personen-Sanktions-Abgleichs. Backend liefert pro
 * eingegebener Person 0..n Treffer; bei 0 Treffern erscheint die Person
 * trotzdem in der Tabelle, damit der Pruefer sieht, dass abgeglichen wurde.
 */
export interface AuditPersonsCheckHit {
  /** Listen-Eintragsname (kann von der eingegebenen Schreibweise abweichen). */
  name: string;
  /** 0–100 (Backend rundet typischerweise auf 1 Nachkommastelle). */
  score: number;
  confidence: string;
  /** Welche Listen den Treffer geliefert haben (z.B. eu_fsf, un_sc, ofac). */
  lists: string[];
  aliases: string[];
  /** Optionale Identifikatoren — Geburtsdatum/Land sind fuer den Pruefer. */
  birth_date: string | null;
  countries: string;
  programs: string;
}

export interface AuditPersonsCheckEntry {
  /** Wie der Pruefer den Namen eingegeben hat (1:1 zur UI-Zeile). */
  input_name: string;
  /** Eingegebene Rolle (Geschaeftsfuehrer, UBO, ...) oder null. */
  input_role: string | null;
  hits: AuditPersonsCheckHit[];
}

export interface AuditReportPersonsCheck {
  /** Anzahl Personen, die der Pruefer eingegeben hat. */
  total_persons: number;
  /** Summe der Treffer ueber alle Personen. */
  total_hits: number;
  /** Pro eingegebener Person ein Eintrag (Reihenfolge wie im Formular). */
  entries: AuditPersonsCheckEntry[];
  /** Listen, gegen die abgeglichen wurde (z.B. eu_fsf, un_sc, ...). */
  listing_sources: string[];
}

// ── Coverage-Anzeige (Item 2) ────────────────────────────────────────────────

/**
 * Coverage-Status pro Modul/Quelle. Wartungs-Indikator, NICHT als Risiko.
 * `status` faerbt die Pill: complete=gruen, partial=gelb, unknown=grau.
 */
export type AuditCoverageStatus = 'complete' | 'partial' | 'unknown';

export interface AuditCoverageEntry {
  /** z.B. "State-Aid", "Beguenstigtenverzeichnis", "Sanktionen". */
  module: string;
  /** Quellen-Schluessel oder Anzeigename, z.B. "TAM (EU)", "Hessen EFRE". */
  source: string;
  /** Lokal vorhandene Datensaetze. */
  local_count: number | null;
  /** Erwartete Datensaetze laut Quelle (kann null sein). */
  expected_count: number | null;
  /** 0..1 (Backend rundet auf 3 Nachkommastellen). null wenn unbekannt. */
  coverage_ratio: number | null;
  /** ISO-Datum/-Datetime oder null. */
  last_harvest_at: string | null;
  status: AuditCoverageStatus;
  /** Optionaler Hinweistext fuer den Pruefer. */
  note: string | null;
}

export interface AuditReportCoverage {
  entries: AuditCoverageEntry[];
}

/**
 * Konzernverbund-Erweiterung (Mai 2026, Item 2).
 *
 * GLEIF + Wikidata liefern Mutter/Tochter-Beziehungen zur Anker-Firma.
 * Die Tochterfirmen werden separat in State-Aid und Beneficiaries gesucht;
 * die Treffer sind mit `via_corporate_child` markiert (welche Konzernfirma
 * den Treffer ausgeloest hat). Die UI muss das transparent anzeigen.
 */
export interface CorporateEntity {
  name: string;
  legal_form: string | null;
  country: string | null;
  lei: string | null;
  wikidata_id: string | null;
  address: string | null;
  source: 'gleif' | 'wikidata' | 'manual';
  source_url: string;
  /** ISO-Datum (oder null) — Datenstand bei der Quelle. */
  data_freshness: string | null;
  /** ISO-Datum — wann WIR den Lookup gemacht haben. */
  fetched_at: string | null;
}

export interface AuditReportCorporateGroup {
  primary_entity: CorporateEntity | null;
  ultimate_parent: CorporateEntity | null;
  direct_parent: CorporateEntity | null;
  children_count: number;
  children_top: CorporateEntity[];
  additional_state_aid_count: number;
  additional_state_aid_amount_eur: number;
  additional_state_aid_awards: Array<Record<string, unknown>>;
  additional_beneficiaries_count: number;
  additional_beneficiaries_amount_eur: number;
  additional_beneficiaries: Array<Record<string, unknown>>;
  coverage_note: string;
  sources_used: string[];
  fetched_at: string | null;
  cache_meta: Record<string, unknown>;
}

export interface AuditReportData {
  query: string;
  issued_at: string;
  auftraggeber: string | null;
  pruefer_name: string | null;
  state_aid: AuditReportStateAid;
  beneficiaries: AuditReportBeneficiaries;
  sanctions: AuditReportSanctions;
  cross_references: AuditReportCrossReference[];
  data_freshness: Record<string, string>;
  sources_explanation: AuditReportSourceExplanation[];
  /** Mehrzeiliger Hinweistext aus dem Backend (Absaetze via \n\n). */
  disclaimer: string;
  /**
   * Konzernverbund-Erweiterung. `null` wenn der Toggle nicht aktiv war.
   */
  corporate_group: AuditReportCorporateGroup | null;
  /**
   * Personen-Sanktionscheck (Item 1). Nur gefuellt, wenn der Pruefer beim
   * Bericht-Aufruf mindestens eine Person eingegeben hat.
   */
  persons_check?: AuditReportPersonsCheck | null;
  /**
   * Coverage-Status (Item 5) — Wartungs-Indikator, kein Risiko-Marker.
   * Wenn nicht vorhanden, blendet die UI die Sektion einfach aus.
   */
  coverage?: AuditReportCoverage | null;
  /**
   * LLM-Verifikation (Stufe 4 der Hybrid-Pipeline). Nur gefuellt, wenn der
   * Pruefer `include_llm_verification=true` aktiviert hat.
   */
  llm_verification?: AuditReportLlmVerification | null;
}

export interface AuditReportParams {
  q: string;
  country_code?: string;
  auftraggeber?: string;
  /**
   * Konzernverbund-Lookup (GLEIF + Wikidata) aktivieren.
   * Default: false. Lookup-Dauer: 5-15 Sekunden.
   */
  include_corporate_group?: boolean;
  /**
   * LLM-Verifikation der unsicheren Querbezuege (Score 75–89) aktivieren.
   * Default: false. Lookup-Dauer: typischerweise ~3 Minuten fuer 20 Eintraege.
   * Aktiviert Stufe 4 der Hybrid-Pipeline (Qwen3-14B Re-Ranker).
   */
  include_llm_verification?: boolean;
  /**
   * Personen-Liste fuer den Sanktions-Abgleich (Item 1). Wird im
   * GET-Request als wiederholter `persons`-Parameter mit `Name|Rolle`
   * URL-encoded uebertragen — leer wenn keine Personen eingegeben.
   */
  persons?: AuditPersonInput[];
}

export interface AuditReportPdfParams extends AuditReportParams {
  pruefer_name?: string;
}

/**
 * Standalone-Lookup des Konzernverbunds — fuer Frontend-Vorschau ohne
 * den vollen Audit-Report.
 */
export interface CorporateGroupResponse {
  query: string;
  group: {
    query: string;
    primary_entity: CorporateEntity | null;
    ultimate_parent: CorporateEntity | null;
    direct_parent: CorporateEntity | null;
    children: CorporateEntity[];
    children_count: number;
    sources_used: string[];
    coverage_note: string;
    fetched_at: string | null;
  };
  cache_meta: {
    cache: 'hit' | 'miss' | 'stale-refreshed' | 'disabled';
    fetched_at?: string | null;
    expires_at?: string | null;
    source?: string;
  };
  coverage_note: string;
  sources_used: string[];
}

export interface CorporateGroupParams {
  q: string;
  include_children?: boolean;
  max_children?: number;
  timeout_seconds?: number;
}

/**
 * Serialisiert eine Personen-Liste fuer URL-Parameter im Format
 * `Name|Rolle`. Leere Eintraege werden gefiltert; Rolle ist optional und
 * faellt auf einen leeren String zurueck (Backend setzt dann die
 * Standard-Rolle "Sonstige" intern).
 */
function serializePersonsForQuery(persons: AuditPersonInput[]): string[] {
  return persons
    .map((p) => {
      const name = (p.name || '').trim();
      if (!name) return null;
      const role = (p.role || '').trim();
      return `${name}|${role}`;
    })
    .filter((v): v is string => v !== null);
}

/**
 * Baut den Query-String fuer `/audit-report` inkl. dem Personen-Array.
 * Personen werden als wiederholte `persons`-Parameter uebertragen, alle
 * anderen Felder via `buildQuery`. Leere Personen-Listen erzeugen keinen
 * Parameter.
 */
function buildAuditReportQuery(params: AuditReportParams): string {
  const { persons, ...rest } = params;
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(rest)) {
    if (value === undefined || value === null) continue;
    if (typeof value === 'string' && value === '') continue;
    sp.set(key, String(value));
  }
  if (Array.isArray(persons) && persons.length > 0) {
    for (const entry of serializePersonsForQuery(persons)) {
      sp.append('persons', entry);
    }
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

/**
 * Liest den Cross-Register-Pruefbericht als JSON ein. Suchparameter werden
 * URL-kodiert; leere Strings werden vom HTTP-Helper verworfen.
 *
 * Wenn `include_corporate_group: true`, kann der Lookup 5-15 Sekunden
 * dauern (zwei externe APIs werden befragt). Die UI sollte einen
 * Lade-Indikator anzeigen.
 *
 * Personen werden als wiederholter `persons`-Parameter im Format
 * `Name|Rolle` uebertragen — der Backend-Endpoint nimmt sie als Liste
 * entgegen und liefert die Treffer in `persons_check` zurueck.
 */
export function getAuditReport(params: AuditReportParams): Promise<AuditReportData> {
  return getJson<AuditReportData>(`/audit-report${buildAuditReportQuery(params)}`);
}

/**
 * Triggert den serverseitigen PDF-Renderer und liefert den Blob zurueck. Der
 * Aufrufer entscheidet selbst, wie der Download ausgeliefert wird (z.B. via
 * `URL.createObjectURL` und `<a download>`-Klick) — das ist beim Rendering
 * der Seite einfacher zu handhaben als ein Window-Redirect.
 *
 * Bei `include_corporate_group: true` enthaelt das PDF eine zusaetzliche
 * Sektion "Konzernverbund-Erweiterung" mit GLEIF/Wikidata-Quellen.
 *
 * Personen werden im Body als `persons: [{name, role}, ...]`-Array
 * uebertragen. Rolle darf null sein.
 */
export async function downloadAuditReportPdf(params: AuditReportPdfParams): Promise<Blob> {
  // Body wird wie bisher als JSON gesendet; Persons-Array wird unveraendert
  // weitergereicht (Backend akzeptiert null fuer role).
  const body: Record<string, unknown> = { ...params };
  // Wenn `persons` leer ist, lieber komplett weglassen (Backend ist
  // tolerant, aber wir vermeiden unnoetige Felder im Log).
  if (!Array.isArray(params.persons) || params.persons.length === 0) {
    delete body.persons;
  } else {
    body.persons = params.persons
      .map((p) => ({
        name: (p.name || '').trim(),
        role: p.role && p.role.trim() ? p.role.trim() : null,
      }))
      .filter((p) => p.name.length > 0);
  }
  const res = await fetch(`${BASE}/audit-report/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status}: ${text || res.statusText}`);
  }
  return res.blob();
}

/**
 * Standalone-Konzernverbund-Lookup ohne Audit-Report-Aufbau.
 *
 * Quellen: GLEIF Public API + Wikidata SPARQL (beide kostenlos und
 * oeffentlich). Das Backend cached die Antworten 7 Tage lang — die UI sieht
 * im `cache_meta.cache`-Feld, ob der aktuelle Treffer aus dem Cache kommt.
 *
 * Wichtig fuer die UI: der `coverage_note` muss prominent angezeigt werden,
 * inkl. dem Datenstand pro Eintrag (Spalte `data_freshness`).
 */
export function getCorporateGroup(
  params: CorporateGroupParams,
): Promise<CorporateGroupResponse> {
  return getJson<CorporateGroupResponse>(
    `/corporate-group${buildQuery(params as unknown as Record<string, unknown>)}`,
  );
}

export function runValidation(): Promise<{ run_id: number | null; report: ValidationReport }> {
  return postJson<{ run_id: number | null; report: ValidationReport }>('/validation/run', {});
}

// ── Audit-Trail (Item 4) ─────────────────────────────────────────────────────

/**
 * Ein einzelner Eintrag im Pruefbericht-Verlauf. Backend liefert die
 * Metadaten — keine PDFs.
 */
export interface AuditReportLogItem {
  id: number;
  created_at: string | null;
  query: string;
  auftraggeber: string | null;
  pruefer_name: string | null;
  pruefer_user_id: string | null;
  state_aid_hits: number;
  beneficiaries_hits: number;
  sanctions_hits: number;
  cross_references: number;
  pdf_size_bytes: number;
  pdf_sha256: string | null;
}

export interface AuditReportLogResponse {
  count: number;
  items: AuditReportLogItem[];
  /**
   * Cursor fuer die naechste Seite (kleinste id der aktuellen Seite). Null,
   * wenn keine weiteren Seiten existieren oder das Backend kein Cursor-
   * Feld liefert (Fallback: clientseitig auf min(id) ableiten).
   */
  before_id?: number | null;
}

export interface AuditReportLogParams {
  /** Maximal 500 (Backend-Cap). Default 50. */
  limit?: number;
  /** Cursor: nur Eintraege mit `id < before_id` zurueckliefern. */
  before_id?: number;
  /** Filter: nur Eintraege eines bestimmten Pruefers. */
  user_id?: string;
  /** Volltext-Filter (Suchbegriff im Query, Auftraggeber oder Pruefer-Namen). */
  q?: string;
  /** Datum-Range (ISO-Date). */
  since?: string;
  until?: string;
}

/**
 * Liest die Pruefbericht-Historie als Admin. Liefert ausschliesslich
 * Metadaten — keine PDFs. Das Backend pruefen die Auth via
 * `require_admin`-Dependency und gibt 403, wenn kein Admin-Token vorliegt.
 */
export function getAuditReportLog(
  params: AuditReportLogParams = {},
): Promise<AuditReportLogResponse> {
  return getJson<AuditReportLogResponse>(
    `/audit-report/log${buildQuery(params as Record<string, unknown>)}`,
  );
}

// ── KI-Suche (SSE) ───────────────────────────────────────────────────────────

export interface AskStateAidRequest {
  question: string;
  country_code?: string;
  locale?: string;
  limit?: number;
}

export interface AskResultsPayload {
  total_hits: number;
  hits: StateAidSearchHit[];
  stats: Record<string, unknown>;
}

export interface AskEventHandlers {
  onFilter?: (filter: Record<string, unknown>) => void;
  onResults?: (payload: AskResultsPayload) => void;
  onSummaryToken?: (text: string) => void;
  onDone?: (info: { elapsed_ms: number }) => void;
  onError?: (message: string) => void;
}

export interface AskController {
  abort: () => void;
}

/**
 * Streamt eine KI-Suche an `/api/state-aid/ask` und ruft pro SSE-Event den
 * passenden Handler auf. Da `EventSource` POST nicht unterstuetzt, parsen wir
 * den ReadableStream selbst — Buffer-Strategie analog zu `streamSSE` in api.ts:
 * Chunks akkumulieren, an Doppelten-Newlines splitten, je Block `event:` /
 * `data:` Zeilen separat lesen.
 */
export function askStateAid(req: AskStateAidRequest, handlers: AskEventHandlers): AskController {
  const controller = new AbortController();

  fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
    body: JSON.stringify(req),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        handlers.onError?.(text || `HTTP ${res.status}`);
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) {
        handlers.onError?.('Streaming nicht verfuegbar.');
        return;
      }
      const decoder = new TextDecoder();
      let buffer = '';
      // SSE-Frames sind durch Leerzeile (\n\n) getrennt. Pro Frame koennen
      // mehrere `data:`-Zeilen gehoeren (laut SSE-Spec werden sie zusammengefuegt).
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // Frames extrahieren: alles vor dem letzten `\n\n` ist abgeschlossen.
        let sepIndex = buffer.indexOf('\n\n');
        while (sepIndex !== -1) {
          const frame = buffer.slice(0, sepIndex);
          buffer = buffer.slice(sepIndex + 2);
          parseSseFrame(frame, handlers);
          sepIndex = buffer.indexOf('\n\n');
        }
      }
      // Rest-Buffer (falls Server ohne abschliessendes \n\n schliesst).
      if (buffer.trim()) {
        parseSseFrame(buffer, handlers);
      }
    })
    .catch((err: unknown) => {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      handlers.onError?.(err instanceof Error ? err.message : String(err));
    });

  return { abort: () => controller.abort() };
}

/** Liest ein SSE-Frame ("event: X\ndata: ...") und ruft den passenden Handler. */
function parseSseFrame(frame: string, handlers: AskEventHandlers): void {
  const lines = frame.split('\n');
  let event = 'message';
  const dataLines: string[] = [];
  for (const raw of lines) {
    const line = raw.replace(/\r$/, '');
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''));
    }
  }
  if (dataLines.length === 0) return;
  const dataStr = dataLines.join('\n');
  let data: unknown;
  try {
    data = JSON.parse(dataStr);
  } catch {
    return;
  }
  const obj = (data && typeof data === 'object') ? data as Record<string, unknown> : {};
  switch (event) {
    case 'filter': {
      const f = obj.filter;
      if (f && typeof f === 'object') {
        handlers.onFilter?.(f as Record<string, unknown>);
      }
      break;
    }
    case 'results': {
      const total = typeof obj.total_hits === 'number' ? obj.total_hits : 0;
      const hits = Array.isArray(obj.hits) ? obj.hits as StateAidSearchHit[] : [];
      const stats = (obj.stats && typeof obj.stats === 'object')
        ? obj.stats as Record<string, unknown>
        : {};
      handlers.onResults?.({ total_hits: total, hits, stats });
      break;
    }
    case 'summary_token': {
      const t = typeof obj.text === 'string' ? obj.text : '';
      if (t) handlers.onSummaryToken?.(t);
      break;
    }
    case 'done': {
      const ms = typeof obj.elapsed_ms === 'number' ? obj.elapsed_ms : 0;
      handlers.onDone?.({ elapsed_ms: ms });
      break;
    }
    case 'error': {
      const msg = typeof obj.message === 'string' ? obj.message : 'Unbekannter Fehler.';
      handlers.onError?.(msg);
      break;
    }
    default:
      break;
  }
}
