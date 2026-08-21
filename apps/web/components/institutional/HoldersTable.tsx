import type { ReactNode } from 'react';
import type { Holders } from '../../lib/api';
import { professionalFilerLabel } from '../../lib/filers';
import { Delta } from '../primitives/Delta';
import { Panel, SectionLabel } from '../primitives/Panel';

/**
 * Format a reported position value the way the design does.
 *
 * Large sums are abbreviated so a column of them can be compared at a glance:
 * `$1.24B` reads faster than `$1,240,000,000`, and the exact figure is one click away
 * in the filing.
 *
 * @param value - Value in dollars, as a decimal string, or null when unreported.
 * @returns The abbreviated value, or a dash when there is nothing to show.
 */
export function formatMarketValue(value: string | null): string {
  if (value === null) {
    return '--';
  }
  const amount = Number.parseFloat(value);
  if (Number.isNaN(amount)) {
    return '--';
  }
  if (amount >= 1_000_000_000) {
    return `$${(amount / 1_000_000_000).toFixed(2)}B`;
  }
  if (amount >= 1_000_000) {
    return `$${(amount / 1_000_000).toFixed(1)}M`;
  }
  return `$${amount.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

/**
 * Format a share count with thousands separators.
 *
 * @param shares - Number of shares.
 * @returns The formatted count.
 */
export function formatShares(shares: number): string {
  return shares.toLocaleString('en-US');
}

/**
 * Props for {@link HoldersTable}.
 */
export interface HoldersTableProps {
  /** The positions to show. */
  holders: Holders;
}

/**
 * Which funds hold a stock, and what they did with it last quarter.
 *
 * This is the second, independent signal beside the price data: a commodity moving is
 * one thing, professional money positioning for it is another. Every row states the
 * quarter it describes, because a holding is a snapshot at a date and not a live
 * position.
 *
 * @param props - The positions.
 * @returns The table.
 */
export function HoldersTable({ holders }: HoldersTableProps): ReactNode {
  return (
    <section aria-labelledby="holders-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel tone="primary">
          <span id="holders-heading">Smart money moves</span>
        </SectionLabel>
        <p className="tabular text-xs text-ink-faint">Source: SEC Form 13F</p>
      </div>

      {holders.holders.length === 0 ? (
        <Panel className="p-6">
          <p className="text-sm text-ink-faint">
            No fund has reported a position in {holders.ticker}. Filings are read as the regulator
            publishes them, so a stock with no rows here has not appeared in a disclosure we have
            collected.
          </p>
        </Panel>
      ) : (
        <Panel className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Funds reporting a position in {holders.ticker}, largest first
            </caption>
            <thead>
              <tr className="border-b border-hairline text-label text-ink-muted uppercase">
                <th scope="col" className="p-3 text-left font-medium">
                  Filer name
                </th>
                <th scope="col" className="p-3 text-right font-medium">
                  Shares held
                </th>
                <th scope="col" className="p-3 text-right font-medium">
                  Market value
                </th>
                <th scope="col" className="p-3 text-right font-medium">
                  Percent of portfolio
                </th>
                <th scope="col" className="p-3 text-right font-medium">
                  Quarter
                </th>
                <th scope="col" className="p-3 text-right font-medium">
                  Change since prior quarter
                </th>
              </tr>
            </thead>
            <tbody>
              {holders.holders.map((holder) => (
                <tr
                  key={`${holder.filer_cik}-${holder.quarter_end}`}
                  className="border-b border-hairline last:border-0"
                >
                  <th scope="row" className="p-3 text-left font-normal text-ink">
                    {holder.source_url === null ? (
                      <span title={holder.filer_name}>
                        {professionalFilerLabel(holder.filer_name)}
                      </span>
                    ) : (
                      <a
                        href={holder.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        title={holder.filer_name}
                        className="hover:text-accent"
                      >
                        {professionalFilerLabel(holder.filer_name)}
                      </a>
                    )}
                  </th>
                  <td className="tabular p-3 text-right text-ink">
                    {formatShares(holder.shares_held)}
                  </td>
                  <td className="tabular p-3 text-right text-ink">
                    {formatMarketValue(holder.market_value_usd)}
                  </td>
                  <td className="tabular p-3 text-right text-ink-muted">
                    {holder.pct_portfolio === null ? '--' : `${holder.pct_portfolio}%`}
                  </td>
                  <td className="tabular p-3 text-right text-ink-muted">{holder.quarter_end}</td>
                  <td className="p-3 text-right">
                    <Delta value={holder.delta_pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </section>
  );
}
