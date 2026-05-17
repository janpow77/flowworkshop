import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useDarkMode } from '../hooks/useDarkMode';

export default function DatenschutzPage() {
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
            Datenschutzerklärung
          </h1>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Stand: Mai 2026
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Diese Informationen werden gemäß Art. 13 DSGVO bereitgestellt.
          </p>

          <Section title="1. Verantwortlicher">
            <p>
              Verantwortlich für die Datenverarbeitung im Sinne von Art. 4 Nr. 7 DSGVO ist:
            </p>
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

          <Section title="2. Hosting und Server-Logfiles">
            <p>
              Diese Plattform wird auf einem Cloud-Server der Hetzner Online GmbH,
              Industriestr. 25, 91710 Gunzenhausen, Deutschland, betrieben (Standort
              Falkenstein). Es besteht ein Auftragsverarbeitungsvertrag nach Art. 28 DSGVO.
            </p>
            <p>
              Beim Aufruf der Plattform werden durch den Reverse-Proxy (Caddy) folgende Daten
              verarbeitet:
            </p>
            <ul className="ml-5 list-disc space-y-1">
              <li>IP-Adresse des aufrufenden Endgeräts</li>
              <li>Datum und Uhrzeit des Zugriffs</li>
              <li>Aufgerufene URL und HTTP-Statuscode</li>
              <li>Referrer und User-Agent</li>
              <li>Übertragene Datenmenge</li>
            </ul>
            <p>
              Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse am sicheren
              und stabilen Betrieb der Plattform). Die Logs werden nach <strong>spätestens
              30 Tagen</strong> automatisch gelöscht.
            </p>
          </Section>

          <Section title="3. Funktionale Speicherung im Browser (kein Tracking)">
            <p>
              Diese Plattform setzt <strong>keine Tracking- oder Marketing-Cookies</strong> ein
              und nutzt <strong>keine Webanalyse-Dienste Dritter</strong>.
            </p>
            <p>
              Für angemeldete Nutzer wird im{' '}
              <code className="rounded bg-slate-100 px-1 py-0.5 text-[12px] dark:bg-slate-800">
                localStorage
              </code>{' '}
              des Browsers ein Authentifizierungs-Token gespeichert
              (Schlüssel <code>workshop_token</code>) sowie die Rolle des Nutzers
              (<code>workshop_role</code>). Diese Speicherung ist technisch erforderlich, um
              eine Sitzung aufrechtzuerhalten (Art. 25 Abs. 2 TTDSG). Die Daten verbleiben
              ausschließlich auf dem Endgerät des Nutzers und werden beim Abmelden gelöscht.
            </p>
          </Section>

          <Section title="4. Registrierung und Nutzerkonto">
            <p>
              Für den Zugriff auf den geschützten Bereich ist eine Registrierung erforderlich.
              Dabei werden Name, Organisation, dienstliche Rolle und E-Mail-Adresse
              verarbeitet (Art. 6 Abs. 1 lit. b DSGVO — Vertragsdurchführung;
              Art. 6 Abs. 1 lit. a DSGVO — Einwilligung).
            </p>
            <p>
              Optional hochgeladene Dokumente werden ausschließlich auf dem Server der
              Plattform verarbeitet, nicht an Dritte übermittelt und können vom Nutzer
              jederzeit gelöscht werden. Nutzer werden bei der Registrierung ausdrücklich
              darauf hingewiesen, keine personenbezogenen Daten Dritter hochzuladen.
            </p>
            <p>
              Im Rahmen der Registrierung und Konto-Verwaltung werden Transaktions-E-Mails
              versendet: Eingangsbestätigung nach der Anmeldung, Mitteilung über die
              Freischaltung oder Ablehnung durch den Admin, sowie Passwort-Setup- bzw.
              Reset-Links. Der E-Mail-Versand erfolgt über das beim Hosting-Anbieter
              (Hetzner Online GmbH) gehostete Postfach; Standort des Mail-Servers ist
              Deutschland. Rechtsgrundlage ist Art. 6 Abs. 1 lit. b DSGVO
              (Vertragsdurchführung gegenüber dem registrierten Nutzer).
            </p>
          </Section>

          <Section title="5. Eingaben in Suchfelder">
            <p>
              Eingaben in Suchfelder (z. B. Begünstigten- oder Firmensuche) werden
              ausschließlich zur unmittelbaren Beantwortung der Anfrage gegen öffentliche
              Quell-Systeme bzw. die interne Datenbank verwendet. Eine persistente Speicherung
              der Suchbegriffe im Browser (Local Storage, Cookies) oder im server­seitigen
              Anwendungs-Log findet nicht statt; lediglich technische Zugriffslogs (siehe
              Abschnitt 2) enthalten URL und Statuscode.
            </p>
            <p>
              Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse an der
              Bereitstellung der Recherchefunktion). Betroffene können der Verarbeitung gemäß
              Art. 21 DSGVO widersprechen.
            </p>
          </Section>

          <Section title="6. Aggregation öffentlicher Datenquellen">
            <p>
              Die Plattform aggregiert Informationen aus öffentlich zugänglichen Quellen
              (siehe{' '}
              <Link to="/impressum" className="text-cyan-700 underline-offset-4 hover:underline dark:text-cyan-300">
                Impressum
              </Link>
              ). Die Datenerhebung erfolgt durch lesende HTTP-Anfragen
              (Harvester) gegen die jeweiligen Quell-Systeme; dabei werden keine
              personenbezogenen Daten der Nutzer dieser Plattform an die Quell-Systeme
              übermittelt.
            </p>
            <p>
              Die aggregierten Datensätze können personenbezogene Daten enthalten, soweit die
              Quellen diese rechtmäßig und öffentlich bereitstellen (z. B. Veröffentlichungs-
              pflichten nach Art. 49 VO (EU) 2021/1060 oder Art. 9 VO (EU) 651/2014). Die
              Anzeige dieser Datensätze auf dieser Plattform ist nicht öffentlich zugänglich
              und erfolgt ausschließlich gegenüber angemeldeten Workshop-Teilnehmern.
              Rechtsgrundlage ist Art. 6 Abs. 1 lit. b DSGVO (Durchführung des
              Workshop-Teilnahmevertrags) sowie Art. 6 Abs. 1 lit. f DSGVO (berechtigtes
              Interesse an der Bereitstellung von Schulungsmaterial für einen geschlossenen
              Teilnehmerkreis). Eine Verarbeitung auf Grundlage von Art. 6 Abs. 1 lit. e
              oder Art. 85 DSGVO findet ausdrücklich nicht statt.
            </p>
            <p>
              Betroffene Personen können jederzeit Auskunft, Berichtigung oder Löschung der
              auf dieser Plattform sichtbaren Datensätze verlangen — siehe Abschnitt 10.
            </p>
          </Section>

          <Section title="7. KI-gestützte Auswertungen">
            <p>
              Die Plattform setzt zur Demonstration ein <strong>lokal betriebenes
              Sprachmodell</strong> ein. Sämtliche KI-Auswertungen erfolgen auf der eigenen
              Infrastruktur. Es werden <strong>keine Inhalte an externe LLM-Anbieter</strong>
              {' '}(z. B. OpenAI, Anthropic, Google) übermittelt.
            </p>
            <p>
              Erzeugte Texte, Risiko-Indikatoren oder Bewertungen sind technische
              Demonstrationen und stellen ausdrücklich <strong>keine</strong>
              {' '}automatisierten Einzelfallentscheidungen im Sinne von Art. 22 DSGVO dar.
            </p>
          </Section>

          <Section title="8. Karten und Geokodierung">
            <p>
              Für Kartendarstellungen werden Kacheln von OpenStreetMap-Servern bezogen sowie
              Geokodierungs-Anfragen an Nominatim gesendet. Bei diesen Anfragen wird
              technisch bedingt die IP-Adresse des Servers (nicht die des Endnutzers) an
              den jeweiligen OSM-Dienst übermittelt. Es werden keine Endnutzer-IDs übertragen.
            </p>
          </Section>

          <Section title="9. Backups">
            <p>
              Verschlüsselte Backups (age-Verschlüsselung) der Anwendungsdaten werden auf
              einer Hetzner Storage Box (Standort Falkenstein, Deutschland) sowie optional
              auf einem zweiten verschlüsselten Off-Site-Speicher abgelegt. Die Schlüssel
              verbleiben ausschließlich beim Verantwortlichen; externe Anbieter sehen
              ausschließlich Cipher-Text.
            </p>
          </Section>

          <Section title="10. Rechte der betroffenen Personen">
            <p>Sie haben jederzeit das Recht auf:</p>
            <ul className="ml-5 list-disc space-y-1">
              <li>Auskunft über die zu Ihrer Person gespeicherten Daten (Art. 15 DSGVO)</li>
              <li>Berichtigung unrichtiger Daten (Art. 16 DSGVO)</li>
              <li>Löschung (Art. 17 DSGVO)</li>
              <li>Einschränkung der Verarbeitung (Art. 18 DSGVO)</li>
              <li>Datenübertragbarkeit (Art. 20 DSGVO)</li>
              <li>Widerspruch gegen die Verarbeitung (Art. 21 DSGVO)</li>
              <li>
                Widerruf erteilter Einwilligungen mit Wirkung für die Zukunft (Art. 7 Abs. 3
                DSGVO)
              </li>
            </ul>
            <p>
              Bitte richten Sie entsprechende Anfragen an die im Abschnitt 1 genannte
              E-Mail-Adresse.
            </p>
          </Section>

          <Section title="11. Beschwerderecht bei der Aufsichtsbehörde">
            <p>
              Unbeschadet anderweitiger Rechtsbehelfe steht Ihnen ein Beschwerderecht bei
              einer Datenschutz-Aufsichtsbehörde zu, insbesondere beim Hessischen Beauftragten
              für Datenschutz und Informationsfreiheit, Postfach 31 63, 65021 Wiesbaden.
            </p>
          </Section>

          <Section title="12. Änderungen dieser Datenschutzerklärung">
            <p>
              Diese Datenschutzerklärung kann angepasst werden, sobald sich die
              Verarbeitungstätigkeiten ändern oder rechtliche Vorgaben dies erfordern. Die
              jeweils aktuelle Fassung ist auf dieser Seite einsehbar.
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
