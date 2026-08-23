import type { ReactNode } from 'react';
import Link from 'next/link';
import type { Ripple } from '../../lib/api';
import { Panel, SectionLabel } from '../primitives/Panel';
import { formatShares } from '../institutional/HoldersTable';

/**
 * Props for {@link ExposedFunds}.
 */
export interface ExposedFundsProps {
  /** The traversal result, which carries the exposed filers when any are found. */
  ripple: Ripple;
}

/**
 * Funds holding companies that are exposed to this commodity.
 *
 * This connects the supply-chain graph back to institutional positions:
 * a move in copper matters more when a large fund is positioned in companies
 * that depend on it.
 *
 * @param props - The traversal result.
 * @returns The panel, or nothing when no funds are exposed.
 */
export function ExposedFunds({ ripple }: ExposedFundsProps): ReactNode {
  if (ripple.exposed_filers.length === 0) {
    return (
      <section aria-labelledby="exposed-heading" className="space-y-3">
        <SectionLabel>
          <span id="exposed-heading">Exposed funds</span>
        </SectionLabel>
        <Panel className="p-4">
          <p className="text-sm text-ink-faint">
            No fund positions linked to companies exposed to {ripple.commodity} are recorded yet.
            Fund-to-company-to-commodity links are built from the institutional holdings ledger.
          </p>
        </Panel>
      </section>
    );
  }

  return (
    <section aria-labelledby="exposed-heading" className="space-y-3">
      <SectionLabel>
        <span id="exposed-heading">Exposed funds</span>
      </SectionLabel>

      <Panel className="overflow-x-auto">
        <table
          className="w-full min-w-[560px] text-sm"
          aria-label="Funds exposed to this commodity"
        >
          <thead>
            <tr className="border-b border-hairline text-label text-ink-muted uppercase">
              <th scope="col" className="p-3 text-left font-medium">
                Fund
              </th>
              <th scope="col" className="p-3 text-left font-medium">
                Via company
              </th>
              <th scope="col" className="p-3 text-right font-medium">
                Shares held
              </th>
              <th scope="col" className="p-3 text-right font-medium">
                Quarter
              </th>
            </tr>
          </thead>
          <tbody>
            {ripple.exposed_filers.map((row, i) => {
              const filer = typeof row.filer === 'string' ? row.filer : '';
              const cik = typeof row.cik === 'string' ? row.cik : '';
              const ticker = typeof row.ticker === 'string' ? row.ticker : '';
              const shares = typeof row.shares === 'number' ? row.shares : 0;
              const quarter = typeof row.quarter === 'string' ? row.quarter : '';
              const rawDelta = row.delta_pct;
              const deltaPct =
                typeof rawDelta === 'number'
                  ? rawDelta
                  : typeof rawDelta === 'string'
                    ? Number(rawDelta)
                    : null;

              return (
                <tr
                  key={`${cik}-${ticker}-${String(i)}`}
                  className="border-b border-hairline last:border-0"
                >
                  <td className="p-3">
                    {cik !== '' ? (
                      <Link
                        href={`/institutional/filer/${encodeURIComponent(cik)}`}
                        className="text-accent hover:underline"
                      >
                        {filer !== '' ? filer : cik}
                      </Link>
                    ) : (
                      <span className="text-ink">{filer}</span>
                    )}
                  </td>
                  <td className="p-3">
                    <Link
                      href={`/institutional?ticker=${encodeURIComponent(ticker)}`}
                      className="font-mono text-accent hover:underline"
                    >
                      {ticker}
                    </Link>
                  </td>
                  <td className="tabular p-3 text-right text-ink">
                    {formatShares(shares)}
                    {deltaPct !== null && (
                      <span className={`ml-2 text-xs ${deltaPct >= 0 ? 'text-rise' : 'text-fall'}`}>
                        {deltaPct >= 0 ? '+' : ''}
                        {deltaPct.toFixed(1)}%
                      </span>
                    )}
                  </td>
                  <td className="tabular p-3 text-right text-ink-muted">{quarter}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}
