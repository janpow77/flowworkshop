import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test A: Navigation & Page Loading
 * Prueft, dass die Sidebar-Navigation funktioniert und alle wichtigen Seiten
 * ohne ErrorBoundary laden.
 */

const TEST_EMAIL = 'e2e-nav@test.local';

test.describe('A: Navigation & Page Loading', () => {
  test.beforeAll(async () => {
    // Testbenutzer registrieren (idempotent — Fehler bei Duplikat ist OK)
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    // Vor jedem Test: Login-Token setzen
    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('Startseite laedt ohne Fehler', async ({ page }) => {
    // Sidebar sollte sichtbar sein (Desktop-Viewport)
    const sidebar = page.locator('aside[aria-label="Hauptnavigation"]');
    await expect(sidebar).toBeVisible();

    // Startseite-Link in Sidebar sollte aktiv sein
    const homeLink = sidebar.getByRole('link', { name: 'Startseite' });
    await expect(homeLink).toBeVisible();

    await assertNoErrorBoundary(page);
  });

  test('Sidebar zeigt alle Navigationsgruppen', async ({ page }) => {
    const sidebar = page.locator('aside[aria-label="Hauptnavigation"]');

    // Gruppen-Labels pruefen
    await expect(sidebar.getByText('Veranstaltung')).toBeVisible();
    await expect(sidebar.getByText('Szenarien')).toBeVisible();

    // Arbeitsraeume-Links pruefen
    await expect(sidebar.getByRole('link', { name: 'Projekte' })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Wissensbasis' })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Datenanalyse' })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Unternehmenssuche' })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'AI Act' })).toBeVisible();
  });

  const pagesToTest = [
    { name: 'Projekte', path: '/projects', waitFor: 'Projekte' },
    { name: 'Wissensbasis', path: '/knowledge', waitFor: 'Wissensbasis' },
    { name: 'Datenanalyse', path: '/dataframes', waitFor: 'Datenanalyse' },
    { name: 'Unternehmenssuche', path: '/company-search', waitFor: 'Unternehmenssuche' },
    { name: 'AI Act', path: '/ai-act', waitFor: 'AI Act' },
    { name: 'Tagesordnung', path: '/agenda', waitFor: 'Tagesordnung' },
  ];

  for (const { name, path } of pagesToTest) {
    test(`Seite "${name}" laedt via Sidebar-Navigation`, async ({ page }) => {
      // Per Sidebar-Link navigieren (sofern Link existiert)
      const sidebar = page.locator('aside[aria-label="Hauptnavigation"]');
      const link = sidebar.getByRole('link', { name });

      if (await link.isVisible()) {
        await link.click();
        await page.waitForURL(`**${path}`);
      } else {
        // Direkt navigieren (z.B. wenn Szenarien gesperrt)
        await page.goto(path);
      }

      await page.waitForLoadState('networkidle');
      await assertNoErrorBoundary(page);
    });
  }

  test('404-Seite bei ungueltiger URL', async ({ page }) => {
    await page.goto('/diese-seite-gibt-es-nicht');
    await page.waitForLoadState('networkidle');
    // Sollte keine ErrorBoundary zeigen, sondern die NotFoundPage
    await assertNoErrorBoundary(page);
  });
});
