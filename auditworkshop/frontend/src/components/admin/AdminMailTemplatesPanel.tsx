import { useEffect, useState } from 'react';
import {
  Loader2, Mail, Save, RotateCcw, Eye, Check, AlertTriangle, X,
} from 'lucide-react';
import { getWorkshopAuthHeaders } from '../../lib/api';

interface TemplateListEntry {
  key: string;
  subject: string;
  description: string | null;
  placeholders: string[];
  updated_at: string | null;
  is_overridden: boolean;
}

interface TemplateDetail extends TemplateListEntry {
  body: string;
  default_subject: string;
  default_body: string;
}

const KEY_LABELS: Record<string, string> = {
  invite: 'Einladung mit Setup-Link',
  confirmation: 'Anmeldebestätigung (Teilnehmer)',
  admin_notify: 'Admin-Benachrichtigung (alter /register-Pfad)',
  signup_alert: 'Admin-Benachrichtigung (Selbst-Anmeldung)',
};

export default function AdminMailTemplatesPanel() {
  const [list, setList] = useState<TemplateListEntry[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>('invite');
  const [detail, setDetail] = useState<TemplateDetail | null>(null);
  const [draftSubject, setDraftSubject] = useState('');
  const [draftBody, setDraftBody] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [savedFlash, setSavedFlash] = useState(false);
  const [previewModal, setPreviewModal] = useState<{ subject: string; body: string } | null>(null);
  const [resetConfirm, setResetConfirm] = useState(false);

  const loadList = async () => {
    setError('');
    try {
      const r = await fetch('/api/admin/mail-templates', { headers: getWorkshopAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d: TemplateListEntry[] = await r.json();
      setList(d);
      if (d.length > 0 && !d.find((t) => t.key === selectedKey)) {
        setSelectedKey(d[0].key);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Vorlagenliste.');
    }
  };

  const loadDetail = async (key: string) => {
    setLoading(true);
    setError('');
    try {
      const r = await fetch(`/api/admin/mail-templates/${key}`, { headers: getWorkshopAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d: TemplateDetail = await r.json();
      setDetail(d);
      setDraftSubject(d.subject);
      setDraftBody(d.body);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden des Templates.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadList(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (selectedKey) loadDetail(selectedKey); }, [selectedKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const isDirty = !!detail && (draftSubject !== detail.subject || draftBody !== detail.body);

  const save = async () => {
    if (!detail) return;
    setSaving(true);
    setError('');
    try {
      const r = await fetch(`/api/admin/mail-templates/${detail.key}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
        body: JSON.stringify({ subject: draftSubject, body: draftBody }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${r.status}`);
      }
      const d: TemplateDetail = await r.json();
      setDetail(d);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Speichern fehlgeschlagen.');
    } finally {
      setSaving(false);
    }
  };

  const previewLive = async () => {
    if (!detail) return;
    setError('');
    try {
      const r = await fetch(`/api/admin/mail-templates/${detail.key}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
        body: JSON.stringify({ subject: draftSubject, body: draftBody }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${r.status}`);
      }
      const d = await r.json();
      setPreviewModal({ subject: d.subject, body: d.body });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Vorschau fehlgeschlagen.');
    }
  };

  const resetToDefault = async () => {
    if (!detail) return;
    setResetConfirm(false);
    setError('');
    try {
      const r = await fetch(`/api/admin/mail-templates/${detail.key}/reset`, {
        method: 'POST',
        headers: getWorkshopAuthHeaders(),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d: TemplateDetail = await r.json();
      setDetail(d);
      setDraftSubject(d.subject);
      setDraftBody(d.body);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Zurücksetzen fehlgeschlagen.');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white inline-flex items-center gap-2">
          <Mail size={18} /> Mail-Vorlagen
        </h2>
        <p className="text-xs text-slate-500 ml-2">
          Body und Betreff aller automatischen E-Mails. Änderungen wirken sofort.
        </p>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 flex items-center gap-2">
          <AlertTriangle size={14} />
          <span className="break-all">{error}</span>
          <button onClick={() => setError('')} className="ml-auto"><X size={14} /></button>
        </div>
      )}

      {/* Tabs für die einzelnen Vorlagen */}
      <div className="flex flex-wrap gap-1 rounded-2xl bg-slate-100 dark:bg-slate-800 p-1">
        {list.map((t) => (
          <button
            key={t.key}
            onClick={() => setSelectedKey(t.key)}
            className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs transition ${
              selectedKey === t.key
                ? 'bg-white text-slate-900 shadow dark:bg-slate-700 dark:text-white'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <span>{KEY_LABELS[t.key] || t.key}</span>
            {t.is_overridden && (
              <span className="text-[10px] uppercase tracking-wider bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 px-1.5 py-0.5 rounded">
                bearbeitet
              </span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={20} className="animate-spin text-slate-400" />
        </div>
      ) : detail ? (
        <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 space-y-4">
          {detail.description && (
            <p className="text-xs text-slate-500 italic">{detail.description}</p>
          )}

          {/* Subject */}
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">Betreff</label>
            <input
              value={draftSubject}
              onChange={(e) => setDraftSubject(e.target.value)}
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm font-mono"
            />
          </div>

          {/* Body */}
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">
              Body (Plain-Text mit Jinja-Platzhaltern <code>{'{{ var }}'}</code>)
            </label>
            <textarea
              value={draftBody}
              onChange={(e) => setDraftBody(e.target.value)}
              rows={26}
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs font-mono leading-relaxed"
              spellCheck={false}
            />
          </div>

          {/* Platzhalter-Liste */}
          {detail.placeholders.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">Verfügbare Platzhalter:</div>
              <div className="flex flex-wrap gap-1.5">
                {detail.placeholders.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => navigator.clipboard.writeText(`{{ ${p} }}`)}
                    title="In Zwischenablage kopieren"
                    className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-slate-300 cursor-pointer"
                  >
                    {`{{ ${p} }}`}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-slate-400 mt-1">Klick auf einen Platzhalter kopiert ihn in die Zwischenablage.</p>
            </div>
          )}

          {/* Buttons */}
          <div className="flex flex-wrap gap-2 items-center pt-2 border-t border-slate-200 dark:border-slate-800">
            <button
              onClick={previewLive}
              className="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              <Eye size={14} /> Vorschau
            </button>
            <button
              onClick={save}
              disabled={!isDirty || saving}
              className={`inline-flex items-center gap-1 text-sm px-4 py-1.5 rounded text-white transition-colors ${
                savedFlash ? 'bg-emerald-500' : 'bg-emerald-600 hover:bg-emerald-700'
              } disabled:bg-slate-300`}
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : savedFlash ? <Check size={14} /> : <Save size={14} />}
              {savedFlash ? 'Gespeichert' : 'Speichern'}
            </button>
            <div className="ml-auto flex items-center gap-2">
              {detail.is_overridden && (
                <span className="text-[11px] text-slate-400">
                  zuletzt geändert: {detail.updated_at ? detail.updated_at.slice(0, 16).replace('T', ' ') : '–'}
                </span>
              )}
              {detail.is_overridden && (
                <button
                  onClick={() => setResetConfirm(true)}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300"
                  title="Auf hartcodierten Default zurücksetzen"
                >
                  <RotateCcw size={12} /> Auf Default zurücksetzen
                </button>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {/* Vorschau-Modal */}
      {previewModal && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 px-4">
          <div className="max-w-3xl w-full max-h-[85vh] rounded-3xl bg-white dark:bg-slate-900 shadow-2xl flex flex-col">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 dark:border-slate-800">
              <h3 className="font-semibold text-slate-900 dark:text-white">Vorschau mit Demo-Daten</h3>
              <button onClick={() => setPreviewModal(null)} className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-3 overflow-y-auto flex-1">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Betreff</div>
                <div className="text-sm text-slate-900 dark:text-white font-medium">{previewModal.subject}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Body</div>
                <pre className="text-xs font-mono whitespace-pre-wrap leading-relaxed text-slate-700 dark:text-slate-200 bg-slate-50 dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700">{previewModal.body}</pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reset-Bestätigung */}
      {resetConfirm && detail && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 px-4">
          <div className="max-w-md w-full rounded-3xl bg-white dark:bg-slate-900 p-6 shadow-2xl">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-2 inline-flex items-center gap-2">
              <RotateCcw size={16} /> Vorlage zurücksetzen?
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Die Bearbeitung der Vorlage „{KEY_LABELS[detail.key] || detail.key}" wird verworfen und der hartcodierte Default
              wieder aktiv. Diese Aktion kann nicht rückgängig gemacht werden.
            </p>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setResetConfirm(false)} className="text-sm px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                Abbrechen
              </button>
              <button onClick={resetToDefault} className="text-sm px-3 py-1.5 rounded bg-rose-600 text-white hover:bg-rose-700">
                Zurücksetzen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
