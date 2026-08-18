import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  API_BASE_URL,
  ApiError,
  askCopilot,
  fetchFromApi,
  getHealthFeed,
  getHolders,
  getRipple,
  getRiskMap,
  getTrend,
  riskMapSchema,
} from './api';

const VALID_RISK_MAP = {
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
          pct_change_1d: '1.8',
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

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
      ...response,
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('fetchFromApi', () => {
  it('returns the validated reply', async () => {
    mockFetch({ json: () => Promise.resolve(VALID_RISK_MAP) });

    const result = await fetchFromApi('/api/risk-map', riskMapSchema);

    expect(result.sectors[0]?.entries[0]?.entity_name).toBe('Copper');
  });

  it('keeps prices as strings so no precision is lost on the way to the screen', async () => {
    mockFetch({ json: () => Promise.resolve(VALID_RISK_MAP) });

    const result = await fetchFromApi('/api/risk-map', riskMapSchema);

    expect(result.sectors[0]?.entries[0]?.price).toBe('4.52');
  });

  it('never serves a cached reply, since a stale market would look current', async () => {
    mockFetch({ json: () => Promise.resolve(VALID_RISK_MAP) });

    await fetchFromApi('/api/risk-map', riskMapSchema);

    const [, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(init!.cache).toBe('no-store');
  });

  it('reports an error status rather than returning an empty result', async () => {
    mockFetch({ ok: false, status: 503, json: () => Promise.resolve({}) });

    await expect(fetchFromApi('/api/risk-map', riskMapSchema)).rejects.toBeInstanceOf(ApiError);
  });

  it('reports a reply that does not match the expected shape', async () => {
    mockFetch({ json: () => Promise.resolve({ sectors: 'not a list' }) });

    await expect(fetchFromApi('/api/risk-map', riskMapSchema)).rejects.toThrow(
      /did not match the expected shape/,
    );
  });

  it('reports an unreachable API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')));

    await expect(fetchFromApi('/api/risk-map', riskMapSchema)).rejects.toThrow(/Could not reach/);
  });
});

describe('endpoint helpers', () => {
  it('reads the risk map from its documented path', async () => {
    mockFetch({ json: () => Promise.resolve(VALID_RISK_MAP) });

    await getRiskMap();

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('/api/risk-map');
  });

  it('addresses the API by IPv4 by default, since localhost resolves to IPv6 first', () => {
    expect(API_BASE_URL).toMatch(/^http:\/\/(127\.0\.0\.1|[^/]+)/);
    expect(API_BASE_URL).not.toContain('//localhost');
  });

  it('encodes an entity name so one with a space still resolves', async () => {
    mockFetch({
      json: () =>
        Promise.resolve({
          entity_name: 'Stator Coil',
          sector: 'metals',
          currency: 'USD',
          unit: 'lb',
          days: 30,
          points: [],
          change_pct_over_window: null,
          latest_price: '4.52',
          source_name: 'investing.com',
          source_url: 'https://www.investing.com/commodities/copper',
        }),
    });

    await getTrend('Stator Coil');

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('Stator%20Coil');
  });

  it('passes the requested window through', async () => {
    mockFetch({
      json: () =>
        Promise.resolve({
          entity_name: 'Copper',
          sector: 'metals',
          currency: 'USD',
          unit: 'lb',
          days: 7,
          points: [],
          change_pct_over_window: null,
          latest_price: '4.52',
          source_name: 'investing.com',
          source_url: 'https://www.investing.com/commodities/copper',
        }),
    });

    await getTrend('Copper', 7);

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('days=7');
  });

  it('reads a ripple traversal at its documented depth', async () => {
    mockFetch({
      json: () =>
        Promise.resolve({
          commodity: 'Copper',
          depth: 3,
          nodes: [],
          links: [],
          affected_industries: [],
          exposed_filers: [],
          explanation: null,
        }),
    });

    const result = await getRipple('Copper', 3);

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('/api/graph/ripple/Copper?depth=3');
    expect(result.depth).toBe(3);
  });

  it('reads the holders of a stock', async () => {
    mockFetch({ json: () => Promise.resolve({ ticker: 'NVDA', holders: [] }) });

    const result = await getHolders('NVDA');

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('/api/institutional/holders/NVDA');
    expect(result.holders).toEqual([]);
  });

  it('reads the health feed with a limit', async () => {
    mockFetch({ json: () => Promise.resolve({ events: [] }) });

    await getHealthFeed(25);

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('/api/pipeline-health?limit=25');
  });

  it('sends a copilot question as a POST body', async () => {
    mockFetch({
      json: () => Promise.resolve({ answer: 'Copper is up.', sources: [], data_as_of: null }),
    });

    const result = await askCopilot('what is copper doing');

    const [url, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(url).toContain('/api/copilot/ask');
    expect(init?.method).toBe('POST');
    expect(init?.body).toContain('what is copper doing');
    expect(result.answer).toBe('Copper is up.');
  });

  it('rejects a copilot reply that is missing its sources list', async () => {
    mockFetch({ json: () => Promise.resolve({ answer: 'Copper is up.' }) });

    await expect(askCopilot('what is copper doing')).rejects.toBeInstanceOf(ApiError);
  });
});
