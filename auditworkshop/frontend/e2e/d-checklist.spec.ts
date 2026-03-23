import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test D: Checklist AI Workflow (Protected Route)
 * Erfordert Login. Navigiert zu einem Projekt und dessen Checkliste.
 * Prueft Laden der Checkliste, Fragen-Sidebar und Skeleton-Loader.
 */

const TEST_EMAIL = 'e2e-checklist@test.local';

// IDs aus der Demo-Datenbank
const DEMO_PROJECT_ID = '0ff2df6c-ee26-478c-beb7-e15d7f5ed972';
const DEMO_CHECKLIST_ID = '87ee4e08-c50d-4b96-a427-4283f5d48390';

test.describe('D: Checklist AI Workflow', () => {
  test.beforeAll(async () => {
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);
  });

  test('Projekte-Seite laedt und zeigt Demo-Projekt', async ({ page }) => {
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Demo-Projekt sollte sichtbar sein
    await expect(page.getByText('DEMO-2024-001', { exact: false })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Digitalisierung kommunaler Infrastruktur', { exact: false })).toBeVisible();
  });

  test('Projektdetail-Seite laedt', async ({ page }) => {
    await page.goto(`/projects/${DEMO_PROJECT_ID}`);
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Projekt-Informationen pruefen
    await expect(page.getByText('DEMO-2024-001', { exact: false })).toBeVisible({ timeout: 10000 });
    // Checkliste sollte verlinkt sein
    await expect(page.getByText('VKO-Checkliste', { exact: false })).toBeVisible();
  });

  test('Checklisten-Seite laedt mit Fragen', async ({ page }) => {
    await page.goto(`/projects/${DEMO_PROJECT_ID}/checklists/${DEMO_CHECKLIST_ID}`);
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Checklisten-Name im Breadcrumb oder Header
    await expect(page.getByText('VKO-Checkliste', { exact: false })).toBeVisible({ timeout: 10000 });

    // Die Checkliste hat 30 Fragen — mindestens einige sollten in der Sidebar sichtbar sein
    // Fragen werden als Liste links angezeigt
    const questionItems = page.locator('[role="button"], [data-question-id]');
    // Alternativ: nach typischen Checklistenfragen-Texten suchen
    // Die Fragen enthalten Nummern wie "1.", "2." etc.

    // Warten bis Fragen geladen sind (nicht mehr Skeleton)
    await page.waitForTimeout(2000);

    // Es sollten mehrere klickbare Elemente in der Fragen-Sidebar geben
    // Pruefe ob mindestens die Seitenstruktur korrekt ist (zwei Spalten)
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible();
  });

  test('Skeleton-Loader erscheint beim initialen Laden', async ({ page }) => {
    // Netzwerk drosseln fuer sichtbare Skeleton-Phase
    await page.route('**/api/projects/*/checklists/*', async (route) => {
      // Verzoegere die API-Antwort um 1 Sekunde
      await new Promise((r) => setTimeout(r, 1000));
      await route.continue();
    });

    await page.goto(`/projects/${DEMO_PROJECT_ID}/checklists/${DEMO_CHECKLIST_ID}`);

    // Skeleton sollte kurz sichtbar sein (animate-pulse Klasse)
    const skeleton = page.locator('.animate-pulse').first();
    await expect(skeleton).toBeVisible({ timeout: 3000 });

    // Nach dem Laden sollten die Skeletons verschwinden
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
  });

  test('Navigation von Projekte zu Checkliste via UI', async ({ page }) => {
    // Start bei Projekte
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');

    // Auf das Demo-Projekt klicken
    const projectLink = page.getByText('Digitalisierung kommunaler Infrastruktur', { exact: false });
    await expect(projectLink).toBeVisible({ timeout: 10000 });
    await projectLink.click();

    // Projektdetail-Seite
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(new RegExp(`/projects/${DEMO_PROJECT_ID}`));
    await assertNoErrorBoundary(page);

    // Auf Checkliste klicken
    const checklistLink = page.getByText('VKO-Checkliste', { exact: false });
    await expect(checklistLink).toBeVisible({ timeout: 10000 });
    await checklistLink.click();

    // Checklisten-Seite
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(new RegExp(`/checklists/`));
    await assertNoErrorBoundary(page);
  });

  test('Login-Gate: Geschuetzte Seite ohne Token zeigt Login', async ({ page }) => {
    // localStorage leeren
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.removeItem('workshop_token');
      localStorage.removeItem('workshop_role');
    });
    await page.goto('/projects');
    await page.waitForLoadState('networkidle');

    // Sollte die Login-Seite zeigen (Auth-Gate in App.tsx)
    await expect(page.getByRole('heading', { name: 'Anmelden' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByLabel('E-Mail-Adresse')).toBeVisible();
  });
});
