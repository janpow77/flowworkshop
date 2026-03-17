import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import LlmResponsePanel from '../workshop/LlmResponsePanel';

describe('LlmResponsePanel', () => {
  it('zeigt Streaming-Text an', () => {
    render(
      <LlmResponsePanel
        response="Das ist eine KI-Antwort"
        streaming={false}
      />,
    );
    expect(screen.getByText('Das ist eine KI-Antwort')).toBeInTheDocument();
  });

  it('zeigt "KI-Antwort" Header wenn nicht streaming', () => {
    render(
      <LlmResponsePanel
        response="Fertige Antwort"
        streaming={false}
      />,
    );
    expect(screen.getByText('KI-Antwort')).toBeInTheDocument();
  });

  it('zeigt Lade-Animation wenn streaming ohne Response', () => {
    render(
      <LlmResponsePanel
        response=""
        streaming={true}
      />,
    );
    expect(screen.getByText('KI verarbeitet die Anfrage...')).toBeInTheDocument();
  });

  it('zeigt "Generiere Antwort" wenn streaming', () => {
    render(
      <LlmResponsePanel
        response="Teilantwort..."
        streaming={true}
      />,
    );
    expect(screen.getByText(/Generiere Antwort/)).toBeInTheDocument();
  });

  it('zeigt Fehlermeldung bei error', () => {
    render(
      <LlmResponsePanel
        response=""
        streaming={false}
        error="Verbindung fehlgeschlagen"
      />,
    );
    expect(screen.getByText('Verbindung fehlgeschlagen')).toBeInTheDocument();
  });

  it('zeigt Token-Zaehler und Modell an', () => {
    render(
      <LlmResponsePanel
        response="Antwort"
        streaming={false}
        tokenCount={150}
        model="qwen3:14b"
        tokPerS={25}
      />,
    );
    expect(screen.getByText(/150 Token/)).toBeInTheDocument();
    expect(screen.getByText(/qwen3:14b/)).toBeInTheDocument();
    expect(screen.getByText(/25 tok\/s/)).toBeInTheDocument();
  });

  it('zeigt Platzhalter wenn keine Antwort und nicht streaming', () => {
    render(
      <LlmResponsePanel
        response=""
        streaming={false}
      />,
    );
    expect(screen.getByText('Noch keine Antwort generiert.')).toBeInTheDocument();
  });
});
