import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AgendaPage from '../AgendaPage';

// Mock-Daten
const mockMeta = {
  title: 'KI und LLMs in der EFRE-Pruefbehoerde',
  subtitle: 'Workshop zur Digitalisierung',
  date: '15.–17.07.2026',
  time: '09:00–17:00',
  location_short: 'Hannover',
  location_full: 'Hannover Congress Centrum',
  organizer: 'EFRE Pruefbehoerde',
  registration_deadline: '01.07.2026',
};

const mockDays = [
  {
    day: 1,
    label: 'Tag 1 — Dienstag, 15. Juli 2026',
    items: [
      {
        id: 'item-1',
        day: 1,
        time: '09:00',
        duration_minutes: 30,
        item_type: 'vortrag',
        title: 'Eroeffnung und Begruessung',
        speaker: 'Dr. Mueller',
        note: null,
        category: 'plenary',
        status: 'pending',
        started_at: null,
        scenario_id: null,
        sort_order: 1,
      },
      {
        id: 'item-2',
        day: 1,
        time: '09:30',
        duration_minutes: 45,
        item_type: 'workshop',
        title: 'Szenario 1: Dokumentenanalyse',
        speaker: null,
        note: null,
        category: 'plenary',
        status: 'pending',
        started_at: null,
        scenario_id: 1,
        sort_order: 2,
      },
    ],
  },
  {
    day: 2,
    label: 'Tag 2 — Mittwoch, 16. Juli 2026',
    items: [
      {
        id: 'item-3',
        day: 2,
        time: '09:00',
        duration_minutes: 60,
        item_type: 'diskussion',
        title: 'Erfahrungsaustausch',
        speaker: null,
        note: null,
        category: 'plenary',
        status: 'pending',
        started_at: null,
        scenario_id: null,
        sort_order: 1,
      },
    ],
  },
];

const mockWs5Days: typeof mockDays = [];

const mockTopics = [
  {
    id: 'topic-1',
    topic: 'Automatisierte Pruefung',
    question: 'Wie kann KI bei der VKO helfen?',
    organization: 'NBank',
    votes: 3,
  },
];

function mockFetchResponses() {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    if (url.includes('/api/event/meta')) {
      return Promise.resolve(new Response(JSON.stringify(mockMeta)));
    }
    if (url.includes('category=workshop5')) {
      return Promise.resolve(new Response(JSON.stringify(mockWs5Days)));
    }
    if (url.includes('/api/event/agenda/days')) {
      return Promise.resolve(new Response(JSON.stringify(mockDays)));
    }
    if (url.includes('/api/event/topics')) {
      return Promise.resolve(new Response(JSON.stringify(mockTopics)));
    }
    return Promise.resolve(new Response(JSON.stringify({})));
  });
}

function renderAgenda() {
  return render(
    <MemoryRouter>
      <AgendaPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mockFetchResponses();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('AgendaPage', () => {
  it('rendert den Header mit Titel', async () => {
    renderAgenda();
    await waitFor(() => {
      expect(screen.getByText(mockMeta.title)).toBeInTheDocument();
    });
  });

  it('zeigt Tages-Gruppen an', async () => {
    renderAgenda();
    await waitFor(() => {
      expect(screen.getByText('Tag 1 — Dienstag, 15. Juli 2026')).toBeInTheDocument();
      expect(screen.getByText('Tag 2 — Mittwoch, 16. Juli 2026')).toBeInTheDocument();
    });
  });

  it('schaltet auf Workshop-5-Tab um', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderAgenda();
    await waitFor(() => {
      expect(screen.getByText(mockMeta.title)).toBeInTheDocument();
    });
    const ws5Button = screen.getByRole('button', { name: /Workshop 5/i });
    await user.click(ws5Button);
    // Workshop 5 hat keine Tage -> Hinweistext
    await waitFor(() => {
      expect(screen.getByText(/Noch keine Programmpunkte/)).toBeInTheDocument();
    });
  });

  it('zeigt Programmpunkte innerhalb der Tages-Gruppen', async () => {
    renderAgenda();
    await waitFor(() => {
      expect(screen.getByText('Eroeffnung und Begruessung')).toBeInTheDocument();
      // Szenario-Titel taucht sowohl als h3 als auch als Link-Badge auf
      expect(screen.getAllByText(/Szenario 1/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Erfahrungsaustausch')).toBeInTheDocument();
    });
  });
});
