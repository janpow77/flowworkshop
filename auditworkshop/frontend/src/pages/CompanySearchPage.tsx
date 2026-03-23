import {
  startTransition, useDeferredValue, useEffect, useMemo, useState,
} from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight, Building2, FileText, Filter, Globe2, Layers3, Loader2,
  MapPin, Scale, Search, ShieldCheck, Sparkles, Trash2, Upload, Wallet,
} from 'lucide-react';
import { Skeleton } from '../components/ui/Skeleton';
import {
  deleteReferenceSource,
  getSystemProfile,
  importReferenceData,
  listBeneficiarySources,
  listReferenceSources,
  searchBeneficiaries,
  searchReferenceData,
  type BeneficiaryCompanyHit,
  type BeneficiarySearchResponse,
  type BeneficiarySource,
  type ReferenceRegistrySearchResponse,
  type ReferenceRegistrySource,
  type ReferenceRegistryType,
  type SystemProfile,
} from '../lib/api';

const SCOPE_OPTIONS = [
  { value: 'all', label: 'Alles' },
  { value: 'company', label: 'Unternehmen' },
  { value: 'project', label: 'Vorhaben' },
  { value: 'aktenzeichen', label: 'Aktenzeichen' },
  { value: 'location', label: 'Ort' },
] as const;

const MIN_COST_OPTIONS = [
  { value: 0, label: 'Alle Volumina' },
  { value: 100000, label: 'ab 100.000 EUR' },
  { value: 500000, label: 'ab 500.000 EUR' },
  { value: 1000000, label: 'ab 1 Mio. EUR' },
  { value: 5000000, label: 'ab 5 Mio. EUR' },
];

const REGISTRY_OPTIONS: Array<{ value: ReferenceRegistryType; label: string }> = [
  { value: 'sanctions', label: 'Sanktionslisten' },
  { value: 'tam', label: 'TAM' },
  { value: 'state_aid', label: 'Staatliche Beihilfe' },
  { value: 'cohesio', label: 'Cohesio' },
  { value: 'other', label: 'Sonstiges Register' },
];

const MATCH_LABELS: Record<string, string> = {
  name: 'Unternehmen',
  projekt: 'Vorhaben',
  aktenzeichen: 'Aktenzeichen',
  standort: 'Ort',
  beschreibung: 'Beschreibung',
  country: 'Land',
  status: 'Status',
};

const REGISTRY_STYLES: Record<string, string> = {
  sanctions: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
  tam: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300',
  state_aid: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  cohesio: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  other: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
};

function formatInt(value: number): string {
  return value.toLocaleString('de-DE');
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function registryLabel(type: string | null | undefined): string {
  return REGISTRY_OPTIONS.find((item) => item.value === type)?.label || 'Sonstiges Register';
}

function deriveImportSource(type: ReferenceRegistryType, fileName: string): string {
  const base = fileName.replace(/\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return `${type}_${base || 'import'}`;
}

function emptyBeneficiaryResult(
  query: string,
  scope: BeneficiarySearchResponse['scope'],
): BeneficiarySearchResponse {
  return {
    query,
    scope,
    summary: {
      sources_considered: 0,
      records_scanned: 0,
      matches: 0,
      companies: 0,
      total_match_volume: 0,
    },
    companies: [],
    records: [],
  };
}

function emptyReferenceResult(query: string): ReferenceRegistrySearchResponse {
  return {
    query,
    summary: {
      sources_considered: 0,
      matches: 0,
    },
    hits: [],
  };
}

export default function CompanySearchPage() {
  const [profile, setProfile] = useState<SystemProfile | null>(null);
  const [beneficiarySources, setBeneficiarySources] = useState<BeneficiarySource[]>([]);
  const [referenceSources, setReferenceSources] = useState<ReferenceRegistrySource[]>([]);

  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query.trim());
  const [scope, setScope] = useState<(typeof SCOPE_OPTIONS)[number]['value']>('all');
  const [bundesland, setBundesland] = useState('');
  const [fonds, setFonds] = useState('');
  const [beneficiarySourceFilter, setBeneficiarySourceFilter] = useState('');
  const [minCost, setMinCost] = useState(0);

  const [result, setResult] = useState<BeneficiarySearchResponse>(emptyBeneficiaryResult('', 'all'));
  const [referenceResult, setReferenceResult] = useState<ReferenceRegistrySearchResponse>(emptyReferenceResult(''));
  const [selectedCompany, setSelectedCompany] = useState<BeneficiaryCompanyHit | null>(null);

  const [registryType, setRegistryType] = useState<ReferenceRegistryType>('sanctions');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importFiles, setImportFiles] = useState<File[]>([]);
  const [importSourceName, setImportSourceName] = useState('');
  const [importSheet, setImportSheet] = useState('0');
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState('');
  const [importDragOver, setImportDragOver] = useState(false);

  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');

  const hasAnyData = beneficiarySources.length > 0 || referenceSources.length > 0;

  async function loadWorkspaceData() {
    const [systemProfile, beneficiaryResponse, referenceResponse] = await Promise.all([
      getSystemProfile().catch(() => null),
      listBeneficiarySources(),
      listReferenceSources(),
    ]);
    setProfile(systemProfile);
    setBeneficiarySources(beneficiaryResponse.sources || []);
    setReferenceSources(referenceResponse.sources || []);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadWorkspaceData();
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Daten konnten nicht geladen werden.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (loading) return undefined;

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setSearching(true);
      setError('');
      try {
        const [beneficiaryResponse, registerResponse] = await Promise.all([
          beneficiarySources.length > 0
            ? searchBeneficiaries({
                q: deferredQuery,
                scope,
                bundesland: bundesland || undefined,
                fonds: fonds || undefined,
                source: beneficiarySourceFilter || undefined,
                min_cost: minCost || undefined,
                limit: 80,
                company_limit: 18,
              })
            : Promise.resolve(emptyBeneficiaryResult(deferredQuery, scope)),
          referenceSources.length > 0
            ? searchReferenceData({ q: deferredQuery, limit: 24 })
            : Promise.resolve(emptyReferenceResult(deferredQuery)),
        ]);

        if (cancelled) return;

        setResult(beneficiaryResponse);
        setReferenceResult(registerResponse);
        setSelectedCompany((current) => (
          beneficiaryResponse.companies.find((item) => item.company_name === current?.company_name)
          || beneficiaryResponse.companies[0]
          || null
        ));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Suche fehlgeschlagen.');
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, deferredQuery ? 180 : 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    beneficiarySourceFilter,
    beneficiarySources.length,
    bundesland,
    deferredQuery,
    fonds,
    loading,
    minCost,
    referenceSources.length,
    scope,
  ]);

  const bundeslaender = useMemo(
    () => [...new Set(beneficiarySources.map((item) => item.bundesland).filter(Boolean))].sort() as string[],
    [beneficiarySources],
  );
  const fondsOptions = useMemo(
    () => [...new Set(beneficiarySources.map((item) => item.fonds).filter(Boolean))].sort() as string[],
    [beneficiarySources],
  );
  const activeFilters = [bundesland, fonds, beneficiarySourceFilter, minCost > 0 ? String(minCost) : ''].filter(Boolean).length;
  const resultTitle = deferredQuery
    ? `Treffer für "${deferredQuery}"`
    : 'Top-Unternehmen nach Fördervolumen';

  const handleImportFile = (file: File | null) => {
    setImportFile(file);
    if (file && !importSourceName.trim()) {
      setImportSourceName(deriveImportSource(registryType, file.name));
    }
  };

  const handleImportFiles = (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 1) {
      handleImportFile(fileArray[0]);
    } else if (fileArray.length > 1) {
      // Erste Datei wie bisher behandeln, Rest merken
      handleImportFile(fileArray[0]);
      setImportFiles(fileArray.slice(1));
    }
  };

  const handleImport = async () => {
    if (!importFile) return;
    setImporting(true);
    setImportMessage('');
    setError('');
    try {
      // Alle Dateien sequentiell importieren (erste + restliche)
      const allFiles = [importFile, ...importFiles];
      const results: string[] = [];
      for (const file of allFiles) {
        const form = new FormData();
        form.append('file', file);
        form.append('registry_type', registryType);
        form.append('source', allFiles.length === 1
          ? (importSourceName.trim() || deriveImportSource(registryType, file.name))
          : deriveImportSource(registryType, file.name));
        form.append('sheet', importSheet || '0');
        const response = await importReferenceData(form);
        results.push(`${registryLabel(response.registry_type)}: ${formatInt(response.rows)} Zeilen in ${response.source}`);
      }
      setImportMessage(results.join(' | '));
      setImportFile(null);
      setImportFiles([]);
      setImportSourceName('');
      await loadWorkspaceData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import fehlgeschlagen.');
    } finally {
      setImporting(false);
    }
  };

  const handleDeleteRegister = async (source: string) => {
    if (!confirm(`Registerquelle "${source}" wirklich löschen?`)) return;
    try {
      await deleteReferenceSource(source);
      await loadWorkspaceData();
      setImportMessage('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Löschen fehlgeschlagen.');
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-48 w-full rounded-[34px]" />
        <div className="grid gap-4 xl:grid-cols-[1.18fr_0.82fr]">
          <Skeleton className="h-32 w-full rounded-[30px]" />
          <Skeleton className="h-64 w-full rounded-[30px]" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,rgba(7,33,54,0.98),rgba(8,79,104,0.95)_48%,rgba(203,89,53,0.88))] px-7 py-8 text-white shadow-[0_38px_120px_-64px_rgba(15,23,42,0.96)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.18),rgba(255,255,255,0)_32%)]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-100/70">Unternehmenssuche mit Registerimport</div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight lg:text-4xl">Unternehmen, Vorhaben und Referenzregister in einem Blick</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-cyan-50/85 lg:text-base">
              Diese Seite verbindet die lokalen Begünstigtenverzeichnisse mit importierten Referenzregistern wie Sanktionslisten,
              TAM, State Aid oder Cohesio. So lässt sich im Workshop sauber von einem Unternehmen zu Förderfällen und Warnsignalen springen.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/scenario/6" className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/15">
                <MapPin size={15} />
                Begünstigtenanalyse
              </Link>
              <Link to="/ai-act" className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-900 transition hover:bg-slate-100">
                <Scale size={15} />
                AI-Act-Merkblatt
              </Link>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
            <div className="rounded-[26px] border border-white/15 bg-black/10 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-cyan-100/60">Begünstigtenquellen</div>
              <div className="mt-2 text-2xl font-semibold">{formatInt(beneficiarySources.length)}</div>
              <div className="mt-1 text-sm text-cyan-50/70">Lokale Förderverzeichnisse für die Kernsuche.</div>
            </div>
            <div className="rounded-[26px] border border-white/15 bg-black/10 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-cyan-100/60">Registerquellen</div>
              <div className="mt-2 text-2xl font-semibold">{formatInt(referenceSources.length)}</div>
              <div className="mt-1 text-sm text-cyan-50/70">Importierte Referenzdaten für Hinweise und Abgleiche.</div>
            </div>
            <div className="rounded-[26px] border border-white/15 bg-black/10 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-cyan-100/60">Betriebsprofil</div>
              <div className="mt-2 flex items-center gap-2 text-lg font-semibold">
                <ShieldCheck size={18} className="text-emerald-200" />
                {profile?.privacy_mode ? 'Datenschutzmodus' : 'Standard'}
              </div>
              <div className="mt-1 text-sm text-cyan-50/70">Suche und Registerimport bleiben lokal im Workshop steuerbar.</div>
            </div>
          </div>
        </div>
      </section>

      {!hasAnyData && (
        <section className="rounded-[32px] border border-slate-200/80 bg-white/85 p-8 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.65)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="mx-auto max-w-2xl text-center">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[24px] bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">
              <Building2 size={28} />
            </div>
            <h2 className="mt-5 text-2xl font-semibold text-slate-900 dark:text-white">Noch keine Daten für die Unternehmenssuche geladen</h2>
            <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
              Laden Sie entweder ein Begünstigtenverzeichnis oder direkt ein Referenzregister hoch. Beides bleibt als eigene Quelle
              erhalten und kann danach in der Suche kombiniert werden.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link to="/scenario/6" className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-indigo-500 dark:hover:bg-indigo-400">
                <MapPin size={16} />
                Verzeichnis hochladen
              </Link>
              <Link to="/ai-act" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">
                <Scale size={16} />
                AI-Act-Merkblatt lesen
              </Link>
            </div>
          </div>
        </section>
      )}

      <section className="grid gap-4 xl:grid-cols-[1.18fr_0.82fr]">
        <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] p-4 dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-50 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">
                <Search size={20} />
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-slate-900 dark:text-white">Recherche über Unternehmen, Vorhaben und Aktenzeichen</div>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">Treffer aktualisieren sich live über die geladenen Quellen.</div>
              </div>
            </div>
            <div className="mt-4 flex items-center gap-3 rounded-[24px] border border-slate-200 bg-white/90 px-4 py-3 dark:border-slate-700 dark:bg-slate-950/60">
              <Search size={18} className="text-slate-400" />
              <input
                value={query}
                onChange={(event) => startTransition(() => setQuery(event.target.value))}
                placeholder="Unternehmen, Projektname, Aktenzeichen oder Ort suchen…"
                className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-slate-100"
                aria-label="Unternehmenssuche"
              />
              {searching && <Loader2 size={16} className="animate-spin text-cyan-600" />}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {SCOPE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setScope(option.value)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    scope === option.value
                      ? 'bg-slate-900 text-white shadow-[0_16px_32px_-22px_rgba(15,23,42,0.8)] dark:bg-cyan-500 dark:text-slate-950'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-white">
              <Filter size={15} />
              Filter für Begünstigtenquellen
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <select value={bundesland} onChange={(event) => setBundesland(event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                <option value="">Alle Bundesländer</option>
                {bundeslaender.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select value={fonds} onChange={(event) => setFonds(event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                <option value="">Alle Fonds</option>
                {fondsOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select value={beneficiarySourceFilter} onChange={(event) => setBeneficiarySourceFilter(event.target.value)} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                <option value="">Alle Quellen</option>
                {beneficiarySources.map((item) => <option key={item.source} value={item.source}>{item.bundesland || item.source}</option>)}
              </select>
              <select value={minCost} onChange={(event) => setMinCost(Number(event.target.value))} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                {MIN_COST_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </div>
            <div className="mt-4 flex items-center justify-between rounded-2xl bg-slate-50/90 px-4 py-3 text-sm dark:bg-slate-950/55">
              <span className="text-slate-500 dark:text-slate-400">Aktive Filter</span>
              <span className="font-semibold text-slate-900 dark:text-white">{formatInt(activeFilters)}</span>
            </div>
          </div>

          <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_24px_80px_-52px_rgba(15,23,42,0.62)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white">Referenzregister importieren</div>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">Sanktionslisten, TAM, State Aid, Cohesio oder eigene Prüfregister lokal einlesen.</div>
              </div>
              <Link to="/ai-act" className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
                <Scale size={13} />
                AI Act
              </Link>
            </div>
            <div className="mt-4 space-y-3">
              <select value={registryType} onChange={(event) => {
                const nextType = event.target.value as ReferenceRegistryType;
                setRegistryType(nextType);
                if (importFile && !importSourceName.trim()) {
                  setImportSourceName(deriveImportSource(nextType, importFile.name));
                }
              }} className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                {REGISTRY_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>

              <div
                onDragOver={(e) => { e.preventDefault(); setImportDragOver(true); }}
                onDragLeave={() => setImportDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setImportDragOver(false);
                  if (e.dataTransfer.files.length > 0) handleImportFiles(e.dataTransfer.files);
                }}
                className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer ${
                  importDragOver
                    ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
                    : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400'
                }`}
                onClick={() => document.getElementById('company-import-upload')?.click()}
              >
                <Upload size={24} className="mx-auto text-slate-400 mb-2" />
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {importFile
                    ? (importFiles.length > 0 ? `${importFile.name} + ${importFiles.length} weitere` : importFile.name)
                    : 'Registerdateien hierher ziehen oder klicken'}
                </p>
                <p className="text-xs text-slate-400 mt-1">XLSX, XLS oder CSV — max. 50 MB je Datei</p>
                <input
                  id="company-import-upload"
                  type="file"
                  accept=".xlsx,.xls,.xlsm,.csv"
                  multiple
                  className="hidden"
                  onChange={(event) => {
                    if (event.target.files && event.target.files.length > 0) handleImportFiles(event.target.files);
                  }}
                />
              </div>

              <input
                value={importSourceName}
                onChange={(event) => setImportSourceName(event.target.value)}
                placeholder="Technischer Quellname"
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              />
              <input
                value={importSheet}
                onChange={(event) => setImportSheet(event.target.value)}
                placeholder="Blattname oder Index, z.B. 0"
                className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              />

              <button
                onClick={handleImport}
                disabled={!importFile || importing}
                className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-60 dark:bg-cyan-500 dark:text-slate-950 dark:hover:bg-cyan-400"
              >
                {importing ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                {importing ? 'Import läuft…' : 'Register importieren'}
              </button>
            </div>

            {importMessage && (
              <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/40 dark:text-emerald-300">
                {importMessage}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="rounded-[28px] border border-violet-200 bg-violet-50/90 px-5 py-4 shadow-[0_20px_70px_-48px_rgba(109,40,217,0.25)] dark:border-violet-900/70 dark:bg-violet-950/30">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-violet-900 dark:text-violet-200">
              <Scale size={16} />
              AI-Act-Leitplanke für Prüfer
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-violet-800/85 dark:text-violet-200/80">
              Seit dem 2. Februar 2025 gelten Verbote und AI-Literacy-Pflichten. Für den Workshop heißt das:
              KI- und Registertreffer dürfen Hinweise liefern, aber keine belastbare Entscheidung ohne menschliche Prüfung ersetzen.
            </p>
          </div>
          <Link to="/ai-act" className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-medium text-violet-900 transition hover:bg-violet-100 dark:bg-slate-900 dark:text-violet-200 dark:hover:bg-slate-800">
            Vollständige Zusammenfassung
            <ArrowUpRight size={15} />
          </Link>
        </div>
      </section>

      {profile?.privacy_mode && (
        <div className="rounded-[26px] border border-emerald-200 bg-emerald-50/90 px-5 py-4 text-sm text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/50 dark:text-emerald-300">
          <div className="flex items-center gap-2 font-medium">
            <ShieldCheck size={16} />
            Datenschutzmodus aktiv
          </div>
          <p className="mt-1 leading-6">
            Die Suchmaske arbeitet ohne externe Recherche und nutzt nur die im Workshop eingelesenen Verzeichnisse und Registerdateien.
          </p>
        </div>
      )}

      {error && (
        <div className="rounded-[24px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_22px_76px_-52px_rgba(15,23,42,0.58)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900 dark:text-white">{resultTitle}</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {formatInt(result.summary.matches)} Treffer in {formatInt(result.summary.sources_considered)} Begünstigtenquellen
              </div>
            </div>
            <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-300">
              {result.summary.total_match_volume ? formatCurrency(result.summary.total_match_volume) : '0 €'}
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {result.companies.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-slate-200 bg-slate-50/80 px-4 py-10 text-center dark:border-slate-700 dark:bg-slate-950/45">
                <Sparkles size={22} className="mx-auto text-slate-300 dark:text-slate-600" />
                <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Keine passenden Unternehmen in den Förderverzeichnissen gefunden.</p>
              </div>
            ) : (
              result.companies.map((company) => (
                <button
                  key={`${company.company_name}-${company.sources.join('|')}`}
                  onClick={() => setSelectedCompany(company)}
                  className={`w-full rounded-[24px] border px-4 py-4 text-left transition ${
                    selectedCompany?.company_name === company.company_name
                      ? 'border-cyan-200 bg-cyan-50/80 shadow-[0_18px_40px_-30px_rgba(8,145,178,0.65)] dark:border-cyan-900 dark:bg-cyan-950/35'
                      : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-slate-700 dark:hover:bg-slate-900/80'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Building2 size={16} className="text-cyan-600 dark:text-cyan-300" />
                        <div className="truncate text-base font-semibold text-slate-900 dark:text-white">{company.company_name}</div>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {company.bundeslaender.slice(0, 3).map((item) => (
                          <span key={item} className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{item}</span>
                        ))}
                        {company.matched_fields.slice(0, 2).map((item) => (
                          <span key={item} className="rounded-full bg-cyan-50 px-2.5 py-1 text-[11px] font-medium text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">
                            Match: {MATCH_LABELS[item] || item}
                          </span>
                        ))}
                      </div>
                    </div>
                    <ArrowUpRight size={16} className="mt-1 shrink-0 text-slate-300 dark:text-slate-600" />
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl bg-slate-50 px-3 py-3 dark:bg-slate-900/80">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Volumen</div>
                      <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{company.total_kosten_label}</div>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-3 py-3 dark:bg-slate-900/80">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Vorhaben</div>
                      <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{formatInt(company.project_count)}</div>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_22px_76px_-52px_rgba(15,23,42,0.58)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
          {!selectedCompany ? (
            <div className="flex h-full min-h-[420px] items-center justify-center rounded-[24px] border border-dashed border-slate-200 bg-slate-50/80 text-center dark:border-slate-700 dark:bg-slate-950/45">
              <div className="max-w-sm px-6">
                <Layers3 size={24} className="mx-auto text-slate-300 dark:text-slate-600" />
                <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Wählen Sie links ein Unternehmen aus, um die zugehörigen Vorhaben zu sehen.</p>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="rounded-[26px] border border-slate-200/80 bg-[linear-gradient(145deg,rgba(248,250,252,0.95),rgba(239,246,255,0.92))] p-5 dark:border-slate-800 dark:bg-[linear-gradient(145deg,rgba(15,23,42,0.7),rgba(8,47,73,0.45))]">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400 dark:text-slate-500">Unternehmensansicht</div>
                    <h2 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{selectedCompany.company_name}</h2>
                  </div>
                  <div className="rounded-[22px] bg-white/90 px-4 py-3 text-right shadow-sm dark:bg-slate-950/60">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Gesamtvolumen</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{selectedCompany.total_kosten_label}</div>
                  </div>
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-3">
                  <div className="rounded-2xl bg-white/85 px-4 py-4 dark:bg-slate-950/55">
                    <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      <FileText size={14} />
                      Vorhaben
                    </div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{formatInt(selectedCompany.project_count)}</div>
                  </div>
                  <div className="rounded-2xl bg-white/85 px-4 py-4 dark:bg-slate-950/55">
                    <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      <MapPin size={14} />
                      Standorte
                    </div>
                    <div className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{selectedCompany.standorte.slice(0, 2).join(' · ') || 'k.A.'}</div>
                  </div>
                  <div className="rounded-2xl bg-white/85 px-4 py-4 dark:bg-slate-950/55">
                    <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      <Wallet size={14} />
                      Fonds
                    </div>
                    <div className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{selectedCompany.fonds.join(' · ') || 'k.A.'}</div>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {selectedCompany.bundeslaender.map((item) => (
                    <span key={item} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{item}</span>
                  ))}
                  {selectedCompany.aktenzeichen.map((item) => (
                    <span key={item} className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">{item}</span>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">Zugeordnete Vorhaben</div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">Einzelvorhaben aus den geladenen Förderverzeichnissen.</div>
                  </div>
                  <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                    {formatInt(selectedCompany.projects.length)} sichtbar
                  </div>
                </div>

                <div className="space-y-3">
                  {selectedCompany.projects.map((project, index) => (
                    <div key={`${project.project_name}-${project.aktenzeichen}-${index}`} className="rounded-[24px] border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/45">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-slate-900 dark:text-white">
                            {project.project_name || 'Vorhaben ohne Bezeichnung'}
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {project.aktenzeichen && (
                              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                {project.aktenzeichen}
                              </span>
                            )}
                            {project.location && (
                              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                {project.location}
                              </span>
                            )}
                            {project.matched_fields.map((item) => (
                              <span key={`${item}-${index}`} className="rounded-full bg-cyan-50 px-2.5 py-1 text-[11px] font-medium text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">
                                {MATCH_LABELS[item] || item}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-slate-50 px-3 py-2 text-right dark:bg-slate-900/80">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Volumen</div>
                          <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{project.kosten_label}</div>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 md:grid-cols-3">
                        <div className="rounded-2xl bg-slate-50 px-3 py-3 text-sm text-slate-600 dark:bg-slate-900/75 dark:text-slate-300">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Quelle</div>
                          <div className="mt-1 font-medium text-slate-900 dark:text-white">{project.source}</div>
                        </div>
                        <div className="rounded-2xl bg-slate-50 px-3 py-3 text-sm text-slate-600 dark:bg-slate-900/75 dark:text-slate-300">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Bundesland / Fonds</div>
                          <div className="mt-1 font-medium text-slate-900 dark:text-white">
                            {[project.bundesland, project.fonds].filter(Boolean).join(' · ') || 'k.A.'}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-slate-50 px-3 py-3 text-sm text-slate-600 dark:bg-slate-900/75 dark:text-slate-300">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Periode / Kategorie</div>
                          <div className="mt-1 font-medium text-slate-900 dark:text-white">
                            {[project.periode, project.category].filter(Boolean).join(' · ') || 'k.A.'}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-[30px] border border-slate-200/80 bg-white/88 p-5 shadow-[0_22px_76px_-52px_rgba(15,23,42,0.58)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/75">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900 dark:text-white">Registertreffer und Quellenübersicht</div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {formatInt(referenceResult.summary.matches)} Treffer in {formatInt(referenceResult.summary.sources_considered)} Registerquellen
              {referenceResult.summary.matches > referenceResult.hits.length
                ? ` · Anzeige der stärksten ${formatInt(referenceResult.hits.length)}`
                : ''}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {referenceSources.map((item) => (
              <span key={item.source} className={`rounded-full px-3 py-1 text-xs font-medium ${REGISTRY_STYLES[item.registry_type || 'other'] || REGISTRY_STYLES.other}`}>
                {registryLabel(item.registry_type)} · {item.source}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_0.72fr]">
          <div className="space-y-3">
            {!deferredQuery ? (
              <div className="rounded-[24px] border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center dark:border-slate-700 dark:bg-slate-950/45">
                <Globe2 size={22} className="mx-auto text-slate-300 dark:text-slate-600" />
                <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Die Registersuche startet, sobald ein Suchbegriff eingegeben wird.</p>
              </div>
            ) : referenceSources.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center dark:border-slate-700 dark:bg-slate-950/45">
                <Upload size={22} className="mx-auto text-slate-300 dark:text-slate-600" />
                <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Noch keine Referenzregister importiert.</p>
              </div>
            ) : referenceResult.hits.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center dark:border-slate-700 dark:bg-slate-950/45">
                <Sparkles size={22} className="mx-auto text-slate-300 dark:text-slate-600" />
                <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Keine Registertreffer für den aktuellen Suchbegriff.</p>
              </div>
            ) : (
              referenceResult.hits.map((hit, index) => (
                <div key={`${hit.source}-${hit.company_name}-${index}`} className="rounded-[24px] border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/45">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${REGISTRY_STYLES[hit.registry_type] || REGISTRY_STYLES.other}`}>
                          {registryLabel(hit.registry_type)}
                        </span>
                        <span className="text-xs text-slate-400">{hit.source}</span>
                      </div>
                      <div className="mt-3 text-base font-semibold text-slate-900 dark:text-white">{hit.company_name}</div>
                      {hit.project_name && (
                        <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">{hit.project_name}</div>
                      )}
                    </div>
                    <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      Score {hit.match_score}
                    </div>
                  </div>

                  {(hit.description || hit.status || hit.country || hit.location || hit.aktenzeichen) && (
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {hit.description && (
                        <div className="rounded-2xl bg-slate-50 px-3 py-3 text-sm text-slate-600 dark:bg-slate-900/75 dark:text-slate-300">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Beschreibung</div>
                          <div className="mt-1 line-clamp-3">{hit.description}</div>
                        </div>
                      )}
                      <div className="rounded-2xl bg-slate-50 px-3 py-3 text-sm text-slate-600 dark:bg-slate-900/75 dark:text-slate-300">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Kontext</div>
                        <div className="mt-1 space-y-1">
                          {hit.aktenzeichen && <div>Aktenzeichen: <span className="font-medium text-slate-900 dark:text-white">{hit.aktenzeichen}</span></div>}
                          {hit.location && <div>Ort: <span className="font-medium text-slate-900 dark:text-white">{hit.location}</span></div>}
                          {hit.country && <div>Land: <span className="font-medium text-slate-900 dark:text-white">{hit.country}</span></div>}
                          {hit.status && <div>Status: <span className="font-medium text-slate-900 dark:text-white">{hit.status}</span></div>}
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
                    {hit.matched_fields.map((item) => (
                      <span key={`${item}-${index}`} className="rounded-full bg-cyan-50 px-2.5 py-1 text-[11px] font-medium text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">
                        {MATCH_LABELS[item] || item}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="rounded-[26px] border border-slate-200 bg-slate-50/90 p-4 dark:border-slate-800 dark:bg-slate-950/45">
            <div className="text-sm font-semibold text-slate-900 dark:text-white">Importierte Registerquellen</div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">Diese Quellen stehen für den Abgleich zur Verfügung.</div>
            <div className="mt-4 space-y-3">
              {referenceSources.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-white/80 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">
                  Noch keine Registerquellen geladen.
                </div>
              ) : (
                referenceSources.map((item) => (
                  <div key={item.source} className="rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/70">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${REGISTRY_STYLES[item.registry_type || 'other'] || REGISTRY_STYLES.other}`}>
                            {registryLabel(item.registry_type)}
                          </span>
                          <span className="text-sm font-medium text-slate-900 dark:text-white">{item.source}</span>
                        </div>
                        <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                          {formatInt(item.row_count)} Zeilen{item.filename ? ` · ${item.filename}` : ''}
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteRegister(item.source)}
                        className="rounded-full p-2 text-slate-400 transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-300"
                        aria-label={`${item.source} löschen`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
