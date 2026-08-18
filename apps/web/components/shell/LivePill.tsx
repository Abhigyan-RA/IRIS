import type { ReactNode } from 'react';
import { StatusDot } from '../primitives/StatusDot';

/**
 * Props for {@link LivePill}.
 */
export interface LivePillProps {
  /**
   * How long ago the data was last refreshed, already phrased for reading, such as
   * "2m ago". Formatting is the caller's job because only the caller knows whether
   * the value came from a server render or a live poll.
   */
  updatedLabel: string;
  /** Whether collection is currently running. */
  isLive?: boolean;
}

/**
 * The "live" badge in the top bar.
 *
 * It exists to answer a question a reader has before any number matters: is this
 * screen still being fed? A dashboard that looks alive while its collectors are
 * stopped is worse than one that says so.
 *
 * @param props - The refresh label and whether collection is running.
 * @returns The badge.
 */
export function LivePill({ updatedLabel, isLive = true }: LivePillProps): ReactNode {
  return (
    <span className="inline-flex items-center gap-2 rounded-pill border border-hairline bg-panel px-3 py-1">
      <StatusDot status={isLive ? 'healthy' : 'failed'} label="Data collection" />
      <span className="tabular text-xs text-ink-muted uppercase">
        {isLive ? 'Live' : 'Stopped'}
      </span>
      <span aria-hidden="true" className="text-ink-faint">
        .
      </span>
      <span className="tabular text-xs text-ink-muted">{updatedLabel}</span>
    </span>
  );
}
