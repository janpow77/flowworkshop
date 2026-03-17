/**
 * LLM Inference Pipeline – animierte Übersicht mit Live-GPU/System-Stats.
 *
 * PDF → OCR → Parser & Chunker → ASUS NUC 15 → 2 GPUs → LLM-Antwort (Streaming)
 *
 * Konfiguration:
 *   - Props: statsUrl (überschreibt alles)
 *   - Env:   VITE_GPU_STATS_URL (z.B. http://192.168.1.50:8765)
 *   - Fallback: http://localhost:8765
 *
 * Wiederverwendbar in allen Projekten – einfach importieren:
 *   import PipelineWidget from '@/components/charts/PipelineWidget';
 *   <PipelineWidget statsUrl="http://nuc:8765" />
 */
import { useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_STATS_URL = '/api/system';
const POLL_MS = 3000;

function resolveStatsUrl(propUrl?: string): string {
  if (propUrl) return propUrl.replace(/\/+$/, '');
  const envUrl = import.meta.env.VITE_GPU_STATS_URL;
  if (envUrl) return String(envUrl).replace(/\/+$/, '');
  return DEFAULT_STATS_URL;
}

/* ── Types (exported for reuse) ── */
export interface GpuInfo {
  index: number;
  name: string;
  utilization: number;
  power_draw: number;
  temperature: number;
  mem_used: number;
  mem_total: number;
}
export interface GpuResponse { ok: boolean; gpus: GpuInfo[] }
export interface OllamaModel {
  name: string;
  size_gb: number;
  vram_gb: number;
  expires_at: string;
}
export interface SystemResponse {
  ok: boolean;
  cpu: { percent: number; cores: number };
  host_ram: { used_gb: number; total_gb: number; free_gb: number };
  container_ram: { used_gb: number; limit_gb: number; host: boolean };
  ollama: { worker_count: number; total_rss_gb: number; workers: { pid: number; rss_gb: number }[]; models: OllamaModel[] };
  network: { recv_mb: number; sent_mb: number };
}

export interface PipelineWidgetProps {
  /** URL des gpu_stats_server.py (z.B. http://192.168.1.50:8765) */
  statsUrl?: string;
  /** Polling-Intervall in ms (default: 3000) */
  pollInterval?: number;
}

const STYLE_ID = 'pw-kf';
const CSS = `
/* ── Pipeline Widget Scoped Styles ── */
.pw{--nv:#76b900;--nv-glow:rgba(118,185,0,.35);--nv-dim:rgba(118,185,0,.15);--tb:#00b0f0;--tb-glow:rgba(0,176,240,.3);--amber:#f59e0b;--amber-glow:rgba(245,158,11,.3);--pw-card:rgba(255,255,255,.03);--pw-deep:rgba(255,255,255,.02);--pw-border:rgba(255,255,255,.08);--pw-text:#e8e7e0;--pw-muted:#9c9a92;font-family:'Sora',system-ui,sans-serif;color:var(--pw-text)}
@media(prefers-color-scheme:light){
  .pw{--pw-card:#f5f4f0;--pw-deep:#ebebE6;--pw-border:#c8c7c0;--pw-text:#1a1a18;--pw-muted:#6b6b66}
}
.dark .pw{--pw-card:rgba(255,255,255,.03);--pw-deep:rgba(255,255,255,.02);--pw-border:rgba(255,255,255,.08);--pw-text:#e8e7e0;--pw-muted:#9c9a92}
:not(.dark) .pw{--pw-card:#f5f4f0;--pw-deep:#ebebE6;--pw-border:#c8c7c0;--pw-text:#1a1a18;--pw-muted:#6b6b66}

.pw-title{text-align:center;font-size:13px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--pw-muted);margin-bottom:20px}
.pw-pipeline{display:flex;align-items:center;gap:0;position:relative;justify-content:center;flex-wrap:nowrap;overflow-x:auto;padding:8px}

/* stage */
.pw-stage{display:flex;flex-direction:column;align-items:center;gap:6px;flex-shrink:0}
.pw-stage-box{background:var(--pw-card);border:.5px solid var(--pw-border);border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;align-items:center;gap:5px;min-width:76px;position:relative;transition:border-color .3s}
.pw-stage-box:hover{border-color:#888}
.pw-stage-icon{font-size:22px;line-height:1}
.pw-stage-label{font-size:10px;font-weight:600;text-align:center;color:var(--pw-muted);letter-spacing:.04em;max-width:72px;line-height:1.3}
.pw-stage-sub{font-size:9px;color:var(--pw-muted);font-family:'JetBrains Mono',monospace}

/* connectors */
.pw-conn{display:flex;align-items:center;flex-shrink:0;position:relative;width:28px}
.pw-conn-line{width:100%;height:1.5px;background:var(--pw-border);position:relative;overflow:visible}
.pw-conn-dot{width:5px;height:5px;border-radius:50%;background:var(--tb);position:absolute;top:50%;transform:translateY(-50%);animation:pw-flow 2s linear infinite;opacity:0}
.pw-conn-dot:nth-child(1){animation-delay:0s}
.pw-conn-dot:nth-child(2){animation-delay:.7s}
.pw-conn-dot:nth-child(3){animation-delay:1.4s}
@keyframes pw-flow{0%{left:-6px;opacity:0}10%{opacity:1}90%{opacity:1}100%{left:calc(100% + 6px);opacity:0}}

/* NUC */
.pw-nuc{background:var(--pw-card);border:.5px solid rgba(245,158,11,.4);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;align-items:center;gap:6px;position:relative}
.pw-nuc-chip{width:44px;height:44px;border-radius:8px;border:1.5px solid var(--amber);display:flex;align-items:center;justify-content:center;position:relative;background:var(--pw-deep)}
.pw-nuc-chip::before{content:'';position:absolute;inset:-4px;border-radius:11px;border:.5px dashed rgba(245,158,11,.3)}
.pw-nuc-badge{font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:600;color:var(--amber);letter-spacing:.06em}
.pw-nuc-label{font-size:10px;font-weight:600;color:var(--pw-muted);letter-spacing:.04em}
.pw-nuc-led{width:5px;height:5px;border-radius:50%;background:var(--amber);animation:pw-blink-amber 2s ease-in-out infinite;box-shadow:0 0 4px var(--amber-glow)}
@keyframes pw-blink-amber{0%,100%{opacity:1}50%{opacity:.3}}
.pw-nuc-stats{font-size:8px;color:var(--pw-muted);font-family:'JetBrains Mono',monospace;text-align:center;line-height:1.5}

/* GPU section */
.pw-gpu-section{display:flex;flex-direction:column;gap:10px;align-items:flex-start}
.pw-gpu-card{background:var(--pw-card);border-radius:10px;padding:10px 12px;display:flex;align-items:center;gap:10px;min-width:200px;position:relative;border:.5px solid rgba(118,185,0,.5);transition:border-color .3s}
.pw-gpu-card:hover{border-color:var(--nv)}
.pw-gpu-card.pw-egpu{border-color:rgba(0,176,240,.3)}

/* GPU PCB */
.pw-gpu-pcb{width:52px;height:36px;border-radius:4px;background:var(--pw-deep);border:1px solid rgba(118,185,0,.3);position:relative;flex-shrink:0;overflow:hidden}
.pw-gpu-pcb::after{content:'';position:absolute;bottom:0;left:0;right:0;height:6px;background:rgba(118,185,0,.15);border-top:.5px solid rgba(118,185,0,.3)}
.pw-gpu-pcb-bar{position:absolute;bottom:8px;left:50%;transform:translateX(-50%);width:24px;height:3px;border-radius:1px;background:rgba(118,185,0,.4)}

/* fans */
.pw-fan{width:14px;height:14px;border-radius:50%;border:1.5px solid rgba(118,185,0,.5);position:absolute;top:5px;animation:pw-spin 2s linear infinite}
.pw-fan::before{content:'';position:absolute;inset:2px;border-radius:50%;border-top:1.5px solid var(--nv);border-bottom:1.5px solid transparent;border-left:1.5px solid transparent;border-right:1.5px solid transparent}
.pw-fan-l{left:5px}
.pw-fan-r{right:5px;animation-direction:reverse}
@keyframes pw-spin{to{transform:rotate(360deg)}}

/* GPU info */
.pw-gpu-brand{font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:600;color:var(--nv);letter-spacing:.1em;text-transform:uppercase}
.pw-gpu-model{font-size:11px;font-weight:700;color:var(--pw-text);line-height:1.2;margin:2px 0}
.pw-gpu-spec{font-size:9px;color:var(--pw-muted)}
.pw-gpu-status{display:flex;align-items:center;gap:4px;margin-top:4px}
.pw-gpu-led{width:6px;height:6px;border-radius:50%;background:var(--nv);flex-shrink:0}
.pw-gpu-led.pw-fast{animation:pw-blink-nv .6s ease-in-out infinite;box-shadow:0 0 6px var(--nv-glow)}
.pw-gpu-led.pw-slow{animation:pw-blink-nv 1.4s ease-in-out infinite;box-shadow:0 0 6px var(--nv-glow)}
.pw-gpu-led.pw-off{background:#666;animation:none;box-shadow:none}
@keyframes pw-blink-nv{0%,100%{opacity:1;box-shadow:0 0 8px var(--nv-glow)}50%{opacity:.2;box-shadow:none}}
.pw-gpu-status-text{font-size:9px;color:var(--nv);font-family:'JetBrains Mono',monospace;letter-spacing:.04em}
.pw-gpu-status-text.pw-idle{color:var(--pw-muted)}

/* VRAM */
.pw-vram-bar{width:100%;height:3px;background:var(--pw-deep);border-radius:2px;margin-top:3px;overflow:hidden}
.pw-vram-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--nv),rgba(118,185,0,.5));transition:width .8s ease}
.pw-vram-fill.pw-animated{animation:pw-vram-pulse 3s ease-in-out infinite}
@keyframes pw-vram-pulse{0%,100%{width:45%}50%{width:72%}}
.pw-vram-fill.pw-big.pw-animated{animation:pw-vram-pulse-big 2.8s ease-in-out infinite}
@keyframes pw-vram-pulse-big{0%,100%{width:55%}50%{width:88%}}
.pw-vram-label{font-size:8px;color:var(--pw-muted);font-family:'JetBrains Mono',monospace;margin-top:1px}

/* eGPU badge */
.pw-egpu-badge{font-size:8px;font-weight:600;background:rgba(0,176,240,.12);color:var(--tb);border:.5px solid rgba(0,176,240,.35);border-radius:4px;padding:1px 5px;letter-spacing:.06em;white-space:nowrap}

/* Thunderbolt connector */
.pw-tb-conn{display:flex;align-items:center;gap:3px;padding:2px 0}
.pw-tb-line{width:10px;height:1.5px;background:linear-gradient(90deg,var(--pw-border),var(--tb));position:relative;overflow:visible}
.pw-tb-dot{width:4px;height:4px;border-radius:50%;background:var(--tb);position:absolute;top:50%;transform:translateY(-50%);animation:pw-tb-flow 1.2s linear infinite;opacity:0}
.pw-tb-dot:nth-child(1){animation-delay:0s}
.pw-tb-dot:nth-child(2){animation-delay:.6s}
@keyframes pw-tb-flow{0%{left:-4px;opacity:0}15%{opacity:.9}85%{opacity:.9}100%{left:calc(100% + 4px);opacity:0}}

/* Output */
.pw-output{background:var(--pw-card);border:.5px solid rgba(0,176,240,.3);border-radius:10px;padding:10px 14px;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:80px}
.pw-stream{width:60px;height:28px;position:relative;overflow:hidden;border-radius:4px}
.pw-stream-line{position:absolute;height:1.5px;border-radius:1px;background:var(--tb);left:0;animation:pw-stream-anim 1.8s linear infinite;opacity:.7}
.pw-stream-line:nth-child(1){top:5px;width:80%;animation-delay:0s}
.pw-stream-line:nth-child(2){top:11px;width:60%;animation-delay:.3s}
.pw-stream-line:nth-child(3){top:17px;width:90%;animation-delay:.6s}
.pw-stream-line:nth-child(4){top:23px;width:50%;animation-delay:.9s}
@keyframes pw-stream-anim{0%{opacity:0;transform:translateX(-100%)}10%{opacity:.7}90%{opacity:.7}100%{opacity:0;transform:translateX(120%)}}

/* Legend */
.pw-legend{display:flex;align-items:center;gap:20px;justify-content:center;margin-top:16px;flex-wrap:wrap}
.pw-legend-item{display:flex;align-items:center;gap:5px;font-size:10px;color:var(--pw-muted)}
.pw-legend-dot{width:6px;height:6px;border-radius:50%}

/* live badge */
.pw-live-badge{display:inline-flex;align-items:center;gap:4px;font-size:8px;font-weight:600;padding:1px 6px;border-radius:4px;letter-spacing:.06em;font-family:'JetBrains Mono',monospace}
.pw-live-badge.pw-online{color:#22c55e;background:rgba(34,197,94,.1);border:.5px solid rgba(34,197,94,.3)}
.pw-live-badge.pw-offline{color:var(--pw-muted);background:rgba(156,154,146,.08);border:.5px solid rgba(156,154,146,.2)}
.pw-live-badge.pw-error{color:#ef4444;background:rgba(239,68,68,.08);border:.5px solid rgba(239,68,68,.25)}
.pw-live-dot{width:5px;height:5px;border-radius:50%}
.pw-live-dot.pw-on{background:#22c55e;animation:pw-blink-live 1.5s ease-in-out infinite}
.pw-live-dot.pw-off{background:#666}
.pw-live-dot.pw-err{background:#ef4444}
@keyframes pw-blink-live{0%,100%{opacity:1}50%{opacity:.4}}

/* system stats table */
.pw-sys-table{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;font-size:8px;font-family:'JetBrains Mono',monospace;color:var(--pw-muted);margin-top:10px;padding:8px 10px;background:var(--pw-deep);border-radius:6px;border:.5px solid var(--pw-border)}
.pw-sys-key{font-weight:600;color:var(--pw-text);white-space:nowrap}
.pw-sys-val{white-space:nowrap}
`;

function injectStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const el = document.createElement('style');
  el.id = STYLE_ID;
  el.textContent = CSS;
  document.head.appendChild(el);
}

/* ── tiny helpers ── */
function Conn() {
  return (
    <div className="pw-conn">
      <div className="pw-conn-line">
        <div className="pw-conn-dot" />
        <div className="pw-conn-dot" />
      </div>
    </div>
  );
}

function GpuPcb({ tbBorder }: { tbBorder?: boolean }) {
  return (
    <div className="pw-gpu-pcb" style={tbBorder ? { borderColor: 'rgba(0,176,240,.35)' } : undefined}>
      <div className="pw-fan pw-fan-l" />
      <div className="pw-fan pw-fan-r" />
      <div className="pw-gpu-pcb-bar" />
    </div>
  );
}

function formatMb(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`;
}

/* ── System Stats Panel ── */
function SystemStatsPanel({ sys, gpus }: { sys: SystemResponse; gpus: GpuInfo[] | null }) {
  const rows: [string, string][] = [];

  // Ollama Workers
  if (sys.ollama.worker_count > 0) {
    const pids = sys.ollama.workers.map((w) => w.pid).join(', ');
    rows.push(['Worker', `${sys.ollama.worker_count} Prozesse (PID ${pids})`]);
  }

  // CPU
  rows.push(['CPU', `${sys.cpu.percent}% (${sys.cpu.cores} Cores)`]);

  // Container RAM (nur wenn nicht Host-Fallback)
  if (!sys.container_ram.host && sys.container_ram.limit_gb > 0) {
    rows.push(['Container RAM', `${sys.container_ram.used_gb} / ${sys.container_ram.limit_gb} GB`]);
  }

  // Per-Worker RSS
  if (sys.ollama.worker_count > 0) {
    const avgRss = sys.ollama.total_rss_gb / sys.ollama.worker_count;
    rows.push(['Pro Worker', `~${avgRss.toFixed(1)} GB RSS`]);
  }

  // Host RAM
  rows.push(['Host RAM', `${sys.host_ram.used_gb} / ${sys.host_ram.total_gb} GB (${sys.host_ram.free_gb} GB frei)`]);

  // GPU VRAM (aggregiert)
  if (gpus && gpus.length > 0) {
    const totalUsed = gpus.reduce((s, g) => s + g.mem_used, 0);
    const totalMax = gpus.reduce((s, g) => s + g.mem_total, 0);
    rows.push(['GPU VRAM', `${(totalUsed / 1024).toFixed(1)} / ${(totalMax / 1024).toFixed(0)} GB`]);
  }

  // Aktive LLM-Modelle
  if (sys.ollama.models && sys.ollama.models.length > 0) {
    const modelNames = sys.ollama.models.map((m) => {
      const vram = m.vram_gb > 0 ? ` (${m.vram_gb} GB VRAM)` : '';
      return `${m.name}${vram}`;
    }).join(', ');
    rows.push(['LLM-Modell', modelNames]);
  }

  // Netzwerk
  rows.push(['Netzwerk', `${formatMb(sys.network.recv_mb)} in / ${formatMb(sys.network.sent_mb)} out`]);

  return (
    <div className="pw-sys-table" role="table" aria-label="System-Metriken">
      {rows.map(([key, val]) => (
        <div key={key} style={{ display: 'contents' }} role="row">
          <div className="pw-sys-key" role="rowheader">{key}</div>
          <div className="pw-sys-val" role="cell">{val}</div>
        </div>
      ))}
    </div>
  );
}

/* ── GPU card with live data ── */
function GpuCard({
  gpu,
  label,
  spec,
  workload,
  isEgpu,
  fastLed,
}: {
  gpu: GpuInfo | null;
  label: string;
  spec: string;
  workload: string;
  isEgpu?: boolean;
  fastLed?: boolean;
}) {
  const hasData = gpu !== null;
  const utilPct = hasData ? gpu.utilization : 0;
  const memPct = hasData && gpu.mem_total > 0 ? (gpu.mem_used / gpu.mem_total) * 100 : 0;
  const isActive = hasData && utilPct > 2;
  const memLabel = hasData
    ? `VRAM ${(gpu.mem_used / 1024).toFixed(1)} / ${(gpu.mem_total / 1024).toFixed(0)} GB`
    : `VRAM · ${workload}`;
  const statusText = hasData
    ? `${isActive ? 'AKTIV' : 'BEREIT'} · ${utilPct.toFixed(0)}% · ${gpu.temperature}°C · ${gpu.power_draw.toFixed(0)}W`
    : `AKTIV · ${workload}`;

  return (
    <div className={`pw-gpu-card${isEgpu ? ' pw-egpu' : ''}`}>
      {isEgpu ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, flexShrink: 0 }}>
          <div className="pw-tb-conn">
            <div style={{ fontSize: 9, color: 'var(--tb)', fontWeight: 600, fontFamily: "'JetBrains Mono',monospace", writingMode: 'vertical-rl' as const, transform: 'rotate(180deg)', letterSpacing: '.08em' }}>
              TB4
            </div>
            <div className="pw-tb-line">
              <div className="pw-tb-dot" />
              <div className="pw-tb-dot" />
            </div>
          </div>
          <GpuPcb tbBorder />
        </div>
      ) : (
        <GpuPcb />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: isEgpu ? 1 : 0 }}>
          <div className="pw-gpu-brand">NVIDIA GeForce</div>
          {isEgpu && <div className="pw-egpu-badge">eGPU</div>}
        </div>
        <div className="pw-gpu-model">{label}</div>
        <div className="pw-gpu-spec">{spec}</div>
        <div className="pw-vram-bar">
          <div
            className={`pw-vram-fill${isEgpu ? ' pw-big' : ''}${!hasData ? ' pw-animated' : ''}`}
            style={hasData ? { width: `${memPct}%` } : undefined}
          />
        </div>
        <div className="pw-vram-label">{memLabel}</div>
        <div className="pw-gpu-status">
          <div className={`pw-gpu-led ${!hasData ? (fastLed ? 'pw-fast' : 'pw-slow') : isActive ? 'pw-fast' : 'pw-off'}`} />
          <div className={`pw-gpu-status-text${!isActive && hasData ? ' pw-idle' : ''}`}>{statusText}</div>
        </div>
      </div>
    </div>
  );
}

/* ── main ── */
export default function PipelineWidget({ statsUrl, pollInterval = POLL_MS }: PipelineWidgetProps) {
  const [open, setOpen] = useState(false);
  const [gpus, setGpus] = useState<GpuInfo[] | null>(null);
  const [sys, setSys] = useState<SystemResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const baseUrl = useRef(resolveStatsUrl(statsUrl));

  // Update baseUrl when prop changes
  useEffect(() => {
    baseUrl.current = resolveStatsUrl(statsUrl);
  }, [statsUrl]);

  useEffect(injectStyles, []);

  const fetchStats = useCallback(async () => {
    const url = baseUrl.current;
    try {
      const [gRes, sRes] = await Promise.all([
        fetch(`${url}/gpu`, { signal: AbortSignal.timeout(5000) }).then((r) => r.json() as Promise<GpuResponse>),
        fetch(`${url}/info`, { signal: AbortSignal.timeout(5000) }).then((r) => r.json() as Promise<SystemResponse>),
      ]);
      if (gRes.ok) setGpus(gRes.gpus);
      if (sRes.ok) setSys(sRes);
      setLive(true);
      setError(null);
    } catch (err) {
      setLive(false);
      setError(
        err instanceof TypeError
          ? `Stats-Server nicht erreichbar (${url})`
          : `Verbindungsfehler: ${err instanceof Error ? err.message : 'unbekannt'}`
      );
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    fetchStats();
    timerRef.current = setInterval(fetchStats, pollInterval);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [open, fetchStats, pollInterval]);

  // Match GPUs to slots: gpu0 = internal (5060 Ti), gpu1 = eGPU (5070 Ti)
  const gpu0 = gpus?.find((g) => g.index === 0) ?? null;
  const gpu1 = gpus?.find((g) => g.index === 1) ?? null;

  const cpuLabel = sys
    ? `CPU ${sys.cpu.percent}% · ${sys.cpu.cores} Cores`
    : 'Core Ultra · 64 GB RAM';
  const ramLabel = sys
    ? `RAM ${sys.host_ram.used_gb} / ${sys.host_ram.total_gb} GB`
    : '';

  const badgeClass = live ? 'pw-online' : error ? 'pw-error' : 'pw-offline';
  const dotClass = live ? 'pw-on' : error ? 'pw-err' : 'pw-off';
  const badgeText = live ? 'LIVE' : error ? 'OFFLINE' : 'STATIC';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border overflow-hidden">
      {/* Toggle header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-6 py-4 text-left"
        aria-expanded={open}
        aria-label="KI-Pipeline anzeigen"
      >
        <div className="flex items-center gap-2">
          <span className="text-lg" aria-hidden="true">&#x1F9E0;</span>
          <span className="text-sm font-bold text-gray-900 dark:text-white">KI-Pipeline</span>
          <span className="text-[10px] text-gray-400 dark:text-gray-500" style={{ fontFamily: 'monospace' }}>
            Lokale Verarbeitung · DSGVO-konform
          </span>
          {open && (
            <span className={`pw-live-badge ${badgeClass}`} title={error ?? undefined}>
              <span className={`pw-live-dot ${dotClass}`} />
              {badgeText}
            </span>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {open && (
        <div className="pw px-4 pb-5">
          {/* Connection error hint */}
          {error && !live && (
            <div className="text-center text-[10px] text-red-400 mb-3" style={{ fontFamily: "'JetBrains Mono',monospace" }}>
              {error}
            </div>
          )}

          <div className="pw-pipeline">

            {/* PDF */}
            <div className="pw-stage">
              <div className="pw-stage-box">
                <div className="pw-stage-icon">&#x1F4C4;</div>
                <div className="pw-stage-label">PDF-Dokument</div>
              </div>
              <div className="pw-stage-sub">Preisblatt</div>
            </div>

            <Conn />

            {/* OCR */}
            <div className="pw-stage">
              <div className="pw-stage-box" style={{ borderColor: 'rgba(0,176,240,.3)' }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <rect x="3" y="3" width="7" height="7" rx="1" stroke="#00b0f0" strokeWidth="1.5" />
                  <rect x="14" y="3" width="7" height="7" rx="1" stroke="#00b0f0" strokeWidth="1.5" />
                  <rect x="3" y="14" width="7" height="7" rx="1" stroke="#00b0f0" strokeWidth="1.5" />
                  <rect x="14" y="14" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 1" opacity={0.3} />
                </svg>
                <div className="pw-stage-label">OCR</div>
              </div>
              <div className="pw-stage-sub">Texterkennung</div>
            </div>

            <Conn />

            {/* Parser */}
            <div className="pw-stage">
              <div className="pw-stage-box">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M4 6h16M4 10h12M4 14h8M4 18h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity={0.4} />
                  <circle cx="19" cy="17" r="3" stroke="#00b0f0" strokeWidth="1.5" />
                  <path d="M21.5 19.5l-1.5-1.5" stroke="#00b0f0" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <div className="pw-stage-label">Parser &amp; Chunker</div>
              </div>
              <div className="pw-stage-sub">Tokenisierung</div>
            </div>

            <Conn />

            {/* NUC */}
            <div className="pw-stage">
              <div className="pw-nuc">
                <div className="pw-nuc-chip">
                  <div className="pw-nuc-badge">NUC</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div className="pw-nuc-led" />
                  <div className="pw-nuc-label">ASUS NUC 15</div>
                </div>
                <div className="pw-nuc-stats">
                  {cpuLabel}
                  {ramLabel && <><br />{ramLabel}</>}
                  {sys && sys.ollama.worker_count > 0 && (
                    <><br />Ollama: {sys.ollama.worker_count} Worker · {sys.ollama.total_rss_gb} GB</>
                  )}
                  {sys && sys.ollama.models && sys.ollama.models.length > 0 && (
                    <><br />{sys.ollama.models.map((m) => m.name).join(', ')}</>
                  )}
                </div>
              </div>
            </div>

            {/* Split branches */}
            <div style={{ display: 'flex', alignItems: 'center', height: 120, position: 'relative', width: 40, flexShrink: 0 }}>
              <div style={{ position: 'absolute', left: 0, top: '50%', width: 12, height: 1.5, background: 'var(--pw-border)', transform: 'translateY(-50%)' }} />
              <div style={{ position: 'absolute', left: 12, top: 19, width: 1.5, height: 'calc(50% - 19px + 1px)', background: 'var(--pw-border)' }} />
              <div style={{ position: 'absolute', left: 12, top: 19, right: 0, height: 1.5, background: 'var(--pw-border)' }} />
              <div style={{ position: 'absolute', left: 12, bottom: 19, width: 1.5, height: 'calc(50% - 19px + 1px)', background: 'var(--pw-border)' }} />
              <div style={{ position: 'absolute', left: 12, bottom: 19, right: 0, height: 1.5, background: 'var(--pw-border)' }} />
            </div>

            {/* GPU column */}
            <div className="pw-gpu-section">
              <GpuCard
                gpu={gpu0}
                label="RTX 5060 Ti"
                spec="16 GB GDDR7 · PCIe intern"
                workload="Desktop-Workloads"
              />
              <GpuCard
                gpu={gpu1}
                label="RTX 5070 Ti"
                spec="16 GB GDDR7 · Razer Core X V2"
                workload="Qwen3-14B / 30B-A3B"
                isEgpu
                fastLed
              />
            </div>

            {/* Merge branches */}
            <div style={{ display: 'flex', alignItems: 'center', height: 120, position: 'relative', width: 32, flexShrink: 0 }}>
              <div style={{ position: 'absolute', right: 0, top: 19, left: 0, height: 1.5, background: 'var(--pw-border)' }} />
              <div style={{ position: 'absolute', right: 0, top: 19, width: 1.5, height: 'calc(50% - 19px + 1px)', background: 'var(--pw-border)' }} />
              <div style={{ position: 'absolute', right: 0, bottom: 19, left: 0, height: 1.5, background: 'var(--pw-border)' }} />
              <div style={{ position: 'absolute', right: 0, bottom: 19, width: 1.5, height: 'calc(50% - 19px + 1px)', background: 'var(--pw-border)' }} />
            </div>

            <Conn />

            {/* Output */}
            <div className="pw-stage">
              <div className="pw-output">
                <div className="pw-stream">
                  <div className="pw-stream-line" />
                  <div className="pw-stream-line" />
                  <div className="pw-stream-line" />
                  <div className="pw-stream-line" />
                </div>
                <div className="pw-stage-label" style={{ color: 'var(--tb)' }}>LLM-Antwort</div>
              </div>
              <div className="pw-stage-sub">Streaming</div>
            </div>

          </div>

          {/* System Stats Table (nur bei Live-Daten) */}
          {sys && live && <SystemStatsPanel sys={sys} gpus={gpus} />}

          {/* Legend */}
          <div className="pw-legend">
            <div className="pw-legend-item"><div className="pw-legend-dot" style={{ background: 'var(--tb)' }} />Datenfluss</div>
            <div className="pw-legend-item"><div className="pw-legend-dot" style={{ background: 'var(--nv)' }} />GPU aktiv (NVIDIA)</div>
            <div className="pw-legend-item"><div className="pw-legend-dot" style={{ background: 'var(--amber)' }} />Host-CPU (NUC 15)</div>
            <div className="pw-legend-item"><div className="pw-legend-dot" style={{ background: 'rgba(0,176,240,.7)' }} />Thunderbolt 4</div>
            <div className="pw-legend-item" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 9, color: 'var(--pw-muted)' }}>
              &#x1F512; Keine Daten verlassen das Gerät · DSGVO-konform
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
