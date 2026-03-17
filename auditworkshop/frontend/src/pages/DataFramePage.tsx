import { useState, useEffect, useCallback } from 'react';
import { Database, Table, Upload, Trash2, Search, Loader2, FileSpreadsheet, AlertTriangle } from 'lucide-react';

interface DfTable {
  table_name: string;
  source: string;
  rows: number;
}

interface ColumnInfo {
  name: string;
  type: string;
}

interface TableInfo {
  exists: boolean;
  table_name: string;
  row_count: number;
  columns: ColumnInfo[];
}

export default function DataFramePage() {
  const [tables, setTables] = useState<DfTable[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [tableInfo, setTableInfo] = useState<TableInfo | null>(null);
  const [summary, setSummary] = useState<string>('');

  // SQL Query
  const [sqlQuery, setSqlQuery] = useState('');
  const [queryResult, setQueryResult] = useState<{ rows: Record<string, unknown>[]; count: number } | null>(null);
  const [queryError, setQueryError] = useState('');
  const [querying, setQuerying] = useState(false);

  // Ingest
  const [ingestFile, setIngestFile] = useState<File | null>(null);
  const [ingestSource, setIngestSource] = useState('');
  const [ingestSheet, setIngestSheet] = useState('0');
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState('');
  const [dragOver, setDragOver] = useState(false);

  const loadTables = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/dataframes/');
      const data = await res.json();
      setTables(data.tables || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTables(); }, [loadTables]);

  const selectTable = async (source: string) => {
    setSelectedSource(source);
    setQueryResult(null);
    setQueryError('');
    setSqlQuery(`SELECT * FROM {table} LIMIT 10`);

    const [infoRes, summaryRes] = await Promise.all([
      fetch(`/api/dataframes/${source}/info`),
      fetch(`/api/dataframes/${source}/summary`),
    ]);
    setTableInfo(await infoRes.json());
    const summaryData = await summaryRes.json();
    setSummary(summaryData.summary || '');
  };

  const runQuery = async () => {
    if (!selectedSource || !sqlQuery) return;
    setQuerying(true);
    setQueryError('');
    try {
      const res = await fetch(`/api/dataframes/${encodeURIComponent(selectedSource)}/query?sql=${encodeURIComponent(sqlQuery)}`);
      const data = await res.json();
      if (!res.ok) {
        setQueryError(data.detail || 'Fehler');
        setQueryResult(null);
      } else {
        setQueryResult(data);
      }
    } catch (err) {
      setQueryError(String(err));
    } finally {
      setQuerying(false);
    }
  };

  const deleteTable = async (source: string) => {
    if (!confirm(`Tabelle "${source}" wirklich löschen?`)) return;
    await fetch(`/api/dataframes/${encodeURIComponent(source)}`, { method: 'DELETE' });
    if (selectedSource === source) {
      setSelectedSource(null);
      setTableInfo(null);
    }
    loadTables();
  };

  const handleIngest = async () => {
    if (!ingestFile || !ingestSource) return;
    setIngesting(true);
    setIngestResult('');
    try {
      const form = new FormData();
      form.append('file', ingestFile);
      form.append('source', ingestSource);
      form.append('sheet', ingestSheet);
      const res = await fetch('/api/dataframes/ingest', { method: 'POST', body: form });
      const data = await res.json();
      if (res.ok) {
        setIngestResult(`${data.rows} Zeilen, ${data.columns.length} Spalten → ${data.table_name}`);
        setIngestFile(null);
        setIngestSource('');
        loadTables();
      } else {
        setIngestResult(`Fehler: ${data.detail}`);
      }
    } finally {
      setIngesting(false);
    }
  };

  // Example queries
  const exampleQueries = selectedSource ? [
    { label: 'Alle Daten (10)', sql: 'SELECT * FROM {table} LIMIT 10' },
    { label: 'Anzahl Zeilen', sql: 'SELECT COUNT(*) AS anzahl FROM {table}' },
    ...(tableInfo?.columns.some(c => c.type.includes('double') || c.type.includes('int') || c.type.includes('numeric'))
      ? [{ label: 'Numerische Spalten (Summe)', sql: `SELECT ${tableInfo.columns.filter(c => c.type.includes('double') || c.type.includes('int') || c.type.includes('numeric')).slice(0, 3).map(c => `SUM("${c.name}") AS sum_${c.name.slice(0, 20)}`).join(', ')} FROM {table}` }]
      : []),
  ] : [];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <FileSpreadsheet size={24} /> DataFrame-Tabellen
        </h1>
        <span className="text-sm text-slate-400">{tables.length} Tabellen</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Table list + Upload */}
        <div className="space-y-4">
          {/* Tables */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
                <Table size={14} /> Tabellen
              </h2>
            </div>
            {loading ? (
              <div className="p-6 text-center"><Loader2 className="animate-spin mx-auto text-indigo-500" size={20} /></div>
            ) : tables.length === 0 ? (
              <div className="p-6 text-center text-sm text-slate-400">Keine Tabellen vorhanden.</div>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {tables.map((t) => (
                  <button
                    key={t.source}
                    onClick={() => selectTable(t.source)}
                    className={`w-full flex items-center justify-between px-4 py-3 text-left text-sm transition-colors group ${
                      selectedSource === t.source
                        ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                  >
                    <div>
                      <div className="font-medium text-slate-900 dark:text-white">{t.source}</div>
                      <div className="text-xs text-slate-400">{t.rows} Zeilen</div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteTable(t.source); }}
                      className="p-1 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                      aria-label="Löschen"
                    >
                      <Trash2 size={14} />
                    </button>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Upload */}
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
              <Upload size={14} /> XLSX/CSV einlesen
            </h2>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                // Mehrere Dateien: Erste direkt setzen, Rest sequentiell via handleIngest
                const f = e.dataTransfer.files[0];
                if (f) {
                  setIngestFile(f);
                  if (!ingestSource) setIngestSource(f.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase());
                }
              }}
              className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors mb-3 ${
                dragOver ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20' : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400'
              }`}
              onClick={() => document.getElementById('df-upload')?.click()}
            >
              {ingestFile ? (
                <div className="text-sm text-slate-700 dark:text-slate-300">{ingestFile.name}</div>
              ) : (
                <>
                  <Upload size={24} className="mx-auto text-slate-400 mb-2" />
                  <p className="text-sm text-slate-500 dark:text-slate-400">XLSX oder CSV hierher ziehen oder klicken</p>
                  <p className="text-xs text-slate-400 mt-1">XLSX, XLS, CSV — max. 50 MB je Datei</p>
                </>
              )}
              <input id="df-upload" type="file" accept=".xlsx,.xls,.xlsm,.csv" multiple className="hidden" onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  setIngestFile(f);
                  if (!ingestSource) setIngestSource(f.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase());
                }
              }} />
            </div>
            {ingestFile && (
              <div className="space-y-2">
                <input value={ingestSource} onChange={(e) => setIngestSource(e.target.value)} placeholder="Tabellenname" aria-label="Tabellenname" className="w-full px-3 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700" />
                <input value={ingestSheet} onChange={(e) => setIngestSheet(e.target.value)} placeholder="Blatt (0 oder Name)" aria-label="Blatt" className="w-full px-3 py-1.5 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700" />
                <button onClick={handleIngest} disabled={!ingestSource || ingesting} className="w-full px-3 py-1.5 text-sm rounded-full bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-700 flex items-center justify-center gap-1">
                  {ingesting ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
                  {ingesting ? 'Einlesen…' : 'Als SQL-Tabelle speichern'}
                </button>
              </div>
            )}
            {ingestResult && <p className={`text-xs mt-2 ${ingestResult.startsWith('Fehler') ? 'text-red-500' : 'text-green-600 dark:text-green-400'}`}>{ingestResult}</p>}
          </div>
        </div>

        {/* Right: Table detail + SQL */}
        <div className="lg:col-span-2 space-y-4">
          {selectedSource && tableInfo ? (
            <>
              {/* Schema */}
              <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
                  {selectedSource} — {tableInfo.row_count} Zeilen, {tableInfo.columns.length} Spalten
                </h2>
                <div className="flex flex-wrap gap-1.5">
                  {tableInfo.columns.map((c) => (
                    <span key={c.name} className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs bg-slate-100 dark:bg-slate-800">
                      <span className="font-medium text-slate-700 dark:text-slate-300">{c.name}</span>
                      <span className="text-slate-400">({c.type})</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Summary */}
              {summary && (
                <details className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
                  <summary className="px-4 py-3 text-sm font-semibold text-slate-700 dark:text-slate-300 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800">
                    Statistik-Zusammenfassung (für LLM-Kontext)
                  </summary>
                  <pre className="px-4 pb-4 text-xs text-slate-600 dark:text-slate-400 whitespace-pre-wrap font-mono">{summary}</pre>
                </details>
              )}

              {/* SQL Query */}
              <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-2">
                  <Search size={14} /> SQL-Abfrage
                </h2>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {exampleQueries.map((eq) => (
                    <button key={eq.label} onClick={() => setSqlQuery(eq.sql)} className="text-xs px-2 py-1 rounded bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-900/40">
                      {eq.label}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <textarea
                    value={sqlQuery}
                    onChange={(e) => setSqlQuery(e.target.value)}
                    rows={2}
                    className="flex-1 px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-800 text-sm font-mono resize-none"
                    placeholder='SELECT * FROM {table} LIMIT 10'
                    onKeyDown={(e) => { if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); runQuery(); } }}
                    aria-label="SQL-Abfrage"
                  />
                  <button onClick={runQuery} disabled={querying || !sqlQuery} className="self-end px-4 py-2 rounded-full bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500 dark:hover:bg-indigo-400 dark:disabled:bg-slate-700">
                    {querying ? <Loader2 size={14} className="animate-spin" /> : 'Ausführen'}
                  </button>
                </div>
                <p className="text-xs text-slate-400 mt-1">Ctrl+Enter zum Ausführen · {'{table}'} = Tabellenname</p>
              </div>

              {/* Query Error */}
              {queryError && (
                <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3 flex items-start gap-2">
                  <AlertTriangle size={14} className="text-red-500 mt-0.5 shrink-0" />
                  <p className="text-sm text-red-600 dark:text-red-400">{queryError}</p>
                </div>
              )}

              {/* Query Results */}
              {queryResult && (
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
                  <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs text-slate-500">
                    {queryResult.count} Ergebnis(se)
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 dark:border-slate-700">
                          {queryResult.rows.length > 0 && Object.keys(queryResult.rows[0]).map((col) => (
                            <th key={col} className="px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400 whitespace-nowrap">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryResult.rows.map((row, i) => (
                          <tr key={i} className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">
                            {Object.values(row).map((val, j) => (
                              <td key={j} className="px-3 py-2 text-slate-700 dark:text-slate-300 max-w-xs truncate" title={String(val ?? '')}>
                                {val === null ? <span className="text-slate-300">NULL</span> : String(val)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-600 p-12 text-center text-slate-400">
              <FileSpreadsheet size={40} className="mx-auto mb-3" />
              <p>Tabelle links auswählen oder XLSX hochladen</p>
              <p className="text-xs mt-1">Begünstigtenverzeichnisse, Transparenzlisten, XLSX-Auswertungen → SQL-Tabellen</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
