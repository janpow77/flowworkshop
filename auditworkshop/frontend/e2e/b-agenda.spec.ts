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
    // Header mit Meta-Infos sollte sichtbar sein
    await expect(page.getByText('Prueferworkshop der Pruefbehoerden 2026')).toBeVisible({ timeout: 10000 });
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
    await expect(page.getByText('Prueferworkshop der Pruefbehoerden 2026')).toBeVisible({ timeout: 10000 });
    const registerLink = page.getByRole('link', { name: 'Anmelden' });
    await expect(registerLink).toBeVisible();
    await registerLink.click();
    await expect(page).toHaveURL(/\/register/);
  });

  test('Meta-Informationen werden angezeigt', async ({ page }) => {
    await expect(page.getByText('Prueferworkshop der Pruefbehoerden 2026')).toBeVisible({ timeout: 10000 });
    // Ort und Datum
    await expect(page.getByText('Hannover').first()).toBeVisible();
    await expect(page.getByText('Mai 2026', { exact: false }).first()).toBeVisible();
  });

  test('Themenboard-Bereich ist vorhanden', async ({ page }) => {
    await expect(page.getByText('Dienstag')).toBeVisible({ timeout: 10000 });

    // Themenboard wird weiter unten auf der Seite angezeigt
    // Pruefen ob mindestens ein Topic sichtbar ist oder der Bereich existiert
    const topicSection = page.getByText('Themenvorschl', { exact: false });
    // Scrollen um den Bereich sichtbar zu machen
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);

    // Es gibt entweder Topics oder den Abschnitt
    const hasTopics = await topicSection.isVisible().catch(() => false);
    // Alternativ: pruefen ob bekannte Topics da sind
    const hasKnownTopic = await page.getByText('KI im Vergaberecht', { exact: false }).isVisible().catch(() => false);

    expect(hasTopics || hasKnownTopic).toBeTruthy();
  });
});
