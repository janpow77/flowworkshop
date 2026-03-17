import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import RegisterPage from '../RegisterPage';

function renderRegister(route = '/register') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <RegisterPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.resolve(new Response(JSON.stringify({}), { status: 404 })),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('RegisterPage', () => {
  it('rendert den Stepper mit allen Schritten', () => {
    renderRegister();
    // "Persoenliche Daten" taucht sowohl im Stepper als auch im h2 auf
    expect(screen.getAllByText('Persoenliche Daten').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Themenvorschlag')).toBeInTheDocument();
    expect(screen.getByText(/Einreichung & Datenschutz/)).toBeInTheDocument();
    expect(screen.getByText('Bestaetigung')).toBeInTheDocument();
  });

  it('zeigt Step-1-Felder', () => {
    renderRegister();
    expect(screen.getByLabelText('Vorname')).toBeInTheDocument();
    expect(screen.getByLabelText('Nachname')).toBeInTheDocument();
    expect(screen.getByLabelText(/Organisation/)).toBeInTheDocument();
    expect(screen.getByLabelText(/E-Mail/i)).toBeInTheDocument();
  });

  it('Weiter-Button ist disabled ohne Pflichtfelder', () => {
    renderRegister();
    const weiterBtn = screen.getByRole('button', { name: /Weiter/i });
    expect(weiterBtn).toBeDisabled();
  });

  it('Weiter-Button wird aktiv nach Ausfuellen der Pflichtfelder', async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText('Vorname'), 'Max');
    await user.type(screen.getByLabelText('Nachname'), 'Mustermann');
    await user.type(screen.getByLabelText(/Organisation/), 'NBank');
    await user.type(screen.getByLabelText(/E-Mail/i), 'max@nbank.de');

    const weiterBtn = screen.getByRole('button', { name: /Weiter/i });
    expect(weiterBtn).not.toBeDisabled();
  });

  it('Invite-Token fuellt Felder vor', async () => {
    const inviteData = {
      first_name: 'Anna',
      last_name: 'Schmidt',
      organization: 'IB Sachsen-Anhalt',
      email: 'anna@ib-sa.de',
      department: 'Foerderabteilung',
      fund: 'EFRE',
      already_registered: false,
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.includes('/api/event/invite/')) {
        return Promise.resolve(new Response(JSON.stringify(inviteData)));
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 404 }));
    });

    renderRegister('/register?token=abc123');

    await waitFor(() => {
      expect(screen.getByLabelText('Vorname')).toHaveValue('Anna');
      expect(screen.getByLabelText('Nachname')).toHaveValue('Schmidt');
      expect(screen.getByLabelText(/Organisation/)).toHaveValue('IB Sachsen-Anhalt');
      expect(screen.getByLabelText(/E-Mail/i)).toHaveValue('anna@ib-sa.de');
    });
  });
});
