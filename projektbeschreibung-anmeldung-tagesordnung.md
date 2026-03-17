# Teilbereich: Anmeldung und Tagesordnung

**Projekt:** Digitale Vorfeld-Einreichung – Prüferworkshop EFRE Hessen  
**Verantwortlicher:** Jan Riener  
**Stand:** März 2026  

---

## Zweck

Dieser Teilbereich umfasst drei eng miteinander verknüpfte Funktionen: die Anmeldung der Teilnehmer zum Prüferworkshop, die öffentliche Darstellung der Tagesordnung und die Bereitstellung eines QR-Codes für den Zugang zur Anmeldeseite. Alle drei Funktionen sind aufeinander abgestimmt und nutzen denselben persistenten Datenspeicher. Die Anmeldung erfasst die Teilnehmerdaten und den Themenvorschlag; die Tagesordnung zeigt den vom Admin gepflegten Programmablauf; der QR-Code ermöglicht den barrierefreien Zugang zur Anmeldung über mobile Endgeräte.

---

## Teilfunktion 1: Anmeldung

### Ablauf

Das Anmeldeformular ist in vier Schritte unterteilt. Im ersten Schritt werden Name, Behörde und dienstliche E-Mail-Adresse erfasst. Der Fachbereich ist ein optionales Feld. Im zweiten Schritt gibt der Teilnehmer einen Themenvorschlag und eine konkrete Fragestellung ein. Im dritten Schritt legt er die Sichtbarkeit seiner Einreichung fest und lädt ggf. Unterlagen hoch. Im vierten Schritt erscheint eine automatische Bestätigungsnachricht.

### Sichtbarkeitsoptionen

Bei der Einreichung kann zwischen zwei Modi gewählt werden. Die öffentliche Einreichung macht das Thema im Themenboard sichtbar und gibt anderen Teilnehmern die Möglichkeit, dafür zu voten. Die nicht-öffentliche Einreichung ist ausschließlich für die Workshopmoderation sichtbar. Wer öffentlich einreicht, kann zusätzlich die Anonymisierung aktivieren; in diesem Fall wird die Behördenangabe im Board nicht angezeigt, bleibt aber intern hinterlegt.

### Datenschutzeinwilligungen

Vor der Einreichung sind zwei Einwilligungen zu bestätigen. Die Kenntnisnahme des Datenschutzhinweises nach Artikel 13 DS-GVO ist Pflicht; ohne diese Bestätigung ist eine Einreichung nicht möglich. Die Einwilligung zur Übermittlung an die Anthropic API ist freiwillig und steuert ausschließlich, ob nach dem Absenden eine KI-generierte Bestätigungsnachricht erzeugt wird.

### Technische Umsetzung

Die Formulareingaben werden nach dem Absenden als JSON-Objekt im geteilten Artifact-Speicher unter dem Schlüssel `workshop-submissions` abgelegt. Gespeichert werden: eine zufällig generierte ID, Thema, Fragestellung, Organisation, Sichtbarkeitsstatus, Anonymisierungsstatus, initiale Vote-Zahl (0) und ein ISO-Zeitstempel. Die E-Mail-Adresse und der Name des Einreichenden werden nicht im geteilten Speicher abgelegt, sondern bleiben in der laufenden Session.

### Felder und Validierung

| Feld              | Typ       | Pflicht | Validierung                          |
|-------------------|-----------|---------|--------------------------------------|
| Vorname           | Text      | ja      | nicht leer                           |
| Nachname          | Text      | ja      | nicht leer                           |
| Organisation      | Text      | ja      | nicht leer                           |
| E-Mail            | E-Mail    | ja      | Format `x@y.z`                       |
| Fachbereich       | Text      | nein    | –                                    |
| Themenvorschlag   | Text      | ja      | nicht leer                           |
| Fragestellung     | Textarea  | nein    | –                                    |
| Anmerkungen       | Textarea  | nein    | –                                    |
| Sichtbarkeit      | Toggle    | ja      | öffentlich / nur Moderation          |
| Anonymisierung    | Checkbox  | nein    | nur bei öffentlicher Einreichung     |
| Datei-Upload      | File      | nein    | max. 10 MB, PDF oder DOCX            |
| Datenschutz       | Checkbox  | ja      | muss aktiv sein                      |
| Anthropic-API     | Checkbox  | nein    | steuert KI-Bestätigung               |

---

## Teilfunktion 2: Tagesordnung

### Öffentliche Ansicht

Die Tagesordnung ist die Startseite der Anwendung und für alle Teilnehmer ohne Anmeldung zugänglich. Sie zeigt die Workshop-Metadaten im Kopf (Titel, Untertitel, Datum, Uhrzeit, Ort, vollständige Adresse, Veranstalter, Anmeldeschluss) sowie alle Programmpunkte als vertikalen Zeitstrahl. Der Zeitstrahl ist farblich nach Programmpunkt-Typ gegliedert. Pausen sind visuell zurückgenommen. Die Gesamtdauer und die Anzahl der Programmpunkte werden automatisch berechnet.

### Programmpunkt-Typen

| Typ          | Farbe        | Beschreibung                                      |
|--------------|--------------|---------------------------------------------------|
| Vortrag      | Dunkelblau   | Präsentation durch Referenten                     |
| Diskussion   | Mittelblau   | Plenumsrunde oder moderiertes Gespräch            |
| Workshop     | Gold         | Gruppenarbeit oder interaktive Einheit            |
| Pause        | Grau         | Kaffee- oder Mittagspause, visuell reduziert      |
| Organisation | Grün         | Begrüßung, Abschluss, organisatorische Hinweise   |

### Admin-Verwaltung der Tagesordnung

Der Admin-Bereich ist über einen PIN-geschützten Zugang erreichbar. Der Standard-PIN ist `1234` und soll vor dem Produktiveinsatz geändert werden. Nach der Anmeldung stehen drei Tabs zur Verfügung.

Unter **„Programmpunkte"** können Einträge hinzugefügt, bearbeitet, gelöscht und per Drag-and-drop oder Pfeilschaltflächen umgeordnet werden. Pro Eintrag sind Uhrzeit, Dauer in Minuten, Typ, Titel, Referent und eine optionale Anmerkung pflegbar. Änderungen werden sofort im geteilten Speicher gespeichert und sind für alle Teilnehmer in Echtzeit sichtbar.

Unter **„Workshop-Daten"** lassen sich die Metadaten der Veranstaltung bearbeiten: Titel, Untertitel, Datum, Uhrzeit, Ort (Kurzform für die Infozeile), vollständige Adresse, Veranstalter und Anmeldeschluss. Eine Live-Vorschau zeigt, wie der Kopfbereich der öffentlichen Tagesordnung nach der Speicherung aussehen wird.

Unter **„QR-Code"** wird die URL der gehosteten Anwendung hinterlegt und daraus ein QR-Code generiert. Der Tab ist in Teilfunktion 3 beschrieben.

### Datenspeicher

| Schlüssel          | Modus  | Inhalt                                              |
|--------------------|--------|-----------------------------------------------------|
| `workshop-agenda`  | shared | Array der Programmpunkte (JSON)                     |
| `workshop-meta`    | shared | Workshop-Metadaten inkl. Titel, Datum, Ort, QR-URL  |

Beide Schlüssel liegen im geteilten Speicher und sind damit für alle Nutzer der Anwendung sichtbar. Eine Vorbelegung (`DEFAULT_AGENDA` und `DEFAULT_META`) ist im Code hinterlegt und greift, solange noch keine gespeicherten Daten vorhanden sind.

---

## Teilfunktion 3: QR-Code-Verwaltung

### Zweck

Der QR-Code-Tab im Admin-Bereich ermöglicht es, einen Anmelde-QR-Code zu erzeugen, herunterzuladen und als Aushang aufzubereiten. Teilnehmer können den QR-Code mit ihrem Mobilgerät scannen und gelangen direkt auf die Anmeldeseite der Anwendung, ohne die URL manuell eingeben zu müssen. Der Code eignet sich für Einladungs-E-Mails, Plakate am Veranstaltungsort und digitale Präsentationen.

### Ablauf

Der Admin trägt im Feld „URL der Anwendung" die vollständige Adresse der gehosteten App ein, z. B. `https://workshop.jan-riener.de`. Nach dem Speichern wird der QR-Code sofort generiert. Die URL wird im Feld `qrUrl` des Workshop-Metadaten-Objekts gespeichert und bleibt nach dem Schließen des Browsers erhalten.

### Ausgabeformate

Sobald eine URL hinterlegt ist, stehen zwei Ausgabeformate zur Verfügung.

Der **QR-Code als Bilddatei** kann in der Auflösung 600×600 Pixel heruntergeladen werden. Er lässt sich direkt in eine E-Mail einbetten oder in einem Bildbearbeitungsprogramm weiterverarbeiten. Der Download-Link öffnet die Bilddatei über die externe API `qrserver.com`.

Die **Druckvorlage** zeigt eine Vorschau eines Aushangs im Workshop-Design mit QR-Code, Veranstaltungstitel, Datum, Uhrzeit und Ort. Sie kann über die Druckfunktion des Browsers ausgedruckt werden.

### Technische Umsetzung

Der QR-Code wird über den kostenlosen Dienst `api.qrserver.com` generiert. Die URL wird als Query-Parameter übergeben und als PNG-Bild zurückgeliefert. Eine lokale Generierung ist nicht erforderlich; es wird keine Bibliothek installiert. Der Dienst ist für den produktiven Einsatz ausreichend, erfordert aber eine aktive Internetverbindung. Für einen vollständig offline-fähigen Betrieb soll die QR-Code-Generierung durch eine lokale Bibliothek wie `qrcode.react` ersetzt werden.

### Datenspeicher

Die QR-URL ist Bestandteil des `workshop-meta`-Objekts und wird zusammen mit den übrigen Metadaten unter dem Schlüssel `workshop-meta` im geteilten Speicher abgelegt. Ein separater Speicherschlüssel ist nicht erforderlich.

---

## Zusammenspiel der drei Teilfunktionen

Tagesordnung, Anmeldung und QR-Code bilden den Einstiegsbereich des Workshops. Die Tagesordnung gibt den zeitlichen Rahmen vor und ist die Startseite; der QR-Code leitet Teilnehmer von außen direkt auf das Anmeldeformular; die Anmeldung führt nach dem Absenden optional ins Themenboard. Der Programmpunkt „Eingereichte Themen aus dem Voting" in der Vorbelegungs-Tagesordnung verweist direkt auf die Ergebnisse des Einreichungs- und Votingprozesses. Der Admin soll diesen Programmpunkt nach Ablauf der Einreichungsphase manuell mit den tatsächlichen Top-Themen befüllen.

---

## Hinweise für die Weiterentwicklung

Der Admin-PIN soll vor dem Produktiveinsatz aus einer Umgebungsvariable geladen werden, nicht als Klartext im Quellcode stehen. Für einen dauerhaften Betrieb außerhalb der Artifact-Umgebung ist ein Backend mit persistenter Datenbank erforderlich; der Artikel-13-DS-GVO-Hinweis ist bei jeder strukturellen Änderung der Datenverarbeitung zu aktualisieren. Der Datei-Upload speichert Dateien derzeit nur im Browser-Arbeitsspeicher; serverseitige Speicherung soll in der Produktivversion implementiert werden. Die QR-Code-Generierung über `qrserver.com` setzt eine Internetverbindung voraus; für einen offline-fähigen Betrieb soll eine lokale Bibliothek eingesetzt werden.
