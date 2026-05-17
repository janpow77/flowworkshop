# Datenschutzgutachten — workshop.flowaudit.de

**Stichtag:** Mai 2026
**Stand:** nach Iteration 2 (Commit `a660525`, Branch
`claude/add-legal-compliance-QGM6a`)
**Verfasser:** Betreiber-Selbsteinschätzung
**Adressat:** Verantwortlicher (Jan Riener, Eppstein), zur Vorlage bei einem auf
DSGVO/IT-Recht spezialisierten Anwalt sowie zu eigenen Compliance-Zwecken

---

## A. Vorbemerkung und Charakter dieses Dokuments

Dieses Dokument ist eine **Selbsteinschätzung des Betreibers** zur
datenschutzrechtlichen Lage der Plattform `workshop.flowaudit.de`. Es ist
**ausdrücklich kein anwaltliches Rechtsgutachten** und **keine
Datenschutz-Folgenabschätzung im Sinne des Art. 35 DSGVO**.

Sein Zweck ist:

1. die strukturierte Bestandsaufnahme aller verarbeitungs-relevanten
   Tatsachen und der jeweils einschlägigen Rechtsgrundlagen,
2. die ehrliche Identifikation der Restrisiken, die mit dem aktuellen
   technischen Stand verbunden sind,
3. eine belastbare Arbeitsgrundlage für die nachfolgende, kostenpflichtige
   anwaltliche Prüfung und gegebenenfalls für eine formale DSFA,
4. eine prüfbare Dokumentation interner Compliance-Arbeit für den Fall einer
   aufsichtsbehördlichen Anfrage (Art. 31, Art. 58 DSGVO).

Eine vollständige Rechtssicherheit kann dieses Dokument **nicht ersetzen**.
Es wurde unter Berücksichtigung von DSGVO, BDSG (2018 i. d. F. 2024), DDG,
MStV und einschlägiger EuGH-/BGH-/OLG-Rechtsprechung erstellt, **ersetzt aber
keine anwaltliche Beratung im Einzelfall**.

---

## B. Sachverhalt

### B.1 Verantwortlicher (Art. 4 Nr. 7 DSGVO)

| Feld | Inhalt |
|---|---|
| Name | Jan Riener |
| Anschrift | Am Vogelgesang 20, 65817 Eppstein |
| E-Mail | jan.riener@vwvg.de |
| Rolle | Privatperson, Betrieb der Plattform außerhalb dienstlicher Aufgaben |
| Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV | identisch |
| Datenschutzbeauftragter | nicht bestellt (siehe C.12) |

### B.2 Plattform-Beschreibung

`workshop.flowaudit.de` ist eine Schulungs- und Demonstrationsplattform für
Auditoren und EFRE-Prüfbehörden. Sie zeigt anhand realer öffentlicher
Datenquellen, wie ein KI-/LLM-gestützter Register-Abgleich (State-Aid,
Begünstigtenverzeichnisse, Sanktionslisten) aussehen kann.

Architektur (Stand Mai 2026):

| Schicht | Technologie | Standort |
|---|---|---|
| Hosting | Hetzner Online GmbH (CCX23) | Falkenstein/Nürnberg, Deutschland |
| Datenbank | PostgreSQL 16 + pgvector | gleicher Host |
| Backend | FastAPI (Python 3.12) | gleicher Host |
| Frontend | React 19, statisch ausgeliefert via nginx | gleicher Host |
| LLM | Ollama (qwen3:14b) auf NUC-Spoke via llm-router | Eigenstandort, kein Drittanbieter |
| Mail-Versand | SMTP (mail.your-server.de) | Hetzner Online GmbH, Deutschland |
| Kartenkacheln | OpenStreetMap (`tile.openstreetmap.org`) | OpenStreetMap Foundation, UK |
| Geocoding | Nominatim (serverseitig, mit lokalem 3.177-Eintrag-Cache) | OpenStreetMap Foundation, UK |
| Schriften | Fontsource (lokal ausgeliefert seit Mai 2026) | nicht extern |

### B.3 Datenkategorien

| Kategorie | Quelle | Personenbezug |
|---|---|---|
| Anmelde-Daten registrierter Nutzer | Selbsteingabe bei `/signup` | direkt |
| Authentifizierungs-Token | Session-Cookie/localStorage | direkt |
| Server-Access-Logs | nginx/FastAPI, TTL ≤ 30 Tage | IP-Adresse (gehasht) |
| Sucheingaben | Nutzer-Sessions | indirekt (keine Persistenz) |
| Begünstigten-Datensätze (EFRE Art. 49 VO 2021/1060) | offizielle Transparenzlisten DE/AT | direkt (Empfänger, Adresse, Förderbetrag) |
| State-Aid-Datensätze (Art. 9 VO 651/2014) | TAM (EU-Kommission) | direkt (Unternehmen, Förderhöhe) |
| Sanktionslisten | OpenSanctions (EU FSF, UN SC, OFAC, OFSI, SECO) | **Art. 9 / Art. 10 DSGVO** |
| Konzernverbund | GLEIF + Wikidata SPARQL | direkt (Unternehmens-Bezug) |
| Geokoordinaten | Nominatim-Cache | nicht personenbezogen |
| Transaktions-Mails | Nutzer-/Admin-E-Mail-Adressen | direkt |

### B.4 Verarbeitungstätigkeiten

| # | Tätigkeit | Endpunkt(e) | Zweck |
|---|---|---|---|
| 1 | Selbstregistrierung | `POST /api/auth/signup` | Vertragsanbahnung Workshop-Teilnahme |
| 2 | Admin-Freischaltung | `POST /api/auth/users/{id}/approve` | Vertragsschluss |
| 3 | Login | `POST /api/auth/login`, `/qr-login` | Vertragsdurchführung |
| 4 | Suche in State-Aid / Beneficiaries / Sanctions | diverse GET (auth-pflichtig) | Schulungs-/Vertragsdurchführung |
| 5 | Export von Datensätzen | diverse `/export` (auth-pflichtig) | Schulungs-/Vertragsdurchführung |
| 6 | Cross-Register-Audit-Bericht | `GET/POST /api/state-aid/audit-report*` | Schulungs-/Vertragsdurchführung |
| 7 | LLM-gestützte Frage-Antwort | `POST /api/state-aid/ask` | Schulungs-/Vertragsdurchführung |
| 8 | Server-Logs | nginx/FastAPI | IT-Sicherheit, Fehleranalyse (Art. 6 Abs. 1 lit. f) |
| 9 | Karten-Anzeige | Frontend → tile.openstreetmap.org | UI-Darstellung |
| 10 | Geocoding-Pflege | Backend → nominatim.openstreetmap.org | Aufbau Karten-Layer |
| 11 | Transaktions-Mails | SMTP Hetzner | Account-Verwaltung |
| 12 | Backups | age-verschlüsselt, externer Speicher | IT-Sicherheit |

### B.5 Empfänger und Auftragsverarbeiter

| Empfänger | Funktion | Vertrag |
|---|---|---|
| Hetzner Online GmbH | Hosting + SMTP | AVV nach Art. 28 (vorhanden) |
| OpenStreetMap Foundation | Karten-Tiles | Public-Service ohne AVV; Endnutzer-IP wird übermittelt |
| OpenStreetMap Foundation (Nominatim) | Geocoding | nur Server-IP, kein Endnutzerbezug, max 1 req/s |
| GLEIF / Wikidata | Konzernverbund-Lookup | öffentliche APIs ohne AVV; nur Suchbegriff, keine PII |
| OpenSanctions | Sanctions-Datensatz-Lieferant | öffentliche Quellliste, Download |
| EU-Kommission (TAM) | State-Aid-Datensätze | öffentliche Quelle |
| Empfänger der Mails | Nutzer selbst + alle role=admin Accounts | kein Drittempfang |

**Keine** Datenübermittlung an LLM-Anbieter (OpenAI, Anthropic, Google). Das
LLM läuft ausschließlich auf eigener Hardware (Ollama auf NUC).

### B.6 Speicherorte und Drittstaaten-Übermittlung

| Verarbeitung | Standort | Drittland? |
|---|---|---|
| Datenbank, Backend, Frontend, SMTP | Hetzner Falkenstein/Nürnberg (DE) | nein |
| Backups | age-verschlüsselt; selbst bei Drittland-Speicherung nur Cipher-Text | irrelevant |
| OSM-Tiles | UK | **ja** (UK, Angemessenheitsbeschluss der EU vom Juni 2021) |
| Nominatim (serverseitig) | UK | **ja** (UK, Angemessenheitsbeschluss; mildert durch Cache) |
| GLEIF/Wikidata-Lookups | global verteilt | **ja**, aber nur Firmen-Suchbegriff (kein PII) |
| LLM-Inferenz | NUC im EU-Raum | nein |

### B.7 Speicherdauern

| Datenkategorie | TTL | Quelle |
|---|---|---|
| Server-Access-Logs | ≤ 30 Tage | `WORKSHOP_ACCESS_LOG_TTL_DAYS` in `/etc/auditworkshop/env` |
| Sessions (Bearer-Token) | persistent bis `logout` oder admin-`suspend` | DB-Tabelle `workshop_sessions` |
| Registrierungs-Daten | bis zur Konto-Löschung (`deleted_at`) | DB-Tabelle `workshop_registrations` |
| Aggregierte Quell-Datensätze (Beneficiaries/State-Aid/Sanctions) | bis zur nächsten Harvest-Aktualisierung | Quell-Tabelle wird ersetzt |
| Audit-Report-Log | bis zur manuellen Bereinigung durch Admin | `workshop_audit_report_log` |
| Security-Audit-Log | bis zur manuellen Bereinigung | `workshop_security_audit` |
| Geocoding-Cache | persistent (3.177 Einträge, Mai 2026) | `backend/data/geocode_cache.json` |
| Transaktions-Mails | nicht serverseitig persistiert (Versand-only) | — |

---

## C. Rechtliche Bewertung

### C.1 Anwendungsbereich der DSGVO (Art. 2)

Die DSGVO findet auf alle in B.4 genannten Verarbeitungstätigkeiten
**uneingeschränkt** Anwendung. Die **Haushaltsausnahme nach Art. 2 Abs. 2
lit. c DSGVO** greift nicht: Sobald personenbezogene Daten einem
unbestimmten Personenkreis im Internet zugänglich gemacht werden (auch im
Login-Bereich, sofern Selbstregistrierung möglich ist), ist die Verarbeitung
keine „ausschließlich persönliche oder familiäre Tätigkeit" mehr —
ständige Rechtsprechung seit EuGH **C-101/01 (Lindqvist)**, bestätigt in
EuGH C-212/13 (Ryneš) und C-345/17 (Buivids).

**Ergebnis:** Privatperson Jan Riener ist Verantwortlicher im Sinne des
Art. 4 Nr. 7 DSGVO. Sämtliche Pflichten der DSGVO greifen.

### C.2 Rechtsgrundlagen je Verarbeitungstätigkeit

#### C.2.1 Registrierung und Account-Verwaltung (B.4 Nr. 1–3, 11)

- **Art. 6 Abs. 1 lit. b DSGVO** (Vertragsdurchführung): Der Workshop ist
  ein Schulungs-Angebot, die Anmeldung begründet ein vertragsähnliches
  Nutzungsverhältnis.
- **Art. 6 Abs. 1 lit. a DSGVO** (Einwilligung): Im Anmeldeformular wird
  explizit eine Datenschutz-Einwilligung abgefragt
  (`privacy_accepted=true`); Pflichtfeld.
- **Transaktions-Mails** (Bestätigung, Approval, Reject, Reset) sind
  notwendiger Bestandteil der Vertragsdurchführung → ebenfalls lit. b.
- **Admin-Benachrichtigungs-Mails** an `role=admin`-Nutzer sind
  berechtigtes Interesse des Verantwortlichen an effizienter
  Workflow-Abwicklung → Art. 6 Abs. 1 lit. f.

**Bewertung:** rechtmäßig. Drei-Schritt-Prüfung der lit. f-Mails
(berechtigtes Interesse — Erforderlichkeit — Abwägung) fällt eindeutig
positiv aus, da die Admin-Empfänger als Funktionsträger handeln.

#### C.2.2 Aggregation und Anzeige öffentlicher Datensätze (B.4 Nr. 4–7)

**Datenquellen-Charakter:** Sämtliche aggregierten Datensätze stammen aus
gesetzlich publizitätspflichtigen Quellen:

| Quelle | Rechtsgrundlage der Quell-Publikation |
|---|---|
| EFRE-Transparenzlisten | Art. 49 Abs. 3 VO (EU) 2021/1060 |
| State-Aid (TAM) | Art. 9 VO (EU) 651/2014 (AGVO) |
| Sanktionslisten | Art. 215 AEUV i. V. m. den einzelnen Sanktions-VOen |

**Bewertung der Re-Aggregation:**

- **State-Aid + Beneficiaries:** Hier ist die Übertragbarkeit der
  North-Data-Doktrin (Art. 6 Abs. 1 lit. f i. V. m. Publizitätspflicht der
  Quelle, vgl. OLG Düsseldorf I-15 U 32/23) **strukturell möglich**, aber
  durch zwei Faktoren geschwächt: (a) der Verantwortliche ist Privatperson
  ohne kommerzielles Substanz-Interesse, (b) die Quell-Publizität dient
  einem **spezifischen** Zweck (Mittelverwendungs-Transparenz, vgl. EuGH
  C-92/09 Schecke/Eifert), der die Re-Aggregations-Schranken enger zieht
  als beim Handelsregister.

  Mit der Iteration-2-Privatisierung (Login-Pflicht, geschlossener
  Workshop-Teilnehmerkreis) wird **Art. 6 Abs. 1 lit. b DSGVO**
  (Vertragsdurchführung) zur primären Rechtsgrundlage, ergänzt um lit. f
  (berechtigtes Interesse an Schulungsmaterial für den geschlossenen
  Teilnehmerkreis). Die Interessenabwägung fällt durch die enge Adressaten-
  schaft positiv aus.

  **Ergebnis:** Verarbeitung in der Post-Iteration-2-Architektur **als
  rechtmäßig zu bewerten**, vorbehaltlich vertraglich klar dokumentierter
  Zweckbindung (Workshop-/Schulungszweck, Verbot kommerzieller Nutzung,
  Verbot Profiling Dritter) in den Nutzungsbedingungen.

- **Sanktionslisten:** Hier liegt eine besondere Datenkategorie nach
  **Art. 9 DSGVO** vor (politische/religiöse/ethnische Zuordnung als
  Sanktionsgrund möglich) und teilweise Art. 10 DSGVO (strafrechtliche
  Verurteilungen, etwa bei Cyber-Sanktionen). Art. 6 allein genügt nicht;
  ein **Erlaubnistatbestand nach Art. 9 Abs. 2 DSGVO** ist erforderlich.

  Verfügbare Tatbestände für Privatpersonen sind eng:
  - **lit. e** („offensichtlich öffentlich gemacht durch die betroffene
    Person") — **nicht einschlägig**, weil die Veröffentlichung durch die
    sanktionsverhängende Stelle erfolgt, nicht durch die betroffene Person
    selbst (h. M., bestätigt etwa in der Stellungnahme des EDPB zum Thema).
  - **lit. g** („erhebliches öffentliches Interesse auf Grundlage von
    Rechtsvorschriften") — bislang in DE für private Aggregatoren nicht
    explizit per Gesetz eröffnet. § 22 BDSG erfasst nur spezifische
    Konstellationen.
  - **lit. f** („Geltendmachung, Ausübung oder Verteidigung von
    Rechtsansprüchen") — auf Schulungs-Demo nicht passend.
  - **GwG-Privileg** — nur für Verpflichtete nach § 2 GwG (Banken, Notare,
    Anwälte, etc.), nicht für Privatpersonen.

  **Ergebnis:** Die Verarbeitung der Sanktionsdaten-Suche durch eine
  Privatperson **bewegt sich auch nach Iteration 2 in einer rechtlichen
  Grauzone**. Die Login-Pflicht entschärft das Risiko erheblich
  (Massenscraping, anonymer Selbst-Lookup, Profiling Dritter sind
  eliminiert), behebt aber den fehlenden Art.-9-Erlaubnistatbestand
  formal-juristisch nicht.

  **Empfehlung:** Eine der drei Varianten umsetzen — (a) Sanctions-Modul
  aus der Plattform entfernen, (b) Sanctions-Modul nur für Nutzer mit
  GwG-Verpflichteten-Status freischalten (Verifikation erforderlich), oder
  (c) ausdrückliche **Einwilligung** des Nutzers in die Verarbeitung
  einholen und stark auf den Schulungs-Demo-Charakter abstellen (Art. 9
  Abs. 2 lit. a). Variante (c) ist die mit dem geringsten Eingriff in das
  bestehende Setup, aber ihre rechtliche Tragfähigkeit ist umstritten,
  weil eine Einwilligung Dritter (der gelisteten Personen) gerade nicht
  vorliegt.

#### C.2.3 Server-Logs (B.4 Nr. 8)

- **Art. 6 Abs. 1 lit. f DSGVO** (IT-Sicherheit, Fehleranalyse).
- IP-Adresse wird gehasht persistiert; TTL ≤ 30 Tage konfiguriert.
- Bewertung: **rechtmäßig**, entspricht etablierter Verwaltungspraxis und
  Empfehlungen der Datenschutzkonferenz (DSK).

#### C.2.4 Karten und Geocoding (B.4 Nr. 9–10)

- OSM-Tiles werden **direkt vom Browser** des Endnutzers von
  `tile.openstreetmap.org` (UK) abgerufen; dabei wird die **Endnutzer-IP**
  an OSMF übermittelt.
- Nominatim-Geocoding läuft serverseitig, daher kein Endnutzerbezug.
- Rechtsgrundlage Endnutzer-Tile-Abruf: **Art. 6 Abs. 1 lit. b DSGVO**
  (Karten-Visualisierung ist Bestandteil der Schulungs-Inhalte) bzw.
  lit. f (berechtigtes Interesse an Visualisierung).
- UK gilt seit Juni 2021 als sicherer Drittstaat (Angemessenheitsbeschluss
  der EU-Kommission). Daher kein Standardvertragsklausel-Erfordernis.
- **Hinweispflicht** in Datenschutzerklärung Abschnitt 8 erfüllt.
- Bewertung: **rechtmäßig**. Optional zur Risikominimierung:
  Opt-in-Banner vor Tile-Abruf oder Self-Hosting der Tiles.

#### C.2.5 Konzernverbund-Lookup (GLEIF/Wikidata)

- Nur **Suchbegriff (Firmenname)** wird übertragen — keine
  personenbezogenen Daten der Nutzer.
- GLEIF API ist öffentlich, Wikidata SPARQL ebenfalls.
- Rechtsgrundlage: nicht erforderlich, da keine personenbezogene
  Verarbeitung beim Drittempfänger.
- Bewertung: **rechtmäßig**.

#### C.2.6 LLM-gestützte Auswertungen

- Lokales Sprachmodell (Ollama auf NUC), **keine Übermittlung an Dritte**.
- Eingaben der Nutzer bleiben in der EU/in eigener Infrastruktur.
- Output wird nicht persistiert (außer kurzfristig in Usage-Logs zu
  Optimierungszwecken).
- Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO (Vertragsdurchführung).
- Bewertung: **rechtmäßig**. Beispielhaft für DSGVO-konforme KI-Nutzung.

### C.3 Besondere Datenkategorien (Art. 9 DSGVO)

Siehe C.2.2 zu Sanktionsdaten — dies ist der einzige Bereich, in dem Art. 9
einschlägig ist. **Empfehlung dort entscheidend.**

Für EFRE- und State-Aid-Datensätze gilt Art. 9 nicht: Förder-Empfang ist
keine besondere Datenkategorie.

### C.4 Strafrechtsbezogene Daten (Art. 10 DSGVO)

Teilweise einschlägig bei **Cyber-Sanktionen** (EU FSF Spezifika).
Verarbeitung durch Privatpersonen ist nur unter sehr engen Voraussetzungen
zulässig (§ 22 BDSG, eng auszulegen).

**Empfehlung:** Diese Daten ebenfalls aus dem Anwendungsbereich entfernen,
sobald das Sanctions-Modul in eine der drei Varianten nach C.2.2 überführt
wird.

### C.5 Informationspflichten (Art. 13 DSGVO)

- **Datenschutzerklärung** unter `/datenschutz`, mit explizitem
  Art.-13-Hinweis am Kopf und Abschnitten zu allen Verarbeitungstätigkeiten.
- **Impressum** unter `/impressum` mit § 5 DDG- und § 18 Abs. 2 MStV-Angaben.
- Footer-Links auf allen authentifizierten Routen (`AppShell.tsx` Z. 35–37).
- Bewertung: **erfüllt**, mit empfohlener Ergänzung um einen kurzen
  Abschnitt zur Drittstaaten-Übermittlung (OSM-Tiles, UK).

### C.6 Betroffenenrechte (Art. 15–22 DSGVO)

- **Auskunft (Art. 15):** Nutzer haben über `/account` Vollzugriff auf alle
  eigenen Account-Daten.
- **Berichtigung (Art. 16):** über `/account` Passwort-Reset; Stammdaten
  können nur über Admin geändert werden (kein Self-Service in Iteration 2 —
  **Schwachstelle**).
- **Löschung (Art. 17):** Über `deleted_at`-Flag im Registration-Modell
  technisch vorgesehen, kein UI-Self-Service — Anfrage muss per Mail an den
  Verantwortlichen gerichtet werden.
- **Einschränkung (Art. 18):** Admin-Endpunkt `/users/{id}/suspend`
  invalidiert Sessions, hält Daten aber vor.
- **Datenübertragbarkeit (Art. 20):** technisch nicht implementiert,
  juristisch relevant nur bei Konto-Daten — Empfehlung: Account-Export-Button.
- **Widerspruch (Art. 21):** in Datenschutzerklärung erwähnt; Annahme über
  E-Mail an Verantwortlichen.
- **Automatisierte Einzelentscheidungen (Art. 22):** keine, da die
  LLM-Ausgaben keine rechtliche Wirkung gegenüber Betroffenen entfalten —
  alle Auswertungen sind beratende Tools für Nutzer.

**Empfehlung:** Self-Service-Löschung im Account-Bereich und
Account-Export-Funktion ergänzen.

### C.7 Datenschutz durch Technik und Voreinstellungen (Art. 25)

Positiv:
- Lokales LLM (kein Anbieter-Transfer).
- Restriktives CORS (`localhost:3000/3004/5173` + `workshop.flowaudit.de`).
- TLS-Pflicht in Produktion (`https://`).
- localStorage nur für funktional notwendige Daten (Token, Rolle,
  Prompt-Drafts) → Art. 25 Abs. 2 TTDSG gedeckt.
- Login-Gating sämtlicher sensibler Routen.
- Keine Tracker, keine Analytics, keine externen CDNs außer (lokal
  gehosteten) Fontsource-Schriften.
- Rate-Limiting auf authentifizierten Endpunkten gegen Bulk-Scraping.

Verbesserungspotenzial:
- IP-Hash der Server-Logs nutzt SHA-256 ohne Pepper — sollte mit
  rotierendem Salt versehen werden, sonst Re-Identifikation möglich.
- Backup-Schlüssel-Rotation ist nicht dokumentiert.

### C.8 Auftragsverarbeitung (Art. 28 DSGVO)

| Auftragsverarbeiter | Vertrag | Status |
|---|---|---|
| Hetzner Online GmbH (Hosting + SMTP) | Standard-AVV | **vorhanden** (Bestandsverhältnis) |
| OpenStreetMap Foundation (Tiles) | Kein AVV | **nicht erforderlich**, da OSMF kein Auftragsverarbeiter im Rechtssinne ist (eigenverantwortliche Bereitstellung) |
| OpenStreetMap Foundation (Nominatim, serverseitig) | Kein AVV | **nicht erforderlich**, da nur Server-IP übermittelt wird |

**Bewertung:** AVV-Lage **konform**, vorausgesetzt der Hetzner-AVV ist
aktuell und schriftlich/digital verfügbar.

### C.9 Verzeichnis von Verarbeitungstätigkeiten (Art. 30 DSGVO)

**Pflicht greift** auch für Privatpersonen, sobald die Verarbeitung
- nicht nur gelegentlich erfolgt (Art. 30 Abs. 5 erste Ausnahme entfällt),
- besondere Datenkategorien betrifft (Sanktionsdaten = Art. 9; **trifft zu**)
- oder ein Risiko für die Rechte und Freiheiten betroffener Personen
  birgt (ebenfalls einschlägig).

**Ergebnis:** Verzeichnis ist **Pflicht**. Dieses Gutachten zusammen mit
COMPLIANCE.md kann als Grundlage dienen; ein formales VVT muss aber
zusätzlich angelegt werden, mindestens mit den in Art. 30 Abs. 1 genannten
Pflichtangaben (Name, Kontakt, Zwecke, Kategorien, Empfänger, Fristen, TOM).

### C.10 Technische und organisatorische Maßnahmen (Art. 32 DSGVO)

Implementiert:
- TLS auf allen produktiven Endpunkten (LetsEncrypt via Caddy/nginx).
- PBKDF2-SHA256 mit 240.000 Iterationen für Passwort-Hashing
  (`backend/routers/auth.py` Z. 93–110).
- HMAC-signierte QR-Login-Token mit gerotierten Secrets.
- Login-Gating mit Status-Prüfung (`pending_approval`, `rejected`,
  `suspended`).
- Worker-Token getrennt von Nutzer-Sessions.
- Audit-Log (`SecurityAuditLog`) für Auth-/Admin-Aktionen.
- age-verschlüsselte Backups.
- pgvector-Index nicht öffentlich exponiert; nur über Backend-API.

Empfehlungen:
- **HSTS-Header** + **CSP** in nginx-Config setzen (falls noch nicht).
- **Backup-Restore-Test** mindestens jährlich dokumentieren.
- **Penetrationstest** vor erster Workshop-Durchführung in Produktion.
- Notfall-Plan (Art. 33-Meldepflicht binnen 72 h) schriftlich fixieren.

### C.11 Datenschutz-Folgenabschätzung (Art. 35 DSGVO)

**Pflicht greift**, wenn die Verarbeitung „voraussichtlich ein hohes Risiko
für die Rechte und Freiheiten natürlicher Personen zur Folge hat". Indizien
nach Art. 35 Abs. 3 und der DSK-Liste:

- Verarbeitung **besonderer Datenkategorien in großem Umfang** (Sanktions-
  daten ja, → trifft zu, solange Sanctions-Modul aktiv)
- **systematische Bewertung** persönlicher Aspekte (Fuzzy-Match-Suche +
  Cross-Register-Audit-Bericht haben Profiling-Charakter, auch wenn keine
  automatisierte Einzelentscheidung getroffen wird)
- **innovative Technologien** (LLM-Pipeline) → empfohlen, nicht zwingend
- **Datenverarbeitung über Personen, die ihre Zustimmung nicht erteilt
  haben** (Begünstigte, Geschäftsführer in State-Aid-Daten) → trifft zu

**Ergebnis:** DSFA-Pflicht ist **gegeben**, **insbesondere für das
Sanctions-Modul**. Ein DSFA-Volldokument liegt nicht vor; dieses Gutachten
liefert die strukturierte Vorarbeit, ersetzt die DSFA aber nicht.

**Dringende Empfehlung:** Vor produktiver Aktivierung des Sanctions-Moduls
eine formale DSFA durchführen (eigene Anstrengung + Anwaltsprüfung). Bis
dahin: Sanctions-Modul nur in Demo-/Schulungs-Sessions mit klarer Belehrung
nutzen.

### C.12 Datenschutzbeauftragter (Art. 37 DSGVO)

- Pflicht greift nicht automatisch (Art. 37 Abs. 1 lit. c verlangt
  „Kerntätigkeit" mit umfangreicher Verarbeitung besonderer Kategorien).
- Workshop-Plattform ist **Nebentätigkeit**, nicht Kerntätigkeit der
  Privatperson.
- **DSB-Pflicht: nein.** Freiwillige Bestellung möglich und bei Aktivierung
  des Sanctions-Moduls dringend zu erwägen.

### C.13 Meldepflichten bei Datenpannen (Art. 33, 34 DSGVO)

- Verantwortlicher muss binnen 72 h an die zuständige Aufsichtsbehörde
  melden (HBDI für Hessen, da Sitz Eppstein).
- Bei hohem Risiko zusätzlich Information der Betroffenen.
- Aktuell **kein dokumentierter Meldeprozess** — sollte schriftlich
  fixiert werden.

### C.14 Dienstrechtliche Aspekte (außerhalb DSGVO, aber risiko-relevant)

Da der Betreiber Bedienstet der hessischen Verwaltung ist und die Plattform
thematisch nahe an der dienstlichen Prüfaufgabe (EFRE-Prüfbehörde) liegt:

- **Genehmigungspflichtige Nebentätigkeit** nach § 73 HBG / TV-H ist zu
  beantragen, falls nicht bereits erfolgt.
- **Interessenkonflikt-Erklärung** gegenüber dem Dienstherrn empfohlen.
- Strikte Trennung dienstlicher und privater Datenbestände sicherstellen.

Diese Punkte sind nicht DSGVO-relevant, gehören aber zur Gesamtrisiko-
Würdigung.

---

## D. Risiko-Analyse und Restrisiken

Bewertung nach **Wahrscheinlichkeit × Schwere** in Anlehnung an die
DSFA-Methodik der DSK.

| # | Restrisiko | Wahrscheinlichkeit | Schwere | Brutto-Risiko | Mitigation Iteration 2 | Netto-Risiko |
|---|---|---|---|---|---|---|
| R1 | Sanctions-Modul ohne tragfähige Art.-9-Grundlage | hoch | hoch | **rot** | Login-Gating, Rate-Limit | **gelb** (formal-juristisch ungelöst) |
| R2 | Re-Aggregation EFRE/State-Aid für Schulung | mittel | mittel | gelb | Login-Gating + lit. b/f | grün |
| R3 | OSM-Tile-Abruf überträgt Endnutzer-IP nach UK | hoch | niedrig | gelb | Hinweis in Datenschutz | grün (UK = sicherer Drittstaat) |
| R4 | Nominatim-Übermittlung der Suchbegriffe | mittel | niedrig | gelb | Server-seitig, Cache-Mitigation | grün |
| R5 | Anwaltliche Prüfung fehlt | hoch | mittel | gelb | Selbsteinschätzung vorhanden | gelb (Anwaltsbesuch ausstehend) |
| R6 | DSFA für Sanctions fehlt | hoch | hoch | **rot** | dieses Gutachten als Vorarbeit | gelb (Volldokument ausstehend) |
| R7 | Dienstrechtliche Anzeige der Nebentätigkeit | mittel | mittel | gelb | außerhalb Code-Scope | gelb (organisatorisch zu erledigen) |
| R8 | Datenpanne-Meldeprozess nicht dokumentiert | niedrig | mittel | grün | — | gelb (schriftlich fixieren) |
| R9 | Re-Identifizierung über IP-Hash ohne Pepper | niedrig | niedrig | grün | — | grün |
| R10 | Sicherheits-Audit (Pentest) fehlt | mittel | mittel | gelb | — | gelb (vor Workshop nachholen) |
| R11 | Self-Service-Löschung für Nutzer fehlt | niedrig | niedrig | grün | Admin-Workflow vorhanden | grün |

**Ergebnis:** **Zwei rote bzw. abgemilderte rote Restrisiken (R1, R6)** —
beide knüpfen am Sanctions-Modul an. Solange das Sanctions-Modul aktiv ist
**und** noch keine DSFA + Anwaltsfreigabe vorliegt, ist die produktive
Aktivierung der Plattform **risikobehaftet**.

---

## E. Ergebnis (zusammenfassende Würdigung)

1. **Die DSGVO findet auf die Plattform vollumfänglich Anwendung.** Die
   Haushaltsausnahme greift nicht.

2. **Mit Iteration 2 (Login-Gating + Mail-Layer + Rechtsgrundlagen-
   Umstellung)** ist die Plattform für die Verarbeitungstätigkeiten Nr.
   1–11 (B.4) **bei Beachtung der Empfehlungen aus Abschnitt F als
   datenschutzrechtlich verteidigungsfähig zu bewerten**.

3. **Das Sanctions-Modul bleibt der zentrale juristische Risikoherd.**
   Auch nach Iteration 2 fehlt eine tragfähige Rechtsgrundlage nach Art. 9
   Abs. 2 DSGVO. Hier ist eine bewusste, dokumentierte Entscheidung des
   Verantwortlichen zwingend (siehe F.1).

4. **Pflichten im Hintergrund** (formales VVT nach Art. 30, DSFA nach
   Art. 35, schriftliche TOM-Dokumentation nach Art. 32) sind teilweise
   unerfüllt und müssen vor produktivem Betrieb nachgezogen werden.

5. **Die Plattform ist nicht „verboten" zu betreiben**, sondern lebt vom
   Zusammenspiel der getroffenen Maßnahmen. Das Risiko liegt im
   unentdeckten Versäumnis einzelner Pflichten, weniger in der
   grundsätzlichen Konzeption.

---

## F. Handlungsempfehlungen (priorisiert)

### F.1 Vor produktiver Aktivierung — kritisch

- [ ] **Entscheidung Sanctions-Modul:**
  - Variante A: Modul **entfernen** (chirurgischer Eingriff, Code bleibt
    erhalten, Routing deaktiviert).
  - Variante B: Modul nur für Nutzer mit **dokumentiertem
    GwG-Verpflichteten-Status** freischalten (zweite Status-Stufe im
    Registration-Modell).
  - Variante C: **explizite Einwilligung** nach Art. 9 Abs. 2 lit. a in
    Anmelde-Workflow integrieren mit klarer Belehrung über den
    Demo-Charakter.
- [ ] **Anwaltsprüfung** dieses Gutachtens und der gewählten Variante (1–2 h
  bei DSGVO-spezialisiertem Anwalt, ca. 300–800 €).
- [ ] **DSFA-Volldokument** anlegen, insbesondere für das Sanctions-Modul
  falls dieses aktiv bleibt.
- [ ] **Nebentätigkeits-Anzeige** beim Dienstherrn (organisatorisch).

### F.2 Vor produktiver Aktivierung — wichtig

- [ ] **Verzeichnis von Verarbeitungstätigkeiten (Art. 30)** als eigenes
  Dokument anlegen (`auditworkshop/VVT.md` oder Online-Tool wie Otris/proIVE).
- [ ] **TOM-Dokumentation** schriftlich fixieren (kann sich auf
  COMPLIANCE.md und Hetzner-AVV stützen).
- [ ] **Datenpanne-Meldeprozess** schriftlich definieren (Trigger,
  Eskalations-Pfad, HBDI-Kontakt).
- [ ] **HSTS + CSP-Header** in nginx-Config setzen.
- [ ] **Pentest** oder zumindest automatisierter Security-Scan (z. B.
  OWASP ZAP) vor erstem Live-Workshop.
- [ ] **Datenschutzerklärung** ergänzen:
  - Klarer Hinweis auf Drittstaaten-Übermittlung (OSM-Tiles, UK +
    Angemessenheitsbeschluss).
  - Hinweis auf das fehlende DSB-Erfordernis und die freiwillige
    Selbsteinschätzung.

### F.3 Mittelfristig (vor zweitem Workshop-Zyklus)

- [ ] **Self-Service-Löschung** im `/account`-Bereich implementieren.
- [ ] **Account-Daten-Export** als ZIP/JSON-Download (Art. 20-konform).
- [ ] **IP-Hash mit Pepper** + Pepper-Rotation alle 90 Tage.
- [ ] **Backup-Restore-Test** mindestens jährlich, dokumentiert.
- [ ] **Audit-Wiederholung** dieses Gutachtens bei jeder substantiellen
  Architekturänderung.

### F.4 Periodisch

- [ ] **Halbjährliches Compliance-Review** (Code, Quellen-Lizenzen,
  Hetzner-AVV-Stand, DSK-Beschlüsse).
- [ ] **Update des Stands** in `DatenschutzPage.tsx` (`Stand: …`) bei jeder
  Änderung.

---

## G. Vorbehalte und ausdrückliche Grenzen dieses Gutachtens

1. **Kein Anwaltsgutachten:** Dieses Dokument ist eine technische und
   strukturelle Selbsteinschätzung. Es erteilt keine Rechtsberatung und
   kann eine solche nicht ersetzen. Für rechtsverbindliche Aussagen ist
   ein zugelassener Anwalt mit DSGVO-Schwerpunkt zu konsultieren.

2. **Keine vollständige DSFA:** Die DSFA nach Art. 35 DSGVO ist ein
   eigenständiges Dokument mit formalen Anforderungen (Beschreibung,
   Bewertung der Notwendigkeit und Verhältnismäßigkeit, Risikobewertung
   für die Rechte und Freiheiten der Betroffenen, Abhilfemaßnahmen). Sie
   ist noch nicht erstellt.

3. **Stichtag-Bezug:** Die Bewertung bezieht sich auf den Stand
   `claude/add-legal-compliance-QGM6a@a660525` (Mai 2026). Spätere
   Code-Änderungen können die Bewertung verschieben.

4. **Rechtsprechungs-Bezug:** Die zitierten EuGH-/BGH-/OLG-Entscheidungen
   spiegeln den Stand Mai 2026 wider. Neuere Entscheidungen wurden nicht
   berücksichtigt.

5. **Eigene Befangenheit:** Verfasser dieses Gutachtens ist der Betreiber
   selbst — eine externe unabhängige Begutachtung kann zu abweichenden
   Bewertungen kommen.

6. **Open Source und Quell-Lizenzen:** Die Lizenzkonformität der externen
   Quellen (OpenSanctions, OSM/Nominatim, TAM-Nutzungsbedingungen,
   Wikidata/GLEIF) ist nicht Gegenstand dieses Gutachtens. Sie ist
   separat zu prüfen.

---

## Anhang — Referenzierte Rechtsprechung und Normen

- **DSGVO** (VO (EU) 2016/679): Art. 2, 4, 5, 6, 9, 10, 13, 15–22, 25,
  28, 30, 32, 33, 34, 35, 37
- **BDSG (Stand 2024)**: § 22, § 26
- **DDG**: § 5
- **MStV**: § 18 Abs. 2
- **TTDSG**: § 25 Abs. 2
- **HBG**: § 73 (Nebentätigkeit)
- **EuGH C-101/01** Lindqvist (6.11.2003) — Haushaltsausnahme
- **EuGH C-92/09 + C-93/09** Schecke/Eifert (9.11.2010) —
  EFRE-Transparenz-Grenzen
- **EuGH C-212/13** Ryneš (11.12.2014) — Haushaltsausnahme
- **EuGH C-398/15** Manni (9.3.2017) — Handelsregister-Publizität
- **EuGH C-345/17** Buivids (14.2.2019) — Haushaltsausnahme
- **EuGH C-203/22** CK/Magistrat Wien (2024) — Auskunfts-Anforderungen
- **EuGH C-621/22** KNLTB (2024) — lit. f-Interessenabwägung
- **OLG Düsseldorf I-15 U 32/23** (27.7.2023) — North-Data-Aggregator
- **BGH VI ZR 64/23** (19.3.2024) — Companyhouse / Wirtschaftsauskunfteien
- **VO (EU) 2021/1060** Art. 49 — EFRE-Transparenzpflicht
- **VO (EU) 651/2014** Art. 9 — State-Aid-Transparenzpflicht
- **Angemessenheitsbeschluss UK** (28.6.2021, VO (EU) 2021/1772)

---

*Ende des Datenschutzgutachtens.*
