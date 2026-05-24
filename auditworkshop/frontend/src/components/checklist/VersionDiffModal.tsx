/**
 * flowworkshop · components/checklist/VersionDiffModal.tsx
 *
 * Modal zum Vergleich zweier Gesamtversionen einer Checkliste (field-level Diff).
 * Vorbild: audit_designer components/editor/TreeVersionDiffModal.vue.
 *
 * Aufbau:
 *  - Kopf mit zwei Versions-Selects (A=alt/links, B=neu/rechts) + Tausch-Button.
 *  - Summary-Leiste: +hinzugefuegt (gruen) / −entfernt (rot) / ~geaendert (amber)
 *    / unveraendert (grau).
 *  - Tabs „Geaendert / Hinzugefuegt / Entfernt" mit Count-Badges.
 *  - Geaenderte Knoten sind aufklappbar → Feld-Diff zweispaltig Side-by-Side
 *    (links alt rot, rechts neu gruen, deutsche Feld-Labels).
 *
 * Farbwelt audit_designer (BLAU primary, violet=DECISION). Dark Mode. Keine
 * zusaetzlichen Abhaengigkeiten.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeftRight, ChevronDown, ChevronRight, GitCompare, Loader2,
  Minus, Pencil, Plus, X,
} from 'lucide-react';
import {
  compareChecklistVersions,
  type ChecklistVersion, type VersionDiff, type VersionDiffChangedNode,
  type VersionDiffNodeBrief,
} from '../../lib/api';
import { FIELD_LABELS, NODE_TYPE_META } from './treeMeta';
import type { NodeType } from '../../lib/api';

interface VersionDiffModalProps {
  templateId: string;
  versions: ChecklistVersion[];
  /** Vorausgewaehlte Version A (alt). */
  initialVersionAId?: string | null;
  /** Vorausgewaehlte Version B (neu). */
  initialVersionBId?: string | null;
  onClose: () => void;
}

type DiffTab = 'changed' | 'added' | 'removed';

/** Menschenlesbare Darstellung eines (ggf. komplexen) Feldwerts. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '(leer)';
  if (typeof value === 'boolean') return value ? 'ja' : 'nein';
  if (Array.isArray(value)) {
    if (value.length === 0) return '(leer)';
    return value.map((v, i) => `${i + 1}. ${formatValue(v)}`).join('\n');
  }
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

/** Knotentyp-Label (faellt auf den Rohwert zurueck). */
function nodeTypeLabel(raw: string | null): string {
  if (!raw) return '';
  const meta = NODE_TYPE_META[raw as NodeType];
  return meta ? meta.label : raw;
}

/** Versions-Auswahl: Versionsnummer + Datum + Knotenanzahl als Option-Label. */
function versionOptionLabel(v: ChecklistVersion): string {
  const date = v.created_at
    ? new Date(v.created_at).toLocaleDateString('de-DE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
    })
    : '–';
  return `${v.version_number} · ${date} · ${v.node_count} Knoten`;
}

export default function VersionDiffModal({
  templateId, versions, initialVersionAId, initialVersionBId, onClose,
}: VersionDiffModalProps) {
  // Vorauswahl: A = aelteste angebotene, B = neueste — oder die uebergebenen IDs.
  const [versionAId, setVersionAId] = useState<string>(() => {
    if (initialVersionAId) return initialVersionAId;
    return versions.length ? versions[versions.length - 1].id : '';
  });
  const [versionBId, setVersionBId] = useState<string>(() => {
    if (initialVersionBId) return initialVersionBId;
    return versions.length ? versions[0].id : '';
  });

  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<DiffTab>('changed');
  const [openNodes, setOpenNodes] = useState<Set<string>>(new Set());

  // Escape schliesst das Modal.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // Diff laden, sobald beide Versionen gewaehlt und verschieden sind. Saemtliche
  // Zustands-Updates erfolgen in Promise-Callbacks (kein synchrones setState im
  // Effekt-Koerper) — auch der Ungueltig-Fall wird ueber ``Promise.resolve``
  // asynchron gesetzt.
  useEffect(() => {
    let cancelled = false;
    const samePair = versionAId === versionBId;
    if (!versionAId || !versionBId || samePair) {
      void Promise.resolve().then(() => {
        if (cancelled) return;
        setDiff(null);
        setLoading(false);
        setError(samePair ? 'Bitte zwei unterschiedliche Versionen wählen.' : '');
      });
      return () => { cancelled = true; };
    }
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setLoading(true);
      setError('');
      setOpenNodes(new Set());
    });
    compareChecklistVersions(templateId, versionAId, versionBId)
      .then((d) => {
        if (cancelled) return;
        setDiff(d);
        // Auf den ersten nicht-leeren Tab springen.
        if (d.summary.changed > 0) setTab('changed');
        else if (d.summary.added > 0) setTab('added');
        else if (d.summary.removed > 0) setTab('removed');
        else setTab('changed');
      })
      .catch(() => { if (!cancelled) setError('Der Versionsvergleich konnte nicht geladen werden.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [templateId, versionAId, versionBId]);

  const swap = () => {
    setVersionAId(versionBId);
    setVersionBId(versionAId);
  };

  const toggleNode = (nodeId: string) => {
    setOpenNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId); else next.add(nodeId);
      return next;
    });
  };

  const summary = diff?.summary;
  const tabItems: Array<{ key: DiffTab; label: string; count: number; dot: string }> = useMemo(() => [
    { key: 'changed', label: 'Geändert', count: summary?.changed ?? 0, dot: 'bg-amber-500' },
    { key: 'added', label: 'Hinzugefügt', count: summary?.added ?? 0, dot: 'bg-green-500' },
    { key: 'removed', label: 'Entfernt', count: summary?.removed ?? 0, dot: 'bg-red-500' },
  ], [summary]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-2xl bg-white shadow-xl dark:bg-slate-900">
        {/* Kopfzeile */}
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-slate-100">
            <GitCompare size={18} className="text-blue-600 dark:text-blue-400" /> Versionen vergleichen
          </h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Schließen">
            <X size={18} />
          </button>
        </div>

        {/* Versions-Selects + Tausch */}
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <label className="flex min-w-[180px] flex-1 flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">Version A (alt)</span>
            <select
              value={versionAId}
              onChange={(e) => setVersionAId(e.target.value)}
              aria-label="Version A (alt)"
              className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>{versionOptionLabel(v)}</option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={swap}
            title="Versionen tauschen"
            aria-label="Versionen tauschen"
            className="mb-0.5 shrink-0 rounded-lg border border-slate-300 p-2 text-slate-500 transition-colors hover:bg-blue-50 hover:text-blue-600 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-blue-900/30 dark:hover:text-blue-300"
          >
            <ArrowLeftRight size={16} />
          </button>

          <label className="flex min-w-[180px] flex-1 flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">Version B (neu)</span>
            <select
              value={versionBId}
              onChange={(e) => setVersionBId(e.target.value)}
              aria-label="Version B (neu)"
              className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>{versionOptionLabel(v)}</option>
              ))}
            </select>
          </label>
        </div>

        {/* Summary-Leiste */}
        {summary && (
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-5 py-3 text-xs dark:border-slate-700">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-1 font-medium text-green-700 dark:bg-green-900/30 dark:text-green-300">
              <Plus size={12} /> {summary.added} hinzugefügt
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-red-100 px-2.5 py-1 font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300">
              <Minus size={12} /> {summary.removed} entfernt
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
              <Pencil size={12} /> {summary.changed} geändert
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {summary.unchanged} unverändert
            </span>
          </div>
        )}

        {/* Tabs */}
        {diff && !loading && !error && (
          <div className="flex items-center gap-1 border-b border-slate-200 px-5 pt-2 dark:border-slate-700">
            {tabItems.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`-mb-px flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
                  tab === t.key
                    ? 'border-blue-500 font-medium text-blue-700 dark:border-blue-400 dark:text-blue-300'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${t.dot}`} aria-hidden="true" />
                {t.label}
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums ${
                  tab === t.key
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                }`}>
                  {t.count}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Inhalt */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex items-center gap-2 px-1 py-10 text-sm text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Lädt Vergleich…
            </div>
          ) : error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
              {error}
            </div>
          ) : !diff ? (
            <div className="px-1 py-10 text-center text-sm text-slate-400">
              Wählen Sie zwei Versionen, um sie zu vergleichen.
            </div>
          ) : tab === 'changed' ? (
            <ChangedList
              nodes={diff.changed}
              openNodes={openNodes}
              onToggle={toggleNode}
            />
          ) : tab === 'added' ? (
            <BriefList nodes={diff.added} accent="added" />
          ) : (
            <BriefList nodes={diff.removed} accent="removed" />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Geaenderte Knoten (aufklappbar, Side-by-Side-Feld-Diff) ────────────────────

function ChangedList({
  nodes, openNodes, onToggle,
}: {
  nodes: VersionDiffChangedNode[];
  openNodes: Set<string>;
  onToggle: (nodeId: string) => void;
}) {
  if (nodes.length === 0) {
    return <p className="px-1 py-10 text-center text-sm text-slate-400">Keine geänderten Knoten.</p>;
  }
  return (
    <ul className="space-y-2">
      {nodes.map((node) => {
        const open = openNodes.has(node.node_id);
        const fieldEntries = Object.entries(node.fields);
        return (
          <li key={node.node_id} className="overflow-hidden rounded-lg border border-amber-200 dark:border-amber-900/50">
            <button
              type="button"
              onClick={() => onToggle(node.node_id)}
              className="flex w-full items-center gap-2 bg-amber-50/70 px-3 py-2 text-left transition-colors hover:bg-amber-100/70 dark:bg-amber-900/15 dark:hover:bg-amber-900/25"
              aria-expanded={open}
            >
              {open ? <ChevronDown size={15} className="shrink-0 text-amber-600 dark:text-amber-400" /> : <ChevronRight size={15} className="shrink-0 text-amber-600 dark:text-amber-400" />}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-slate-700 dark:text-slate-200">
                  {node.title || '(ohne Titel)'}
                </span>
                <span className="block text-[11px] text-slate-500 dark:text-slate-400">
                  {nodeTypeLabel(node.node_type)} · {fieldEntries.length} {fieldEntries.length === 1 ? 'Feld geändert' : 'Felder geändert'}
                </span>
              </span>
            </button>
            {open && (
              <div className="overflow-hidden border-t border-amber-200 dark:border-amber-900/50">
                <div className="grid grid-cols-[minmax(90px,1fr)_1fr_1fr] bg-slate-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  <span>Feld</span>
                  <span>Version A (alt)</span>
                  <span>Version B (neu)</span>
                </div>
                {fieldEntries.map(([field, change]) => (
                  <div
                    key={field}
                    className="grid grid-cols-[minmax(90px,1fr)_1fr_1fr] items-stretch border-t border-slate-100 text-xs dark:border-slate-800"
                  >
                    <div className="px-3 py-2 font-medium text-slate-600 dark:text-slate-300">
                      {fieldLabel(field)}
                    </div>
                    <div className="border-l border-slate-100 bg-red-50/50 px-3 py-2 text-red-800 dark:border-slate-800 dark:bg-red-900/10 dark:text-red-300">
                      <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-sans">{formatValue(change.old)}</pre>
                    </div>
                    <div className="border-l border-slate-100 bg-green-50/60 px-3 py-2 text-green-800 dark:border-slate-800 dark:bg-green-900/15 dark:text-green-300">
                      <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-sans">{formatValue(change.new)}</pre>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ── Hinzugefuegte / entfernte Knoten (flache Liste) ────────────────────────────

function BriefList({
  nodes, accent,
}: { nodes: VersionDiffNodeBrief[]; accent: 'added' | 'removed' }) {
  if (nodes.length === 0) {
    return (
      <p className="px-1 py-10 text-center text-sm text-slate-400">
        {accent === 'added' ? 'Keine hinzugefügten Knoten.' : 'Keine entfernten Knoten.'}
      </p>
    );
  }
  const cls = accent === 'added'
    ? 'border-green-200 bg-green-50/60 dark:border-green-900/50 dark:bg-green-900/15'
    : 'border-red-200 bg-red-50/60 dark:border-red-900/50 dark:bg-red-900/15';
  const iconCls = accent === 'added'
    ? 'text-green-600 dark:text-green-400'
    : 'text-red-600 dark:text-red-400';
  const Icon = accent === 'added' ? Plus : Minus;
  return (
    <ul className="space-y-1.5">
      {nodes.map((node) => (
        <li key={node.node_id} className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${cls}`}>
          <Icon size={14} className={`shrink-0 ${iconCls}`} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-slate-700 dark:text-slate-200">
              {node.title || '(ohne Titel)'}
            </span>
            <span className="block text-[11px] text-slate-500 dark:text-slate-400">
              {nodeTypeLabel(node.node_type)}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
