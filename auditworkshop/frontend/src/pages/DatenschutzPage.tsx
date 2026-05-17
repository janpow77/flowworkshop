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

          <Section title="2. Hosting, Verarbeitungsorte und Server-Logfiles">
            <p>
              Die Web-Anwendung (Frontend, Backend, Datenbank, Reverse-Proxy) wird auf einem
              Cloud-Server der Hetzner Online GmbH, Industriestr. 25, 91710 Gunzenhausen,
              Deutschland, betrieben (Standort Falkenstein, FSN1). Mit Hetzner besteht ein
              Auftragsverarbeitungsvertrag nach Art. 28 DSGVO. Sämtliche Nutzersitzungen,
              Registrierungsdaten, hochgeladenen Dokumente und aggregierten öffentlichen
              Datenbestände werden ausschließlich dort gespeichert.
            </p>
            <p>
              Die KI-Inferenz (siehe Abschnitt 6) erfolgt <strong>nicht</strong> auf dem
              Hetzner-Server, sondern auf zwei vom Verantwortlichen selbst betriebenen
              GPU-Geräten am Standort Eppstein (Privatadresse des Verantwortlichen, siehe
              Abschnitt 1). Die Geräte sind ausschließlich für die Modell-Ausführung zuständig
              und speichern Anfragen nicht persistent.
            </p>
            <p>
              Die Verbindung zwischen dem Hetzner-Server und den Inferenz-Geräten erfolgt
              über ein privates WireGuard-basiertes Mesh-Netzwerk der Tailscale Inc.,
              100 Spear Street, Suite 1850, San Francisco, CA 94105, USA. Tailscale vermittelt
              ausschließlich verschlüsselte Punkt-zu-Punkt-Verbindungen (Coordination Plane);
              die transportierten Inhalte werden Ende-zu-Ende zwischen den Endpunkten
              verschlüsselt und sind für Tailscale technisch nicht einsehbar. Für die
              Übermittlung von Verbindungs-Metadaten in die USA besteht ein
              Auftragsverarbeitungsvertrag nach Art. 28 DSGVO sowie eine Übermittlung auf
              Grundlage des EU-US Data Privacy Framework (Angemessenheitsbeschluss vom
              10. Juli 2023, Art. 45 DSGVO).
            </p>
            <p>
              Beim Aufruf der Plattform werden durch den Reverse-Proxy (Caddy) auf dem
              Hetzner-Server folgende Daten verarbeitet:
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

          <Section title="4. Registrierung, Nutzerkonto und E-Mail-Versand">
            <p>
              Für den Zugriff auf den geschützten Bereich ist eine Registrierung erforderlich.
              Dabei werden Name, Organisation, dienstliche Rolle und E-Mail-Adresse
              verarbeitet (Art. 6 Abs. 1 lit. b DSGVO — Vertragsdurchführung;
              Art. 6 Abs. 1 lit. a DSGVO — Einwilligung).
            </p>
            <p>
              Optional hochgeladene Dokumente werden auf dem Hetzner-Server gespeichert
              (siehe Abschnitt 2) und nicht an Dritte übermittelt. Für die Aufbereitung
              (OCR, Vektor-Embeddings, KI-Auswertung) werden Inhalte in die in Abschnitt 6
              beschriebene KI-Pipeline gegeben; sie verlässt die selbst betriebene
              Infrastruktur des Verantwortlichen nicht. Uploads können vom Nutzer jederzeit
              gelöscht werden. Nutzer werden bei der Registrierung ausdrücklich darauf
              hingewiesen, keine personenbezogenen Daten Dritter hochzuladen.
            </p>
            <p>
              Nach erfolgreicher Anmeldung versendet die Plattform eine
              Anmeldebestätigung an die angegebene E-Mail-Adresse sowie eine
              Benachrichtigung an den Veranstalter. Auf Wunsch (separate, freiwillige
              Einwilligung im Anmeldeformular) wird die Bestätigungsmail um einen kurzen,
              vom selbst betriebenen Sprachmodell erzeugten Personalisierungs-Absatz
              ergänzt; ohne diese Einwilligung wird ausschließlich der statische
              Standardtext versandt. Der Versand erfolgt über den SMTP-Dienst der
              <strong> 1&1 IONOS SE</strong>, Elgendorfer Straße 57, 56410 Montabaur,
              Deutschland (Mailbox <code>jan.riener@vwvg.de</code>). Mit IONOS besteht
              ein Auftragsverarbeitungsvertrag nach Art. 28 DSGVO. Rechtsgrundlage ist
              Art. 6 Abs. 1 lit. b DSGVO (Vertragsdurchführung) sowie hinsichtlich der
              KI-Personalisierung Art. 6 Abs. 1 lit. a DSGVO (Einwilligung), jederzeit
              widerruflich mit Wirkung für die Zukunft.
            </p>
          </Section>

          <Section title="5. Aggregation öffentlicher Datenquellen">
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
              pflichten nach Art. 49 VO (EU) 2021/1060). Rechtsgrundlage der Verarbeitung
              durch diese Plattform ist Art. 6 Abs. 1 lit. e und f DSGVO i. V. m.
              Art. 85 DSGVO (Demonstrations- und Schulungszweck im öffentlichen Interesse).
            </p>
            <p>
              Betroffene Personen können jederzeit Auskunft, Berichtigung oder Löschung der
              auf dieser Plattform sichtbaren Datensätze verlangen — siehe Abschnitt 9.
            </p>
          </Section>

          <Section title="6. KI-gestützte Auswertungen">
            <p>
              Die Plattform setzt zur Demonstration ausschließlich <strong>selbst betriebene,
              quelloffene Sprachmodelle</strong> ein (u. a. Qwen-Familie, BGE-Embeddings).
              Diese laufen auf den in Abschnitt 2 beschriebenen GPU-Geräten am Standort
              Eppstein und werden vom Hetzner-Server über das Tailscale-Mesh angesprochen.
              Es werden <strong>keine Inhalte an externe LLM-Anbieter</strong> (z. B. OpenAI,
              Anthropic, Google) übermittelt.
            </p>
            <p>
              Vom KI-Pfad umfasst sind: Textgenerierung (LLM), Vektor-Embeddings für die
              Wissens­suche, optische Zeichenerkennung (OCR) bei PDF-Uploads sowie das
              Re-Ranking von Suchtreffern. Anfragen werden auf den Inferenz-Geräten nur
              flüchtig im Arbeitsspeicher verarbeitet und nicht protokolliert oder
              persistiert; eine Auswertung dieser Inhalte zu Trainingszwecken findet nicht
              statt.
            </p>
            <p>
              Erzeugte Texte, Risiko-Indikatoren oder Bewertungen sind technische
              Demonstrationen und stellen ausdrücklich <strong>keine</strong>
              {' '}automatisierten Einzelfallentscheidungen im Sinne von Art. 22 DSGVO dar.
            </p>
          </Section>

          <Section title="7. Karten und Geokodierung">
            <p>
              Für Kartendarstellungen werden Kacheln von OpenStreetMap-Servern bezogen sowie
              Geokodierungs-Anfragen an Nominatim gesendet. Bei diesen Anfragen wird
              technisch bedingt die IP-Adresse des Servers (nicht die des Endnutzers) an
              den jeweiligen OSM-Dienst übermittelt. Es werden keine Endnutzer-IDs übertragen.
            </p>
          </Section>

          <Section title="8. Backups">
            <p>
              Verschlüsselte Backups (age-Verschlüsselung) der Anwendungsdaten werden auf
              einer Hetzner Storage Box (Standort Falkenstein, Deutschland) sowie optional
              auf einem zweiten verschlüsselten Off-Site-Speicher abgelegt. Die Schlüssel
              verbleiben ausschließlich beim Verantwortlichen; externe Anbieter sehen
              ausschließlich Cipher-Text.
            </p>
          </Section>

          <Section title="9. Rechte der betroffenen Personen">
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

          <Section title="10. Beschwerderecht bei der Aufsichtsbehörde">
            <p>
              Unbeschadet anderweitiger Rechtsbehelfe steht Ihnen ein Beschwerderecht bei
              einer Datenschutz-Aufsichtsbehörde zu, insbesondere beim Hessischen Beauftragten
              für Datenschutz und Informationsfreiheit, Postfach 31 63, 65021 Wiesbaden.
            </p>
          </Section>

          <Section title="11. Änderungen dieser Datenschutzerklärung">
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
