# Begünstigten-Transparenzlisten — Harvest-Status

**Stand: 06.08.2026** · geprüft gegen die Produktionsinstanz auf CCX23

## Ausgangslage

Die 35 Einträge in `workshop_beneficiary_sources_config` standen auf
`source_type='manual_upload'` ohne `source_url`. `_is_source_due()` lässt nur
`xlsx_url`/`csv_url` durch, also übersprang der nächtliche Auto-Harvest jede
Quelle — seit dem 05.07.2026 kam kein einziger neuer Datensatz an, während der
Lauf jede Nacht `status=ok` meldete.

## Erreichbarkeit der Direktlinks (Live-Prüfung vom Produktionshost)

| Ergebnis | Quellen |
|---|---|
| liefert eine Datei | 19 |
| HTTP 404 | 6 (Brandenburg EFRE, Bremen EFRE + ESF, Bund ISF, Rheinland-Pfalz EFRE, Thüringen EFRE) |
| Verbindungsfehler / TLS | 2 (Baden-Württemberg EFRE, Bund AMIF) |
| liefert HTML statt Datei | 1 (Mecklenburg-Vorpommern ESF) |
| ohne Direktlink in der Registry | 7 (Hessen, Niedersachsen, Brandenburg JTF, beide AT-Quellen) |

Die Links zeigen auf **versionierte Dateinamen** („…Stand_28.02.2026.xlsx"). Wenn
ein Land eine neue Liste veröffentlicht, wechselt der Dateiname und der
Direktlink stirbt. Bremen EFRE war am 05.07. noch erreichbar und ist am 06.08.
tot — genau dieses Muster. Ein dauerhaft funktionierender Auto-Harvest braucht
deshalb entweder eine Landing-Page-Auflösung (Link auf der Portalseite suchen)
oder eine gepflegte Registry.

## Testlauf vom 06.08.2026

Ein einmaliger Lauf mit gesetzten URLs ergab **4 erfolgreiche und 24
fehlgeschlagene Quellen**:

| Quelle | Datensätze | entspricht Registry |
|---|---|---|
| Baden-Württemberg ESF | 1.482 | ja |
| Bayern ESF | 3.042 | ja |
| Hamburg ESF | 82 | ja |
| Thüringen ESF | 5.153 | ja |

Die 24 Fehlschläge verteilen sich auf:

- **8 Download-Fehler** (404/TLS) — siehe Tabelle oben
- **6 Format-Fehler** „nur für XLSX/XLS/CSV" — der Server liefert
  `application/zip` bzw. `application/octet-stream`, die Typerkennung greift
  über die Endung nicht durch
- **10 Parser-Fehler** — „Keine valide Begünstigtenzeile", „Begünstigtenname
  fehlt in Zeile n", `'int' object has no attribute 'strip'`. Die Länder nutzen
  abweichende Spaltenüberschriften und Kopfzeilen; ohne gepflegtes
  `field_mapping`/`header_row` je Quelle greift die Auto-Erkennung nicht.

## Wichtig: Snapshot-Modus löscht

`run_beneficiary_auto_harvest` ruft den Harvester mit `mode="snapshot"` auf.
Snapshot löscht **alle** bestehenden Datensätze der Quelle und schreibt den
frisch geladenen Stand — bewusst so, damit die Tabelle den aktuellen
Quellensnapshot abbildet und nicht die historisch aufaddierte Menge.

Die Löschung erfolgt erst **nach** erfolgreichem Parsen und Validieren und
liegt mit dem Insert in einer Transaktion. Im Testlauf hat sich das bewährt:
alle 24 Fehlschläge rollten sauber zurück, es entstand nicht einmal ein
Run-Eintrag.

Bei den 4 erfolgreichen Quellen wurden dabei doppelte Import-Schichten
bereinigt (Thüringen ESF: 10.306 → 5.153 Zeilen, also exakt die Hälfte). Die
Tabelle enthält solche Doppel-Importe bei zahlreichen weiteren Quellen —
Thüringen EFRE 4.307 Zeilen bei 2.154 eindeutigen, Bund ISF 122 bei 61,
Bremen EFRE 252 bei 126. Wer den Bestand für Auswertungen nutzt, muss das
wissen.

## Aktueller Zustand

**Vier Quellen sind automatisiert** und holen ihre Aktualisierung alle 30 Tage
selbst: Baden-Württemberg ESF, Bayern ESF, Hamburg ESF, Thüringen ESF. Ihr
Bestand entspricht exakt den heute veröffentlichten Listen.

Die übrigen 31 stehen auf `manual_upload`, bis ein `field_mapping` je Land
hinterlegt ist — ein nicht parsebarer Lauf bringt nichts ausser Rauschen im
Protokoll. Die ermittelten Kopfzeilen sind bereits gespeichert und gehen nicht
verloren.

Die Datenbank wird seit dem 06.08.2026 nächtlich gesichert, jeder weitere
Harvest-Versuch ist damit reversibel.

## Nächste Schritte

1. Pro Quelle `field_mapping`, `sheet_name` und `header_row` in der
   Konfiguration hinterlegen — das behebt die 10 Parser-Fehler
2. Typerkennung über den `Content-Type` statt über die Dateiendung, damit
   `application/zip`/`octet-stream` als XLSX durchgehen (6 Quellen)
3. Tote Direktlinks aus den Portalseiten neu ziehen (8 Quellen)
4. Erst danach `source_type` wieder auf `xlsx_url`/`csv_url` setzen —
   `scripts/seed_beneficiary_source_urls.py --apply` erledigt das
5. ~~Die Workshop-Datenbank hat kein Backup.~~ **Erledigt am 06.08.2026** —
   `scripts/backup-auditworkshop-daily.sh`, nächtlich um 04:45 im Crontab des
   Nutzers `deploy`.

## Link-Aktualisierung (07.08.2026)

Die Länder veröffentlichen ihre Listen unter versionierten Dateinamen. Mit
jeder neuen Veröffentlichung stirbt der bisherige Direktlink — die
Portalseite bleibt dagegen stabil. `scripts/finde_transparenzlisten_links.py`
lädt deshalb die Portalseite, sammelt alle Verweise auf XLSX/CSV, bewertet
sie nach Stichworten und prüft jeden Kandidaten am Inhalt (eine XLSX ist ein
ZIP-Archiv und beginnt mit `PK\x03\x04`).

Eine Mindestpunktzahl verhindert thematisch benachbarte Fehlgriffe: Auf der
hessischen Seite wurde zunächst der „Zeitplan der geplanten Aufrufe"
eingesammelt — eine XLSX, aber keine Vorhabensliste.

Sieben Links wurden so wiederhergestellt:

| Quelle | Datensätze |
|---|---|
| Bremen ESF | 1.071 |
| Brandenburg JTF | 959 |
| Brandenburg EFRE | 676 |
| Bund AMIF | 441 |
| Bremen EFRE | 234 |
| Rheinland-Pfalz EFRE | 198 |
| Bund ISF | 63 |

Damit sind **23 Quellen** automatisiert, der Bestand liegt bei **74.395
Datensätzen**.

### Fondsübergreifende Listen

Brandenburg veröffentlicht EFRE und JTF in **einer** Datei: 676 EFRE- und
960 JTF-Vorhaben in einem Blatt. Ohne Filter hätte die EFRE-Quelle alle
1.636 Zeilen bekommen und 960 davon fälschlich als EFRE gestempelt. In einem
Prüfwerkzeug ist eine solche Falschzuordnung schlimmer als eine fehlende
Zeile.

`filtere_nach_fonds` behält deshalb nur den eigenen Fonds — aber bewusst nur
dann, wenn die Datei wirklich mehrere Fonds enthält. Bei einer einheitlichen
Liste bleibt alles unangetastet, sonst würde eine abweichende Schreibweise
(„ESF+" gegen „ESF") den kompletten Import leeren. Passt kein einziger Wert,
wird ebenfalls nicht gefiltert, sondern gewarnt.

### Weiterhin offen

Bei acht Quellen ist die Portalseite selbst umgezogen (HTTP 404/403) oder
enthält keinen Datei-Verweis mehr: Baden-Württemberg EFRE, Hessen EFRE und
ESF, Mecklenburg-Vorpommern ESF, Niedersachsen EFRE und ESF, Saarland EFRE
und ESF sowie Thüringen EFRE. Für sie muss die Portaladresse neu recherchiert
werden; das Werkzeug findet den Datei-Link danach von allein.

## Ergebnis der Länder-Kalibrierung (06.08.2026)

`scripts/kalibriere_beneficiary_quellen.py` probiert für jede Quelle alle
Blätter und Kopfzeilen durch und wählt die Variante, unter der die
Spaltenerkennung des Harvesters die meisten Rollen trifft (Name, Vorhaben,
Kosten, Datum, Ort). Bei Gleichstand gewinnt die kleinste Kopfzeile, denn der
Vorspann steht immer oben. Vor dem Speichern prüft das Skript, ob die gewählte
Variante mindestens die Hälfte des bisherigen Bestands ergibt — sonst wird die
Quelle übersprungen statt durch ein Rumpfergebnis ersetzt.

Bestand nach dem Durchlauf: **71.156 Datensätze** (vorher 53.547, überwiegend
doppelte Import-Schichten).

| Land / Fonds | Datensätze | Anmerkung |
|---|---|---|
| Nordrhein-Westfalen ESF | 23.133 | vorher 6.810 |
| Rheinland-Pfalz ESF | 6.395 | deckt sich exakt mit dem Vorbestand |
| Sachsen EFRE | 5.761 | |
| Thüringen ESF | 5.153 | |
| Brandenburg ESF | 4.024 | vorher 1.867, damals falsch geparst |
| Sachsen-Anhalt ESF | 3.862 | |
| Bayern ESF | 3.042 | |
| Sachsen ESF | 2.561 | |
| Baden-Württemberg ESF | 1.482 | |
| Sachsen-Anhalt EFRE | 1.033 | |
| Berlin EFRE | 687 | |
| Mecklenburg-Vorpommern EFRE | 467 | |
| Berlin ESF | 387 | |
| Bayern EFRE | 333 | |
| Hamburg ESF / EFRE | 82 / 56 | |

Nicht automatisierbar bleiben: acht Quellen mit toten Direktlinks
(404/HTML/TLS), Nordrhein-Westfalen EFRE (kein lesbares XLSX-Archiv),
Bremen EFRE + ESF und Schleswig-Holstein ESF (keine erkennbare Namensspalte),
Bund AMIF (Server bricht die Verbindung ab) sowie sieben Quellen ohne
Direktlink in der Registry.

## Fünf Fehler im Import-Pfad, die dabei sichtbar wurden

1. **Eine Leerzeile verwarf den ganzen Import.** Die Validierung stufte jede
   Zeile ohne Begünstigtennamen als harten Fehler ein. Landeslisten enthalten
   aber regelmässig Leer-, Summen- und Fußnotenzeilen — bei Nordrhein-Westfalen
   ESF scheiterten 28.498 Datensätze an Zeile 2. Solche Zeilen werden nun
   übersprungen; erst über 20 % (und mehr als 50 Zeilen) bricht der Lauf ab,
   weil dann die Kopfzeile nicht stimmt.
2. **Ein Konflikt riss alle Folgezeilen mit.** Sachsen führt Vor- und Nachname
   getrennt, wodurch zwei echte Zeilen denselben Datensatz-Hash ergeben. Die
   Eindeutigkeitsverletzung vergiftete die Transaktion, alle weiteren Zeilen
   liefen in „current transaction is aborted". Jede Zeile bekommt jetzt einen
   eigenen Savepoint, Konflikte werden als übersprungen gezählt.
3. **Zahlen in Textspalten brachen den Import.** `'int' object has no attribute
   'strip'` — mehrere Länder führen numerische Projektnummern und
   Gemeindeschlüssel. Alle Textfelder laufen jetzt über `_stringify`.
4. **Die Dateityp-Erkennung las die Endung aus der URL.** Adressen wie
   `…liste.xlsx?ts=1774519001` oder `sixcms/media.php/9/12345` scheiterten mit
   „nur fuer XLSX/XLS/CSV". Jetzt entscheidet der Inhalt (ZIP-Signatur).
5. **Die wahre Fehlerursache blieb verborgen.** Nach einem Rollback griff der
   Code auf das ORM-Objekt des Laufs zu und warf `ObjectDeletedError` — die
   eigentliche Meldung ging verloren. Der Status wird jetzt lokal geführt.

## Ermittelte Kopfzeilen (Analyse vom 06.08.2026)

`scripts/analyse_transparenzlisten.py` lädt jede erreichbare Quelle und
bestimmt Blatt und Kopfzeile. Ergebnis:

| Quelle | Blatt | Kopfzeile (0-basiert) |
|---|---|---|
| Bayern EFRE | Liste der Vorhaben | 5 |
| Berlin EFRE | „Liste der Vorhaben 31.10.2025" | 6 |
| Berlin ESF | Projektliste | 6 |
| Brandenburg ESF | Liste der Vorhaben | 2 |
| Hamburg EFRE | Sheet1 | 0 |
| Nordrhein-Westfalen ESF | ESF-Liste der Vorhaben | 1 |
| Rheinland-Pfalz ESF | Liste der Vorhaben 31.12.2025 | 1 |
| Sachsen-Anhalt EFRE | „Liste der Vorhaben" | 6 |
| Sachsen-Anhalt ESF | „Liste der Vorhaben" | 7 |
| Sachsen EFRE / ESF | Liste der Vorhaben | 7 |

Die Kopfzeilen sind in der Konfiguration hinterlegt. Sie **allein genügen
nicht**: Ein Testlauf mit gesetzten Kopfzeilen scheiterte weiterhin, weil
`_detect_canonical_columns` die Spaltennamen der Länder nicht trifft. Bayern
und Rheinland-Pfalz führen zweisprachige, mehrzeilige Überschriften
(„Name des Begünstigten /\nbeneficiary name"), Nordrhein-Westfalen ESF ist
komplett englisch („Beneficiary", „Operation name"), Sachsen-Anhalt setzt
noch eine Zwischenzeile über die Daten.

Nächster Schritt ist deshalb ein explizites `field_mapping` je Quelle —
Zuordnung `beneficiary_name`/`project_name`/… auf die Originalüberschrift.
Das ist Fleißarbeit pro Land, aber mit der Analyse oben mechanisch.
