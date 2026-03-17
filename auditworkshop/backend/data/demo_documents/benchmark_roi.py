TITLE = "Effizienzanalyse -- KI-Unterstuetzung bei EFRE-Verwaltungskontrollen"
CONTENT = """
Effizienzanalyse: KI-gestuetzte Vorhabenpruefung

1. Vergleich: Manuell vs. KI-unterstuetzt

Aufgabe                              | Manuell    | KI-unterstuetzt | Ersparnis
-------------------------------------|------------|----------------|----------
Auflagen aus Bescheid extrahieren    | 30-45 Min. | 5-10 Min.      | ~70%
VKO-Checkliste ausfuellen (25 Punkte)| 2-3 Std.   | 30-60 Min.     | ~65%
Berichtsentwurf formulieren          | 1-2 Std.   | 15-30 Min.     | ~75%
Vergabedokumentation pruefen          | 45-90 Min. | 15-30 Min.     | ~60%
Recherche in EU-Verordnungen         | 30-60 Min. | 2-5 Min.       | ~90%

2. Hochrechnung pro Pruefbehoerde

Annahmen:
- 50 Vorhabenpruefungen pro Jahr (Art. 77 Stichprobe)
- Durchschnittlich 8 Stunden pro Pruefung (Vorbereitung + Durchfuehrung + Bericht)
- KI-Unterstuetzung spart durchschnittlich 40% der Vorbereitungs- und Berichtszeit

Berechnung:
- Zeitaufwand ohne KI: 50 x 8 = 400 Personenstunden/Jahr
- Davon KI-unterstuetzbar: ~60% = 240 Stunden
- Ersparnis bei 40% Effizienzgewinn: 96 Personenstunden/Jahr
- Das entspricht ca. 12 Arbeitstagen oder 2,4 Personenwochen pro Jahr

3. Qualitative Vorteile

- Konsistenz: KI wendet Pruefmassstaebe gleichmaessig an (kein "Montagspruefer-Effekt")
- Vollstaendigkeit: Automatische Pruefung aller 30 VKO-Punkte vs. selektive manuelle Pruefung
- Nachvollziehbarkeit: Jede KI-Bewertung mit Fundstelle und Begruendung dokumentiert
- Wissenstransfer: Neue Pruefer koennen von den KI-Vorschlaegen lernen
- EU-Recht-Recherche: Sekundenschnelle Suche in 26 Dokumenten statt manuelles Blaettern

4. Investitionsbedarf

Hardware (einmalig):
- GPU-faehiger Server (z.B. ASUS NUC mit eGPU): ca. 2.500-4.000 EUR
- Alternativ: Bestehender Server mit NVIDIA-GPU ab 8 GB VRAM

Software:
- Open-Source-Stack: 0 EUR Lizenzkosten
- Ollama + Qwen3-14B: Kostenlos, lokal betrieben

Personal:
- Einrichtung und Anpassung: ~5 Personentage
- Laufende Pflege (Wissensdatenbank aktualisieren): ~1 Tag/Quartal

5. Return on Investment

Bei einer Vollkostenrechnung (Hardware + Personal) amortisiert sich die Investition innerhalb von 6-12 Monaten durch eingesparte Personalstunden. Der qualitative Nutzen (Konsistenz, Vollstaendigkeit) ist ab dem ersten Einsatz wirksam.
"""
