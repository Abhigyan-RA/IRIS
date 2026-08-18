import { AlertTriangle, Bot, CheckCircle2, XCircle } from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';
import type { HealthEvent } from '../../lib/api';
import { Panel, SectionLabel } from '../primitives/Panel';

/**
 * How each stage of a collector run is presented.
 *
 * The label text is what appears on screen and in logs. Bracketed words rather than
 * emoji: they are searchable, they survive any terminal or log aggregator, and a
 * screen reader announces them predictably. The icon beside each label is a named
 * component from the icon library, which is both clearer and more accessible than a
 * pictograph pasted into a string.
 */
export const EVENT_PRESENTATION: Record<
  HealthEvent['event_type'],
  { label: string; icon: ComponentType<{ className?: string }>; tone: string }
> = {
  success: { label: '[OK]', icon: CheckCircle2, tone: 'text-fall border-fall' },
  collection_failed: { label: '[FAILED]', icon: XCircle, tone: 'text-rise border-rise' },
  dom_shift_detected: { label: '[WARNING]', icon: AlertTriangle, tone: 'text-warn border-warn' },
  self_heal_triggered: { label: '[AUTO-HEALING]', icon: Bot, tone: 'text-accent border-accent' },
  self_heal_resolved: { label: '[RESOLVED]', icon: CheckCircle2, tone: 'text-fall border-fall' },
  self_heal_failed: { label: '[FAILED]', icon: XCircle, tone: 'text-rise border-rise' },
};

/**
 * Format an event timestamp as a UTC wall clock.
 *
 * @param isoTimestamp - Timestamp as returned by the API.
 * @returns The time as `HH:MM:SS`, or the original text when it cannot be parsed.
 */
export function formatEventTime(isoTimestamp: string): string {
  const moment = new Date(isoTimestamp);
  if (Number.isNaN(moment.getTime())) {
    return isoTimestamp;
  }
  return moment.toISOString().slice(11, 19);
}

/**
 * Props for {@link AuditLog}.
 */
export interface AuditLogProps {
  /** Events, newest first, as the API returns them. */
  events: readonly HealthEvent[];
}

/**
 * The self-healing audit log.
 *
 * This is the screen that answers a fair question about any scraping system: what
 * happens when a website changes? The feed shows the answer as it happened, with the
 * detection, the repair, and the recovery each timed, so the claim can be checked
 * rather than believed.
 *
 * @param props - The events to show.
 * @returns The log.
 */
export function AuditLog({ events }: AuditLogProps): ReactNode {
  return (
    <section aria-labelledby="audit-heading" className="space-y-3">
      <SectionLabel tone="primary">
        <span id="audit-heading">Self-healing audit log</span>
      </SectionLabel>

      {events.length === 0 ? (
        <Panel className="p-6">
          <p className="text-sm text-ink-faint">
            No collector activity has been recorded yet. Runs appear here as the scheduler works
            through the sources.
          </p>
        </Panel>
      ) : (
        <Panel className="divide-y divide-hairline">
          <ul>
            {events.map((event) => {
              const presentation = EVENT_PRESENTATION[event.event_type];
              const Icon = presentation.icon;
              return (
                <li
                  key={`${event.scraper_id}-${event.occurred_at}-${event.event_type}`}
                  className="flex flex-wrap items-start gap-3 border-b border-hairline p-3 last:border-0"
                >
                  <time
                    dateTime={event.occurred_at}
                    className="tabular w-20 shrink-0 text-xs text-ink-faint"
                  >
                    {formatEventTime(event.occurred_at)}
                  </time>

                  <span className="tabular w-40 shrink-0 truncate text-xs text-ink-muted">
                    {event.scraper_id}
                  </span>

                  <span
                    className={`inline-flex shrink-0 items-center gap-2 rounded-card border px-2 py-1 text-xs ${presentation.tone}`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {presentation.label}
                  </span>

                  <span className="min-w-48 flex-1 text-sm text-ink">
                    {event.message ?? event.event_type.replace(/_/g, ' ')}
                  </span>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}
    </section>
  );
}
