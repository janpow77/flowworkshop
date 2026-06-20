/**
 * frontend · components/workshop/EntityResolutionPanel.tsx
 *
 * Konsolidierte Firmensicht (Entity-Resolution). Die Lese-Sicht (Suche +
 * Detail) ist für jeden eingeloggten Prüfer verfügbar (Backend: require_session).
 * Das Bestätigen/Ablehnen einzelner Matches ist Admin-only (require_admin) und
 * wird im Frontend nur gerendert, wenn ``workshop_role === 'admin'`` — exakt
 * das Gating, das auch AuditReportTrailPage/AdminBeneficiarySourcesPage nutzen.
 *
 * Rebuild und LLM-Verifikations-Batch sind bewusst CLI-/Hintergrund-Operationen
 * (siehe scripts/rebuild_entity_resolution.py bzw. POST .../llm-verify-batch
 * mit background=true). Hier gibt es dafür nur einen Hinweistext, keinen Button,
 * der den HTTP-Worker minutenlang blockiert.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Banknote, Building2, CheckCircle2, ChevronRight, Fingerprint, Layers3,
  Loader2, Network, Search, ShieldAlert, ShieldCheck, Users, XCircle,
} from 'lucide-react';
import {
  confirmEntityMatch,
  getEntity,
  rejectEntityMatch,
  searchEntities,
  type CountryCode,
  type EntityDetail,
  type EntityMatch,
  type EntitySearchHit,
} from '../../lib/api';

/** Admin-Gating analog AuditReportTrailPage.tsx / AdminBeneficiarySourcesPage.tsx. */
function isAdmin(): boolean {
  return (localStorage.getItem('workshop_role') || '') === 'admin';
}

const MODULE_META: Record<string, { label: string; className: string }> = {
  state_aid: {
    label: 'Beihilfe-Register',
    className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  },
  beneficiary: {
    label: 'Begünstigtenverzeichnis',
    className: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300',
  },
  sanctions: {
    label: 'Sanktionsliste',
    className: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
  },
};

function moduleMeta(module: string): { label: string; className: string } {
  return MODULE_META[module] || {
    label: module,
    className: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  };
}

/** Verfahren in lesbarer Form (z.B. ``name_fuzzy_88`` → „Namens-Ähnlichkeit (88)"). */
function methodLabel(method: string): string {
  if (method === 'lei') return 'LEI (Rechtsträgerkennung)';
  if (method === 'identifier') return 'Nationale Kennung (z.B. HRB)';
  if (method === 'name_exact') return 'Name exakt (normalisiert)';
  if (method.startsWith('name_fuzzy')) {
    const score = method.split('_').pop();
    return score && /^\d+$/.test(score)
      ? `Namens-Ähnlichkeit (${score})`
      : 'Namens-Ähnlichkeit';
  }
  if (method.startsWith('name_new')) return 'Neu angelegt (kein Bestandstreffer)';
  if (method.includes('llm')) return 'LLM-Verifikation';
  return method;
}

/** Evidenz-Schlüssel deutsch beschriften; unbekannte Keys unverändert lassen. */
const EVIDENCE_LABELS: Record<string, string> = {
  lei: 'LEI',
  identifier: 'Kennung',
  name_in_record: 'Name im Datensatz',
  name_normalized: 'Name (normalisiert)',
  matched_canonical_name: 'Zugeordneter Name',
  matched_normalized: 'Zugeordnet (normalisiert)',
  fuzzy_score: 'Ähnlichkeits-Score',
};

function evidenceLabel(key: string): string {
  return EVIDENCE_LABELS[key] || key;
}

/** Evidenz-Wert sicher als String darstellen (Objekte/Arrays als JSON). */
function evidenceValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }
  if (typeof value === 'string' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Farbgebung der Konfidenz-Pille: hoch=grün, mittel=amber, niedrig=slate. */
function confidenceClass(confidence: number): string {
  if (confidence >= 90) return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200';
  if (confidence >= 75) return 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200';
  return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

interface EntityResolutionPanelProps {
  /** Übernimmt den aktuellen Suchbegriff der Seite (optional). */
  initialQuery?: string;
  /** Länderfilter aus der Hauptseite (optional, DE/AT). */
  countryCode?: CountryCode | '';
}

export default function EntityResolutionPanel({
  initialQuery = '',
  countryCode = '',
}: EntityResolutionPanelProps) {
  const admin = useMemo(() => isAdmin(), []);

  const [query, setQuery] = useState(initialQuery);
  const [hits, setHits] = useState<EntitySearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  // Pro Match laufende Confirm/Reject-Aktion (verhindert Doppelklick).
  const [pendingMatchId, setPendingMatchId] = useState<number | null>(null);
  const [actionError, setActionError] = useState('');

  // Suche (debounced). Leerer Query liefert die zuletzt gesehenen Entitäten.
  useEffect(() => {
    let cancelled = false;
    const trimmed = query.trim();
    setSearching(true);
    setSearchError('');
    const timer = window.setTimeout(() => {
      searchEntities(trimmed, { country_code: countryCode || undefined, limit: 25 })
        .then((res) => {
          if (cancelled) return;
          setHits(res.results);
          // Auswahl beibehalten, sonst ersten Treffer wählen.
          setSelectedId((current) => {
            if (current && res.results.some((h) => h.id === current)) return current;
            return res.results[0]?.id ?? null;
          });
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setSearchError(err instanceof Error ? err.message : 'Suche fehlgeschlagen.');
          setHits([]);
        })
        .finally(() => { if (!cancelled) setSearching(false); });
    }, trimmed ? 220 : 0);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, countryCode]);

  // Detail laden, sobald sich die Auswahl ändert.
  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return undefined;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError('');
    setActionError('');
    getEntity(selectedId)
      .then((res) => { if (!cancelled) setDetail(res); })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDetailError(err instanceof Error ? err.message : 'Detail konnte nicht geladen werden.');
        setDetail(null);
      })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId]);

  async function reloadDetail(id: number): Promise<void> {
    try {
      const res = await getEntity(id);
      setDetail(res);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Detail konnte nicht aktualisiert werden.');
    }
  }

  async function handleConfirm(match: EntityMatch): Promise<void> {
    if (!detail) return;
    setPendingMatchId(match.id);
    setActionError('');
    try {
      await confirmEntityMatch(detail.id, match.id);
      await reloadDetail(detail.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Bestätigen fehlgeschlagen.');
    } finally {
      setPendingMatchId(null);
    }
  }

  async function handleReject(match: EntityMatch): Promise<void> {
    if (!detail) return;
    setPendingMatchId(match.id);
    setActionError('');
    try {
      await rejectEntityMatch(detail.id, match.id);
      await reloadDetail(detail.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Ablehnen fehlgeschlagen.');
    } finally {
      setPendingMatchId(null);
    }
  }

  return (
    <section className="rounded-[30px] border border-indigo-200/70 bg-gradient-to-br from-white via-indigo-50/40 to-white p-5 shadow-[0_22px_76px_-52px_rgba(79,70,229,0.4)] dark:border-indigo-500/25 dark:from-slate-900 dark:via-indigo-950/20 dark:to-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-md shadow-indigo-600/30">
            <Network size={18} />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900 dark:text-white">Konsolidierte Firmensicht (Entity-Resolution)</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">
              Über Register hinweg zusammengeführte Rechtsträger — mit Beleg je Zuordnung.
              {admin
                ? ' Als Admin können Sie einzelne Zuordnungen bestätigen oder ablehnen.'
                : ' Bestätigen/Ablehnen ist Administratoren vorbehalten.'}
            </div>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-[11px] font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-200">
          <Users size={12} />
          Human-in-the-Loop
        </span>
      </div>

      {/* Suchfeld */}
      <div className="mt-4 flex items-center gap-3 rounded-[24px] border border-slate-200 bg-white/90 px-4 py-3 dark:border-slate-700 dark:bg-slate-950/60">
        <Search size={18} className="text-slate-400" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Rechtsträger suchen (Name)…"
          className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-slate-100"
          aria-label="Konsolidierte Firmensuche"
        />
        {searching && <Loader2 size={16} className="animate-spin text-indigo-500" />}
      </div>

      {searchError && (
        <div className="mt-3 rounded-2xl border border-amber-200/70 bg-amber-50/70 px-4 py-3 text-xs text-amber-800 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
          {searchError}
        </div>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
        {/* Trefferliste */}
        <div className="space-y-2">
          {!searching && hits.length === 0 && !searchError && (
            <div className="rounded-[24px] border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center dark:border-slate-700 dark:bg-slate-950/45">
              <Layers3 size={22} className="mx-auto text-slate-300 dark:text-slate-600" />
              <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
                {query.trim()
                  ? 'Keine konsolidierten Rechtsträger für diesen Suchbegriff.'
                  : 'Noch keine Entitäten vorhanden. Der Bestand wird über den Rebuild aufgebaut (siehe Hinweis unten).'}
              </p>
            </div>
          )}

          {hits.map((hit) => (
            <button
              key={hit.id}
              type="button"
              onClick={() => setSelectedId(hit.id)}
              className={`w-full rounded-[22px] border px-4 py-3 text-left transition ${
                selectedId === hit.id
                  ? 'border-indigo-200 bg-indigo-50/80 shadow-[0_18px_40px_-30px_rgba(79,70,229,0.6)] dark:border-indigo-900 dark:bg-indigo-950/35'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-slate-700 dark:hover:bg-slate-900/80'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Building2 size={15} className="shrink-0 text-indigo-600 dark:text-indigo-300" />
                    <span className="truncate text-sm font-semibold text-slate-900 dark:text-white">{hit.canonical_name}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    {hit.country_code && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{hit.country_code}</span>
                    )}
                    {hit.lei && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                        <Fingerprint size={10} /> LEI
                      </span>
                    )}
                    <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-200">
                      {hit.match_count} {hit.match_count === 1 ? 'Zuordnung' : 'Zuordnungen'}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {hit.has_state_aid && (
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${moduleMeta('state_aid').className}`}>
                        <Banknote size={10} /> Beihilfe
                      </span>
                    )}
                    {hit.has_beneficiary && (
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${moduleMeta('beneficiary').className}`}>
                        <Building2 size={10} /> Begünstigte
                      </span>
                    )}
                    {hit.has_sanctions && (
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${moduleMeta('sanctions').className}`}>
                        <ShieldAlert size={10} /> Sanktionen
                      </span>
                    )}
                  </div>
                </div>
                <ChevronRight size={16} className="mt-1 shrink-0 text-slate-300 dark:text-slate-600" />
              </div>
            </button>
          ))}
        </div>

        {/* Detailansicht */}
        <div className="rounded-[24px] border border-slate-200 bg-white/90 p-4 dark:border-slate-800 dark:bg-slate-950/50">
          {selectedId === null ? (
            <div className="flex h-full min-h-[280px] items-center justify-center text-center">
              <div className="max-w-xs px-6">
                <Network size={22} className="mx-auto text-slate-300 dark:text-slate-600" />
                <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
                  Wählen Sie links einen Rechtsträger, um Zuordnungen und Belege zu sehen.
                </p>
              </div>
            </div>
          ) : detailLoading ? (
            <div className="flex h-full min-h-[280px] items-center justify-center text-sm text-slate-500 dark:text-slate-400">
              <Loader2 size={16} className="mr-2 animate-spin" /> Detail wird geladen …
            </div>
          ) : detailError ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300">
              {detailError}
            </div>
          ) : detail ? (
            <div className="space-y-4">
              {/* Kopf */}
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">Konsolidierter Rechtsträger</div>
                <h3 className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{detail.canonical_name}</h3>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{detail.entity_type}</span>
                  {detail.country_code && (
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{detail.country_code}</span>
                  )}
                  {detail.lei && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 font-mono font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      <Fingerprint size={11} /> {detail.lei}
                    </span>
                  )}
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    Zuletzt gesehen: {formatDate(detail.last_seen_at)}
                  </span>
                </div>
              </div>

              {/* Konzern-Hierarchie (nur wenn vorhanden) */}
              {(detail.parent || detail.ultimate_parent || detail.children.length > 0) && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-3 py-3 text-xs dark:border-slate-800 dark:bg-slate-900/60">
                  <div className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-slate-200">
                    <Network size={13} /> Konzernverbund
                  </div>
                  <div className="mt-2 space-y-1 text-slate-600 dark:text-slate-300">
                    {detail.ultimate_parent && (
                      <div>Oberste Muttergesellschaft: <span className="font-medium text-slate-900 dark:text-white">{detail.ultimate_parent.canonical_name}</span></div>
                    )}
                    {detail.parent && (
                      <div>Direkte Muttergesellschaft: <span className="font-medium text-slate-900 dark:text-white">{detail.parent.canonical_name}</span></div>
                    )}
                    {detail.children.length > 0 && (
                      <div>
                        Tochtergesellschaften ({detail.children.length}): {detail.children.slice(0, 5).map((c) => c.canonical_name).join(', ')}
                        {detail.children.length > 5 ? ' …' : ''}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {actionError && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300">
                  {actionError}
                </div>
              )}

              {/* Matches */}
              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-900 dark:text-white">Zuordnungen ({detail.matches.length})</div>
                </div>
                <div className="space-y-3">
                  {detail.matches.length === 0 ? (
                    <p className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950/45 dark:text-slate-400">
                      Keine Zuordnungen vorhanden.
                    </p>
                  ) : (
                    detail.matches.map((match) => {
                      const meta = moduleMeta(match.source_module);
                      const evidenceEntries = match.match_evidence
                        ? Object.entries(match.match_evidence)
                        : [];
                      const busy = pendingMatchId === match.id;
                      return (
                        <div
                          key={match.id}
                          className={`rounded-2xl border px-4 py-3 ${
                            match.rejected
                              ? 'border-rose-200 bg-rose-50/60 dark:border-rose-900/60 dark:bg-rose-950/25'
                              : match.confirmed_at
                                ? 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/60 dark:bg-emerald-950/25'
                                : 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950/40'
                          }`}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${meta.className}`}>{meta.label}</span>
                              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                {methodLabel(match.match_method)}
                              </span>
                              <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${confidenceClass(match.match_confidence)}`}>
                                Konfidenz {match.match_confidence.toFixed(0)}
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 text-[11px]">
                              {match.rejected ? (
                                <span className="inline-flex items-center gap-1 font-medium text-rose-600 dark:text-rose-300"><XCircle size={13} /> abgelehnt</span>
                              ) : match.confirmed_at ? (
                                <span className="inline-flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-300"><CheckCircle2 size={13} /> bestätigt</span>
                              ) : (
                                <span className="inline-flex items-center gap-1 font-medium text-slate-400">offen</span>
                              )}
                            </div>
                          </div>

                          <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                            Quelle: <span className="font-mono">{match.source_table}</span> · Datensatz <span className="font-mono">{match.source_record_id}</span>
                          </div>

                          {evidenceEntries.length > 0 && (
                            <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                              {evidenceEntries.map(([key, value]) => (
                                <div key={key} className="flex flex-col">
                                  <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-400">{evidenceLabel(key)}</dt>
                                  <dd className="truncate text-xs font-medium text-slate-800 dark:text-slate-200" title={evidenceValue(value)}>{evidenceValue(value)}</dd>
                                </div>
                              ))}
                            </dl>
                          )}

                          {(match.confirmed_at || match.confirmed_by_user_id) && (
                            <div className="mt-2 text-[10px] text-slate-400">
                              {match.confirmed_at ? `Geprüft am ${formatDate(match.confirmed_at)}` : 'Bearbeitet'}
                              {match.confirmed_by_user_id ? ` · ${match.confirmed_by_user_id}` : ''}
                            </div>
                          )}

                          {admin && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => handleConfirm(match)}
                                disabled={busy || (!!match.confirmed_at && !match.rejected)}
                                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                                Bestätigen
                              </button>
                              <button
                                type="button"
                                onClick={() => handleReject(match)}
                                disabled={busy || match.rejected}
                                className="inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-rose-500/40 dark:bg-slate-900 dark:text-rose-300 dark:hover:bg-rose-950/30"
                              >
                                {busy ? <Loader2 size={13} className="animate-spin" /> : <XCircle size={13} />}
                                Ablehnen
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Hinweis: Rebuild + LLM-Batch sind CLI-/Hintergrund-Operationen. */}
      <div className="mt-4 flex items-start gap-2 rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-950/45 dark:text-slate-400">
        <ShieldCheck size={14} className="mt-0.5 shrink-0 text-slate-400" />
        <span>
          Der Aufbau des Entity-Bestands (Rebuild) und der LLM-Verifikations-Batch laufen als
          Hintergrund-/CLI-Operationen (<span className="font-mono">scripts/rebuild_entity_resolution.py</span> bzw.
          der Admin-Endpunkt mit <span className="font-mono">background=true</span>) und werden bewusst nicht aus der
          Oberfläche heraus synchron gestartet, um den Server nicht zu blockieren. KI-Treffer sind Hinweise — die
          fachliche Entscheidung trifft der Prüfer.
        </span>
      </div>
    </section>
  );
}
