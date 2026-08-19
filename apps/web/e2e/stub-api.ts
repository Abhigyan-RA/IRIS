/**
 * A stand-in for the backend, used only by the end-to-end test.
 *
 * The end-to-end test exists to prove that the five screens work together as a
 * journey: see what changed, find out what it affects, check how funds are
 * positioned, confirm the pipeline is honest, then ask a question. That journey is
 * about the dashboard, not about the database, so it runs against fixed replies
 * rather than live data.
 *
 * Fixed replies also make the test meaningful. Against a live pipeline, the figures
 * change between runs, so the test could only assert that something appeared. Here it
 * can assert the exact numbers a reader would see.
 *
 * The dashboard fetches from the server, not the browser, so request interception in
 * the browser would not see these calls. A real server on a real port is the only way
 * to stand in for the API.
 */

import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';

/** Port the stub listens on, matching what the dashboard is pointed at. */
export const STUB_PORT = 8123;

const RISK_MAP = {
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
          pct_change_7d: '11.4',
          recorded_at: '2026-08-15T12:00:00Z',
          source_name: 'investing.com',
          source_url: 'https://www.investing.com/commodities/copper',
          ingestion_method: 'brightdata_scrape',
          is_stale: false,
        },
      ],
    },
    {
      sector: 'freight',
      entries: [
        {
          entity_name: 'FBX_Global',
          region: 'Global',
          sector: 'freight',
          price: '5240',
          currency: 'USD',
          unit: 'feu',
          pct_change_1d: '12.4',
          pct_change_7d: null,
          recorded_at: '2026-08-15T11:00:00Z',
          source_name: 'data.freightos.com',
          source_url: 'https://data.freightos.com/',
          ingestion_method: 'brightdata_scrape',
          is_stale: false,
        },
      ],
    },
  ],
};

const TREND = {
  entity_name: 'Copper',
  sector: 'metals',
  currency: 'USD',
  unit: 'lb',
  days: 30,
  points: [
    { recorded_at: '2026-07-16T12:00:00Z', price: '4.10' },
    { recorded_at: '2026-08-15T12:00:00Z', price: '4.52' },
  ],
  change_pct_over_window: '10.2',
  latest_price: '4.52',
  source_name: 'investing.com',
  source_url: 'https://www.investing.com/commodities/copper',
};

const RIPPLE = {
  commodity: 'Copper',
  depth: 2,
  nodes: [
    { name: 'Copper', kind: 'Commodity' },
    { name: 'Stator Coil', kind: 'Component' },
    { name: 'EV Battery Manufacturing', kind: 'Industry' },
  ],
  links: [
    { source: 'Copper', relationship: 'REFINED_INTO', target: 'Stator Coil', weight: null },
    {
      source: 'Stator Coil',
      relationship: 'REQUIRED_FOR',
      target: 'EV Battery Manufacturing',
      weight: 0.18,
    },
  ],
  affected_industries: ['EV Battery Manufacturing'],
  exposed_filers: [{ filer: 'Bridgewater Associates', cik: '0001350694', ticker: 'NVDA' }],
  explanation:
    'Copper is refined into stator coils, which electric vehicle manufacturing depends on, so a sustained rise raises battery pack costs.',
};

const HOLDERS = {
  ticker: 'NVDA',
  holders: [
    {
      filer_name: 'Bridgewater Associates',
      filer_cik: '0001350694',
      shares_held: 1_200_000,
      market_value_usd: '144000000.00',
      pct_portfolio: '7.02',
      shares_change_qoq: 150_000,
      delta_pct: '14.286',
      quarter_end: '2026-06-30',
      source_url: 'https://www.sec.gov/edgar/browse/?CIK=0001350694',
    },
  ],
};

const INSTITUTIONAL_OVERVIEW = {
  quarter_end: '2026-06-30',
  total_funds: 1,
  total_stocks: 1,
  total_positions: 1,
  funds: [
    {
      filer_name: 'Bridgewater Associates',
      filer_cik: '0001350694',
      position_count: 1,
      reported_value_usd: '144000000.00',
      source_name: 'SEC EDGAR',
      source_url: 'https://www.sec.gov/edgar/browse/?CIK=0001350694',
      enrichment: {
        report_period: '2026-06-30',
        filing_date: '2026-08-14',
        reported_value_usd: '144000000.00',
        discretionary_aum_usd: null,
        top_10_concentration_pct: '42.1',
        holdings_count: 1,
        portfolio_turnover_pct: null,
        whale_score: null,
        source_name: 'whalewisdom.com',
        source_url: 'https://whalewisdom.com/filer/bridgewater-associates-lp',
        observed_at: '2026-08-15T13:00:00Z',
      },
    },
  ],
  stocks: [
    {
      stock_ticker: 'NVDA',
      stock_name: 'NVIDIA Corp',
      holder_count: 1,
      shares_held: 1_200_000,
      market_value_usd: '144000000.00',
      shares_change_qoq: 150_000,
      enriched_positions: 1,
    },
  ],
  top_buys: [
    {
      filer_name: 'Bridgewater Associates',
      filer_cik: '0001350694',
      stock_ticker: 'NVDA',
      shares_held: 1_200_000,
      market_value_usd: '144000000.00',
      shares_change_qoq: 150_000,
      quarter_end: '2026-06-30',
      source_name: 'SEC EDGAR',
      source_url: 'https://www.sec.gov/edgar/browse/?CIK=0001350694',
    },
  ],
  top_sells: [],
  enrichment_coverage: {
    matched_funds: 1,
    matched_positions: 1,
    observed_at: '2026-08-15T13:00:00Z',
  },
  coverage_note:
    'Official SEC 13F coverage includes every latest-quarter position currently stored; human-readable enrichment is limited to the configured WhaleWisdom watchlist. 13F reports are quarterly, delayed, long-only disclosures and do not show shorts.',
};

const HEALTH_FEED = {
  events: [
    {
      scraper_id: 'fbx_scraper',
      source_name: 'data.freightos.com',
      event_type: 'self_heal_resolved',
      message: '[RESOLVED] collection resumed: 12 rows returned with all required fields',
      occurred_at: '2026-08-15T03:03:20Z',
    },
    {
      scraper_id: 'fbx_scraper',
      source_name: 'data.freightos.com',
      event_type: 'self_heal_triggered',
      message: '[AUTO-HEALING] repair requested for: price',
      occurred_at: '2026-08-15T03:02:00Z',
    },
    {
      scraper_id: 'fbx_scraper',
      source_name: 'data.freightos.com',
      event_type: 'dom_shift_detected',
      message: '[WARNING] data.freightos.com looks different: no rows returned',
      occurred_at: '2026-08-15T03:00:12Z',
    },
  ],
};

const COPILOT_ANSWER = {
  answer:
    'Copper is 4.52 USD per pound, up 8.2 percent since the previous published price, and it feeds electric vehicle manufacturing.',
  sources: ['https://www.investing.com/commodities/copper'],
  data_as_of: '2026-08-15T12:00:00Z',
};

/**
 * Choose the reply for a request path.
 *
 * @param path - Request path, including any query string.
 * @returns The reply body, or null when the path is not stubbed.
 */
function replyFor(path: string): unknown {
  if (path.startsWith('/api/risk-map')) {
    return RISK_MAP;
  }
  if (path.startsWith('/api/commodities/')) {
    return TREND;
  }
  if (path.startsWith('/api/graph/ripple/')) {
    return RIPPLE;
  }
  if (path.startsWith('/api/institutional/overview')) {
    return INSTITUTIONAL_OVERVIEW;
  }
  if (path.startsWith('/api/institutional/holders/')) {
    // Only the ticker this journey uses is known. Anything else answers as the real
    // API would for a stock with no filings we can serve, which is what lets the test
    // check that a failure is reported on the page.
    return path.includes('/NVDA') ? HOLDERS : null;
  }
  if (path.startsWith('/api/pipeline-health')) {
    return HEALTH_FEED;
  }
  if (path.startsWith('/api/copilot/ask')) {
    return COPILOT_ANSWER;
  }
  return null;
}

const server = createServer((request: IncomingMessage, response: ServerResponse) => {
  // The copilot question is sent from the browser, which makes it a cross-origin
  // request. The real API allows the dashboard's origin explicitly, and the stub has
  // to do the same or the browser will discard the reply.
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  };

  if (request.method === 'OPTIONS') {
    response.writeHead(204, corsHeaders);
    response.end();
    return;
  }

  const body = replyFor(request.url ?? '');
  if (body === null) {
    response.writeHead(404, { ...corsHeaders, 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ detail: 'not stubbed' }));
    return;
  }
  response.writeHead(200, { ...corsHeaders, 'Content-Type': 'application/json' });
  response.end(JSON.stringify(body));
});

server.listen(STUB_PORT, () => {
  process.stdout.write(`Stub API listening on ${String(STUB_PORT)}\n`);
});
