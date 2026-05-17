# Compliance — Auditworkshop

Dokumentation des Standes der rechtlichen Implementierungen und der Ergebnisse
des technischen DSGVO-Audits. Diese Datei ist die zentrale Anlaufstelle für
Compliance-Fragen rund um die Plattform.

Stand: Mai 2026

---

## 1. Aktueller Stand der rechtlichen Implementierungen

### 1.1 Impressum

- **Quelle:** `frontend/src/pages/ImpressumPage.tsx`
- **Routing:** öffentliche Route `/impressum` in `frontend/src/App.tsx` (Z. 73)
- **Footer-Link:** `frontend/src/components/layout/AppShell.tsx` (Z. 35–37)
- **Rechtsgrundlagen:**
  - Angaben gemäß **§ 5 DDG** (Digitale-Dienste-Gesetz, ersetzt seit Mai 2024 das
    TMG)
  - Verantwortlich für den Inhalt nach **§ 18 Abs. 2 MStV**
    (Medienstaatsvertrag)
- **Inhaltliche Abschnitte:** Angaben, Zweck des Angebots, Datenquellen, Haftung
  für Inhalte, Hinweis auf KI-gestützte Auswertungen, Haftung für externe Links,
  Urheberrecht, MStV-Verantwortlichkeit, Verweis auf Datenschutzerklärung.

### 1.2 Datenschutzerklärung

- **Quelle:** `frontend/src/pages/DatenschutzPage.tsx`
- **Routing:** öffentliche Route `/datenschutz` in `frontend/src/App.tsx` (Z. 74)
- **Footer-Link:** `frontend/src/components/layout/AppShell.tsx` (Z. 35–37)
- **Rechtsgrundlagen (explizit benannt):**
  - **Art. 13 DSGVO** als übergeordnete Informationspflicht (Kopfhinweis)
  - **Art. 6 Abs. 1 lit. f DSGVO** — berechtigtes Interesse (Server-Logs,
    Suchanfragen)
  - **Art. 6 Abs. 1 lit. b DSGVO** — Vertragsdurchführung (Registrierung)
  - **Art. 6 Abs. 1 lit. a DSGVO** — Einwilligung (Registrierung)
  - **Art. 6 Abs. 1 lit. b und f DSGVO** — Workshop-Teilnahmevertrag bzw.
    berechtigtes Interesse an Schulungsmaterial für den geschlossenen
    Teilnehmerkreis (Aggregation öffentlicher Quellen; vormals lit. e + Art. 85,
    seit Iteration 2 umgestellt — siehe Abschnitt 4)
  - **Art. 25 Abs. 2 TTDSG** — technisch erforderlicher localStorage
  - **Art. 28 DSGVO** — Auftragsverarbeitungsvertrag mit Hetzner Online GmbH
    (Standort Falkenstein/Frankfurt, Deutschland)
- **Inhaltliche Abschnitte (1–12):** Verantwortlicher, Hosting/Logfiles,
  funktionale Speicherung im Browser, Registrierung, **Eingaben in Suchfelder**,
  Aggregation öffentlicher Datenquellen, KI-gestützte Auswertungen, Karten und
  Geokodierung, Backups, Rechte der Betroffenen, Beschwerderecht, Änderungen.

---

## 2. Ergebnisse des technischen DSGVO-Audits

Stichtag: Mai 2026, Branch `claude/add-legal-compliance-QGM6a`.

### 2.1 Risikobefunde

| # | Befund | Datei / Stelle | Bewertung | Empfohlene Maßnahme |
|---|---|---|---|---|
| 1 | ~~Google Fonts (Fraunces, IBM Plex Sans) werden direkt vom Google-CDN geladen~~ — **behoben** mit Commit, der Fontsource-Pakete (`@fontsource-variable/fraunces`, `@fontsource/ibm-plex-sans`) lokal hostet | `frontend/src/main.tsx`, `frontend/index.html` | **erledigt** | — |
| 2 | OpenStreetMap-Tiles werden vom Browser direkt abgerufen | `frontend/src/components/workshop/BeneficiaryMap.tsx`, `frontend/src/components/state_aid/StateAidMap.tsx` | **niedrig** — Endnutzer-IP an `tile.openstreetmap.org`; in Datenschutzerklärung Abschnitt 8 transparent gemacht | Falls erforderlich: Opt-in-Banner vor Map-Anzeige oder lokaler Tile-Proxy |
| 3 | Geocoding via Nominatim | `backend/services/geocoding_service.py:837` | **niedrig** — Server-IP an Nominatim, **kein** Endnutzerbezug; Cache mit 3.177 Einträgen mildert | Bestehender Cache reicht aus; `ALLOW_REMOTE_GEOCODING` bewusst konfigurieren |
| 4 | `localStorage` für Auth-Token (`workshop_token`) und Rolle (`workshop_role`) | `frontend/src/App.tsx` | **funktional erforderlich** — durch Art. 25 Abs. 2 TTDSG gedeckt | Sicherstellen, dass Logout den Token entfernt (bereits implementiert) |
| 5 | `localStorage` für Prompt-Drafts in Szenarien | `frontend/src/pages/ScenarioPage.tsx` | **niedrig** — nur Klartext-Drafts des Nutzers, keine Drittdaten | Hinweis in der UI (z. B. „Entwurf wird lokal gespeichert") prüfen |
| 6 | Backend-Access-Log TTL | `backend/main.py:56` (`WORKSHOP_ACCESS_LOG_TTL_DAYS`) | **prüfen** — TTL sollte ≤ 30 Tage liegen (Datenschutz-Best-Practice) | Wert in der Produktiv-Konfiguration (`/etc/auditworkshop/env`) auf ≤ 30 stellen |

### 2.2 Positivbefunde (kein Risiko)

- **Keine Tracker, keine Analytics, keine externen CDNs** außer Google Fonts —
  insbesondere kein Google Analytics, Matomo, Plausible, Sentry, Hotjar oder
  Tag-Manager im Code gefunden.
- **Keine Speicherung von Suchbegriffen** im Frontend: CompanySearchPage,
  KnowledgePage und BeneficiariesPage halten Sucheingaben nur in flüchtigem
  `useState`, schreiben sie nicht in Local/Session-Storage oder Cookies.
- **Restriktives CORS:** Nur `localhost:3000`, `localhost:3004`,
  `localhost:5173` und `https://workshop.flowaudit.de` in
  `backend/main.py` als `allow_origins` zugelassen.
- **EU-Hosting:** Hetzner Online GmbH, Standort Falkenstein/Frankfurt,
  Deutschland. Auftragsverarbeitungsvertrag nach Art. 28 DSGVO geschlossen
  (siehe DatenschutzPage Abschnitt 2).
- **Lokales LLM:** Inferenz erfolgt ausschließlich auf eigener Infrastruktur
  (Ollama auf NUC / CCX23). Keine Datenübermittlung an externe LLM-Anbieter
  (OpenAI, Anthropic, Google).
- **Verschlüsselte Backups:** age-Verschlüsselung; externe Anbieter sehen
  ausschließlich Cipher-Text (DatenschutzPage Abschnitt 9).

---

## 3. Checkliste

Operative Aufgaben, die außerhalb des Codes (organisatorisch, vertraglich,
dienstrechtlich) erledigt werden müssen oder periodisch zu prüfen sind:

- [ ] Vertrag zur Auftragsverarbeitung (AVV) mit der Hetzner Online GmbH
  digital prüfen und ablegen (Art. 28 DSGVO).
- [ ] **Dienstrechtliche Nebentätigkeitsanzeige** beim Dienstherrn einreichen
  (Betrieb der Plattform als private Nebentätigkeit).
- [x] ~~Google Fonts in `frontend/index.html` Z. 9–11 lokal hosten oder durch
  Systemschriftarten ersetzen (Audit-Befund #1).~~ Umgesetzt durch
  Fontsource-Pakete; `index.html` enthält keine externen Font-Referenzen mehr.
- [ ] `WORKSHOP_ACCESS_LOG_TTL_DAYS` in der Produktiv-Konfiguration prüfen
  und auf ≤ 30 Tage setzen (Audit-Befund #6).
- [ ] Bei den OSM-Map-Komponenten klären, ob ein Opt-in-Banner oder ein lokaler
  Tile-Proxy benötigt wird (Audit-Befund #2).
- [ ] Sicherstellen, dass die Footer-Links zu Impressum und Datenschutz auch
  auf den öffentlichen Routen (`/agenda`, `/register`, `/login`) gut erreichbar
  sind — aktuell sind sie nur über `AppShell` eingebaut.
- [ ] Bei jeder substanziellen Änderung an Verarbeitungstätigkeiten das
  Stand-Datum in `DatenschutzPage.tsx` (Z. 42) und in dieser Datei aktualisieren.
- [ ] Periodische Wiederholung des Code-Audits — empfohlen halbjährlich oder
  bei größeren Frontend-/Backend-Releases.
- [ ] Platzhalter im Impressum prüfen, sobald sich die Anschrift, der
  Verantwortliche oder die E-Mail-Adresse ändert (`ImpressumPage.tsx`).

---

## 4. Iteration 2 — Privatisierung sensibler Routen + Mail-Versand

Stichtag: Mai 2026. Adressiert die materiellen Compliance-Risiken (Sanktions-
daten, Begünstigtenverzeichnis, State-Aid-Register), die formal von Iteration 1
unberührt waren.

### 4.1 Login-Gating sensibler Routen (Option A)

Sämtliche Datenrouten, die personenbezogene oder personenbeziehbare Daten
liefern, sind nicht mehr anonym aufrufbar:

| Modul | Endpunkte | Schutz |
|---|---|---|
| Sanctions | `GET /api/sanctions/lists`, `/sources`, `/method`, `/stats`, `/search`, `/export` | `Depends(require_session)` (`backend/routers/sanctions.py`) |
| Beneficiaries | `GET /api/beneficiaries/countries`, `/sources`, `/map`, `/search`, `/analytics`, `/nuts`, `/nuts-geojson`, `/choropleth`, `/export` | `Depends(require_session)` (`backend/routers/beneficiaries.py`) |
| State-Aid | `GET /status`, `/sources`, `/search`, `/award/{id}`, `/map`, `/stats`, `/stats/export`, `/company-dossier`, `/export`, `/corporate-group`, `/audit-report`; `POST /ask`, `/audit-report/pdf` | `Depends(require_session)` (`backend/routers/state_aid.py`) |

Frontend (`frontend/src/App.tsx`): Der bisherige `!authToken`-Block
(öffentliche `PublicShell`-Routen für `/scenario/6`, `/begünstigte`,
`/sanktionslisten`, `/beihilfen`, `/audit-report`) wurde entfernt. Nicht
authentifizierte Aufrufe landen über den Catch-all `*` auf der `LoginPage`.
Die ungenutzte `PublicShell.tsx` wurde gelöscht.

`/api/state-aid/validation/last` bleibt bewusst offen — es liefert nur einen
JSON-Status (Anzahl Findings, keine personenbezogenen Daten) und wird vom UI
für ein Status-Banner gepollt.

### 4.2 Rechtsgrundlagen-Umstellung

Die Datenschutzerklärung (`frontend/src/pages/DatenschutzPage.tsx`,
Abschnitt 6) stützt sich nicht mehr auf Art. 6 Abs. 1 lit. e + Art. 85 DSGVO,
sondern auf:

- **Art. 6 Abs. 1 lit. b DSGVO** — Durchführung des Workshop-Teilnahmevertrags
  gegenüber angemeldeten Nutzern
- **Art. 6 Abs. 1 lit. f DSGVO** — berechtigtes Interesse an der Bereitstellung
  von Schulungsmaterial für einen geschlossenen Teilnehmerkreis

Die Begründung „Demonstrations- und Schulungszweck im öffentlichen Interesse"
ist juristisch ehrlicher nicht mehr haltbar (lit. e setzt hoheitliche Befugnis
voraus, Art. 85 setzt redaktionell-journalistische Tätigkeit voraus — beides
für eine Privatperson nicht gegeben).

### 4.3 Rate-Limiting auf authentifizierten Endpunkten

`backend/routers/state_aid.py` (`_RATE_LIMIT_WINDOWS`):

| Bucket | Limit | Begründung |
|---|---|---|
| `ask` | 6 / 60 s | Bereits vorhanden; zwei LLM-Calls pro Request |
| `search` | 60 / 60 s | Bereits vorhanden |
| `export` | 10 / 60 s | Neu — schützt vor Bulk-Scraping durch authentifizierte Sessions |
| `audit-report` | 10 / 60 s | Neu — schützt LLM-/PDF-Render-Last bei Cross-Register-Bericht |

Aktiv genutzt im State-Aid-Modul. Sanctions- und Beneficiaries-Exporte sind
durch `require_session` ohnehin nicht mehr anonym verfügbar; ein erweiterter
Rate-Limiter dafür ist ein separater Schritt (würde Auslagern von
`_check_rate_limit` in ein gemeinsames Service-Modul erfordern).

### 4.4 Benutzer-Freischaltung durch Admin + Transaktions-Mails

Das User-Modell (`backend/models/registration.py`) und der Login-Flow
(`backend/routers/auth.py`) implementieren bereits einen Approval-Workflow:
Selbstregistrierung → `status='pending_approval'` → Admin schaltet frei
(`POST /api/auth/users/{id}/approve`) → `status='active'` → Login möglich.
Iteration 2 ergänzt dazu den **automatisierten E-Mail-Versand** über einen
neuen Service `backend/services/mail_service.py` (stdlib `smtplib`, kein neues
Drittpaket).

| Auslöser | Empfänger | Funktion |
|---|---|---|
| `POST /signup` | Neuer Nutzer | `send_signup_confirmation` — Eingangsbestätigung mit Hinweis auf ausstehende Freischaltung |
| `POST /signup` | Alle `role=admin` Nutzer | `send_admin_new_signup` — Liste der Registrierungsdaten + Link auf `/admin` |
| `POST /users/{id}/approve` | Betroffener Nutzer | `send_approval_notification` — Freischaltungs-Bestätigung |
| `POST /users/{id}/reject` | Betroffener Nutzer | `send_rejection_notification` — Absage inkl. optionaler Begründung |
| `POST /users/{id}/reset-token` | Betroffener Nutzer | `send_setup_link` — Setup-/Reset-Link mit 24 h Gültigkeit |

Konfiguration (`backend/config.py`, Env-Vars in `/etc/auditworkshop/env`):

| Variable | Default | Bemerkung |
|---|---|---|
| `MAIL_ENABLED` | `true` | `false` unterdrückt sämtlichen Versand (Tests/Dev) |
| `SMTP_HOST` | `mail.your-server.de` | Hetzner-Postfach |
| `SMTP_PORT` | `465` | SSL implizit, alternativ `587` mit `SMTP_STARTTLS=true` |
| `SMTP_USER` | `""` | Hetzner-Postfach-Adresse |
| `SMTP_PASSWORD` | `""` | Hetzner-Postfach-Passwort |
| `SMTP_USE_SSL` | `true` | Bei Port 465 |
| `SMTP_STARTTLS` | `false` | Bei Port 587 auf `true` |
| `SMTP_TIMEOUT` | `20` | Sekunden |
| `MAIL_FROM` | `""` | Absender-Adresse; falls leer wird `SMTP_USER` verwendet |
| `MAIL_FROM_NAME` | `FlowAudit Workshop` | Anzeigename im `From:`-Header |
| `PUBLIC_BASE_URL` | `https://workshop.flowaudit.de` | Wird in Mail-Links eingesetzt |

Fehler beim Versand werden protokolliert, blockieren aber niemals die
aufrufenden API-Endpunkte (Mail ist additive Information, nicht
transaktionskritisch).

### 4.5 Datenschutz-rechtliche Implikationen

- **Empfänger der Mail** sind ausschließlich registrierte Nutzer (Eigenadresse)
  bzw. Admins (Funktionsadressen). Keine externen Empfänger.
- **Übermittlung** an Hetzner Online GmbH (gleicher AVV-Vertrag wie das
  bestehende Hosting). EU-Standort, keine Drittstaaten-Übermittlung.
- **Inhalte** der Mails enthalten Namen, E-Mail-Adresse, Organisation und
  optional die Registrierungs-Begründung des neuen Nutzers (Admin-Benachr.).
  Keine besonderen Kategorien (Art. 9), keine Sanktions-/Audit-Inhalte.
- **Rechtsgrundlagen:** Bestätigungs- und Status-Mails an den Nutzer beruhen
  auf Art. 6 Abs. 1 lit. b DSGVO (Vertragsdurchführung). Admin-Benachrichtigung
  beruht auf Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse an der
  Abwicklung der Anmelde-Workflows).

### 4.6 Offene Punkte aus Iteration 2

- [ ] DSFA-Skeleton anlegen (`auditworkshop/DSFA.md`) — vorläufige
  Selbsteinschätzung, vor produktiver Nutzung von einem Datenschutzbeauftragten
  finalisieren lassen.
- [x] ~~Datenschutzerklärung um einen kurzen Abschnitt zum Versand von
  Transaktionsmails (Bestätigung, Approval, Reset) ergänzen.~~ Umgesetzt in
  `DatenschutzPage.tsx` Abschnitt 4.
- [ ] SMTP-Zugang (Postfach + Passwort) auf Hetzner einrichten und in
  `/etc/auditworkshop/env` hinterlegen, dann ersten End-to-End-Test laufen
  lassen.
- [ ] Anpassen des Smoke-Tests (`scripts/workshop_smoke.sh`): bisher öffentlich
  geprüfte Endpunkte (Sanctions/Beneficiaries/State-Aid) brauchen jetzt einen
  Token oder müssen mit erwartetem 401-Status laufen.
- [ ] Periodische Wiederholung des Code-Audits in 6 Monaten.
