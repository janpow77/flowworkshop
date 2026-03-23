import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test G: DataFrame (XLSX Upload + SQL)
 * Prueft Tabellenliste, SQL-Abfrage-Interface, Ergebnisdarstellung und Upload-Bereich.
 */

const TEST_EMAIL = 'e2e-dataframe@test.local';

const MOCK_TABLES = {
  tables: [
    { table_name: 'df_transparenzliste_hessen', source: 'transparenzliste_hessen', rows: 1247 },
    { table_name: 'df_esf_hessen', source: 'esf_hessen', rows: 583 },
  ],
};

const MOCK_TABLE_INFO = {
  exists: true,
  table_name: 'df_transparenzliste_hessen',
  row_count: 1247,
  columns: [
    { name: 'beguenstigter', type: 'text' },
    { name: 'vorhaben', type: 'text' },
    { name: 'gesamtkosten', type: 'double precision' },
    { name: 'eu_beteiligung', type: 'double precision' },
    { name: 'standort', type: 'text' },
  ],
};

const MOCK_SUMMARY = {
  summary: 'Tabelle mit 1247 Zeilen und 5 Spalten.\nGesamtkosten: min=1000, max=5000000, mean=250000',
};

const MOCK_QUERY_RESULT = {
  rows: [
    { beguenstigter: 'Stadt Kassel', vorhaben: 'Digitalisierung', gesamtkosten: 500000, eu_beteiligung: 250000, standort: 'Kassel' },
    { beguenstigter: 'Stadt Frankfurt', vorhaben: 'Infrastruktur', gesamtkosten: 1200000, eu_beteiligung: 600000, standort: 'Frankfurt' },
  ],
  count: 2,
};

test.describe('G: DataFrame (XLSX Upload + SQL)', () => {
  test.beforeAll(async () => {
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);

    // Tabellenliste mocken
    await page.route('**/api/dataframes/', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_TABLES),
        });
      } else {
        await route.continue();
      }
    });
  });

  test('Seite laedt und zeigt Tabellenliste', async ({ page }) => {
    await page.goto('/dataframes');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Hauptueberschrift
    await expect(page.getByText('DataFrame-Tabellen', { exact: false })).toBeVisible();

    // Tabellen-Zaehler
    await expect(page.getByText('2 Tabellen', { exact: false })).toBeVisible({ timeout: 10000 });

    // Tabellennamen
    await expect(page.getByText('transparenzliste_hessen', { exact: false })).toBeVisible();
    await expect(page.getByText('esf_hessen', { exact: false })).toBeVisible();

    // Zeilenanzahl
    await expect(page.getByText('1247 Zeilen', { exact: false })).toBeVisible();
  });

  test('Tabelle auswaehlen zeigt Schema und SQL-Abfrage', async ({ page }) => {
    // Info- und Summary-Endpunkte mocken
    await page.route('**/api/dataframes/transparenzliste_hessen/info', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TABLE_INFO),
      });
    });
    await page.route('**/api/dataframes/transparenzliste_hessen/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SUMMARY),
      });
    });

    await page.goto('/dataframes');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Tabelle anklicken
    await page.getByText('transparenzliste_hessen').first().click();

    // Schema sichtbar
    await expect(page.getByText('1247 Zeilen, 5 Spalten', { exact: false })).toBeVisible({ timeout: 10000 });

    // Spalten sichtbar
    await expect(page.getByText('beguenstigter', { exact: true })).toBeVisible();
    await expect(page.getByText('gesamtkosten', { exact: true }).first()).toBeVisible();

    // SQL-Abfrage-Bereich
    await expect(page.getByText('SQL-Abfrage', { exact: false })).toBeVisible();
    const sqlTextarea = page.getByLabel('SQL-Abfrage');
    await expect(sqlTextarea).toBeVisible();

    // Beispiel-Queries sollten sichtbar sein
    await expect(page.getByText('Alle Daten (10)', { exact: false })).toBeVisible();
    await expect(page.getByText('Anzahl Zeilen', { exact: false })).toBeVisible();
  });

  test('SQL-Abfrage ausfuehren zeigt Ergebnistabelle', async ({ page }) => {
    // Info und Summary
    await page.route('**/api/dataframes/transparenzliste_hessen/info', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TABLE_INFO),
      });
    });
    await page.route('**/api/dataframes/transparenzliste_hessen/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SUMMARY),
      });
    });
    // Query-Endpunkt
    await page.route('**/api/dataframes/transparenzliste_hessen/query**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_QUERY_RESULT),
      });
    });

    await page.goto('/dataframes');
    await page.waitForLoadState('networkidle');

    // Tabelle auswaehlen
    await page.getByText('transparenzliste_hessen').first().click();
    await expect(page.getByLabel('SQL-Abfrage')).toBeVisible({ timeout: 10000 });

    // Ausfuehren-Button klicken
    await page.getByRole('button', { name: /Ausführen/ }).click();

    // Ergebnisse pruefen
    await expect(page.getByText('2 Ergebnis(se)', { exact: false })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Stadt Kassel', { exact: false })).toBeVisible();
    await expect(page.getByText('Stadt Frankfurt', { exact: false })).toBeVisible();
  });

  test('Upload-Bereich ist sichtbar', async ({ page }) => {
    await page.goto('/dataframes');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Upload-Hinweis
    await expect(page.getByText('XLSX/CSV einlesen', { exact: false })).toBeVisible();
    await expect(page.getByText('XLSX oder CSV hierher ziehen', { exact: false })).toBeVisible();
  });

  test('Placeholder wenn keine Tabelle ausgewaehlt', async ({ page }) => {
    await page.goto('/dataframes');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Placeholder-Text im rechten Bereich
    await expect(page.getByText('Tabelle links auswählen oder XLSX hochladen', { exact: false })).toBeVisible();
  });

  test('SQL-Abfrage Fehler wird angezeigt', async ({ page }) => {
    await page.route('**/api/dataframes/transparenzliste_hessen/info', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TABLE_INFO),
      });
    });
    await page.route('**/api/dataframes/transparenzliste_hessen/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SUMMARY),
      });
    });
    await page.route('**/api/dataframes/transparenzliste_hessen/query**', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Syntaxfehler in SQL' }),
      });
    });

    await page.goto('/dataframes');
    await page.waitForLoadState('networkidle');

    await page.getByText('transparenzliste_hessen').first().click();
    await expect(page.getByLabel('SQL-Abfrage')).toBeVisible({ timeout: 10000 });

    // Ungueltige SQL eingeben
    const sqlTextarea = page.getByLabel('SQL-Abfrage');
    await sqlTextarea.fill('SELEKT * FORM {table}');
    await page.getByRole('button', { name: /Ausführen/ }).click();

    // Fehlermeldung sichtbar
    await expect(page.getByText('Syntaxfehler in SQL', { exact: false })).toBeVisible({ timeout: 10000 });
  });
});
