import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { HealthEvent } from '../../lib/api';
import { AuditLog, EVENT_PRESENTATION, formatEventTime } from './AuditLog';

function event(overrides: Partial<HealthEvent> = {}): HealthEvent {
  return {
    scraper_id: 'fbx_scraper',
    source_name: 'data.freightos.com',
    event_type: 'dom_shift_detected',
    message: '[WARNING] data.freightos.com looks different: no rows returned',
    occurred_at: '2026-08-15T03:00:12Z',
    ...overrides,
  };
}

describe('formatEventTime', () => {
  it('shows the time in UTC', () => {
    expect(formatEventTime('2026-08-15T03:00:12Z')).toBe('03:00:12');
  });

  it('leaves an unparseable timestamp as it was rather than showing a wrong time', () => {
    expect(formatEventTime('not a timestamp')).toBe('not a timestamp');
  });
});

describe('EVENT_PRESENTATION', () => {
  it('uses bracketed text labels rather than symbols', () => {
    for (const presentation of Object.values(EVENT_PRESENTATION)) {
      expect(presentation.label).toMatch(/^\[[A-Z-]+\]$/);
    }
  });

  it('covers every stage a run can reach', () => {
    expect(Object.keys(EVENT_PRESENTATION)).toEqual([
      'success',
      'collection_failed',
      'dom_shift_detected',
      'self_heal_triggered',
      'self_heal_resolved',
      'self_heal_failed',
    ]);
  });

  it('pairs every label with a named icon component', () => {
    for (const presentation of Object.values(EVENT_PRESENTATION)) {
      expect(typeof presentation.icon).not.toBe('string');
    }
  });
});

describe('AuditLog', () => {
  it('is a labelled region', () => {
    render(<AuditLog events={[event()]} />);

    expect(screen.getByRole('region', { name: /Self-healing audit log/ })).toBeInTheDocument();
  });

  it('shows the time, the collector, the stage, and what happened', () => {
    render(<AuditLog events={[event()]} />);

    expect(screen.getByText('03:00:12')).toBeInTheDocument();
    expect(screen.getByText('fbx_scraper')).toBeInTheDocument();
    expect(screen.getByText('[WARNING]')).toBeInTheDocument();
    expect(screen.getByText(/looks different/)).toBeInTheDocument();
  });

  it('shows a full repair sequence in the order it happened', () => {
    render(
      <AuditLog
        events={[
          event({ event_type: 'dom_shift_detected', occurred_at: '2026-08-15T03:00:12Z' }),
          event({ event_type: 'self_heal_triggered', occurred_at: '2026-08-15T03:02:00Z' }),
          event({ event_type: 'self_heal_resolved', occurred_at: '2026-08-15T03:03:20Z' }),
        ]}
      />,
    );

    const labels = screen.getAllByRole('listitem').map((item) => item.textContent);
    expect(labels[0]).toContain('[WARNING]');
    expect(labels[1]).toContain('[AUTO-HEALING]');
    expect(labels[2]).toContain('[RESOLVED]');
  });

  it('exposes each timestamp in a machine-readable form', () => {
    render(<AuditLog events={[event()]} />);

    expect(screen.getByRole('time')).toHaveAttribute('datetime', '2026-08-15T03:00:12Z');
  });

  it('falls back to the stage name when an event carries no message', () => {
    render(<AuditLog events={[event({ event_type: 'self_heal_failed', message: null })]} />);

    expect(screen.getByText('self heal failed')).toBeInTheDocument();
  });

  it('explains a quiet feed rather than showing an empty panel', () => {
    render(<AuditLog events={[]} />);

    expect(screen.getByText(/No collector activity has been recorded yet/)).toBeInTheDocument();
  });

  it('contains no emoji, whatever the backend sent', () => {
    render(
      <AuditLog events={[event({ message: '[RESOLVED] collection resumed after 10 seconds' })]} />,
    );

    const text = screen.getByRole('region').textContent;
    expect(/\p{Extended_Pictographic}/u.test(text)).toBe(false);
  });
});
