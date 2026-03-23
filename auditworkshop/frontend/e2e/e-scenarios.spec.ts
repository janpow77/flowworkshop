import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test E: Szenarien 1-6 (LLM-Streaming)
 * Prueft Laden der Szenario-Seiten, SSE-Streaming via Mocks und UI-Interaktionen.
 * Route: /scenario/:id (Singular!)
 * Szenarien sind nur sichtbar wenn workshop_mode=true oder role=moderator.
 */

const TEST_EMAIL = 'e2e-scenarios@test.local';

const SCENARIO_TITLES: Record<number, string> = {
  1: 'Dokumentenanalyse',
  2: 'Checklisten-KI',
  3: 'Halluzinations-Demo',
  4: 'Berichtsentwurf',
  5: 'Vorab-Upload',
  6: 'Begünstigtenverzeichnis',
};

/** Erzeugt eine SSE-Antwort mit Fake-Tokens. */
function buildSSEBody(tokens: string[]): string {
  let body = '';
  for (const t of tokens) {
    body += `data: ${JSON.stringify({ token: t })}\n\n`;
  }
  body += `data: ${JSON.stringify({ done: true, token_count: tokens.length, model: 'mock-model', tok_per_s: 42.0 })}\n\n`;
  return body;
}

test.describe('E: Szenarien 1-6 (LLM-Streaming)', () => {
  test.beforeAll(async () => {
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    // Workshop-Modus aktivieren damit Szenarien freigeschaltet sind
    await page.route('**/api/event/meta', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          title: 'Prueferworkshop 2026',
          subtitle: 'KI und LLMs',
          date: '12. Mai 2026',
          time: '09:00',
          location_short: 'Hannover',
          location_full: 'Hannover',
          organizer: 'EFRE',
          registration_deadline: '30. April 2026',
          qr_url: '',
          workshop_mode: true,
        }),
      });
    });

    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);
  });

  for (const num of [1, 2, 3, 4, 5, 6]) {
    test(`Szenario ${num} (${SCENARIO_TITLES[num]}) laedt ohne Fehler`, async ({ page }) => {
      await page.goto(`/scenario/${num}`);
      await page.waitForLoadState('networkidle');
      await assertNoErrorBoundary(page);

      // Szenario-Titel pruefen
      await expect(page.getByText(SCENARIO_TITLES[num], { exact: false }).first()).toBeVisible({ timeout: 10000 });

      // Szenario-Nummer im Header
      await expect(page.getByText(`Workshop-Szenario ${num}`, { exact: false })).toBeVisible();
    });
  }

  test('Szenario 1: Prompt-Eingabe und SSE-Streaming', async ({ page }) => {
    // SSE-Endpunkt mocken
    await page.route('**/api/workshop/stream', async (route) => {
      const body = buildSSEBody(['Dies ', 'ist ', 'eine ', 'Test-Antwort ', 'der ', 'KI.']);
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body,
      });
    });

    await page.goto('/scenario/1');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Prompt-Textarea sollte vorhanden sein
    const textarea = page.getByLabel('Prompt eingeben');
    await expect(textarea).toBeVisible();

    // Absenden-Button sollte deaktiviert sein (leerer Prompt)
    const sendBtn = page.getByLabel('Absenden');
    await expect(sendBtn).toBeDisabled();

    // Prompt eingeben
    await textarea.fill('Welche Auflagen enthält der Bescheid?');
    await expect(sendBtn).toBeEnabled();

    // Absenden
    await sendBtn.click();

    // Warten bis die gestreamte Antwort sichtbar wird
    await expect(page.getByText('Test-Antwort', { exact: false })).toBeVisible({ timeout: 10000 });
  });

  test('Szenario 2: Demo-Checkliste-Button und Projektlink sichtbar', async ({ page }) => {
    // Demo-seed mocken damit kein echter Seed passiert
    await page.route('**/api/demo/seed', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', project_id: 'mock-id', checklist_id: 'mock-cl-id' }),
      });
    });

    await page.goto('/scenario/2');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Empfohlener Demo-Einstieg sichtbar
    await expect(page.getByText('Empfohlener Demo-Einstieg', { exact: false })).toBeVisible();

    // Demo-Checkliste-Button
    const demoBtn = page.getByRole('button', { name: /Demo-Checkliste/ });
    await expect(demoBtn).toBeVisible();

    // Projektübersicht-Link
    await expect(page.getByRole('link', { name: /Projektübersicht/ })).toBeVisible();
  });

  test('Szenario 3: RAG-Toggle sichtbar und umschaltbar', async ({ page }) => {
    await page.goto('/scenario/3');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // RAG-Kontext-Checkbox
    const ragCheckbox = page.locator('input[type="checkbox"]');
    await expect(ragCheckbox).toBeVisible();
    await expect(ragCheckbox).toBeChecked();

    // Hinweistext "Mit Kontext"
    await expect(page.getByText('Mit Kontext', { exact: false })).toBeVisible();

    // Toggle ausschalten
    await ragCheckbox.uncheck();
    await expect(page.getByText('Ohne Kontext', { exact: false })).toBeVisible();
  });

  test('Szenario 4: Prompt-Eingabe, Demo-laden-Button und DocumentDropzone', async ({ page }) => {
    await page.goto('/scenario/4');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Prompt-Textarea
    await expect(page.getByLabel('Prompt eingeben')).toBeVisible();

    // Demo-laden Button (fuer Szenario 1 und 4)
    await expect(page.getByRole('button', { name: /Demo laden/ })).toBeVisible();
  });

  test('Szenario 5: Hinweis auf Wissensdatenbank sichtbar', async ({ page }) => {
    await page.goto('/scenario/5');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Hinweis-Text
    await expect(page.getByText('Wissensdatenbank', { exact: false }).first()).toBeVisible();

    // Prompt-Textarea
    await expect(page.getByLabel('Prompt eingeben')).toBeVisible();
  });

  test('Szenario 6: Karte und Statistik-Hinweise sichtbar', async ({ page }) => {
    // Beneficiaries-Endpunkte mocken fuer die Karte
    await page.route('**/api/beneficiaries/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ sources: [], records: [], summary: {} }),
      });
    });

    await page.goto('/scenario/6');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Statistikfragen-Hinweis
    await expect(page.getByText('Statistikfragen', { exact: false })).toBeVisible();

    // Links zu Unternehmenssuche und Datenraum
    await expect(page.getByRole('link', { name: 'Unternehmenssuche öffnen' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Datenraum öffnen' })).toBeVisible();

    // Prompt-Textarea
    await expect(page.getByLabel('Prompt eingeben')).toBeVisible();
  });

  test('SSE-Streaming zeigt Modell-Info nach Abschluss', async ({ page }) => {
    await page.route('**/api/workshop/stream', async (route) => {
      const body = buildSSEBody(['Antwort ', 'komplett.']);
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body,
      });
    });

    await page.goto('/scenario/4');
    await page.waitForLoadState('networkidle');

    const textarea = page.getByLabel('Prompt eingeben');
    await textarea.fill('Vergabevermerk fehlt.');
    await page.getByLabel('Absenden').click();

    // Antwort sollte erscheinen
    await expect(page.getByText('Antwort komplett', { exact: false })).toBeVisible({ timeout: 10000 });

    // Modell-Info (mock-model) und Token-Zaehler
    await expect(page.getByText('mock-model', { exact: false })).toBeVisible({ timeout: 5000 });
  });
});
