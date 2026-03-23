import { test, expect } from '@playwright/test';
import { assertNoErrorBoundary } from './helpers';

/**
 * Test C: Registration & Topic Submission (Public Route)
 * Durchlaeuft den 4-Schritt-Registrierungsprozess:
 *   Step 1: Persoenliche Daten
 *   Step 2: Thema & Dokumente
 *   Step 3: Sichtbarkeit & Datenschutz
 *   Step 4: Bestaetigung
 */

test.describe('C: Registration Flow', () => {
  // Eindeutige E-Mail pro Testlauf
  const uniqueEmail = `e2e-reg-${Date.now()}@test.local`;

  test('Vollstaendiger Registrierungsprozess (Step 1-4)', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // --- Step 1: Persoenliche Daten ---
    await expect(page.getByRole('heading', { name: 'Persönliche Daten' })).toBeVisible();

    // Formularfelder ausfuellen
    await page.getByLabel('Vorname').fill('Max');
    await page.getByLabel('Nachname').fill('Mustermann');
    await page.getByLabel('Organisation').fill('Testbehoerde Hessen');
    await page.getByLabel('Dienstliche E-Mail').fill(uniqueEmail);
    await page.getByLabel('Fachbereich').fill('Abt. III');

    // Weiter-Button klicken
    const weiterBtn = page.getByRole('button', { name: 'Weiter' });
    await expect(weiterBtn).toBeEnabled();
    await weiterBtn.click();

    // --- Step 2: Thema & Dokumente ---
    await expect(page.getByText('Themenvorschlag')).toBeVisible();

    await page.getByLabel('Themenvorschlag').fill('KI-gestuetzte Belegpruefung');
    await page.getByLabel('Konkrete Fragestellung').fill('Wie zuverlaessig ist die automatische Dokumentenanalyse?');
    await page.getByLabel('Anmerkungen').fill('Erfahrungsbericht aus der Praxis');

    // Datei-Upload-Bereich sollte sichtbar sein
    await expect(page.getByText('Dokumente beifügen (optional)')).toBeVisible();

    await weiterBtn.click();

    // --- Step 3: Sichtbarkeit & Datenschutz ---
    await expect(page.getByRole('heading', { name: 'Sichtbarkeit & Datenschutz' })).toBeVisible();

    // Oeffentlich ist standardmaessig ausgewaehlt
    const publicRadio = page.getByText('Öffentlich').locator('..');
    await expect(publicRadio).toBeVisible();

    // Datenschutz-Checkbox anklicken (Pflicht)
    const privacyCheckbox = page.getByText('Datenschutzhinweis', { exact: false }).locator('..').locator('input[type="checkbox"]');
    await privacyCheckbox.check();

    // Absenden-Button sollte jetzt aktiv sein
    const submitBtn = page.getByRole('button', { name: 'Absenden' });
    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    // --- Step 4: Bestaetigung ---
    await expect(page.getByText('Anmeldung erfolgreich')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('KI-gestuetzte Belegpruefung', { exact: false })).toBeVisible();

    // Links zur Startseite und Tagesordnung sollten im Bestaetigungs-Bereich sichtbar sein
    await expect(page.getByRole('link', { name: 'Zum Login' })).toBeVisible();
    await expect(page.getByRole('main').locator('a').filter({ hasText: /^Tagesordnung$/ })).toBeVisible();
  });

  test('Step 1 Validierung: Weiter-Button deaktiviert ohne Pflichtfelder', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');

    // Weiter-Button sollte initial deaktiviert sein (Felder leer)
    const weiterBtn = page.getByRole('button', { name: 'Weiter' });
    await expect(weiterBtn).toBeDisabled();

    // Nur Vorname ausfuellen — reicht nicht
    await page.getByLabel('Vorname').fill('Test');
    await expect(weiterBtn).toBeDisabled();

    // Alle Pflichtfelder ausfuellen
    await page.getByLabel('Nachname').fill('User');
    await page.getByLabel('Organisation').fill('Org');
    await page.getByLabel('Dienstliche E-Mail').fill('valid@email.de');
    await expect(weiterBtn).toBeEnabled();
  });

  test('Step 3 Validierung: Absenden nur mit Datenschutz-Checkbox', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');

    // Schnell durch Step 1 und 2
    await page.getByLabel('Vorname').fill('Val');
    await page.getByLabel('Nachname').fill('Test');
    await page.getByLabel('Organisation').fill('Org');
    await page.getByLabel('Dienstliche E-Mail').fill(`val-${Date.now()}@test.local`);
    await page.getByRole('button', { name: 'Weiter' }).click();

    await page.getByLabel('Themenvorschlag').fill('Validierungstest');
    await page.getByRole('button', { name: 'Weiter' }).click();

    // Absenden-Button sollte deaktiviert sein (Datenschutz nicht akzeptiert)
    const submitBtn = page.getByRole('button', { name: 'Absenden' });
    await expect(submitBtn).toBeDisabled();
  });

  test('Zurueck-Navigation zwischen Steps', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');

    // Step 1 ausfuellen und weiter
    await page.getByLabel('Vorname').fill('Nav');
    await page.getByLabel('Nachname').fill('Test');
    await page.getByLabel('Organisation').fill('Org');
    await page.getByLabel('Dienstliche E-Mail').fill('nav@test.local');
    await page.getByRole('button', { name: 'Weiter' }).click();

    // Step 2 sollte sichtbar sein
    await expect(page.getByText('Themenvorschlag')).toBeVisible();

    // Zurueck-Button klicken
    await page.getByRole('button', { name: 'Zurück' }).click();

    // Step 1 sollte wieder sichtbar sein mit erhaltenen Daten
    await expect(page.getByLabel('Vorname')).toHaveValue('Nav');
  });
});
