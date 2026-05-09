import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap, GeoJSON } from 'react-leaflet';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type { Layer, PathOptions } from 'leaflet';
import {
  Loader2, MapPin, AlertTriangle, X, FileSpreadsheet,
  Trash2, ShieldCheck, FileImage, FileText, Maximize2, Minimize2,
  Layers,
} from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import {
  getSystemProfile,
  getWorkshopAuthHeaders,
  type SystemProfile,
  type CountryCode,
} from '../../lib/api';
import { useExport } from '../../lib/useExport';

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

// "EFRE" + "Bremen" → "EFRE Bremen"; einzelner Wert → der Wert; sonst leer.
function formatFondsBl(fonds?: string | null, bundesland?: string | null): string {
  const f = (fonds || '').trim();
  const b = (bundesland || '').trim();
  if (f && b) return `${f} ${b}`;
  return f || b || '';
}

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
  // Wenn gesetzt + nicht leer: Karte zeigt nur Begünstigte mit Namen-Match
  // (case-insensitive). null/undefined/[] = Default (alle anzeigen).
  highlightNames?: string[] | null;
  // Wenn false, blendet Bundesland-/Mindestbetrag-Filter und die linke
  // Statistikzeile aus. Sinnvoll in Tabs, in denen die Karte nur als
  // visueller Begleiter dient (Unternehmenssuche, KI-Auswertung) — dort
  // filtert die Suche bzw. der Country-Picker schon ausserhalb der Karte.
  showFilterControls?: boolean;
  // Choropleth-Layer (NUTS-1) zusätzlich/statt Pins. Default off.
  choroplethEnabled?: boolean;
  choroplethMetric?: 'count' | 'value';
};

interface ChoroplethRegion {
  nuts_code: string;
  name: string;
  value: number;
  value_label: string;
}

interface ChoroplethResponse {
  regions: ChoroplethRegion[];
  max_value: number;
}

// 5-stufige sequentielle Amber→Orange-Skala (hell → dunkel). Passt zum
// Workshop-Akzent (Cards verwenden bereits amber/orange-Verlauf in den
// Stat-Tiles und im Choropleth-Pin-Hervorheber).
const CHOROPLETH_BINS = ['#fffbeb', '#fde68a', '#fbbf24', '#f97316', '#c2410c'];
const CHOROPLETH_NEUTRAL = '#e5e7eb'; // Region ohne Daten

// Bestimmt die Farbe per Quintil-Klassifizierung. Werte == 0 -> neutral grau.
function colorForValue(value: number, breaks: number[]): string {
  if (!Number.isFinite(value) || value <= 0) return CHOROPLETH_NEUTRAL;
  for (let i = 0; i < breaks.length; i += 1) {
    if (value <= breaks[i]) return CHOROPLETH_BINS[i];
  }
  return CHOROPLETH_BINS[CHOROPLETH_BINS.length - 1];
}

// Berechnet 5 Quintil-Schwellen aus den positiven Regionswerten. Wenn weniger
// als 5 unterschiedliche Werte vorliegen, werden die Bin-Grenzen einfach durch
// das Maximum gestaucht — die Farbskala bleibt nutzbar.
function computeQuintileBreaks(values: number[]): number[] {
  const positives = values.filter((v) => Number.isFinite(v) && v > 0).sort((a, b) => a - b);
  if (positives.length === 0) return [0, 0, 0, 0, 0];
  const max = positives[positives.length - 1];
  if (positives.length < 5) {
    return [0.2, 0.4, 0.6, 0.8, 1].map((q) => max * q);
  }
  const breaks: number[] = [];
  for (let i = 1; i <= 5; i += 1) {
    const idx = Math.min(positives.length - 1, Math.ceil((i / 5) * positives.length) - 1);
    breaks.push(positives[idx]);
  }
  return breaks;
}

function formatChoroplethMetric(metric: 'count' | 'value'): string {
  return metric === 'count' ? 'Vorhaben' : 'Volumen';
}

export default function BeneficiaryMap({
  className,
  countryCode = 'DE',
  highlightNames,
  showFilterControls = true,
  choroplethEnabled = false,
  choroplethMetric = 'count',
}: BeneficiaryMapProps) {
  const [data, setData] = useState<Beneficiary[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [regionLabel, setRegionLabel] = useState<string>('Bundesland');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [profile, setProfile] = useState<SystemProfile | null>(null);

  // Filter
  const [filterBl, setFilterBl] = useState('');
  const [minKosten, setMinKosten] = useState(0);

  // Vollbild + Export
  const [fullscreen, setFullscreen] = useState(false);
  const [exporting, setExporting] = useState<'png' | 'pdf' | null>(null);
  const [showSources, setShowSources] = useState(false);
  const mapShellRef = useRef<HTMLDivElement>(null);

  // Choropleth-Layer State. Initialwert kommt aus den Props, wird aber per
  // Toolbar-Button (Layers-Icon) lokal getoggelt.
  const [choroplethActive, setChoroplethActive] = useState(choroplethEnabled);
  // Heatmap-Granularitaet: NUTS-1 (Bundesland) oder NUTS-3 (Kreis).
  // NUTS-3 hat aktuell keine Polygon-GeoJSON — der Fallback zeigt
  // automatisch ein Bar-Chart mit den Top-Kreisen.
  const [choroplethLevel, setChoroplethLevel] = useState<1 | 3>(1);
  const [choroplethData, setChoroplethData] = useState<ChoroplethResponse | null>(null);
  const [choroplethGeo, setChoroplethGeo] = useState<FeatureCollection | null>(null);
  const [choroplethGeoMissing, setChoroplethGeoMissing] = useState(false);
  const [choroplethLoading, setChoroplethLoading] = useState(false);
  const [choroplethError, setChoroplethError] = useState('');

  useEffect(() => {
    setChoroplethActive(choroplethEnabled);
  }, [choroplethEnabled]);

  const countryQuery = countryCode ? `?country_code=${countryCode}` : '';

  // ESC schließt Vollbild
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setFullscreen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fullscreen]);

  const exportApi = useExport();
  const canManageSources = ['moderator', 'admin'].includes(localStorage.getItem('workshop_role') || '');
  const exportMap = useCallback(async (format: 'png' | 'pdf') => {
    const target = mapShellRef.current;
    if (!target) return;
    setExporting(format);
    try {
      const ts = new Date().toISOString().slice(0, 10);
      const fileBase = `beguenstigtenkarte_${countryCode || 'all'}_${ts}`;
      if (format === 'png') {
        await exportApi.toPng(target, { filename: fileBase });
      } else {
        await exportApi.toPdf(target, {
          filename: fileBase,
          title: 'Begünstigtenverzeichnisse',
          subtitle: `${filtered.length} Vorhaben · ${formatEur(totalKosten)} · Stand ${ts}`,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export fehlgeschlagen.');
    } finally {
      setExporting(null);
    }
  // filtered/totalKosten existieren weiter unten — Closure-State bei Aufruf
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countryCode, exportApi]);

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

  // Choropleth-Daten holen (NUTS-1, aktuelles Land + gewählte Metrik). Werte
  // werden auch dann geladen, wenn die GeoJSON-Polygone fehlen — dann zeigt
  // das Inset-Fallback (Top-5 Bar-Chart) trotzdem etwas Sinnvolles.
  useEffect(() => {
    if (!choroplethActive) return;
    if (!countryCode) return;
    let cancelled = false;
    setChoroplethLoading(true);
    setChoroplethError('');

    const headers = { ...getWorkshopAuthHeaders() };
    const valuesUrl = `/api/beneficiaries/choropleth?country_code=${countryCode}&level=${choroplethLevel}&metric=${choroplethMetric}`;
    const geoUrl = `/api/beneficiaries/nuts-geojson?country_code=${countryCode}&level=${choroplethLevel}`;

    Promise.all([
      fetch(valuesUrl, { headers }).then((res) => {
        if (!res.ok) throw new Error(`Werte HTTP ${res.status}`);
        return res.json() as Promise<ChoroplethResponse>;
      }),
      fetch(geoUrl, { headers }).then((res) => {
        // 404 ist erlaubt — Endpoint optional. Fallback: Bar-Chart-Inset.
        if (res.status === 404) return null;
        if (!res.ok) throw new Error(`GeoJSON HTTP ${res.status}`);
        return res.json() as Promise<FeatureCollection>;
      }),
    ])
      .then(([values, geo]) => {
        if (cancelled) return;
        setChoroplethData(values);
        setChoroplethGeo(geo);
        setChoroplethGeoMissing(geo === null);
      })
      .catch((err) => {
        if (cancelled) return;
        setChoroplethError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setChoroplethLoading(false);
      });

    return () => { cancelled = true; };
  }, [choroplethActive, countryCode, choroplethMetric, choroplethLevel]);

  const handleDeleteSource = async (source: string) => {
    if (!confirm('Verzeichnis entfernen?')) return;
    await fetch(`/api/beneficiaries/${encodeURIComponent(source)}`, {
      method: 'DELETE',
      headers: { ...getWorkshopAuthHeaders() },
    });
    await loadMap();
  };

  const bundeslaender = [...new Set(data.map((b) => b.bundesland).filter(Boolean))].sort();
  // Highlight-Filter: case-insensitive Substring/Match auf Beneficiary-Name.
  // Drei Modi je nach highlightNames-Wert:
  //   null/undefined  → kein Filter, alle Marker
  //   []              → "leere Karte" (Tab Unternehmenssuche vor erster Eingabe):
  //                     OSM-Tiles laden, aber keine Marker rendern
  //   ['Foo', ...]    → nur Treffer mit Namens-Match anzeigen
  const highlightActive = Array.isArray(highlightNames) && highlightNames.length > 0;
  const highlightAwaiting = Array.isArray(highlightNames) && highlightNames.length === 0;
  const highlightLower = useMemo(
    () => (highlightActive ? highlightNames!.map((n) => n.toLowerCase()) : []),
    [highlightActive, highlightNames],
  );
  const filtered = useMemo(() => {
    if (highlightAwaiting) return [];
    return data.filter((b) => {
      if (filterBl && b.bundesland !== filterBl) return false;
      if (minKosten > 0 && b.kosten < minKosten) return false;
      if (highlightActive) {
        const name = (b.name || '').toLowerCase();
        const hit = highlightLower.some((q) => name === q || name.includes(q));
        if (!hit) return false;
      }
      return true;
    });
  }, [data, filterBl, minKosten, highlightActive, highlightAwaiting, highlightLower]);
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

  // Lookup nuts_code → Region für schnellen Zugriff im GeoJSON-Renderer.
  const choroplethByCode = useMemo(() => {
    const m = new Map<string, ChoroplethRegion>();
    for (const r of choroplethData?.regions || []) {
      m.set(r.nuts_code, r);
    }
    return m;
  }, [choroplethData]);

  const choroplethBreaks = useMemo(
    () => computeQuintileBreaks((choroplethData?.regions || []).map((r) => r.value)),
    [choroplethData],
  );

  const choroplethTop5 = useMemo(() => {
    return [...(choroplethData?.regions || [])]
      .filter((r) => r.value > 0)
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);
  }, [choroplethData]);

  // Style-Funktion für GeoJSON-Features: Farbe nach Wert, schmaler Rand.
  const choroplethStyle = useCallback((feature?: Feature<Geometry>): PathOptions => {
    const props = (feature?.properties ?? {}) as { nuts_code?: string; NUTS_ID?: string };
    const code = props.nuts_code || props.NUTS_ID || '';
    const region = choroplethByCode.get(code);
    return {
      fillColor: colorForValue(region?.value ?? 0, choroplethBreaks),
      fillOpacity: 0.65,
      color: '#475569',
      weight: 0.8,
      opacity: 0.7,
    };
  }, [choroplethByCode, choroplethBreaks]);

  // Pro Feature einen Tooltip/Popup mit Regionname + Wert binden.
  const choroplethOnEach = useCallback((feature: Feature<Geometry>, layer: Layer) => {
    const props = (feature.properties ?? {}) as { nuts_code?: string; NUTS_ID?: string; name?: string; NAME?: string };
    const code = props.nuts_code || props.NUTS_ID || '';
    const region = choroplethByCode.get(code);
    const fallbackName = props.name || props.NAME || code || 'Region';
    const name = region?.name || fallbackName;
    const valueLabel = region?.value_label ?? '–';
    const html = `<div style="font-size:12px;line-height:1.4">
      <strong>${name}</strong><br/>
      <span style="color:#64748b">${formatChoroplethMetric(choroplethMetric)}: </span>${valueLabel}
    </div>`;
    layer.bindPopup(html);
    layer.bindTooltip(`${name}: ${valueLabel}`, { sticky: true });
  }, [choroplethByCode, choroplethMetric]);

  return (
    <div className={`space-y-4 ${className || ''}`}>
      {/* Fehler */}
      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-2 flex items-center gap-2 text-sm">
          <AlertTriangle size={16} className="text-red-500 shrink-0" />
          <span className="text-red-600 dark:text-red-400">{error}</span>
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600"><X size={14} /></button>
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
              : 'Der automatische Worker hat für diese Auswahl noch keine auswertbaren Verzeichnisse geladen.'}
          </p>
        </div>
      ) : (
        <div className={`rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden ${fullscreen ? 'fixed inset-2 z-[1000] flex flex-col shadow-2xl' : ''}`}>
          {/* Karten-Header */}
          <div className="px-4 py-2.5 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2 text-sm">
              <MapPin size={15} className="text-indigo-500" />
              {highlightAwaiting ? (
                <span className="text-slate-500 dark:text-slate-400">
                  Karte wartet auf Suche — Treffer erscheinen hier nach der Eingabe.
                </span>
              ) : showFilterControls ? (
                <>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    {filtered.length.toLocaleString('de-DE')} Vorhaben
                  </span>
                  <span className="text-slate-400">
                    an {pins.length.toLocaleString('de-DE')} Standort{pins.length === 1 ? '' : 'en'}
                  </span>
                  {totalKosten > 0 && (
                    <span className="text-slate-400">· {formatEur(totalKosten)}</span>
                  )}
                </>
              ) : highlightActive ? (
                <span className="text-slate-700 dark:text-slate-300 font-semibold">
                  {filtered.length.toLocaleString('de-DE')} Treffer auf der Karte
                </span>
              ) : (
                <span className="text-slate-500 dark:text-slate-400">Begünstigtenkarte</span>
              )}
              {showFilterControls && highlightActive && (
                <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                  Filter: {highlightNames!.length === 1 ? highlightNames![0] : `${highlightNames!.length} Treffer`}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {showFilterControls && bundeslaender.length > 1 && (
                <select value={filterBl} onChange={(e) => setFilterBl(e.target.value)}
                  className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700"
                  aria-label={`${regionLabel} filtern`}>
                  <option value="">Alle {regionLabel === 'Bundesland' ? 'Bundesländer' : `${regionLabel}e`}</option>
                  {bundeslaender.map((bl) => <option key={bl} value={bl}>{bl}</option>)}
                </select>
              )}
              {showFilterControls && (
                <select value={minKosten} onChange={(e) => setMinKosten(Number(e.target.value))}
                  className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700"
                  aria-label="Mindestbetrag">
                  <option value={0}>Alle Beträge</option>
                  <option value={100000}>&gt; 100.000 €</option>
                  <option value={500000}>&gt; 500.000 €</option>
                  <option value={1000000}>&gt; 1 Mio €</option>
                  <option value={5000000}>&gt; 5 Mio €</option>
                </select>
              )}
              <button
                onClick={() => setChoroplethActive((v) => !v)}
                className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors ${
                  choroplethActive
                    ? 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                    : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 hover:bg-slate-100 dark:hover:bg-slate-600'
                }`}
                title={choroplethActive ? 'Heatmap (Regionen einfärben) deaktivieren' : 'Heatmap: Regionen nach Vorhabenanzahl einfärben'}
                aria-pressed={choroplethActive}
              >
                <Layers size={12} />
                Heatmap
              </button>
              {choroplethActive && (
                <select
                  value={choroplethLevel}
                  onChange={(e) => setChoroplethLevel(Number(e.target.value) as 1 | 3)}
                  className="text-xs px-2 py-1 rounded border border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                  aria-label="Heatmap-Granularität"
                  title="Bundesland (NUTS-1) oder Kreis (NUTS-3)"
                >
                  <option value={1}>Bundesland</option>
                  <option value={3}>Kreis (NUTS-3)</option>
                </select>
              )}
              <div className="flex items-center gap-1 border-l border-slate-300 dark:border-slate-600 pl-2 ml-1">
                <button
                  onClick={() => exportMap('png')}
                  disabled={!!exporting}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 hover:bg-slate-100 dark:hover:bg-slate-600 disabled:opacity-50"
                  title="Karte als PNG-Bild exportieren"
                >
                  {exporting === 'png' ? <Loader2 size={12} className="animate-spin" /> : <FileImage size={12} />}
                  PNG
                </button>
                <button
                  onClick={() => exportMap('pdf')}
                  disabled={!!exporting}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 hover:bg-slate-100 dark:hover:bg-slate-600 disabled:opacity-50"
                  title="Karte als PDF exportieren"
                >
                  {exporting === 'pdf' ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />}
                  PDF
                </button>
                <button
                  onClick={() => setFullscreen((v) => !v)}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 hover:bg-slate-100 dark:hover:bg-slate-600"
                  title={fullscreen ? 'Vollbild beenden (Esc)' : 'Vollbild öffnen'}
                  aria-label={fullscreen ? 'Vollbild beenden' : 'Vollbild öffnen'}
                >
                  {fullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
                </button>
              </div>
            </div>
          </div>

          <div
            ref={mapShellRef}
            className={`beneficiary-map-shell ${fullscreen ? 'flex-1' : 'h-[820px]'}`}
          >
            <div className="relative h-full w-full">
              <MapContainer key={countryCode || 'all'} center={mapView.center} zoom={mapView.zoom} className="h-full w-full" scrollWheelZoom={true}>
                {allowRemoteTiles && (
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                )}
                {points.length > 0 && <FitBounds points={points} />}
                {choroplethActive && choroplethGeo && (
                  <GeoJSON
                    // Key zwingt React zum Re-Mount, sobald sich Werte/Skala
                    // ändern — sonst übernimmt Leaflet die neuen Styles nicht.
                    key={`choro-${countryCode}-${choroplethMetric}-${choroplethBreaks.join('|')}`}
                    data={choroplethGeo}
                    style={choroplethStyle}
                    onEachFeature={choroplethOnEach}
                  />
                )}
                {/* Pins ausblenden, sobald die Heatmap aktiv ist —
                   die Polygone liefern dort die Aggregation, die Pins
                   wuerden den Choropleth-Layer optisch ueberdecken. */}
                {!choroplethActive && pins.map((pin, i) => {
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
                                  {(() => {
                                    const fondsBl = formatFondsBl(g.vorhaben[0].fonds, g.vorhaben[0].bundesland);
                                    return fondsBl ? ` · ${fondsBl}` : '';
                                  })()}
                                </p>
                                <ul className="space-y-1">
                                  {g.vorhaben.map((v, vi) => {
                                    const period = formatPeriod(v.beginn, v.ende);
                                    const fondsBl = formatFondsBl(v.fonds, v.bundesland);
                                    const showCountry = v.country_name && v.country_name !== pin.country_name;
                                    return (
                                      <li key={vi} className="text-slate-600 dark:text-slate-400">
                                        {v.projekt && (
                                          <span className="block line-clamp-2">{v.projekt}</span>
                                        )}
                                        <span className="text-[10px] text-slate-500 flex flex-wrap gap-x-2">
                                          {v.kosten > 0 && <span>{formatEur(v.kosten)}</span>}
                                          {period && <span>📅 {period}</span>}
                                          {fondsBl && <span>{fondsBl}</span>}
                                          {v.kategorie && <span className="line-clamp-1">{v.kategorie}</span>}
                                          {showCountry && <span>{v.country_name}</span>}
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
              {choroplethActive && choroplethLoading && (
                <div className="pointer-events-none absolute right-3 top-3 z-[500] rounded-md bg-white/90 dark:bg-slate-900/90 px-2 py-1 text-[10px] text-slate-500 shadow inline-flex items-center gap-1">
                  <Loader2 size={11} className="animate-spin" />
                  Heatmap lädt…
                </div>
              )}
              {choroplethActive && choroplethError && !choroplethLoading && (
                <div className="absolute right-3 top-3 z-[500] max-w-[260px] rounded-md bg-red-50 dark:bg-red-950/70 border border-red-200 dark:border-red-800 px-2 py-1 text-[10px] text-red-700 dark:text-red-300 shadow">
                  Heatmap nicht ladbar: {choroplethError}
                </div>
              )}
              {choroplethActive && !choroplethLoading && !choroplethError && choroplethGeoMissing && choroplethData && (
                <div className="absolute right-3 top-3 z-[500] w-[260px] rounded-md bg-white/95 dark:bg-slate-900/95 border border-slate-200 dark:border-slate-700 px-3 py-2 shadow">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400">
                      Top 5 · {formatChoroplethMetric(choroplethMetric)}
                    </span>
                    <Layers size={11} className="text-rose-500" />
                  </div>
                  <p className="text-[10px] text-slate-400 mb-2 leading-tight">
                    NUTS-Polygone nicht verfügbar — Fallback als Bar-Chart.
                  </p>
                  {choroplethTop5.length === 0 ? (
                    <p className="text-[11px] text-slate-500">Keine Daten.</p>
                  ) : (
                    <ul className="space-y-1">
                      {choroplethTop5.map((r) => {
                        const max = choroplethData.max_value || r.value || 1;
                        const width = Math.max(6, Math.round((r.value / max) * 100));
                        return (
                          <li key={r.nuts_code} className="text-[11px]">
                            <div className="flex items-baseline justify-between gap-2">
                              <span className="truncate text-slate-700 dark:text-slate-200">{r.name}</span>
                              <span className="shrink-0 text-slate-500 dark:text-slate-400 tabular-nums">{r.value_label}</span>
                            </div>
                            <div className="mt-0.5 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                              <div className="h-full rounded-full bg-orange-500" style={{ width: `${width}%` }} />
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Sources-Popover (über der Legende) */}
          {sources.length > 0 && showSources && (
            <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 max-h-48 overflow-y-auto">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400">
                  {sources.length} Begünstigtenverzeichnis{sources.length === 1 ? '' : 'se'} geladen
                </span>
                <button onClick={() => setShowSources(false)} className="text-slate-400 hover:text-slate-600">
                  <X size={14} />
                </button>
              </div>
              <div className="flex gap-2 flex-wrap">
                {sources.map((s) => (
                  <div key={s.source} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 group">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: getBlColor(s.bundesland || '') }} />
                    <FileSpreadsheet size={12} className="text-slate-400" />
                    <span className="font-medium text-slate-700 dark:text-slate-300">{s.bundesland || s.source}</span>
                    {s.fonds && <span className="text-slate-400">{s.fonds}</span>}
                    {s.periode && <span className="text-slate-400">{s.periode}</span>}
                    <span className="text-slate-400">·</span>
                    <span className="text-slate-500">{s.count.toLocaleString('de-DE')}/{s.total_rows.toLocaleString('de-DE')}</span>
                    {canManageSources && (
                      <button
                        onClick={() => handleDeleteSource(s.source)}
                        className="text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 ml-0.5"
                        aria-label={`${s.bundesland} entfernen`}
                      >
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Legende */}
          <div className="px-4 py-2 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 flex flex-wrap gap-3 items-center">
            {sources.length > 0 && (
              <button
                onClick={() => setShowSources(!showSources)}
                className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                title="Geladene Begünstigtenverzeichnisse anzeigen"
              >
                <FileSpreadsheet size={12} />
                <span className="font-medium">{sources.length}</span>
                <span className="text-slate-400">{sources.length === 1 ? 'Quelle' : 'Quellen'}</span>
              </button>
            )}
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
