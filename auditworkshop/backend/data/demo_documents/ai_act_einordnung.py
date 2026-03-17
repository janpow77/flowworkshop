TITLE = "Risikoklassifizierung der Workshop-Anwendung nach EU AI Act"
CONTENT = """
Risikoklassifizierung gemaess VO (EU) 2024/1689 (EU AI Act)

1. Einordnung der Anwendung

Die Workshop-Anwendung "FlowWorkshop" ist ein KI-gestuetztes Assistenzsystem fuer EFRE-Pruefer. Sie nutzt ein lokal betriebenes Large Language Model (Qwen3-14B via Ollama) zur Unterstuetzung bei der Dokumentenanalyse, Checklisten-Bewertung und Berichtsformulierung.

2. Risikoklasse

Die Anwendung faellt unter KEINE der in Art. 6 Abs. 1 und 2 definierten Hochrisiko-Kategorien:

- Kein Einsatz im Bereich der biometrischen Identifizierung (Anhang III Nr. 1)
- Kein Einsatz in kritischer Infrastruktur (Anhang III Nr. 2)
- Kein Einsatz im Bildungsbereich (Anhang III Nr. 3)
- Kein Einsatz im Beschaeftigungsbereich (Anhang III Nr. 4)
- Kein Einsatz bei wesentlichen privaten oder oeffentlichen Dienstleistungen (Anhang III Nr. 5)
- Kein Einsatz in der Strafverfolgung (Anhang III Nr. 6)
- Kein Einsatz im Bereich Migration (Anhang III Nr. 7)
- Kein Einsatz in der Rechtspflege (Anhang III Nr. 8)

Einordnung: BEGRENZTES RISIKO (Art. 50 -- Transparenzpflichten)

3. Begruendung

Die Anwendung trifft keine autonomen Entscheidungen ueber Foerdermittel oder Verwaltungsakte. Sie dient ausschliesslich als Arbeitsmittel zur Unterstuetzung menschlicher Pruefer. Das pruefungsrechtliche Urteil obliegt ausschliesslich dem Pruefer (Disclaimer wird bei jeder Ausgabe angezeigt).

4. Transparenzpflichten nach Art. 50

Folgende Pflichten werden eingehalten:
a) Kennzeichnung: Jede KI-generierte Ausgabe ist als solche erkennbar (Disclaimer, KI-Status-Badge).
b) Information: Die Nutzer werden darueber informiert, dass sie mit einem KI-System interagieren.
c) Dokumentation: Die verwendeten Modelle, Prompts und Datenquellen sind transparent (Pipeline-Widget, System-Info).

5. Zusaetzliche Sicherheitsmassnahmen

- Lokale Verarbeitung: Kein Datenabfluss an externe Server.
- Human-in-the-Loop: Accept/Reject/Edit-Workflow bei KI-Bewertungen.
- RAG-Beschraenkung: KI antwortet nur auf Basis vorgelegter Dokumente.
- Halluzinations-Kontrolle: Szenario 3 demonstriert explizit die Risiken.
- Kein Fine-Tuning auf personenbezogene oder vertrauliche Daten.

6. Fazit

Die Anwendung erfuellt die Anforderungen des EU AI Act fuer Systeme mit begrenztem Risiko. Eine Registrierung in der EU-Datenbank nach Art. 49 ist nicht erforderlich, da kein Hochrisiko-KI-System vorliegt. Die freiwillige Einhaltung der Transparenzpflichten nach Art. 50 staerkt das Vertrauen der Anwender und entspricht dem Grundsatz der verantwortungsvollen KI-Nutzung in der oeffentlichen Verwaltung.
"""
