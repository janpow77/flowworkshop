import { type Page } from '@playwright/test';

const API_BASE = 'http://localhost:8006';

/**
 * Registriert einen Testbenutzer ueber die API und gibt die registration_id zurueck.
 */
export async function registerTestUser(
  email: string,
  firstName = 'E2E',
  lastName = 'Tester',
  organization = 'E2E Testbehoerde',
): Promise<string> {
  const res = await fetch(`${API_BASE}/api/event/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      first_name: firstName,
      last_name: lastName,
      organization,
      email,
      department: null,
      fund: null,
      privacy_accepted: true,
      anthropic_consent: false,
    }),
  });
  const data = await res.json();
  return data.registration_id;
}

/**
 * Loggt sich ueber die API ein und gibt den Token zurueck.
 */
export async function getAuthToken(email: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  const data = await res.json();
  return data.token;
}

/**
 * Setzt den Auth-Token im localStorage und laedt die Seite neu.
 * So wird der Auth-Gate in App.tsx umgangen.
 */
export async function loginViaLocalStorage(page: Page, email: string, role = 'participant'): Promise<void> {
  const token = await getAuthToken(email);
  await page.evaluate(
    ({ t, r }) => {
      localStorage.setItem('workshop_token', t);
      localStorage.setItem('workshop_role', r);
    },
    { t: token, r: role },
  );
}

/**
 * Sicherstellen, dass kein ErrorBoundary sichtbar ist.
 */
export async function assertNoErrorBoundary(page: Page): Promise<void> {
  const errorHeading = page.getByText('Ein Fehler ist aufgetreten');
  // Warten dass die Seite geladen ist, dann pruefen dass kein Error sichtbar ist
  await page.waitForTimeout(300);
  const visible = await errorHeading.isVisible().catch(() => false);
  if (visible) {
    throw new Error('ErrorBoundary ist sichtbar — die Seite hat einen Renderfehler.');
  }
}
