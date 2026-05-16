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
  - **Art. 6 Abs. 1 lit. e und f DSGVO i. V. m. Art. 85 DSGVO** — öffentliches
    Interesse / Demonstrationszweck (Aggregation öffentlicher Quellen)
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
| 1 | Google Fonts (Fraunces, IBM Plex Sans) werden direkt vom Google-CDN geladen | `frontend/index.html` Z. 9–11 | **mittel** — IP-Adresse des Endnutzers wird an Google übertragen | Schriftarten lokal hosten (WOFF2 unter `frontend/public/fonts/`, `@font-face` in `index.css`) oder durch Systemschriftarten ersetzen |
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
- [ ] Google Fonts in `frontend/index.html` Z. 9–11 lokal hosten oder durch
  Systemschriftarten ersetzen (Audit-Befund #1).
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
