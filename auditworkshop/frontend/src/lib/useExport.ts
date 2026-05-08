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
   * XLSX-Export: erzeugt ein minimales OOXML-Spreadsheet (1 Sheet, 1 Tab)
   * direkt im Browser — ohne SheetJS-Dependency. Nutzt das bereits
   * gebundelte JSZip. Die Datei laesst sich in Excel, LibreOffice, Numbers
   * und Google Sheets oeffnen.
   *
   * Hinweis: Strings werden via inline-strings (`<is><t>`) geschrieben,
   * Zahlen als Number. Keine Formeln, kein Styling. Reicht voellig fuer
   * tabellarische Auswertungs-Exporte.
   */
  const toXlsx = useCallback(async (
    rows: Array<Record<string, unknown>>,
    opts: { filename?: string; columns?: string[]; sheetName?: string } = {},
  ) => {
    const { default: JSZip } = await import('jszip');
    const cols = opts.columns ?? (rows.length > 0 ? Object.keys(rows[0]) : []);
    const sheetName = (opts.sheetName ?? 'Auswertung').slice(0, 31).replace(/[\\/*?[\]:]/g, '');

    const colLetter = (n: number): string => {
      let s = '';
      let i = n;
      while (i >= 0) {
        s = String.fromCharCode((i % 26) + 65) + s;
        i = Math.floor(i / 26) - 1;
      }
      return s;
    };
    const escapeXml = (v: unknown): string => {
      const s = v === null || v === undefined ? '' : String(v);
      return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;').replace(/'/g, '&apos;');
    };
    const isFiniteNumber = (v: unknown): v is number =>
      typeof v === 'number' && Number.isFinite(v);

    const allRows: Array<Array<unknown>> = [
      cols,
      ...rows.map((r) => cols.map((c) => r[c])),
    ];
    const sheetXmlRows = allRows.map((row, rIdx) => {
      const cells = row.map((val, cIdx) => {
        const ref = `${colLetter(cIdx)}${rIdx + 1}`;
        // Header-Zeile (rIdx==0) immer als String ausgeben, damit auch
        // numerische Spaltennamen als Text erhalten bleiben.
        if (rIdx > 0 && isFiniteNumber(val)) {
          return `<c r="${ref}"><v>${val}</v></c>`;
        }
        return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${escapeXml(val)}</t></is></c>`;
      }).join('');
      return `<row r="${rIdx + 1}">${cells}</row>`;
    }).join('');
    const sheetXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetXmlRows}</sheetData></worksheet>`;
    const workbookXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${escapeXml(sheetName)}" sheetId="1" r:id="rId1"/></sheets></workbook>`;
    const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`;
    const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`;
    const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`;

    const zip = new JSZip();
    zip.file('[Content_Types].xml', contentTypes);
    zip.folder('_rels')!.file('.rels', rootRels);
    const xl = zip.folder('xl')!;
    xl.file('workbook.xml', workbookXml);
    xl.folder('_rels')!.file('workbook.xml.rels', workbookRels);
    xl.folder('worksheets')!.file('sheet1.xml', sheetXml);

    const blob = await zip.generateAsync({
      type: 'blob',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    downloadBlob(blob, `${opts.filename ?? `export_${isoStamp()}`}.xlsx`);
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

  return { toPng, toJpeg, toPdf, toCsv, toXlsx, toZip };
}
