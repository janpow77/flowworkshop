/**
 * flowworkshop · lib/api.ts
 * Zentraler API-Client und Typen.
 */

const BASE = '/api';

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  });
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
    body: form,
  });
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
  privacy_mode: boolean;
  allow_remote_geocoding: boolean;
  allow_remote_tiles: boolean;
}

export interface BeneficiarySource {
  source: string;
  bundesland: string | null;
  fonds: string | null;
  periode: string | null;
  row_count: number;
}

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
}

export interface BeneficiaryCompanyHit {
  company_name: string;
  total_kosten: number;
  total_kosten_label: string;
  project_count: number;
  match_score: number;
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
export const listBeneficiarySources = () => request<{ sources: BeneficiarySource[] }>('/beneficiaries/sources');
export const searchBeneficiaries = (params: {
  q?: string;
  scope?: 'all' | 'company' | 'project' | 'aktenzeichen' | 'location';
  bundesland?: string;
  fonds?: string;
  source?: string;
  min_cost?: number;
  limit?: number;
  company_limit?: number;
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
  return request<BeneficiarySearchResponse>(`/beneficiaries/search?${query.toString()}`);
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
): AbortController {
  const controller = new AbortController();
  fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
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
