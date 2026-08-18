import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type * as apiModule from '../../../lib/api';
import { ApiError, type RiskMap } from '../../../lib/api';
import RiskMapPage from './page';

const getRiskMap = vi.hoisted(() => vi.fn());

vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual<typeof apiModule>('../../../lib/api');
  return { ...actual, getRiskMap };
});

const MAP: RiskMap = {
  generated_at: '2026-08-15T14:32:05Z',
  sectors: [
    {
      sector: 'metals',
      entries: [
        {
          entity_name: 'Copper',
          region: 'Global',
          sector: 'metals',
          price: '4.52',
          currency: 'USD',
          unit: 'lb',
          pct_change_1d: '8.2',
          pct_change_7d: null,
          recorded_at: '2026-08-15T12:00:00Z',
          source_name: 'investing.com',
          source_url: 'https://www.investing.com/commodities/copper',
          ingestion_method: 'brightdata_scrape',
          is_stale: false,
        },
      ],
    },
  ],
};

afterEach(() => {
  vi.clearAllMocks();
});

describe('RiskMapPage', () => {
  it('shows the map and the movers when data is available', async () => {
    getRiskMap.mockResolvedValue(MAP);

    render(await RiskMapPage());

    expect(screen.getByRole('region', { name: /Global risk map/ })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Top movers/ })).toBeInTheDocument();
  });

  it('summarises what is tracked', async () => {
    getRiskMap.mockResolvedValue(MAP);

    render(await RiskMapPage());

    expect(screen.getByRole('region', { name: /Tracked movement/ })).toBeInTheDocument();
    expect(screen.getByText(/1 rising and 0 falling/)).toBeInTheDocument();
  });

  it('says the API could not be reached rather than showing an empty screen', async () => {
    getRiskMap.mockRejectedValue(new ApiError('API returned 503 for /api/risk-map'));

    render(await RiskMapPage());

    expect(screen.getByText('API returned 503 for /api/risk-map')).toBeInTheDocument();
    expect(screen.getByText(/NEXT_PUBLIC_API_URL/)).toBeInTheDocument();
  });

  it('reports an unexpected failure without leaking its internals', async () => {
    getRiskMap.mockRejectedValue(new TypeError('cannot read property of undefined'));

    render(await RiskMapPage());

    expect(screen.getByText(/could not be loaded for an unexpected reason/)).toBeInTheDocument();
    expect(screen.queryByText(/cannot read property/)).not.toBeInTheDocument();
  });

  it('renders an empty but working screen when nothing has been collected', async () => {
    getRiskMap.mockResolvedValue({ generated_at: '2026-08-15T14:32:05Z', sectors: [] });

    render(await RiskMapPage());

    expect(screen.getByText(/No prices have been collected yet/)).toBeInTheDocument();
    expect(screen.getByText(/No daily changes have been reported/)).toBeInTheDocument();
  });
});
