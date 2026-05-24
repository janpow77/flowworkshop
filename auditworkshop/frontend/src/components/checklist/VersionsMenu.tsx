/**
 * flowworkshop · components/checklist/VersionsMenu.tsx
 *
 * Versions-Dropdown fuer die TreeEditor-Toolbar (Ganz-Checklisten-Versionierung).
 * Zeigt die aktuelle Versionsnummer und oeffnet ein Menue mit:
 *   - „Neue Version anlegen" (Dialog: Versionsnummer + Notiz → createVersion)
 *   - „Versionen vergleichen" (oeffnet VersionDiffModal)
 *   - Liste der Versionen (Datum/Autor/Notiz, Schloss-Icon bei is_frozen) mit
 *     Aktionen „Freigeben/Einfrieren" und „Wiederherstellen" (editor/owner).
 *
 * Rollen: viewer sieht Liste/Vergleich; editor/owner darf anlegen/freigeben/
 * wiederherstellen (Schreibaktionen sonst ausgeblendet).
 *
 * Farbwelt audit_designer (BLAU primary). Dark Mode. Keine zusaetzlichen
 * Abhaengigkeiten.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle, GitBranch, Loader2, Lock, Plus, RotateCcw, ShieldCheck, X,
} from 'lucide-react';
import {
  createChecklistVersion, freezeChecklistVersion, listChecklistVersions,
  restoreChecklistVersion, type ChecklistVersion,
} from '../../lib/api';
import VersionDiffModal from './VersionDiffModal';

interface VersionsMenuProps {
  templateId: string;
  /** editor/owner — darf anlegen, einfrieren, wiederherstellen. */
  canEdit: boolean;
  /** Erfolgsmeldung (transienter Hinweis) an den TreeEditor. */
  onNotify: (msg: string) => void;
  /** Fehlermeldung (transienter Hinweis) an den TreeEditor. */
  onError: (msg: string) => void;
  /** Wird nach einer Wiederherstellung aufgerufen — Baum neu laden. */
  onRestored: () => void;
}

function formatDate(iso: string | null): string {
  if (!iso) return '–';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '–';
  return d.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function VersionsMenu({
  templateId, canEdit, onNotify, onError, onRestored,
}: VersionsMenuProps) {
  const [open, setOpen] = useState(false);
  const [versions, setVersions] = useState<ChecklistVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [showDiff, setShowDiff] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);

  // Aktuelle (neueste) Version fuer die Toolbar-Beschriftung.
  const current = versions[0] ?? null;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listChecklistVersions(templateId);
      setVersions(rows);
      setError('');
    } catch {
      setError('Die Versionen konnten nicht geladen werden.');
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [templateId]);

  // Beim ersten Oeffnen sowie sofort beim Mount (fuer die Toolbar-Beschriftung)
  // laden.
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (open && !loaded) void load();
  }, [open, loaded, load]);

  // Klick ausserhalb + Escape schliessen das Dropdown (nicht aber offene Modals).
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !showCreate && !showDiff) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open, showCreate, showDiff]);

  const handleFreeze = async (v: ChecklistVersion) => {
    if (!canEdit || v.is_frozen) return;
    if (!confirm(
      `Version „${v.version_number}" einfrieren und freigeben? `
      + 'Eine eingefrorene Version bleibt als unveränderlicher Freigabestand erhalten.',
    )) return;
    setBusyId(v.id);
    try {
      await freezeChecklistVersion(templateId, v.id);
      await load();
      onNotify(`Version „${v.version_number}" wurde freigegeben.`);
    } catch (e) {
      onError(String(e).includes('403')
        ? 'Keine Berechtigung zum Freigeben.'
        : 'Die Version konnte nicht freigegeben werden.');
    } finally {
      setBusyId(null);
    }
  };

  const handleRestore = async (v: ChecklistVersion) => {
    if (!canEdit) return;
    if (!confirm(
      `Arbeitskopie auf Version „${v.version_number}" zurücksetzen? `
      + 'Die aktuelle Arbeitskopie wird vollständig durch den Snapshot dieser '
      + 'Version ersetzt.',
    )) return;
    setBusyId(v.id);
    try {
      const res = await restoreChecklistVersion(templateId, v.id);
      setOpen(false);
      onNotify(
        `Version „${v.version_number}" wiederhergestellt — `
        + `${res.restored_node_count} Knoten geladen.`,
      );
      onRestored();
    } catch (e) {
      onError(String(e).includes('403')
        ? 'Keine Berechtigung zum Wiederherstellen.'
        : 'Die Wiederherstellung ist fehlgeschlagen.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Versionen verwalten"
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        <GitBranch size={14} />
        Versionen
        {current && (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
            {current.is_frozen && <Lock size={9} />}
            {current.version_number}
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-1.5 w-80 max-w-[92vw] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900"
        >
          {/* Aktionsleiste */}
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2.5 dark:border-slate-800">
            {canEdit && (
              <button
                type="button"
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-1.5 rounded-full bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500"
              >
                <Plus size={13} /> Neue Version
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowDiff(true)}
              disabled={versions.length < 2}
              className="flex items-center gap-1.5 rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
              title={versions.length < 2 ? 'Mindestens zwei Versionen nötig' : 'Versionen vergleichen'}
            >
              <GitBranch size={13} /> Vergleichen
            </button>
          </div>

          {/* Versionsliste */}
          <div className="max-h-80 overflow-y-auto px-2 py-2">
            {loading ? (
              <div className="flex items-center gap-2 px-2 py-6 text-sm text-slate-400">
                <Loader2 size={15} className="animate-spin" /> Lädt Versionen…
              </div>
            ) : error ? (
              <div className="mx-1 flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-400">
                <AlertCircle size={14} /> {error}
              </div>
            ) : versions.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-slate-400">
                Noch keine Versionen angelegt.
                {canEdit && ' Legen Sie oben die erste Version an.'}
              </p>
            ) : (
              <ul className="space-y-1">
                {versions.map((v) => {
                  const busy = busyId === v.id;
                  return (
                    <li
                      key={v.id}
                      className="rounded-lg border border-slate-100 px-2.5 py-2 dark:border-slate-800"
                    >
                      <div className="flex items-start gap-2">
                        <span className={`mt-0.5 shrink-0 ${v.is_frozen ? 'text-blue-500 dark:text-blue-400' : 'text-slate-300 dark:text-slate-600'}`}>
                          {v.is_frozen ? <Lock size={14} /> : <GitBranch size={14} />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">{v.version_number}</span>
                            <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                              v.status === 'released'
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                            }`}>
                              {v.status === 'released' ? 'Freigegeben' : 'Entwurf'}
                            </span>
                          </div>
                          <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                            {v.created_by_name || 'Unbekannt'} · {formatDate(v.created_at)} · {v.node_count} Knoten
                          </div>
                          {v.notes && (
                            <p className="mt-1 break-words text-[11px] italic text-slate-500 dark:text-slate-400">
                              {v.notes}
                            </p>
                          )}
                          {canEdit && (
                            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                              {!v.is_frozen && (
                                <button
                                  type="button"
                                  onClick={() => handleFreeze(v)}
                                  disabled={busy}
                                  className="inline-flex items-center gap-1 rounded-full bg-green-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-green-500 disabled:opacity-60"
                                >
                                  {busy ? <Loader2 size={11} className="animate-spin" /> : <ShieldCheck size={11} />}
                                  Freigeben
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => handleRestore(v)}
                                disabled={busy}
                                className="inline-flex items-center gap-1 rounded-full border border-amber-300 px-2.5 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-60 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-900/30"
                              >
                                {busy ? <Loader2 size={11} className="animate-spin" /> : <RotateCcw size={11} />}
                                Wiederherstellen
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}

      {showCreate && (
        <CreateVersionDialog
          existingNumbers={versions.map((v) => v.version_number)}
          suggested={versions.length === 0 ? '1.0' : ''}
          onCancel={() => setShowCreate(false)}
          onCreate={async (versionNumber, notes) => {
            await createChecklistVersion(templateId, { version_number: versionNumber, notes });
            await load();
            setShowCreate(false);
            onNotify(`Version „${versionNumber}" wurde angelegt.`);
          }}
        />
      )}

      {showDiff && versions.length >= 2 && (
        <VersionDiffModal
          templateId={templateId}
          versions={versions}
          initialVersionAId={versions[versions.length - 1].id}
          initialVersionBId={versions[0].id}
          onClose={() => setShowDiff(false)}
        />
      )}
    </div>
  );
}

// ── Dialog: Neue Version anlegen ───────────────────────────────────────────────

function CreateVersionDialog({
  existingNumbers, suggested, onCancel, onCreate,
}: {
  existingNumbers: string[];
  suggested: string;
  onCancel: () => void;
  onCreate: (versionNumber: string, notes: string | null) => Promise<void>;
}) {
  const [versionNumber, setVersionNumber] = useState(suggested);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape' && !saving) onCancel(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onCancel, saving]);

  const submit = async () => {
    const num = versionNumber.trim();
    if (!num) { setError('Bitte eine Versionsnummer eingeben.'); return; }
    if (num.length > 40) { setError('Die Versionsnummer darf höchstens 40 Zeichen lang sein.'); return; }
    if (existingNumbers.includes(num)) {
      setError(`Die Versionsnummer „${num}" existiert für diese Checkliste bereits.`);
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onCreate(num, notes.trim() || null);
    } catch (e) {
      setError(String(e).includes('409')
        ? `Die Versionsnummer „${num}" existiert bereits.`
        : 'Die Version konnte nicht angelegt werden.');
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h3 className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-slate-100">
            <Plus size={17} className="text-blue-600 dark:text-blue-400" /> Neue Version anlegen
          </h3>
          <button type="button" onClick={onCancel} disabled={saving} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800" aria-label="Schließen">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Es wird ein Snapshot der aktuellen Knoten als benannte Gesamtversion eingefroren.
          </p>
          <label className="block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">Versionsnummer</span>
            <input
              value={versionNumber}
              onChange={(e) => setVersionNumber(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void submit(); }}
              maxLength={40}
              autoFocus
              placeholder="z. B. 1.0, 2024-Q1, Freigabe März"
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">Notiz (optional)</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Was wurde in dieser Version geändert?"
              className="w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            />
          </label>
          {error && (
            <div className="flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-400">
              <AlertCircle size={14} /> {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-700">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-full px-4 py-1.5 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-full bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            Version anlegen
          </button>
        </div>
      </div>
    </div>
  );
}
