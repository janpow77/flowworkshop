/**
 * StateAidSearchPanel — Suchfeld + Filterleiste fuer das Beihilfe-Register.
 *
 * Plan §9.2: Filter fuer Unternehmen, Land, NUTS, Zeitraum, Betrag,
 * Beihilfeinstrument, Beihilfeziel, Behoerde, SA-Referenz, NACE, Quelle.
 *
 * Top: Q + Land + Jahr (kompakt). Restliche Filter in einem klappbaren
 * "Erweiterte Filter"-Block. Default-Land: DE (kann auf AT umgestellt werden).
 */
import { useState, type FormEvent } from 'react';
import { ChevronDown, ChevronUp, Filter, Loader2, RotateCcw, Search, Sparkles } from 'lucide-react';
import type { StateAidSource } from '../../lib/stateAidApi';
import type { StateAidFilterState } from './stateAidFilters';

interface Props {
  value: StateAidFilterState;
  onChange: (value: StateAidFilterState) => void;
  onSubmit: (value: StateAidFilterState) => void;
  onReset: () => void;
  sources: StateAidSource[];
  busy?: boolean;
}

const COUNTRY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Alle Laender' },
  { value: 'DE', label: 'DE · Deutschland' },
  { value: 'AT', label: 'AT · Oesterreich' },
  { value: 'EU', label: 'EU · alle Mitgliedstaaten' },
];

const YEAR_OPTIONS = (() => {
  const now = new Date().getFullYear();
  const years: Array<{ value: string; label: string }> = [{ value: '', label: 'Alle Jahre' }];
  for (let y = now; y >= now - 9; y -= 1) {
    years.push({ value: String(y), label: String(y) });
  }
  return years;
})();

export default function StateAidSearchPanel({ value, onChange, onSubmit, onReset, sources, busy }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit(value);
  }

  function setField<K extends keyof StateAidFilterState>(key: K, val: StateAidFilterState[K]) {
    onChange({ ...value, [key]: val });
  }

  function setYear(year: string) {
    if (!year) {
      onChange({ ...value, since: '', until: '' });
    } else {
      onChange({ ...value, since: `${year}-01-01`, until: `${year}-12-31` });
    }
  }

  // Aktives "Jahr" aus since/until ableiten — nur wenn ein voller Kalenderjahr-Zeitraum vorliegt.
  const activeYear = (() => {
    if (!value.since || !value.until) return '';
    const m1 = value.since.match(/^(\d{4})-01-01$/);
    const m2 = value.until.match(/^(\d{4})-12-31$/);
    if (m1 && m2 && m1[1] === m2[1]) return m1[1];
    return '';
  })();

  // Fuzzy-Schwelle → menschliche Klassifizierung (analog Sanctions-Konfidenz).
  const scoreLabel = (() => {
    const s = value.min_score;
    if (s >= 97) return { tag: 'exact', tone: 'text-emerald-700 dark:text-emerald-300' };
    if (s >= 90) return { tag: 'hoch', tone: 'text-emerald-600 dark:text-emerald-400' };
    if (s >= 80) return { tag: 'mittel', tone: 'text-amber-600 dark:text-amber-400' };
    if (s >= 65) return { tag: 'niedrig', tone: 'text-amber-700 dark:text-amber-300' };
    return { tag: 'sehr niedrig', tone: 'text-rose-600 dark:text-rose-300' };
  })();

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75"
    >
      <div className="rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] p-4 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
            <Search size={20} />
          </div>
          <div className="flex-1">
            <div className="text-sm font-medium text-slate-900 dark:text-white">Treffersuche im Beihilfe-Register</div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Begriff, Land und Zeitraum kombinieren — Fuzzy-Match passt sich an.
            </div>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3 rounded-[24px] border border-slate-200 bg-white/90 px-4 py-3 dark:border-slate-700 dark:bg-slate-950/60">
          <Search size={18} className="text-slate-400" />
          <input
            type="text"
            value={value.q}
            onChange={(e) => setField('q', e.target.value)}
            placeholder="Unternehmen, Behoerde oder SA-Referenz …"
            className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-slate-100"
            aria-label="Suchbegriff"
          />
          <button
            type="submit"
            disabled={busy}
            className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-full bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            Suchen
          </button>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <select
            value={value.country_code}
            onChange={(e) => setField('country_code', e.target.value)}
            className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-emerald-500 dark:focus:ring-emerald-500/30"
            aria-label="Land"
          >
            {COUNTRY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <select
            value={activeYear}
            onChange={(e) => setYear(e.target.value)}
            className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-emerald-500 dark:focus:ring-emerald-500/30"
            aria-label="Jahr"
          >
            {YEAR_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div
        className="mt-4 rounded-[18px] bg-slate-50 px-4 py-3 dark:bg-slate-900/60"
        title="Tiefer = mehr Treffer, ungenauer. 65 ist der empfohlene Default."
      >
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
          <div className="flex items-center gap-2">
            <Sparkles size={13} className="text-emerald-500" />
            <span className="font-medium text-slate-600 dark:text-slate-300">Fuzzy-Schwelle</span>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={40}
              max={100}
              step={5}
              value={value.min_score}
              onChange={(e) => setField('min_score', Number(e.target.value))}
              aria-label="Fuzzy-Schwelle"
              className="w-44 accent-emerald-600"
            />
            <span className="w-10 text-right font-mono text-sm font-semibold text-emerald-700 dark:text-emerald-300">
              {value.min_score}
            </span>
            <span className={`font-medium ${scoreLabel.tone}`}>{scoreLabel.tag}</span>
          </div>
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            exact &ge;97 · hoch &ge;90 · mittel &ge;80 · niedrig &ge;65 — tiefer = mehr Treffer, ungenauer.
          </span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-600 transition hover:border-emerald-300 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-emerald-500/40 dark:hover:text-emerald-300"
        >
          <Filter size={12} /> Erweiterte Filter
          {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-500 transition hover:border-slate-300 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <RotateCcw size={12} /> Zuruecksetzen
        </button>
        {sources.length > 0 && (
          <span className="text-slate-400 dark:text-slate-500">
            {sources.filter((s) => s.enabled).length} aktive Quelle{sources.filter((s) => s.enabled).length === 1 ? '' : 'n'}
          </span>
        )}
      </div>

      {showAdvanced && (
        <div className="mt-3 grid gap-3 rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] p-4 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))] sm:grid-cols-2 lg:grid-cols-3">
          <Field label="NUTS-Region (z. B. DE7)">
            <input
              type="text"
              value={value.nuts_code}
              onChange={(e) => setField('nuts_code', e.target.value)}
              placeholder="DE71, AT12 …"
              className={inputClass}
            />
          </Field>
          <Field label="Quelle">
            <select
              value={value.source_key}
              onChange={(e) => setField('source_key', e.target.value)}
              className={inputClass}
            >
              <option value="">Alle Quellen</option>
              {sources.map((s) => (
                <option key={s.source_key} value={s.source_key}>{s.display_name}</option>
              ))}
            </select>
          </Field>
          <Field label="SA-Referenz">
            <input
              type="text"
              value={value.sa_reference}
              onChange={(e) => setField('sa_reference', e.target.value)}
              placeholder="SA.12345"
              className={inputClass}
            />
          </Field>
          <Field label="Beihilfeinstrument">
            <input
              type="text"
              value={value.aid_instrument}
              onChange={(e) => setField('aid_instrument', e.target.value)}
              placeholder="Zuschuss, Darlehen …"
              className={inputClass}
            />
          </Field>
          <Field label="Beihilfeziel">
            <input
              type="text"
              value={value.aid_objective}
              onChange={(e) => setField('aid_objective', e.target.value)}
              placeholder="Regionale Entwicklung …"
              className={inputClass}
            />
          </Field>
          <Field label="Bewilligende Behoerde">
            <input
              type="text"
              value={value.granting_authority}
              onChange={(e) => setField('granting_authority', e.target.value)}
              placeholder="Ministerium / Kammer …"
              className={inputClass}
            />
          </Field>
          <Field label="NACE-Code (optional)">
            <input
              type="text"
              value={value.nace}
              onChange={(e) => setField('nace', e.target.value)}
              placeholder="z. B. 25.62"
              className={inputClass}
            />
          </Field>
          <Field label="Mindestbetrag (EUR)">
            <input
              type="number"
              min={0}
              value={value.min_amount}
              onChange={(e) => setField('min_amount', e.target.value)}
              placeholder="0"
              className={inputClass}
            />
          </Field>
          <Field label="Hoechstbetrag (EUR)">
            <input
              type="number"
              min={0}
              value={value.max_amount}
              onChange={(e) => setField('max_amount', e.target.value)}
              placeholder=""
              className={inputClass}
            />
          </Field>
          <Field label="Bewilligt ab">
            <input
              type="date"
              value={value.since}
              onChange={(e) => setField('since', e.target.value)}
              className={inputClass}
            />
          </Field>
          <Field label="Bewilligt bis">
            <input
              type="date"
              value={value.until}
              onChange={(e) => setField('until', e.target.value)}
              className={inputClass}
            />
          </Field>
        </div>
      )}
    </form>
  );
}

const inputClass =
  'w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-emerald-500 dark:focus:ring-emerald-500/30';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="font-medium text-slate-600 dark:text-slate-400">{label}</span>
      {children}
    </label>
  );
}
