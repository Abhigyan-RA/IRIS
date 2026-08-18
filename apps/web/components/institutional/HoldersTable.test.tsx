import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Holders } from '../../lib/api';
import { HoldersTable, formatMarketValue, formatShares } from './HoldersTable';

type Holder = Holders['holders'][number];

function holder(overrides: Partial<Holder> = {}): Holder {
  return {
    filer_name: 'Bridgewater Associates',
    filer_cik: '0001350694',
    shares_held: 14_850_200,
    market_value_usd: '1240000000.00',
    pct_portfolio: '6.8',
    shares_change_qoq: 1_600_000,
    delta_pct: '12.4',
    quarter_end: '2026-06-30',
    source_url: 'https://www.sec.gov/edgar/browse/?CIK=0001350694',
    ...overrides,
  };
}

function holders(rows: Holder[] = [holder()]): Holders {
  return { ticker: 'XOM', holders: rows };
}

describe('formatMarketValue', () => {
  it('abbreviates billions so a column can be compared at a glance', () => {
    expect(formatMarketValue('1240000000.00')).toBe('$1.24B');
  });

  it('abbreviates millions', () => {
    expect(formatMarketValue('230400000.00')).toBe('$230.4M');
  });

  it('writes smaller sums in full', () => {
    expect(formatMarketValue('412500.00')).toBe('$412,500');
  });

  it('shows a dash when no value was reported', () => {
    expect(formatMarketValue(null)).toBe('--');
  });

  it('shows a dash for a value that is not a number', () => {
    expect(formatMarketValue('unknown')).toBe('--');
  });
});

describe('formatShares', () => {
  it('separates thousands so long counts stay readable', () => {
    expect(formatShares(14_850_200)).toBe('14,850,200');
  });
});

describe('HoldersTable', () => {
  it('renders a real table with a caption', () => {
    render(<HoldersTable holders={holders()} />);

    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText(/Funds reporting a position in XOM/)).toBeInTheDocument();
  });

  it('shows each position with its shares, value, and change', () => {
    render(<HoldersTable holders={holders()} />);

    expect(screen.getByText('14,850,200')).toBeInTheDocument();
    expect(screen.getByText('$1.24B')).toBeInTheDocument();
    expect(screen.getByText('+12.4%')).toBeInTheDocument();
  });

  it('states the quarter, because a holding is a snapshot rather than a live position', () => {
    render(<HoldersTable holders={holders()} />);

    expect(screen.getByText('2026-06-30')).toBeInTheDocument();
  });

  it('links a fund to the filing its numbers came from', () => {
    render(<HoldersTable holders={holders()} />);

    expect(screen.getByRole('link', { name: 'Bridgewater Associates' })).toHaveAttribute(
      'href',
      'https://www.sec.gov/edgar/browse/?CIK=0001350694',
    );
  });

  it('still names a fund when no filing link is recorded', () => {
    render(<HoldersTable holders={holders([holder({ source_url: null })])} />);

    expect(screen.getByText('Bridgewater Associates')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows a dash where a percentage was not reported', () => {
    render(<HoldersTable holders={holders([holder({ pct_portfolio: null })])} />);

    expect(screen.getAllByText('--').length).toBeGreaterThan(0);
  });

  it('explains an empty result rather than showing an empty table', () => {
    render(<HoldersTable holders={holders([])} />);

    expect(screen.getByText(/No fund has reported a position in XOM/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('uses the fund name as the row header, so a screen reader announces it per cell', () => {
    render(<HoldersTable holders={holders()} />);

    expect(screen.getByRole('rowheader')).toHaveTextContent('Bridgewater Associates');
  });
});
