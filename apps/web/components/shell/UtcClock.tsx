'use client';

import { Clock } from 'lucide-react';
import { useSyncExternalStore, type ReactNode } from 'react';

/**
 * Formats a moment as a UTC wall clock, as shown in the top bar.
 *
 * UTC rather than local time because the data is global: a freight rate published at
 * 14:00 UTC is the same event for a reader in Chicago and one in Singapore, and a
 * local timestamp would have two people describe the same figure differently.
 *
 * @param moment - The moment to format.
 * @returns The time as `HH:MM:SS`.
 */
export function formatUtcClock(moment: Date): string {
  const hours = String(moment.getUTCHours()).padStart(2, '0');
  const minutes = String(moment.getUTCMinutes()).padStart(2, '0');
  const seconds = String(moment.getUTCSeconds()).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

/**
 * Subscribe to the passing of each second.
 *
 * @param onTick - Called once per second.
 * @returns A function that stops the ticking.
 */
function subscribeToSeconds(onTick: () => void): () => void {
  const timer = setInterval(onTick, 1000);
  return () => {
    clearInterval(timer);
  };
}

/**
 * Read the current time, rounded to the second.
 *
 * @returns Milliseconds since the epoch, truncated to whole seconds so that the
 * value only changes when the displayed time does.
 */
function readNow(): number {
  return Math.floor(Date.now() / 1000) * 1000;
}

/**
 * Read the time to use for the very first render.
 *
 * The server renders a fixed epoch rather than its own clock: if it rendered the real
 * time, the markup would differ from what the browser produces a moment later, and
 * React would report a mismatch. The browser corrects it on its first tick.
 *
 * @returns A stable value for the server render.
 */
function readServerNow(): number {
  return 0;
}

/**
 * Props for {@link UtcClock}.
 */
export interface UtcClockProps {
  /**
   * Fixed moment to display. Used by tests and Storybook so the clock is
   * predictable; omitted in the running app, where it ticks.
   */
  now?: Date | undefined;
}

/**
 * A ticking UTC clock.
 *
 * The clock is an external system as far as React is concerned, so it is subscribed
 * to rather than copied into state on a timer. That keeps the component free of an
 * effect that writes state on mount.
 *
 * @param props - Optionally a fixed moment.
 * @returns The clock.
 */
export function UtcClock({ now }: UtcClockProps): ReactNode {
  const ticking = useSyncExternalStore(subscribeToSeconds, readNow, readServerNow);
  const moment = now ?? new Date(ticking);

  return (
    <span className="inline-flex items-center gap-2 text-ink-muted">
      <Clock aria-hidden="true" className="h-4 w-4" />
      <time dateTime={moment.toISOString()} className="tabular text-sm">
        {formatUtcClock(moment)} UTC
      </time>
    </span>
  );
}
