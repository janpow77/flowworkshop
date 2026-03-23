import { test, expect } from '@playwright/test';
import { registerTestUser, loginViaLocalStorage, assertNoErrorBoundary } from './helpers';

/**
 * Test H: Admin-Bereich
 * Prueft PIN-Login, Tab-Navigation, Agenda-Verwaltung, Meta-Daten und Registrations.
 */

const TEST_EMAIL = 'e2e-admin@test.local';

const MOCK_META = {
  title: 'Prueferworkshop der Pruefbehoerden 2026',
  subtitle: 'KI und LLMs in der EFRE-Pruefbehoerde',
  date: '12.–14. Mai 2026',
  time: '09:00–17:00',
  location_short: 'Hannover',
  location_full: 'ADAC Fahrsicherheitszentrum Hannover',
  organizer: 'EFRE-Pruefbehoerde Hessen',
  registration_deadline: '30. April 2026',
  qr_url: 'https://workshop.example.de',
  workshop_mode: false,
};

const MOCK_AGENDA = [
  { id: 'a1', time: '09:00', duration_minutes: 30, item_type: 'organisation', title: 'Begruessung', speaker: null, note: null, sort_order: 1 },
  { id: 'a2', time: '09:30', duration_minutes: 60, item_type: 'vortrag', title: 'KI im Foerderwesen', speaker: 'Dr. Mueller', note: null, sort_order: 2 },
  { id: 'a3', time: '10:30', duration_minutes: 15, item_type: 'pause', title: 'Kaffeepause', speaker: null, note: null, sort_order: 3 },
];

const MOCK_REGISTRATIONS = {
  registrations: [
    { id: 'r1', first_name: 'Max', last_name: 'Mustermann', organization: 'Behoerde A', email: 'max@test.de', created_at: '2026-03-20T10:00:00' },
    { id: 'r2', first_name: 'Erika', last_name: 'Beispiel', organization: 'Behoerde B', email: 'erika@test.de', created_at: '2026-03-21T14:30:00' },
  ],
};

const MOCK_TOPICS = {
  topics: [
    { id: 't1', topic: 'KI-gestuetzte Belegpruefung', organization: 'Behoerde A', votes: 5, visibility: 'public', question: 'Wie zuverlaessig ist die automatische Analyse?' },
    { id: 't2', topic: 'RAG im Vergaberecht', organization: null, votes: 3, visibility: 'public', question: null },
  ],
};

test.describe('H: Admin-Bereich', () => {
  test.beforeAll(async () => {
    await registerTestUser(TEST_EMAIL).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await loginViaLocalStorage(page, TEST_EMAIL);
  });

  test('PIN-Login-Formular wird angezeigt', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await assertNoErrorBoundary(page);

    // Admin-Zugang Ueberschrift
    await expect(page.getByText('Admin-Zugang', { exact: false })).toBeVisible();

    // PIN-Eingabefeld
    const pinInput = page.getByLabel('Admin-PIN');
    await expect(pinInput).toBeVisible();

    // Anmelden-Button
    await expect(page.getByRole('button', { name: 'Anmelden' })).toBeVisible();
  });

  test('Falscher PIN zeigt Fehlermeldung', async ({ page }) => {
    await page.route('**/api/event/admin/auth', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid PIN' }),
      });
    });

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    await page.getByLabel('Admin-PIN').fill('0000');
    await page.getByRole('button', { name: 'Anmelden' }).click();

    await expect(page.getByText('Falscher PIN', { exact: false })).toBeVisible({ timeout: 5000 });
  });

  test('Erfolgreicher Login zeigt Tabs und Agenda', async ({ page }) => {
    // Auth-Endpunkt mocken
    await page.route('**/api/event/admin/auth', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });
    await page.route('**/api/event/meta', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_META),
      });
    });
    await page.route('**/api/event/agenda', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_AGENDA),
      });
    });
    await page.route('**/api/event/admin/registrations**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_REGISTRATIONS),
      });
    });
    await page.route('**/api/event/admin/topics**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TOPICS),
      });
    });

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // PIN eingeben und anmelden
    await page.getByLabel('Admin-PIN').fill('1234');
    await page.getByRole('button', { name: 'Anmelden' }).click();

    // Workshop-Verwaltung Ueberschrift
    await expect(page.getByText('Workshop-Verwaltung', { exact: false })).toBeVisible({ timeout: 10000 });

    // Tabs sichtbar
    await expect(page.getByRole('button', { name: /Programm/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Workshop-Daten/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /QR-Code/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Anmeldungen/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Themen/ })).toBeVisible();

    // Agenda-Eintraege in der Programm-Tab sichtbar
    await expect(page.getByText('Begruessung', { exact: false })).toBeVisible();
    await expect(page.getByText('KI im Foerderwesen', { exact: false })).toBeVisible();
    await expect(page.getByText('Dr. Mueller', { exact: false })).toBeVisible();
  });

  test('Tab-Navigation: Anmeldungen anzeigen', async ({ page }) => {
    // Alle Endpunkte mocken (wie oben)
    await page.route('**/api/event/admin/auth', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    });
    await page.route('**/api/event/meta', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_META) });
    });
    await page.route('**/api/event/agenda', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AGENDA) });
    });
    await page.route('**/api/event/admin/registrations**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_REGISTRATIONS) });
    });
    await page.route('**/api/event/admin/topics**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_TOPICS) });
    });

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await page.getByLabel('Admin-PIN').fill('1234');
    await page.getByRole('button', { name: 'Anmelden' }).click();
    await expect(page.getByText('Workshop-Verwaltung')).toBeVisible({ timeout: 10000 });

    // Anmeldungen-Tab klicken
    await page.getByRole('button', { name: /Anmeldungen/ }).click();

    // Registrierungen sichtbar
    await expect(page.getByText('Max Mustermann', { exact: false })).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Erika Beispiel', { exact: false })).toBeVisible();
    await expect(page.getByText('Behoerde A', { exact: false })).toBeVisible();
  });

  test('Tab-Navigation: Themen anzeigen', async ({ page }) => {
    await page.route('**/api/event/admin/auth', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    });
    await page.route('**/api/event/meta', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_META) });
    });
    await page.route('**/api/event/agenda', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AGENDA) });
    });
    await page.route('**/api/event/admin/registrations**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_REGISTRATIONS) });
    });
    await page.route('**/api/event/admin/topics**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_TOPICS) });
    });

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await page.getByLabel('Admin-PIN').fill('1234');
    await page.getByRole('button', { name: 'Anmelden' }).click();
    await expect(page.getByText('Workshop-Verwaltung')).toBeVisible({ timeout: 10000 });

    // Themen-Tab klicken
    await page.getByRole('button', { name: /Themen/ }).click();

    // Themen sichtbar
    await expect(page.getByText('KI-gestuetzte Belegpruefung', { exact: false })).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('RAG im Vergaberecht', { exact: false })).toBeVisible();
  });

  test('Neuer Programmpunkt Formular sichtbar', async ({ page }) => {
    await page.route('**/api/event/admin/auth', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    });
    await page.route('**/api/event/meta', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_META) });
    });
    await page.route('**/api/event/agenda', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_AGENDA) });
    });
    await page.route('**/api/event/admin/registrations**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_REGISTRATIONS) });
    });
    await page.route('**/api/event/admin/topics**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_TOPICS) });
    });

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await page.getByLabel('Admin-PIN').fill('1234');
    await page.getByRole('button', { name: 'Anmelden' }).click();
    await expect(page.getByText('Workshop-Verwaltung')).toBeVisible({ timeout: 10000 });

    // "Neuer Programmpunkt" Formular
    await expect(page.getByText('Neuer Programmpunkt', { exact: false })).toBeVisible();

    // Eingabefelder fuer neuen Programmpunkt
    await expect(page.getByLabel('Uhrzeit')).toBeVisible();
    await expect(page.getByLabel('Titel')).toBeVisible();

    // Hinzufuegen-Button deaktiviert (leere Felder)
    const addBtn = page.getByRole('button', { name: /Hinzufügen/ });
    await expect(addBtn).toBeDisabled();
  });
});
