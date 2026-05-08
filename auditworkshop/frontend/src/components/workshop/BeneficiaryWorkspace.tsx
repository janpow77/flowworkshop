/**
 * BeneficiaryWorkspace — Tab-Register für /scenario/6 und /begünstigte.
 *
 * Drei Reiter:
 *  1. Strukturierte Schnellsuche (default) — Country-Picker, Karte, Analytics
 *  2. Unternehmenssuche                    — Volltext-Firmensuche + Trefferliste
 *  3. KI-Fragen                            — freie LLM-Auswertung mit Stream
 *
 * Tab-State persistent in URL als ?tab=schnellsuche|unternehmen|frage.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  BarChart3,
  Brain,
  Building2,
  Database,
  Loader2,
  Search,
  Send,
  Sparkles,
} from 'lucide-react';
import LlmResponsePanel from './LlmResponsePanel';
import BeneficiaryMap from './BeneficiaryMap';
import BeneficiaryAnalyticsPanel from './BeneficiaryAnalyticsPanel';
import BeneficiaryCompanySearch from './BeneficiaryCompanySearch';
import { streamSSE, type CountryCode } from '../../lib/api';

type TabKey = 'schnellsuche' | 'unternehmen' | 'frage';

const TABS: Array<{
  key: TabKey;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  description: string;
}> = [
  {
    key: 'schnellsuche',
    label: 'Strukturierte Schnellsuche',
    icon: BarChart3,
    description: 'Karte und vorbereitete Auswertungen mit Filter nach Land, Bundesland und Fonds.',
  },
  {
    key: 'unternehmen',
    label: 'Unternehmenssuche',
    icon: Building2,
    description: 'Volltext-Firmensuche über alle Begünstigtenverzeichnisse mit Konfidenz-Badge.',
  },
  {
    key: 'frage',
    label: 'Auswertung mit Künstlicher Intelligenz (KI)',
    icon: Brain,
    description: 'Freie Frage an die KI — die Auswertung läuft lokal gegen die geladenen Daten.',
  },
];

const QUESTION_PRESETS: string[] = [
  'Welche Kommunen erhalten die höchste Förderung?',
  'Wie verteilt sich die Fördersumme auf die Bundesländer?',
  'Welche Branchen werden am stärksten gefördert?',
];

const COUNTRY_OPTIONS: Array<{ value: CountryCode | ''; label: string }> = [
  { value: 'DE', label: 'Deutschland' },
  { value: 'AT', label: 'Österreich' },
  { value: '', label: 'Alle' },
];

interface Props {
  isPublicMode: boolean;
}

function isTabKey(value: string | null): value is TabKey {
  return value === 'schnellsuche' || value === 'unternehmen' || value === 'frage';
}

export default function BeneficiaryWorkspace({ isPublicMode }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = isTabKey(searchParams.get('tab')) ? (searchParams.get('tab') as TabKey) : 'schnellsuche';
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);

  // Country-Filter wird tabübergreifend geteilt
  const [countryCode, setCountryCode] = useState<CountryCode | ''>('DE');

  // Karte ist immer sichtbar; in Tab "unternehmen" filtert sie auf Suchtreffer.
  // Die Suchkomponente meldet ihre aktuellen Treffer-Namen via Callback hoch.
  const [highlightedNames, setHighlightedNames] = useState<string[]>([]);

  // KI-Frage-State
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [tokenCount, setTokenCount] = useState<number>();
  const [model, setModel] = useState<string>();
  const [tokPerS, setTokPerS] = useState<number>();
  const [error, setError] = useState<string>();
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [streamStartedAt, setStreamStartedAt] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Tab-Wechsel synchron in URL spiegeln. Beim Verlassen der Unternehmenssuche
  // wird der Karten-Filter zurückgesetzt, damit die Default-Karte sichtbar ist.
  const handleTabChange = useCallback(
    (key: TabKey) => {
      setActiveTab(key);
      if (key !== 'unternehmen') setHighlightedNames([]);
      const next = new URLSearchParams(searchParams);
      if (key === 'schnellsuche') {
        next.delete('tab');
      } else {
        next.set('tab', key);
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  // Cleanup laufender Streams beim Unmount
  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  const handleSubmit = useCallback(() => {
    if (!prompt.trim() || streaming) return;
    setResponse('');
    setStreaming(true);
    setError(undefined);
    setTokenCount(undefined);
    setStreamStatus(null);
    setStreamStartedAt(Date.now());

    controllerRef.current = streamSSE(
      '/workshop/stream',
      {
        scenario: 6,
        prompt,
        documents: [],
        with_context: true,
        ...(countryCode ? { country_code: countryCode } : {}),
      },
      (token) => {
        setStreamStatus(null);
        setResponse((prev) => prev + token);
      },
      (doneInfo) => {
        setStreaming(false);
        setStreamStatus(null);
        setTokenCount(doneInfo.token_count);
        setModel(doneInfo.model);
        setTokPerS(doneInfo.tok_per_s);
      },
      (err) => {
        setStreaming(false);
        setStreamStatus(null);
        setError(err);
      },
      (state) => setStreamStatus(state),
    );
  }, [prompt, countryCode, streaming]);

  const handleStop = () => {
    controllerRef.current?.abort();
    setStreaming(false);
  };

  const activeDescription = useMemo(
    () => TABS.find((t) => t.key === activeTab)?.description ?? '',
    [activeTab],
  );

  const countryPicker = (
    <div
      role="tablist"
      aria-label="Begünstigtenverzeichnis nach Land filtern"
      className="inline-flex rounded-full border border-rose-200 bg-white p-1 text-xs font-semibold dark:border-rose-900/60 dark:bg-slate-900"
    >
      {COUNTRY_OPTIONS.map((option) => {
        const active = countryCode === option.value;
        return (
          <button
            key={option.label}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => setCountryCode(option.value)}
            className={`rounded-full px-4 py-1.5 transition ${
              active
                ? 'bg-rose-600 text-white shadow dark:bg-rose-500'
                : 'text-slate-600 hover:bg-rose-100 dark:text-slate-300 dark:hover:bg-rose-900/40'
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );

  return (
    <div className="space-y-5">
      {/* ── Tab-Pill-Bar + Country-Filter ───────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="Begünstigtenverzeichnis-Werkzeuge"
          className="inline-flex flex-wrap gap-1 rounded-full border border-slate-200 bg-white p-1 shadow-[0_18px_60px_-44px_rgba(15,23,42,0.45)] dark:border-slate-700 dark:bg-slate-900"
        >
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => handleTabChange(tab.key)}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition ${
                  active
                    ? 'bg-rose-600 text-white shadow-[0_12px_28px_-18px_rgba(225,29,72,0.65)] dark:bg-rose-500'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700/80 dark:text-rose-300/80">
            Land
          </span>
          {countryPicker}
        </div>
      </div>

      <p className="text-xs text-slate-500 dark:text-slate-400">{activeDescription}</p>

      {/* ── Karte (immer sichtbar) ─────────────────────────────── */}
      <BeneficiaryMap
        countryCode={countryCode}
        highlightNames={activeTab === 'unternehmen' ? highlightedNames : null}
      />

      {/* ── Tab-spezifischer Inhalt unter der Karte ────────────── */}
      {activeTab === 'schnellsuche' && (
        <BeneficiaryAnalyticsPanel
          countryCode={countryCode}
          onSelectPrompt={(value) => {
            setPrompt(value);
            handleTabChange('frage');
          }}
        />
      )}

      {activeTab === 'unternehmen' && (
        <BeneficiaryCompanySearch
          countryCode={countryCode}
          onResultsChange={setHighlightedNames}
        />
      )}

      {activeTab === 'frage' && (
        <div className="rounded-[28px] border-2 border-rose-300/60 bg-gradient-to-br from-rose-50/60 via-white to-amber-50/40 p-6 shadow-[0_24px_80px_-44px_rgba(225,29,72,0.45)] backdrop-blur dark:border-rose-900/60 dark:from-rose-950/30 dark:via-slate-900/80 dark:to-amber-950/20">
          <div className="mb-4 flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-500 to-amber-500 text-white shadow-lg">
              <Sparkles size={20} />
            </span>
            <div className="flex-1">
              <h2 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
                KI-Auswertung der Begünstigtenverzeichnisse
              </h2>
              <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                {isPublicMode
                  ? 'Stellen Sie freie Fragen zur konsolidierten Datenlage. Die Auswertung läuft lokal gegen die geladenen Begünstigtenverzeichnisse aus EFRE, ESF+, JTF, ISF und AMIF.'
                  : 'Stellen Sie freie Fragen direkt an die KI. Die Auswertung läuft gegen die aktuell eingelesenen Begünstigtenlisten.'}
              </p>
            </div>
          </div>

          <div className="relative rounded-[20px] border-2 border-rose-200 bg-white shadow-[0_18px_60px_-48px_rgba(225,29,72,0.6)] focus-within:border-rose-400 focus-within:ring-2 focus-within:ring-rose-200 dark:border-rose-900/70 dark:bg-slate-950 dark:focus-within:border-rose-500">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder={'Stellen Sie eine Frage an die KI… z.B. „Welche Träger dominieren in der Bauindustrie?"   ⏎ zum Senden'}
              rows={3}
              className="min-h-[100px] w-full resize-none rounded-[20px] bg-transparent px-5 pt-4 pb-14 text-base text-slate-900 placeholder:text-slate-400 focus:outline-none dark:text-slate-100"
              aria-label="Frage an die KI"
            />
            <button
              onClick={handleSubmit}
              disabled={!prompt.trim() || streaming}
              className="absolute bottom-3 right-3 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-rose-600 to-amber-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md transition hover:from-rose-700 hover:to-amber-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {streaming ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
              {streaming ? 'Generiert…' : 'Frage stellen'}
            </button>
          </div>

          {/* Vordefinierte Beispielfragen */}
          <div className="mt-4">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <Sparkles size={11} className="text-rose-500" />
              Beispielfragen — Klicken zum Übernehmen
            </div>
            <div className="flex flex-wrap gap-2">
              {QUESTION_PRESETS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => setPrompt(q)}
                  disabled={streaming}
                  className="group inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 shadow-sm transition hover:border-rose-400 hover:bg-rose-50 hover:text-rose-700 hover:shadow disabled:opacity-40 dark:border-rose-900/50 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-rose-600 dark:hover:bg-rose-950/30"
                >
                  <Sparkles size={11} className="text-rose-400 group-hover:text-rose-500" />
                  {q}
                </button>
              ))}
            </div>
          </div>

          {!isPublicMode && (
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-rose-200/60 pt-3 text-xs dark:border-rose-900/40">
              <span className="text-slate-500 dark:text-slate-400">Andere Suchwege:</span>
              <Link
                to="/company-search"
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-slate-700 hover:bg-rose-100/50 dark:text-slate-300 dark:hover:bg-rose-950/30"
              >
                <Search size={12} /> Unternehmenssuche
              </Link>
              <Link
                to="/dataframes"
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-slate-700 hover:bg-rose-100/50 dark:text-slate-300 dark:hover:bg-rose-950/30"
              >
                <Database size={12} /> Datenraum (SQL)
              </Link>
            </div>
          )}

          <div className="mt-5">
            <LlmResponsePanel
              response={response}
              streaming={streaming}
              tokenCount={tokenCount}
              model={model}
              tokPerS={tokPerS}
              error={error}
              onStop={handleStop}
              onRetry={handleSubmit}
              status={streamStatus}
              startedAt={streamStartedAt}
            />
          </div>
        </div>
      )}
    </div>
  );
}
