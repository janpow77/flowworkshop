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

Der Auto-Harvest ist **bewusst wieder deaktiviert** (alle 35 Quellen auf
`manual_upload`), bis die Parser-Fehler je Quelle behoben sind. Eine Aktivierung
mit 24 von 28 fehlschlagenden Quellen bringt nichts.

## Nächste Schritte

1. Pro Quelle `field_mapping`, `sheet_name` und `header_row` in der
   Konfiguration hinterlegen — das behebt die 10 Parser-Fehler
2. Typerkennung über den `Content-Type` statt über die Dateiendung, damit
   `application/zip`/`octet-stream` als XLSX durchgehen (6 Quellen)
3. Tote Direktlinks aus den Portalseiten neu ziehen (8 Quellen)
4. Erst danach `source_type` wieder auf `xlsx_url`/`csv_url` setzen —
   `scripts/seed_beneficiary_source_urls.py --apply` erledigt das
5. **Unabhängig davon: die Workshop-Datenbank hat kein Backup.** Auf dem Host
   sichern `wesenszug` und `rechnungslegung` nächtlich, `workshop` nicht.
   Für eine Datenbank mit 44.000 Begünstigten- und 350.000 Beihilfe-Datensätzen
   ist das die dringendste offene Baustelle.
