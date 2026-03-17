import { useState } from 'react';
import { Check, X, Edit3, RotateCcw, Sparkles, Loader2 } from 'lucide-react';
import type { RemarkAiStatus } from '../../lib/api';

interface Props {
  remarkAi: string | null;
  remarkAiEdited: string | null;
  status: RemarkAiStatus | null;
  rejectFeedback: string | null;
  onAccept: () => void;
  onReject: (feedback?: string) => void;
  onEdit: (text: string) => void;
  onGenerate: () => void;
  generating?: boolean;
}

export default function AiRemarkCard({
  remarkAi, remarkAiEdited, status, rejectFeedback,
  onAccept, onReject, onEdit, onGenerate, generating,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectText, setRejectText] = useState('');

  const displayText = remarkAiEdited || remarkAi;
  let parsedRemark: {
    status?: string;
    begruendung?: string;
    fundstellen?: string[];
  } | null = null;

  if (displayText) {
    try {
      const candidate = JSON.parse(displayText);
      if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
        parsedRemark = {
          status: typeof candidate.status === 'string' ? candidate.status : undefined,
          begruendung: typeof candidate.begruendung === 'string' ? candidate.begruendung : undefined,
          fundstellen: Array.isArray(candidate.fundstellen)
            ? candidate.fundstellen.filter((entry: unknown): entry is string => typeof entry === 'string')
            : undefined,
        };
      }
    } catch {
      parsedRemark = null;
    }
  }

  const startEdit = () => {
    setEditText(displayText || '');
    setEditing(true);
  };

  const saveEdit = () => {
    onEdit(editText);
    setEditing(false);
  };

  const submitReject = () => {
    onReject(rejectText || undefined);
    setShowRejectInput(false);
    setRejectText('');
  };

  // No AI remark yet
  if (!remarkAi && !generating) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 p-4 text-center">
        <button
          onClick={onGenerate}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Sparkles size={16} /> KI-Bemerkung generieren
        </button>
      </div>
    );
  }

  if (generating) {
    return (
      <div className="rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/20 p-4 flex items-center gap-3">
        <Loader2 size={18} className="animate-spin text-indigo-500" />
        <span className="text-sm text-indigo-700 dark:text-indigo-300">KI generiert Bemerkung…</span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500 flex items-center gap-1">
          <Sparkles size={12} /> KI-Bemerkung
        </span>
      </div>

      <div className="p-4">
        {editing ? (
          <div className="space-y-2">
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={5}
              className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm resize-none"
              aria-label="KI-Bemerkung bearbeiten"
            />
            <div className="flex gap-2">
              <button onClick={saveEdit} className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">Speichern</button>
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">Abbrechen</button>
            </div>
          </div>
        ) : (
          <div className="mb-3">
            {parsedRemark ? (
              <div className="space-y-3">
                {parsedRemark.status && (
                  <div className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {parsedRemark.status.replace(/_/g, ' ')}
                  </div>
                )}
                {parsedRemark.begruendung && (
                  <p className="text-sm leading-7 text-slate-700 dark:text-slate-300">
                    {parsedRemark.begruendung}
                  </p>
                )}
                {parsedRemark.fundstellen && parsedRemark.fundstellen.length > 0 && (
                  <div>
                    <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-slate-400">Fundstellen</div>
                    <div className="space-y-2">
                      {parsedRemark.fundstellen.map((entry) => (
                        <div key={entry} className="rounded-2xl bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800/70 dark:text-slate-300">
                          {entry}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-sans leading-relaxed">
                {displayText}
              </pre>
            )}
          </div>
        )}

        {/* Reject feedback display */}
        {status === 'rejected' && rejectFeedback && (
          <div className="mt-2 p-2 bg-red-50 dark:bg-red-900/20 rounded text-xs text-red-600 dark:text-red-400">
            Ablehnungsgrund: {rejectFeedback}
          </div>
        )}

        {/* Reject input */}
        {showRejectInput && (
          <div className="mt-2 space-y-2">
            <textarea
              value={rejectText}
              onChange={(e) => setRejectText(e.target.value)}
              placeholder="Begründung für Ablehnung (optional)…"
              rows={2}
              className="w-full px-3 py-2 rounded-lg border border-red-300 dark:border-red-700 bg-white dark:bg-slate-800 text-sm resize-none"
              aria-label="Ablehnungsbegründung"
            />
            <div className="flex gap-2">
              <button onClick={submitReject} className="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">Ablehnen</button>
              <button onClick={() => setShowRejectInput(false)} className="px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">Abbrechen</button>
            </div>
          </div>
        )}

        {/* Action buttons */}
        {!editing && !showRejectInput && (
          <div className="flex gap-2 mt-3">
            {status === 'draft' && (
              <>
                <button onClick={onAccept} className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">
                  <Check size={14} /> Akzeptieren
                </button>
                <button onClick={startEdit} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">
                  <Edit3 size={14} /> Bearbeiten
                </button>
                <button onClick={() => setShowRejectInput(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">
                  <X size={14} /> Ablehnen
                </button>
              </>
            )}
            {status === 'rejected' && (
              <>
                <button onClick={onGenerate} className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-xs rounded-lg hover:bg-indigo-700">
                  <RotateCcw size={14} /> Regenerieren
                </button>
                <button onClick={startEdit} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">
                  <Edit3 size={14} /> Bearbeiten
                </button>
              </>
            )}
            {(status === 'accepted' || status === 'edited') && (
              <button onClick={startEdit} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">
                <Edit3 size={14} /> Bearbeiten
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
