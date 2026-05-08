/**
 * AuditReportTrailPage — Auswertungs-Verlauf (Item 4, Admin-only).
 *
 * Liest den Audit-Trail aus `/api/state-aid/audit-report/log` und zeigt
 * eine filterbare Tabelle mit allen erzeugten Auswertungen. Pro Eintrag
 * stehen Aktionen bereit:
 *  - „Erneut erzeugen" — springt zu /audit-report mit q + auftraggeber
 *  - „PDF herunterladen" — triggert /audit-report/pdf neu (Backend cached
 *    ueber pdf_sha256, falls Hash bekannt)
 *  - „Details" — Modal mit allen Metadaten (User-ID, SHA256, ...)
 *
 * Pagination via Cursor (`before_id`). Backend liefert das Feld optional
 * — wir leiten es clientseitig auch aus dem kleinsten id der aktuellen
 * Seite ab, falls es nicht in der Response steht.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  ArrowDownToLine,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  FileText,
  Filter,
  Loader2,
  RefreshCw,
  ScrollText,
  Search,
  User,
  X,
} from 'lucide-react';
import {
  auditTrailExportUrl,
  downloadAuditReportPdf,
  getAuditReportLog,
  type AuditReportLogItem,
  type AuditReportLogParams,
  type AuditReportPdfParams,
} from '../lib/stateAidApi';
import ExportButtons, { type ExportFormat } from '../components/ui/ExportButtons';

const PAGE_SIZE = 25;

// Eine kleine Anzahl Pruefer-User-IDs reicht fuer den Workshop-Filter.
// In der Praxis sind das die User aus dem `users.role IN (admin, moderator)`-
// Set; wir extrahieren sie clientseitig aus den geladenen Logs, damit kein
// extra Endpoint noetig ist.

// ── Format-Helfer ────────────────────────────────────────────────────────────

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('de-DE');
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Liefert true, wenn der Eintrag nach den Filter-Werten sichtbar bleiben
 * soll. Server-seitige Filterung wird zusaetzlich genutzt; clientseitig
 * filtern wir aber redundant, damit Filter ohne Backend-Roundtrip
 * reagieren (UX).
 */
function entryMatchesFilters(
  entry: AuditReportLogItem,
  q: string,
  userId: string,
  since: string,
  until: string,
): boolean {
  if (q) {
    const needle = q.toLowerCase();
    const haystacks = [
      entry.query,
      entry.auftraggeber || '',
      entry.pruefer_name || '',
    ].map((s) => s.toLowerCase());
    if (!haystacks.some((h) => h.includes(needle))) return false;
  }
  if (userId && entry.pruefer_user_id !== userId) return false;
  if (entry.created_at) {
    const dt = new Date(entry.created_at).getTime();
    if (since) {
      const start = new Date(since).getTime();
      if (Number.isFinite(start) && dt < start) return false;
    }
    if (until) {
      // until-Datum als End-of-Day interpretieren.
      const end = new Date(`${until}T23:59:59`).getTime();
      if (Number.isFinite(end) && dt > end) return false;
    }
  }
  return true;
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AuditReportTrailPage() {
  const navigate = useNavigate();
  const isAdmin = (localStorage.getItem('workshop_role') || '') === 'admin';

  const [items, setItems] = useState<AuditReportLogItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Cursor-Stack fuer Vor/Zurueck-Navigation. Jeder Eintrag ist die
  // before_id, die zur Anzeige der jeweiligen Seite gefuehrt hat.
  const [cursorStack, setCursorStack] = useState<Array<number | null>>([null]);

  // Filter-State
  const [filterQuery, setFilterQuery] = useState<string>('');
  const [filterUserId, setFilterUserId] = useState<string>('');
  const [filterSince, setFilterSince] = useState<string>('');
  const [filterUntil, setFilterUntil] = useState<string>('');

  // Detail-Modal
  const [detailItem, setDetailItem] = useState<AuditReportLogItem | null>(null);

  // PDF-Download-Tracking
  const [pdfBusyId, setPdfBusyId] = useState<number | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const currentCursor = cursorStack[cursorStack.length - 1];

  const load = useCallback(
    async (cursor: number | null) => {
      setLoading(true);
      setError(null);
      try {
        const params: AuditReportLogParams = { limit: PAGE_SIZE };
        if (cursor !== null) params.before_id = cursor;
        if (filterQuery.trim()) params.q = filterQuery.trim();
        if (filterUserId) params.user_id = filterUserId;
        if (filterSince) params.since = filterSince;
        if (filterUntil) params.until = filterUntil;
        const data = await getAuditReportLog(params);
        setItems(data.items || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Verlauf konnte nicht geladen werden.');
        setItems([]);
      } finally {
        setLoading(false);
      }
    },
    [filterQuery, filterUserId, filterSince, filterUntil],
  );

  useEffect(() => {
    if (isAdmin) void load(currentCursor);
  }, [isAdmin, currentCursor, load]);

  // Pruefer-Dropdown-Optionen aus dem aktuellen Datensatz extrahieren.
  // Wenn der Filter aktiv ist, nehmen wir trotzdem die Original-Liste
  // (vor Client-Filterung), damit der Dropdown nicht leer wird.
  const userOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of items) {
      if (!item.pruefer_user_id) continue;
      const label = item.pruefer_name || item.pruefer_user_id;
      map.set(item.pruefer_user_id, label);
    }
    return Array.from(map.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label, 'de'));
  }, [items]);

  // Client-seitige Sicherheits-Filterung (Server filtert auch, aber wir
  // doppeln die Logik fuer UX-Reaktivitaet).
  const filteredItems = useMemo(
    () =>
      items.filter((entry) =>
        entryMatchesFilters(entry, filterQuery.trim(), filterUserId, filterSince, filterUntil),
      ),
    [items, filterQuery, filterUserId, filterSince, filterUntil],
  );

  // Cursor fuer "naechste Seite" ableiten — kleinste id der aktuellen Page.
  const nextCursor = useMemo<number | null>(() => {
    if (items.length < PAGE_SIZE) return null;
    return items.reduce<number>((acc, x) => (acc === 0 ? x.id : Math.min(acc, x.id)), 0) || null;
  }, [items]);

  function handleResetFilters() {
    setFilterQuery('');
    setFilterUserId('');
    setFilterSince('');
    setFilterUntil('');
    setCursorStack([null]);
  }

  function handleNextPage() {
    if (nextCursor === null) return;
    setCursorStack((prev) => [...prev, nextCursor]);
  }

  function handlePrevPage() {
    setCursorStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
  }

  function handleReRun(item: AuditReportLogItem) {
    const params = new URLSearchParams();
    params.set('q', item.query);
    if (item.auftraggeber) params.set('auftraggeber', item.auftraggeber);
    navigate(`/audit-report?${params.toString()}`);
  }

  async function handleDownloadPdf(item: AuditReportLogItem) {
    setPdfBusyId(item.id);
    setPdfError(null);
    try {
      const params: AuditReportPdfParams = { q: item.query };
      if (item.auftraggeber) params.auftraggeber = item.auftraggeber;
      if (item.pruefer_name) params.pruefer_name = item.pruefer_name;
      const blob = await downloadAuditReportPdf(params);
      const url = URL.createObjectURL(blob);
      try {
        const a = document.createElement('a');
        a.href = url;
        a.download = `auswertung_${item.id}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      } finally {
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : 'PDF-Download fehlgeschlagen.');
    } finally {
      setPdfBusyId(null);
    }
  }

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <div className="rounded-2xl border border-amber-300 bg-amber-50 px-6 py-5 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <h2 className="font-semibold mb-2">Nur für Admins.</h2>
          <p className="text-sm">
            Diese Seite zeigt den Auswertungs-Verlauf und ist ausschließlich für
            Administratoren zugänglich.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Hero-Card ────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(15,23,72,0.98),rgba(31,41,128,0.94)_45%,rgba(67,86,198,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-100/80">
                <ScrollText size={13} /> Audit-Trail
              </span>
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight lg:text-4xl">
              Auswertungs-Verlauf
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-indigo-50/90 lg:text-base">
              Wer hat wann welche Auswertung erzeugt — vollständige Historie aus dem
              Audit-Log.
            </p>
          </div>
          <div className="rounded-2xl border border-white/20 bg-white/10 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-indigo-100/80">
              Trail exportieren
            </div>
            <div className="mt-2">
              <ExportButtons
                formats={['csv', 'xlsx']}
                onExport={(fmt: ExportFormat) => {
                  if (fmt !== 'csv' && fmt !== 'xlsx') return;
                  const url = auditTrailExportUrl(fmt, 500);
                  const a = document.createElement('a');
                  a.href = url;
                  a.rel = 'noopener noreferrer';
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                }}
              />
            </div>
          </div>
        </div>
      </section>

      {/* ── Filter-Leiste ────────────────────────────────────────────── */}
      <section className="rounded-[30px] border border-white/70 bg-white/90 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <Filter size={14} className="text-slate-500 dark:text-slate-400" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Filter
          </span>
        </div>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
              Suchbegriff
            </span>
            <div className="relative mt-1">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={filterQuery}
                onChange={(e) => {
                  setFilterQuery(e.target.value);
                  setCursorStack([null]);
                }}
                placeholder="Firma, Auftraggeber, Prüfer…"
                className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100"
              />
            </div>
          </label>
          <label className="block">
            <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
              Prüfer
            </span>
            <select
              value={filterUserId}
              onChange={(e) => {
                setFilterUserId(e.target.value);
                setCursorStack([null]);
              }}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100"
            >
              <option value="">Alle Prüfer</option>
              {userOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
              Von (Datum)
            </span>
            <input
              type="date"
              value={filterSince}
              onChange={(e) => {
                setFilterSince(e.target.value);
                setCursorStack([null]);
              }}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
              Bis (Datum)
            </span>
            <input
              type="date"
              value={filterUntil}
              onChange={(e) => {
                setFilterUntil(e.target.value);
                setCursorStack([null]);
              }}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100"
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleResetFilters}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <X size={12} /> Filter zurücksetzen
          </button>
          <button
            type="button"
            onClick={() => void load(currentCursor)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Neu laden
          </button>
          <span className="ml-auto text-[11px] text-slate-500 dark:text-slate-400">
            {filteredItems.length} sichtbar
            {items.length !== filteredItems.length && ` (von ${items.length} geladen)`}
          </span>
        </div>
      </section>

      {/* ── Fehler-State ─────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-3 rounded-[26px] border border-rose-200 bg-rose-50/80 px-5 py-4 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-100">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Verlauf konnte nicht geladen werden.</div>
            <div className="mt-0.5 text-xs">{error}</div>
          </div>
        </div>
      )}

      {pdfError && (
        <div className="flex items-start gap-3 rounded-[26px] border border-rose-200 bg-rose-50/80 px-5 py-4 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-100">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">PDF-Download fehlgeschlagen.</div>
            <div className="mt-0.5 text-xs">{pdfError}</div>
          </div>
        </div>
      )}

      {/* ── Tabelle ───────────────────────────────────────────────────── */}
      <section className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center px-4 py-10 text-sm text-slate-500 dark:text-slate-400">
            <Loader2 size={18} className="mr-2 animate-spin" />
            Verlauf wird geladen…
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="rounded-[22px] border border-dashed border-slate-300 bg-slate-50/70 px-4 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
            <Database size={20} className="mx-auto mb-2 text-slate-400" />
            Keine Berichte für die aktuellen Filter.
          </div>
        ) : (
          <div className="overflow-hidden rounded-[22px] border border-slate-200/80 dark:border-slate-800">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500 dark:bg-slate-900/60 dark:text-slate-400">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Zeitstempel</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Prüfer</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Auftraggeber</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Suchbegriff</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">State-Aid</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Begünstigte</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Sanktionen</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Querbezüge</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Aktionen</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white text-slate-700 dark:divide-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
                  {filteredItems.map((item) => (
                    <tr
                      key={item.id}
                      className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60 dark:odd:bg-slate-950/40 dark:even:bg-slate-900/40 dark:hover:bg-slate-900/70"
                    >
                      <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-500 dark:text-slate-400">
                        {formatDateTime(item.created_at)}
                      </td>
                      <td className="px-4 py-2 text-xs">
                        {item.pruefer_name ? (
                          <div className="flex items-center gap-1">
                            <User size={11} className="text-slate-400" />
                            <span>{item.pruefer_name}</span>
                          </div>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="max-w-[180px] truncate px-4 py-2 text-xs" title={item.auftraggeber || undefined}>
                        {item.auftraggeber || '—'}
                      </td>
                      <td className="max-w-[220px] truncate px-4 py-2 font-medium" title={item.query}>
                        {item.query}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs">
                        {formatInt(item.state_aid_hits)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs">
                        {formatInt(item.beneficiaries_hits)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs">
                        {formatInt(item.sanctions_hits)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs">
                        {formatInt(item.cross_references)}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => handleReRun(item)}
                            title="Erneut erzeugen"
                            aria-label={`Bericht ${item.id} erneut erzeugen`}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:bg-indigo-50 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-200"
                          >
                            <RefreshCw size={12} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDownloadPdf(item)}
                            disabled={pdfBusyId === item.id}
                            title="PDF herunterladen"
                            aria-label={`Bericht ${item.id} als PDF herunterladen`}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:bg-indigo-50 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-200"
                          >
                            {pdfBusyId === item.id ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <ArrowDownToLine size={12} />
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={() => setDetailItem(item)}
                            title="Details"
                            aria-label={`Details zu Bericht ${item.id}`}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:bg-slate-50 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                          >
                            <Eye size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Pagination ──────────────────────────────────────────────── */}
        <div className="mt-4 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={handlePrevPage}
            disabled={cursorStack.length <= 1 || loading}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ChevronLeft size={12} /> Zurück
          </button>
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            Seite {cursorStack.length}
          </span>
          <button
            type="button"
            onClick={handleNextPage}
            disabled={nextCursor === null || loading}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Weiter <ChevronRight size={12} />
          </button>
        </div>
      </section>

      {/* ── Hinweis ──────────────────────────────────────────────────── */}
      <p className="text-[11px] leading-5 text-slate-500 dark:text-slate-400">
        Backend liefert nur Metadaten — keine PDFs werden gespeichert. Beim Klick auf
        „PDF herunterladen" wird die Auswertung aus den aktuellen Quellen neu aggregiert.
        {' '}
        <Link to="/audit-report" className="text-indigo-700 underline hover:text-indigo-900 dark:text-indigo-300 dark:hover:text-indigo-100">
          Neue Auswertung erstellen
        </Link>
      </p>

      {/* ── Detail-Modal ────────────────────────────────────────────── */}
      {detailItem && <DetailModal item={detailItem} onClose={() => setDetailItem(null)} />}
    </div>
  );
}

// ── Detail-Modal ─────────────────────────────────────────────────────────────

function DetailModal({
  item,
  onClose,
}: {
  item: AuditReportLogItem;
  onClose: () => void;
}) {
  // Esc schliesst das Modal — wie im AdminBeneficiarySourcesPage-Drawer.
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-950"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              Bericht-Details (#{item.id})
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Modal schließen"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto p-6">
          <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
            <DetailRow label="Erzeugt" value={formatDateTime(item.created_at)} mono />
            <DetailRow label="Suchbegriff" value={item.query} />
            <DetailRow label="Auftraggeber" value={item.auftraggeber || '—'} />
            <DetailRow label="Prüfer-Name" value={item.pruefer_name || '—'} />
            <DetailRow label="Prüfer-User-ID" value={item.pruefer_user_id || '—'} mono />
            <DetailRow label="State-Aid-Treffer" value={formatInt(item.state_aid_hits)} mono />
            <DetailRow label="Begünstigten-Treffer" value={formatInt(item.beneficiaries_hits)} mono />
            <DetailRow label="Sanktions-Treffer" value={formatInt(item.sanctions_hits)} mono />
            <DetailRow label="Querbezüge" value={formatInt(item.cross_references)} mono />
            <DetailRow label="PDF-Größe" value={formatBytes(item.pdf_size_bytes)} mono />
            <DetailRow label="PDF-SHA256" value={item.pdf_sha256 || '—'} mono breakAll />
          </dl>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-6 py-4 dark:border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Schließen
          </button>
        </div>
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono = false,
  breakAll = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  breakAll?: boolean;
}) {
  return (
    <>
      <dt className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</dt>
      <dd
        className={`text-sm text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-xs' : ''} ${
          breakAll ? 'break-all' : ''
        }`}
      >
        {value}
      </dd>
    </>
  );
}
