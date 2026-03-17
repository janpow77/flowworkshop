import { useCallback, useState } from 'react';
import { Upload, FileText, X, Loader2, CheckCircle } from 'lucide-react';

interface Props {
  onFilesRead: (texts: string[]) => void;
  maxFiles?: number;
  accept?: string;
  /** Label for the dropzone */
  label?: string;
}

const ALL_ACCEPT = '.pdf,.xlsx,.xls,.xlsm,.docx,.docm,.html,.htm,.rtf,.txt';

interface ParsedFile {
  file: File;
  text: string;
  status: 'pending' | 'parsing' | 'done' | 'error';
  info?: string;
}

export default function DocumentDropzone({ onFilesRead, maxFiles = 3, accept = ALL_ACCEPT, label }: Props) {
  const [parsed, setParsed] = useState<ParsedFile[]>([]);
  const [dragOver, setDragOver] = useState(false);

  const processFiles = useCallback(async (newFiles: File[]) => {
    const limited = newFiles.slice(0, maxFiles);
    const items: ParsedFile[] = limited.map((f) => ({
      file: f,
      text: '',
      status: 'pending' as const,
    }));
    setParsed(items);

    const results: string[] = [];

    for (let i = 0; i < items.length; i++) {
      const f = items[i].file;
      setParsed((prev) => prev.map((p, j) => j === i ? { ...p, status: 'parsing' } : p));

      try {
        if (f.name.toLowerCase().endsWith('.txt')) {
          // Textdateien client-seitig lesen
          const text = await f.text();
          results.push(text);
          setParsed((prev) => prev.map((p, j) => j === i ? {
            ...p, text, status: 'done',
            info: `${text.length} Zeichen`,
          } : p));
          continue;
        }

        {
          // Alle anderen Formate serverseitig parsen
          const form = new FormData();
          form.append('file', f);
          const res = await fetch('/api/workshop/parse-file', { method: 'POST', body: form });
          if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Fehler' }));
            throw new Error(err.detail || `HTTP ${res.status}`);
          }
          const data = await res.json();
          results.push(data.text);
          setParsed((prev) => prev.map((p, j) => j === i ? {
            ...p, text: data.text, status: 'done',
            info: `${data.pages} Seiten, ${data.char_count} Zeichen (${data.method})`,
          } : p));
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Unbekannter Fehler';
        setParsed((prev) => prev.map((p, j) => j === i ? { ...p, status: 'error', info: msg } : p));
      }
    }

    onFilesRead(results);
  }, [maxFiles, onFilesRead]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    processFiles(Array.from(e.dataTransfer.files));
  }, [processFiles]);

  const handleInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) processFiles(Array.from(e.target.files));
  }, [processFiles]);

  const removeFile = (idx: number) => {
    const next = parsed.filter((_, i) => i !== idx);
    setParsed(next);
    onFilesRead(next.filter((p) => p.status === 'done').map((p) => p.text));
  };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer ${
          dragOver
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
            : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400'
        }`}
        onClick={() => document.getElementById('dropzone-input')?.click()}
        role="button"
        tabIndex={0}
        aria-label="PDF oder Textdateien hierher ziehen oder klicken"
      >
        <Upload size={24} className="mx-auto text-slate-400 mb-2" />
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {label || `Dateien hierher ziehen (max. ${maxFiles})`}
        </p>
        <p className="text-xs text-slate-400 mt-1">PDF, XLSX, DOCX, HTML, RTF, TXT — max. 50 MB je Datei</p>
        <input
          id="dropzone-input"
          type="file"
          className="hidden"
          accept={accept}
          multiple
          onChange={handleInput}
        />
      </div>
      {parsed.length > 0 && (
        <ul className="mt-2 space-y-1">
          {parsed.map((p, i) => (
            <li key={i} className="flex items-center gap-2 text-sm bg-slate-50 dark:bg-slate-800 rounded px-3 py-2">
              {p.status === 'parsing' ? (
                <Loader2 size={14} className="animate-spin text-indigo-500 shrink-0" />
              ) : p.status === 'done' ? (
                <CheckCircle size={14} className="text-green-500 shrink-0" />
              ) : p.status === 'error' ? (
                <X size={14} className="text-red-500 shrink-0" />
              ) : (
                <FileText size={14} className="text-slate-400 shrink-0" />
              )}
              <span className="flex-1 truncate text-slate-700 dark:text-slate-300">{p.file.name}</span>
              {p.info && (
                <span className={`text-xs shrink-0 ${p.status === 'error' ? 'text-red-500' : 'text-slate-400'}`}>
                  {p.info}
                </span>
              )}
              <button onClick={(e) => { e.stopPropagation(); removeFile(i); }} className="text-slate-400 hover:text-red-500 shrink-0" aria-label={`${p.file.name} entfernen`}>
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
