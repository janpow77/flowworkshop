import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test J: AI Act Seite
 * Prueft statische Inhalte zur KI-Verordnung, Zeitstrahl und Leitplanken.
 */

const TEST_EMAIL = 'e2e-aiact@test.local';

test.describe('J: AI Act Page', () => {
  test.beforeAll(async () => {
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);
  });

  test('Seite laedt ohne Fehler', async ({ page }) => {
    await page.goto('/ai-act');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Hauptueberschrift
    await expect(page.getByText('Rote Linien und Vorsichtspunkte', { exact: false })).toBeVisible({ timeout: 10000 });
  });

  test('Hero-Section mit Kurzbeschreibung', async ({ page }) => {
    await page.goto('/ai-act');
    await page.waitForLoadState('networkidle');

    // Eyebrow-Text
    await expect(page.getByText('AI Act für Prüfer', { exact: false })).toBeVisible();

    // Beschreibungstext
    await expect(page.getByText('Prüfer-Merkblatt', { exact: false })).toBeVisible();
  });

  test('Kurzfassung: Was man nicht einfach tun sollte', async ({ page }) => {
    await page.goto('/ai-act');
    await page.waitForLoadState('networkidle');

    // Kurzfassungs-Box
    await expect(page.getByText('Kurzfassung', { exact: false })).toBeVisible();
    await expect(page.getByText('Was man als Prüfer nicht einfach tun sollte', { exact: false })).toBeVisible();

    // Einzelne Punkte
    await expect(page.getByText('automatisierte Freigabe oder Sperre', { exact: false })).toBeVisible();
    await expect(page.getByText('verdeckter KI-Einsatz', { exact: false })).toBeVisible();
  });

  test('Drei Karten: Verboten, Nicht blind uebernehmen, Prueferische Leitplanke', async ({ page }) => {
    await page.goto('/ai-act');
    await page.waitForLoadState('networkidle');

    // Karte 1: Verboten
    await expect(page.getByText('Verboten', { exact: false }).first()).toBeVisible();
    await expect(page.getByText('Social Scoring', { exact: false })).toBeVisible();

    // Karte 2: Nicht blind uebernehmen
    await expect(page.getByText('Nicht blind übernehmen', { exact: false })).toBeVisible();
    await expect(page.getByText('Keine negative Entscheidung allein aus einem Modelltreffer', { exact: false })).toBeVisible();

    // Karte 3: Prueferische Leitplanke
    await expect(page.getByText('Prüferische Leitplanke', { exact: false })).toBeVisible();
    await expect(page.getByText('KI ist Assistenz, nicht Entscheidungsträger', { exact: false })).toBeVisible();
  });

  test('Zeitstrahl zeigt wichtige Daten', async ({ page }) => {
    await page.goto('/ai-act');
    await page.waitForLoadState('networkidle');

    // Zeitstrahl-Ueberschrift
    await expect(page.getByText('Zeitstrahl', { exact: false })).toBeVisible();

    // Einzelne Zeitpunkte
    await expect(page.getByText('1. August 2024', { exact: false })).toBeVisible();
    await expect(page.getByText('AI Act in Kraft getreten', { exact: false })).toBeVisible();
    await expect(page.getByText('2. August 2026', { exact: false })).toBeVisible();
    await expect(page.getByText('grundsätzlich anwendbar', { exact: false })).toBeVisible();
  });

  test('Link zurueck zur Unternehmenssuche', async ({ page }) => {
    await page.goto('/ai-act');
    await page.waitForLoadState('networkidle');

    const backLink = page.getByRole('link', { name: /Unternehmenssuche/ }).first();
    await expect(backLink).toBeVisible();
  });

  test('Dokumentation-Hinweis sichtbar', async ({ page }) => {
    await page.goto('/ai-act');
    await page.waitForLoadState('networkidle');

    // "Dokumentation zaehlt" Abschnitt
    await expect(page.getByText('Dokumentation zählt', { exact: false })).toBeVisible();
    await expect(page.getByText('Datenquelle, Suchstand, Modellgrenzen', { exact: false })).toBeVisible();
  });
});
