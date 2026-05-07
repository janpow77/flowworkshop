/**
 * Zentraler Export-Hook für Karten, Forum-Threads, Dokumente-Listen, etc.
 *
 * Nutzt html-to-image (OKLCH-fähig, kompatibel mit Tailwind v4) und jsPDF.
 * Beide Libraries werden lazy importiert, damit das Initial-Bundle schlank
 * bleibt.
 */
import { useCallback } from 'react';

export type ExportFormat = 'png' | 'jpeg' | 'pdf';

interface PdfOptions {
  /** PDF-Header-Zeile (1 Zeile, links oben) */
  title?: string;
  /** zusätzliche Subtitle-Zeile unter Title */
  subtitle?: string;
  /** Dateiname ohne Extension */
  filename?: string;
  /** A4 default; auch 'a3', 'letter' möglich */
  pageFormat?: 'a4' | 'a3' | 'letter';
  /** Auto-Orientierung anhand des Seitenverhältnisses */
  autoOrientation?: boolean;
}

interface ImageOptions {
  filename?: string;
  /** Skalierungsfaktor (default 2 = retina) */
  scale?: number;
  /** Hintergrundfarbe falls transparent (default white) */
  backgroundColor?: string;
}

function isoStamp(): string {
  return new Date().toISOString().slice(0, 10);
}

function downloadDataUrl(dataUrl: string, filename: string) {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function useExport() {
  const toPng = useCallback(async (
    element: HTMLElement | null,
    opts: ImageOptions = {},
  ): Promise<void> => {
    if (!element) throw new Error('Export-Ziel-Element nicht vorhanden.');
    const { toPng: htmlToPng } = await import('html-to-image');
    const dataUrl = await htmlToPng(element, {
      pixelRatio: opts.scale ?? 2,
      backgroundColor: opts.backgroundColor ?? '#ffffff',
      cacheBust: true,
    });
    downloadDataUrl(dataUrl, `${opts.filename ?? `export_${isoStamp()}`}.png`);
  }, []);

  const toJpeg = useCallback(async (
    element: HTMLElement | null,
    opts: ImageOptions = {},
  ): Promise<void> => {
    if (!element) throw new Error('Export-Ziel-Element nicht vorhanden.');
    const { toJpeg: htmlToJpeg } = await import('html-to-image');
    const dataUrl = await htmlToJpeg(element, {
      pixelRatio: opts.scale ?? 2,
      backgroundColor: opts.backgroundColor ?? '#ffffff',
      cacheBust: true,
      quality: 0.92,
    });
    downloadDataUrl(dataUrl, `${opts.filename ?? `export_${isoStamp()}`}.jpg`);
  }, []);

  const toPdf = useCallback(async (
    element: HTMLElement | null,
    opts: PdfOptions = {},
  ): Promise<void> => {
    if (!element) throw new Error('Export-Ziel-Element nicht vorhanden.');
    const [{ toJpeg: htmlToJpeg }, { jsPDF }] = await Promise.all([
      import('html-to-image'),
      import('jspdf'),
    ]);
    // Erst als JPEG (kleiner als PNG, A4 reicht 0.92)
    const dataUrl = await htmlToJpeg(element, {
      pixelRatio: 2,
      backgroundColor: '#ffffff',
      cacheBust: true,
      quality: 0.92,
    });

    // Bild-Dimensionen ermitteln, um Orientation zu wählen
    const img = new Image();
    img.src = dataUrl;
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('PDF-Bildvorbereitung fehlgeschlagen'));
    });

    const orientation = (opts.autoOrientation ?? true)
      ? (img.width >= img.height ? 'l' : 'p')
      : 'l';
    const pdf = new jsPDF({
      orientation,
      unit: 'pt',
      format: opts.pageFormat ?? 'a4',
    });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const margin = 24;
    const headerH = (opts.title ? 16 : 0) + (opts.subtitle ? 14 : 0);
    const availW = pageW - 2 * margin;
    const availH = pageH - 2 * margin - headerH;
    const ratio = Math.min(availW / img.width, availH / img.height);
    const w = img.width * ratio;
    const h = img.height * ratio;

    let cursorY = margin;
    if (opts.title) {
      pdf.setFontSize(12);
      pdf.text(opts.title, margin, cursorY + 12);
      cursorY += 16;
    }
    if (opts.subtitle) {
      pdf.setFontSize(9);
      pdf.setTextColor(120);
      pdf.text(opts.subtitle, margin, cursorY + 11);
      pdf.setTextColor(0);
      cursorY += 14;
    }

    pdf.addImage(dataUrl, 'JPEG', margin, cursorY + 4, w, h);
    pdf.save(`${opts.filename ?? `export_${isoStamp()}`}.pdf`);
  }, []);

  /**
   * CSV-Export: rendert Zeilen als RFC-4180-konformes CSV (BOM für Excel)
   */
  const toCsv = useCallback((
    rows: Array<Record<string, unknown>>,
    opts: { filename?: string; columns?: string[]; separator?: ',' | ';' } = {},
  ) => {
    const sep = opts.separator ?? ';';
    const cols = opts.columns ?? (rows.length > 0 ? Object.keys(rows[0]) : []);
    const escape = (v: unknown): string => {
      const s = v === null || v === undefined ? '' : String(v);
      if (s.includes(sep) || s.includes('"') || s.includes('\n')) {
        return '"' + s.replace(/"/g, '""') + '"';
      }
      return s;
    };
    const lines = [
      cols.join(sep),
      ...rows.map((r) => cols.map((c) => escape(r[c])).join(sep)),
    ];
    const csv = '﻿' + lines.join('\r\n'); // BOM für Excel-UTF-8
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    downloadBlob(blob, `${opts.filename ?? `export_${isoStamp()}`}.csv`);
  }, []);

  /**
   * Mehrere URLs als ZIP herunterladen (für Bulk-Download in Documents).
   * Nutzt JSZip lazy.
   */
  const toZip = useCallback(async (
    files: Array<{ name: string; url: string }>,
    opts: { filename?: string } = {},
  ) => {
    const { default: JSZip } = await import('jszip');
    const zip = new JSZip();
    await Promise.all(
      files.map(async (f) => {
        const res = await fetch(f.url);
        if (!res.ok) throw new Error(`Datei ${f.name} nicht abrufbar`);
        const blob = await res.blob();
        zip.file(f.name, blob);
      }),
    );
    const out = await zip.generateAsync({ type: 'blob' });
    downloadBlob(out, `${opts.filename ?? `dokumente_${isoStamp()}`}.zip`);
  }, []);

  return { toPng, toJpeg, toPdf, toCsv, toZip };
}
