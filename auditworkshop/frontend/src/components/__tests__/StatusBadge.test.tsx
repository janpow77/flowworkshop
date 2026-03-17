import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from '../checklist/StatusBadge';

describe('StatusBadge', () => {
  it('zeigt "Akzeptiert" fuer accepted', () => {
    render(<StatusBadge status="accepted" />);
    expect(screen.getByText('Akzeptiert')).toBeInTheDocument();
  });

  it('zeigt "Abgelehnt" fuer rejected', () => {
    render(<StatusBadge status="rejected" />);
    expect(screen.getByText('Abgelehnt')).toBeInTheDocument();
  });

  it('zeigt "Entwurf" fuer draft', () => {
    render(<StatusBadge status="draft" />);
    expect(screen.getByText('Entwurf')).toBeInTheDocument();
  });

  it('zeigt "Bearbeitet" fuer edited', () => {
    render(<StatusBadge status="edited" />);
    expect(screen.getByText('Bearbeitet')).toBeInTheDocument();
  });

  it('zeigt Fallback fuer null', () => {
    render(<StatusBadge status={null} />);
    // 'none' Status zeigt das Label '—'
    const badge = screen.getByText('—', { selector: 'span > span:last-child' });
    expect(badge).toBeInTheDocument();
  });

  it('zeigt nur Icon im compact-Modus', () => {
    const { container } = render(<StatusBadge status="accepted" compact />);
    // Im compact-Modus wird kein Label-Text gerendert
    expect(screen.queryByText('Akzeptiert')).not.toBeInTheDocument();
    // Aber das Icon-Zeichen ist da
    expect(container.textContent).toContain('\u2713');
  });
});
