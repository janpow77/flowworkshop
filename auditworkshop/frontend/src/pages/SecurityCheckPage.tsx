/**
 * SecurityCheckPage — Webseiten-Sicherheitsprüfung (KA 6 — ISMS-Systemprüfung).
 *
 * Nicht-intrusive technische Prüfung der von außen erreichbaren Konfiguration
 * einer Webseite nach IT-Grundschutz (TLS/TR-02102-2, Sicherheitsheader/APP.3.1,
 * HTTPS-Erzwingung & offene Ports/NET.3.3, Versions-/CVE-Indikation).
 *
 * Ablauf:
 *  1. URL eingeben + Pflicht-Berechtigungs-Checkbox bestätigen.
 *  2. `startSecurityScan` → `scan_id`. Danach alle 2 s `getSecurityScanStatus`
 *     pollen, bis `completed`/`failed` — mit Live-Fortschritt und Ampel-Zählern.
 *  3. Bei `completed`: vollständigen `getSecurityScanReport` laden und rendern
 *     (Kopf, Gesamt-Ampel, Zähler, Einzelbefunde gruppiert, Screenshot,
 *     Architektur-Diagramm, PDF-Download).
 *
 * Wichtige Designvorgaben:
 *  - Berechtigung ist Pflicht: „Scan starten" bleibt deaktiviert, solange die
 *    Checkbox nicht angehakt ist (Backend gibt sonst 403 zurück).
 *  - Screenshot/Architektur-Endpunkte sind session-geschützt. Ein
 *    `<img src="/api/…">` würde den Bearer-Header NICHT mitsenden, daher
 *    laden wir die Bilder per fetch als Blob → ObjectURL.
 *  - ObjectURLs werden sauber per `URL.revokeObjectURL` aufgeräumt.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import {
  AlertTriangle,
  ArrowDownToLine,
  CheckCircle2,
  ExternalLink,
  Globe,
  Image as ImageIcon,
  Loader2,
  Network,
  RefreshCcw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import {
  downloadSecurityScanPdf,
  fetchSecurityScanImage,
  getSecurityScanReport,
  getSecurityScanStatus,
  startSecurityScan,
  type SecurityFinding,
  type SecurityOverall,
  type SecurityRating,
  type SecurityScanReport,
  type SecurityScanStatus,
} from '../lib/api';

// Poll-Intervall für den Status (in ms).
const POLL_INTERVAL_MS = 2000;

const EXAMPLE_URLS = [
  'https://www.efre-hessen.de',
  'https://www.bund.de',
  'https://example.com',
];

// ── Ampel-Stil (emerald=konform, amber=gelb, rose=rot, slate=grau) ───────────
// Spiegelt die Badge-Logik aus components/state_aid/AuditReportPreview.tsx.

const RATING_BADGE: Record<SecurityRating, string> = {
  konform: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  gelb: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  rot: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
  grau: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
};

const RATING_DOT: Record<SecurityRating, string> = {
  konform: 'bg-emerald-500',
  gelb: 'bg-amber-500',
  rot: 'bg-rose-500',
  grau: 'bg-slate-400',
};

// Gesamt-Ampel: das Backend liefert „kritisch" statt „rot".
const OVERALL_BADGE: Record<SecurityOverall, string> = {
  konform: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-500/30',
  gelb: 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:ring-amber-500/30',
  kritisch: 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:ring-rose-500/30',
};

const OVERALL_LABEL: Record<SecurityOverall, string> = {
  konform: 'Konform',
  gelb: 'Eingeschränkt konform',
  kritisch: 'Kritisch',
};

const PFLICHT_TEXT =
  'Ich bestätige, dass ich zur technischen Sicherheitsprüfung dieser Webseite ' +
  'berechtigt bin bzw. die ausdrückliche Einwilligung des Betreibers vorliegt. ' +
  'Die Prüfung ist nicht-intrusiv.';

// ── Format-Helfer ────────────────────────────────────────────────────────────

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('de-DE', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function safeFilenamePart(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60);
}

function buildPdfFilename(host: string | null, url: string): string {
  const part = safeFilenamePart(host || url) || 'sicherheitspruefung';
  return `sicherheitspruefung_${part}.pdf`;
}

export default function SecurityCheckPage() {
  const [url, setUrl] = useState<string>('');
  const [authorized, setAuthorized] = useState<boolean>(false);

  const [scanId, setScanId] = useState<string | null>(null);
  const [status, setStatus] = useState<SecurityScanStatus | null>(null);
  const [report, setReport] = useState<SecurityScanReport | null>(null);

  const [starting, setStarting] = useState<boolean>(false);
  const [polling, setPolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [pdfBusy, setPdfBusy] = useState<boolean>(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  // Auth-geladene Bilder als ObjectURL (Bearer-Header nötig).
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [architectureUrl, setArchitectureUrl] = useState<string | null>(null);

  // Poll-Timer-Referenz, damit wir ihn sicher abräumen können.
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Flag, das ein noch laufendes Polling nach Reset/Unmount stoppt.
  const activeScanRef = useRef<string | null>(null);

  const isRunning = starting || polling;

  /** Stoppt das laufende Polling und löscht den Timer. */
  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
    activeScanRef.current = null;
    setPolling(false);
  }, []);

  /** Gibt evtl. erzeugte Bild-ObjectURLs frei (Leak-Schutz). */
  const revokeImages = useCallback(() => {
    setScreenshotUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setArchitectureUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, []);

  // Beim Unmount aufräumen: Polling stoppen + ObjectURLs freigeben.
  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
      activeScanRef.current = null;
      // Direkt freigeben — die State-Closure hält die letzten URLs.
      setScreenshotUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setArchitectureUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, []);

  /**
   * Lädt nach Abschluss den vollständigen Bericht + die Auth-geschützten
   * Bilder. Bilder werden per fetch als Blob geholt und als ObjectURL
   * eingebunden (img-Tags senden keinen Authorization-Header).
   */
  const loadReportAndImages = useCallback(
    async (id: string, st: SecurityScanStatus) => {
      try {
        const data = await getSecurityScanReport(id);
        if (activeScanRef.current !== id && activeScanRef.current !== null) {
          // Zwischenzeitlich neuer Scan gestartet — Ergebnis verwerfen.
          return;
        }
        setReport(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Bericht konnte nicht geladen werden.');
        return;
      }

      // Bilder nur laden, wenn der Status sie ankündigt.
      if (st.has_screenshot) {
        try {
          const blob = await fetchSecurityScanImage(id, 'screenshot');
          const objectUrl = URL.createObjectURL(blob);
          setScreenshotUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return objectUrl;
          });
        } catch {
          // Screenshot ist optional — Fehler hier nicht eskalieren.
        }
      }
      if (st.has_architecture) {
        try {
          const blob = await fetchSecurityScanImage(id, 'architecture');
          const objectUrl = URL.createObjectURL(blob);
          setArchitectureUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return objectUrl;
          });
        } catch {
          // Architektur-Diagramm ist optional.
        }
      }
    },
    [],
  );

  /**
   * Pollt einmal den Status und plant — solange der Scan läuft — den
   * nächsten Tick. Bei `completed` wird der Bericht geladen, bei `failed`
   * eine Fehlermeldung gesetzt.
   */
  const pollOnce = useCallback(
    async (id: string) => {
      if (activeScanRef.current !== id) return;
      try {
        const st = await getSecurityScanStatus(id);
        if (activeScanRef.current !== id) return;
        setStatus(st);

        if (st.status === 'completed') {
          stopPolling();
          await loadReportAndImages(id, st);
          return;
        }
        if (st.status === 'failed') {
          stopPolling();
          setError(st.error || 'Die Prüfung ist fehlgeschlagen.');
          return;
        }
        // pending / running → nächster Tick.
        pollTimer.current = setTimeout(() => { void pollOnce(id); }, POLL_INTERVAL_MS);
      } catch (err) {
        // Netzwerkfehler: einmal mehr versuchen statt sofort abbrechen.
        if (activeScanRef.current !== id) return;
        setError(err instanceof Error ? err.message : 'Status konnte nicht abgerufen werden.');
        stopPolling();
      }
    },
    [loadReportAndImages, stopPolling],
  );

  async function runScan(targetUrl: string): Promise<void> {
    const trimmed = targetUrl.trim();
    if (!trimmed) {
      setError('Bitte eine URL eingeben.');
      return;
    }
    if (!authorized) {
      setError('Bitte zuerst die Berechtigung bestätigen.');
      return;
    }

    // Vorherigen Lauf vollständig zurücksetzen.
    stopPolling();
    revokeImages();
    setError(null);
    setPdfError(null);
    setReport(null);
    setStatus(null);
    setScanId(null);
    setStarting(true);

    try {
      const res = await startSecurityScan(trimmed, true);
      setScanId(res.scan_id);
      activeScanRef.current = res.scan_id;
      setStatus({
        scan_id: res.scan_id,
        status: res.status,
        url: trimmed,
        host: null,
        started_at: null,
        finished_at: null,
        overall: null,
        counts: { konform: 0, gelb: 0, rot: 0, grau: 0 },
        has_screenshot: false,
        has_architecture: false,
        error: null,
      });
      setPolling(true);
      // Erstes Poll leicht verzögern, damit das Backend den Job angelegt hat.
      pollTimer.current = setTimeout(() => { void pollOnce(res.scan_id); }, POLL_INTERVAL_MS);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.startsWith('403')) {
        setError('Die Prüfung wurde abgelehnt — die Berechtigung muss bestätigt sein.');
      } else if (message.startsWith('429')) {
        setError('Zu viele Anfragen (Rate-Limit). Bitte später erneut versuchen.');
      } else {
        setError(message);
      }
      activeScanRef.current = null;
    } finally {
      setStarting(false);
    }
  }

  function handleSubmit(e: FormEvent): void {
    e.preventDefault();
    void runScan(url);
  }

  function handleReset(): void {
    stopPolling();
    revokeImages();
    setUrl('');
    setAuthorized(false);
    setScanId(null);
    setStatus(null);
    setReport(null);
    setError(null);
    setPdfError(null);
  }

  async function handlePdfDownload(): Promise<void> {
    if (!scanId) return;
    setPdfBusy(true);
    setPdfError(null);
    try {
      const blob = await downloadSecurityScanPdf(scanId);
      const objectUrl = URL.createObjectURL(blob);
      try {
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = buildPdfFilename(report?.host ?? status?.host ?? null, report?.url ?? url);
        document.body.appendChild(a);
        a.click();
        a.remove();
      } finally {
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      }
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : 'PDF-Download fehlgeschlagen.');
    } finally {
      setPdfBusy(false);
    }
  }

  // Befunde gruppiert nach `gruppe` (Reihenfolge des ersten Auftretens).
  const groupedFindings = useMemo<Array<{ gruppe: string; findings: SecurityFinding[] }>>(() => {
    if (!report?.findings?.length) return [];
    const order: string[] = [];
    const map = new Map<string, SecurityFinding[]>();
    for (const f of report.findings) {
      const key = f.gruppe || 'Sonstige';
      if (!map.has(key)) {
        map.set(key, []);
        order.push(key);
      }
      map.get(key)!.push(f);
    }
    return order.map((gruppe) => ({ gruppe, findings: map.get(gruppe)! }));
  }, [report]);

  const counts = status?.counts ?? report?.counts ?? null;
  const overall = report?.overall ?? status?.overall ?? null;

  return (
    <div className="space-y-6">
      {/* ── Hero-Sektion ──────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(8,47,73,0.98),rgba(14,86,114,0.94)_45%,rgba(34,138,167,0.85))] px-7 py-9 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.95)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),rgba(255,255,255,0)_38%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-100/80">
                <ShieldCheck size={13} /> KA 6 — ISMS-Systemprüfung
              </span>
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight lg:text-4xl">
              Webseiten-Sicherheitsprüfung
            </h1>
            <div className="mt-5 inline-flex max-w-2xl items-start gap-2.5 rounded-[22px] border border-white/15 bg-white/10 px-4 py-3 text-xs leading-5 text-cyan-50/90 backdrop-blur-sm">
              <Sparkles size={14} className="mt-0.5 shrink-0 text-cyan-200" />
              <span>
                Nicht-intrusive technische Prüfung der von außen erreichbaren Konfiguration nach
                IT-Grundschutz — TLS (TR-02102-2), Sicherheitsheader (APP.3.1), HTTPS-Erzwingung
                und offene Ports (NET.3.3). Ersetzt keine vollständige Grundschutz-Prüfung (BSI 200-2).
              </span>
            </div>
          </div>
          <div className="rounded-[28px] border border-white/15 bg-black/15 p-5 backdrop-blur">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/60">Ampel-Übersicht</div>
            <div className="mt-3 grid grid-cols-4 gap-2 text-center">
              <Stat label="Konform" value={counts ? counts.konform : '—'} tone="emerald" />
              <Stat label="Gelb" value={counts ? counts.gelb : '—'} tone="amber" />
              <Stat label="Rot" value={counts ? counts.rot : '—'} tone="rose" />
              <Stat label="Grau" value={counts ? counts.grau : '—'} tone="slate" />
            </div>
            <div className="mt-4 flex items-center justify-between text-[11px] text-white/70">
              <span>Gesamtbewertung</span>
              {overall ? (
                <span className="font-semibold text-white">{OVERALL_LABEL[overall]}</span>
              ) : (
                <span className="font-mono">—</span>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Eingabe-Card ─────────────────────────────────────────────── */}
      <form
        onSubmit={handleSubmit}
        className="rounded-[30px] border border-white/70 bg-white/90 p-6 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80"
      >
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Webseiten-URL
          </span>
          <div className="relative mt-1.5">
            <Globe size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              inputMode="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.beispiel-behörde.de"
              required
              className="w-full rounded-[20px] border border-slate-200 bg-white py-3 pl-11 pr-4 text-sm text-slate-900 shadow-sm outline-none transition focus:border-cyan-400 focus:ring-2 focus:ring-cyan-200 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100 dark:focus:border-cyan-500 dark:focus:ring-cyan-500/30"
            />
          </div>
        </label>

        {/* ── Pflicht-Berechtigungs-Checkbox ─────────────────────────── */}
        <div className="mt-5 rounded-[24px] border border-cyan-200/70 bg-cyan-50/50 p-4 dark:border-cyan-500/30 dark:bg-cyan-950/20">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={authorized}
              onChange={(e) => setAuthorized(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-cyan-300 text-cyan-600 focus:ring-cyan-500"
              aria-describedby="websec-auth-hint"
            />
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <ShieldAlert size={14} className="text-cyan-700 dark:text-cyan-300" />
                <span className="text-sm font-semibold text-cyan-900 dark:text-cyan-100">
                  Berechtigung bestätigen (erforderlich)
                </span>
              </div>
              <p id="websec-auth-hint" className="mt-1 text-xs leading-5 text-cyan-800/85 dark:text-cyan-200/85">
                {PFLICHT_TEXT}
              </p>
            </div>
          </label>
        </div>

        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Die Prüfung greift ausschließlich öffentlich erreichbare Endpunkte ab und führt keine
            aktiven Angriffe oder Lasttests durch.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="submit"
              disabled={isRunning || !authorized || !url.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-cyan-600 px-6 py-3 text-sm font-medium text-white shadow-md shadow-cyan-600/30 transition hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isRunning ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
              Scan starten
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <RefreshCcw size={12} /> Zurücksetzen
            </button>
          </div>
        </div>
      </form>

      {/* ── Fehler-State ─────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-3 rounded-[26px] border border-rose-200 bg-rose-50/80 px-5 py-4 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-950/40 dark:text-rose-100">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Prüfung nicht möglich.</div>
            <div className="mt-0.5 text-xs">{error}</div>
          </div>
        </div>
      )}

      {/* ── Live-Fortschritt (während Polling) ───────────────────────── */}
      {isRunning && !report && (
        <section className="rounded-[30px] border border-cyan-200/70 bg-cyan-50/50 px-6 py-7 dark:border-cyan-500/30 dark:bg-cyan-950/25">
          <div className="flex items-start gap-3">
            <Loader2 size={20} className="mt-0.5 shrink-0 animate-spin text-cyan-700 dark:text-cyan-300" />
            <div className="flex-1">
              <div className="text-sm font-semibold text-cyan-900 dark:text-cyan-100">
                {status?.status === 'pending'
                  ? 'Prüfung wird vorbereitet …'
                  : 'Prüfung läuft — Konfiguration wird analysiert …'}
              </div>
              <p className="mt-1 text-xs leading-5 text-cyan-800/85 dark:text-cyan-200/85">
                {status?.url || url}
                {scanId && (
                  <span className="ml-2 font-mono text-[11px] text-cyan-700/70 dark:text-cyan-300/70">
                    #{scanId.slice(0, 8)}
                  </span>
                )}
              </p>
            </div>
          </div>
          {counts && (
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <CountTile label="Konform" value={counts.konform} rating="konform" />
              <CountTile label="Gelb" value={counts.gelb} rating="gelb" />
              <CountTile label="Rot" value={counts.rot} rating="rot" />
              <CountTile label="Grau" value={counts.grau} rating="grau" />
            </div>
          )}
        </section>
      )}

      {/* ── Bericht ──────────────────────────────────────────────────── */}
      {report && !isRunning && (
        <ReportView
          report={report}
          screenshotUrl={screenshotUrl}
          architectureUrl={architectureUrl}
          groupedFindings={groupedFindings}
        />
      )}

      {/* ── Empty-State (vor erstem Scan) ────────────────────────────── */}
      {!report && !isRunning && !error && (
        <section className="rounded-[30px] border border-dashed border-slate-300 bg-white/80 px-6 py-10 text-center shadow-sm dark:border-slate-700 dark:bg-slate-900/60">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">
            <ShieldCheck size={24} />
          </div>
          <h2 className="mt-4 text-base font-semibold text-slate-900 dark:text-white">
            URL eingeben und Berechtigung bestätigen, um die Prüfung zu starten
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500 dark:text-slate-400">
            Die Prüfung ist nicht-intrusiv und liefert einen Befundbericht mit Soll/Ist-Abgleich
            und Empfehlungen. Eine fachliche Bewertung trifft der Prüfer.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {EXAMPLE_URLS.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => setUrl(example)}
                className="inline-flex items-center gap-1.5 rounded-full border border-cyan-200 bg-cyan-50/70 px-3 py-1.5 text-xs font-medium text-cyan-700 transition hover:bg-cyan-100 dark:border-cyan-500/30 dark:bg-cyan-950/40 dark:text-cyan-200 dark:hover:bg-cyan-950/70"
              >
                <Globe size={12} /> {example}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* ── Sticky PDF-Footer ────────────────────────────────────────── */}
      {report && (
        <div className="sticky bottom-4 z-20">
          <div className="mx-auto rounded-[26px] border border-white/70 bg-white/95 p-4 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.5)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="max-w-xl text-xs leading-5 text-slate-500 dark:text-slate-400">
                Der Befundbericht dokumentiert die von außen erreichbare Konfiguration. Er ersetzt
                keine vollständige Grundschutz-Prüfung (BSI 200-2); die abschließende Beurteilung
                obliegt dem Prüfer.
              </p>
              <div className="flex flex-col items-end gap-1">
                <button
                  type="button"
                  onClick={() => { void handlePdfDownload(); }}
                  disabled={pdfBusy}
                  className="inline-flex items-center gap-2 rounded-full bg-cyan-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-600/30 transition hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {pdfBusy ? <Loader2 size={16} className="animate-spin" /> : <ArrowDownToLine size={16} />}
                  Befundbericht als PDF
                </button>
                {pdfError && (
                  <span className="max-w-xs text-right text-[11px] text-rose-600 dark:text-rose-300">
                    {pdfError}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Hilfs-Komponenten ────────────────────────────────────────────────────────

const STAT_TONE: Record<'emerald' | 'amber' | 'rose' | 'slate', string> = {
  emerald: 'text-emerald-200',
  amber: 'text-amber-200',
  rose: 'text-rose-200',
  slate: 'text-slate-200',
};

/** Kompakte Kennzahl im Hero-Block (farbiger Background). */
function Stat({ label, value, tone }: { label: string; value: string | number; tone: keyof typeof STAT_TONE }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-2 py-3">
      <div className="text-[10px] uppercase tracking-wider text-white/60">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${STAT_TONE[tone]}`}>{value}</div>
    </div>
  );
}

/** Ampel-Zähler-Kachel (helle Variante für Fortschritt + Bericht). */
function CountTile({ label, value, rating }: { label: string; value: number; rating: SecurityRating }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white px-4 py-3 text-center dark:border-slate-800 dark:bg-slate-900/60">
      <div className="flex items-center justify-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${RATING_DOT[rating]}`} />
        <span className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</span>
      </div>
      <div className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{value}</div>
    </div>
  );
}

/** Ampel-Badge für einen Einzelbefund. */
function RatingBadge({ rating, label }: { rating: SecurityRating; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${RATING_BADGE[rating]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${RATING_DOT[rating]}`} />
      {label || rating}
    </span>
  );
}

interface ReportViewProps {
  report: SecurityScanReport;
  screenshotUrl: string | null;
  architectureUrl: string | null;
  groupedFindings: Array<{ gruppe: string; findings: SecurityFinding[] }>;
}

function ReportView({ report, screenshotUrl, architectureUrl, groupedFindings }: ReportViewProps) {
  const overall = report.overall;
  const counts = report.counts;
  return (
    <div className="space-y-6">
      {/* ── Bericht-Kopf ─────────────────────────────────────────────── */}
      <section className="rounded-[30px] border border-slate-200/80 bg-white/90 p-6 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
              Befundbericht
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <h2 className="break-all text-lg font-semibold text-slate-900 dark:text-white">
                {report.host || report.url}
              </h2>
              <a
                href={report.url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 text-xs font-medium text-cyan-700 hover:underline dark:text-cyan-300"
              >
                <ExternalLink size={12} /> öffnen
              </a>
            </div>
            <dl className="mt-3 grid gap-x-8 gap-y-1 text-xs text-slate-600 sm:grid-cols-2 dark:text-slate-300">
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400 dark:text-slate-500">Geprüfte URL</dt>
                <dd className="break-all text-right font-medium">{report.url}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400 dark:text-slate-500">Prüfzeitpunkt</dt>
                <dd className="text-right font-medium">{formatDateTime(report.finished_at || report.started_at)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400 dark:text-slate-500">Berechtigung</dt>
                <dd className="text-right font-medium">{report.authorized_by || 'bestätigt'}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-400 dark:text-slate-500">Bezugsrahmen</dt>
                <dd className="text-right font-medium">{report.bezugsrahmen || 'IT-Grundschutz (BSI)'}</dd>
              </div>
            </dl>
            {report.authorization_text && (
              <p className="mt-3 rounded-2xl border border-slate-200/80 bg-slate-50/70 px-4 py-2.5 text-[11px] leading-5 text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400">
                {report.authorization_text}
              </p>
            )}
          </div>

          {/* Gesamt-Ampel-Badge */}
          {overall && (
            <div className={`inline-flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold ring-1 ${OVERALL_BADGE[overall]}`}>
              {overall === 'konform' ? <CheckCircle2 size={18} /> : overall === 'gelb' ? <ShieldAlert size={18} /> : <AlertTriangle size={18} />}
              {OVERALL_LABEL[overall]}
            </div>
          )}
        </div>

        {/* Ampel-Zähler */}
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <CountTile label="Konform" value={counts.konform} rating="konform" />
          <CountTile label="Gelb" value={counts.gelb} rating="gelb" />
          <CountTile label="Rot" value={counts.rot} rating="rot" />
          <CountTile label="Grau" value={counts.grau} rating="grau" />
        </div>
      </section>

      {/* ── Einzelbefunde, gruppiert nach `gruppe` ───────────────────── */}
      {groupedFindings.length === 0 ? (
        <section className="rounded-[30px] border border-dashed border-slate-300 bg-white/80 px-6 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">
          Es wurden keine Einzelbefunde geliefert.
        </section>
      ) : (
        groupedFindings.map((group) => (
          <section
            key={group.gruppe}
            className="rounded-[30px] border border-slate-200/80 bg-white/90 p-6 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80"
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{group.gruppe}</h3>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {group.findings.length}
              </span>
            </div>
            <ul className="mt-4 space-y-3">
              {group.findings.map((f) => (
                <li
                  key={f.pruef_id}
                  className="rounded-[22px] border border-slate-200/80 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/40"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500">{f.pruef_id}</span>
                        <h4 className="text-sm font-semibold text-slate-900 dark:text-white">{f.titel}</h4>
                      </div>
                      {f.bezug && (
                        <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{f.bezug}</div>
                      )}
                    </div>
                    <RatingBadge rating={f.bewertung} label={f.bewertung_label} />
                  </div>

                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-200/70 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-950/40">
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                        Sollzustand
                      </div>
                      <p className="mt-1 text-xs leading-5 text-slate-700 dark:text-slate-200">{f.sollzustand || '—'}</p>
                    </div>
                    <div className="rounded-xl border border-slate-200/70 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-950/40">
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                        Istzustand
                      </div>
                      <p className="mt-1 text-xs leading-5 text-slate-700 dark:text-slate-200">{f.istzustand || '—'}</p>
                    </div>
                  </div>

                  {f.empfehlung && (
                    <div className="mt-3 rounded-xl border border-cyan-200/70 bg-cyan-50/50 px-3 py-2 dark:border-cyan-500/30 dark:bg-cyan-950/20">
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-700 dark:text-cyan-300">
                        Empfehlung
                      </div>
                      <p className="mt-1 text-xs leading-5 text-cyan-900 dark:text-cyan-100">{f.empfehlung}</p>
                    </div>
                  )}

                  {(f.eingriffstiefe || f.rohbefund) && (
                    <details className="group mt-3">
                      <summary className="cursor-pointer list-none text-[11px] font-medium text-slate-500 transition hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200">
                        Rohbefund &amp; Eingriffstiefe anzeigen
                      </summary>
                      <div className="mt-2 space-y-2 text-[11px] leading-5 text-slate-500 dark:text-slate-400">
                        {f.eingriffstiefe && (
                          <div>
                            <span className="font-semibold text-slate-600 dark:text-slate-300">Eingriffstiefe: </span>
                            {f.eingriffstiefe}
                          </div>
                        )}
                        {f.rohbefund && (
                          <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-slate-900/90 px-3 py-2 font-mono text-[10px] text-slate-100">
                            {f.rohbefund}
                          </pre>
                        )}
                      </div>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      {/* ── Screenshot + Architektur-Diagramm ────────────────────────── */}
      {(screenshotUrl || architectureUrl) && (
        <section className="grid gap-6 lg:grid-cols-2">
          {screenshotUrl && (
            <div className="rounded-[30px] border border-slate-200/80 bg-white/90 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
              <div className="flex items-center gap-2">
                <ImageIcon size={15} className="text-slate-400" />
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Screenshot</h3>
              </div>
              <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/80 dark:border-slate-800">
                <img
                  src={screenshotUrl}
                  alt={`Screenshot der geprüften Webseite ${report.host || report.url}`}
                  className="w-full"
                  loading="lazy"
                />
              </div>
            </div>
          )}
          {architectureUrl && (
            <div className="rounded-[30px] border border-slate-200/80 bg-white/90 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
              <div className="flex items-center gap-2">
                <Network size={15} className="text-slate-400" />
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Architektur-Diagramm</h3>
              </div>
              <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/80 dark:border-slate-800">
                <img
                  src={architectureUrl}
                  alt={`Architektur-Diagramm der geprüften Webseite ${report.host || report.url}`}
                  className="w-full"
                  loading="lazy"
                />
              </div>
            </div>
          )}
        </section>
      )}

      {/* ── Geltungsbereich-Hinweis ──────────────────────────────────── */}
      <section className="rounded-[26px] border border-slate-200/80 bg-slate-50/70 px-6 py-5 text-xs leading-5 text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400">
        <div className="flex items-start gap-2.5">
          <ShieldAlert size={15} className="mt-0.5 shrink-0 text-slate-400" />
          <p>
            <span className="font-semibold text-slate-600 dark:text-slate-300">Geltungsbereich: </span>
            Die Prüfung umfasst ausschließlich die von außen erreichbare Konfiguration (TLS,
            Sicherheitsheader, HTTPS-Erzwingung, offene Ports, Versions-/CVE-Indikation) und ist
            nicht-intrusiv. Sie ersetzt keine vollständige IT-Grundschutz-Prüfung nach BSI-Standard
            200-2 und keine Penetrationsprüfung. Eine abschließende fachliche Bewertung obliegt dem
            Prüfer.
          </p>
        </div>
      </section>
    </div>
  );
}
