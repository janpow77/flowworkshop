/**
 * flowworkshop · pages/AdminBeneficiarySourcesPage.tsx
 *
 * Phase 6b — Admin-UI fuer die datengetriebene Beneficiary-Quellen-Pipeline.
 *
 * Listet alle Quellen-Configs, erlaubt CRUD + Test-Run + manuellen Harvest +
 * Run-History. Quellen mit `enabled=false` werden mit reduzierter Opacity
 * dargestellt — Soft-Disable ist kein Loeschen.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Loader2, Plus, RefreshCw, Settings, Database, Globe2, FlaskConical,
  Zap, Power, AlertCircle, CheckCircle2, Circle, X, Save, Upload,
  Trash2, FileText, Clock, Activity,
} from 'lucide-react';
import { getWorkshopAuthHeaders } from '../lib/api';

// ── Typen ────────────────────────────────────────────────────────────────────

interface SourceConfig {
  source_key: string;
  display_name: string;
  bundesland: string | null;
  fonds: string | null;
  periode: string | null;
  country_code: string | null;
  source_type: 'xlsx_url' | 'csv_url' | 'manual_upload';
  source_url: string | null;
  source_landing_page: string | null;
  update_frequency_days: number | null;
  license: string | null;
  sheet_name: string | null;
  header_row: number;
  field_mapping: Record<string, string>;
  required_fields: string[];
  validations: Record<string, unknown>[];
  enabled: boolean;
  last_successful_harvest_at: string | null;
  last_harvest_run_id: string | null;
  last_seen_sha256: string | null;
  record_count: number;
  quality: 'green' | 'yellow' | 'red' | null;
  coverage_note: string | null;
  notes_for_pruefer: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface HarvestRun {
  id: string;
  source_key: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  records_seen: number;
  records_inserted: number;
  records_skipped: number;
  records_failed: number;
  triggered_by: string;
  error_message: string | null;
  parameters: Record<string, unknown>;
}

interface TestRunResponse {
  source_key: string;
  fetch_source: string;
  file_name: string;
  file_size_bytes: number;
  rows_parsed: number;
  preview_rows_returned: number;
  skipped_no_name: number;
  detected_field_mapping: Record<string, string>;
  preview: { row_number: number; fields: Record<string, unknown> }[];
  validation_findings: { row_number: number; issues: string[] }[];
  validation_findings_count: number;
}

const CANONICAL_ALIASES = [
  'name', 'projekt', 'aktenzeichen', 'beschreibung',
  'kosten', 'kosten_eu', 'currency',
  'standort', 'ort', 'plz', 'landkreis', 'nuts', 'latitude', 'longitude',
  'beginn', 'ende', 'funded_at',
] as const;

// ── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return 'nie';
  const t = new Date(iso).getTime();
  const diffSec = Math.floor((Date.now() - t) / 1000);
  if (diffSec < 60) return `vor ${diffSec}s`;
  if (diffSec < 3600) return `vor ${Math.floor(diffSec / 60)} min`;
  if (diffSec < 86400) return `vor ${Math.floor(diffSec / 3600)} h`;
  if (diffSec < 86400 * 30) return `vor ${Math.floor(diffSec / 86400)} d`;
  return new Date(iso).toLocaleDateString('de-DE');
}

function qualityClass(q: string | null): string {
  if (q === 'green') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200';
  if (q === 'yellow') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200';
  if (q === 'red') return 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200';
  return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
}

function statusClass(s: string): string {
  if (s === 'ok') return 'text-emerald-700 dark:text-emerald-300';
  if (s === 'partial' || s === 'unchanged') return 'text-amber-700 dark:text-amber-300';
  if (s === 'failed') return 'text-rose-700 dark:text-rose-300';
  return 'text-slate-500';
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AdminBeneficiarySourcesPage() {
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [filter, setFilter] = useState<'all' | 'enabled' | 'disabled'>('enabled');

  const isAdmin = (localStorage.getItem('workshop_role') || '') === 'admin';

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const r = await fetch('/api/admin/beneficiary-sources', {
        headers: getWorkshopAuthHeaders(),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setSources(d.sources || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin, load]);

  const filtered = useMemo(() => {
    if (filter === 'all') return sources;
    if (filter === 'enabled') return sources.filter((s) => s.enabled);
    return sources.filter((s) => !s.enabled);
  }, [sources, filter]);

  const active = useMemo(
    () => sources.find((s) => s.source_key === activeKey) || null,
    [sources, activeKey],
  );

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <div className="rounded-2xl border border-amber-300 bg-amber-50 px-6 py-5 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <h2 className="font-semibold mb-2">Nur für Admins.</h2>
          <p className="text-sm">
            Diese Seite verwaltet die datengetriebene Quellen-Pipeline und ist nur
            für Administratoren zugänglich.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 space-y-6">
      {/* Hero-Card */}
      <div className="rounded-3xl border border-slate-200/70 bg-white/85 backdrop-blur p-6 dark:border-slate-800/70 dark:bg-slate-900/70">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-300">
              <Database size={14} />
              <span>Phase 6b · Datengetriebene Pipeline</span>
            </div>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
              Beneficiaries-Quellen-Verwaltung
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
              Pro Begünstigtenverzeichnis-Quelle eine Konfiguration: URL, Field-
              Mapping, Validierungen, Update-Frequenz. Der Worker liest die
              Configs nachts und führt einen Smart-Mode-Harvest aus — keine
              Code-Änderung mehr nötig, wenn ein neues Bundesland dazukommt.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as 'all' | 'enabled' | 'disabled')}
              className="text-xs px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
            >
              <option value="enabled">Aktive ({sources.filter((s) => s.enabled).length})</option>
              <option value="disabled">Deaktivierte ({sources.filter((s) => !s.enabled).length})</option>
              <option value="all">Alle ({sources.length})</option>
            </select>
            <button
              onClick={load}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Neu laden
            </button>
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-xl bg-cyan-600 text-white hover:bg-cyan-700"
            >
              <Plus size={14} />
              Neue Quelle
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} />
            {error}
          </div>
        </div>
      )}

      {/* Liste */}
      <SourcesList
        sources={filtered}
        onSelect={(k) => setActiveKey(k)}
      />

      {/* Detail-Drawer */}
      {active && (
        <SourceDetailDrawer
          source={active}
          onClose={() => setActiveKey(null)}
          onChanged={load}
        />
      )}

      {/* Create-Modal */}
      {showCreate && (
        <CreateSourceModal
          onClose={() => setShowCreate(false)}
          onCreated={async () => {
            setShowCreate(false);
            await load();
          }}
        />
      )}
    </div>
  );
}

// ── Liste ────────────────────────────────────────────────────────────────────

function SourcesList({
  sources,
  onSelect,
}: {
  sources: SourceConfig[];
  onSelect: (key: string) => void;
}) {
  if (sources.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/60">
        Keine Quellen gefunden. Klicken Sie oben auf
        {' '}<strong>Neue Quelle</strong>, um eine erste Config anzulegen.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {sources.map((s) => (
        <SourceCard key={s.source_key} source={s} onSelect={() => onSelect(s.source_key)} />
      ))}
    </div>
  );
}

function SourceCard({
  source: s,
  onSelect,
}: {
  source: SourceConfig;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`text-left rounded-2xl border bg-white p-4 hover:shadow-lg transition-all dark:bg-slate-900 ${
        s.enabled
          ? 'border-slate-200 dark:border-slate-800'
          : 'border-slate-200/60 opacity-60 dark:border-slate-800/60'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${
              s.quality === 'green' ? 'bg-emerald-500'
              : s.quality === 'yellow' ? 'bg-amber-500'
              : s.quality === 'red' ? 'bg-rose-500'
              : 'bg-slate-300 dark:bg-slate-600'
            }`} />
            <h3 className="font-semibold text-sm text-slate-900 dark:text-white truncate">
              {s.display_name}
            </h3>
          </div>
          <code className="mt-1 block text-[11px] text-slate-500 dark:text-slate-400 truncate">
            {s.source_key}
          </code>
        </div>
        {!s.enabled && (
          <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
            <Power size={10} /> Aus
          </span>
        )}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        {s.bundesland && (
          <div>
            <dt className="text-slate-400 dark:text-slate-500">Bundesland</dt>
            <dd className="text-slate-700 dark:text-slate-200 truncate">{s.bundesland}</dd>
          </div>
        )}
        {s.fonds && (
          <div>
            <dt className="text-slate-400 dark:text-slate-500">Fonds</dt>
            <dd className="text-slate-700 dark:text-slate-200 truncate">{s.fonds}</dd>
          </div>
        )}
        {s.country_code && (
          <div>
            <dt className="text-slate-400 dark:text-slate-500">Land</dt>
            <dd className="text-slate-700 dark:text-slate-200 truncate">{s.country_code}</dd>
          </div>
        )}
        <div>
          <dt className="text-slate-400 dark:text-slate-500">Quelle</dt>
          <dd className="text-slate-700 dark:text-slate-200 truncate">
            {s.source_type === 'xlsx_url' ? <span className="inline-flex items-center gap-1"><Globe2 size={10} /> XLSX-URL</span>
            : s.source_type === 'csv_url' ? <span className="inline-flex items-center gap-1"><Globe2 size={10} /> CSV-URL</span>
            : <span className="inline-flex items-center gap-1"><Upload size={10} /> Upload</span>}
          </dd>
        </div>
      </dl>

      <div className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-[11px]">
        <span className="inline-flex items-center gap-1 text-slate-500 dark:text-slate-400">
          <Clock size={10} />
          {relativeTime(s.last_successful_harvest_at)}
        </span>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${qualityClass(s.quality)}`}>
          {s.record_count.toLocaleString('de-DE')} Records
        </span>
      </div>
    </button>
  );
}

// ── Detail-Drawer ────────────────────────────────────────────────────────────

function SourceDetailDrawer({
  source,
  onClose,
  onChanged,
}: {
  source: SourceConfig;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [draft, setDraft] = useState<SourceConfig>(source);
  const [tab, setTab] = useState<'config' | 'mapping' | 'test' | 'history'>('config');
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [actionError, setActionError] = useState('');

  // Drawer schliesst sich auf Esc
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Beim Wechsel der Quelle: Draft neu seeden.
  useEffect(() => { setDraft(source); }, [source]);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(source),
    [draft, source],
  );

  const save = async () => {
    setSaving(true);
    setActionError('');
    try {
      const payload: Partial<SourceConfig> = {
        display_name: draft.display_name,
        bundesland: draft.bundesland,
        fonds: draft.fonds,
        periode: draft.periode,
        country_code: draft.country_code,
        source_type: draft.source_type,
        source_url: draft.source_url,
        source_landing_page: draft.source_landing_page,
        update_frequency_days: draft.update_frequency_days,
        license: draft.license,
        sheet_name: draft.sheet_name,
        header_row: draft.header_row,
        field_mapping: draft.field_mapping,
        required_fields: draft.required_fields,
        validations: draft.validations,
        enabled: draft.enabled,
        coverage_note: draft.coverage_note,
        notes_for_pruefer: draft.notes_for_pruefer,
      };
      const r = await fetch(`/api/admin/beneficiary-sources/${draft.source_key}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${r.status}`);
      }
      await onChanged();
      setSavedAt(Date.now());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  const toggleEnabled = async () => {
    if (draft.enabled) {
      if (!confirm(`Quelle '${draft.source_key}' soft-deaktivieren? (Worker holt sie nicht mehr automatisch.)`)) return;
      const r = await fetch(`/api/admin/beneficiary-sources/${draft.source_key}`, {
        method: 'DELETE',
        headers: getWorkshopAuthHeaders(),
      });
      if (r.ok) {
        await onChanged();
        onClose();
      }
    } else {
      // Re-enable via PUT
      setDraft({ ...draft, enabled: true });
      await save();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="absolute right-0 top-0 h-full w-full max-w-3xl bg-white shadow-2xl dark:bg-slate-950 overflow-y-auto"
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-white/95 dark:bg-slate-950/95 backdrop-blur border-b border-slate-200 dark:border-slate-800 px-6 py-4 flex items-center justify-between">
          <div>
            <code className="text-xs text-slate-500 dark:text-slate-400">
              {draft.source_key}
            </code>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              {draft.display_name}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <button
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-50"
              >
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                Speichern
              </button>
            )}
            {!dirty && savedAt && (Date.now() - savedAt < 3000) && (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={12} /> Gespeichert
              </span>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="px-6 pt-4 border-b border-slate-200 dark:border-slate-800 flex items-center gap-1 overflow-x-auto">
          {[
            { id: 'config', label: 'Konfiguration', icon: Settings },
            { id: 'mapping', label: 'Field-Mapping', icon: FileText },
            { id: 'test', label: 'Test-Run', icon: FlaskConical },
            { id: 'history', label: 'Run-History', icon: Activity },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id as 'config' | 'mapping' | 'test' | 'history')}
              className={`inline-flex items-center gap-1 px-4 py-2 text-xs font-medium border-b-2 -mb-px ${
                tab === id
                  ? 'border-cyan-600 text-cyan-700 dark:text-cyan-300'
                  : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>

        {actionError && (
          <div className="mx-6 mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
            {actionError}
          </div>
        )}

        {/* Inhalt */}
        <div className="p-6 space-y-4">
          {tab === 'config' && (
            <ConfigTab
              draft={draft}
              setDraft={setDraft}
              source={source}
              onToggleEnabled={toggleEnabled}
              onChanged={onChanged}
              setActionError={setActionError}
            />
          )}
          {tab === 'mapping' && (
            <MappingTab draft={draft} setDraft={setDraft} />
          )}
          {tab === 'test' && (
            <TestRunTab sourceKey={draft.source_key} />
          )}
          {tab === 'history' && (
            <RunHistoryTab sourceKey={draft.source_key} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Tab: Konfiguration ───────────────────────────────────────────────────────

function ConfigTab({
  draft,
  setDraft,
  source,
  onToggleEnabled,
  onChanged,
  setActionError,
}: {
  draft: SourceConfig;
  setDraft: (c: SourceConfig) => void;
  source: SourceConfig;
  onToggleEnabled: () => Promise<void>;
  onChanged: () => Promise<void>;
  setActionError: (msg: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [harvesting, setHarvesting] = useState(false);
  const [harvestResult, setHarvestResult] = useState<Record<string, unknown> | null>(null);

  const triggerHarvest = async () => {
    setHarvesting(true);
    setActionError('');
    setHarvestResult(null);
    try {
      const fd = new FormData();
      const f = fileRef.current?.files?.[0];
      if (f) fd.append('file', f);
      fd.append('mode', 'smart');
      const r = await fetch(`/api/admin/beneficiary-sources/${draft.source_key}/harvest`, {
        method: 'POST',
        headers: getWorkshopAuthHeaders(),
        body: fd,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setHarvestResult(d);
      await onChanged();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Harvest fehlgeschlagen');
    } finally {
      setHarvesting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Status-Info */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Stat label="Status" value={source.enabled ? 'aktiv' : 'deaktiviert'} accent={source.enabled ? 'emerald' : 'slate'} />
        <Stat label="Records" value={source.record_count.toLocaleString('de-DE')} />
        <Stat label="Letzter Lauf" value={relativeTime(source.last_successful_harvest_at)} />
      </div>

      {/* Felder */}
      <Section title="Anzeige + Filter">
        <Field label="Anzeigename" value={draft.display_name}
          onChange={(v) => setDraft({ ...draft, display_name: v })} />
        <Row>
          <Field label="Bundesland" value={draft.bundesland || ''}
            onChange={(v) => setDraft({ ...draft, bundesland: v || null })} />
          <Field label="Fonds" value={draft.fonds || ''}
            onChange={(v) => setDraft({ ...draft, fonds: v || null })} />
          <Field label="Periode" value={draft.periode || ''}
            onChange={(v) => setDraft({ ...draft, periode: v || null })} />
          <Field label="Country (ISO-2)" value={draft.country_code || ''}
            onChange={(v) => setDraft({ ...draft, country_code: v || null })} />
        </Row>
      </Section>

      <Section title="Quelle">
        <SelectField
          label="Source-Typ"
          value={draft.source_type}
          options={[
            { v: 'xlsx_url', l: 'XLSX-URL (Worker laedt automatisch)' },
            { v: 'csv_url', l: 'CSV-URL (Worker laedt automatisch)' },
            { v: 'manual_upload', l: 'Manueller Upload (Admin laedt selbst)' },
          ]}
          onChange={(v) => setDraft({ ...draft, source_type: v as SourceConfig['source_type'] })}
        />
        {(draft.source_type === 'xlsx_url' || draft.source_type === 'csv_url') && (
          <>
            <Field label="Source-URL" value={draft.source_url || ''}
              onChange={(v) => setDraft({ ...draft, source_url: v || null })}
              placeholder="https://example.gov/transparenzliste.xlsx" />
            <Field label="Landing-Page (optional)" value={draft.source_landing_page || ''}
              onChange={(v) => setDraft({ ...draft, source_landing_page: v || null })}
              placeholder="https://example.gov/efre/transparenz" />
            <Row>
              <NumberField label="Update-Frequenz (Tage)" value={draft.update_frequency_days}
                onChange={(v) => setDraft({ ...draft, update_frequency_days: v })} min={1} max={3650} />
              <Field label="Lizenz" value={draft.license || ''}
                onChange={(v) => setDraft({ ...draft, license: v || null })}
                placeholder="dl-de/by-2-0, CC-BY-4.0, …" />
            </Row>
            <Row>
              <Field label="Sheet-Name (optional)" value={draft.sheet_name || ''}
                onChange={(v) => setDraft({ ...draft, sheet_name: v || null })} />
              <NumberField label="Header-Row" value={draft.header_row}
                onChange={(v) => setDraft({ ...draft, header_row: v ?? 0 })} min={0} max={20} />
            </Row>
          </>
        )}
      </Section>

      <Section title="Notizen">
        <TextAreaField label="Coverage-Hinweis" value={draft.coverage_note || ''}
          onChange={(v) => setDraft({ ...draft, coverage_note: v || null })} />
        <TextAreaField label="Hinweis für den Prüfer" value={draft.notes_for_pruefer || ''}
          onChange={(v) => setDraft({ ...draft, notes_for_pruefer: v || null })} />
      </Section>

      {/* Aktionen */}
      <Section title="Aktionen">
        <div className="space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv,.xlsm"
              className="text-xs file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:text-slate-700 dark:file:border-slate-700 dark:file:bg-slate-800 dark:file:text-slate-200" />
            <button
              onClick={triggerHarvest}
              disabled={harvesting}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {harvesting ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
              Harvest jetzt
            </button>
            <button
              onClick={onToggleEnabled}
              className={`inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg ${
                draft.enabled
                  ? 'bg-rose-50 text-rose-700 hover:bg-rose-100 dark:bg-rose-950/50 dark:text-rose-200'
                  : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/50 dark:text-emerald-200'
              }`}
            >
              {draft.enabled ? <><Trash2 size={12} /> Soft-Disable</> : <><Power size={12} /> Aktivieren</>}
            </button>
          </div>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Bei xlsx_url/csv_url ohne hochgeladene Datei zieht der Worker die Datei direkt von der konfigurierten URL.
          </p>
          {harvestResult && (
            <pre className="text-[11px] bg-slate-50 dark:bg-slate-900 rounded-lg p-3 overflow-x-auto border border-slate-200 dark:border-slate-800">
              {JSON.stringify(harvestResult, null, 2)}
            </pre>
          )}
        </div>
      </Section>
    </div>
  );
}

// ── Tab: Field-Mapping + Validations ─────────────────────────────────────────

function MappingTab({
  draft,
  setDraft,
}: {
  draft: SourceConfig;
  setDraft: (c: SourceConfig) => void;
}) {
  const setMapping = (alias: string, header: string) => {
    const m = { ...draft.field_mapping };
    if (header.trim()) m[alias] = header.trim();
    else delete m[alias];
    setDraft({ ...draft, field_mapping: m });
  };

  const toggleRequired = (alias: string) => {
    const set = new Set(draft.required_fields);
    if (set.has(alias)) set.delete(alias);
    else set.add(alias);
    setDraft({ ...draft, required_fields: [...set] });
  };

  const addValidation = () => {
    setDraft({
      ...draft,
      validations: [
        ...(draft.validations || []),
        { field: '', regex: '', message: '' },
      ],
    });
  };

  const updateValidation = (idx: number, key: 'field' | 'regex' | 'message', value: string) => {
    const arr = [...(draft.validations || [])];
    arr[idx] = { ...arr[idx], [key]: value };
    setDraft({ ...draft, validations: arr });
  };

  const removeValidation = (idx: number) => {
    const arr = [...(draft.validations || [])];
    arr.splice(idx, 1);
    setDraft({ ...draft, validations: arr });
  };

  return (
    <div className="space-y-6">
      <Section title="Field-Mapping (kanonisch -> XLSX-Spalte)">
        <p className="text-[11px] text-slate-500 dark:text-slate-400 mb-3">
          Lasst ein Feld leer, wenn der Worker es ueber das Pattern-Fallback automatisch erkennen soll.
        </p>
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500">
              <tr>
                <th className="text-left px-3 py-2 font-medium w-28">Pflicht?</th>
                <th className="text-left px-3 py-2 font-medium w-32">Kanonisch</th>
                <th className="text-left px-3 py-2 font-medium">XLSX-Spalte</th>
              </tr>
            </thead>
            <tbody>
              {CANONICAL_ALIASES.map((alias) => (
                <tr key={alias} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="px-3 py-1.5">
                    <input
                      type="checkbox"
                      checked={draft.required_fields.includes(alias)}
                      onChange={() => toggleRequired(alias)}
                    />
                  </td>
                  <td className="px-3 py-1.5"><code className="text-slate-700 dark:text-slate-200">{alias}</code></td>
                  <td className="px-3 py-1.5">
                    <input
                      type="text"
                      value={draft.field_mapping[alias] || ''}
                      onChange={(e) => setMapping(alias, e.target.value)}
                      placeholder="(automatisch)"
                      className="w-full text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Validierungen">
        <p className="text-[11px] text-slate-500 dark:text-slate-400 mb-3">
          Pro Regel: ein Feldname (kanonisch), ein Python-Regex und eine optionale Fehlermeldung.
        </p>
        <div className="space-y-2">
          {(draft.validations || []).map((rule, idx) => (
            <div key={idx} className="grid grid-cols-1 md:grid-cols-12 gap-2 items-center rounded-xl border border-slate-200 dark:border-slate-800 p-3">
              <input
                type="text"
                value={String(rule.field || '')}
                onChange={(e) => updateValidation(idx, 'field', e.target.value)}
                placeholder="z.B. cost_total_raw"
                className="md:col-span-3 text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <input
                type="text"
                value={String(rule.regex || '')}
                onChange={(e) => updateValidation(idx, 'regex', e.target.value)}
                placeholder="^\d"
                className="md:col-span-4 text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono"
              />
              <input
                type="text"
                value={String(rule.message || '')}
                onChange={(e) => updateValidation(idx, 'message', e.target.value)}
                placeholder="Fehler-Hinweis (optional)"
                className="md:col-span-4 text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
              />
              <button
                onClick={() => removeValidation(idx)}
                className="md:col-span-1 inline-flex items-center justify-center p-1.5 rounded text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          <button
            onClick={addValidation}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-dashed border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-900"
          >
            <Plus size={12} /> Regel hinzufügen
          </button>
        </div>
      </Section>
    </div>
  );
}

// ── Tab: Test-Run ────────────────────────────────────────────────────────────

function TestRunTab({ sourceKey }: { sourceKey: string }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<TestRunResponse | null>(null);

  const run = async () => {
    setRunning(true);
    setError('');
    setResult(null);
    try {
      const fd = new FormData();
      const f = fileRef.current?.files?.[0];
      if (f) fd.append('file', f);
      const r = await fetch(`/api/admin/beneficiary-sources/${sourceKey}/test-run`, {
        method: 'POST',
        headers: getWorkshopAuthHeaders(),
        body: fd,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setResult(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Test-Run fehlgeschlagen');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-cyan-200 bg-cyan-50/60 dark:border-cyan-900/40 dark:bg-cyan-950/20 p-4">
        <h3 className="text-sm font-semibold text-cyan-900 dark:text-cyan-100">Test-Run ohne DB-Write</h3>
        <p className="mt-1 text-xs text-cyan-800 dark:text-cyan-200">
          Liest die Datei (Upload oder konfigurierte URL), parsed sie mit dem aktuellen
          Field-Mapping und liefert eine Vorschau der ersten 10 Zeilen plus Validation-
          Findings — ohne in die zentrale Tabelle zu schreiben.
        </p>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv,.xlsm"
          className="text-xs file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:text-slate-700 dark:file:border-slate-700 dark:file:bg-slate-800 dark:file:text-slate-200" />
        <button
          onClick={run}
          disabled={running}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-50"
        >
          {running ? <Loader2 size={12} className="animate-spin" /> : <FlaskConical size={12} />}
          Test-Run starten
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Stat label="Geparst" value={result.rows_parsed.toString()} />
            <Stat label="Vorschau" value={result.preview_rows_returned.toString()} />
            <Stat label="Ohne Name" value={result.skipped_no_name.toString()} accent={result.skipped_no_name > 0 ? 'amber' : undefined} />
            <Stat label="Validation-Issues" value={result.validation_findings_count.toString()} accent={result.validation_findings_count > 0 ? 'rose' : 'emerald'} />
          </div>

          <Section title="Erkanntes Field-Mapping">
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden text-xs">
              <table className="w-full">
                <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500">
                  <tr>
                    <th className="text-left px-3 py-1.5 font-medium">Alias</th>
                    <th className="text-left px-3 py-1.5 font-medium">XLSX-Header</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.detected_field_mapping).map(([k, v]) => (
                    <tr key={k} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="px-3 py-1.5"><code>{k}</code></td>
                      <td className="px-3 py-1.5">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {result.preview.length > 0 && (
            <Section title="Vorschau (erste Zeilen)">
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-x-auto text-xs">
                <table className="w-full">
                  <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500">
                    <tr>
                      <th className="text-left px-3 py-1.5 font-medium w-16">Zeile</th>
                      <th className="text-left px-3 py-1.5 font-medium">Felder</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.preview.map((p, i) => (
                      <tr key={i} className="border-t border-slate-200 dark:border-slate-800 align-top">
                        <td className="px-3 py-1.5 text-slate-500">{p.row_number}</td>
                        <td className="px-3 py-1.5">
                          <div className="space-y-0.5">
                            {Object.entries(p.fields).map(([k, v]) => (
                              <div key={k} className="flex gap-2">
                                <code className="text-slate-500">{k}</code>
                                <span className="truncate text-slate-700 dark:text-slate-300">{String(v ?? '')}</span>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}

          {result.validation_findings.length > 0 && (
            <Section title="Validation-Findings">
              <ul className="space-y-1 text-xs">
                {result.validation_findings.map((f, i) => (
                  <li key={i} className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 dark:bg-amber-950/30 dark:border-amber-900/40">
                    <strong>Zeile {f.row_number}:</strong>{' '}
                    {f.issues.join(' · ')}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tab: Run-History ─────────────────────────────────────────────────────────

function RunHistoryTab({ sourceKey }: { sourceKey: string }) {
  const [runs, setRuns] = useState<HarvestRun[]>([]);
  // Loading-Flag startet true — vermeidet React-Lint-Warning
  // 'set-state-in-effect' und zeigt direkt einen Spinner an.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetch(`/api/admin/beneficiary-sources/${sourceKey}/runs?limit=20`, {
      headers: getWorkshopAuthHeaders(),
    })
      .then((r) => r.json())
      .then((d) => { if (mounted) setRuns(d.runs || []); })
      .catch(() => { /* ignore */ })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [sourceKey]);

  if (loading) {
    return <Loader2 className="animate-spin" />;
  }
  if (runs.length === 0) {
    return (
      <div className="text-sm text-slate-500 italic">
        Noch keine Harvest-Laeufe. Trigger den ersten manuell ueber den Tab „Konfiguration“.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {runs.map((r) => (
        <div key={r.id} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3 text-xs">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <Circle size={8} className={statusClass(r.status)} fill="currentColor" />
              <code className="text-[10px] text-slate-500">{r.id.slice(0, 8)}</code>
              <span className={`font-medium ${statusClass(r.status)}`}>{r.status}</span>
            </div>
            <div className="text-[10px] text-slate-500">
              {r.triggered_by}
            </div>
          </div>
          <div className="mt-2 grid grid-cols-4 gap-2 text-[11px]">
            <span><strong>{r.records_seen}</strong> seen</span>
            <span className="text-emerald-700 dark:text-emerald-300"><strong>{r.records_inserted}</strong> insert</span>
            <span className="text-amber-700 dark:text-amber-300"><strong>{r.records_skipped}</strong> skip</span>
            <span className="text-rose-700 dark:text-rose-300"><strong>{r.records_failed}</strong> fail</span>
          </div>
          {r.error_message && (
            <div className="mt-2 text-rose-700 dark:text-rose-300 truncate">
              {r.error_message}
            </div>
          )}
          <div className="mt-1 text-[10px] text-slate-400">
            {r.started_at ? new Date(r.started_at).toLocaleString('de-DE') : ''}
            {r.finished_at && (() => {
              const dur = (new Date(r.finished_at).getTime() - new Date(r.started_at!).getTime()) / 1000;
              return `   ·   ${dur.toFixed(1)}s`;
            })()}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Create-Modal ─────────────────────────────────────────────────────────────

function CreateSourceModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [draft, setDraft] = useState({
    source_key: '',
    display_name: '',
    bundesland: '',
    fonds: 'EFRE',
    periode: '2021-2027',
    country_code: 'DE',
    source_type: 'manual_upload' as SourceConfig['source_type'],
    source_url: '',
    source_landing_page: '',
    update_frequency_days: 30,
    license: '',
    sheet_name: '',
    header_row: 0,
    enabled: true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const slugValid = /^[a-z0-9_-]+$/.test(draft.source_key);
  const valid = draft.source_key && draft.display_name && slugValid &&
    (draft.source_type === 'manual_upload' || !!draft.source_url);

  const submit = async () => {
    setSaving(true);
    setError('');
    try {
      const payload = {
        ...draft,
        source_url: draft.source_url || null,
        source_landing_page: draft.source_landing_page || null,
        sheet_name: draft.sheet_name || null,
        license: draft.license || null,
      };
      const r = await fetch('/api/admin/beneficiary-sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
        body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      await onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Anlegen fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl bg-white dark:bg-slate-950 rounded-2xl shadow-2xl overflow-hidden"
      >
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Neue Beneficiary-Quelle</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-3 max-h-[70vh] overflow-y-auto">
          <Field label="Source-Key (slug, [a-z0-9_-])"
            value={draft.source_key}
            onChange={(v) => setDraft({ ...draft, source_key: v.toLowerCase() })}
            placeholder="hessen_efre_2021_2027" />
          {!slugValid && draft.source_key && (
            <p className="text-[11px] text-rose-600">Nur Kleinbuchstaben, Ziffern, Unter-/Bindestriche.</p>
          )}
          <Field label="Anzeigename" value={draft.display_name}
            onChange={(v) => setDraft({ ...draft, display_name: v })}
            placeholder="Hessen · EFRE · 2021-2027" />
          <Row>
            <Field label="Bundesland" value={draft.bundesland}
              onChange={(v) => setDraft({ ...draft, bundesland: v })} />
            <Field label="Fonds" value={draft.fonds}
              onChange={(v) => setDraft({ ...draft, fonds: v })} />
            <Field label="Periode" value={draft.periode}
              onChange={(v) => setDraft({ ...draft, periode: v })} />
            <Field label="Country (ISO-2)" value={draft.country_code}
              onChange={(v) => setDraft({ ...draft, country_code: v.toUpperCase() })} />
          </Row>
          <SelectField
            label="Source-Typ"
            value={draft.source_type}
            options={[
              { v: 'manual_upload', l: 'Manueller Upload' },
              { v: 'xlsx_url', l: 'XLSX-URL' },
              { v: 'csv_url', l: 'CSV-URL' },
            ]}
            onChange={(v) => setDraft({ ...draft, source_type: v as SourceConfig['source_type'] })}
          />
          {(draft.source_type === 'xlsx_url' || draft.source_type === 'csv_url') && (
            <>
              <Field label="Source-URL (Pflicht)" value={draft.source_url}
                onChange={(v) => setDraft({ ...draft, source_url: v })} />
              <Row>
                <NumberField label="Update-Frequenz (Tage)" value={draft.update_frequency_days}
                  onChange={(v) => setDraft({ ...draft, update_frequency_days: v ?? 30 })} min={1} max={3650} />
                <Field label="Sheet-Name (optional)" value={draft.sheet_name}
                  onChange={(v) => setDraft({ ...draft, sheet_name: v })} />
                <NumberField label="Header-Row" value={draft.header_row}
                  onChange={(v) => setDraft({ ...draft, header_row: v ?? 0 })} min={0} max={20} />
              </Row>
            </>
          )}

          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
              {error}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-end gap-2">
          <button onClick={onClose}
            className="px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700">
            Abbrechen
          </button>
          <button onClick={submit} disabled={!valid || saving}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-50">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            Anlegen
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Util-Components ──────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400 font-semibold">
        {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">{children}</div>
  );
}

function Field({
  label, value, onChange, placeholder,
}: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
      />
    </label>
  );
}

function NumberField({
  label, value, onChange, min, max,
}: { label: string; value: number | null; onChange: (v: number | null) => void; min?: number; max?: number }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">{label}</span>
      <input
        type="number"
        value={value ?? ''}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="w-full text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
      />
    </label>
  );
}

function SelectField({
  label, value, onChange, options,
}: { label: string; value: string; onChange: (v: string) => void; options: { v: string; l: string }[] }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
      >
        {options.map((o) => (
          <option key={o.v} value={o.v}>{o.l}</option>
        ))}
      </select>
    </label>
  );
}

function TextAreaField({
  label, value, onChange,
}: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
      />
    </label>
  );
}

function Stat({
  label, value, accent,
}: { label: string; value: string; accent?: 'emerald' | 'amber' | 'rose' | 'slate' }) {
  const tone = accent === 'emerald' ? 'text-emerald-700 dark:text-emerald-300'
    : accent === 'amber' ? 'text-amber-700 dark:text-amber-300'
    : accent === 'rose' ? 'text-rose-700 dark:text-rose-300'
    : 'text-slate-700 dark:text-slate-200';
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 px-3 py-2 bg-white/70 dark:bg-slate-900/70">
      <div className="text-[10px] uppercase tracking-wider text-slate-400 dark:text-slate-500">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold ${tone}`}>{value}</div>
    </div>
  );
}
