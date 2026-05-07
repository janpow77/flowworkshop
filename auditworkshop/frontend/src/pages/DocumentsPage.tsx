import { useEffect, useMemo, useState, useRef, type DragEvent } from 'react';
import {
  FolderArchive, FileText, BarChart, Scale, Users, Folder,
  Upload, Download, Trash2, Search, AlertTriangle, Loader2, FileImage,
  FileSpreadsheet, FileCode, File as FileIcon, X,
} from 'lucide-react';
import { getWorkshopAuthHeaders } from '../lib/api';

interface FolderItem {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  visibility: string;
  upload_policy: string;
  is_shared_pool: boolean;
  icon: string | null;
  file_count: number;
  size_bytes: number;
}

interface FileItem {
  id: string;
  folder_id: string;
  name: string;
  description: string | null;
  tags: string[] | null;
  mime_type: string | null;
  size_bytes: number;
  current_version_no: number;
  uploaded_at: string | null;
  uploader_name: string | null;
  uploader_organization: string | null;
  uploader_bundesland: string | null;
  download_count: number;
  can_delete: boolean;
}

const FOLDER_ICONS: Record<string, typeof Folder> = {
  FolderArchive, FileText, BarChart, Scale, Users,
};

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  if (b < 1024 ** 3) return `${(b / 1024 / 1024).toFixed(1)} MB`;
  return `${(b / 1024 ** 3).toFixed(2)} GB`;
}

function fileIcon(mime: string | null) {
  if (!mime) return FileIcon;
  if (mime.startsWith('image/')) return FileImage;
  if (mime.includes('spreadsheet') || mime.includes('excel')) return FileSpreadsheet;
  if (mime.includes('json') || mime.includes('xml') || mime.startsWith('text/')) return FileCode;
  return FileText;
}

export default function DocumentsPage() {
  const [folders, setFolders] = useState<FolderItem[]>([]);
  const [activeFolder, setActiveFolder] = useState<FolderItem | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filterBl, setFilterBl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const role = localStorage.getItem('workshop_role') || '';
  const isLoggedIn = !!localStorage.getItem('workshop_token');
  const isMod = role === 'moderator' || role === 'admin';

  const loadFolders = async () => {
    try {
      const r = await fetch('/api/docs/folders', { headers: getWorkshopAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setFolders(d);
      if (!activeFolder && d.length > 0) setActiveFolder(d[0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    }
  };

  const loadFiles = async () => {
    if (!activeFolder) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('q', search);
      if (filterBl) params.set('bundesland', filterBl);
      const r = await fetch(`/api/docs/folders/${activeFolder.id}/files?${params}`, {
        headers: getWorkshopAuthHeaders(),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setFiles(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadFolders(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => {
    if (activeFolder) loadFiles();
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [activeFolder, search, filterBl]);

  const upload = async (file: File) => {
    if (!activeFolder) return;
    setUploading(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await fetch(`/api/docs/folders/${activeFolder.id}/files`, {
        method: 'POST',
        headers: getWorkshopAuthHeaders(),
        body: form,
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `Upload fehlgeschlagen (${r.status})`);
      }
      await Promise.all([loadFiles(), loadFolders()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload-Fehler');
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (!canUpload) return;
    const f = e.dataTransfer.files[0];
    if (f) upload(f);
  };

  const deleteFile = async (id: string) => {
    if (!confirm('Datei wirklich löschen?')) return;
    const r = await fetch(`/api/docs/files/${id}`, {
      method: 'DELETE',
      headers: getWorkshopAuthHeaders(),
    });
    if (r.ok) loadFiles();
  };

  const allBundeslaender = useMemo(() => {
    return Array.from(new Set(files.map((f) => f.uploader_bundesland).filter(Boolean))).sort();
  }, [files]) as string[];

  const canUpload = activeFolder
    && isLoggedIn
    && (
      activeFolder.upload_policy === 'members'
      || (activeFolder.upload_policy === 'moderators' && isMod)
    );

  return (
    <div className="space-y-5">
      <section className="rounded-[28px] border border-white/70 bg-[linear-gradient(135deg,rgba(120,53,15,0.95),rgba(180,83,9,0.9)_45%,rgba(217,119,6,0.85))] px-7 py-6 text-white shadow-[0_28px_80px_-50px_rgba(180,83,9,0.6)]">
        <div className="text-[11px] uppercase tracking-[0.22em] text-amber-100/70">
          <FolderArchive size={11} className="inline mr-1" /> Dokumente
        </div>
        <h1 className="mt-2 text-2xl font-semibold">Geteilte Dateien & Material</h1>
        <p className="mt-2 text-sm text-white/85">
          Workshop-Folien, Templates, Auswertungen und eigene Beiträge der Teilnehmer
        </p>
      </section>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5" /><span>{error}</span>
          <button onClick={() => setError('')} className="ml-auto opacity-50 hover:opacity-100"><X size={14} /></button>
        </div>
      )}

      <div className="grid lg:grid-cols-[280px_1fr] gap-5">
        {/* Folder-Tree */}
        <aside className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 px-1">Ordner</h2>
          {folders.map((f) => {
            const Icon = (f.icon && FOLDER_ICONS[f.icon]) || Folder;
            return (
              <button key={f.id}
                onClick={() => setActiveFolder(f)}
                className={`w-full text-left rounded-xl border p-3 transition ${
                  activeFolder?.id === f.id
                    ? 'border-cyan-400 bg-cyan-50 dark:border-cyan-700 dark:bg-cyan-950/30'
                    : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900'
                }`}>
                <div className="flex items-start gap-2">
                  <Icon size={16} className="mt-0.5 shrink-0 text-amber-600" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-900 dark:text-white">{f.name}</div>
                    {f.description && <div className="text-[11px] text-slate-500 line-clamp-2 mt-0.5">{f.description}</div>}
                    <div className="text-[10px] text-slate-400 mt-1">
                      {f.file_count} Dateien · {formatBytes(f.size_bytes)}
                      {f.is_shared_pool && ' · Geteilt'}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </aside>

        {/* Datei-Bereich */}
        <main className="space-y-3">
          {!activeFolder ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white/40 p-12 text-center text-sm text-slate-500">
              Bitte einen Ordner auswählen.
            </div>
          ) : (
            <>
              {/* Header mit Filter + Upload */}
              <div className="flex flex-wrap items-center gap-3">
                <div className="relative flex-1 min-w-[200px]">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input value={search} onChange={(e) => setSearch(e.target.value)}
                    placeholder="Datei suchen…"
                    className="w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 py-2 text-sm focus:border-cyan-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900" />
                </div>
                {activeFolder.is_shared_pool && allBundeslaender.length > 0 && (
                  <select value={filterBl} onChange={(e) => setFilterBl(e.target.value)}
                    className="text-sm px-3 py-2 rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                    <option value="">Alle Bundesländer</option>
                    {allBundeslaender.map((bl) => <option key={bl} value={bl}>{bl}</option>)}
                  </select>
                )}
                {canUpload && (
                  <button onClick={() => inputRef.current?.click()} disabled={uploading}
                    className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-50">
                    {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                    Hochladen
                  </button>
                )}
                <input ref={inputRef} type="file" className="hidden"
                  onChange={(e) => { if (e.target.files?.[0]) upload(e.target.files[0]); }} />
              </div>

              {/* Drop-Zone */}
              {canUpload && (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                  className={`rounded-2xl border-2 border-dashed p-5 text-center text-sm transition ${
                    dragOver
                      ? 'border-cyan-400 bg-cyan-50 dark:bg-cyan-950/30'
                      : 'border-slate-300 bg-white/40 dark:border-slate-700 dark:bg-slate-900/40'
                  }`}>
                  <Upload size={18} className="mx-auto text-slate-400 mb-1" />
                  <span className="text-slate-600 dark:text-slate-400">
                    Datei hierher ziehen — max 50 MB · PDF, Office, Bild, Text, ZIP
                  </span>
                </div>
              )}

              {/* Datei-Tabelle */}
              <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
                {loading ? (
                  <div className="p-6 text-center text-sm text-slate-500">Lädt…</div>
                ) : files.length === 0 ? (
                  <div className="p-12 text-center text-sm text-slate-500">
                    Keine Dateien in diesem Ordner.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 dark:bg-slate-800 text-xs uppercase tracking-wider text-slate-500">
                        <tr>
                          <th className="px-4 py-2 text-left">Name</th>
                          <th className="px-4 py-2 text-left hidden md:table-cell">Hochgeladen</th>
                          <th className="px-4 py-2 text-right">Größe</th>
                          <th className="px-4 py-2 text-right">Aktionen</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                        {files.map((f) => {
                          const Icon = fileIcon(f.mime_type);
                          return (
                            <tr key={f.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                              <td className="px-4 py-3">
                                <div className="flex items-start gap-2">
                                  <Icon size={16} className="mt-0.5 shrink-0 text-slate-400" />
                                  <div className="min-w-0">
                                    <div className="font-medium text-slate-900 dark:text-white line-clamp-1">{f.name}</div>
                                    {f.description && <div className="text-xs text-slate-500 line-clamp-1">{f.description}</div>}
                                    {f.tags && f.tags.length > 0 && (
                                      <div className="flex gap-1 mt-1 flex-wrap">
                                        {f.tags.map((t) => (
                                          <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-800">{t}</span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </td>
                              <td className="px-4 py-3 text-xs text-slate-500 hidden md:table-cell">
                                {f.uploader_name && <div>{f.uploader_name}</div>}
                                {f.uploader_bundesland && <div className="text-slate-400">{f.uploader_bundesland}</div>}
                                {f.uploaded_at && <div className="text-slate-400">{new Date(f.uploaded_at).toLocaleDateString('de-DE')}</div>}
                              </td>
                              <td className="px-4 py-3 text-right text-xs text-slate-500 whitespace-nowrap">
                                {formatBytes(f.size_bytes)}
                                {f.current_version_no > 1 && <span className="text-slate-400 block">v{f.current_version_no}</span>}
                              </td>
                              <td className="px-4 py-3 text-right">
                                <div className="inline-flex gap-1">
                                  <a href={`/api/docs/files/${f.id}/download`}
                                    className="text-slate-500 hover:text-cyan-600 p-1" title="Download">
                                    <Download size={14} />
                                  </a>
                                  {f.can_delete && (
                                    <button onClick={() => deleteFile(f.id)}
                                      className="text-slate-400 hover:text-rose-600 p-1" title="Löschen">
                                      <Trash2 size={14} />
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
