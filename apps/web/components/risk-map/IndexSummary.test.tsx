import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { RiskMap, RiskMapEntry } from '../../lib/api';
import { ContributionBreakdown, IndexSummary, contributionBySector } from './IndexSummary';

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

function map(sectors: RiskMap['sectors']): RiskMap {
  return { generated_at: '2026-08-15T14:32:05Z', sectors };
}

describe('contributionBySector', () => {
  it('splits movement between categories', () => {
    const result = contributionBySector(
      map([
        { sector: 'metals', entries: [entry({ pct_change_1d: '6' })] },
        { sector: 'freight', entries: [entry({ sector: 'freight', pct_change_1d: '2' })] },
      ]),
    );

    expect(result).toEqual([
      { sector: 'metals', percent: 75, movers: 1 },
      { sector: 'freight', percent: 25, movers: 1 },
    ]);
  });

  it('counts a fall as movement, since direction is not the question here', () => {
    const result = contributionBySector(
      map([
        { sector: 'metals', entries: [entry({ pct_change_1d: '-5' })] },
        { sector: 'energy', entries: [entry({ sector: 'energy', pct_change_1d: '5' })] },
      ]),
    );

    expect(result.map((item) => item.percent)).toEqual([50, 50]);
  });

  it('returns nothing when no movement has been reported', () => {
    expect(
      contributionBySector(map([{ sector: 'metals', entries: [entry({ pct_change_1d: null })] }])),
    ).toEqual([]);
  });

  it('leaves out a category that has not moved', () => {
    const result = contributionBySector(
      map([
        { sector: 'metals', entries: [entry({ pct_change_1d: '4' })] },
        { sector: 'agriculture', entries: [entry({ sector: 'agriculture', pct_change_1d: '0' })] },
      ]),
    );

    expect(result).toHaveLength(1);
  });
});

describe('ContributionBreakdown', () => {
  it('shows each category with its share', () => {
    render(
      <ContributionBreakdown
        map={map([{ sector: 'metals', entries: [entry({ pct_change_1d: '4' })] }])}
      />,
    );

    expect(screen.getByText('metals')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('exposes each bar as a meter with its value, not just a coloured strip', () => {
    render(
      <ContributionBreakdown
        map={map([{ sector: 'metals', entries: [entry({ pct_change_1d: '4' })] }])}
      />,
    );

    const meter = screen.getByRole('meter', { name: /metals share/ });
    expect(meter).toHaveAttribute('aria-valuenow', '100');
  });

  it('explains an empty breakdown', () => {
    render(<ContributionBreakdown map={map([])} />);

    expect(screen.getByText(/No movement to attribute yet/)).toBeInTheDocument();
  });
});

describe('IndexSummary', () => {
  it('reports how many entities are tracked and which way they moved', () => {
    render(
      <IndexSummary
        map={map([
          {
            sector: 'metals',
            entries: [
              entry({ entity_name: 'Copper', pct_change_1d: '1.8' }),
              entry({ entity_name: 'Steel', pct_change_1d: '-3.1' }),
            ],
          },
        ])}
      />,
    );

    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText(/1 rising and 1 falling/)).toBeInTheDocument();
  });

  it('reports the largest move, keeping its direction', () => {
    render(
      <IndexSummary
        map={map([
          {
            sector: 'metals',
            entries: [
              entry({ pct_change_1d: '1.8' }),
              entry({ entity_name: 'Steel', pct_change_1d: '-12.4' }),
            ],
          },
        ])}
      />,
    );

    expect(screen.getByText('-12.4%')).toBeInTheDocument();
  });

  it('says how many figures are stale rather than leaving it to be noticed', () => {
    render(
      <IndexSummary
        map={map([
          { sector: 'metals', entries: [entry({ is_stale: true }), entry({ entity_name: 'B' })] },
        ])}
      />,
    );

    expect(screen.getByText(/1 figure is behind their freshness target/)).toBeInTheDocument();
  });

  it('says nothing about staleness when everything is current', () => {
    render(<IndexSummary map={map([{ sector: 'metals', entries: [entry()] }])} />);

    expect(screen.queryByText(/freshness target/)).not.toBeInTheDocument();
  });

  it('handles an empty map without inventing a figure', () => {
    render(<IndexSummary map={map([])} />);

    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.queryByText(/Largest move/)).not.toBeInTheDocument();
  });
});
