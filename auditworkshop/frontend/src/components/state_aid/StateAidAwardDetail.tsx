/**
 * StateAidAwardDetail — Drawer/Modal mit allen Award-Feldern.
 *
 * Plan §4.3 + §13: KOM-Link-Status klar ausweisen
 *   - "Fallakte verlinkt"            (case_url vorhanden)
 *   - "Direktlink Entscheidung"      (decision_url vorhanden)
 *   - "kein direkter Dokumentlink"   (nur SA-Ref, kein URL)
 */
import { useEffect } from 'react';
import { ExternalLink, FileText, Link2, ShieldQuestion, X } from 'lucide-react';
import { safeExternalUrl, type StateAidAward } from '../../lib/stateAidApi';

interface Props {
  award: StateAidAward | null;
  onClose: () => void;
}

function formatEur(value: number | null | undefined, currency = 'EUR'): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

export default function StateAidAwardDetail({ award, onClose }: Props) {
  useEffect(() => {
    if (!award) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [award, onClose]);

  if (!award) return null;

  const linkStatus = (() => {
    if (award.decision_url) return { tone: 'emerald', label: 'Direktlink Entscheidung', icon: FileText };
    if (award.case_url) return { tone: 'cyan', label: 'Fallakte verlinkt', icon: Link2 };
    if (award.sa_reference) return { tone: 'amber', label: 'Kein direkter Dokumentlink — nur SA-Referenz', icon: ShieldQuestion };
    return { tone: 'slate', label: 'Keine KOM-Referenz', icon: ShieldQuestion };
  })();

  const tone: Record<string, string> = {
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-950/40 dark:text-emerald-200',
    cyan: 'border-cyan-200 bg-cyan-50 text-cyan-800 dark:border-cyan-500/30 dark:bg-cyan-950/40 dark:text-cyan-200',
    amber: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-200',
    slate: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300',
  };
  const StatusIcon = linkStatus.icon;

  return (
    <div className="fixed inset-0 z-[1100] flex justify-end bg-slate-900/50 backdrop-blur-sm dark:bg-slate-950/70" onClick={onClose}>
      <aside
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-2xl flex-col overflow-hidden bg-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.96)] dark:bg-slate-900"
        role="dialog"
        aria-label="Award-Detail"
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-6 py-4 dark:border-slate-700">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-[0.22em] text-emerald-600 dark:text-emerald-300">Beihilfe-Award</div>
            <h2 className="mt-1 truncate text-lg font-semibold text-slate-900 dark:text-slate-100">
              {award.beneficiary_name}
            </h2>
            {award.beneficiary_identifier && (
              <div className="mt-0.5 font-mono text-xs text-slate-400">{award.beneficiary_identifier}</div>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-label="Schliessen"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className={`mb-5 flex items-start gap-3 rounded-[24px] border px-4 py-3 text-sm ${tone[linkStatus.tone]}`}>
            <StatusIcon size={18} className="mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="font-semibold">{linkStatus.label}</div>
              <p className="mt-1 text-xs opacity-80">
                Die SA-Referenz verweist auf die Fallakte der Kommission. Ein direkter
                Entscheidungslink ist nur ausgewiesen, wenn er automatisiert eindeutig
                ermittelt wurde.
              </p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {/*
                  safeExternalUrl filtert javascript:/data:/file:-URLs raus.
                  Falls TAM oder Admin-DB einen boesartigen URL-Wert
                  einschleusen wuerden, verschwindet hier einfach der Link.
                */}
                {(() => {
                  const safeCase = safeExternalUrl(award.case_url);
                  return safeCase ? (
                    <a
                      href={safeCase}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-full bg-white/70 px-3 py-1 font-medium text-cyan-800 transition hover:bg-white dark:bg-slate-900/70 dark:text-cyan-200"
                    >
                      Fallakte oeffnen <ExternalLink size={11} />
                    </a>
                  ) : null;
                })()}
                {(() => {
                  const safeDecision = safeExternalUrl(award.decision_url);
                  return safeDecision ? (
                    <a
                      href={safeDecision}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-full bg-white/70 px-3 py-1 font-medium text-emerald-800 transition hover:bg-white dark:bg-slate-900/70 dark:text-emerald-200"
                    >
                      Entscheidung (PDF) <ExternalLink size={11} />
                    </a>
                  ) : null;
                })()}
                {(() => {
                  const safeSource = safeExternalUrl(award.source_url);
                  return safeSource ? (
                    <a
                      href={safeSource}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-full bg-white/70 px-3 py-1 font-medium text-slate-700 transition hover:bg-white dark:bg-slate-900/70 dark:text-slate-200"
                    >
                      Quelle <ExternalLink size={11} />
                    </a>
                  ) : null;
                })()}
              </div>
            </div>
          </div>

          <Section title="Beihilfedetails">
            <Row label="Betrag (EUR)" value={formatEur(award.aid_amount_eur)} mono />
            {award.aid_amount !== null && award.aid_currency && award.aid_currency !== 'EUR' && (
              <Row
                label="Original-Betrag"
                value={formatEur(award.aid_amount, award.aid_currency)}
                mono
              />
            )}
            <Row label="Beihilfeinstrument" value={award.aid_instrument || '—'} />
            <Row label="Beihilfeziel" value={award.aid_objective || '—'} />
            <Row label="Massnahmentitel" value={award.aid_measure_title || '—'} />
            <Row label="Bewilligungsdatum" value={formatDate(award.granting_date)} />
            <Row label="Veroeffentlichungsdatum" value={formatDate(award.publication_date)} />
          </Section>

          <Section title="Region & Branche">
            <Row label="Land" value={[award.country_code, award.country_name].filter(Boolean).join(' · ') || '—'} />
            <Row
              label="NUTS"
              value={
                award.nuts_code
                  ? `${award.nuts_code}${award.nuts_label ? ` · ${award.nuts_label}` : ''}${award.nuts_level !== null ? ` (Level ${award.nuts_level})` : ''}`
                  : '—'
              }
              mono={!!award.nuts_code}
            />
            <Row label="NACE" value={award.nace_label || '—'} />
            <Row label="Beguenstigtentyp" value={award.beneficiary_type || '—'} />
          </Section>

          <Section title="Behoerden & Referenzen">
            <Row label="Bewilligende Behoerde" value={award.granting_authority || '—'} />
            <Row label="Beauftragte Stelle" value={award.entrusted_entity || '—'} />
            <Row label="Massnahmenreferenz" value={award.measure_reference || '—'} mono />
            <Row label="SA-Referenz (KOM)" value={award.sa_reference || '—'} mono />
          </Section>

          <Section title="Quelle">
            <Row label="Quellenkennung" value={award.source_key} mono />
            <Row label="Datensatz-ID" value={award.source_record_id} mono />
            <Row label="Award-ID" value={award.id} mono />
          </Section>
        </div>
      </aside>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
        {title}
      </div>
      <dl className="grid gap-1.5 rounded-[22px] border border-slate-200 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 text-sm dark:border-slate-700 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.6),rgba(2,6,23,0.7))]">
        {children}
      </dl>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start gap-3 py-1">
      <dt className="w-44 shrink-0 text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className={`flex-1 break-words text-slate-700 dark:text-slate-200 ${mono ? 'font-mono text-[12px]' : ''}`}>
        {value}
      </dd>
    </div>
  );
}
