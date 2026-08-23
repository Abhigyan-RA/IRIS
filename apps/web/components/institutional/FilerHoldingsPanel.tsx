import type { ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import type { FilerHoldings } from '../../lib/api';
import { Delta } from '../primitives/Delta';
import { Panel, SectionLabel } from '../primitives/Panel';
import { formatMarketValue, formatShares } from './HoldersTable';

export interface FilerHoldingsPanelProps {
  holdings: FilerHoldings;
}

/** Sector badge — small monospace label shown when no company name is available. */
function SectorBadge({ sector }: { sector: string }): ReactNode {
  return (
    <span className="bg-surface mt-0.5 inline-block rounded px-1.5 py-0.5 font-mono text-xs text-ink-faint uppercase">
      {sector}
    </span>
  );
}

/**
 * Full holdings breakdown for one institutional fund.
 *
 * Shows all reported positions from the SEC EDGAR ledger with sector labels
 * and QoQ share changes from the WhaleWisdom enrichment layer.
 */
export function FilerHoldingsPanel({ holdings }: FilerHoldingsPanelProps): ReactNode {
  const { filer_name, filer_cik, holdings: rows } = holdings;

  // Summary metrics computed from holdings
  const totalValue = rows.reduce((sum, r) => {
    const v = r.market_value_usd ? parseFloat(r.market_value_usd) : 0;
    return sum + v;
  }, 0);
  const netShareChange = rows.reduce((sum, r) => sum + (r.shares_change_qoq ?? 0), 0);
  const quarter = rows[0]?.quarter_end ?? null;

  // Sector distribution
  const sectorMap: Record<string, number> = {};
  for (const row of rows) {
    if (row.sector) {
      sectorMap[row.sector] = (sectorMap[row.sector] ?? 0) + 1;
    }
  }
  const topSectors = Object.entries(sectorMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Header */}
      <header>
        <SectionLabel tone="primary">Fund holdings</SectionLabel>
        <h1 className="mt-2 text-title text-ink">{filer_name ?? filer_cik}</h1>
        <p className="mt-1 font-mono text-sm text-ink-faint">CIK {filer_cik}</p>
        {quarter && (
          <p className="mt-1 text-sm text-ink-muted">
            Reporting quarter: <span className="tabular text-ink">{quarter}</span>
          </p>
        )}
      </header>

      {/* Summary metrics */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Panel className="p-4">
          <p className="text-label text-ink-faint uppercase">Positions</p>
          <p className="tabular mt-2 text-2xl font-semibold text-ink">
            {rows.length.toLocaleString('en-US')}
          </p>
        </Panel>
        <Panel className="p-4">
          <p className="text-label text-ink-faint uppercase">Reported value</p>
          <p className="tabular mt-2 text-2xl font-semibold text-ink">
            {formatMarketValue(totalValue.toString())}
          </p>
        </Panel>
        <Panel className="p-4">
          <p className="text-label text-ink-faint uppercase">Net share change</p>
          <p
            className={`tabular mt-2 text-2xl font-semibold ${
              netShareChange >= 0 ? 'text-rise' : 'text-fall'
            }`}
          >
            {netShareChange >= 0 ? '+' : ''}
            {formatShares(netShareChange)}
          </p>
        </Panel>
      </div>

      {/* Sector distribution */}
      {topSectors.length > 0 && (
        <Panel className="p-4">
          <p className="mb-3 text-sm font-medium text-ink">Top sectors</p>
          <div className="flex flex-wrap gap-2">
            {topSectors.map(([sector, count]) => (
              <span
                key={sector}
                className="flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1 text-xs text-ink-muted"
              >
                <span className="font-mono uppercase">{sector}</span>
                <span className="tabular text-ink-faint">{count}</span>
              </span>
            ))}
          </div>
        </Panel>
      )}

      {/* Holdings table */}
      {rows.length === 0 ? (
        <Panel className="p-8 text-center">
          <p className="text-sm text-ink-faint">No holdings stored for this fund.</p>
        </Panel>
      ) : (
        <section aria-labelledby="holdings-heading" className="space-y-3">
          <SectionLabel tone="primary">
            <span id="holdings-heading">All reported positions</span>
          </SectionLabel>
          <Panel className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm" aria-label="Fund holdings">
              <thead>
                <tr className="border-b border-hairline text-label text-ink-muted uppercase">
                  <th scope="col" className="p-3 text-left font-medium">
                    Ticker
                  </th>
                  <th scope="col" className="p-3 text-left font-medium">
                    Sector
                  </th>
                  <th scope="col" className="p-3 text-right font-medium">
                    Shares held
                  </th>
                  <th scope="col" className="p-3 text-right font-medium">
                    Market value
                  </th>
                  <th scope="col" className="p-3 text-right font-medium">
                    % of portfolio
                  </th>
                  <th scope="col" className="p-3 text-right font-medium">
                    Prior %
                  </th>
                  <th scope="col" className="p-3 text-right font-medium">
                    QoQ change
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={`${row.stock_ticker}-${row.quarter_end}`}
                    className="border-b border-hairline last:border-0"
                  >
                    <td className="p-3">
                      <span className="font-mono text-accent">{row.stock_ticker}</span>
                      {row.source_url && (
                        <a
                          href={row.source_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          aria-label={`${row.stock_ticker} filing`}
                          className="ml-1.5 inline-block align-middle text-ink-faint hover:text-accent"
                        >
                          <ExternalLink aria-hidden="true" className="h-3 w-3" />
                        </a>
                      )}
                    </td>
                    <td className="p-3">
                      {row.sector ? (
                        <SectorBadge sector={row.sector} />
                      ) : (
                        <span className="text-ink-faint">--</span>
                      )}
                    </td>
                    <td className="tabular p-3 text-right text-ink">
                      {formatShares(row.shares_held)}
                    </td>
                    <td className="tabular p-3 text-right text-ink">
                      {formatMarketValue(row.market_value_usd)}
                    </td>
                    <td className="tabular p-3 text-right text-ink-muted">
                      {row.pct_portfolio !== null ? `${row.pct_portfolio}%` : '--'}
                    </td>
                    <td className="tabular p-3 text-right text-ink-faint">
                      {row.previous_pct_portfolio !== null
                        ? `${row.previous_pct_portfolio}%`
                        : '--'}
                    </td>
                    <td className="p-3 text-right">
                      <Delta value={row.delta_pct} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </section>
      )}
    </div>
  );
}
