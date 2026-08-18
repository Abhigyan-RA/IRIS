import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { HealthEvent } from '../../lib/api';
import { CollectorHealth, collectorStates } from './CollectorHealth';

function event(overrides: Partial<HealthEvent> = {}): HealthEvent {
  return {
    scraper_id: 'fbx_scraper',
    source_name: 'data.freightos.com',
    event_type: 'success',
    message: '[OK] 12 rows returned',
    occurred_at: '2026-08-15T03:05:00Z',
    ...overrides,
  };
}

describe('collectorStates', () => {
  it('uses the most recent event to decide the current state', () => {
    const states = collectorStates([
      event({ event_type: 'self_heal_resolved', occurred_at: '2026-08-15T03:03:00Z' }),
      event({ event_type: 'dom_shift_detected', occurred_at: '2026-08-15T03:00:00Z' }),
    ]);

    expect(states[0]?.status).toBe('healthy');
  });

  it('reports a collector that could not be repaired as failed', () => {
    const states = collectorStates([event({ event_type: 'self_heal_failed' })]);

    expect(states[0]?.status).toBe('failed');
  });

  it('reports a detected change as degraded rather than failed', () => {
    const states = collectorStates([event({ event_type: 'dom_shift_detected' })]);

    expect(states[0]?.status).toBe('degraded');
  });

  it('notes that a collector needed repairing, even once it recovered', () => {
    const states = collectorStates([
      event({ event_type: 'self_heal_resolved', occurred_at: '2026-08-15T03:03:00Z' }),
      event({ event_type: 'self_heal_triggered', occurred_at: '2026-08-15T03:02:00Z' }),
    ]);

    expect(states[0]?.wasRepaired).toBe(true);
  });

  it('does not claim a repair for a collector that simply worked', () => {
    expect(collectorStates([event()])[0]?.wasRepaired).toBe(false);
  });

  it('lists one entry per collector, not one per event', () => {
    const states = collectorStates([
      event({ scraper_id: 'fbx_scraper' }),
      event({ scraper_id: 'fbx_scraper', occurred_at: '2026-08-15T02:00:00Z' }),
      event({ scraper_id: 'lme_copper_scraper' }),
    ]);

    expect(states).toHaveLength(2);
  });

  it('puts the worst state first, so a problem is not buried', () => {
    const states = collectorStates([
      event({ scraper_id: 'healthy_one', event_type: 'success' }),
      event({ scraper_id: 'broken_one', event_type: 'self_heal_failed' }),
      event({ scraper_id: 'wobbly_one', event_type: 'dom_shift_detected' }),
    ]);

    expect(states.map((state) => state.scraperId)).toEqual([
      'broken_one',
      'wobbly_one',
      'healthy_one',
    ]);
  });

  it('returns nothing for an empty feed', () => {
    expect(collectorStates([])).toEqual([]);
  });
});

describe('CollectorHealth', () => {
  it('counts how many collectors are healthy', () => {
    render(
      <CollectorHealth
        events={[
          event({ scraper_id: 'a', event_type: 'success' }),
          event({ scraper_id: 'b', event_type: 'self_heal_failed' }),
        ]}
      />,
    );

    expect(screen.getByText('1 of 2 healthy')).toBeInTheDocument();
  });

  it('marks a collector that had to be repaired', () => {
    render(
      <CollectorHealth
        events={[
          event({ event_type: 'self_heal_resolved' }),
          event({ event_type: 'self_heal_triggered', occurred_at: '2026-08-15T03:02:00Z' }),
        ]}
      />,
    );

    expect(screen.getByText('Repaired')).toBeInTheDocument();
  });

  it('describes each status without relying on colour', () => {
    render(<CollectorHealth events={[event({ event_type: 'self_heal_failed' })]} />);

    expect(screen.getByRole('img', { name: 'fbx_scraper: failed' })).toBeInTheDocument();
  });

  it('explains an empty summary', () => {
    render(<CollectorHealth events={[]} />);

    expect(screen.getByText(/No collector has reported yet/)).toBeInTheDocument();
  });
});
