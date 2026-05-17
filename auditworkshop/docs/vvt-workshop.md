# Verzeichnis von Verarbeitungstätigkeiten (Art. 30 Abs. 1 DSGVO)

**Schulungs- und Demonstrationsplattform „Prüferworkshop EFRE Hessen 2026"**

| Feld | Angabe |
|------|--------|
| Verantwortlicher | Jan Riener, Am Vogelgesang 20, 65817 Eppstein, jan.riener@vwvg.de |
| Datenschutzbeauftragter | (sofern bestellt — sonst „nicht bestellt, da Voraussetzungen nach Art. 37 DSGVO nicht erfüllt") |
| Erstellt am | 2026-05-17 |
| Letzte Aktualisierung | 2026-05-17 |

## A — Anmeldung und Teilnehmerverwaltung

| Feld | Angabe |
|------|--------|
| Zweck | Organisation des dreitägigen Workshops, Zugangskontrolle zur Plattform, Versand der Bestätigungs- und Erinnerungs-Mails |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. b DSGVO (Workshop-Anmeldung als vertragsähnliches Schuldverhältnis), Art. 6 Abs. 1 lit. a DSGVO (Einwilligung in optionale Felder und KI-Personalisierung) |
| Kategorien Betroffener | Angemeldete Teilnehmerinnen und Teilnehmer (Prüferinnen/Prüfer der Hessischen Prüfbehörde EFRE und eingeladener Schwesterbehörden) |
| Datenkategorien | Vor- und Nachname, dienstliche E-Mail-Adresse, Organisation, optional: Fachbereich, Themenvorschlag, dienstliche Rolle, Bundesland |
| Empfänger | Hetzner Online GmbH (Hosting), 1&1 IONOS SE (Mail-Transport) |
| Drittlandsübermittlung | Keine |
| Löschfrist | Spätestens 6 Monate nach Workshop-Ende (Stichtag 07.11.2026) |
| TOMs | TLS-Verschlüsselung, Zugangsbeschränkung über Sitzungstoken, AVV nach Art. 28 mit Hetzner und IONOS, verschlüsselte Backups |

## B — Vorab-Upload von Dokumenten durch Teilnehmer

| Feld | Angabe |
|------|--------|
| Zweck | Workshop-Demonstration mit konkretem Material der Teilnehmenden (Förderbescheide, Prüfberichte, Auszüge) |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. b DSGVO (Vertragsdurchführung Workshop-Teilnahme), Art. 6 Abs. 1 lit. a DSGVO (Einwilligung im Anmeldeformular) |
| Kategorien Betroffener | Teilnehmende selbst; Begünstigte/Dritte nur, soweit Teilnehmende sie trotz ausdrücklichen Hinweises nicht anonymisieren |
| Datenkategorien | PDF-/DOCX-Inhalte (max. 10 MB je Datei, max. 200 MB pro Teilnehmer), abgeleitete Vektor-Embeddings und OCR-Text |
| Empfänger | Hetzner (Speicherung), eigene Inferenz-Hardware in Eppstein (OCR/Embedding) |
| Drittlandsübermittlung | Keine (Tailscale-Mesh nur als verschlüsselte Transportstrecke zwischen eigenen Systemen) |
| Löschfrist | Auf Wunsch des Teilnehmers jederzeit; spätestens 6 Monate nach Workshop-Ende |
| TOMs | Datei-Größen- und Format-Validierung serverseitig, Quota-Limits pro Konto, ausdrücklicher Hinweis im Upload-Schritt „keine personenbezogenen Daten Dritter" |

## C — Themen- und Forenbeiträge

| Feld | Angabe |
|------|--------|
| Zweck | Strukturierte fachliche Diskussion vor und während des Workshops |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. b DSGVO (Workshop-Teilnahme), Art. 6 Abs. 1 lit. a DSGVO (Einwilligung zur Sichtbarkeit „öffentlich" vs. „nur Moderation") |
| Kategorien Betroffener | Teilnehmende, die Beiträge verfassen |
| Datenkategorien | Beitragstext, Themenvorschlag, Organisation (optional anonymisierbar), Zeitstempel |
| Empfänger | Sichtbar für andere Teilnehmende (bei Visibility „public") bzw. nur für Moderation |
| Drittlandsübermittlung | Keine |
| Löschfrist | Spätestens 6 Monate nach Workshop-Ende; auf Wunsch des Verfassers jederzeit |
| TOMs | Sichtbarkeitssteuerung pro Beitrag, Moderationsrecht, Löschanspruch pro Beitrag |

## D — KI-Auswertung (LLM, Embedding, OCR, Re-Ranking)

| Feld | Angabe |
|------|--------|
| Zweck | Demonstration KI-gestützter Auswertungs- und Risikoanalyseverfahren in der Verwaltungskontrolle |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. b DSGVO (Vertragsdurchführung Workshop), zusätzlich Art. 6 Abs. 1 lit. a DSGVO für KI-personalisierten Mail-Absatz |
| Kategorien Betroffener | Teilnehmende; Begünstigte/Dritte aus aggregierten Datenquellen |
| Datenkategorien | Prompts, Dokumenteninhalte, abgeleitete Antworten, Konfidenz-Indikatoren |
| Empfänger | Ausschließlich eigene Inferenz-Hardware (NUC, EVO-X2) am Standort Eppstein |
| Drittlandsübermittlung | Keine (Tailscale-Mesh zwischen Hetzner-Server und Inferenz-Hardware ist Ende-zu-Ende verschlüsselt; Tailscale Inc. erhält nur Verbindungs-Metadaten — gestützt auf EU-US Data Privacy Framework, Art. 45 DSGVO) |
| Löschfrist | Inferenz erfolgt flüchtig im Arbeitsspeicher, keine Persistenz auf den Inferenz-Geräten; abgeleitete Embeddings folgen Upload-Löschung |
| TOMs | Kein Modelltraining auf Inhalten, kein externes API, technische Demonstration ohne automatisierte Einzelfallentscheidung (Art. 22 DSGVO), Disclaimer unter jeder LLM-Antwort |

## E — Aggregation öffentlicher Datenquellen

| Feld | Angabe |
|------|--------|
| Zweck | Demonstration risikobasierter Auswertung von EFRE-/ESF-/JTF-Transparenzlisten und Beihilferegistern |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. e und f DSGVO i. V. m. Art. 85 DSGVO (öffentliches Interesse, Schulung und Demonstration) |
| Kategorien Betroffener | Begünstigte aus den jeweils öffentlich publizierten Listen |
| Datenkategorien | Namen, Adressen, Förderhöhen, Vorhabenbeschreibungen (entsprechen den jeweiligen amtlichen Veröffentlichungspflichten nach Art. 49 VO (EU) 2021/1060) |
| Empfänger | Workshop-Teilnehmende auf der Plattform |
| Drittlandsübermittlung | Keine |
| Löschfrist | Synchronisation mit den amtlichen Quellen; lokal nicht über das Workshop-Ende hinaus erforderlich |
| TOMs | Lesender Bezug per HTTP, keine Re-Identifikation außerhalb der amtlichen Veröffentlichungen, Hinweis auf Betroffenenrechte in der Datenschutzerklärung |

## F — Sanktionslisten

| Feld | Angabe |
|------|--------|
| Zweck | Dokumentation der einschlägigen Sanktionsregime + Verlinkung der amtlichen Suchmasken (EU FSF, UN SC, OFAC SDN, UK OFSI, SECO) |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. e DSGVO (öffentliches Interesse, Schulungszweck) |
| Kategorien Betroffener | Sanktionierte Personen und Organisationen aus den amtlich publizierten Listen |
| Datenkategorien | Name, Aliase, Geburtsdaten, Listeneinträge |
| Empfänger | **Nur Administratoren** — Suche und Export sind für Workshop-Teilnehmende deaktiviert, lediglich Listenbeschreibungen und Direktlinks bleiben sichtbar |
| Drittlandsübermittlung | Keine (lokal indexiert) |
| Löschfrist | Mit Workshop-Ende komplett deaktivierbar; Bezug über OpenSanctions-Snapshot |
| TOMs | Admin-Only-Endpoints (HTTP 403 für Nicht-Admins), DSGVO-Hinweisbanner für Teilnehmende, dokumentierter Demo-Charakter |

## G — E-Mail-Versand (Bestätigung + Admin-Notify)

| Feld | Angabe |
|------|--------|
| Zweck | Versand der Anmeldebestätigung an Teilnehmende und Benachrichtigung des Veranstalters |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. b DSGVO (Vertragsdurchführung), bei KI-personalisiertem Absatz zusätzlich Art. 6 Abs. 1 lit. a DSGVO |
| Kategorien Betroffener | Teilnehmende, Veranstalter |
| Datenkategorien | Name, E-Mail-Adresse, Organisation, Anmeldedaten, ggf. KI-personalisierter Textabsatz |
| Empfänger | 1&1 IONOS SE (Mail-Transport-Provider, Mailbox jan.riener@vwvg.de) |
| Drittlandsübermittlung | Keine |
| Löschfrist | Mail-Inhalte verbleiben im SMTP-Log nach IONOS-Standardretention; Versandprotokoll im Anwendungslog folgt der Caddy-Retention (30 Tage) |
| TOMs | STARTTLS-Pflicht bei SMTP, AVV mit IONOS, BackgroundTask isoliert Mail-Fehler von der HTTP-Anfrage |

## H — Caddy-Zugriffslogs

| Feld | Angabe |
|------|--------|
| Zweck | Sicherer und stabiler Betrieb der Plattform, Fehleranalyse, Missbrauchsabwehr |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse) |
| Kategorien Betroffener | Alle Aufrufer der Plattform |
| Datenkategorien | IP-Adresse, Zeitstempel, URL, HTTP-Status, Referrer, User-Agent, übertragenes Volumen |
| Empfänger | Verantwortlicher; Hetzner als Betreiber des Untergrund-Hosts |
| Drittlandsübermittlung | Keine |
| Löschfrist | Spätestens 30 Tage (journald `MaxRetentionSec=2592000` bzw. Caddy-eigene Rotation) |
| TOMs | Logs nur lokal auf dem Hetzner-Server, kein Export, Speicherbegrenzung über `SystemMaxUse=` zusätzlich zur Zeit-Retention |

---

## Allgemeine technisch-organisatorische Maßnahmen

- **Verschlüsselung im Transit:** TLS 1.2+ (Let's Encrypt), HSTS, STARTTLS bei SMTP, Tailscale-WireGuard zwischen Hetzner und Inferenz-Hardware
- **Verschlüsselung im Ruhezustand:** age-verschlüsselte Backups; Schlüssel ausschließlich beim Verantwortlichen
- **Zugriffskontrolle:** Rollenmodell (`attendee` / `moderator` / `admin`), Sanktionssuche und Mail-Test ausschließlich für Admin-Rolle
- **Logging und Monitoring:** Strukturierte Logs (JSON via Caddy), Health-Endpoints, Access-Log-Pruning per Scheduler
- **Datenminimierung:** Nur die für den Workshop-Zweck erforderlichen Felder, optionale Felder ausdrücklich als „optional" markiert
- **Löschkonzept:** Soft-Delete-Flag im Datenmodell (`deleted_at`), endgültige Löschung 6 Monate nach Workshop
- **Schulung:** Verantwortlicher und Moderation halten ausschließlich selbst die Inferenz-Hardware
- **Auftragsverarbeiter:** Hetzner Online GmbH, Tailscale Inc., 1&1 IONOS SE — jeweils mit AVV nach Art. 28 DSGVO

## Verweise

- Datenschutzerklärung: https://workshop.flowaudit.de/datenschutz
- Impressum: https://workshop.flowaudit.de/impressum
- AVV-Hetzner: Standardvertrag, abrufbar im Hetzner-Kundenkonto
- AVV-Tailscale: https://tailscale.com/legal/dpa
- AVV-IONOS: Standardvertrag, abrufbar im IONOS-Geschäftskundenkonto
