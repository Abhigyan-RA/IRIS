import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { RiskMapEntry } from '../../lib/api';
import { GLOBAL_COORDINATES, RiskMapPanel } from './RiskMapPanel';

function entry(overrides: Partial<RiskMapEntry> = {}): RiskMapEntry {
  return {
    entity_name: 'Steel_HRC_US',
    region: 'North America',
    sector: 'metals',
    price: '840',
    currency: 'USD',
    unit: 'ton',
    pct_change_1d: '8.2',
    pct_change_7d: null,
    recorded_at: '2026-08-15T12:00:00Z',
    source_name: 'investing.com',
    source_url: 'https://www.investing.com/commodities/copper',
    ingestion_method: 'brightdata_scrape',
    is_stale: false,
    ...overrides,
  };
}

describe('RiskMapPanel', () => {
  it('is a labelled region', () => {
    render(<RiskMapPanel entries={[entry()]} />);

    expect(screen.getByRole('region', { name: /Global risk map/ })).toBeInTheDocument();
  });

  it('states each marker in text rather than by position and colour alone', () => {
    render(<RiskMapPanel entries={[entry()]} />);

    const marker = screen.getByRole('link');
    expect(marker).toHaveTextContent('North America: Steel_HRC_US');
    expect(marker).toHaveTextContent('840 USD/ton');
    expect(marker).toHaveTextContent('+8.2%');
  });

  it('makes each marker a link into the ripple view, reachable by keyboard', () => {
    render(<RiskMapPanel entries={[entry({ entity_name: 'Copper' })]} />);

    expect(screen.getByRole('link')).toHaveAttribute('href', '/ripple/Copper');
  });

  it('encodes an entity name containing a space', () => {
    render(<RiskMapPanel entries={[entry({ entity_name: 'Stator Coil' })]} />);

    expect(screen.getByRole('link')).toHaveAttribute('href', '/ripple/Stator%20Coil');
  });

  it('pins the largest movers first and stops at the limit', () => {
    render(
      <RiskMapPanel
        limit={2}
        entries={[
          entry({ entity_name: 'Small', pct_change_1d: '0.4' }),
          entry({ entity_name: 'Largest', pct_change_1d: '-12.4' }),
          entry({ entity_name: 'Middle', pct_change_1d: '8.2' }),
        ]}
      />,
    );

    const markers = screen.getAllByRole('link');
    expect(markers).toHaveLength(2);
    expect(markers[0]).toHaveTextContent('Largest');
    expect(markers[1]).toHaveTextContent('Middle');
  });

  it('draws a real world map behind the markers', () => {
    render(<RiskMapPanel entries={[entry()]} />);

    expect(screen.getByTestId('world-map').querySelectorAll('path').length).toBeGreaterThan(50);
  });

  it('places a marker over its region, as a share of the map', () => {
    render(<RiskMapPanel entries={[entry({ region: 'Europe' })]} />);

    const style = screen.getByRole('listitem').getAttribute('style') ?? '';
    expect(style).toMatch(/left: \d+(\.\d+)?%/);
    expect(style).toMatch(/top: \d+(\.\d+)?%/);
  });

  it('places western regions left of eastern ones', () => {
    render(
      <RiskMapPanel
        entries={[
          entry({ entity_name: 'US', region: 'North America', pct_change_1d: '9' }),
          entry({ entity_name: 'Asia', region: 'Asia Pacific', pct_change_1d: '8' }),
        ]}
      />,
    );

    const leftPercent = /left: ([\d.]+)%/;
    const positions = screen
      .getAllByRole('listitem')
      .map((item) =>
        Number.parseFloat(leftPercent.exec(item.getAttribute('style') ?? '')?.[1] ?? '0'),
      );
    expect(positions[0]).toBeLessThan(positions[1] ?? 0);
  });

  it('spreads markers that share a region so none is hidden', () => {
    render(
      <RiskMapPanel
        entries={[
          entry({ entity_name: 'First', region: 'Global', pct_change_1d: '9' }),
          entry({ entity_name: 'Second', region: 'Global', pct_change_1d: '8' }),
        ]}
      />,
    );

    const styles = screen.getAllByRole('listitem').map((item) => item.getAttribute('style'));
    expect(styles[0]).not.toBe(styles[1]);
  });

  it('falls back to the global coordinate for an unmapped region', () => {
    render(<RiskMapPanel entries={[entry({ region: 'Antarctica' })]} />);

    expect(screen.getByRole('listitem').getAttribute('style')).toMatch(/left: \d/);
    expect(GLOBAL_COORDINATES).toBeDefined();
  });

  it('explains an empty map instead of showing a blank rectangle', () => {
    render(<RiskMapPanel entries={[]} />);

    expect(screen.getByText(/No prices have been collected yet/)).toBeInTheDocument();
  });

  it('hides the decorative backdrop from assistive technology', () => {
    render(<RiskMapPanel entries={[entry()]} />);

    expect(screen.getByRole('region').querySelector('[aria-hidden="true"]')).not.toBeNull();
  });
});
