import { useRef, useEffect, useState } from 'react';
import { Loader2, StopCircle, RotateCcw, Copy, Check } from 'lucide-react';

interface Props {
  response: string;
  streaming: boolean;
  tokenCount?: number;
  model?: string;
  tokPerS?: number;
  error?: string;
  onStop?: () => void;
  onRetry?: () => void;
}

export default function LlmResponsePanel({
  response, streaming, tokenCount, model, tokPerS, error, onStop, onRetry,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (streaming) endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [response, streaming]);

  const handleCopy = async () => {
    if (!response) return;
    try {
      await navigator.clipboard.writeText(response);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* Clipboard nicht verfügbar */ }
  };

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          {streaming && <Loader2 size={14} className="animate-spin text-indigo-500" />}
          <span>{streaming ? 'Generiere Antwort…' : 'KI-Antwort'}</span>
        </div>
        <div className="flex items-center gap-2">
          {!streaming && response && (
            <button
              onClick={handleCopy}
              className="inline-flex items-center gap-1 text-slate-400 hover:text-indigo-500 p-1 text-xs transition"
              aria-label="Antwort kopieren"
            >
              {copied ? <><Check size={14} className="text-emerald-500" /> <span className="text-emerald-500">Kopiert!</span></> : <Copy size={14} />}
            </button>
          )}
          {streaming && onStop && (
            <button onClick={onStop} className="text-red-500 hover:text-red-700 p-1" aria-label="Stoppen">
              <StopCircle size={16} />
            </button>
          )}
          {!streaming && response && onRetry && (
            <button onClick={onRetry} className="text-slate-400 hover:text-indigo-500 p-1" aria-label="Neu generieren">
              <RotateCcw size={16} />
            </button>
          )}
          {tokenCount !== undefined && (
            <span className="text-xs text-slate-400">
              {tokenCount} Token{model && ` · ${model}`}{tokPerS !== undefined && ` · ${tokPerS} tok/s`}
            </span>
          )}
        </div>
      </div>
      <div className="p-4 max-h-[60vh] overflow-y-auto">
        {error ? (
          <p className="text-red-500 text-sm">{error}</p>
        ) : streaming && !response ? (
          <div className="flex items-center gap-3 py-6 px-4">
            <div className="flex gap-1">
              <div className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce glow-cyan [animation-delay:0ms]" />
              <div className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce glow-cyan [animation-delay:150ms]" />
              <div className="h-2 w-2 rounded-full bg-indigo-400 animate-bounce glow-cyan [animation-delay:300ms]" />
            </div>
            <span className="text-sm text-slate-500">KI verarbeitet die Anfrage...</span>
          </div>
        ) : response ? (
          <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-sans leading-relaxed">{response}{streaming && <span className="inline-block w-2 h-4 ml-0.5 bg-indigo-500 dark:bg-indigo-400 animate-cursor rounded-sm" />}</pre>
        ) : (
          <p className="text-sm text-slate-400 italic">Noch keine Antwort generiert.</p>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
