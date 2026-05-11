import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useDarkMode } from '../hooks/useDarkMode';

export default function ImpressumPage() {
  const [dark] = useDarkMode();

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-[var(--app-bg)] text-slate-900 dark:text-slate-100">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-20 top-0 h-72 w-72 rounded-full bg-cyan-300/20 blur-3xl dark:bg-cyan-500/10" />
        <div className="absolute right-[-7rem] top-24 h-80 w-80 rounded-full bg-amber-300/20 blur-3xl dark:bg-amber-400/10" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.78),rgba(255,255,255,0)_48%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,41,59,0.5),rgba(2,6,23,0)_45%)]" />
      </div>

      <header className="relative z-10 border-b border-slate-200/60 bg-white/70 backdrop-blur-md dark:border-slate-800/60 dark:bg-slate-950/60">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-5 py-3 lg:px-8">
          <Link to="/" className="flex items-center gap-3 text-slate-700 dark:text-slate-200">
            <span className="text-2xl">🇪🇺</span>
            <div className="leading-tight">
              <div className="text-sm font-semibold">Prüferworkshop 2026</div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400">
                Schulungs- und Demonstrationsplattform
              </div>
            </div>
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <ArrowLeft size={14} /> Zurück
          </Link>
        </div>
      </header>

      <main className="relative z-10 flex-1 overflow-auto px-5 pb-12 pt-8 lg:px-8">
        <article className="mx-auto w-full max-w-3xl rounded-2xl border border-slate-200/70 bg-white/80 p-8 shadow-sm backdrop-blur-md dark:border-slate-800/70 dark:bg-slate-950/60 lg:p-10">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">
            Impressum
          </h1>

          <Section title="Angaben gemäß § 5 DDG">
            <p className="font-medium">Jan Riener</p>
            <p>Am Vogelgesang 20</p>
            <p>65817 Eppstein</p>
            <p className="pt-1">
              E-Mail:{' '}
              <a
                href="mailto:jan.riener@vwvg.de"
                className="text-cyan-700 underline-offset-4 hover:underline dark:text-cyan-300"
              >
                jan.riener@vwvg.de
              </a>
            </p>
          </Section>

          <Section title="Zweck des Angebots">
            <p>
              Dieses Internetangebot wurde im Rahmen von Schulungs- und Demonstrationszwecken
              für Auditoren und Prüfbehörden entwickelt. Die bereitgestellten Informationen
              dienen ausschließlich der allgemeinen Information, Analyse und Weiterbildung.
            </p>
            <p>Das Angebot ist vollständig kostenlos und verfolgt keine kommerziellen Zwecke.</p>
          </Section>

          <Section title="Datenquellen">
            <p>
              Die dargestellten Informationen stammen aus öffentlich zugänglichen Quellen,
              Registern, Veröffentlichungen oder Open-Data-Angeboten Dritter. Insbesondere:
            </p>
            <ul className="ml-5 list-disc space-y-1">
              <li>
                EU-Beihilferegister „Transparency Aid Module" (TAM) der Europäischen Kommission
              </li>
              <li>
                EFRE-/ESF-/JTF-Transparenzlisten der Länder gemäß Art. 49 VO (EU) 2021/1060
              </li>
              <li>EU Financial Sanctions File (EU FSF), OFAC, OFSI</li>
              <li>OpenStreetMap / Nominatim für Geokodierung und Kartendarstellung</li>
              <li>NUTS-Klassifikation und Postleitzahl-Open-Data</li>
            </ul>
            <p>Es erfolgt keine Gewähr für:</p>
            <ul className="ml-5 list-disc space-y-1">
              <li>Vollständigkeit,</li>
              <li>Aktualität,</li>
              <li>Richtigkeit,</li>
              <li>Verfügbarkeit oder</li>
              <li>rechtliche Verwertbarkeit der dargestellten Daten.</li>
            </ul>
            <p>
              Die Verantwortung für die Inhalte der jeweiligen Datenquellen liegt ausschließlich
              bei den jeweiligen Betreibern oder Herausgebern.
            </p>
          </Section>

          <Section title="Haftung für Inhalte">
            <p>
              Die Inhalte dieser Website wurden mit größtmöglicher Sorgfalt erstellt. Eine
              Haftung für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte wird
              jedoch ausgeschlossen.
            </p>
            <p>
              Dieses Angebot stellt keine Rechtsberatung, Prüfungsfeststellung oder verbindliche
              Bewertung dar.
            </p>
          </Section>

          <Section title="KI-gestützte Auswertungen">
            <p>
              Teile dieser Plattform nutzen lokal betriebene Sprachmodelle (LLMs) zur
              Demonstration KI-gestützter Auswertungs- und Risikoanalyseverfahren. Erzeugte
              Texte, Risiko-Indikatoren oder Bewertungen sind <strong>technische
              Demonstrationen</strong> und <strong>keine</strong> abschließenden
              Prüfungsfeststellungen, Risikoeinstufungen im Rechtssinne oder verbindlichen
              Aussagen über Personen oder Unternehmen.
            </p>
          </Section>

          <Section title="Haftung für externe Links">
            <p>
              Diese Website kann Verlinkungen zu externen Websites Dritter enthalten. Auf deren
              Inhalte besteht kein Einfluss. Für die Inhalte der verlinkten Seiten ist stets
              der jeweilige Anbieter oder Betreiber verantwortlich.
            </p>
          </Section>

          <Section title="Urheberrecht">
            <p>
              Soweit nicht anders angegeben, unterliegen die auf dieser Website erstellten
              Inhalte dem deutschen Urheberrecht. Daten aus öffentlichen Quellen bleiben den
              jeweiligen Rechteinhabern zugeordnet.
            </p>
          </Section>

          <Section title="Datenschutz">
            <p>
              Informationen zur Verarbeitung personenbezogener Daten finden sich in der
              gesonderten{' '}
              <Link
                to="/datenschutz"
                className="text-cyan-700 underline-offset-4 hover:underline dark:text-cyan-300"
              >
                Datenschutzerklärung
              </Link>
              .
            </p>
          </Section>

        </article>
      </main>

      <footer className="relative z-10 border-t border-slate-200/60 bg-white/60 px-5 py-3 text-center text-[11px] text-slate-500 backdrop-blur-md dark:border-slate-800/60 dark:bg-slate-950/40 dark:text-slate-400 lg:px-8">
        <Link to="/impressum" className="hover:underline">
          Impressum
        </Link>
        <span className="mx-2">·</span>
        <Link to="/datenschutz" className="hover:underline">
          Datenschutz
        </Link>
        <span className="mx-2">·</span>
        {dark ? 'Dark' : 'Hell'}-Modus aktiv
      </footer>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8 space-y-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
      <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
      {children}
    </section>
  );
}
