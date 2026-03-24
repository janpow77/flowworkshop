import { test, expect } from '@playwright/test';
import { assertNoErrorBoundary } from './helpers';

/**
 * Test B: Agenda (Public Route)
 * Die Tagesordnung ist oeffentlich zugaenglich (kein Login erforderlich).
 * Prueft Tage, Agenda-Eintraege und Themenboard.
 */

test.describe('B: Agenda (Public Route)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/agenda');
    await page.waitForLoadState('networkidle');
  });

  test('Agenda-Seite laedt ohne Fehler', async ({ page }) => {
    await assertNoErrorBoundary(page);
    // Header mit Meta-Infos sollte sichtbar sein (echte Umlaute im UI)
    await expect(page.getByRole('heading', { name: /Prüferworkshop der Prüfbehörden 2026/ })).toBeVisible({ timeout: 10000 });
  });

  test('Zeigt 3 Tage: Dienstag, Mittwoch, Donnerstag', async ({ page }) => {
    // Warten bis die Tage geladen sind (Skeleton verschwindet)
    await expect(page.getByText('Dienstag')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Mittwoch')).toBeVisible();
    await expect(page.getByText('Donnerstag')).toBeVisible();
  });

  test('Zeigt typische Agenda-Eintraege', async ({ page }) => {
    // Warten auf Laden
    await expect(page.getByText('Dienstag')).toBeVisible({ timeout: 10000 });

    // Typische Eintraege pruefen (Titel aus der Agenda-API)
    const expectedItems = [
      'Begruessung',
      'Kaffeepause',
      'Beginn der Workshops',
      'Beginn der Veranstaltung',
    ];

    let found = 0;
    for (const item of expectedItems) {
      const locator = page.getByText(item, { exact: false });
      if (await locator.first().isVisible().catch(() => false)) {
        found++;
      }
    }

    // Mindestens 2 der erwarteten Eintraege sollten sichtbar sein
    expect(found).toBeGreaterThanOrEqual(2);
  });

  test('Anmelden-Button ist sichtbar und fuehrt zu /register', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Prüferworkshop der Prüfbehörden 2026/ })).toBeVisible({ timeout: 10000 });
    const registerLink = page.getByRole('link', { name: 'Anmelden' });
    await expect(registerLink).toBeVisible();
    await registerLink.click();
    await expect(page).toHaveURL(/\/register/);
  });

  test('Meta-Informationen werden angezeigt', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Prüferworkshop der Prüfbehörden 2026/ })).toBeVisible({ timeout: 10000 });
    // Ort und Datum
    await expect(page.getByText('Hannover').first()).toBeVisible();
    await expect(page.getByText('Mai 2026', { exact: false }).first()).toBeVisible();
  });

  test('Wichtige Adressen und Programm-Bereiche sind vorhanden', async ({ page }) => {
    await expect(page.getByText('Dienstag')).toBeVisible({ timeout: 10000 });

    // Scrollen um untere Bereiche sichtbar zu machen
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);

    // "Wichtige Adressen"-Bereich oder "Eingereichte Themen" sollte sichtbar sein
    const hasAddresses = await page.getByText('Wichtige Adressen', { exact: false }).isVisible().catch(() => false);
    const hasTopics = await page.getByText('Eingereichte Themen', { exact: false }).isVisible().catch(() => false);

    expect(hasAddresses || hasTopics).toBeTruthy();
  });
});
