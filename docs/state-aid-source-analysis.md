# TAM Public Search — Quellenanalyse

Stand: 2026-05-08

Bezug: `docs/eu-state-aid-register-plan.md` Paket A.

## Endpunkte

| Schritt | URL | Methode | Zweck |
|---|---|---|---|
| Init | `https://webgate.ec.europa.eu/competition/transparency/public?lang=en` | GET | CSRFTOKEN + Cookies holen |
| Search | `https://webgate.ec.europa.eu/competition/transparency/public/search` | POST | erstes Refinement (Country -> erweitert das Formular um Regionen + Filter) |
| Results | `https://webgate.ec.europa.eu/competition/transparency/public/search/results` | POST | Liefert HTML-Trefferseite |
| Pagination | `.../public/search/results?offset=N&max=100` | GET | Sessionbasiert, danach blaetterbar |
| Detail | `.../public/aidAward/show/{id}` | GET | Einzeldatensatz |
| SA-Fallakte | `https://competition-cases.ec.europa.eu/cases/SA.{n}` | GET | von TAM verlinkt |

## CSRF / Session

- Token in `<input name="CSRFTOKEN">` (alphanumerische Bloecke).
- Token bleibt pro Session konstant; Cookie-Jar wird zwingend gebraucht.
- Header: `User-Agent` setzen; `Origin: https://webgate.ec.europa.eu` ist nicht zwingend, aber empfohlen.

## Form-Felder (`/public/search/results`)

Pflicht (mindestens):

- `CSRFTOKEN`
- `countries` (z.B. `CountryDEU`)

Optional:

- `grantingAuthorityRegions` (z.B. `RegionNuts2024.DE7` — Hessen)
- `beneficiaryName`
- `beneficiaryNationalId`
- `beneficiaryTypes`
- `aidInstruments`
- `objectives`
- `sectors`
- `dateGrantedFrom` / `dateGrantedTo` (Format `dd/mm/yyyy`)
- `nominalAmountFrom` / `nominalAmountTo`
- `grantedAmountFrom` / `grantedAmountTo`
- `currency` (z.B. `EUR`)
- `aidMeasureCaseNumber` (SA-Referenz)
- `aidMeasureTitle`
- `grantingAuthorityNames`
- `entrustedEntities`
- `financialIntermediaries`
- `refNo`
- `aidMeasureCovid19`

## Ergebnis

- HTML-Tabelle `id="resultsTable"`, 19 Spalten:
  Country, Aid Measure Title, SA.Number (-> `https://competition-cases.ec.europa.eu/cases/SA.NNNNN`),
  Ref-no., National ID, Beneficiary Name, Beneficiary Type, Region, NACE,
  Aid Instrument, Objectives, Nominal Amount, Granted Amount, Date of granting,
  Granting Authority Name, Entrusted Entity, Financial Intermediaries, Published Date,
  Another Beneficiary MS, Third country.
- Detail-URL pro Zeile: `<a href="/public/aidAward/show/{id}">{Ref-no.}</a>`.
- Pagination: `currentStep`/`step`-Anchors, `?offset=N&max=10|25|50|100`. `max=100` ist das Maximum.
- Beispielzaehler: Deutschland gesamt = ca. 276 240 Awards, Hessen 2024 = ca. 28 820.

## CSV-Export (verworfen)

- Endpoint `/public/search/exportCsv` wirft NullPointerException ohne vorherige
  saveUserCriteria-Sequenz.
- Die saveUserCriteria-Maske erfordert Vor-/Nachname und E-Mail-Adresse. Vermutlich
  asynchroner E-Mail-Versand.
- Fuer einen automatisierten Harvester ungeeignet, deshalb kein CSV-Pfad.

## Entscheidung

- **HTTP + BeautifulSoup**, kein Browser, kein CSV-Export.
- Pagination per `max=100` und `offset`.
- Pro Lauf wird zwingend gefiltert (Land + Region + Datumsfenster), damit der
  Crawl nicht ueber Tage laeuft.
- Default fuer den Workshop-Demo: `--country DE --region DE7 --since 2024-01-01 --limit 500`.
- Rate Limit: 1 Request / 600 ms, Backoff bei 5xx.
- Detailseiten werden nur on-demand geladen (z. B. wenn Felder in der Tabelle leer sind).

## Felder-Mapping (TAM -> normalisierte Tabelle)

| TAM-Spalte | `workshop_state_aid_awards` |
|---|---|
| Country | `country_name` (+ ISO-Map -> `country_code`) |
| Aid Measure Title | `aid_objective` (Zusatz: `measure_title` im raw-payload) |
| SA.Number | `sa_reference`, `case_url` |
| Ref-no. | `source_record_id` (+ Detail-URL -> `source_url`) |
| National ID | `beneficiary_identifier` |
| Name of the beneficiary | `beneficiary_name` (+ normalisiert) |
| Beneficiary Type | `beneficiary_type` |
| Region | `nuts_label` (Code aus `data-country-bid`/Region-Code in Form) |
| Sector (NACE) | `nace_label` |
| Aid Instrument | `aid_instrument` |
| Objectives of the Aid | `aid_objective` |
| Nominal Amount | `aid_amount` (+ `aid_currency`) |
| Aid element | `aid_amount_eur` (sofern EUR) |
| Date of granting | `granting_date` |
| Granting Authority | `granting_authority` |
| Entrusted Entity | `entrusted_entity` |
| Published Date | `publication_date` |

## Risiken

- HTML-Struktur kann sich aendern (Klassennamen `dataTable list`, `currentStep`).
- TAM enthaelt keine maschinenlesbaren NUTS-Codes pro Award, nur Region-Label.
  Die Code-Zuordnung muss aus dem Suchformular abgeleitet oder per Lookup-Tabelle
  ergaenzt werden.
- Detail-Seiten werden nicht in jedem Fall NUTS-Codes liefern; Karte wird daher
  konservativ aggregiert (Default: NUTS II / Land).

## Naechste Schritte

- Paket B: Backend-Datenmodell.
- Paket C: Harvester `harvest_state_aid.py` mit BeautifulSoup-Parser.
