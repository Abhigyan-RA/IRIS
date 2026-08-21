import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Holders, InstitutionalOverview } from '../../lib/api';
import { InstitutionalOverviewPanel } from './InstitutionalOverviewPanel';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const OVERVIEW: InstitutionalOverview = {
  quarter_end: '2025-12-31',
  total_funds: 2,
  total_stocks: 2,
  total_positions: 3,
  funds: [
    {
      filer_name: 'Berkshire Hathaway',
      filer_cik: '0001067983',
      position_count: 1,
      reported_value_usd: '6000000000',
      source_name: 'SEC EDGAR',
      source_url: 'https://www.sec.gov/berkshire',
      enrichment: null,
    },
    {
      filer_name: 'Bridgewater Associates',
      filer_cik: '0001350694',
      position_count: 2,
      reported_value_usd: '3500000000',
      source_name: 'SEC EDGAR',
      source_url: 'https://www.sec.gov/bridgewater',
      enrichment: {
        report_period: '2025-12-31',
        filing_date: '2026-02-14',
        reported_value_usd: '3500000000',
        discretionary_aum_usd: null,
        top_10_concentration_pct: '42.1',
        holdings_count: 2,
        portfolio_turnover_pct: null,
        whale_score: null,
        source_name: 'whalewisdom.com',
        source_url: 'https://whalewisdom.com/filer/bridgewater',
        observed_at: '2026-02-16T12:00:00Z',
      },
    },
  ],
  stocks: [
    {
      stock_ticker: 'AAPL',
      stock_name: 'Apple Inc',
      sector: 'INFORMATION TECHNOLOGY',
      holder_count: 2,
      shares_held: 400,
      market_value_usd: '8000000000',
      shares_change_qoq: 50,
      enriched_positions: 1,
    },
    {
      stock_ticker: 'MSFT',
      stock_name: 'Microsoft Corp',
      sector: 'INFORMATION TECHNOLOGY',
      holder_count: 1,
      shares_held: 50,
      market_value_usd: '1500000000',
      shares_change_qoq: -10,
      enriched_positions: 0,
    },
  ],
  enrichment_only_funds: [
    {
      filer_name: 'State Street Corp',
      filer_cik: '0000093751',
      holdings_count: 25,
      reported_value_usd: '1445691222216',
      source_name: 'whalewisdom.com',
      source_url: 'https://whalewisdom.com/filer/state-street-corp',
      observed_at: '2026-02-16T12:00:00Z',
    },
  ],
  top_buys: [
    {
      filer_name: 'Berkshire Hathaway',
      filer_cik: '0001067983',
      stock_ticker: 'AAPL',
      shares_held: 300,
      market_value_usd: '6000000000',
      shares_change_qoq: 30,
      quarter_end: '2025-12-31',
      source_name: 'SEC EDGAR',
      source_url: 'https://www.sec.gov/berkshire',
    },
  ],
  top_sells: [
    {
      filer_name: 'Bridgewater Associates',
      filer_cik: '0001350694',
      stock_ticker: 'MSFT',
      shares_held: 50,
      market_value_usd: '1500000000',
      shares_change_qoq: -10,
      quarter_end: '2025-12-31',
      source_name: 'SEC EDGAR',
      source_url: 'https://www.sec.gov/bridgewater',
    },
  ],
  enrichment_coverage: {
    matched_funds: 1,
    enrichment_only_funds: 1,
    matched_positions: 1,
    observed_at: '2026-02-16T12:00:00Z',
  },
  coverage_note:
    'Official SEC 13F coverage includes every latest-quarter position currently stored; human-readable enrichment is limited to the configured WhaleWisdom watchlist. 13F reports are quarterly, delayed, long-only disclosures and do not show shorts.',
};

const HOLDERS: Holders = {
  ticker: 'AAPL',
  holders: [
    {
      filer_name: 'Berkshire Hathaway',
      filer_cik: '0001067983',
      shares_held: 300,
      market_value_usd: '6000000000',
      pct_portfolio: '25',
      shares_change_qoq: 30,
      delta_pct: '11.111',
      quarter_end: '2025-12-31',
      source_url: 'https://www.sec.gov/berkshire',
    },
  ],
};

describe('InstitutionalOverviewPanel', () => {
  it('shows current coverage, reporting period, provenance, and enrichment freshness', () => {
    render(<InstitutionalOverviewPanel overview={OVERVIEW} holders={HOLDERS} ticker="AAPL" />);

    expect(screen.getByText('2', { selector: '[data-metric="funds"]' })).toBeInTheDocument();
    expect(screen.getAllByText('2025-12-31').length).toBeGreaterThan(0);
    expect(screen.getByText(/configured WhaleWisdom watchlist/)).toBeInTheDocument();
    expect(screen.getByText(/Enrichment observed/)).toHaveTextContent('Feb 16, 2026');
    expect(screen.getAllByText('SEC EDGAR').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /WhaleWisdom enrichment/ })).toHaveAttribute(
      'href',
      'https://whalewisdom.com/filer/bridgewater',
    );
  });

  it('lists every returned fund and stock while stating any server-side cap', () => {
    render(<InstitutionalOverviewPanel overview={OVERVIEW} holders={HOLDERS} ticker="AAPL" />);

    const funds = screen.getByRole('table', { name: /currently stored funds/i });
    expect(within(funds).getByText('Berkshire Hathaway')).toBeInTheDocument();
    expect(within(funds).getByText('Bridgewater Associates')).toBeInTheDocument();
    const stocks = screen.getByRole('table', { name: /currently stored stocks/i });
    expect(within(stocks).getByText('Apple Inc')).toBeInTheDocument();
    expect(within(stocks).getByText('Microsoft Corp')).toBeInTheDocument();
    expect(screen.getByText('Showing 2 of 2 funds')).toBeInTheDocument();
    expect(screen.getByText('Showing 2 of 2 stocks')).toBeInTheDocument();
  });

  it('filters funds and stocks without hiding the honest total coverage', () => {
    render(<InstitutionalOverviewPanel overview={OVERVIEW} holders={HOLDERS} ticker="AAPL" />);

    fireEvent.change(screen.getByRole('searchbox', { name: /filter funds and stocks/i }), {
      target: { value: 'Microsoft' },
    });

    expect(screen.queryByText('Apple Inc')).not.toBeInTheDocument();
    expect(screen.getByText('Microsoft Corp')).toBeInTheDocument();
    expect(screen.getByText('Showing 2 of 2 funds')).toBeInTheDocument();
  });

  it('shows official buys and sells plus the selected stock holder detail', () => {
    render(<InstitutionalOverviewPanel overview={OVERVIEW} holders={HOLDERS} ticker="AAPL" />);

    expect(screen.getByRole('heading', { name: 'Top buys' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Top sells' })).toBeInTheDocument();
    expect(screen.getByText('+30 shares')).toBeInTheDocument();
    expect(screen.getByText('-10 shares')).toBeInTheDocument();
    expect(screen.getByText(/Funds reporting a position in AAPL/)).toBeInTheDocument();
  });

  it('lists watchlist funds that have no official filing, labelled as public-page data', () => {
    render(<InstitutionalOverviewPanel overview={OVERVIEW} holders={HOLDERS} ticker="AAPL" />);

    const table = screen.getByRole('table', {
      name: /watchlist funds awaiting an official filing/i,
    });
    expect(within(table).getByText('State Street Corp')).toBeInTheDocument();
    expect(within(table).getByText('25')).toBeInTheDocument();
    expect(
      within(table).getByRole('link', { name: /State Street Corp public page/ }),
    ).toHaveAttribute('href', 'https://whalewisdom.com/filer/state-street-corp');
    expect(screen.getByText(/These funds have no official filing stored yet/)).toBeInTheDocument();
  });

  it('omits the watchlist section entirely when every fund has an official filing', () => {
    render(
      <InstitutionalOverviewPanel
        overview={{ ...OVERVIEW, enrichment_only_funds: [] }}
        holders={HOLDERS}
        ticker="AAPL"
      />,
    );

    expect(
      screen.queryByRole('table', { name: /watchlist funds awaiting an official filing/i }),
    ).not.toBeInTheDocument();
  });

  it('renders an explicit empty state rather than empty tables', () => {
    const empty: InstitutionalOverview = {
      ...OVERVIEW,
      quarter_end: null,
      total_funds: 0,
      total_stocks: 0,
      total_positions: 0,
      funds: [],
      stocks: [],
      enrichment_only_funds: [],
      top_buys: [],
      top_sells: [],
    };

    render(
      <InstitutionalOverviewPanel
        overview={empty}
        holders={{ ticker: 'AAPL', holders: [] }}
        ticker="AAPL"
      />,
    );

    expect(
      screen.getByText(/No institutional filings have been collected yet/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('table', { name: /currently stored funds/i }),
    ).not.toBeInTheDocument();
  });
});
