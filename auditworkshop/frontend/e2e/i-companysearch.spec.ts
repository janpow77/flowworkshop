import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test I: Unternehmenssuche (CompanySearch)
 * Prueft Laden, Suche, Ergebnis-Cards und Filter.
 */

const TEST_EMAIL = 'e2e-company@test.local';

const MOCK_BENEFICIARY_SOURCES = {
  sources: [
    { source: 'transparenzliste_hessen', bundesland: 'Hessen', fonds: 'EFRE', periode: '2021-2027', row_count: 1247 },
    { source: 'transparenzliste_esf', bundesland: 'Hessen', fonds: 'ESF+', periode: '2021-2027', row_count: 583 },
  ],
};

const MOCK_REFERENCE_SOURCES = {
  sources: [
    { table_name: 'ref_sanctions_eu_2024', source: 'sanctions_eu_2024', row_count: 12500, dataset_group: null, registry_type: 'sanctions', filename: 'eu_sanctions_2024.xlsx' },
  ],
};

const MOCK_SEARCH_EMPTY = {
  query: '',
  scope: 'all',
  summary: {
    sources_considered: 2,
    records_scanned: 1830,
    matches: 0,
    companies: 0,
    total_match_volume: 0,
  },
  companies: [],
  records: [],
};

const MOCK_SEARCH_RESULT = {
  query: 'Kassel',
  scope: 'all',
  summary: {
    sources_considered: 2,
    records_scanned: 1830,
    matches: 15,
    companies: 2,
    total_match_volume: 3500000,
  },
  companies: [
    {
      company_name: 'Stadt Kassel',
      total_kosten: 2000000,
      total_kosten_label: '2.000.000 EUR',
      project_count: 5,
      match_score: 0.95,
      sources: ['transparenzliste_hessen'],
      bundeslaender: ['Hessen'],
      fonds: ['EFRE'],
      standorte: ['Kassel'],
      aktenzeichen: ['AZ-2024-001'],
      matched_fields: ['name', 'standort'],
      projects: [
        {
          project_name: 'Digitalisierung Buergerservice',
          aktenzeichen: 'AZ-2024-001',
          location: 'Kassel',
          category: 'Digitalisierung',
          kosten: 500000,
          kosten_label: '500.000 EUR',
          source: 'transparenzliste_hessen',
          bundesland: 'Hessen',
          fonds: 'EFRE',
          periode: '2021-2027',
          matched_fields: ['name'],
          match_score: 0.9,
        },
      ],
    },
    {
      company_name: 'Universitaet Kassel',
      total_kosten: 1500000,
      total_kosten_label: '1.500.000 EUR',
      project_count: 3,
      match_score: 0.85,
      sources: ['transparenzliste_hessen'],
      bundeslaender: ['Hessen'],
      fonds: ['EFRE'],
      standorte: ['Kassel'],
      aktenzeichen: ['AZ-2024-002'],
      matched_fields: ['name'],
      projects: [],
    },
  ],
  records: [],
};

const MOCK_REFERENCE_SEARCH_EMPTY = {
  query: '',
  summary: { sources_considered: 1, matches: 0 },
  hits: [],
};

const MOCK_REFERENCE_SEARCH = {
  query: 'Kassel',
  summary: { sources_considered: 1, matches: 0 },
  hits: [],
};

test.describe('I: Unternehmenssuche (CompanySearch)', () => {
  test.beforeAll(async () => {
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);

    // Basis-Endpunkte mocken
    await page.route('**/api/system/profile', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          gpu_name: 'NVIDIA RTX 5070 Ti',
          vram_total_gb: 16.0,
          ollama_model: 'qwen3:14b',
          embedding_model: 'paraphrase-multilingual-mpnet-base-v2',
        }),
      });
    });
    await page.route('**/api/beneficiaries/sources', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_BENEFICIARY_SOURCES),
      });
    });
    await page.route('**/api/reference-data/sources', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_REFERENCE_SOURCES),
      });
    });
    // Standard-Suchergebnisse (leere Suche beim Laden)
    await page.route('**/api/beneficiaries/search**', async (route) => {
      const url = route.request().url();
      if (url.includes('q=Kassel') || url.includes('q=kassel')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_SEARCH_RESULT),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_SEARCH_EMPTY),
        });
      }
    });
    await page.route('**/api/reference-data/search**', async (route) => {
      const url = route.request().url();
      if (url.includes('q=Kassel') || url.includes('q=kassel')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_REFERENCE_SEARCH),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_REFERENCE_SEARCH_EMPTY),
        });
      }
    });
  });

  test('Seite laedt ohne ErrorBoundary', async ({ page }) => {
    await page.goto('/company-search');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Hauptueberschrift
    await expect(page.getByText('Unternehmenssuche', { exact: false }).first()).toBeVisible({ timeout: 10000 });
  });

  test('Suchfeld ist vorhanden', async ({ page }) => {
    await page.goto('/company-search');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Es gibt ein Input-Element fuer die Suche
    const inputs = page.locator('input');
    const count = await inputs.count();
    expect(count).toBeGreaterThan(0);
  });

  test('Suche liefert Ergebnis-Cards', async ({ page }) => {
    await page.goto('/company-search');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Suchbegriff eingeben
    const firstInput = page.locator('input').first();
    await firstInput.fill('Kassel');

    // Warten auf Ergebnisse (deferredValue triggert automatisch nach Timeout)
    await expect(page.getByText('Stadt Kassel', { exact: false }).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Universitaet Kassel', { exact: false }).first()).toBeVisible();
  });

  test('Leerer Zustand ohne Suchergebnisse', async ({ page }) => {
    await page.goto('/company-search');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Ohne Suche sollte "Stadt Kassel" nicht sichtbar sein
    const kasselVisible = await page.getByText('Stadt Kassel').isVisible().catch(() => false);
    expect(kasselVisible).toBeFalsy();
  });

  test('AI Act Link ist sichtbar', async ({ page }) => {
    await page.goto('/company-search');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    await expect(page.getByRole('link', { name: /AI Act/ }).first()).toBeVisible();
  });
});
