import type { ReactNode } from 'react';

/**
 * The four states anything in this interface can be in.
 *
 * `live` means actively updating, which the design distinguishes from merely
 * healthy by using the accent colour rather than green.
 */
export type Status = 'healthy' | 'degraded' | 'failed' | 'live';

const STATUS_COLOURS: Record<Status, string> = {
  healthy: 'bg-fall',
  degraded: 'bg-warn',
  failed: 'bg-rise',
  live: 'bg-accent',
};

/**
 * Props for {@link StatusDot}.
 */
export interface StatusDotProps {
  /** What state the thing being described is in. */
  status: Status;
  /** What the dot refers to, such as "Freight and shipping". */
  label: string;
}

/**
 * A small coloured dot indicating status.
 *
 * The dot carries an accessible name that states both the subject and its status,
 * because colour alone is invisible to a screen reader and ambiguous to anyone who
 * cannot distinguish red from green.
 *
 * @param props - The status and what it refers to.
 * @returns The dot.
 */
export function StatusDot({ status, label }: StatusDotProps): ReactNode {
  return (
    <span
      role="img"
      aria-label={`${label}: ${status}`}
      className={`inline-block h-2 w-2 rounded-pill ${STATUS_COLOURS[status]}`}
    />
  );
}
