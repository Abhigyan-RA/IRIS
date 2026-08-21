import type { ReactNode } from 'react';
import type { RiskMapEntry } from '../../lib/api';
import { Delta } from '../primitives/Delta';
import { Panel, SectionLabel } from '../primitives/Panel';
import { StatusDot } from '../primitives/StatusDot';

/**
 * How large a daily move has to be before it counts as a spike worth flagging.
 *
 * Read from the design, where the flagged markers sit at 8.2 and 12.4 percent while
 * ordinary entries sit near 1 to 5 percent. It is a display threshold only: nothing
 * about the stored data changes.
 */
export const SPIKE_THRESHOLD_PERCENT = 5;

/**
 * Decide how prominently to draw an entry.
 *
 * @param entry - The entry to judge.
 * @returns `spike` for a large rise, `easing` for a large fall, `steady` otherwise.
 */
export function moveSeverity(entry: RiskMapEntry): 'spike' | 'easing' | 'steady' {
  if (entry.pct_change_1d === null) {
    return 'steady';
  }
  const change = Number.parseFloat(entry.pct_change_1d);
  if (Number.isNaN(change)) {
    return 'steady';
  }
  if (change >= SPIKE_THRESHOLD_PERCENT) {
    return 'spike';
  }
  if (change <= -SPIKE_THRESHOLD_PERCENT) {
    return 'easing';
  }
  return 'steady';
}

const SEVERITY_BORDER: Record<ReturnType<typeof moveSeverity>, string> = {
  spike: 'border-rise',
  easing: 'border-fall',
  steady: 'border-hairline',
};

/**
 * Props for {@link MoverCard}.
 */
export interface MoverCardProps {
  /** The entry to show. */
  entry: RiskMapEntry;
}

/**
 * One entry in the movers row.
 *
 * @param props - The entry.
 * @returns The card.
 */
export function MoverCard({ entry }: MoverCardProps): ReactNode {
  const severity = moveSeverity(entry);
  return (
    <Panel className={`min-w-0 p-4 ${SEVERITY_BORDER[severity]}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-label text-ink-muted uppercase">{entry.sector}</p>
        <StatusDot
          status={severity === 'spike' ? 'failed' : severity === 'easing' ? 'healthy' : 'live'}
          label={`${entry.entity_name} movement`}
        />
      </div>
      <p className="mt-2 truncate text-sm text-ink" title={entry.entity_name}>
        {entry.entity_name}
      </p>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="tabular text-sm text-ink">{entry.price}</span>
        <Delta value={entry.pct_change_1d} />
      </div>
    </Panel>
  );
}

/**
 * Props for {@link TopMovers}.
 */
export interface TopMoversProps {
  /** Entries across all categories. */
  entries: readonly RiskMapEntry[];
  /** How many to show. */
  limit?: number;
}

/**
 * The row of largest movers beneath the map.
 *
 * Ordered by the size of the move regardless of direction, because the reader's
 * question is "what changed most", not "what went up".
 *
 * @param props - The entries and how many to show.
 * @returns The row.
 */
export function TopMovers({ entries, limit = 6 }: TopMoversProps): ReactNode {
  const ranked = [...entries]
    .filter((entry) => entry.pct_change_1d !== null)
    .sort(
      (left, right) =>
        Math.abs(Number.parseFloat(right.pct_change_1d ?? '0')) -
        Math.abs(Number.parseFloat(left.pct_change_1d ?? '0')),
    )
    .slice(0, limit);

  return (
    <section aria-labelledby="top-movers-heading" className="space-y-3">
      <SectionLabel>
        <span id="top-movers-heading">Top movers (24h)</span>
      </SectionLabel>

      {ranked.length === 0 ? (
        <Panel className="p-4">
          <p className="text-sm text-ink-faint">
            No daily changes have been reported yet. Movers appear once a source has published
            twice.
          </p>
        </Panel>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
          {ranked.map((entry) => (
            <li key={`${entry.sector}-${entry.entity_name}`}>
              <MoverCard entry={entry} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
