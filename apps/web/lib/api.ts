import { z } from 'zod';

/**
 * Talking to the backend.
 *
 * Every response is validated against a schema before any component sees it. The
 * dashboard and the API are deployed separately and can be different versions, so
 * a changed or truncated payload has to surface as a clear error here rather than as
 * `undefined` inside a chart three layers down.
 *
 * Prices stay strings all the way to the screen. They are decimals in the database,
 * and converting them to JavaScript numbers would quietly round a figure that
 * someone is about to sign a contract against.
 */

/** Base URL of the API, exposed to the browser by design.
 *
 * The default uses the IPv4 address rather than `localhost`. Node resolves `localhost`
 * to IPv6 first, and a server listening only on IPv4 is then unreachable, which
 * surfaces as an unexplained "fetch failed" during server rendering.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

/** One of the four categories of data this platform tracks. */
export const sectorSchema = z.enum(['freight', 'energy', 'metals', 'agriculture']);

/** A tracked entity as shown on the risk map. */
export const riskMapEntrySchema = z.object({
  entity_name: z.string(),
  region: z.string(),
  sector: sectorSchema,
  price: z.string(),
  currency: z.string(),
  unit: z.string(),
  pct_change_1d: z.string().nullable(),
  pct_change_7d: z.string().nullable(),
  recorded_at: z.string(),
  source_name: z.string(),
  source_url: z.string(),
  ingestion_method: z.string(),
  is_stale: z.boolean(),
});

/** One category's entries. */
export const riskMapSectorSchema = z.object({
  sector: sectorSchema,
  entries: z.array(riskMapEntrySchema),
});

/** The whole risk map. */
export const riskMapSchema = z.object({
  generated_at: z.string(),
  sectors: z.array(riskMapSectorSchema),
});

/** Price history for one entity. */
export const trendSchema = z.object({
  entity_name: z.string(),
  sector: sectorSchema,
  currency: z.string(),
  unit: z.string(),
  days: z.number(),
  points: z.array(z.object({ recorded_at: z.string(), price: z.string() })),
  change_pct_over_window: z.string().nullable(),
  latest_price: z.string(),
  source_name: z.string(),
  source_url: z.string(),
});

/** What a commodity feeds into. */
export const rippleSchema = z.object({
  commodity: z.string(),
  depth: z.number(),
  nodes: z.array(z.object({ name: z.string(), kind: z.string() })),
  links: z.array(
    z.object({
      source: z.string(),
      relationship: z.string(),
      target: z.string(),
      weight: z.number().nullable(),
    }),
  ),
  affected_industries: z.array(z.string()),
  exposed_filers: z.array(z.record(z.string(), z.unknown())),
  explanation: z.string().nullable(),
});

/** Funds reporting a position in one stock. */
export const holdersSchema = z.object({
  ticker: z.string(),
  holders: z.array(
    z.object({
      filer_name: z.string(),
      filer_cik: z.string(),
      shares_held: z.number(),
      market_value_usd: z.string().nullable(),
      pct_portfolio: z.string().nullable(),
      shares_change_qoq: z.number().nullable(),
      delta_pct: z.string().nullable(),
      quarter_end: z.string(),
      source_url: z.string().nullable(),
    }),
  ),
});

/** One fund's full reported portfolio. */
export const filerHoldingsSchema = z.object({
  filer_cik: z.string(),
  filer_name: z.string().nullable(),
  holdings: z.array(
    z.object({
      stock_ticker: z.string(),
      shares_held: z.number(),
      market_value_usd: z.string().nullable(),
      pct_portfolio: z.string().nullable(),
      shares_change_qoq: z.number().nullable(),
      delta_pct: z.string().nullable(),
      quarter_end: z.string(),
      source_url: z.string().nullable(),
      sector: z.string().nullable(),
      rank: z.number().int().nullable(),
      previous_pct_portfolio: z.string().nullable(),
    }),
  ),
});

export const institutionalOverviewSchema = z.object({
  quarter_end: z.string().nullable(),
  total_funds: z.number().int().nonnegative(),
  total_stocks: z.number().int().nonnegative(),
  total_positions: z.number().int().nonnegative(),
  funds: z.array(
    z.object({
      filer_name: z.string(),
      filer_cik: z.string(),
      position_count: z.number().int().nonnegative(),
      reported_value_usd: z.string(),
      source_name: z.string(),
      source_url: z.string().nullable(),
      enrichment: z
        .object({
          report_period: z.string(),
          filing_date: z.string().nullable(),
          reported_value_usd: z.string().nullable(),
          discretionary_aum_usd: z.string().nullable(),
          top_10_concentration_pct: z.string().nullable(),
          holdings_count: z.number().int().nonnegative().nullable(),
          portfolio_turnover_pct: z.string().nullable(),
          whale_score: z.string().nullable(),
          net_share_change: z.number().int().nullable(),
          source_name: z.string(),
          source_url: z.string(),
          observed_at: z.string(),
        })
        .nullable(),
    }),
  ),
  enrichment_only_funds: z.array(
    z.object({
      filer_name: z.string(),
      filer_cik: z.string(),
      holdings_count: z.number().int().nonnegative().nullable(),
      reported_value_usd: z.string().nullable(),
      source_name: z.string(),
      source_url: z.string(),
      observed_at: z.string(),
    }),
  ),
  stocks: z.array(
    z.object({
      stock_ticker: z.string(),
      stock_name: z.string().nullable(),
      sector: z.string().nullable(),
      holder_count: z.number().int().nonnegative(),
      shares_held: z.number().int().nonnegative(),
      market_value_usd: z.string(),
      shares_change_qoq: z.number().int(),
      enriched_positions: z.number().int().nonnegative(),
    }),
  ),
  top_buys: z.array(
    z.object({
      filer_name: z.string(),
      filer_cik: z.string(),
      stock_ticker: z.string(),
      shares_held: z.number().int().nonnegative(),
      market_value_usd: z.string().nullable(),
      shares_change_qoq: z.number().int(),
      quarter_end: z.string(),
      source_name: z.string(),
      source_url: z.string().nullable(),
    }),
  ),
  top_sells: z.array(
    z.object({
      filer_name: z.string(),
      filer_cik: z.string(),
      stock_ticker: z.string(),
      shares_held: z.number().int().nonnegative(),
      market_value_usd: z.string().nullable(),
      shares_change_qoq: z.number().int(),
      quarter_end: z.string(),
      source_name: z.string(),
      source_url: z.string().nullable(),
    }),
  ),
  enrichment_coverage: z.object({
    matched_funds: z.number().int().nonnegative(),
    enrichment_only_funds: z.number().int().nonnegative(),
    matched_positions: z.number().int().nonnegative(),
    observed_at: z.string().nullable(),
  }),
  coverage_note: z.string(),
});

/** Recent collector activity. */
export const healthFeedSchema = z.object({
  events: z.array(
    z.object({
      scraper_id: z.string(),
      source_name: z.string(),
      event_type: z.enum([
        'success',
        'collection_failed',
        'dom_shift_detected',
        'self_heal_triggered',
        'self_heal_resolved',
        'self_heal_failed',
      ]),
      message: z.string().nullable(),
      occurred_at: z.string(),
    }),
  ),
});

/** An answer from the copilot. */
export const copilotAnswerSchema = z.object({
  answer: z.string(),
  sources: z.array(z.string()),
  data_as_of: z.string().nullable(),
});

export type RiskMap = z.infer<typeof riskMapSchema>;
export type RiskMapEntry = z.infer<typeof riskMapEntrySchema>;
export type Trend = z.infer<typeof trendSchema>;
export type Ripple = z.infer<typeof rippleSchema>;
export type Holders = z.infer<typeof holdersSchema>;
export type FilerHoldings = z.infer<typeof filerHoldingsSchema>;
export type InstitutionalOverview = z.infer<typeof institutionalOverviewSchema>;
export type HealthFeed = z.infer<typeof healthFeedSchema>;
export type HealthEvent = HealthFeed['events'][number];
export type CopilotAnswer = z.infer<typeof copilotAnswerSchema>;

// Re-exported so callers import their errors from the client they call, while the
// reader-facing wording for each one lives in a single module.
export { ApiError, SchemaError } from './failures';
import { ApiError, SchemaError } from './failures';

/**
 * Fetch a path from the API and validate the reply.
 *
 * @param path - Path beneath the API base URL, starting with a slash.
 * @param schema - Shape the reply must match.
 * @param init - Extra request options, such as a POST body.
 * @returns The validated reply.
 * @throws ApiError If the request fails, the status is an error, or the body does
 * not match the schema.
 */
export async function fetchFromApi<Output>(
  path: string,
  schema: z.ZodType<Output>,
  init?: RequestInit,
): Promise<Output> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      // Live data: a cached response would show a stale market as a current one.
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch (error) {
    // Status zero means the request never got a reply at all, which is a stopped or
    // unreachable service rather than a refusal.
    throw new ApiError(0, `Could not reach the API at ${path}: ${String(error)}`);
  }

  if (!response.ok) {
    throw new ApiError(response.status, `API returned ${String(response.status)} for ${path}`);
  }

  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) {
    throw new SchemaError(
      `API reply for ${path} did not match the expected shape: ${parsed.error.message}`,
    );
  }
  return parsed.data;
}

/**
 * Read the risk map.
 *
 * @returns The newest price per tracked entity, grouped by category.
 */
export function getRiskMap(): Promise<RiskMap> {
  return fetchFromApi('/api/risk-map', riskMapSchema);
}

/**
 * Read price history for one entity.
 *
 * @param entityName - Entity to look up.
 * @param days - How many days of history to read.
 * @returns The history.
 */
export function getTrend(entityName: string, days = 30): Promise<Trend> {
  return fetchFromApi(
    `/api/commodities/${encodeURIComponent(entityName)}/trend?days=${String(days)}`,
    trendSchema,
  );
}

/**
 * Read what a commodity feeds into.
 *
 * @param commodity - Commodity to start from.
 * @param depth - How many steps downstream to follow.
 * @returns The chain, the industries affected, and the funds exposed.
 */
export function getRipple(commodity: string, depth = 2): Promise<Ripple> {
  return fetchFromApi(
    `/api/graph/ripple/${encodeURIComponent(commodity)}?depth=${String(depth)}`,
    rippleSchema,
  );
}

/**
 * Read the funds holding one stock.
 *
 * @param ticker - Ticker symbol.
 * @returns The reported positions.
 */
export function getHolders(ticker: string): Promise<Holders> {
  return fetchFromApi(`/api/institutional/holders/${encodeURIComponent(ticker)}`, holdersSchema);
}

/**
 * Read one fund's full reported portfolio.
 *
 * @param filerCik - The fund's CIK identifier.
 * @returns The fund name and its positions, largest first.
 */
export function getFilerHoldings(filerCik: string): Promise<FilerHoldings> {
  return fetchFromApi(
    `/api/institutional/filer/${encodeURIComponent(filerCik)}/holdings`,
    filerHoldingsSchema,
  );
}

export function getInstitutionalOverview(): Promise<InstitutionalOverview> {
  return fetchFromApi(
    '/api/institutional/overview?fund_limit=1000&stock_limit=1000&mover_limit=100',
    institutionalOverviewSchema,
  );
}

/**
 * Read recent collector activity.
 *
 * @param limit - How many entries to read.
 * @returns The entries, newest first.
 */
export function getHealthFeed(limit = 50): Promise<HealthFeed> {
  return fetchFromApi(`/api/pipeline-health?limit=${String(limit)}`, healthFeedSchema);
}

/**
 * Ask the copilot a question.
 *
 * @param question - The question, in plain language.
 * @returns The answer with its sources.
 */
export function askCopilot(question: string): Promise<CopilotAnswer> {
  return fetchFromApi('/api/copilot/ask', copilotAnswerSchema, {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}
