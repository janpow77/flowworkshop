import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test F: Wissensdatenbank (Knowledge Base / RAG)
 * Prueft Statistiken, Semantische Suche, Frage-Antwort und Upload-Bereich.
 */

const TEST_EMAIL = 'e2e-knowledge@test.local';

const MOCK_STATS = {
  documents: 5,
  chunks: 342,
  sources: [
    { source: 'VO_2021_1060', chunks: 180, filename: 'vo_2021_1060.pdf' },
    { source: 'VO_2021_1059', chunks: 162, filename: 'vo_2021_1059.pdf' },
  ],
};

const MOCK_SEARCH_RESULTS = {
  results: [
    { source: 'VO_2021_1060', text: 'Artikel 74 regelt die Verwaltungspruefungen...', score: 0.87, chunk_index: 12 },
    { source: 'VO_2021_1059', text: 'Die Pruefbehoerde fuehrt Vor-Ort-Kontrollen durch...', score: 0.72, chunk_index: 45 },
  ],
};

function buildSSEBody(tokens: string[]): string {
  let body = '';
  for (const t of tokens) {
    body += `data: ${JSON.stringify({ token: t })}\n\n`;
  }
  body += `data: ${JSON.stringify({ done: true, token_count: tokens.length, model: 'qwen3:14b', tok_per_s: 35.0 })}\n\n`;
  return body;
}

test.describe('F: Knowledge Base (RAG)', () => {
  test.beforeAll(async () => {
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);

    // Statistiken mocken
    await page.route('**/api/knowledge/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_STATS),
      });
    });
  });

  test('Seite laedt und zeigt Statistiken', async ({ page }) => {
    await page.goto('/knowledge');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Hauptueberschrift
    await expect(page.getByRole('heading', { name: 'Wissensdatenbank' })).toBeVisible();

    // Stats-Anzeige
    await expect(page.getByText('5 Dokumente', { exact: false })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('342 Textabschnitte', { exact: false })).toBeVisible();
  });

  test('Quellen werden aufgelistet', async ({ page }) => {
    await page.goto('/knowledge');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Quellen-Panel
    await expect(page.getByText('Quellen verwalten', { exact: false })).toBeVisible();

    // Quellenname sichtbar
    await expect(page.getByText('VO_2021_1060', { exact: false }).first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('VO_2021_1059', { exact: false }).first()).toBeVisible();

    // Chunk-Zaehler
    await expect(page.getByText('180 Abschnitte', { exact: false })).toBeVisible();
  });

  test('Semantische Suche liefert Ergebnisse', async ({ page }) => {
    await page.route('**/api/knowledge/search**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SEARCH_RESULTS),
      });
    });

    await page.goto('/knowledge');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Suchfeld
    const searchInput = page.getByLabel('Semantische Suche');
    await expect(searchInput).toBeVisible();

    // Suche ausfuehren
    await searchInput.fill('Verwaltungspruefung');
    await page.getByRole('button', { name: 'Suchen' }).click();

    // Ergebnisse
    await expect(page.getByText('Artikel 74 regelt', { exact: false })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Score: 0.87', { exact: false })).toBeVisible();
    await expect(page.getByText('Vor-Ort-Kontrollen', { exact: false })).toBeVisible();
  });

  test('Frage stellen mit SSE-Streaming', async ({ page }) => {
    await page.route('**/api/workshop/stream', async (route) => {
      const body = buildSSEBody([
        'Artikel 74 der VO 2021/1060 ',
        'regelt die Verwaltungspruefungen ',
        'fuer EFRE-gefoerderte Vorhaben.',
      ]);
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body,
      });
    });

    await page.goto('/knowledge');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Frage-Panel
    await expect(page.getByText('Frage stellen', { exact: false })).toBeVisible();

    // Eingabe
    const askInput = page.getByLabel('Frage an die Wissensdatenbank');
    await expect(askInput).toBeVisible();
    await askInput.fill('Was regelt Art. 74 VO 2021/1060?');

    // Absenden
    await page.getByRole('button', { name: 'Fragen' }).click();

    // Antwort sollte gestreamt werden
    await expect(page.getByText('Verwaltungspruefungen', { exact: false })).toBeVisible({ timeout: 10000 });
  });

  test('Upload-Bereich (Ingest Dropzone) ist sichtbar', async ({ page }) => {
    await page.goto('/knowledge');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Dropzone-Hinweistext
    await expect(page.getByText('Datei hierher ziehen oder klicken', { exact: false })).toBeVisible();

    // Unterstuetzte Formate
    await expect(page.getByText('PDF, XLSX, DOCX', { exact: false })).toBeVisible();
  });
});
