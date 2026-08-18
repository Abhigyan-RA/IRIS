import type { ReactNode } from 'react';
import type { HealthEvent } from '../../lib/api';
import { Panel, SectionLabel } from '../primitives/Panel';
import { StatusDot, type Status } from '../primitives/StatusDot';

/**
 * What one collector's most recent run says about it.
 */
export interface CollectorState {
  /** Collector identifier. */
  scraperId: string;
  /** Website or API it reads. */
  sourceName: string;
  /** Status derived from its most recent event. */
  status: Status;
  /** When that event happened. */
  occurredAt: string;
  /** Whether a repair was needed at any point in the events we have. */
  wasRepaired: boolean;
}

const STATUS_BY_EVENT: Record<HealthEvent['event_type'], Status> = {
  success: 'healthy',
  collection_failed: 'failed',
  self_heal_resolved: 'healthy',
  dom_shift_detected: 'degraded',
  self_heal_triggered: 'degraded',
  self_heal_failed: 'failed',
};

/**
 * Work out the current state of each collector from the event feed.
 *
 * The feed is the record of what happened; this is the answer to "so how are things
 * now". Only the most recent event per collector decides its status, because a
 * collector that broke and then recovered is working, and reporting it as broken
 * would train the reader to ignore the screen.
 *
 * @param events - Events, newest first, as the API returns them.
 * @returns One entry per collector seen, worst state first.
 */
export function collectorStates(events: readonly HealthEvent[]): CollectorState[] {
  const latest = new Map<string, CollectorState>();
  const repaired = new Set<string>();

  for (const event of events) {
    if (event.event_type === 'self_heal_resolved' || event.event_type === 'self_heal_triggered') {
      repaired.add(event.scraper_id);
    }
    // The feed arrives newest first, so the first sighting of a collector is its
    // current state and later ones are history.
    if (!latest.has(event.scraper_id)) {
      latest.set(event.scraper_id, {
        scraperId: event.scraper_id,
        sourceName: event.source_name,
        status: STATUS_BY_EVENT[event.event_type],
        occurredAt: event.occurred_at,
        wasRepaired: false,
      });
    }
  }

  const severity: Record<Status, number> = { failed: 0, degraded: 1, live: 2, healthy: 3 };
  return [...latest.values()]
    .map((state) => ({ ...state, wasRepaired: repaired.has(state.scraperId) }))
    .sort(
      (left, right) =>
        severity[left.status] - severity[right.status] ||
        left.scraperId.localeCompare(right.scraperId),
    );
}

/**
 * Props for {@link CollectorHealth}.
 */
export interface CollectorHealthProps {
  /** Events, newest first. */
  events: readonly HealthEvent[];
}

/**
 * The state of every collector, derived from the feed.
 *
 * @param props - The events.
 * @returns The summary.
 */
export function CollectorHealth({ events }: CollectorHealthProps): ReactNode {
  const states = collectorStates(events);
  const healthy = states.filter((state) => state.status === 'healthy').length;

  return (
    <section aria-labelledby="collectors-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel>
          <span id="collectors-heading">Collectors</span>
        </SectionLabel>
        {states.length > 0 && (
          <p className="tabular text-xs text-ink-faint">
            {healthy} of {states.length} healthy
          </p>
        )}
      </div>

      {states.length === 0 ? (
        <Panel className="p-4">
          <p className="text-sm text-ink-faint">
            No collector has reported yet, so there is nothing to summarise.
          </p>
        </Panel>
      ) : (
        <ul className="space-y-2">
          {states.map((state) => (
            <li key={state.scraperId}>
              <Panel className="flex items-center gap-3 p-3">
                <StatusDot status={state.status} label={state.scraperId} />
                <span className="tabular min-w-0 flex-1 truncate text-sm text-ink">
                  {state.scraperId}
                </span>
                {state.wasRepaired && (
                  <span className="rounded-pill border border-accent px-2 py-0.5 text-xs text-accent">
                    Repaired
                  </span>
                )}
                <time dateTime={state.occurredAt} className="tabular text-xs text-ink-faint">
                  {state.occurredAt.slice(11, 19)}
                </time>
              </Panel>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
