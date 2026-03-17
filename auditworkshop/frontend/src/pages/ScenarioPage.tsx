import { useState, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Send, Sparkles, FolderOpen, Loader2, Database, ShieldCheck, Building2,
  FileText, RotateCcw, Info,
} from 'lucide-react';
import LlmResponsePanel from '../components/workshop/LlmResponsePanel';
import DocumentDropzone from '../components/workshop/DocumentDropzone';
import BeneficiaryMap from '../components/workshop/BeneficiaryMap';
import { seedDemoData, streamSSE } from '../lib/api';

const SCENARIO_INFO: Record<number, {
  title: string;
  description: string;
  placeholder: string;
  accent: string;
  eyebrow: string;
  hint: string;
}> = {
  1: {
    title: 'Dokumentenanalyse',
    description: 'Laden Sie einen Förderbescheid hoch. Die KI extrahiert alle bindenden Auflagen und Nachweispflichten.',
    placeholder: 'z.B. "Welche Auflagen enthält der Bescheid?"',
    accent: 'from-cyan-700 via-sky-700 to-blue-600',
    eyebrow: 'Bescheide lesen und strukturieren',
    hint: 'Laden Sie einen Förderbescheid hoch oder nutzen Sie das Demo-Dokument.',
  },
  2: {
    title: 'Checklisten-KI',
    description: 'Die KI bewertet VKO-Prüfpunkte auf Basis vorgelegter Unterlagen. Nutzen Sie die Projektverwaltung für das vollwertige Checklisten-System.',
    placeholder: 'z.B. "Bewerte die Vergabeprüfpunkte"',
    accent: 'from-indigo-700 via-slate-900 to-cyan-700',
    eyebrow: 'Der vollwertige Prüfworkflow',
    hint: 'Klicken Sie "Demo-Checkliste öffnen" um mit 30 VKO-Prüfpunkten zu starten.',
  },
  3: {
    title: 'Halluzinations-Demo',
    description: 'Vergleichen Sie KI-Antworten ohne und mit RAG-Kontext. Der Umschalter zeigt den Unterschied.',
    placeholder: 'z.B. "Welche Schwellenwerte gelten für die Vergabe nach VO 2021/1060?"',
    accent: 'from-amber-600 via-orange-600 to-rose-600',
    eyebrow: 'Wissensabgleich gegen freie Modellantwort',
    hint: 'Stellen Sie dieselbe Frage einmal mit und einmal ohne Wissensabgleich -- der Vergleich zeigt das Halluzinationsrisiko.',
  },
  4: {
    title: 'Berichtsentwurf',
    description: 'Geben Sie Prüffeststellungen ein. Die KI formuliert eine Berichtpassage im Verwaltungsstil.',
    placeholder: 'z.B. "Vergabevermerk fehlt. Publizitätspflichten nicht eingehalten."',
    accent: 'from-emerald-700 via-teal-700 to-cyan-700',
    eyebrow: 'Verwaltungsstil statt Marketingtext',
    hint: 'Geben Sie Prüffeststellungen als Stichpunkte ein. Die KI formuliert daraus eine Berichtpassage.',
  },
  5: {
    title: 'Vorab-Upload & RAG',
    description: 'Laden Sie eigene Dokumente in die Wissensdatenbank und stellen Sie Fragen dazu.',
    placeholder: 'z.B. "Was steht in Artikel 74 zur Verwaltungsprüfung?"',
    accent: 'from-fuchsia-700 via-violet-700 to-indigo-700',
    eyebrow: 'Eigene Unterlagen als Kontext',
    hint: 'Laden Sie zuerst eigene Dokumente in die Wissensdatenbank (/knowledge), dann stellen Sie hier Fragen.',
  },
  6: {
    title: 'Begünstigtenverzeichnis',
    description: 'Analyse des hessischen EFRE-Begünstigtenverzeichnisses mit statistischen Auswertungen.',
    placeholder: 'z.B. "Welche Kommunen erhalten die höchste Förderung?"',
    accent: 'from-rose-700 via-orange-700 to-amber-600',
    eyebrow: 'Raumbezogene Förderanalyse',
    hint: 'Laden Sie ein Begünstigtenverzeichnis als XLSX hoch. Die Karte wird automatisch befüllt.',
  },
};

export default function ScenarioPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const num = parseInt(id || '1', 10);
  const info = SCENARIO_INFO[num] || SCENARIO_INFO[1];

  const [prompt, setPrompt] = useState('');
  const [documents, setDocuments] = useState<string[]>([]);
  const [withContext, setWithContext] = useState(true);
  const [response, setResponse] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [tokenCount, setTokenCount] = useState<number>();
  const [model, setModel] = useState<string>();
  const [tokPerS, setTokPerS] = useState<number>();
  const [error, setError] = useState<string>();
  const [bootstrappingDemo, setBootstrappingDemo] = useState(false);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [splitResponses, setSplitResponses] = useState<{without?: string; with?: string}>({});
  const controllerRef = useRef<AbortController | null>(null);

  const handleSubmit = useCallback(() => {
    if (!prompt.trim() || streaming) return;
    setResponse('');
    setStreaming(true);
    setError(undefined);
    setTokenCount(undefined);

    let accumulated = '';
    controllerRef.current = streamSSE(
      '/workshop/stream',
      { scenario: num, prompt, documents, with_context: withContext },
      (token) => {
        accumulated += token;
        setResponse((prev) => prev + token);
      },
      (doneInfo) => {
        setStreaming(false);
        setTokenCount(doneInfo.token_count);
        setModel(doneInfo.model);
        setTokPerS(doneInfo.tok_per_s);
        // Szenario 3: Antwort in Split-View speichern
        if (num === 3) {
          setSplitResponses((prev) => ({
            ...prev,
            [withContext ? 'with' : 'without']: accumulated,
          }));
        }
      },
      (err) => {
        setStreaming(false);
        setError(err);
      },
    );
  }, [prompt, num, documents, withContext, streaming]);

  const handleStop = () => {
    controllerRef.current?.abort();
    setStreaming(false);
  };

  const handleOpenDemoChecklist = async () => {
    setBootstrappingDemo(true);
    try {
      const result = await seedDemoData();
      if (result.project_id && result.checklist_id) {
        navigate(`/projects/${result.project_id}/checklists/${result.checklist_id}`);
        return;
      }
      navigate('/projects');
    } finally {
      setBootstrappingDemo(false);
    }
  };

  const loadDemoDocument = async () => {
    const endpoint = num === 1
      ? '/api/documents/demo/foerderbescheid'
      : '/api/documents/demo/prueffeststellungen';
    setLoadingDemo(true);
    try {
      const res = await fetch(endpoint);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPrompt(data.text || data.content || '');
    } catch {
      setError('Demo-Dokument konnte nicht geladen werden.');
    } finally {
      setLoadingDemo(false);
    }
  };

  return (
    <div className="space-y-6">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600">
        <ArrowLeft size={16} /> Zurück
      </Link>

      <section className={`relative overflow-hidden rounded-[32px] border border-white/70 bg-gradient-to-br ${info.accent} px-7 py-8 text-white shadow-[0_34px_100px_-52px_rgba(15,23,42,0.95)]`}>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.18),rgba(255,255,255,0)_40%)]" />
        <div className="relative flex items-start gap-5">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white/20 text-2xl font-bold backdrop-blur-sm">
            {num}
          </span>
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.25em] text-white/60">
              Workshop-Szenario {num} &middot; {info.eyebrow}
            </div>
            <h1 className="text-3xl font-semibold tracking-tight lg:text-4xl">
              {info.title}
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-white/84 lg:text-base">
              {info.description}
            </p>
          </div>
        </div>
      </section>

      {info.hint && (
        <div className="rounded-xl border border-sky-200 bg-sky-50/50 px-4 py-3 text-sm text-sky-700 dark:border-sky-800 dark:bg-sky-950/20 dark:text-sky-400 flex items-start gap-2">
          <Info size={16} className="shrink-0 mt-0.5" />
          <span>{info.hint}</span>
        </div>
      )}

      {num === 2 && (
        <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[28px] border border-slate-200/80 bg-white/85 p-6 shadow-[0_24px_80px_-48px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
            <div className="mb-4 flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                <Sparkles size={20} />
              </span>
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Empfohlener Demo-Einstieg</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">Öffnet die echte Checklistenoberfläche statt eines Einzelprompts.</p>
              </div>
            </div>
            <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
              <div className="rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">25 vorkonfigurierte Prüfpunkte inklusive Status-Tracking und Evidence.</div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70">Bulk-Bewertung, Akzeptieren, Bearbeiten und Ablehnen in einem konsistenten Arbeitsbereich.</div>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                onClick={handleOpenDemoChecklist}
                disabled={bootstrappingDemo}
                className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-70 dark:bg-indigo-500 dark:hover:bg-indigo-400"
              >
                {bootstrappingDemo ? <Loader2 size={16} className="animate-spin" /> : <FolderOpen size={16} />}
                Demo-Checkliste öffnen
              </button>
              <Link to="/projects" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">
                Projektübersicht
              </Link>
            </div>
          </div>

          <div className="rounded-[28px] border border-slate-200/80 bg-white/85 p-6 shadow-[0_24px_80px_-48px_rgba(15,23,42,0.5)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-white">
              <ShieldCheck size={16} className="text-emerald-500" />
              Workshop-Mehrwert
            </div>
            <ul className="space-y-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
              <li>KI-Text bleibt als Entwurf sichtbar und nachvollziehbar.</li>
              <li>Fundstellen und RAG-Treffer werden direkt am Prüffall gespeichert.</li>
              <li>Die Oberfläche bildet den tatsächlichen Prüfmodus besser ab als ein Chatfenster.</li>
            </ul>
          </div>
        </section>
      )}

      {[1, 4, 5].includes(num) && (
        <div className="mb-2">
          <div className="flex items-start gap-3">
            <div className="flex-1">
              <DocumentDropzone onFilesRead={setDocuments} />
            </div>
            {[1, 4].includes(num) && (
              <button
                onClick={loadDemoDocument}
                disabled={loadingDemo}
                className="shrink-0 mt-2 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {loadingDemo ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}
                Demo laden
              </button>
            )}
          </div>
        </div>
      )}

      {num === 6 && <BeneficiaryMap className="mb-2" />}

      {num === 3 && (
        <div className="mb-4 flex items-center gap-3 rounded-[26px] border border-amber-200 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-900/20">
          <label className="flex items-center gap-2 text-sm font-medium text-amber-800 dark:text-amber-300 cursor-pointer">
            <input
              type="checkbox"
              checked={withContext}
              onChange={(e) => setWithContext(e.target.checked)}
              className="rounded border-amber-300"
            />
            RAG-Kontext aktivieren (Wissensdatenbank)
          </label>
          <span className="text-xs text-amber-600 dark:text-amber-400">
            {withContext ? 'Mit Kontext — reduziert Halluzinationen' : 'Ohne Kontext — zeigt Halluzinationsrisiko'}
          </span>
        </div>
      )}

      {num === 6 && (
        <div className="rounded-[26px] border border-slate-200/80 bg-white/85 p-5 shadow-[0_20px_70px_-46px_rgba(15,23,42,0.58)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-white">
            <Database size={16} className="text-rose-500" />
            Statistikfragen sind jetzt an die geladenen Verzeichnisse gebunden
          </div>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            Die KI erhält für Szenario 6 nur aggregierte Kennzahlen und Spitzendaten aus den aktuell eingelesenen Begünstigtenlisten. Antworten bleiben damit an die reale Datenlage gekoppelt.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link to="/company-search" className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-rose-500 dark:hover:bg-rose-400">
              <Building2 size={15} />
              Unternehmenssuche öffnen
            </Link>
            <Link to="/dataframes" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">
              <Database size={15} />
              Datenraum öffnen
            </Link>
          </div>
        </div>
      )}

      {num !== 2 && (
        <>
          <div className="mb-6 flex gap-2">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
              placeholder={info.placeholder}
              rows={3}
              className="flex-1 rounded-[26px] border border-slate-200 bg-white/85 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 shadow-[0_18px_60px_-48px_rgba(15,23,42,0.75)] backdrop-blur focus:outline-none focus:ring-2 focus:ring-cyan-500 dark:border-slate-800 dark:bg-slate-900/75 dark:text-slate-100"
              aria-label="Prompt eingeben"
            />
            <button
              onClick={handleSubmit}
              disabled={!prompt.trim() || streaming}
              className="self-end rounded-full bg-slate-900 px-5 py-3 text-white transition-colors hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-700"
              aria-label="Absenden"
            >
              <Send size={18} />
            </button>
          </div>

          <LlmResponsePanel
            response={response}
            streaming={streaming}
            tokenCount={tokenCount}
            model={model}
            tokPerS={tokPerS}
            error={error}
            onStop={handleStop}
            onRetry={handleSubmit}
          />

          {/* Szenario 3: Split-View Vergleich ohne/mit RAG */}
          {num === 3 && splitResponses.without && splitResponses.with && (
            <div className="mt-6 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Vergleichsansicht</h3>
                <button
                  onClick={() => setSplitResponses({})}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  <RotateCcw size={12} /> Vergleich zurücksetzen
                </button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-[20px] border-2 border-red-300 bg-white/90 overflow-hidden dark:border-red-700 dark:bg-slate-900/80">
                  <div className="bg-red-50 px-4 py-2 text-sm font-medium text-red-700 dark:bg-red-900/30 dark:text-red-400">
                    Ohne RAG-Kontext
                  </div>
                  <div className="p-4 max-h-[50vh] overflow-y-auto">
                    <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-sans leading-relaxed">{splitResponses.without}</pre>
                  </div>
                </div>
                <div className="rounded-[20px] border-2 border-emerald-300 bg-white/90 overflow-hidden dark:border-emerald-700 dark:bg-slate-900/80">
                  <div className="bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                    Mit RAG-Kontext
                  </div>
                  <div className="p-4 max-h-[50vh] overflow-y-auto">
                    <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-sans leading-relaxed">{splitResponses.with}</pre>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
