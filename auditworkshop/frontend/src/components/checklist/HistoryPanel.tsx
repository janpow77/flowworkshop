/**
 * flowworkshop · components/checklist/HistoryPanel.tsx
 *
 * Modal „Verlauf" fuer den Checklisten-Designer. Links eine Commit-artige Liste
 * der Knoten-Aenderungen (neueste zuerst), rechts die Diff-/Snapshot-Ansicht des
 * gewaehlten Eintrags. Wiederherstellung (Restore) nur fuer editor/owner; Leser
 * sehen den Verlauf, koennen aber nicht zuruecksetzen.
 *
 * Farbwelt Emerald/Cyan, Dark Mode. Keine zusaetzlichen Abhaengigkeiten.
 */
import { useCallback, useEffect, useState } from 'react';
import { History, Loader2, RotateCcw, X } from 'lucide-react';
import {
  getChecklistHistory, getHistoryDetail, restoreHistory,
  type HistoryDetail, type HistoryEntry,
} from '../../lib/api';
import { changeTypeMeta, formatHistoryDate } from './treeMeta';
import DiffView from './DiffView';

interface HistoryPanelProps {
  templateId: string;
  /** editor/owner — darf Restore ausloesen. */
  canRestore: boolean;
  onClose: () => void;
  /** Wird nach erfolgreichem Restore aufgerufen (Baum neu laden). */
  onRestored: (msg: string) => void;
}

const PAGE_SIZE = 50;

export default function HistoryPanel({
  templateId, canRestore, onClose, onRestored,
}: HistoryPanelProps) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [restoring, setRestoring] = useState(false);

  const loadPage = useCallback(async (offset: number) => {
    const rows = await getChecklistHistory(templateId, { limit: PAGE_SIZE, offset });
    setHasMore(rows.length === PAGE_SIZE);
    return rows;
  }, [templateId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadPage(0)
      .then((rows) => { if (!cancelled) { setEntries(rows); setError(''); } })
      .catch(() => { if (!cancelled) setError('Der Verlauf konnte nicht geladen werden.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [loadPage]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleMore = async () => {
    setLoadingMore(true);
    try {
      const rows = await loadPage(entries.length);
      setEntries((prev) => [...prev, ...rows]);
    } catch {
      setError('Weitere Einträge konnten nicht geladen werden.');
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSelect = async (entry: HistoryEntry) => {
    setSelectedId(entry.id);
    setDetail(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      const d = await getHistoryDetail(templateId, entry.id);
      setDetail(d);
    } catch {
      setDetailError('Die Detailansicht konnte nicht geladen werden.');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleRestore = async () => {
    if (!detail || !canRestore) return;
    const meta = changeTypeMeta(detail.change_type);
    if (!confirm(
      `Knoten auf den Stand „${meta.label} · v${detail.node_version}" `
      + 'zurücksetzen? Diese Wiederherstellung wird als neuer Verlaufseintrag '
      + 'protokolliert.',
    )) return;
    setRestoring(true);
    try {
      const res = await restoreHistory(templateId, detail.id);
      onRestored(
        res.status === 'recreated'
          ? 'Gelöschter Knoten wiederhergestellt.'
          : 'Knoten auf den gewählten Stand zurückgesetzt.',
      );
      // Verlaufsliste neu laden (der Restore erzeugt einen neuen Eintrag).
      const rows = await loadPage(0);
      setEntries(rows);
      setSelectedId(null);
      setDetail(null);
    } catch (e) {
      setDetailError(
        String(e).includes('403')
          ? 'Keine Berechtigung zum Wiederherstellen.'
          : 'Wiederherstellung fehlgeschlagen.',
      );
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[88vh] w-full max-w-4xl flex-col rounded-2xl bg-white shadow-xl dark:bg-slate-900">
        {/* Kopfzeile */}
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-slate-100">
            <History size={18} className="text-emerald-500" /> Verlauf
          </h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Schließen">
            <X size={18} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[300px_1fr]">
          {/* Linke Spalte: Commit-artige Liste */}
          <div className="flex min-h-0 flex-col border-b border-slate-200 md:border-b-0 md:border-r dark:border-slate-700">
            <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
              {loading ? (
                <div className="flex items-center gap-2 px-3 py-10 text-sm text-slate-400">
                  <Loader2 size={16} className="animate-spin" /> Lädt Verlauf…
                </div>
              ) : error ? (
                <div className="mx-1 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
                  {error}
                </div>
              ) : entries.length === 0 ? (
                <p className="px-3 py-10 text-center text-sm text-slate-400">
                  Noch keine Änderungen protokolliert.
                </p>
              ) : (
                <ul className="space-y-0.5">
                  {entries.map((entry) => {
                    const meta = changeTypeMeta(entry.change_type);
                    const Icon = meta.icon;
                    const active = entry.id === selectedId;
                    return (
                      <li key={entry.id}>
                        <button
                          type="button"
                          onClick={() => handleSelect(entry)}
                          className={`flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left transition-colors ${
                            active
                              ? 'bg-emerald-50 dark:bg-emerald-900/25'
                              : 'hover:bg-slate-100 dark:hover:bg-slate-800/70'
                          }`}
                        >
                          <span className={`mt-0.5 shrink-0 ${meta.accent}`}>
                            <Icon size={15} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-xs font-medium text-slate-700 dark:text-slate-200">
                              {meta.label} · v{entry.node_version}
                            </span>
                            <span className="block truncate text-[11px] text-slate-500 dark:text-slate-400">
                              {entry.changed_by_name || 'Unbekannt'} · {formatHistoryDate(entry.created_at)}
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              {!loading && !error && hasMore && (
                <button
                  type="button"
                  onClick={handleMore}
                  disabled={loadingMore}
                  className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-400 dark:hover:bg-slate-800"
                >
                  {loadingMore && <Loader2 size={13} className="animate-spin" />}
                  Weitere laden
                </button>
              )}
            </div>
          </div>

          {/* Rechte Spalte: Diff/Snapshot */}
          <div className="flex min-h-0 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              <DiffView detail={detail} loading={detailLoading} error={detailError} />
            </div>
            {detail && canRestore && (
              <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
                <button
                  type="button"
                  onClick={handleRestore}
                  disabled={restoring}
                  className="flex items-center gap-1.5 rounded-full bg-amber-600 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-amber-500 disabled:opacity-60"
                >
                  {restoring ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                  Auf diesen Stand zurücksetzen
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
