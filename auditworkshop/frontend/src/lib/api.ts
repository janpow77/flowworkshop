/**
 * flowworkshop · lib/api.ts
 * Zentraler API-Client und Typen.
 */

const BASE = '/api';

export function getWorkshopAuthToken(): string | null {
  return localStorage.getItem('workshop_token');
}

export function getWorkshopAuthHeaders(): HeadersInit {
  const token = getWorkshopAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

let authExpiredHandled = false;
function handleAuthExpired(): void {
  if (authExpiredHandled) return;
  authExpiredHandled = true;
  localStorage.removeItem('workshop_token');
  localStorage.removeItem('workshop_role');
  // Auf den Login-Screen zurueckfuehren (App.tsx zeigt LoginPage, wenn kein Token vorhanden ist).
  window.location.assign('/');
}

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const { headers: customHeaders, ...rest } = opts ?? {};
  const res = await fetch(`${BASE}${path}`, {
    ...rest,
    headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders(), ...customHeaders },
  });
  if (res.status === 401 && getWorkshopAuthToken()) {
    handleAuthExpired();
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function requestForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { ...getWorkshopAuthHeaders() },
    body: form,
  });
  if (res.status === 401 && getWorkshopAuthToken()) {
    handleAuthExpired();
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

// ── Typen ────────────────────────────────────────────────────────────────────

export type Foerderphase = '2014-2020' | '2021-2027';
export type AnswerType = 'boolean' | 'boolean_jn' | 'date' | 'amount' | 'enum' | 'text';
export type RemarkAiStatus = 'draft' | 'accepted' | 'edited' | 'rejected';

export interface Project {
  id: string;
  aktenzeichen: string;
  geschaeftsjahr: string;
  program: string | null;
  foerderphase: Foerderphase | null;
  zuwendungsempfaenger: string | null;
  projekttitel: string | null;
  foerderkennzeichen: string | null;
  bewilligungszeitraum: string | null;
  gesamtkosten: string | null;
  foerdersumme: string | null;
  created_at: string;
  updated_at: string | null;
  checklist_count: number;
}

export interface Checklist {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  template_id: string | null;
  question_count: number;
  ai_assessed_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface Question {
  id: string;
  checklist_id: string;
  question_key: string;
  question_text: string | null;
  answer_type: AnswerType;
  category: string | null;
  sort_order: number;
  answer_value: string | null;
  remark_manual: string | null;
  remark_ai: string | null;
  remark_ai_edited: string | null;
  remark_ai_status: RemarkAiStatus | null;
  evidence_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface Evidence {
  id: string;
  source_name: string | null;
  filename: string | null;
  location: string | null;
  snippet: string | null;
  score: number | null;
  created_at: string | null;
}

export interface QuestionDetail extends Question {
  evidence: Evidence[];
  reject_feedback: string | null;
}

export interface ChecklistDetail extends Checklist {
  questions: Question[];
}

export interface KnowledgeSource {
  source: string;
  filename: string;
  chunks: number;
}

export interface KnowledgeStats {
  documents: number;
  chunks: number;
  sources: KnowledgeSource[];
}

export interface SearchResult {
  text: string;
  source: string;
  filename: string;
  chunk_index: number;
  score: number;
}

export interface DemoTemplate {
  template_id: string;
  name: string;
  description: string;
  question_count: number;
}

export interface GpuInfo {
  index: number;
  name: string;
  utilization: string;
  power: string;
  temperature: string;
  memory_used: string;
  memory_total: string;
}

export interface SystemInfo {
  cpu_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  ollama_workers: number[];
}

export interface SystemProfile {
  model_name: string;
  llm_backend?: string;
  llm_endpoint?: string;
  privacy_mode: boolean;
  allow_remote_geocoding: boolean;
  allow_remote_tiles: boolean;
}

export type CountryCode = 'DE' | 'AT';

export interface BeneficiarySource {
  source: string;
  bundesland: string | null;
  fonds: string | null;
  periode: string | null;
  row_count: number;
  country_code?: CountryCode | null;
  country_name?: string | null;
}

export interface CountryProfile {
  country_code: CountryCode;
  country_name: string;
  region_label: string;
  regions: string[];
}

export interface AustriaPresetSource {
  source_id: string;
  country_code: 'AT';
  country_name: string;
  fonds: string;
  periode: string;
  source_url: string;
  display_name: string;
}

export type BeneficiaryMatchConfidence = 'exact' | 'high' | 'medium' | 'low';

export interface BeneficiaryProjectHit {
  project_name: string;
  aktenzeichen: string;
  location: string;
  category: string;
  kosten: number | null;
  kosten_label: string;
  source: string;
  bundesland: string | null;
  fonds: string | null;
  periode: string | null;
  matched_fields: string[];
  match_score: number;
  match_confidence?: BeneficiaryMatchConfidence;
  country_code?: CountryCode | null;
  country_name?: string | null;
}

export interface BeneficiaryCompanyHit {
  company_name: string;
  total_kosten: number;
  total_kosten_label: string;
  project_count: number;
  match_score: number;
  match_confidence?: BeneficiaryMatchConfidence;
  sources: string[];
  bundeslaender: string[];
  fonds: string[];
  standorte: string[];
  aktenzeichen: string[];
  matched_fields: string[];
  projects: BeneficiaryProjectHit[];
}

export interface BeneficiarySearchResponse {
  query: string;
  scope: 'all' | 'company' | 'project' | 'aktenzeichen' | 'location';
  summary: {
    sources_considered: number;
    records_scanned: number;
    matches: number;
    companies: number;
    total_match_volume: number;
  };
  companies: BeneficiaryCompanyHit[];
  records: Array<BeneficiaryProjectHit & {
    company_name: string;
    description: string;
    kosten: number | null;
    kosten_label: string;
    source: string;
    bundesland: string | null;
    fonds: string | null;
    periode: string | null;
  }>;
}

export type BeneficiaryAnalysisMode =
  | 'top_beneficiaries'
  | 'repeat_beneficiaries'
  | 'state_fund_totals'
  | 'top_locations'
  | 'top_sectors'
  | 'multi_state_beneficiaries'
  | 'region_project_counts'
  | 'kreis_project_counts';

export interface BeneficiaryAnalysisItem {
  rank: number;
  label: string;
  sublabel?: string;
  value: number;
  value_label: string;
  project_count?: number;
  source_count?: number;
  bundesland?: string | null;
  fonds?: string | null;
  bundeslaender?: string[];
  fonds_list?: string[];
  locations?: string[];
  sources?: string[];
  // Bei mode=region_project_counts: Aufschluesselung pro Quelle
  // (Bundesprogramm vs. Landesprogramm).
  sources_breakdown?: Array<{
    source: string;
    fonds: string | null;
    count: number;
    value: number;
    value_label: string;
  }>;
}

export interface BeneficiaryAnalyticsResponse {
  mode: BeneficiaryAnalysisMode;
  title: string;
  metric_label: string;
  summary: {
    sources_considered: number;
    records_scanned: number;
    items: number;
    total_volume: number;
    total_volume_label: string;
  };
  filters: {
    bundesland?: string | null;
    fonds?: string | null;
    source?: string | null;
    min_cost?: number | null;
  };
  items: BeneficiaryAnalysisItem[];
}

export type ReferenceRegistryType = 'sanctions' | 'tam' | 'state_aid' | 'cohesio' | 'other';

export interface ReferenceRegistrySource {
  table_name: string;
  source: string;
  row_count: number;
  dataset_group: string | null;
  registry_type: ReferenceRegistryType | null;
  filename: string | null;
}

export interface ReferenceRegistryHit {
  company_name: string;
  project_name: string;
  description: string;
  aktenzeichen: string;
  location: string;
  country: string;
  status: string;
  source: string;
  registry_type: ReferenceRegistryType | 'other';
  filename: string | null;
  matched_fields: string[];
  match_score: number;
}

export interface ReferenceRegistrySearchResponse {
  query: string;
  summary: {
    sources_considered: number;
    matches: number;
  };
  hits: ReferenceRegistryHit[];
}

// ── Checklisten-Templates (Designer) ──────────────────────────────────────────

export type ChecklistTemplateStatus = 'draft' | 'published' | 'archived';

export interface ChecklistTemplate {
  id: string;
  owner_id: string | null;
  title: string;
  description: string | null;
  source_language: string;
  target_language: string;
  source_document_name: string | null;
  properties_json: unknown | null;
  statistics_json: unknown | null;
  status: string;
  node_count: number;
  my_role: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChecklistTemplateMember {
  id: string;
  template_id: string;
  user_id: string;
  role: string;
  invited_by_id: string | null;
  created_at: string | null;
}

export interface ChecklistTemplateCategory {
  id: string;
  template_id: string;
  name: string;
  sort_order: number;
  created_at: string | null;
}

// ── Knoten-Typen (rekursiver Baum) ────────────────────────────────────────────

export type NodeType = 'HEADING' | 'QUESTION' | 'DECISION' | 'HINT';
export type NodeBranch = 'JA' | 'NEIN';
export type TemplateAnswerType =
  | 'BOOLEAN' | 'BOOLEAN_JN' | 'CURRENCY' | 'DATE' | 'CUSTOM_ENUM' | 'TEXT';
export type MemberRoleName = 'owner' | 'editor' | 'commenter' | 'viewer';

export interface ChecklistNode {
  id: string;
  template_id: string;
  parent_id: string | null;
  node_type: NodeType;
  branch: NodeBranch | null;
  ja_label: string | null;
  nein_label: string | null;
  decision_parent_id: string | null;
  sort_order: number;
  title: string | null;
  public_remark: string | null;
  remark_snippets_json: unknown | null;
  eingabetyp: number | null;
  answer_type: TemplateAnswerType | null;
  answer_set_id: string | null;
  category_id: string | null;
  legal_reference: string | null;
  relevant_documents_json: unknown | null;
  is_header_field: boolean;
  source_text_en: string | null;
  translated_text_de: string | null;
  review_text_de: string | null;
  translation_status: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChecklistNodeTree extends ChecklistNode {
  children: ChecklistNodeTree[];
}

export interface NodeCreatePayload {
  parent_id?: string | null;
  node_type?: NodeType;
  branch?: NodeBranch | null;
  ja_label?: string | null;
  nein_label?: string | null;
  decision_parent_id?: string | null;
  sort_order?: number;
  title?: string | null;
  public_remark?: string | null;
  eingabetyp?: number | null;
  answer_type?: TemplateAnswerType | null;
  answer_set_id?: string | null;
  category_id?: string | null;
  legal_reference?: string | null;
  relevant_documents_json?: unknown | null;
  is_header_field?: boolean;
}

export type NodeUpdatePayload = Partial<NodeCreatePayload>;

export interface ChecklistAnswerOption {
  id: string;
  answer_set_id: string;
  name: string;
  sort_order: number;
  is_standard: boolean;
  is_entfaellt: boolean;
  value_number: number | null;
  threshold: number | null;
  bemerkung: string | null;
}

export interface ChecklistAnswerSet {
  id: string;
  template_id: string | null;
  name: string;
  description: string | null;
  sort_order: number;
  created_at: string | null;
  options: ChecklistAnswerOption[];
}

export interface AnswerOptionPayload {
  name: string;
  sort_order?: number;
  is_standard?: boolean;
  is_entfaellt?: boolean;
  value_number?: number | null;
  threshold?: number | null;
  bemerkung?: string | null;
}

export interface ChecklistTemplateMemberDetail extends ChecklistTemplateMember {
  user_name: string | null;
  user_email: string | null;
  organization: string | null;
  bundesland: string | null;
  function_role: string | null;
}

export interface ChecklistTemplateDetail extends ChecklistTemplate {
  members: ChecklistTemplateMemberDetail[];
  categories: ChecklistTemplateCategory[];
  answer_sets: ChecklistAnswerSet[];
}

// ── Versionierung / Verlauf (ChecklistNodeHistory) ───────────────────────────

/** Aenderungsart eines Verlaufseintrags (server-seitige Enum-Werte). */
export type NodeChangeType =
  | 'created' | 'updated' | 'deleted' | 'moved'
  | 'duplicated' | 'restored' | 'translated' | 'reviewed';

/** Ein Verlaufseintrag in der Commit-artigen Listenansicht. */
export interface HistoryEntry {
  id: string;
  template_id: string;
  node_id: string;
  node_version: number;
  change_type: NodeChangeType | string;
  change_reason: string | null;
  summary: string;
  changed_by_id: string | null;
  changed_by_name: string | null;
  created_at: string | null;
}

/** Ein einzelnes Feld-Diff: alter und neuer Wert. */
export interface HistoryFieldChange {
  old: unknown;
  new: unknown;
}

/** Detail eines Verlaufseintrags inkl. Voll-Snapshot und Feld-Diff. */
export interface HistoryDetail extends HistoryEntry {
  node_snapshot: Record<string, unknown> | null;
  changed_fields: Record<string, HistoryFieldChange> | null;
  old_parent_id: string | null;
  new_parent_id: string | null;
  old_position: number | null;
  new_position: number | null;
}

/** Ergebnis einer Wiederherstellung. */
export interface RestoreResult {
  status: string; // "restored" | "recreated"
  node_id: string;
  new_version: number;
  history_id: string;
}

/** Bulk-Ergebnis einer Uebersetzung (EN→DE). */
export interface TranslateResult {
  template_id: string;
  translated_count: number;
  skipped_count: number;
  failed_count: number;
  nodes: Array<{
    id: string;
    source_text_en: string | null;
    title: string | null;
    ok: boolean;
    error: string | null;
  }>;
}

/** Ergebnis einer Einzel-Uebersetzung. */
export interface TranslatedNode {
  id: string;
  source_text_en: string | null;
  title: string | null;
  ok: boolean;
  error: string | null;
}

/** Exportformate des Checklisten-Designers. */
export type ExportFormat = 'word' | 'excel' | 'pdf';
/** Exportmodus: leere Felder vs. befuellte Daten. */
export type ExportMode = 'blank' | 'filled';

// ── Kollaboration (Presence + Node-Locking + Live-Updates via SSE) ───────────

/** Aktuell ueber den SSE-Stream verbundener Nutzer (Presence-Registry). */
export interface CollabPresenceUser {
  user_id: string;
  name: string | null;
  organization: string | null;
  bundesland: string | null;
  last_seen: string | null;
}

/** Aktiver Bearbeitungs-Lock auf einen Knoten inkl. Halter-Stammdaten. */
export interface CollabNodeLock {
  node_id: string;
  template_id?: string;
  locked_by_id: string;
  locked_by_name: string | null;
  organization?: string | null;
  bundesland?: string | null;
  locked_at?: string | null;
  expires_at: string | null;
}

/** Halter-Infos im 409-Body, wenn ein anderer Nutzer den Lock haelt. */
export interface CollabLockConflict {
  message: string;
  locked_by_id: string;
  locked_by_name: string | null;
  organization: string | null;
  bundesland: string | null;
  expires_at: string | null;
}

/** Eigene Sitzungsinfos (Nutzerkennung + Anzeigename). */
export interface SessionInfo {
  user_id: string;
  email: string | null;
  name: string | null;
  organization: string | null;
  role: string | null;
  created_at?: string | null;
}

// ── API-Funktionen ───────────────────────────────────────────────────────────

// Projects
export const listProjects = () => request<{ projects: Project[]; total: number }>('/projects/');
export const getProject = (id: string) => request<Project>(`/projects/${id}`);
export const createProject = (data: Partial<Project>) =>
  request<Project>('/projects/', { method: 'POST', body: JSON.stringify(data) });
export const updateProject = (id: string, data: Partial<Project>) =>
  request<Project>(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteProject = (id: string) =>
  request<void>(`/projects/${id}`, { method: 'DELETE' });

// Checklists
export const listChecklists = (projectId: string) =>
  request<Checklist[]>(`/projects/${projectId}/checklists/`);
export const getChecklist = (projectId: string, clId: string) =>
  request<ChecklistDetail>(`/projects/${projectId}/checklists/${clId}`);
export const createChecklist = (projectId: string, data: { name: string; description?: string; template_id?: string; questions?: unknown[] }) =>
  request<ChecklistDetail>(`/projects/${projectId}/checklists/`, { method: 'POST', body: JSON.stringify(data) });
export const deleteChecklist = (projectId: string, clId: string) =>
  request<void>(`/projects/${projectId}/checklists/${clId}`, { method: 'DELETE' });

// Questions
export const getQuestionDetail = (projectId: string, clId: string, qId: string) =>
  request<QuestionDetail>(`/projects/${projectId}/checklists/${clId}/questions/${qId}`);
export const updateQuestion = (projectId: string, clId: string, qId: string, data: Partial<Question>) =>
  request<Question>(`/projects/${projectId}/checklists/${clId}/questions/${qId}`, { method: 'PUT', body: JSON.stringify(data) });
export const addQuestion = (projectId: string, clId: string, data: Partial<Question>) =>
  request<Question>(`/projects/${projectId}/checklists/${clId}/questions`, { method: 'POST', body: JSON.stringify(data) });
export const deleteQuestion = (projectId: string, clId: string, qId: string) =>
  request<void>(`/projects/${projectId}/checklists/${clId}/questions/${qId}`, { method: 'DELETE' });

// Assessment
export const acceptRemark = (qId: string) =>
  request<{ status: string }>(`/assessment/questions/${qId}/accept`, { method: 'PUT' });
export const rejectRemark = (qId: string, feedback?: string) =>
  request<{ status: string }>(`/assessment/questions/${qId}/reject`, {
    method: 'PUT',
    body: JSON.stringify({ feedback: feedback || null }),
  });
export const editRemark = (qId: string, remarkText: string) =>
  request<{ status: string }>(`/assessment/questions/${qId}/edit`, {
    method: 'PUT',
    body: JSON.stringify({ remark_text: remarkText }),
  });

// Checklisten-Templates (Designer)
export const listChecklistTemplates = () =>
  request<ChecklistTemplate[]>('/checklist-templates/');
export const getChecklistTemplate = (id: string) =>
  request<ChecklistTemplateDetail>(`/checklist-templates/${id}`);

// Knoten-Baum + CRUD + Move
export const getChecklistTree = (id: string) =>
  request<ChecklistNodeTree[]>(`/checklist-templates/${id}/tree`);
export const createChecklistNode = (id: string, data: NodeCreatePayload) =>
  request<ChecklistNode>(`/checklist-templates/${id}/nodes`, {
    method: 'POST', body: JSON.stringify(data),
  });
export const updateChecklistNode = (id: string, nodeId: string, data: NodeUpdatePayload) =>
  request<ChecklistNode>(`/checklist-templates/${id}/nodes/${nodeId}`, {
    method: 'PUT', body: JSON.stringify(data),
  });
export const deleteChecklistNode = (id: string, nodeId: string) =>
  request<void>(`/checklist-templates/${id}/nodes/${nodeId}`, { method: 'DELETE' });
export const moveChecklistNode = (
  id: string, nodeId: string, data: { parent_id: string | null; sort_order: number },
) =>
  request<ChecklistNode>(`/checklist-templates/${id}/nodes/${nodeId}/move`, {
    method: 'POST', body: JSON.stringify(data),
  });

// Mitglieder (angereichert) — fuer Rollen-Anzeige
export const listChecklistMembers = (id: string) =>
  request<ChecklistTemplateMemberDetail[]>(`/checklist-templates/${id}/members`);

// ── Versionierung / Verlauf ───────────────────────────────────────────────────

/** Commit-artiger Gesamtverlauf einer Checkliste (neueste zuerst, paginiert). */
export const getChecklistHistory = (
  id: string,
  opts?: { limit?: number; offset?: number; nodeId?: string },
) => {
  const query = new URLSearchParams();
  if (typeof opts?.limit === 'number') query.set('limit', String(opts.limit));
  if (typeof opts?.offset === 'number') query.set('offset', String(opts.offset));
  if (opts?.nodeId) query.set('node_id', opts.nodeId);
  const suffix = query.toString();
  return request<HistoryEntry[]>(`/checklist-templates/${id}/history${suffix ? `?${suffix}` : ''}`);
};

/** Vollstaendiger Verlauf eines einzelnen Knotens (neueste zuerst). */
export const getNodeHistory = (id: string, nodeId: string) =>
  request<HistoryEntry[]>(`/checklist-templates/${id}/nodes/${nodeId}/history`);

/** Detail eines Verlaufseintrags inkl. Snapshot + Feld-Diff. */
export const getHistoryDetail = (id: string, historyId: string) =>
  request<HistoryDetail>(`/checklist-templates/${id}/history/${historyId}`);

/** Setzt einen Knoten auf den Snapshot eines Verlaufseintrags zurueck (editor+). */
export const restoreHistory = (id: string, historyId: string, changeReason?: string) =>
  request<RestoreResult>(`/checklist-templates/${id}/history/${historyId}/restore`, {
    method: 'POST',
    body: JSON.stringify({ change_reason: changeReason ?? null }),
  });

// ── Export (DOCX/XLSX/PDF) ────────────────────────────────────────────────────

const EXPORT_ENDPOINT: Record<ExportFormat, string> = {
  word: 'export-word',
  excel: 'export-excel',
  pdf: 'export-pdf',
};

const EXPORT_FALLBACK_EXT: Record<ExportFormat, string> = {
  word: 'docx',
  excel: 'xlsx',
  pdf: 'pdf',
};

/**
 * Laedt einen Checklisten-Export als Blob und stoesst den Browser-Download ueber
 * einen temporaeren ``<a>``-Link an (keine zusaetzliche Abhaengigkeit). Der
 * Dateiname wird — falls vorhanden — aus dem ``Content-Disposition``-Header
 * uebernommen, sonst aus Titel/Format gebildet.
 */
export async function exportChecklist(
  id: string,
  format: ExportFormat,
  mode: ExportMode = 'blank',
): Promise<void> {
  const endpoint = EXPORT_ENDPOINT[format];
  const res = await fetch(
    `${BASE}/checklist-templates/${id}/${endpoint}?mode=${encodeURIComponent(mode)}`,
    { headers: { ...getWorkshopAuthHeaders() } },
  );
  if (res.status === 401 && getWorkshopAuthToken()) {
    handleAuthExpired();
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }

  // Dateinamen aus Content-Disposition extrahieren (filename="...").
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const filename = match
    ? decodeURIComponent(match[1])
    : `Pruefcheckliste.${EXPORT_FALLBACK_EXT[format]}`;

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Object-URL nach kurzem Tick freigeben (Safari/Firefox-sicher).
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Uebersetzung (EN→DE via LLM) ──────────────────────────────────────────────

/**
 * Uebersetzt englischsprachige Knoten eines Templates ins Deutsche (editor+).
 * Ohne ``nodeIds`` werden alle EN-Knoten betrachtet. Bei nicht erreichbarem
 * LLM-Backend wirft der Server HTTP 503 (vom Aufrufer abzufangen).
 */
export const translateChecklist = (id: string, nodeIds?: string[]) =>
  request<TranslateResult>(`/checklist-templates/${id}/translate`, {
    method: 'POST',
    body: JSON.stringify(nodeIds && nodeIds.length ? { node_ids: nodeIds } : {}),
  });

/** Uebersetzt einen einzelnen Knoten-Titel EN→DE (editor+). */
export const translateNode = (id: string, nodeId: string) =>
  request<TranslatedNode>(`/checklist-templates/${id}/nodes/${nodeId}/translate`, {
    method: 'POST',
  });

// ── Kollaboration: SSE-Stream, Node-Locks, Presence ──────────────────────────

/**
 * Oeffnet den SSE-Stream einer Checkliste. ``EventSource`` kann keine
 * Authorization-Header setzen, daher wird der Workshop-Token als Query-Parameter
 * uebergeben (Backend validiert ihn ueber ``?token=...``). Liefert die
 * EventSource-Instanz; der Aufrufer haengt ``onmessage``/``onerror`` an und ruft
 * ``close()`` beim Verlassen der Seite.
 */
export function openChecklistEvents(id: string): EventSource {
  const token = getWorkshopAuthToken() ?? '';
  const url = `${BASE}/checklist-templates/${id}/events?token=${encodeURIComponent(token)}`;
  return new EventSource(url);
}

/**
 * Fehler beim Lock-Erwerb. Bei HTTP 409 (anderer Nutzer haelt den Lock) liegt in
 * ``conflict`` der Halter-Datensatz vor; der Aufrufer kann den Inspector dann
 * schreibgeschuetzt mit Halter-Hinweis darstellen.
 */
export class LockConflictError extends Error {
  status: number;
  conflict: CollabLockConflict | null;
  constructor(status: number, conflict: CollabLockConflict | null, message: string) {
    super(message);
    this.name = 'LockConflictError';
    this.status = status;
    this.conflict = conflict;
  }
}

/**
 * Erwirbt/erneuert einen Bearbeitungs-Lock auf einen Knoten. Bei 409 wird ein
 * ``LockConflictError`` mit den Halter-Infos geworfen, sonst der eigene Lock
 * zurueckgegeben.
 */
export async function acquireNodeLock(id: string, nodeId: string): Promise<CollabNodeLock> {
  const res = await fetch(`${BASE}/checklist-templates/${id}/nodes/${nodeId}/lock`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
  });
  if (res.status === 401 && getWorkshopAuthToken()) {
    handleAuthExpired();
  }
  if (res.status === 409) {
    let conflict: CollabLockConflict | null = null;
    try {
      const body = await res.json();
      // FastAPI verpackt HTTPException(detail=...) in {detail: ...}.
      conflict = (body?.detail ?? body) as CollabLockConflict;
    } catch { /* kein JSON-Body */ }
    throw new LockConflictError(409, conflict, conflict?.message ?? 'Knoten ist gesperrt.');
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<CollabNodeLock>;
}

/** Gibt den eigenen Lock auf einen Knoten frei (idempotent). */
export const releaseNodeLock = (id: string, nodeId: string) =>
  request<void>(`/checklist-templates/${id}/nodes/${nodeId}/lock`, { method: 'DELETE' });

/** Listet die aktiven (nicht abgelaufenen) Locks einer Checkliste. */
export const listLocks = (id: string) =>
  request<CollabNodeLock[]>(`/checklist-templates/${id}/locks`);

/** Liefert die aktuell ueber SSE verbundenen Nutzer einer Checkliste. */
export const listPresence = (id: string) =>
  request<CollabPresenceUser[]>(`/checklist-templates/${id}/presence`);

/** Eigene Sitzungsinfos (Nutzerkennung + Anzeigename) — fuer „eigener Nutzer". */
export const getMe = () => request<SessionInfo>('/auth/me');

// Antwortsets: global + checklistenspezifisch
export const listGlobalAnswerSets = () =>
  request<ChecklistAnswerSet[]>('/checklist-templates/answer-sets');
export const listTemplateAnswerSets = (id: string) =>
  request<ChecklistAnswerSet[]>(`/checklist-templates/${id}/answer-sets`);
export const createGlobalAnswerSet = (data: { name: string; description?: string | null; sort_order?: number; options?: AnswerOptionPayload[] }) =>
  request<ChecklistAnswerSet>('/checklist-templates/answer-sets', {
    method: 'POST', body: JSON.stringify(data),
  });
export const createTemplateAnswerSet = (id: string, data: { name: string; description?: string | null; sort_order?: number; options?: AnswerOptionPayload[] }) =>
  request<ChecklistAnswerSet>(`/checklist-templates/${id}/answer-sets`, {
    method: 'POST', body: JSON.stringify(data),
  });
export const updateAnswerSet = (setId: string, data: { name?: string; description?: string | null; sort_order?: number }) =>
  request<ChecklistAnswerSet>(`/checklist-templates/answer-sets/${setId}`, {
    method: 'PUT', body: JSON.stringify(data),
  });
export const deleteAnswerSet = (setId: string) =>
  request<void>(`/checklist-templates/answer-sets/${setId}`, { method: 'DELETE' });
export const addAnswerOption = (setId: string, data: AnswerOptionPayload) =>
  request<ChecklistAnswerOption>(`/checklist-templates/answer-sets/${setId}/options`, {
    method: 'POST', body: JSON.stringify(data),
  });
export const updateAnswerOption = (optionId: string, data: Partial<AnswerOptionPayload>) =>
  request<ChecklistAnswerOption>(`/checklist-templates/answer-options/${optionId}`, {
    method: 'PUT', body: JSON.stringify(data),
  });
export const deleteAnswerOption = (optionId: string) =>
  request<void>(`/checklist-templates/answer-options/${optionId}`, { method: 'DELETE' });

// Kategorien je Checkliste
export const listChecklistCategories = (id: string) =>
  request<ChecklistTemplateCategory[]>(`/checklist-templates/${id}/categories`);
export const createChecklistCategory = (id: string, data: { name: string; sort_order?: number }) =>
  request<ChecklistTemplateCategory>(`/checklist-templates/${id}/categories`, {
    method: 'POST', body: JSON.stringify(data),
  });
export const updateChecklistCategory = (id: string, catId: string, data: { name?: string; sort_order?: number }) =>
  request<ChecklistTemplateCategory>(`/checklist-templates/${id}/categories/${catId}`, {
    method: 'PUT', body: JSON.stringify(data),
  });
export const deleteChecklistCategory = (id: string, catId: string) =>
  request<void>(`/checklist-templates/${id}/categories/${catId}`, { method: 'DELETE' });

// Knowledge
export const getKnowledgeStats = () => request<KnowledgeStats>('/knowledge/stats');
export const searchKnowledge = (q: string, topK = 5) =>
  request<{ query: string; results: SearchResult[] }>(`/knowledge/search?q=${encodeURIComponent(q)}&top_k=${topK}`);
export const deleteKnowledgeSource = (source: string) =>
  request<{ deleted_chunks: number }>(`/knowledge/source/${encodeURIComponent(source)}`, { method: 'DELETE' });

// Demo
export const seedDemoData = () => request<{ status: string; project_id?: string; checklist_id?: string }>('/demo/seed', { method: 'POST' });
export const resetDemoData = () => request<{ status: string }>('/demo/reset', { method: 'DELETE' });
export const listDemoTemplates = () => request<{ templates: DemoTemplate[] }>('/demo/templates');

// System
export const getGpuInfo = () => request<GpuInfo[]>('/system/gpu');
export const getSystemInfo = () => request<SystemInfo>('/system/info');
export const getOllamaStatus = () => request<{ ok: boolean; models?: string[] }>('/system/ollama');
export const getSystemProfile = () => request<SystemProfile>('/system/profile');
export const listBeneficiaryCountries = () =>
  request<{ countries: CountryProfile[]; presets: { AT?: AustriaPresetSource[] } }>('/beneficiaries/countries');

export const listBeneficiarySources = (country_code?: CountryCode | '') => {
  const query = new URLSearchParams();
  if (country_code) query.set('country_code', country_code);
  const suffix = query.toString();
  return request<{ country_code: CountryCode | null; available_country_codes: CountryCode[]; sources: BeneficiarySource[] }>(
    `/beneficiaries/sources${suffix ? `?${suffix}` : ''}`,
  );
};
export const searchBeneficiaries = (params: {
  q?: string;
  scope?: 'all' | 'company' | 'project' | 'aktenzeichen' | 'location';
  bundesland?: string;
  fonds?: string;
  source?: string;
  min_cost?: number;
  limit?: number;
  company_limit?: number;
  country_code?: CountryCode | '';
}) => {
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.scope) query.set('scope', params.scope);
  if (params.bundesland) query.set('bundesland', params.bundesland);
  if (params.fonds) query.set('fonds', params.fonds);
  if (params.source) query.set('source', params.source);
  if (typeof params.min_cost === 'number') query.set('min_cost', String(params.min_cost));
  if (typeof params.limit === 'number') query.set('limit', String(params.limit));
  if (typeof params.company_limit === 'number') query.set('company_limit', String(params.company_limit));
  if (params.country_code) query.set('country_code', params.country_code);
  return request<BeneficiarySearchResponse>(`/beneficiaries/search?${query.toString()}`);
};
export const analyzeBeneficiaries = (params: {
  mode: BeneficiaryAnalysisMode;
  bundesland?: string;
  fonds?: string;
  source?: string;
  min_cost?: number;
  limit?: number;
  country_code?: CountryCode | '';
}) => {
  const query = new URLSearchParams();
  query.set('mode', params.mode);
  if (params.bundesland) query.set('bundesland', params.bundesland);
  if (params.fonds) query.set('fonds', params.fonds);
  if (params.source) query.set('source', params.source);
  if (typeof params.min_cost === 'number') query.set('min_cost', String(params.min_cost));
  if (typeof params.limit === 'number') query.set('limit', String(params.limit));
  if (params.country_code) query.set('country_code', params.country_code);
  return request<BeneficiaryAnalyticsResponse>(`/beneficiaries/analytics?${query.toString()}`);
};
export const listReferenceSources = () => request<{ sources: ReferenceRegistrySource[] }>('/reference-data/sources');
export const searchReferenceData = (params: {
  q?: string;
  registry_type?: ReferenceRegistryType;
  source?: string;
  limit?: number;
}) => {
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.registry_type) query.set('registry_type', params.registry_type);
  if (params.source) query.set('source', params.source);
  if (typeof params.limit === 'number') query.set('limit', String(params.limit));
  return request<ReferenceRegistrySearchResponse>(`/reference-data/search?${query.toString()}`);
};
export const importReferenceData = (form: FormData) => requestForm<{
  source: string;
  registry_type: ReferenceRegistryType;
  rows: number;
  columns: string[];
}>( '/reference-data/import', form);
export const deleteReferenceSource = (source: string) =>
  request<{ status: string; source: string }>(`/reference-data/${encodeURIComponent(source)}`, { method: 'DELETE' });

// SSE Streaming helper
export function streamSSE(
  url: string,
  body: unknown,
  onToken: (token: string) => void,
  onDone: (info: { token_count?: number; model?: string; tok_per_s?: number }) => void,
  onError: (err: string) => void,
  onStatus?: (state: string) => void,
): AbortController {
  const controller = new AbortController();
  fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (res.status === 401 && getWorkshopAuthToken()) {
        handleAuthExpired();
        onError('Sitzung abgelaufen. Bitte erneut anmelden.');
        return;
      }
      if (!res.ok) {
        onError(`HTTP ${res.status}`);
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.error) {
              onError(data.error);
            } else if (data.done) {
              onDone(data);
            } else if (data.token) {
              onToken(data.token);
            } else if (data.type === 'status' && data.state) {
              onStatus?.(data.state);
            } else if (data.type === 'progress') {
              onToken(`\n[${data.current}/${data.total}] ${data.question_key}...\n`);
            }
          } catch { /* skip invalid JSON */ }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(String(err));
    });
  return controller;
}
