/**
 * flowworkshop · components/checklist/ResizeHandle.tsx
 *
 * Vertikaler Zieh-Griff (12px breit) zum Verstellen der Split-View-Breite im
 * Checklisten-Editor. Mittellinie 2px grau, bei Hover/Drag blau und breiter,
 * mittig drei Greifer-Punkt-Paare. Reines Tailwind (keine config-Datei).
 * Vorbild: audit_designer components/ui/ResizeHandle.vue.
 */
interface ResizeHandleProps {
  /** True, solange aktiv gezogen wird (Linie/Greifer bleiben hervorgehoben). */
  resizing: boolean;
  /** Startet das Ziehen (TreeEditor haengt mousemove/mouseup an document). */
  onResizeStart: (e: React.MouseEvent) => void;
}

export default function ResizeHandle({ resizing, onResizeStart }: ResizeHandleProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Bereichsbreite anpassen"
      onMouseDown={(e) => { e.preventDefault(); onResizeStart(e); }}
      className="group relative z-10 flex w-3 shrink-0 cursor-col-resize items-center justify-center"
    >
      {/* Mittellinie: 2px grau, bei Hover/Drag 4px blau */}
      <div
        className={`absolute inset-y-0 left-1/2 -translate-x-1/2 rounded-full transition-all duration-150 ${
          resizing
            ? 'w-1 bg-blue-500'
            : 'w-0.5 bg-slate-300 group-hover:w-1 group-hover:bg-blue-500 dark:bg-slate-600'
        }`}
        aria-hidden="true"
      />
      {/* Greifer-Punkte */}
      <svg
        viewBox="0 0 10 24"
        className={`relative h-6 w-2.5 transition-opacity duration-150 ${
          resizing
            ? 'text-blue-500 opacity-100'
            : 'text-slate-400 opacity-50 group-hover:text-blue-500 group-hover:opacity-100 dark:text-slate-500'
        }`}
        fill="currentColor"
        aria-hidden="true"
      >
        <circle cx="3" cy="8" r="1.5" />
        <circle cx="7" cy="8" r="1.5" />
        <circle cx="3" cy="12" r="1.5" />
        <circle cx="7" cy="12" r="1.5" />
        <circle cx="3" cy="16" r="1.5" />
        <circle cx="7" cy="16" r="1.5" />
      </svg>
    </div>
  );
}
