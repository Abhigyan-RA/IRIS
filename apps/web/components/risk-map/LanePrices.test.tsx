import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { RiskMapEntry } from '../../lib/api';
import { LanePrices, readLaneName } from './LanePrices';

function entry(overrides: Partial<RiskMapEntry> = {}): RiskMapEntry {
  return {
    entity_name: 'FBX03_China_to_North_America_East_Coast',
    sector: 'freight',
    region: 'Global',
    price: '9421.8000',
    currency: 'USD',
    unit: 'feu',
    pct_change_1d: null,
    pct_change_7d: null,
    is_stale: false,
    recorded_at: '2026-08-18T03:12:37Z',
    source_name: 'fbx.freightos.com',
    source_url: 'https://fbx.freightos.com/',
    ingestion_method: 'brightdata_scrape',
    ...overrides,
  };
}

describe('readLaneName', () => {
  it('splits a stored lane name into a code and a readable route', () => {
    expect(readLaneName('FBX03_China_to_North_America_East_Coast')).toEqual({
      code: 'FBX03',
      route: 'China to North America East Coast',
    });
  });

  it('rejects a name that is not a lane', () => {
    expect(readLaneName('FBX_Global')).toBeNull();
    expect(readLaneName('Copper')).toBeNull();
  });
});

describe('LanePrices', () => {
  it('shows nothing at all when no lanes have been collected', () => {
    render(<LanePrices entries={[entry({ entity_name: 'Copper' })]} />);

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('leaves the headline index out, since it is the average of the lanes', () => {
    render(
      <LanePrices entries={[entry(), entry({ entity_name: 'FBX_Global', price: '3690.0000' })]} />,
    );

    expect(screen.getAllByRole('row')).toHaveLength(2);
    expect(screen.queryByText('3690.0000 USD/feu')).not.toBeInTheDocument();
  });

  it('ranks lanes by price, most expensive first', () => {
    render(
      <LanePrices
        entries={[
          entry({ entity_name: 'FBX14_Mediterranean_to_China', price: '432.0000' }),
          entry({ entity_name: 'FBX03_China_to_North_America_East_Coast', price: '9421.8000' }),
          entry({ entity_name: 'FBX11_China_to_Northern_Europe', price: '5008.8000' }),
        ]}
      />,
    );

    const codes = screen.getAllByRole('rowheader').map((cell) => cell.textContent);
    expect(codes).toEqual(['FBX03', 'FBX11', 'FBX14']);
  });

  it('keeps the price exactly as stored, without rounding it', () => {
    render(<LanePrices entries={[entry({ price: '9421.8000' })]} />);

    expect(screen.getByText('9421.8000 USD/feu')).toBeInTheDocument();
  });

  it('links a lane to what it feeds into', () => {
    render(<LanePrices entries={[entry()]} />);

    expect(screen.getByRole('link', { name: 'China to North America East Coast' })).toHaveAttribute(
      'href',
      '/ripple/FBX03_China_to_North_America_East_Coast',
    );
  });

  it('explains why a lane may show no change', () => {
    render(<LanePrices entries={[entry()]} />);

    expect(screen.getByText(/one percentage change for the index as a whole/)).toBeInTheDocument();
  });

  it('describes the table for anyone using a screen reader', () => {
    render(<LanePrices entries={[entry()]} />);

    expect(screen.getByRole('table')).toHaveAccessibleName(/ranked from most to least expensive/);
  });
});
