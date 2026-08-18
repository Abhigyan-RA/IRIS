import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { RiskMapEntry } from '../../lib/api';
import { SPIKE_THRESHOLD_PERCENT, TopMovers, moveSeverity } from './TopMovers';

function entry(overrides: Partial<RiskMapEntry> = {}): RiskMapEntry {
  return {
    entity_name: 'Copper',
    region: 'Global',
    sector: 'metals',
    price: '4.52',
    currency: 'USD',
    unit: 'lb',
    pct_change_1d: '1.8',
    pct_change_7d: null,
    recorded_at: '2026-08-15T12:00:00Z',
    source_name: 'investing.com',
    source_url: 'https://www.investing.com/commodities/copper',
    ingestion_method: 'brightdata_scrape',
    is_stale: false,
    ...overrides,
  };
}

describe('moveSeverity', () => {
  it('treats a large rise as a spike', () => {
    expect(moveSeverity(entry({ pct_change_1d: '8.2' }))).toBe('spike');
  });

  it('treats a large fall as easing', () => {
    expect(moveSeverity(entry({ pct_change_1d: '-6.4' }))).toBe('easing');
  });

  it('treats an ordinary move as steady', () => {
    expect(moveSeverity(entry({ pct_change_1d: '1.8' }))).toBe('steady');
  });

  it('treats an unreported move as steady rather than guessing', () => {
    expect(moveSeverity(entry({ pct_change_1d: null }))).toBe('steady');
  });

  it('uses the documented threshold', () => {
    expect(moveSeverity(entry({ pct_change_1d: String(SPIKE_THRESHOLD_PERCENT) }))).toBe('spike');
  });

  it('ignores a value that is not a number', () => {
    expect(moveSeverity(entry({ pct_change_1d: 'n/a' }))).toBe('steady');
  });
});

describe('TopMovers', () => {
  it('orders by the size of the move, not its direction', () => {
    render(
      <TopMovers
        entries={[
          entry({ entity_name: 'Copper', pct_change_1d: '1.8' }),
          entry({ entity_name: 'Soybeans', pct_change_1d: '-3.2' }),
          entry({ entity_name: 'Baltic Dry', pct_change_1d: '5.1' }),
        ]}
      />,
    );

    const names = screen.getAllByRole('listitem').map((item) => item.textContent);
    expect(names[0]).toContain('Baltic Dry');
    expect(names[1]).toContain('Soybeans');
    expect(names[2]).toContain('Copper');
  });

  it('shows at most the requested number of movers', () => {
    render(
      <TopMovers
        limit={2}
        entries={[
          entry({ entity_name: 'A', pct_change_1d: '9' }),
          entry({ entity_name: 'B', pct_change_1d: '8' }),
          entry({ entity_name: 'C', pct_change_1d: '7' }),
        ]}
      />,
    );

    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('leaves out entries with no reported change', () => {
    render(
      <TopMovers
        entries={[
          entry({ entity_name: 'Copper', pct_change_1d: '1.8' }),
          entry({ entity_name: 'Aluminium', pct_change_1d: null }),
        ]}
      />,
    );

    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('explains an empty row instead of showing nothing', () => {
    render(<TopMovers entries={[]} />);

    expect(screen.getByText(/No daily changes have been reported/)).toBeInTheDocument();
  });

  it('is a labelled section so the page outline makes sense', () => {
    render(<TopMovers entries={[entry()]} />);

    expect(screen.getByRole('region', { name: /Top movers/ })).toBeInTheDocument();
  });

  it('shows each entry with its price and change', () => {
    render(<TopMovers entries={[entry({ price: '112.40', pct_change_1d: '6.4' })]} />);

    expect(screen.getByText('112.40')).toBeInTheDocument();
    expect(screen.getByText('+6.4%')).toBeInTheDocument();
  });
});
