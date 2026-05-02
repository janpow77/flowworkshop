# Claude CLI Prompt: Österreich in Szenario 6 ergänzen

```text
Implementiere eine ländersensitive Erweiterung für Szenario 6 „Begünstigtenverzeichnis“, damit neben Deutschland auch Österreich sauber dargestellt und ausgewertet werden kann.

Ziel:
Die bestehende Deutschland-Demo darf unverändert weiter funktionieren. Zusätzlich soll Österreich als eigenes Land im gleichen Szenario 6 auswählbar sein. Die UI soll ein Segmented Control oder Tabs mit „Deutschland“, „Österreich“ und optional „Alle“ anzeigen.

Darstellung im Workshop:
- Default bleibt „Deutschland“, damit die bestehende Demo stabil bleibt.
- „Österreich“ wird als eigener Tab gezeigt.
- „Alle“ kann optional für einen Gesamtvergleich genutzt werden, aber nicht als Startansicht.
- Filter sollen nicht mehr nur „Bundesland“ heißen, sondern abhängig vom Land „Bundesland“ oder allgemein „Region/Bundesland“.

Fachliche Quellen für Österreich:
- EFRE/JTF Österreich: https://www.efre.gv.at/projekte/projektlandkarte
- ESF+/JTF Österreich: https://www.esf.at/projekte/liste-der-vorhaben-2/

Backend-Anforderungen:

1. Lege zentrale Hinterlegungsdaten an.

Datei:
backend/services/country_profiles.py

Inhalt:
COUNTRY_PROFILES = {
    "DE": {
        "country_name": "Deutschland",
        "nominatim_countrycode": "de",
        "region_label": "Bundesland",
        "regions": [
            "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen",
            "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen",
            "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen",
            "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
        ],
        "aliases": ["deutschland", "germany", "de"],
    },
    "AT": {
        "country_name": "Österreich",
        "nominatim_countrycode": "at",
        "region_label": "Bundesland",
        "regions": [
            "Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich",
            "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien",
        ],
        "aliases": ["österreich", "oesterreich", "austria", "at"],
    },
}

AUSTRIA_BENEFICIARY_SOURCES = [
    {
        "source_id": "austria_efre_jtf_2021_2027",
        "country_code": "AT",
        "country_name": "Österreich",
        "fonds": "EFRE/JTF",
        "periode": "2021-2027",
        "source_url": "https://www.efre.gv.at/projekte/projektlandkarte",
        "display_name": "Österreich EFRE/JTF 2021-2027",
    },
    {
        "source_id": "austria_esf_jtf_2021_2027",
        "country_code": "AT",
        "country_name": "Österreich",
        "fonds": "ESF+/JTF",
        "periode": "2021-2027",
        "source_url": "https://www.esf.at/projekte/liste-der-vorhaben-2/",
        "display_name": "Österreich ESF+/JTF 2021-2027",
    },
]

Diese Daten sollen von dataframe_service.py, geocoding_service.py und beneficiaries.py verwendet werden. Keine doppelten Länderlisten in Frontend-Komponenten pflegen.

2. Erweitere die DataFrame-Metadaten.

In backend/services/dataframe_service.py:
- workshop_df_metadata um country_code und country_name erweitern.
- Bestehende deutsche Quellen sollen automatisch country_code=DE und country_name=Deutschland bekommen.
- Neue österreichische Quellen sollen country_code=AT und country_name=Österreich bekommen.

3. Erweitere die Metadaten-Erkennung.

Erkennung:
- Deutsche Bundesländer bleiben wie bisher.
- Österreichische Bundesländer zusätzlich erkennen:
  Burgenland, Kärnten, Niederösterreich, Oberösterreich, Salzburg,
  Steiermark, Tirol, Vorarlberg, Wien.
- Österreich aus Dateinamen erkennen:
  oesterreich, österreich, austria, AT, efre_at, esf_at.
- Wenn ein österreichisches Bundesland erkannt wird, country_code=AT setzen.
- Wenn ein deutsches Bundesland erkannt wird, country_code=DE setzen.

4. Passe die Beneficiary-APIs an.

In backend/routers/beneficiaries.py:
- /api/beneficiaries/sources soll country_code und country_name zurückgeben.
- /api/beneficiaries/search erhält optional country_code.
- /api/beneficiaries/analytics erhält optional country_code.
- /api/beneficiaries/map erhält optional country_code.
- Bestehende Parameter bundesland, fonds, source, min_cost bleiben kompatibel.

In backend/services/dataframe_service.py:
- get_beneficiary_sources(country_code: str | None = None)
- search_beneficiary_records(..., country_code: str | None = None)
- analyze_beneficiary_records(..., country_code: str | None = None)
- get_beneficiary_llm_context(..., country_code: str | None = None)
- build_beneficiary_analysis_answer(..., country_code: str | None = None)

5. Passe Geocoding an.

In backend/services/geocoding_service.py:
- Für DE Nominatim countrycodes=de.
- Für AT Nominatim countrycodes=at.
- Wenn eine Tabelle latitude/longitude oder lat/lon-Spalten enthält, nutze diese direkt und geocode nicht erneut.
- Deutsche NUTS-Zuordnung darf nicht auf österreichische Punkte angewendet werden.
- Für AT NUTS zunächst weglassen, falls keine eigene AT-NUTS-Datei vorhanden ist.

6. Passe Kartenlogik an.

In get_beneficiary_map_data und /api/beneficiaries/map:
- country_code berücksichtigen.
- Rückgabe sources enthält:
  country_code, country_name, bundesland/region, fonds, periode, count, total_rows.
- Keine Vermischung von DE- und AT-Kartenpunkten, wenn ein Land ausgewählt ist.

Frontend-Anforderungen:

1. ScenarioPage.tsx

In frontend/src/pages/ScenarioPage.tsx bei Szenario 6:
- Oberhalb von BeneficiaryMap und BeneficiaryAnalyticsPanel ein Segmented Control anzeigen:
  Deutschland | Österreich | Alle
- State:
  countryCode: "DE" | "AT" | ""
- Default:
  "DE"
- countryCode an BeneficiaryMap und BeneficiaryAnalyticsPanel weitergeben.

2. BeneficiaryMap

In frontend/src/components/workshop/BeneficiaryMap.tsx:
- Prop countryCode?: "DE" | "AT" | "" akzeptieren.
- /api/beneficiaries/map?country_code=DE bzw. AT laden.
- Quellenliste landesspezifisch anzeigen.
- Wenn für Österreich keine Daten vorhanden sind, Empty State:
  „Für Österreich sind noch keine Begünstigtenverzeichnisse geladen.“

3. BeneficiaryAnalyticsPanel

In frontend/src/components/workshop/BeneficiaryAnalyticsPanel.tsx:
- Prop countryCode?: "DE" | "AT" | "" akzeptieren.
- listBeneficiarySources und analyzeBeneficiaries mit country_code aufrufen.
- Label „Bundesland“ in „Region/Bundesland“ ändern oder aus country_profiles ableiten, falls API verfügbar.
- Statistik getrennt nach Deutschland/Österreich ermöglichen.

4. CompanySearchPage

Nur minimal anpassen:
- Optionaler Länderfilter DE/AT/Alle, falls dort Begünstigtendaten durchsucht werden.
- Bestehendes Verhalten ohne Filter bleibt unverändert.

Tests:

1. Backend-Tests ergänzen:
- Österreichische Metadaten-Erkennung aus Dateiname und Titelzeile.
- country_code-Filter für sources, analytics, search und map.
- AT-Geocoding nutzt countrycodes=at oder vorhandene lat/lon-Spalten.
- Bestehende DE-Tests bleiben grün.

2. Frontend-/E2E-Tests ergänzen:
- Szenario 6 zeigt Tabs Deutschland, Österreich, Alle.
- Umschalten auf Österreich ruft APIs mit country_code=AT auf.
- Empty State erscheint, wenn keine AT-Daten vorhanden sind.
- Deutschland-Tab bleibt kompatibel mit bestehenden Tests.

Akzeptanzkriterien:
- Bestehende Deutschland-Demo läuft unverändert.
- Österreichische Listen können eingelesen, separat gefiltert und ausgewertet werden.
- Karte vermischt DE und AT nicht unkontrolliert.
- Statistik und Suche können pro Land getrennt laufen.
- Österreichische EFRE/JTF-Projektlisten mit vorhandenen Koordinaten nutzen diese direkt.
- Alle bestehenden Tests bleiben grün; neue Tests für AT sind ergänzt.
```
