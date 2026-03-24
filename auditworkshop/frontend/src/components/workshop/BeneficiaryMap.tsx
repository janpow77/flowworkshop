import { useEffect, useState, useCallback } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import { Loader2, MapPin, AlertTriangle, Upload, X, CheckCircle, FileSpreadsheet, Trash2, ShieldCheck } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import { getSystemProfile, type SystemProfile } from '../../lib/api';

interface Beneficiary {
  name: string;
  projekt: string;
  kosten: number;
  standort: string;
  kategorie: string;
  bundesland: string;
  fonds: string;
  lat: number;
  lon: number;
}

interface SourceInfo {
  source: string;
  bundesland: string | null;
  fonds: string | null;
  periode: string | null;
  count: number;
  total_rows: number;
}

// Bundesland → Farbe
const BL_COLORS: Record<string, string> = {
  'Hessen': '#3b82f6', 'Sachsen': '#10b981', 'Bayern': '#6366f1',
  'Nordrhein-Westfalen': '#f59e0b', 'NRW': '#f59e0b',
  'Baden-Württemberg': '#ec4899', 'Niedersachsen': '#14b8a6',
  'Brandenburg': '#8b5cf6', 'Thüringen': '#ef4444',
  'Sachsen-Anhalt': '#f97316', 'Berlin': '#06b6d4',
  'Mecklenburg-Vorpommern': '#84cc16', 'Schleswig-Holstein': '#a855f7',
  'Rheinland-Pfalz': '#e11d48', 'Saarland': '#0ea5e9',
  'Hamburg': '#d946ef', 'Bremen': '#fbbf24',
};
function getBlColor(bl: string): string { return BL_COLORS[bl] || '#6b7280'; }
function formatEur(val: number): string { return val.toLocaleString('de-DE', { maximumFractionDigits: 0 }) + ' €'; }

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) {
      import('leaflet').then((L) => {
        map.fitBounds(L.latLngBounds(points), { padding: [30, 30] });
      });
    }
  }, [points, map]);
  return null;
}

export default function BeneficiaryMap({ className }: { className?: string }) {
  const [data, setData] = useState<Beneficiary[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [profile, setProfile] = useState<SystemProfile | null>(null);

  // Upload
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ status: string; bundesland: string; fonds: string; rows: number } | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Filter
  const [filterBl, setFilterBl] = useState('');
  const [minKosten, setMinKosten] = useState(0);

  const loadMap = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/beneficiaries/map');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json.beneficiaries || []);
      setSources(json.sources || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMap(); }, [loadMap]);
  useEffect(() => {
    getSystemProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setUploadResult(null);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/api/beneficiaries/upload', { method: 'POST', body: form });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'Upload fehlgeschlagen');
      setUploadResult({
        status: json.status,
        bundesland: json.metadata.bundesland,
        fonds: json.metadata.fonds,
        rows: json.rows,
      });
      // Karte neu laden
      await loadMap();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload-Fehler');
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleDeleteSource = async (source: string) => {
    if (!confirm('Verzeichnis entfernen?')) return;
    await fetch(`/api/beneficiaries/${encodeURIComponent(source)}`, { method: 'DELETE' });
    await loadMap();
  };

  const bundeslaender = [...new Set(data.map((b) => b.bundesland).filter(Boolean))].sort();
  const filtered = data.filter((b) => {
    if (filterBl && b.bundesland !== filterBl) return false;
    if (minKosten > 0 && b.kosten < minKosten) return false;
    return true;
  });
  const points: [number, number][] = filtered.map((b) => [b.lat, b.lon]);
  const totalKosten = filtered.reduce((s, b) => s + b.kosten, 0);

  const getRadius = (kosten: number): number => {
    if (kosten <= 0) return 3;
    return Math.max(3, Math.min(18, Math.log10(kosten) * 2));
  };

  return (
    <div className={`space-y-4 ${className || ''}`}>
      {/* Upload-Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !uploading && document.getElementById('beneficiary-upload')?.click()}
        className={`rounded-xl border-2 border-dashed p-5 text-center cursor-pointer transition-colors ${
          dragOver
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
            : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400 bg-white dark:bg-slate-900'
        }`}
        role="button"
        tabIndex={0}
        aria-label="Begünstigtenverzeichnis hochladen"
      >
        {uploading ? (
          <div className="flex items-center justify-center gap-2 text-indigo-600">
            <Loader2 size={20} className="animate-spin" />
            <span className="text-sm font-medium">Wird eingelesen und geocodiert…</span>
          </div>
        ) : (
          <>
            <Upload size={22} className="mx-auto text-slate-400 mb-1" />
            <p className="text-sm text-slate-600 dark:text-slate-400 font-medium">
              Begünstigtenverzeichnis (XLSX) hierher ziehen
            </p>
            <p className="text-xs text-slate-400 mt-0.5">
              Bundesland, Fonds und Förderperiode werden automatisch erkannt · Duplikate werden ersetzt
            </p>
          </>
        )}
        <input
          id="beneficiary-upload"
          type="file"
          accept=".xlsx,.xls,.xlsm"
          className="hidden"
          onChange={(e) => { if (e.target.files?.[0]) handleUpload(e.target.files[0]); }}
          disabled={uploading}
        />
      </div>

      {/* Upload-Ergebnis */}
      {uploadResult && (
        <div className="rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 px-4 py-2 flex items-center gap-2 text-sm">
          <CheckCircle size={16} className="text-green-600 shrink-0" />
          <span className="text-green-700 dark:text-green-300">
            <strong>{uploadResult.bundesland}</strong> {uploadResult.fonds} — {uploadResult.rows.toLocaleString('de-DE')} Vorhaben eingelesen
            {uploadResult.status === 'replaced' && ' (vorherige Version ersetzt)'}
          </span>
          <button onClick={() => setUploadResult(null)} className="ml-auto text-green-400 hover:text-green-600">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Fehler */}
      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-2 flex items-center gap-2 text-sm">
          <AlertTriangle size={16} className="text-red-500 shrink-0" />
          <span className="text-red-600 dark:text-red-400">{error}</span>
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600"><X size={14} /></button>
        </div>
      )}

      {/* Eingelesene Verzeichnisse */}
      {sources.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {sources.map((s) => (
            <div key={s.source} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 group">
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: getBlColor(s.bundesland || '') }} />
              <FileSpreadsheet size={12} className="text-slate-400" />
              <span className="font-medium text-slate-700 dark:text-slate-300">{s.bundesland || s.source}</span>
              {s.fonds && <span className="text-slate-400">{s.fonds}</span>}
              {s.periode && <span className="text-slate-400">{s.periode}</span>}
              <span className="text-slate-400">·</span>
              <span className="text-slate-500">{s.count.toLocaleString('de-DE')}/{s.total_rows.toLocaleString('de-DE')}</span>
              <button
                onClick={() => handleDeleteSource(s.source)}
                className="text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 ml-0.5"
                aria-label={`${s.bundesland} entfernen`}
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      {profile && profile.privacy_mode && (
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 px-1">
          <ShieldCheck size={12} />
          <span>Geocoding nutzt lokalen Cache · Karten-Tiles via OpenStreetMap</span>
        </div>
      )}

      {/* Karte */}
      {loading ? (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-8 text-center">
          <Loader2 size={20} className="animate-spin mx-auto text-indigo-500 mb-2" />
          <p className="text-sm text-slate-400">Lade Kartendaten…</p>
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 p-10 text-center">
          <MapPin size={32} className="mx-auto text-slate-300 mb-2" />
          <p className="text-sm text-slate-400">Noch keine Begünstigtenverzeichnisse eingelesen.</p>
          <p className="text-xs text-slate-400 mt-1">Laden Sie eine XLSX-Transparenzliste hoch.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
          {/* Karten-Header */}
          <div className="px-4 py-2.5 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2 text-sm">
              <MapPin size={15} className="text-indigo-500" />
              <span className="font-semibold text-slate-700 dark:text-slate-300">
                {filtered.length.toLocaleString('de-DE')} Vorhaben
              </span>
              {totalKosten > 0 && (
                <span className="text-slate-400">· {formatEur(totalKosten)}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {bundeslaender.length > 1 && (
                <select value={filterBl} onChange={(e) => setFilterBl(e.target.value)}
                  className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700"
                  aria-label="Bundesland filtern">
                  <option value="">Alle Bundesländer</option>
                  {bundeslaender.map((bl) => <option key={bl} value={bl}>{bl}</option>)}
                </select>
              )}
              <select value={minKosten} onChange={(e) => setMinKosten(Number(e.target.value))}
                className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700"
                aria-label="Mindestbetrag">
                <option value={0}>Alle Beträge</option>
                <option value={100000}>&gt; 100.000 €</option>
                <option value={500000}>&gt; 500.000 €</option>
                <option value={1000000}>&gt; 1 Mio €</option>
                <option value={5000000}>&gt; 5 Mio €</option>
              </select>
            </div>
          </div>

          <div className="beneficiary-map-shell h-[500px]">
            <MapContainer center={[51.0, 10.5]} zoom={6} className="h-full w-full" scrollWheelZoom={true}>
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {points.length > 0 && <FitBounds points={points} />}
              {filtered.map((b, i) => (
                <CircleMarker key={`${b.lat}-${b.lon}-${i}`} center={[b.lat, b.lon]}
                  radius={getRadius(b.kosten)}
                  pathOptions={{ color: getBlColor(b.bundesland), fillColor: getBlColor(b.bundesland), fillOpacity: 0.5, weight: 1 }}>
                  <Popup>
                    <div className="text-xs leading-relaxed min-w-[220px]">
                      <p className="font-bold text-sm mb-1">{b.name}</p>
                      {b.projekt && <p className="text-slate-600 mb-1 line-clamp-2">{b.projekt}</p>}
                      {b.kosten > 0 && <p><strong>Gesamtkosten:</strong> {formatEur(b.kosten)}</p>}
                      <p><strong>Standort:</strong> {b.standort}</p>
                      <p><strong>Land:</strong> {b.bundesland}{b.fonds && ` · ${b.fonds}`}</p>
                      {b.kategorie && <p><strong>Ziel:</strong> {b.kategorie}</p>}
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </div>

          {/* Legende */}
          <div className="px-4 py-2 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 flex flex-wrap gap-3 items-center">
            {bundeslaender.map((bl) => (
              <button key={bl} onClick={() => setFilterBl(filterBl === bl ? '' : bl)}
                className={`flex items-center gap-1.5 text-xs transition-opacity ${filterBl && filterBl !== bl ? 'opacity-30' : ''}`}>
                <span className="w-3 h-3 rounded-full" style={{ backgroundColor: getBlColor(bl) }} />
                {bl}
              </button>
            ))}
            <span className="text-[10px] text-slate-400 ml-auto">
              Kreisgröße = Gesamtkosten (log){profile?.privacy_mode ? ' · lokale Koordinaten' : ''}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
