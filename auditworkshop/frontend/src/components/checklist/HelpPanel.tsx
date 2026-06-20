/**
 * flowworkshop · components/checklist/HelpPanel.tsx
 *
 * Modal mit einer kompakten Anleitung zum Aufbau einer Checkliste im
 * Treeview-Editor. Im Stil der uebrigen Manager-Modals (AnswerSetManager,
 * CategoryManager): zentriertes Off-Canvas-Modal mit Schliessen-Button,
 * Escape-Taste, Dark-Mode-tauglich. Rein informativ — kein State, kein API.
 */
import { useEffect } from 'react';
import {
  X, BookOpen, FolderTree, ListChecks, Tags, FileDown,
  Heading, HelpCircle, Info, Undo2, MousePointerClick,
} from 'lucide-react';

interface HelpPanelProps {
  onClose: () => void;
}

export default function HelpPanel({ onClose }: HelpPanelProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-xl dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-slate-100">
            <BookOpen size={18} className="text-emerald-500" /> Anleitung — Checkliste aufbauen
          </h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Schließen">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5 text-sm leading-6 text-slate-600 dark:text-slate-300">
          {/* 1) Aufbau */}
          <Section icon={<FolderTree size={15} className="text-blue-500" />} title="1 · So bauen Sie eine Checkliste auf">
            <p>
              Legen Sie zunächst über die Toolbar einen <b>Wurzelknoten</b> an: Wählen Sie
              links den Typ aus und klicken Sie auf <b>„Wurzelknoten"</b>. Untergeordnete
              Knoten verschachteln Sie auf zwei Wegen:
            </p>
            <ul className="ml-1 space-y-1.5">
              <li className="flex items-start gap-2">
                <MousePointerClick size={15} className="mt-0.5 shrink-0 text-slate-400" />
                <span><b>Rechtsklick</b> auf einen Knoten öffnet das Kontextmenü (Unterknoten anlegen, duplizieren, löschen).</span>
              </li>
              <li className="flex items-start gap-2">
                <MousePointerClick size={15} className="mt-0.5 shrink-0 text-slate-400" />
                <span><b>Ziehen &amp; Ablegen</b> verschiebt Knoten — oben/unten setzt davor/danach, in der Mitte legt hinein.</span>
              </li>
            </ul>
            <div className="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/50">
              <NodeTypeLine icon={<Heading size={14} className="text-blue-600 dark:text-blue-400" />} label="Überschrift" desc="reines Gliederungselement ohne Antwort" />
              <NodeTypeLine icon={<HelpCircle size={14} className="text-sky-600 dark:text-sky-400" />} label="Frage" desc="Prüfschritt mit Antwort (Antworttyp/Antwortset)" />
              <NodeTypeLine icon={<Info size={14} className="text-amber-600 dark:text-amber-400" />} label="Hinweis" desc={'Erläuterung ohne Bewertung (Präfix „Hinweis:")'} />
            </div>
            <p className="flex items-start gap-2">
              <Undo2 size={15} className="mt-0.5 shrink-0 text-slate-400" />
              <span><b>Strg+Z</b> macht den letzten Schritt rückgängig, <b>Strg+Umschalt+Z</b> stellt ihn wieder her (lokal).</span>
            </p>
          </Section>

          {/* 2) Eigenschaften */}
          <Section icon={<HelpCircle size={15} className="text-sky-500" />} title="2 · Eigenschaften einer Frage">
            <p>
              Ein Klick auf einen Knoten öffnet rechts das <b>Eigenschaften-Panel</b>.
              Dort pflegen Sie:
            </p>
            <ul className="ml-1 list-disc space-y-1 pl-4">
              <li><b>Titel / Fragetext</b> — der eigentliche Prüftext.</li>
              <li><b>Knotentyp</b> — Überschrift, Frage oder Hinweis.</li>
              <li><b>Antworttyp</b> — z. B. „Ja/Nein/Teilweise/Entfällt", „Betrag", „Datum" oder „Auswahl (Antwortset)".</li>
              <li><b>Eingabetyp</b> — Auswahl (Dropdown), Freitext, Betrag oder Datum.</li>
            </ul>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Änderungen werden automatisch gespeichert; der Indikator oben rechts zeigt „speichere… / gespeichert".
            </p>
          </Section>

          {/* 3) Antwortsets */}
          <Section icon={<ListChecks size={15} className="text-emerald-500" />} title="3 · Antwortsets erfassen">
            <p>
              Über den Toolbar-Button <b>„Antwortsets"</b> legen Sie ein Set an —
              etwa <b>„Ja / Nein / Teilweise / Entfällt"</b>. Wählen Sie dabei den
              Geltungsbereich (diese Checkliste oder globale Bibliothek).
            </p>
            <ul className="ml-1 list-disc space-y-1 pl-4">
              <li>Pflegen Sie je Option <b>Name</b>, <b>Standard</b>, <b>Entfällt</b>, <b>Wert</b>, <b>Schwelle</b> und <b>Bemerkung</b>.</li>
              <li>Weisen Sie das Set einer Frage im Eigenschaften-Panel im Feld <b>„Antwortset"</b> zu.</li>
            </ul>
          </Section>

          {/* 4) Kategorien & Versionen */}
          <Section icon={<Tags size={15} className="text-emerald-500" />} title="4 · Kategorien &amp; Versionen">
            <p>
              Über <b>„Kategorien"</b> legen Sie Fragenkategorien an und ordnen sie
              im Eigenschaften-Panel im Feld <b>„Kategorie"</b> zu. Über das
              <b> Versionen</b>-Menü können Sie Stände festhalten, freigeben und bei
              Bedarf auf eine frühere Version zurücksetzen; der <b>Verlauf</b> zeigt
              alle Änderungen.
            </p>
          </Section>

          {/* 5) Export */}
          <Section icon={<FileDown size={15} className="text-blue-500" />} title="5 · Export">
            <p>
              Oben rechts auf der Checklisten-Seite lässt sich die fertige Checkliste
              als <b>Word</b>, <b>Excel</b> oder <b>PDF</b> exportieren.
            </p>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
        {icon} {title}
      </h3>
      {children}
    </section>
  );
}

function NodeTypeLine({ icon, label, desc }: { icon: React.ReactNode; label: string; desc: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span><b>{label}</b> — {desc}</span>
    </div>
  );
}
