/* eslint-disable react/forbid-dom-props --
   The width of a bar is the datum itself. A percentage that changes with the data
   cannot be expressed as a utility class, which is the exception the project's
   styling rule allows for. Every other value in this file is a class. */
import type { ReactNode } from 'react';
import type { RiskMap, RiskMapEntry } from '../../lib/api';
import { Panel, SectionLabel } from '../primitives/Panel';

/**
 * Work out how much of the overall movement each category accounts for.
 *
 * The share is computed from the size of each category's moves relative to the total
 * movement across all categories, so it answers "where is the pressure coming from"
 * rather than "which category has the biggest numbers". A category quoted in dollars
 * per ton and one quoted in index points are comparable this way; their prices are
 * not.
 *
 * @param map - The risk map as returned by the API.
 * @returns One entry per category with data, largest contribution first.
 */
export function contributionBySector(
  map: RiskMap,
): { sector: string; percent: number; movers: number }[] {
  const totals = map.sectors.map((group) => ({
    sector: group.sector,
    movement: group.entries.reduce(
      (sum, entry) => sum + Math.abs(Number.parseFloat(entry.pct_change_1d ?? '0')),
      0,
    ),
    movers: group.entries.filter((entry) => entry.pct_change_1d !== null).length,
  }));

  const overall = totals.reduce((sum, group) => sum + group.movement, 0);
  if (overall === 0) {
    return [];
  }

  return totals
    .filter((group) => group.movement > 0)
    .map((group) => ({
      sector: group.sector,
      percent: Number(((group.movement / overall) * 100).toFixed(1)),
      movers: group.movers,
    }))
    .sort((left, right) => right.percent - left.percent);
}

const SECTOR_BAR: Record<string, string> = {
  freight: 'bg-accent',
  energy: 'bg-warn',
  metals: 'bg-rise',
  agriculture: 'bg-fall',
};

/**
 * Props for {@link ContributionBreakdown}.
 */
export interface ContributionBreakdownProps {
  /** The risk map to summarise. */
  map: RiskMap;
}

/**
 * Which categories are driving today's movement.
 *
 * @param props - The risk map.
 * @returns The breakdown.
 */
export function ContributionBreakdown({ map }: ContributionBreakdownProps): ReactNode {
  const contributions = contributionBySector(map);

  return (
    <section aria-labelledby="contribution-heading" className="space-y-3">
      <SectionLabel>
        <span id="contribution-heading">Contribution breakdown</span>
      </SectionLabel>

      {contributions.length === 0 ? (
        <p className="text-sm text-ink-faint">
          No movement to attribute yet. This fills in once sources report a second price.
        </p>
      ) : (
        <ul className="space-y-3">
          {contributions.map((contribution) => (
            <li key={contribution.sector}>
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-ink capitalize">{contribution.sector}</span>
                <span className="tabular text-sm text-ink-muted">{contribution.percent}%</span>
              </div>
              <div
                role="meter"
                aria-valuenow={contribution.percent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${contribution.sector} share of today's movement`}
                className="mt-1 h-1.5 w-full overflow-hidden rounded-pill bg-panel-inset"
              >
                <div
                  className={`h-full ${SECTOR_BAR[contribution.sector] ?? 'bg-neutral'}`}
                  style={{ width: `${String(contribution.percent)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Props for {@link IndexSummary}.
 */
export interface IndexSummaryProps {
  /** The risk map to summarise. */
  map: RiskMap;
}

/**
 * The headline figure: how many tracked entities are moving, and how sharply.
 *
 * The design shows a single index number here. This reports what the platform can
 * actually stand behind: the number of tracked entities, how many rose, how many
 * fell, and the largest move. A composite index would need a published weighting
 * methodology, and inventing one would put a figure on screen that no source
 * supports.
 *
 * @param props - The risk map.
 * @returns The summary panel.
 */
export function IndexSummary({ map }: IndexSummaryProps): ReactNode {
  const entries: RiskMapEntry[] = map.sectors.flatMap((group) => group.entries);
  const changes = entries
    .map((entry) => Number.parseFloat(entry.pct_change_1d ?? 'NaN'))
    .filter((change) => !Number.isNaN(change));

  const rising = changes.filter((change) => change > 0).length;
  const falling = changes.filter((change) => change < 0).length;
  const largest = changes.reduce(
    (widest, change) => (Math.abs(change) > Math.abs(widest) ? change : widest),
    0,
  );
  const stale = entries.filter((entry) => entry.is_stale).length;

  return (
    <section aria-labelledby="index-heading" className="space-y-4">
      <SectionLabel tone="primary">
        <span id="index-heading">Tracked movement</span>
      </SectionLabel>

      <p className="tabular text-headline text-ink">{entries.length}</p>
      <p className="text-sm text-ink-muted">
        entities tracked, {rising} rising and {falling} falling in the last day
      </p>

      {changes.length > 0 && (
        <Panel className="p-4">
          <p className="text-label text-ink-muted uppercase">Largest move</p>
          <p className={`tabular mt-1 text-xl ${largest > 0 ? 'text-rise' : 'text-fall'}`}>
            {largest > 0 ? '+' : ''}
            {largest.toFixed(1)}%
          </p>
        </Panel>
      )}

      {stale > 0 && (
        <p className="text-sm text-warn">
          {stale} {stale === 1 ? 'figure is' : 'figures are'} behind their freshness target and
          marked stale.
        </p>
      )}
    </section>
  );
}
