'use client';

import { Database, ExternalLink, Search, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import type { Holders, InstitutionalOverview } from '../../lib/api';
import { HoldersTable, formatMarketValue, formatShares } from './HoldersTable';
import { TickerPicker } from './TickerPicker';
import { Panel, SectionLabel } from '../primitives/Panel';

export interface InstitutionalOverviewPanelProps {
  /** Aggregated official ledger plus separate watchlist enrichment. */
  overview: InstitutionalOverview;
  /** Official holder rows for the stock selected in the URL. */
  holders: Holders | null;
  /** Current stock selection. */
  ticker: string;
}

function observedDate(value: string | null): string {
  if (value === null) {
    return 'not available';
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function metric(label: string, value: number, key: string): ReactNode {
  return (
    <Panel className="p-4">
      <p className="text-label text-ink-faint uppercase">{label}</p>
      <p className="tabular mt-2 text-2xl font-semibold text-ink" data-metric={key}>
        {value.toLocaleString('en-US')}
      </p>
    </Panel>
  );
}

function MoveList({
  heading,
  rows,
}: {
  heading: string;
  rows: InstitutionalOverview['top_buys'];
}): ReactNode {
  return (
    <Panel className="p-4">
      <h3 className="text-sm font-semibold text-ink">{heading}</h3>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-ink-faint">No comparable share-count changes stored.</p>
      ) : (
        <ol className="mt-3 divide-y divide-hairline">
          {rows.slice(0, 8).map((row) => (
            <li
              key={`${heading}-${row.filer_cik}-${row.stock_ticker}`}
              className="flex items-start justify-between gap-3 py-2"
            >
              <div className="min-w-0">
                <p className="font-mono text-sm text-ink">{row.stock_ticker}</p>
                <p className="truncate text-xs text-ink-faint">{row.filer_name}</p>
              </div>
              <div className="text-right">
                <p
                  className={`tabular text-sm ${row.shares_change_qoq > 0 ? 'text-fall' : 'text-rise'}`}
                >
                  {row.shares_change_qoq > 0 ? '+' : ''}
                  {formatShares(row.shares_change_qoq)} shares
                </p>
                <p className="text-xs text-ink-faint">{row.source_name}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

/**
 * Complete current institutional view with explicit provenance and coverage boundaries.
 */
export function InstitutionalOverviewPanel({
  overview,
  holders,
  ticker,
}: InstitutionalOverviewPanelProps): ReactNode {
  const [filter, setFilter] = useState('');
  const query = filter.trim().toLowerCase();
  const funds = overview.funds.filter((fund) =>
    `${fund.filer_name} ${fund.filer_cik}`.toLowerCase().includes(query),
  );
  const stocks = overview.stocks.filter((stock) =>
    `${stock.stock_ticker} ${stock.stock_name ?? ''}`.toLowerCase().includes(query),
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <SectionLabel tone="primary">Institutional sentiment</SectionLabel>
          <h1 className="mt-2 text-title text-ink">Current reported portfolios</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Reporting quarter:{' '}
            <span className="tabular text-ink">{overview.quarter_end ?? 'No data'}</span>
          </p>
        </div>
        <div className="text-right text-xs text-ink-faint">
          <p>Official ledger: SEC EDGAR</p>
          <p>Enrichment observed {observedDate(overview.enrichment_coverage.observed_at)}</p>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metric('Funds', overview.total_funds, 'funds')}
        {metric('Stocks', overview.total_stocks, 'stocks')}
        {metric('Reported positions', overview.total_positions, 'positions')}
        {metric('Enriched positions', overview.enrichment_coverage.matched_positions, 'enriched')}
      </div>

      <Panel className="p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div>
            <p className="text-sm font-medium text-ink">Coverage and interpretation</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">{overview.coverage_note}</p>
            <p className="mt-2 text-xs text-ink-faint">
              Enrichment matched{' '}
              {overview.enrichment_coverage.matched_funds.toLocaleString('en-US')} funds and{' '}
              {overview.enrichment_coverage.matched_positions.toLocaleString('en-US')} positions in
              this quarter.
            </p>
          </div>
        </div>
      </Panel>

      {overview.total_positions === 0 ? (
        <Panel className="p-8 text-center">
          <Database aria-hidden="true" className="mx-auto h-6 w-6 text-ink-faint" />
          <h2 className="mt-3 text-sm font-semibold text-ink">
            No institutional filings have been collected yet
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Run the SEC EDGAR collector to populate the authoritative holdings ledger.
          </p>
        </Panel>
      ) : (
        <>
          <div className="relative max-w-xl">
            <Search
              aria-hidden="true"
              className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-ink-faint"
            />
            <input
              type="search"
              aria-label="Filter funds and stocks"
              value={filter}
              onChange={(event) => {
                setFilter(event.target.value);
              }}
              placeholder="Filter by fund, CIK, company, or ticker"
              className="w-full rounded-card border border-hairline bg-panel py-2.5 pr-3 pl-9 text-sm text-ink"
            />
          </div>

          <section className="space-y-3" aria-labelledby="funds-heading">
            <div className="flex items-baseline justify-between gap-4">
              <SectionLabel tone="primary" className="!mb-0">
                <span id="funds-heading">All currently stored funds</span>
              </SectionLabel>
              <p className="text-xs text-ink-faint">
                Showing {overview.funds.length} of {overview.total_funds} funds
              </p>
            </div>
            {funds.length === 0 ? (
              <Panel className="p-4 text-sm text-ink-muted">No funds match this filter.</Panel>
            ) : (
              <Panel className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm" aria-label="Currently stored funds">
                  <thead>
                    <tr className="border-b border-hairline text-label text-ink-muted uppercase">
                      <th className="p-3 text-left font-medium">Fund</th>
                      <th className="p-3 text-right font-medium">Positions</th>
                      <th className="p-3 text-right font-medium">Official value</th>
                      <th className="p-3 text-right font-medium">Top-ten concentration</th>
                      <th className="p-3 text-right font-medium">Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {funds.map((fund) => (
                      <tr key={fund.filer_cik} className="border-b border-hairline last:border-0">
                        <th scope="row" className="p-3 text-left font-normal">
                          <p className="text-ink">{fund.filer_name}</p>
                          <p className="font-mono text-xs text-ink-faint">CIK {fund.filer_cik}</p>
                        </th>
                        <td className="tabular p-3 text-right text-ink">{fund.position_count}</td>
                        <td className="tabular p-3 text-right text-ink">
                          {formatMarketValue(fund.reported_value_usd)}
                        </td>
                        <td className="tabular p-3 text-right text-ink-muted">
                          {fund.enrichment?.top_10_concentration_pct === null ||
                          fund.enrichment === null
                            ? '--'
                            : `${fund.enrichment.top_10_concentration_pct}%`}
                        </td>
                        <td className="p-3 text-right">
                          {fund.source_url === null ? (
                            <span className="text-xs text-ink-faint">{fund.source_name}</span>
                          ) : (
                            <a
                              href={fund.source_url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="text-xs text-accent hover:underline"
                            >
                              {fund.source_name}
                            </a>
                          )}
                          {fund.enrichment !== null && (
                            <a
                              href={fund.enrichment.source_url}
                              target="_blank"
                              rel="noreferrer noopener"
                              aria-label={`${fund.filer_name} WhaleWisdom enrichment`}
                              className="mt-1 flex items-center justify-end gap-1 text-xs text-ink-muted hover:text-accent"
                            >
                              WhaleWisdom <ExternalLink aria-hidden="true" className="h-3 w-3" />
                            </a>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            )}
          </section>

          <section className="space-y-3" aria-labelledby="stocks-heading">
            <div className="flex items-baseline justify-between gap-4">
              <SectionLabel tone="primary" className="!mb-0">
                <span id="stocks-heading">All currently stored stocks</span>
              </SectionLabel>
              <p className="text-xs text-ink-faint">
                Showing {overview.stocks.length} of {overview.total_stocks} stocks
              </p>
            </div>
            {stocks.length === 0 ? (
              <Panel className="p-4 text-sm text-ink-muted">No stocks match this filter.</Panel>
            ) : (
              <Panel className="overflow-x-auto">
                <table
                  className="w-full min-w-[680px] text-sm"
                  aria-label="Currently stored stocks"
                >
                  <thead>
                    <tr className="border-b border-hairline text-label text-ink-muted uppercase">
                      <th className="p-3 text-left font-medium">Stock</th>
                      <th className="p-3 text-right font-medium">Funds</th>
                      <th className="p-3 text-right font-medium">Shares</th>
                      <th className="p-3 text-right font-medium">Reported value</th>
                      <th className="p-3 text-right font-medium">Net share change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stocks.map((stock) => (
                      <tr
                        key={stock.stock_ticker}
                        className="border-b border-hairline last:border-0"
                      >
                        <th scope="row" className="p-3 text-left font-normal">
                          <Link
                            href={`/institutional?ticker=${encodeURIComponent(stock.stock_ticker)}`}
                            className="font-mono text-accent hover:underline"
                          >
                            {stock.stock_ticker}
                          </Link>
                          <p className="text-xs text-ink-muted">
                            {stock.stock_name ?? 'Name unavailable'}
                          </p>
                        </th>
                        <td className="tabular p-3 text-right text-ink">{stock.holder_count}</td>
                        <td className="tabular p-3 text-right text-ink">
                          {formatShares(stock.shares_held)}
                        </td>
                        <td className="tabular p-3 text-right text-ink">
                          {formatMarketValue(stock.market_value_usd)}
                        </td>
                        <td className="tabular p-3 text-right text-ink-muted">
                          {stock.shares_change_qoq > 0 ? '+' : ''}
                          {formatShares(stock.shares_change_qoq)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            )}
          </section>

          <section
            className="grid gap-4 lg:grid-cols-2"
            aria-label="Largest official position changes"
          >
            <MoveList heading="Top buys" rows={overview.top_buys} />
            <MoveList heading="Top sells" rows={overview.top_sells} />
          </section>
        </>
      )}

      <section className="space-y-3">
        <TickerPicker ticker={ticker} />
        {holders !== null && <HoldersTable holders={holders} />}
      </section>
    </div>
  );
}
