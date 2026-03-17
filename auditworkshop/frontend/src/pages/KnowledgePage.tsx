import { useState, useEffect, useCallback, useRef } from 'react';
import { Database, Search, MessageSquare, Trash2, Upload, Loader2, FileText, ChevronDown, ChevronRight, Eye } from 'lucide-react';
import {
  getKnowledgeStats, searchKnowledge, deleteKnowledgeSource, streamSSE,
  type KnowledgeStats, type SearchResult,
} from '../lib/api';

export default function KnowledgePage() {
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  // Ask panel
  const [askQuery, setAskQuery] = useState('');
  const [askResponse, setAskResponse] = useState('');
  const [askStreaming, setAskStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  // Ingest
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<string>('');

  const loadStats = useCallback(() => {
    getKnowledgeStats().then(setStats);
  }, []);

  useEffect(loadStats, [loadStats]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const r = await searchKnowledge(searchQuery, 5);
      setSearchResults(r.results);
    } finally {
      setSearching(false);
    }
  };

  const handleAsk = () => {
    if (!askQuery.trim() || askStreaming) return;
    setAskResponse('');
    setAskStreaming(true);
    controllerRef.current = streamSSE(
      '/workshop/stream',
      { scenario: 5, prompt: askQuery, documents: [], with_context: true },
      (token) => setAskResponse((p) => p + token),
      () => setAskStreaming(false),
      () => setAskStreaming(false),
    );
  };

  // Ingest with inline source-label
  const [ingestSource, setIngestSource] = useState('');
  const [ingestFile, setIngestFile] = useState<File | null>(null);
  const [ingestDragOver, setIngestDragOver] = useState(false);

  const handleIngestFile = (file: File) => {
    setIngestFile(file);
    // Auto-generate source label from filename
    if (!ingestSource) {
      const name = file.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '_').toUpperCase();
      setIngestSource(name);
    }
  };

  const handleIngestSubmit = async () => {
    if (!ingestFile || !ingestSource) return;
    setIngesting(true);
    setIngestResult('');
    try {
      const form = new FormData();
      form.append('file', ingestFile);
      form.append('source', ingestSource);
      const res = await fetch('/api/knowledge/ingest', { method: 'POST', body: form });
      const data = await res.json();
      if (res.ok) {
        setIngestResult(`${data.chunks_stored} Textabschnitte gespeichert (${data.method})`);
        setIngestFile(null);
        setIngestSource('');
        loadStats();
      } else {
        setIngestResult(`Fehler: ${data.detail}`);
      }
    } finally {
      setIngesting(false);
    }
  };

  // Chunk-Browser
  const [expandedSource, setExpandedSource] = useState<string | null>(null);
  const [chunks, setChunks] = useState<{ chunk_index: number; text: string; char_count: number }[]>([]);
  const [chunksTotal, setChunksTotal] = useState(0);
  const [chunksOffset, setChunksOffset] = useState(0);
  const [chunksLoading, setChunksLoading] = useState(false);

  const loadChunks = async (source: string, offset = 0) => {
    setChunksLoading(true);
    try {
      const res = await fetch(`/api/knowledge/source/${source}/chunks?offset=${offset}&limit=10`);
      const data = await res.json();
      setChunks(data.chunks);
      setChunksTotal(data.total);
      setChunksOffset(offset);
    } finally {
      setChunksLoading(false);
    }
  };

  const toggleSource = (source: string) => {
    if (expandedSource === source) {
      setExpandedSource(null);
      setChunks([]);
    } else {
      setExpandedSource(source);
      loadChunks(source, 0);
    }
  };

  const handleDeleteSource = async (source: string) => {
    if (!confirm(`Quelle "${source}" wirklich löschen?`)) return;
    await deleteKnowledgeSource(source);
    if (expandedSource === source) { setExpandedSource(null); setChunks([]); }
    loadStats();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Wissensdatenbank</h1>
        {stats && (
          <span className="text-sm text-slate-500">{stats.documents} Dokumente · {stats.chunks} Textabschnitte</span>
        )}
      </div>

      {/* Ask Panel */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5">
        <h2 className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white mb-3">
          <MessageSquare size={18} /> Frage stellen
        </h2>
        <div className="flex gap-2 mb-3">
          <input
            value={askQuery}
            onChange={(e) => setAskQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAsk(); }}
            placeholder="z.B. Was regelt Art. 74 VO 2021/1060?"
            className="flex-1 px-4 py-3 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm"
            aria-label="Frage an die Wissensdatenbank"
          />
          <button
            onClick={handleAsk}
            disabled={!askQuery.trim() || askStreaming}
            className="px-4 py-2 rounded-full bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-700"
          >
            {askStreaming ? <Loader2 size={16} className="animate-spin" /> : 'Fragen'}
          </button>
        </div>
        {askResponse && (
          <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4 text-sm">
            <pre className="whitespace-pre-wrap font-sans text-slate-700 dark:text-slate-300 leading-relaxed">{askResponse}</pre>
          </div>
        )}
      </div>

      {/* Search Panel */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5">
        <h2 className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white mb-3">
          <Search size={18} /> Semantische Suche
        </h2>
        <div className="flex gap-2 mb-3">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
            placeholder="Suchbegriff eingeben…"
            className="flex-1 px-4 py-3 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm"
            aria-label="Semantische Suche"
          />
          <button onClick={handleSearch} disabled={searching} className="px-4 py-2 rounded-full bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-700">
            {searching ? <Loader2 size={16} className="animate-spin" /> : 'Suchen'}
          </button>
        </div>
        {searchResults.length > 0 && (
          <div className="space-y-2">
            {searchResults.map((r, i) => (
              <div key={i} className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">{r.source}</span>
                  <span className="text-xs text-slate-400">Score: {r.score.toFixed(2)}</span>
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-3">{r.text}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sources Panel */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5">
        <h2 className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white mb-3">
          <Database size={18} /> Quellen verwalten
        </h2>
        {stats && stats.sources.length > 0 ? (
          <div className="space-y-2 mb-4">
            {stats.sources.map((s) => (
              <div key={s.source}>
                <div className="flex items-center justify-between bg-slate-50 dark:bg-slate-800 rounded-lg px-4 py-2">
                  <button
                    onClick={() => toggleSource(s.source)}
                    className="flex items-center gap-2 text-left flex-1 min-w-0"
                    aria-label={`${s.source} ${expandedSource === s.source ? 'zuklappen' : 'aufklappen'}`}
                  >
                    {expandedSource === s.source ? <ChevronDown size={14} className="text-indigo-500 shrink-0" /> : <ChevronRight size={14} className="text-slate-400 shrink-0" />}
                    <FileText size={14} className="text-indigo-500 shrink-0" />
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">{s.source}</span>
                    <span className="text-xs text-slate-400 shrink-0">{s.chunks} Abschnitte</span>
                    {s.filename && <span className="text-[10px] text-slate-400 truncate hidden sm:inline">({s.filename})</span>}
                  </button>
                  <div className="flex items-center gap-1 shrink-0 ml-2">
                    <button onClick={() => toggleSource(s.source)} className="p-1.5 text-slate-400 hover:text-indigo-500" aria-label="Abschnitte anzeigen">
                      <Eye size={14} />
                    </button>
                    <button onClick={() => handleDeleteSource(s.source)} className="p-1.5 text-slate-400 hover:text-red-500" aria-label={`${s.source} löschen`}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                {/* Chunk-Browser */}
                {expandedSource === s.source && (
                  <div className="ml-6 mt-1 mb-2 border-l-2 border-indigo-200 dark:border-indigo-800 pl-4 space-y-2">
                    {chunksLoading ? (
                      <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
                        <Loader2 size={14} className="animate-spin" /> Abschnitte laden...
                      </div>
                    ) : (
                      <>
                        <div className="text-xs text-slate-500 py-1">
                          Abschnitte {chunksOffset + 1}–{Math.min(chunksOffset + chunks.length, chunksTotal)} von {chunksTotal}
                        </div>
                        {chunks.map((c) => (
                          <div key={c.chunk_index} className="rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-3">
                            <div className="flex items-center justify-between mb-1.5">
                              <span className="text-[10px] font-mono text-indigo-500 bg-indigo-50 dark:bg-indigo-950/40 px-1.5 py-0.5 rounded">
                                Chunk #{c.chunk_index + 1}
                              </span>
                              <span className="text-[10px] text-slate-400">{c.char_count} Zeichen</span>
                            </div>
                            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-wrap line-clamp-4 hover:line-clamp-none cursor-pointer transition-all">
                              {c.text}
                            </p>
                          </div>
                        ))}
                        {/* Pagination */}
                        {chunksTotal > 10 && (
                          <div className="flex items-center gap-2 pt-1">
                            <button
                              onClick={() => loadChunks(s.source, Math.max(0, chunksOffset - 10))}
                              disabled={chunksOffset === 0}
                              className="px-3 py-1 text-xs rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30"
                            >
                              Vorherige
                            </button>
                            <button
                              onClick={() => loadChunks(s.source, chunksOffset + 10)}
                              disabled={chunksOffset + 10 >= chunksTotal}
                              className="px-3 py-1 text-xs rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30"
                            >
                              Nächste
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-400 mb-4">Keine Quellen vorhanden.</p>
        )}
        {/* Ingest Dropzone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setIngestDragOver(true); }}
          onDragLeave={() => setIngestDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIngestDragOver(false);
            const file = e.dataTransfer.files[0];
            if (file) handleIngestFile(file);
          }}
          className={`border-2 border-dashed rounded-lg p-4 transition-colors cursor-pointer ${
            ingestDragOver
              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
              : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400'
          }`}
        >
          {ingestFile ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <FileText size={16} className="text-indigo-500" />
                <span className="font-medium">{ingestFile.name}</span>
                <span className="text-xs text-slate-400">({(ingestFile.size / 1024).toFixed(0)} KB)</span>
                <button onClick={() => { setIngestFile(null); setIngestSource(''); }} className="text-slate-400 hover:text-red-500 ml-auto">
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="flex gap-2">
                <input
                  value={ingestSource}
                  onChange={(e) => setIngestSource(e.target.value)}
                  placeholder="Source-Label (z.B. VO_2021_1060)"
                  className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700"
                  aria-label="Source-Label"
                />
                <button
                  onClick={handleIngestSubmit}
                  disabled={!ingestSource || ingesting}
                  className="px-4 py-1.5 text-sm rounded-full bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-700 flex items-center gap-1"
                >
                  {ingesting ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  {ingesting ? 'Verarbeite…' : 'Einlesen'}
                </button>
              </div>
            </div>
          ) : (
            <div
              className="text-center cursor-pointer"
              onClick={() => document.getElementById('knowledge-ingest-input')?.click()}
            >
              <Upload size={24} className="mx-auto text-slate-400 mb-2" />
              <p className="text-sm text-slate-500 dark:text-slate-400">Datei hierher ziehen oder klicken</p>
              <p className="text-xs text-slate-400 mt-1">PDF, XLSX, DOCX, HTML, RTF, TXT — max. 50 MB je Datei</p>
              <input
                id="knowledge-ingest-input"
                type="file"
                accept=".pdf,.xlsx,.xls,.xlsm,.docx,.docm,.html,.htm,.rtf,.txt"
                className="hidden"
                onChange={(e) => { if (e.target.files?.[0]) handleIngestFile(e.target.files[0]); }}
              />
            </div>
          )}
        </div>
        {ingestResult && <p className="text-xs text-green-600 dark:text-green-400 mt-2">{ingestResult}</p>}
      </div>
    </div>
  );
}
