import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2, Sparkles, Plus, Trash2, Download, FileDown } from 'lucide-react';
import StatusBadge from '../components/checklist/StatusBadge';
import AiRemarkCard from '../components/checklist/AiRemarkCard';
import EvidenceCard from '../components/checklist/EvidenceCard';
import Breadcrumb from '../components/layout/Breadcrumb';
import {
  getChecklist, getProject, getQuestionDetail, updateQuestion,
  acceptRemark, rejectRemark, editRemark, addQuestion, deleteQuestion,
  streamSSE,
  type ChecklistDetail, type Question, type QuestionDetail,
} from '../lib/api';

export default function ChecklistPage() {
  const { projectId, checklistId } = useParams<{ projectId: string; checklistId: string }>();
  const [checklist, setChecklist] = useState<ChecklistDetail | null>(null);
  const [projectName, setProjectName] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<QuestionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [bulkAssessing, setBulkAssessing] = useState(false);
  const [bulkProgress, setBulkProgress] = useState('');
  const controllerRef = useRef<AbortController | null>(null);

  // Show add question form
  const [showAddForm, setShowAddForm] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newText, setNewText] = useState('');
  const [newCategory, setNewCategory] = useState('');

  const loadChecklist = useCallback(async () => {
    if (!projectId || !checklistId) return;
    setLoading(true);
    try {
      const cl = await getChecklist(projectId, checklistId);
      setChecklist(cl);
      if (!selectedId && cl.questions.length > 0) {
        setSelectedId(cl.questions[0].id);
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, checklistId]);

  useEffect(() => { loadChecklist(); }, [loadChecklist]);

  // Projektname fuer Breadcrumb laden
  useEffect(() => {
    if (projectId) {
      getProject(projectId).then((p) => setProjectName(p.projekttitel || p.aktenzeichen)).catch(() => {});
    }
  }, [projectId]);

  const loadDetail = useCallback(async (qId: string) => {
    if (!projectId || !checklistId) return;
    setDetailLoading(true);
    try {
      const d = await getQuestionDetail(projectId, checklistId, qId);
      setDetail(d);
    } finally {
      setDetailLoading(false);
    }
  }, [projectId, checklistId]);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const handleSelect = (qId: string) => {
    setSelectedId(qId);
  };

  const handleKeyNav = (e: React.KeyboardEvent) => {
    if (!checklist) return;
    const questions = checklist.questions;
    const idx = questions.findIndex((q) => q.id === selectedId);
    if (e.key === 'ArrowDown' && idx < questions.length - 1) {
      e.preventDefault();
      setSelectedId(questions[idx + 1].id);
    }
    if (e.key === 'ArrowUp' && idx > 0) {
      e.preventDefault();
      setSelectedId(questions[idx - 1].id);
    }
  };

  // Assessment
  const handleGenerate = async (qId: string) => {
    setGenerating(true);
    controllerRef.current = streamSSE(
      `/assessment/questions/${qId}/assess`,
      {},
      () => {}, // tokens streamed server-side, we just wait
      async () => {
        setGenerating(false);
        await loadDetail(qId);
        await loadChecklist();
      },
      () => setGenerating(false),
    );
  };

  const handleAccept = async () => {
    if (!detail) return;
    await acceptRemark(detail.id);
    await loadDetail(detail.id);
    await loadChecklist();
  };

  const handleReject = async (feedback?: string) => {
    if (!detail) return;
    await rejectRemark(detail.id, feedback);
    await loadDetail(detail.id);
    await loadChecklist();
  };

  const handleEdit = async (text: string) => {
    if (!detail) return;
    await editRemark(detail.id, text);
    await loadDetail(detail.id);
    await loadChecklist();
  };

  // Debounced save für Textfelder
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleAnswerChange = (value: string) => {
    if (!detail) return;
    setDetail({ ...detail, answer_value: value });
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      if (!projectId || !checklistId || !detail) return;
      await updateQuestion(projectId, checklistId, detail.id, { answer_value: value } as Partial<Question>);
    }, 500);
  };

  const handleManualRemarkChange = (value: string) => {
    if (!detail) return;
    setDetail({ ...detail, remark_manual: value });
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      if (!projectId || !checklistId || !detail) return;
      await updateQuestion(projectId, checklistId, detail.id, { remark_manual: value } as Partial<Question>);
    }, 500);
  };

  // Bulk assess
  const handleBulkAssess = () => {
    if (!checklistId || bulkAssessing) return;
    setBulkAssessing(true);
    setBulkProgress('Starte…');
    controllerRef.current = streamSSE(
      `/assessment/checklists/${checklistId}/assess-all`,
      {},
      (token) => setBulkProgress(token),
      async () => {
        setBulkAssessing(false);
        setBulkProgress('');
        await loadChecklist();
        if (selectedId) await loadDetail(selectedId);
      },
      () => { setBulkAssessing(false); setBulkProgress('Fehler'); },
    );
  };

  // Add question
  const handleAddQuestion = async () => {
    if (!projectId || !checklistId || !newKey) return;
    await addQuestion(projectId, checklistId, {
      question_key: newKey,
      question_text: newText,
      category: newCategory || undefined,
    } as Partial<Question>);
    setShowAddForm(false);
    setNewKey('');
    setNewText('');
    setNewCategory('');
    await loadChecklist();
  };

  // Delete question
  const handleDeleteQuestion = async (qId: string) => {
    if (!projectId || !checklistId) return;
    if (!confirm('Frage löschen?')) return;
    await deleteQuestion(projectId, checklistId, qId);
    if (selectedId === qId) setSelectedId(null);
    setDetail(null);
    await loadChecklist();
  };

  const handleExportCsv = () => {
    if (!checklist) return;
    const escapeCell = (value: string | null | undefined) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const rows = [
      ['question_key', 'category', 'question_text', 'answer_type', 'answer_value', 'remark_manual', 'remark_ai_status', 'remark_ai', 'remark_ai_edited', 'evidence_count'],
      ...checklist.questions.map((q) => [
        q.question_key,
        q.category || '',
        q.question_text || '',
        q.answer_type,
        q.answer_value || '',
        q.remark_manual || '',
        q.remark_ai_status || '',
        q.remark_ai || '',
        q.remark_ai_edited || '',
        String(q.evidence_count ?? 0),
      ]),
    ];
    const csv = rows.map((row) => row.map((cell) => escapeCell(cell)).join(';')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${checklist.name.replace(/[^a-zA-Z0-9_-]+/g, '_') || 'checkliste'}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportPdf = () => {
    if (!checklist) return;
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;

    const rows = checklist.questions.map(q => {
      const remark = q.remark_ai || '';
      const status = q.remark_ai_status || 'none';
      return `<tr>
        <td style="padding:6px;border:1px solid #ddd;font-size:12px;">${q.question_key || ''}</td>
        <td style="padding:6px;border:1px solid #ddd;font-size:12px;">${q.question_text || ''}</td>
        <td style="padding:6px;border:1px solid #ddd;font-size:12px;">${q.answer_value || ''}</td>
        <td style="padding:6px;border:1px solid #ddd;font-size:12px;">${remark}</td>
        <td style="padding:6px;border:1px solid #ddd;font-size:12px;">${status}</td>
      </tr>`;
    }).join('');

    printWindow.document.write(`<!DOCTYPE html><html><head><title>Checkliste Export</title>
      <style>
        body { font-family: 'Segoe UI', sans-serif; padding: 40px; color: #1e293b; }
        h1 { font-size: 18px; margin-bottom: 4px; }
        h2 { font-size: 14px; color: #64748b; font-weight: normal; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f1f5f9; padding: 8px; border: 1px solid #ddd; font-size: 11px; text-align: left; text-transform: uppercase; }
        @media print { body { padding: 20px; } }
      </style></head><body>
      <h1>${checklist.name || 'Checkliste'}</h1>
      <h2>Exportiert am ${new Date().toLocaleDateString('de-DE')}</h2>
      <table>
        <thead><tr><th>Nr.</th><th>Prüfpunkt</th><th>Antwort</th><th>KI-Bemerkung</th><th>Status</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      </body></html>`);
    printWindow.document.close();
    printWindow.print();
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-indigo-500" size={24} /></div>;
  if (!checklist) return <p className="text-slate-400">Checkliste nicht gefunden.</p>;

  // Group questions by category
  const categories = [...new Set(checklist.questions.map((q) => q.category || 'Allgemein'))];

  return (
    <div className="h-full flex flex-col -m-4 lg:-m-6">
      {/* Header */}
      <div className="flex items-center justify-between px-4 lg:px-6 py-3 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
        <div className="flex items-center gap-3">
          <div>
            <Breadcrumb items={[
              { label: 'Home', to: '/' },
              { label: 'Projekte', to: '/projects' },
              { label: projectName || '...', to: `/projects/${projectId}` },
              { label: checklist.name },
            ]} />
            <span className="text-xs text-slate-400">{checklist.questions.length} Fragen · {checklist.ai_assessed_count} KI-bewertet</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportCsv}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <Download size={14} />
            CSV
          </button>
          <button
            onClick={handleExportPdf}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <FileDown size={14} />
            PDF-Export
          </button>
          <button
            onClick={handleBulkAssess}
            disabled={bulkAssessing}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-full bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-700"
          >
            {bulkAssessing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {bulkAssessing ? 'Bewerte…' : 'Alle bewerten'}
          </button>
        </div>
      </div>

      {bulkProgress && (
        <div className="px-6 py-1 text-xs text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 border-b border-indigo-200 dark:border-indigo-800">
          {bulkProgress}
        </div>
      )}

      {/* 2-pane layout */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0">
        {/* Left: Question list (40%) */}
        <div
          className="w-full lg:w-2/5 max-h-[40vh] lg:max-h-none border-b lg:border-b-0 lg:border-r border-slate-200 dark:border-slate-700 overflow-y-auto bg-white dark:bg-slate-900"
          onKeyDown={handleKeyNav}
          tabIndex={0}
          role="listbox"
          aria-label="Fragenliste"
        >
          {/* Status legend */}
          <div className="px-4 py-2 border-b border-slate-100 dark:border-slate-800 flex gap-2 flex-wrap">
            <StatusBadge status="accepted" compact />
            <StatusBadge status="draft" compact />
            <StatusBadge status="edited" compact />
            <StatusBadge status="rejected" compact />
            <StatusBadge status={null} compact />
          </div>

          {categories.map((cat) => (
            <div key={cat}>
              <div className="px-4 py-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 dark:bg-slate-800/50 border-b border-slate-100 dark:border-slate-800">
                {cat}
              </div>
              {checklist.questions
                .filter((q) => (q.category || 'Allgemein') === cat)
                .map((q) => (
                  <button
                    key={q.id}
                    onClick={() => handleSelect(q.id)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left border-b border-slate-100 dark:border-slate-800 transition-colors ${
                      selectedId === q.id
                        ? 'bg-indigo-50 dark:bg-indigo-900/20 border-l-2 border-l-indigo-600'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800/50 border-l-2 border-l-transparent'
                    }`}
                    role="option"
                    aria-selected={selectedId === q.id}
                  >
                    <StatusBadge status={q.remark_ai_status} compact />
                    <span className="font-mono text-xs text-slate-500 w-8 shrink-0">{q.question_key}</span>
                    <span className="text-sm text-slate-700 dark:text-slate-300 truncate flex-1">{q.question_text || '(Kein Text)'}</span>
                  </button>
                ))}
            </div>
          ))}

          {/* Add question button */}
          <div className="p-3">
            {showAddForm ? (
              <div className="space-y-2 p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <input value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="Schlüssel (z.B. 9.1)" aria-label="Fragenschlüssel" className="w-full px-2 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700" />
                <input value={newText} onChange={(e) => setNewText(e.target.value)} placeholder="Fragetext" aria-label="Fragetext" className="w-full px-2 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700" />
                <input value={newCategory} onChange={(e) => setNewCategory(e.target.value)} placeholder="Kategorie" aria-label="Kategorie" className="w-full px-2 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700" />
                <div className="flex gap-2">
                  <button onClick={handleAddQuestion} disabled={!newKey} className="px-3 py-1 text-xs rounded-full bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:disabled:bg-slate-700">Hinzufügen</button>
                  <button onClick={() => setShowAddForm(false)} className="px-3 py-1 text-xs text-slate-500">Abbrechen</button>
                </div>
              </div>
            ) : (
              <button onClick={() => setShowAddForm(true)} className="flex items-center gap-1 text-xs text-slate-400 hover:text-indigo-600">
                <Plus size={14} /> Frage hinzufügen
              </button>
            )}
          </div>
        </div>

        {/* Right: Question detail (60%) */}
        <div className="w-full lg:w-3/5 overflow-y-auto bg-slate-50 dark:bg-slate-950 p-4 lg:p-6">
          {detailLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="animate-spin text-indigo-500" size={20} /></div>
          ) : detail ? (
            <div className="space-y-5">
              {/* Question header */}
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm font-bold text-indigo-600 dark:text-indigo-400">{detail.question_key}</span>
                    <StatusBadge status={detail.remark_ai_status} />
                    {detail.category && <span className="text-xs text-slate-400 px-2 py-0.5 bg-slate-200 dark:bg-slate-800 rounded">{detail.category}</span>}
                  </div>
                  <p className="text-sm text-slate-900 dark:text-white leading-relaxed">{detail.question_text || '(Kein Fragetext)'}</p>
                </div>
                <button
                  onClick={() => handleDeleteQuestion(detail.id)}
                  className="text-slate-300 hover:text-red-500 p-1"
                  aria-label="Frage löschen"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Answer */}
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">Antwort ({detail.answer_type})</label>
                {detail.answer_type === 'boolean' || detail.answer_type === 'boolean_jn' ? (
                  <div className="flex gap-2">
                    {['ja', 'teilweise', 'nein', 'n.a.'].map((opt) => (
                      <button
                        key={opt}
                        onClick={() => handleAnswerChange(opt)}
                        className={`px-2.5 py-1 text-xs rounded-lg border transition ${
                          detail.answer_value === opt
                            ? opt === 'ja' ? 'bg-emerald-100 border-emerald-400 text-emerald-700 dark:bg-emerald-900/30'
                            : opt === 'teilweise' ? 'bg-amber-100 border-amber-400 text-amber-700 dark:bg-amber-900/30'
                            : opt === 'nein' ? 'bg-red-100 border-red-400 text-red-700 dark:bg-red-900/30'
                            : 'bg-slate-100 border-slate-400 text-slate-600 dark:bg-slate-700'
                            : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-700'
                        }`}
                      >
                        {opt === 'n.a.' ? 'N/A' : opt.charAt(0).toUpperCase() + opt.slice(1)}
                      </button>
                    ))}
                  </div>
                ) : (
                  <input
                    value={detail.answer_value || ''}
                    onChange={(e) => handleAnswerChange(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm"
                    placeholder={detail.answer_type === 'date' ? 'TT.MM.JJJJ' : detail.answer_type === 'amount' ? '0,00 EUR' : 'Antwort eingeben…'}
                  />
                )}
              </div>

              {/* Manual remark */}
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">Manuelle Bemerkung</label>
                <textarea
                  value={detail.remark_manual || ''}
                  onChange={(e) => handleManualRemarkChange(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm resize-none"
                  placeholder="Eigene Bemerkung des Prüfers…"
                  aria-label="Manuelle Bemerkung"
                />
              </div>

              {/* AI Remark */}
              <AiRemarkCard
                remarkAi={detail.remark_ai}
                remarkAiEdited={detail.remark_ai_edited}
                status={detail.remark_ai_status}
                rejectFeedback={detail.reject_feedback}
                onAccept={handleAccept}
                onReject={handleReject}
                onEdit={handleEdit}
                onGenerate={() => handleGenerate(detail.id)}
                generating={generating}
              />

              {/* Evidence */}
              {detail.evidence.length > 0 && (
                <div>
                  <h3 className="text-xs font-medium text-slate-500 mb-2">Belege / Evidence ({detail.evidence.length})</h3>
                  <div className="space-y-2">
                    {detail.evidence.map((ev) => (
                      <EvidenceCard key={ev.id} evidence={ev} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-center text-slate-400 py-12">Frage auswählen um Details zu sehen.</p>
          )}
        </div>
      </div>
    </div>
  );
}
