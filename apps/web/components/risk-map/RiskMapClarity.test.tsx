import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { RiskMapEntry } from '../../lib/api';
import { RiskMapPanel, markerLabel, oneMarkerPerRegion } from './RiskMapPanel';

function entry(overrides: Partial<RiskMapEntry> = {}): RiskMapEntry {
  return {
    entity_name: 'Copper',
    region: 'Global',
    sector: 'metals',
    price: '4.52',
    currency: 'USD',
    unit: 'lb',
    pct_change_1d: '1.0',
    pct_change_7d: null,
    recorded_at: '2026-08-15T12:00:00Z',
    source_name: 'investing.com',
    source_url: 'https://example.com',
    ingestion_method: 'brightdata_scrape',
    is_stale: false,
    ...overrides,
  };
}

describe('markerLabel', () => {
  it('shortens a freight lane to its code, since the full route will not fit', () => {
    expect(markerLabel('FBX01_China_to_North_America_West_Coast')).toBe('FBX01');
    expect(markerLabel('FBX26_Europe_to_South_America_West_Coast')).toBe('FBX26');
  });

  it('keeps a headline index recognisable', () => {
    expect(markerLabel('FBX_Global')).toBe('FBX Global');
    expect(markerLabel('Baltic_Dry_Index')).toBe('Baltic Dry Index');
  });

  it('reads underscored names as words', () => {
    expect(markerLabel('WTI_Crude_Delayed')).toBe('WTI Crude Delayed');
  });

  it('leaves an already short name alone', () => {
    expect(markerLabel('Copper')).toBe('Copper');
  });
});

describe('oneMarkerPerRegion', () => {
  it('pins the largest mover in each region, so no two labels share a point', () => {
    const pinned = oneMarkerPerRegion(
      [
        entry({ entity_name: 'Small_Global', pct_change_1d: '0.2' }),
        entry({ entity_name: 'Big_Global', pct_change_1d: '9.0' }),
        entry({ entity_name: 'Oil', region: 'North America', pct_change_1d: '3.0' }),
      ],
      4,
    );

    expect(pinned.map((row) => row.entity_name)).toEqual(['Big_Global', 'Oil']);
  });

  it('caps how many are pinned, because a crowded map cannot be read', () => {
    const pinned = oneMarkerPerRegion(
      [
        entry({ region: 'Global', pct_change_1d: '9' }),
        entry({ region: 'North America', pct_change_1d: '8' }),
        entry({ region: 'Europe', pct_change_1d: '7' }),
        entry({ region: 'Asia Pacific', pct_change_1d: '6' }),
        entry({ region: 'Africa', pct_change_1d: '5' }),
      ],
      4,
    );

    expect(pinned).toHaveLength(4);
  });

  it('treats a missing change as no movement rather than failing', () => {
    const pinned = oneMarkerPerRegion([entry({ pct_change_1d: null })], 4);

    expect(pinned).toHaveLength(1);
  });
});

describe('RiskMapPanel clarity', () => {
  it('draws one marker per region even when many entities are global', () => {
    render(
      <RiskMapPanel
        entries={[
          entry({ entity_name: 'FBX01_China_to_North_America_West_Coast', pct_change_1d: '5' }),
          entry({ entity_name: 'FBX02_North_America_West_Coast_to_China', pct_change_1d: '4' }),
          entry({ entity_name: 'FBX03_China_to_North_America_East_Coast', pct_change_1d: '3' }),
        ]}
      />,
    );

    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('labels a marker with the short name rather than the raw identifier', () => {
    render(
      <RiskMapPanel
        entries={[
          entry({ entity_name: 'FBX01_China_to_North_America_West_Coast', pct_change_1d: '5' }),
        ]}
      />,
    );

    expect(screen.getByText(/FBX01/)).toBeInTheDocument();
    expect(screen.queryByText(/CHINA_TO_NORTH_AMERICA/i)).not.toBeInTheDocument();
  });
});
