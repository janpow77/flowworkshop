/**
 * StateAidMap — NUTS-aggregierte Karte fuer Beihilfe-Awards.
 *
 * Plan §8: keine Scheingenauigkeit. Wenn nur "Land" verfuegbar ist, wird der
 * Kreis groesser und mit "ungenau (Land)" beschriftet. Tooltip zeigt count,
 * Gesamtbetrag und nuts_label/level.
 *
 * Plan §8.4: Anzeige der Kartenqualitaet (kartierbar / nicht kartierbar / Genauigkeit).
 *
 * Plan §8.3 Modus 2 (Choropleth): Toggle „Kreise" ↔ „Flaechen". Bei „Flaechen"
 * werden NUTS-Polygone (DE NUTS-1 / AT NUTS-2) lazy aus /state_aid/*.geojson
 * geladen und proportional zum Aggregat eingefaerbt.
 *
 * Plan §8.3 Modus 3 (Klick-Filter): Popup-Button „Region als Filter setzen"
 * triggert `onRegionClick` — der Page-Container setzt damit `nuts_code` und
 * springt zum Treffer-Tab.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Popup,
  TileLayer,
  useMap,
} from 'react-leaflet';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type { Layer, PathOptions } from 'leaflet';
import { AlertTriangle, Filter, Loader2, MapPin, Maximize2, Minimize2 } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import {
  getMap,
  type StateAidMapPoint,
  type StateAidMapResponse,
} from '../../lib/stateAidApi';
import { getSystemProfile, type SystemProfile } from '../../lib/api';
import { useExport } from '../../lib/useExport';
import ExportButtons, { type ExportFormat } from '../ui/ExportButtons';

export interface StateAidRegionClickPayload {
  nuts_code: string;
  nuts_label: string;
  nuts_level: number | null;
}

interface Props {
  countryCode: string;
  since?: string;
  until?: string;
  onRegionClick?: (payload: StateAidRegionClickPayload) => void;
}

type Mode = 'count' | 'amount';
type DisplayMode = 'circles' | 'choropleth';
/** Aggregations-Granularitaet — 1=NUTS-1 (Bundesland), 2=NUTS-2 (Bezirk), 3=NUTS-3 (Kreis). */
type AggregateLevel = 1 | 2 | 3;

interface NutsFeatureProperties {
  NUTS_ID: string;
  LEVL_CODE: number;
  CNTR_CODE: string;
  NAME_LATN: string;
  NUTS_NAME: string;
}

type NutsFeature = Feature<Geometry, NutsFeatureProperties>;
type NutsFeatureCollection = FeatureCollection<Geometry, NutsFeatureProperties>;

const COUNTRY_CENTER: Record<string, { center: [number, number]; zoom: number }> = {
  DE: { center: [51.0, 10.5], zoom: 6 },
  AT: { center: [47.6, 13.5], zoom: 7 },
  EU: { center: [50.0, 14.0], zoom: 4 },
};

/** GeoJSON-Quellen je Land. Werden lazy via fetch geladen. */
const GEOJSON_SOURCES: Record<string, { url: string; level: number }> = {
  DE: { url: '/state_aid/de_nuts1.geojson', level: 1 },
  AT: { url: '/state_aid/at_nuts2.geojson', level: 2 },
};

function formatEur(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value);
}

function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(value);
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 7);
      return;
    }
    import('leaflet').then((L) => {
      map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
    });
  }, [points, map]);
  return null;
}

function levelLabel(level: number | null | undefined): string {
  if (level === null || level === undefined) return 'unbekannt';
  if (level === 0) return 'Land';
  if (level === 1) return 'NUTS I';
  if (level === 2) return 'NUTS II';
  if (level === 3) return 'NUTS III';
  return `Level ${level}`;
}

/**
 * Liefert ein menschenlesbares Praefix fuer den Tooltip — z.B. "Bundesland: Bayern",
 * "Bezirk: Oberbayern", "Kreis: Muenchen". Faellt auf das NUTS-Label zurueck.
 */
function regionalPrefix(level: number | null | undefined): string {
  if (level === 1) return 'Bundesland';
  if (level === 2) return 'Bezirk';
  if (level === 3) return 'Kreis';
  if (level === 0) return 'Land';
  return 'Region';
}

function dominantPrecision(byLevel: Record<string, number>): string {
  const entries = Object.entries(byLevel);
  if (entries.length === 0) return 'unbekannt';
  entries.sort((a, b) => b[1] - a[1]);
  return levelLabel(Number(entries[0][0]));
}

/**
 * Prefix-Match: Backend liefert Aggregate auf jeweiliger Quell-Granularitaet
 * (NUTS I/II/III). Polygone in DE liegen auf Level 1, in AT auf Level 2 vor.
 * Punkte deren `nuts_code` mit der Polygon-NUTS_ID startet, werden zugeordnet.
 */
function aggregateForRegion(
  region: NutsFeature,
  points: StateAidMapPoint[],
): { count: number; total_eur: number } {
  const id = region.properties.NUTS_ID;
  let count = 0;
  let total_eur = 0;
  for (const p of points) {
    if (!p.nuts_code) continue;
    if (p.nuts_code === id || p.nuts_code.startsWith(id)) {
      count += p.count;
      if (p.total_eur) total_eur += p.total_eur;
    }
  }
  return { count, total_eur };
}

/**
 * Lineare Interpolation einer Skala {0..max} → Hex-Farbe.
 * Erzeugt eine 5-stufige Emerald-Skala (hell → kraeftig).
 */
const CHOROPLETH_COLORS = ['#dcfce7', '#bbf7d0', '#86efac', '#34d399', '#059669'];
const NO_DATA_COLOR = '#e2e8f0';

function colorForValue(value: number, max: number): string {
  if (max <= 0 || value <= 0) return NO_DATA_COLOR;
  const ratio = Math.min(1, value / max);
  const idx = Math.min(CHOROPLETH_COLORS.length - 1, Math.floor(ratio * CHOROPLETH_COLORS.length));
  return CHOROPLETH_COLORS[idx];
}

export default function StateAidMap({ countryCode, since, until, onRegionClick }: Props) {
  const [data, setData] = useState<StateAidMapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('count');
  const [displayMode, setDisplayMode] = useState<DisplayMode>('circles');
  // Aggregations-Level fuer das Backend (Default: NUTS-1 / Bundesland).
  const [aggregateLevel, setAggregateLevel] = useState<AggregateLevel>(1);
  const [profile, setProfile] = useState<SystemProfile | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [geoData, setGeoData] = useState<NutsFeatureCollection | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const mapShellRef = useRef<HTMLDivElement>(null);
  const exportApi = useExport();

  useEffect(() => {
    getSystemProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Asynchron starten, damit setState nicht synchron im Effect-Body aufgerufen wird
    // (siehe react-hooks/set-state-in-effect Lint-Rule).
    queueMicrotask(() => {
      if (cancelled) return;
      setLoading(true);
      setError(null);
      getMap({
        country_code: countryCode || undefined,
        since,
        until,
        level: aggregateLevel,
      })
        .then((res) => { if (!cancelled) setData(res); })
        .catch((err: unknown) => {
          if (!cancelled) setError(err instanceof Error ? err.message : 'Karte konnte nicht geladen werden.');
        })
        .finally(() => { if (!cancelled) setLoading(false); });
    });
    return () => { cancelled = true; };
  }, [countryCode, since, until, aggregateLevel]);

  // GeoJSON lazy laden, wenn Choropleth-Modus aktiv ist und das Land unterstuetzt wird.
  // Hinweis: Triggern auf `displayMode` (User-Auswahl) reicht — bei NUTS-3 nutzt
  // der Renderer den effektiven Modus und zeigt die Polygone gar nicht erst an.
  useEffect(() => {
    if (displayMode !== 'choropleth') return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      const source = GEOJSON_SOURCES[countryCode];
      if (!source) {
        setGeoData(null);
        setGeoError(null);
        setGeoLoading(false);
        return;
      }
      setGeoLoading(true);
      setGeoError(null);
      fetch(source.url)
        .then((res) => {
          if (!res.ok) throw new Error(`GeoJSON ${res.status}`);
          return res.json() as Promise<NutsFeatureCollection>;
        })
        .then((json) => { if (!cancelled) setGeoData(json); })
        .catch((err: unknown) => {
          if (!cancelled) setGeoError(err instanceof Error ? err.message : 'Karten-Polygone konnten nicht geladen werden.');
        })
        .finally(() => { if (!cancelled) setGeoLoading(false); });
    });
    return () => { cancelled = true; };
  }, [displayMode, countryCode]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setFullscreen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fullscreen]);

  const points = useMemo<StateAidMapPoint[]>(() => data?.points ?? [], [data]);
  const mapView = useMemo(() => {
    if (countryCode && COUNTRY_CENTER[countryCode]) return COUNTRY_CENTER[countryCode];
    if (countryCode === '') return COUNTRY_CENTER.EU;
    return COUNTRY_CENTER.DE;
  }, [countryCode]);

  const allowRemoteTiles = profile?.allow_remote_tiles ?? false;
  // Choropleth-Polygone liegen nur fuer das jeweilige Polygon-Level vor — bei
  // NUTS-3-Aggregation (Kreis) blenden wir den Modus aus und faerben Punkte.
  const choroplethSupported = !!GEOJSON_SOURCES[countryCode] && aggregateLevel !== 3;
  // Effektiver Anzeigemodus: bei nicht unterstuetztem Choropleth-Level faellt
  // die Anzeige zur Laufzeit auf "circles" zurueck — ohne den State zu mutieren
  // (vermeidet kaskadierende Renders, lint-rule react-hooks/set-state-in-effect).
  const effectiveDisplayMode: DisplayMode =
    displayMode === 'choropleth' && !choroplethSupported ? 'circles' : displayMode;

  // Aggregate je Polygon — fuer Skala und Tooltip.
  const regionAggregates = useMemo(() => {
    if (!geoData) return null;
    const map = new Map<string, { count: number; total_eur: number; feature: NutsFeature }>();
    for (const feature of geoData.features) {
      const agg = aggregateForRegion(feature, points);
      map.set(feature.properties.NUTS_ID, { ...agg, feature });
    }
    return map;
  }, [geoData, points]);

  const choroplethMax = useMemo(() => {
    if (!regionAggregates) return 0;
    let max = 0;
    for (const { count, total_eur } of regionAggregates.values()) {
      const v = mode === 'count' ? count : total_eur;
      if (v > max) max = v;
    }
    return max;
  }, [regionAggregates, mode]);

  function radiusFor(point: StateAidMapPoint): number {
    if (mode === 'count') {
      // Anzahl: log-skaliert
      const r = Math.log10(Math.max(point.count, 1)) * 6 + 4;
      return Math.max(5, Math.min(34, r));
    }
    const eur = point.total_eur || 0;
    if (eur <= 0) return 4;
    return Math.max(5, Math.min(38, Math.log10(eur) * 2.6));
  }

  function colorFor(point: StateAidMapPoint): string {
    // Land-Genauigkeit -> grau; NUTS II gruen; NUTS III intensiver gruen
    if (!point.nuts_level || point.nuts_level === 0) return '#94a3b8';
    if (point.nuts_level <= 1) return '#0ea5e9';
    if (point.nuts_level === 2) return '#10b981';
    return '#059669';
  }

  function emitRegionClick(payload: StateAidRegionClickPayload) {
    if (!onRegionClick) return;
    onRegionClick(payload);
  }

  function styleForFeature(feature: NutsFeature | undefined): PathOptions {
    if (!feature || !regionAggregates) {
      return { fillColor: NO_DATA_COLOR, fillOpacity: 0.6, color: '#475569', weight: 1 };
    }
    const agg = regionAggregates.get(feature.properties.NUTS_ID);
    const value = agg ? (mode === 'count' ? agg.count : agg.total_eur) : 0;
    const fillColor = colorForValue(value, choroplethMax);
    return {
      fillColor,
      fillOpacity: value > 0 ? 0.75 : 0.35,
      color: '#475569',
      weight: 1,
    };
  }

  function onEachFeature(feature: NutsFeature, layer: Layer) {
    const props = feature.properties;
    const agg = regionAggregates?.get(props.NUTS_ID);
    const count = agg?.count ?? 0;
    const total = agg?.total_eur ?? 0;
    const label = props.NAME_LATN || props.NUTS_NAME;

    const popupHtml = `
      <div class="text-xs leading-relaxed">
        <div class="text-sm font-semibold text-slate-900">${escapeHtml(regionalPrefix(props.LEVL_CODE))}: ${escapeHtml(label)}</div>
        <div class="mt-0.5 text-slate-500">
          <span class="font-mono">${escapeHtml(props.NUTS_ID)}</span> · ${levelLabel(props.LEVL_CODE)}
        </div>
        <div class="mt-2 grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <div class="text-slate-400">Awards</div>
            <div class="font-semibold text-slate-900">${count.toLocaleString('de-DE')}</div>
          </div>
          <div>
            <div class="text-slate-400">Summe</div>
            <div class="font-semibold text-slate-900">${escapeHtml(formatEur(total))}</div>
          </div>
        </div>
        <button
          type="button"
          data-state-aid-filter
          data-nuts-code="${escapeHtml(props.NUTS_ID)}"
          data-nuts-label="${escapeHtml(label)}"
          data-nuts-level="${props.LEVL_CODE}"
          class="mt-3 inline-flex w-full items-center justify-center gap-1 rounded-md bg-emerald-600 px-2 py-1.5 text-[11px] font-medium text-white hover:bg-emerald-700"
        >Region als Filter setzen</button>
      </div>
    `;

    layer.bindPopup(popupHtml, { maxWidth: 280 });
    layer.on('popupopen', (e: { popup: { getElement: () => HTMLElement | null } }) => {
      const root = e.popup.getElement();
      if (!root) return;
      const btn = root.querySelector<HTMLButtonElement>('button[data-state-aid-filter]');
      if (!btn) return;
      btn.addEventListener(
        'click',
        () => {
          emitRegionClick({
            nuts_code: btn.dataset.nutsCode || props.NUTS_ID,
            nuts_label: btn.dataset.nutsLabel || label,
            nuts_level: btn.dataset.nutsLevel ? Number(btn.dataset.nutsLevel) : props.LEVL_CODE,
          });
        },
        { once: true },
      );
    });
  }

  const fitPoints: [number, number][] = points.map((p) => [p.lat, p.lon]);
  const totalRecords = data?.total_records ?? 0;
  const unmappable = data?.unmappable ?? 0;
  const mapped = totalRecords - unmappable;

  // ── Karten-Export ─────────────────────────────────────────────────────
  // PNG/PDF: html-to-image auf Map-Shell (analog BeneficiaryMap).
  // GeoJSON: aktuelle NUTS-Aggregat-Punkte als FeatureCollection serialisieren.
  const handleMapExport = useCallback(
    async (format: ExportFormat) => {
      const ts = new Date().toISOString().slice(0, 10);
      const fileBase = `state_aid_karte_${countryCode || 'EU'}_${aggregateLevel}_${ts}`;
      if (format === 'png') {
        await exportApi.toPng(mapShellRef.current, { filename: fileBase });
        return;
      }
      if (format === 'pdf') {
        await exportApi.toPdf(mapShellRef.current, {
          filename: fileBase,
          title: 'EU-Beihilfen · Geo-Verteilung',
          subtitle: `${mapped.toLocaleString('de-DE')} kartierbare Awards · NUTS-${aggregateLevel} · Stand ${ts}`,
        });
        return;
      }
      if (format === 'geojson') {
        // FeatureCollection aus den NUTS-Aggregat-Punkten bauen (Plan §13).
        const features = points.map((p) => ({
          type: 'Feature' as const,
          properties: {
            nuts_code: p.nuts_code,
            nuts_label: p.nuts_label,
            nuts_level: p.nuts_level,
            country_code: p.country_code,
            count: p.count,
            total_eur: p.total_eur,
          },
          geometry: {
            type: 'Point' as const,
            coordinates: [p.lon, p.lat],
          },
        }));
        const fc = {
          type: 'FeatureCollection' as const,
          name: `state_aid_karte_${countryCode || 'EU'}`,
          features,
          metadata: {
            generated_at: new Date().toISOString(),
            country_code: countryCode || null,
            aggregate_level: aggregateLevel,
            mode,
            since: since ?? null,
            until: until ?? null,
            total_records: totalRecords,
            mapped,
            unmappable,
            disclaimer:
              'Quelle: EU TAM und nationale Beihilfe-Register (Art. 9 Abs. 1 lit. c) VO (EU) Nr. 651/2014). '
              + 'NUTS-Aggregation, keine Adressdaten. Datenstand abhängig vom letzten Harvest pro Quelle.',
          },
        };
        const blob = new Blob([JSON.stringify(fc, null, 2)], {
          type: 'application/geo+json;charset=utf-8',
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${fileBase}.geojson`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    },
    [aggregateLevel, countryCode, exportApi, mapped, mode, points, since, totalRecords, unmappable, until],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[26px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.95),rgba(241,245,249,0.86))] px-4 py-3 text-sm dark:border-slate-800 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.72),rgba(2,6,23,0.8))]">
        <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600 dark:text-slate-300">
          <div>
            <span className="text-slate-400">Kartierbar:</span>{' '}
            <span className="font-semibold text-emerald-700 dark:text-emerald-300">
              {mapped.toLocaleString('de-DE')}
            </span>
            <span className="text-slate-400"> / {totalRecords.toLocaleString('de-DE')}</span>
          </div>
          <div>
            <span className="text-slate-400">Genauigkeit:</span>{' '}
            <span className="font-medium text-slate-800 dark:text-slate-100">
              {data ? dominantPrecision(data.by_level) : 'unbekannt'}
            </span>
          </div>
          {unmappable > 0 && (
            <div className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
              <AlertTriangle size={11} />
              {unmappable.toLocaleString('de-DE')} nicht kartierbar
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center rounded-full border border-slate-200 bg-white p-0.5 text-xs dark:border-slate-700 dark:bg-slate-900">
            {([
              { lvl: 1 as AggregateLevel, label: 'Bundesland' },
              { lvl: 2 as AggregateLevel, label: 'Bezirk' },
              { lvl: 3 as AggregateLevel, label: 'Kreis' },
            ]).map((opt) => {
              const active = aggregateLevel === opt.lvl;
              return (
                <button
                  key={opt.lvl}
                  type="button"
                  onClick={() => setAggregateLevel(opt.lvl)}
                  className={`rounded-full px-3 py-1 transition ${active ? 'bg-emerald-600 text-white' : 'text-slate-600 dark:text-slate-300'}`}
                  title={`Aggregation auf NUTS-${opt.lvl} (${opt.label})`}
                  aria-pressed={active}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <div className="inline-flex items-center rounded-full border border-slate-200 bg-white p-0.5 text-xs dark:border-slate-700 dark:bg-slate-900">
            <button
              type="button"
              onClick={() => setDisplayMode('circles')}
              className={`rounded-full px-3 py-1 transition ${displayMode === 'circles' ? 'bg-emerald-600 text-white' : 'text-slate-600 dark:text-slate-300'}`}
            >
              Kreise
            </button>
            <button
              type="button"
              onClick={() => setDisplayMode('choropleth')}
              disabled={!choroplethSupported}
              className={`rounded-full px-3 py-1 transition ${
                displayMode === 'choropleth' && choroplethSupported
                  ? 'bg-emerald-600 text-white'
                  : choroplethSupported
                    ? 'text-slate-600 dark:text-slate-300'
                    : 'text-slate-300 dark:text-slate-600 cursor-not-allowed'
              }`}
              title={choroplethSupported ? 'Choropleth-Karte' : aggregateLevel === 3 ? 'Choropleth bei Kreis-Aggregation nicht verfügbar' : 'Choropleth nur für DE/AT verfügbar'}
            >
              Flächen
            </button>
          </div>
          <div className="inline-flex items-center rounded-full border border-slate-200 bg-white p-0.5 text-xs dark:border-slate-700 dark:bg-slate-900">
            <button
              type="button"
              onClick={() => setMode('count')}
              className={`rounded-full px-3 py-1 transition ${mode === 'count' ? 'bg-emerald-600 text-white' : 'text-slate-600 dark:text-slate-300'}`}
            >
              Anzahl
            </button>
            <button
              type="button"
              onClick={() => setMode('amount')}
              className={`rounded-full px-3 py-1 transition ${mode === 'amount' ? 'bg-emerald-600 text-white' : 'text-slate-600 dark:text-slate-300'}`}
            >
              Betrag (EUR)
            </button>
          </div>
          <ExportButtons
            formats={['png', 'pdf', 'geojson']}
            onExport={handleMapExport}
            disabled={loading || totalRecords === 0}
            variant="compact"
          />
          <button
            type="button"
            onClick={() => setFullscreen((v) => !v)}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 transition hover:border-emerald-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            title={fullscreen ? 'Vollbild beenden (Esc)' : 'Vollbild'}
            aria-label="Vollbild umschalten"
          >
            {fullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
        </div>
      </div>

      <div className="rounded-[26px] border border-amber-200/70 bg-amber-50/70 px-4 py-3 text-xs leading-5 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
        <div className="flex items-start gap-2">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            Die Karte aggregiert nach der in der Quelle vorhandenen regionalen Genauigkeit.
            Bei NUTS-Daten werden keine genaueren Standorte abgeleitet. Datensätze ohne
            NUTS-Code werden auf Land-Ebene mit größerem Kreis und dem Hinweis
            <em className="not-italic font-medium"> „ungenau (Land)“</em> markiert.
          </span>
        </div>
      </div>

      <div ref={mapShellRef} className={`overflow-hidden rounded-[26px] border border-slate-200/80 bg-white shadow-[0_18px_60px_-48px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/75 ${fullscreen ? 'fixed inset-2 z-[1000] flex flex-col shadow-2xl' : ''}`}>
        <div className={`relative ${fullscreen ? 'flex-1' : 'h-[640px]'}`}>
          {(loading || (effectiveDisplayMode === 'choropleth' && geoLoading)) && (
            <div className="absolute inset-0 z-[400] flex flex-col items-center justify-center gap-3 bg-white/85 backdrop-blur dark:bg-slate-900/85">
              {/* Karten-Skeleton: Pulse-Banner + Spinner-Hint, Layout bleibt stabil. */}
              <div className="flex items-center gap-2 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                <Loader2 size={16} className="animate-spin" />
                <span>Karte wird aggregiert …</span>
              </div>
              <div className="grid w-full max-w-md grid-cols-3 gap-2 px-6">
                <div className="h-16 animate-pulse rounded-md bg-slate-200/80 dark:bg-slate-800/80" aria-hidden />
                <div className="h-16 animate-pulse rounded-md bg-slate-200/80 dark:bg-slate-800/80 [animation-delay:120ms]" aria-hidden />
                <div className="h-16 animate-pulse rounded-md bg-slate-200/80 dark:bg-slate-800/80 [animation-delay:240ms]" aria-hidden />
              </div>
            </div>
          )}
          {error && (
            <div className="absolute inset-0 z-[400] flex items-center justify-center px-4">
              <div className="max-w-md rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-center text-xs text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-200">
                <AlertTriangle size={18} className="mx-auto mb-1" />
                <div className="font-semibold">Karte konnte nicht geladen werden</div>
                <div className="mt-1 opacity-90">{error}</div>
              </div>
            </div>
          )}
          {!loading && !error && totalRecords === 0 && (
            <div className="absolute inset-0 z-[400] flex items-center justify-center px-6 text-center">
              <div className="max-w-sm rounded-xl border border-slate-200 bg-white/90 px-5 py-5 shadow-md dark:border-slate-700 dark:bg-slate-900/90">
                <MapPin size={26} className="mx-auto mb-2 text-slate-400" />
                <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                  Keine kartierbaren Datensätze für aktuelle Filter
                </div>
                <p className="mt-1.5 text-[11px] leading-5 text-slate-500 dark:text-slate-400">
                  Prüfe, ob ein Land gewählt ist und der Zeitraum Daten enthält.
                  Awards ohne NUTS-Code werden nicht auf der Karte gezeigt.
                </p>
              </div>
            </div>
          )}
          {effectiveDisplayMode === 'choropleth' && geoError && (
            <div className="absolute left-3 top-3 z-[500] rounded-md bg-rose-50 px-3 py-1.5 text-[11px] text-rose-700 shadow dark:bg-rose-950/40 dark:text-rose-200">
              {geoError}
            </div>
          )}
          <MapContainer
            key={`${countryCode || 'EU'}-${effectiveDisplayMode}-${mode}-${aggregateLevel}`}
            center={mapView.center}
            zoom={mapView.zoom}
            className="h-full w-full"
            scrollWheelZoom
          >
            {allowRemoteTiles && (
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
            )}
            {effectiveDisplayMode === 'circles' && fitPoints.length > 0 && <FitBounds points={fitPoints} />}

            {effectiveDisplayMode === 'choropleth' && geoData && (
              <GeoJSON
                key={`${countryCode}-${mode}-${choroplethMax}`}
                data={geoData}
                style={(feature) => styleForFeature(feature as NutsFeature | undefined)}
                onEachFeature={(feature, layer) => onEachFeature(feature as NutsFeature, layer)}
              />
            )}

            {effectiveDisplayMode === 'circles' && points.map((p, idx) => {
              const r = radiusFor(p);
              const c = colorFor(p);
              return (
                <CircleMarker
                  key={`${p.nuts_code}-${idx}`}
                  center={[p.lat, p.lon]}
                  radius={r}
                  pathOptions={{ color: c, fillColor: c, fillOpacity: 0.55, weight: 1.2 }}
                >
                  <Popup maxWidth={320}>
                    <div className="text-xs leading-relaxed">
                      <div className="text-sm font-semibold text-slate-900">
                        {regionalPrefix(p.nuts_level)}: {p.nuts_label || p.nuts_code}
                      </div>
                      <div className="mt-0.5 text-slate-500">
                        <span className="font-mono">{p.nuts_code}</span>
                        {p.country_code ? ` · ${p.country_code}` : ''}
                        {' · '}
                        {levelLabel(p.nuts_level)}
                      </div>
                      {(!p.nuts_level || p.nuts_level === 0) && (
                        <div className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                          ungenau (Land)
                        </div>
                      )}
                      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                        <div>
                          <div className="text-slate-400">Awards</div>
                          <div className="font-semibold text-slate-900">{p.count.toLocaleString('de-DE')}</div>
                        </div>
                        <div>
                          <div className="text-slate-400">Summe</div>
                          <div className="font-semibold text-slate-900">{formatEur(p.total_eur)}</div>
                        </div>
                      </div>
                      {onRegionClick && p.nuts_code && (
                        <button
                          type="button"
                          onClick={() => emitRegionClick({
                            nuts_code: p.nuts_code,
                            nuts_label: p.nuts_label || p.nuts_code,
                            nuts_level: p.nuts_level,
                          })}
                          className="mt-3 inline-flex w-full items-center justify-center gap-1 rounded-md bg-emerald-600 px-2 py-1.5 text-[11px] font-medium text-white hover:bg-emerald-700"
                        >
                          <Filter size={11} /> Region als Filter setzen
                        </button>
                      )}
                    </div>
                  </Popup>
                </CircleMarker>
              );
            })}
          </MapContainer>
          {!allowRemoteTiles && (
            <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-md bg-white/90 px-2 py-1 text-[10px] text-slate-500 shadow dark:bg-slate-900/90 dark:text-slate-300">
              Kartenkacheln lokal deaktiviert
            </div>
          )}

          {effectiveDisplayMode === 'choropleth' && choroplethMax > 0 && (
            <div className="pointer-events-none absolute bottom-3 left-3 z-[500] rounded-lg bg-white/95 px-3 py-2 text-[10px] text-slate-700 shadow dark:bg-slate-900/95 dark:text-slate-200">
              <div className="mb-1 font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {mode === 'count' ? 'Awards je Region' : 'Summe (EUR)'}
              </div>
              <div className="flex items-center gap-1">
                {CHOROPLETH_COLORS.map((c) => (
                  <span key={c} className="inline-block h-3 w-6 border border-slate-200 dark:border-slate-700" style={{ backgroundColor: c }} />
                ))}
              </div>
              <div className="mt-0.5 flex items-center justify-between gap-3 font-mono">
                <span>0</span>
                <span>{mode === 'count' ? choroplethMax.toLocaleString('de-DE') : formatAmount(choroplethMax)}</span>
              </div>
            </div>
          )}
        </div>

        {effectiveDisplayMode === 'circles' ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#94a3b8]" /> Land
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#0ea5e9]" /> NUTS I
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#10b981]" /> NUTS II
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#059669]" /> NUTS III
              </span>
            </div>
            <span>
              {mode === 'count' ? 'Kreisgröße = Anzahl Awards (log)' : 'Kreisgröße = Gesamtbetrag in EUR (log)'}
            </span>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
            <span>
              Polygone: {countryCode === 'DE' ? 'DE NUTS-1 (16 Bundesländer)' : countryCode === 'AT' ? 'AT NUTS-2 (9 Bundesländer)' : 'nicht verfügbar'}
              {' · '}
              Quelle GISCO Eurostat (Public Domain)
            </span>
            <span>
              {mode === 'count' ? 'Färbung = Anzahl Awards' : 'Färbung = Gesamtbetrag in EUR'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/** Minimal HTML-Escape — Popup-Inhalt wird via Leaflet als HTML-String injiziert. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
