import { useEffect, useState, useCallback, useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import { Loader2, MapPin, AlertTriangle, Upload, X, CheckCircle, FileSpreadsheet, Trash2, ShieldCheck } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import { getSystemProfile, getWorkshopAuthHeaders, type SystemProfile, type CountryCode } from '../../lib/api';

interface Beneficiary {
  name: string;
  projekt: string;
  kosten: number;
  standort: string;
  kategorie: string;
  bundesland: string;
  fonds: string;
  country_code?: CountryCode | null;
  country_name?: string | null;
  lat: number;
  lon: number;
  beginn?: string;
  ende?: string;
}

// Gruppe von Vorhaben am gleichen Standort (lat/lon).
// Mehrere Vorhaben desselben Begünstigten oder verschiedener Begünstigter
// teilen sich denselben Marker und werden im Popup zusammen angezeigt.
interface MapPin {
  lat: number;
  lon: number;
  standort: string;
  bundesland: string;
  fonds: string;
  country_name?: string | null;
  total_kosten: number;
  beneficiaries: Beneficiary[];
}

interface SourceInfo {
  source: string;
  bundesland: string | null;
  fonds: string | null;
  periode: string | null;
  region_label?: string | null;
  country_code?: CountryCode | null;
  country_name?: string | null;
  count: number;
  total_rows: number;
}

// Bundesland/Region → Farbe (DE + AT)
const BL_COLORS: Record<string, string> = {
  // Deutschland
  'Hessen': '#3b82f6', 'Sachsen': '#10b981', 'Bayern': '#6366f1',
  'Nordrhein-Westfalen': '#f59e0b', 'NRW': '#f59e0b',
  'Baden-Württemberg': '#ec4899', 'Niedersachsen': '#14b8a6',
  'Brandenburg': '#8b5cf6', 'Thüringen': '#ef4444',
  'Sachsen-Anhalt': '#f97316', 'Berlin': '#06b6d4',
  'Mecklenburg-Vorpommern': '#84cc16', 'Schleswig-Holstein': '#a855f7',
  'Rheinland-Pfalz': '#e11d48', 'Saarland': '#0ea5e9',
  'Hamburg': '#d946ef', 'Bremen': '#fbbf24',
  // Bundesebene (für Bundesfonds wie ISF und AMIF)
  'Bund': '#1e40af',
  // Österreich
  'Burgenland': '#dc2626', 'Kärnten': '#0891b2', 'Niederösterreich': '#2563eb',
  'Oberösterreich': '#7c3aed', 'Salzburg': '#db2777', 'Steiermark': '#16a34a',
  'Tirol': '#ea580c', 'Vorarlberg': '#0d9488', 'Wien': '#9333ea',
};

const COUNTRY_CENTER: Record<string, { center: [number, number]; zoom: number }> = {
  DE: { center: [51.0, 10.5], zoom: 6 },
  AT: { center: [47.6, 13.5], zoom: 7 },
};
function getBlColor(bl: string): string { return BL_COLORS[bl] || '#6b7280'; }
function formatEur(val: number): string { return val.toLocaleString('de-DE', { maximumFractionDigits: 0 }) + ' €'; }

// "2024-06-28" → "28.06.2024"; "2024-06-28T..." → "28.06.2024"; sonst Roh
function formatDateDe(iso: string | undefined | null): string {
  if (!iso) return '';
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : String(iso);
}
function formatPeriod(beginn?: string, ende?: string): string {
  const b = formatDateDe(beginn);
  const e = formatDateDe(ende);
  if (b && e) return `${b} – ${e}`;
  if (b) return `seit ${b}`;
  if (e) return `bis ${e}`;
  return '';
}

// Gruppiert eine flache Beneficiary-Liste nach Standort (lat/lon).
// Verwendet einen 4-Nachkommastellen-Schlüssel — geocodierte Koordinaten
// gleicher Adressen kollidieren in der Regel ohnehin.
function groupByLocation(items: Beneficiary[]): MapPin[] {
  const map = new Map<string, MapPin>();
  for (const b of items) {
    const key = `${b.lat.toFixed(4)},${b.lon.toFixed(4)}`;
    let pin = map.get(key);
    if (!pin) {
      pin = {
        lat: b.lat, lon: b.lon, standort: b.standort,
        bundesland: b.bundesland, fonds: b.fonds,
        country_name: b.country_name,
        total_kosten: 0, beneficiaries: [],
      };
      map.set(key, pin);
    }
    pin.beneficiaries.push(b);
    pin.total_kosten += b.kosten || 0;
    // Bundesland-Mehrfachnennung im Pin: vermerken wenn unterschiedlich
    if (b.bundesland && b.bundesland !== pin.bundesland) {
      pin.bundesland = `${pin.bundesland}/${b.bundesland}`;
    }
  }
  return Array.from(map.values()).sort((a, b) => b.total_kosten - a.total_kosten);
}

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

type BeneficiaryMapProps = {
  className?: string;
  countryCode?: CountryCode | '';
};

export default function BeneficiaryMap({ className, countryCode = 'DE' }: BeneficiaryMapProps) {
  const [data, setData] = useState<Beneficiary[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [regionLabel, setRegionLabel] = useState<string>('Bundesland');
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

  const countryQuery = countryCode ? `?country_code=${countryCode}` : '';

  const loadMap = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/beneficiaries/map${countryQuery}`, {
        headers: { ...getWorkshopAuthHeaders() },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json.beneficiaries || []);
      setSources(json.sources || []);
      if (typeof json.region_label === 'string' && json.region_label) {
        setRegionLabel(json.region_label);
      } else {
        setRegionLabel(countryCode === 'AT' ? 'Bundesland' : 'Bundesland');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    } finally {
      setLoading(false);
    }
  }, [countryQuery, countryCode]);

  useEffect(() => { setFilterBl(''); }, [countryCode]);
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
      const res = await fetch('/api/beneficiaries/upload', {
        method: 'POST',
        headers: { ...getWorkshopAuthHeaders() },
        body: form,
      });
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
    await fetch(`/api/beneficiaries/${encodeURIComponent(source)}`, {
      method: 'DELETE',
      headers: { ...getWorkshopAuthHeaders() },
    });
    await loadMap();
  };

  const bundeslaender = [...new Set(data.map((b) => b.bundesland).filter(Boolean))].sort();
  const filtered = data.filter((b) => {
    if (filterBl && b.bundesland !== filterBl) return false;
    if (minKosten > 0 && b.kosten < minKosten) return false;
    return true;
  });
  const pins = useMemo(() => groupByLocation(filtered), [filtered]);
  const points: [number, number][] = pins.map((p) => [p.lat, p.lon]);
  const totalKosten = filtered.reduce((s, b) => s + b.kosten, 0);
  const allowRemoteTiles = profile?.allow_remote_tiles ?? false;
  const mapView = useMemo(() => {
    if (countryCode && COUNTRY_CENTER[countryCode]) return COUNTRY_CENTER[countryCode];
    return { center: [49.5, 11.5] as [number, number], zoom: 5 };
  }, [countryCode]);
  const emptyStateText = useMemo(() => {
    if (countryCode === 'AT') return 'Für Österreich sind noch keine Begünstigtenverzeichnisse geladen.';
    if (countryCode === 'DE') return 'Noch keine deutschen Begünstigtenverzeichnisse eingelesen.';
    return 'Noch keine Begünstigtenverzeichnisse eingelesen.';
  }, [countryCode]);

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
          <span>Geocoding nutzt lokalen Cache · Karten-Tiles bleiben lokal deaktiviert</span>
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
          <p className="text-sm text-slate-400">{emptyStateText}</p>
          <p className="text-xs text-slate-400 mt-1">
            {countryCode === 'AT'
              ? 'Quellen: efre.gv.at/projekte/projektlandkarte und esf.at/projekte/liste-der-vorhaben-2/.'
              : 'Laden Sie eine XLSX-Transparenzliste hoch.'}
          </p>
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
              <span className="text-slate-400">
                an {pins.length.toLocaleString('de-DE')} Standort{pins.length === 1 ? '' : 'en'}
              </span>
              {totalKosten > 0 && (
                <span className="text-slate-400">· {formatEur(totalKosten)}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {bundeslaender.length > 1 && (
                <select value={filterBl} onChange={(e) => setFilterBl(e.target.value)}
                  className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700"
                  aria-label={`${regionLabel} filtern`}>
                  <option value="">Alle {regionLabel === 'Bundesland' ? 'Bundesländer' : `${regionLabel}e`}</option>
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
            <div className="relative h-full w-full">
              <MapContainer key={countryCode || 'all'} center={mapView.center} zoom={mapView.zoom} className="h-full w-full" scrollWheelZoom={true}>
                {allowRemoteTiles && (
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                )}
                {points.length > 0 && <FitBounds points={points} />}
                {pins.map((pin, i) => {
                  // Begünstigte am gleichen Standort nochmal nach Name gruppieren —
                  // ein Begünstigter mit mehreren Vorhaben am selben Ort soll
                  // einen Block mit allen Vorhaben darunter bekommen.
                  const byBeneficiary = new Map<string, Beneficiary[]>();
                  for (const b of pin.beneficiaries) {
                    const arr = byBeneficiary.get(b.name) || [];
                    arr.push(b);
                    byBeneficiary.set(b.name, arr);
                  }
                  const groups = Array.from(byBeneficiary.entries())
                    .map(([name, vorhaben]) => ({
                      name,
                      vorhaben: vorhaben.sort((a, b) =>
                        (a.beginn || '').localeCompare(b.beginn || '')),
                      total: vorhaben.reduce((s, v) => s + (v.kosten || 0), 0),
                    }))
                    .sort((a, b) => b.total - a.total);
                  return (
                    <CircleMarker key={`${pin.lat}-${pin.lon}-${i}`} center={[pin.lat, pin.lon]}
                      radius={getRadius(pin.total_kosten)}
                      pathOptions={{ color: getBlColor(pin.bundesland), fillColor: getBlColor(pin.bundesland), fillOpacity: 0.5, weight: 1 }}>
                      <Popup maxWidth={420}>
                        <div className="text-xs leading-relaxed min-w-[260px] max-w-[400px]">
                          <p className="font-bold text-sm mb-1">{pin.standort}</p>
                          <p className="text-slate-500 mb-2">
                            {pin.beneficiaries.length} Vorhaben · {formatEur(pin.total_kosten)}
                            {pin.country_name && ` · ${pin.country_name}`}
                          </p>
                          <div className="max-h-[280px] overflow-y-auto pr-1 space-y-2">
                            {groups.map((g, gi) => (
                              <div key={gi} className="border-l-2 pl-2"
                                   style={{ borderColor: getBlColor(g.vorhaben[0].bundesland) }}>
                                <p className="font-semibold text-slate-800 dark:text-slate-200">{g.name}</p>
                                <p className="text-[10px] text-slate-500 mb-1">
                                  {g.vorhaben.length} Vorhaben · {formatEur(g.total)}
                                  {g.vorhaben[0].fonds && ` · ${g.vorhaben[0].fonds}`}
                                </p>
                                <ul className="space-y-1">
                                  {g.vorhaben.map((v, vi) => {
                                    const period = formatPeriod(v.beginn, v.ende);
                                    return (
                                      <li key={vi} className="text-slate-600 dark:text-slate-400">
                                        {v.projekt && (
                                          <span className="block line-clamp-2">{v.projekt}</span>
                                        )}
                                        <span className="text-[10px] text-slate-500 flex flex-wrap gap-x-2">
                                          {v.kosten > 0 && <span>{formatEur(v.kosten)}</span>}
                                          {period && <span>📅 {period}</span>}
                                          {v.kategorie && <span className="line-clamp-1">{v.kategorie}</span>}
                                        </span>
                                      </li>
                                    );
                                  })}
                                </ul>
                              </div>
                            ))}
                          </div>
                        </div>
                      </Popup>
                    </CircleMarker>
                  );
                })}
              </MapContainer>
              {!allowRemoteTiles && (
                <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-md bg-white/90 dark:bg-slate-900/90 px-2 py-1 text-[10px] text-slate-500 shadow">
                  Kartenkacheln lokal deaktiviert
                </div>
              )}
            </div>
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
