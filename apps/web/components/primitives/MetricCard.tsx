import type { ReactNode } from 'react';
import { Delta } from './Delta';
import { Panel } from './Panel';

/**
 * Props for {@link MetricCard}.
 */
export interface MetricCardProps {
  /** What is being measured, such as "Steel HRC US". */
  label: string;
  /**
   * The figure, already formatted as text. Values arrive from the API as decimal
   * strings and are passed through unchanged, so no precision is lost to a
   * floating-point conversion on the way to the screen.
   */
  value?: string | null;
  /** What one unit refers to, such as `ton` or `feu`. */
  unit?: string;
  /** Currency symbol shown before the figure. */
  currencySymbol?: string;
  /** Change in percent, or null when none was reported. */
  change?: number | string | null;
  /** Human-readable source, such as "COMEX / Chicago Spot". */
  sourceName?: string;
  /** Exact page or endpoint the figure came from. */
  sourceUrl?: string;
  /** Whether the figure is older than its category's freshness target. */
  isStale?: boolean;
  /** Whether the figure is still being fetched. */
  isLoading?: boolean;
}

/**
 * One figure with its change and its provenance.
 *
 * Used for the evidence cards under a copilot answer, the movers row on the risk
 * map, and the markers on the map itself. Every card can state where its number came
 * from, because a figure on a dashboard that cannot be traced back to a source is
 * not evidence, it is decoration.
 *
 * @param props - The figure and its context.
 * @returns The card.
 */
export function MetricCard({
  label,
  value,
  unit,
  currencySymbol = '',
  change,
  sourceName,
  sourceUrl,
  isStale = false,
  isLoading = false,
}: MetricCardProps): ReactNode {
  return (
    <Panel className="p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-label text-ink-muted uppercase">{label}</p>
        {change !== undefined && <Delta value={change ?? null} />}
      </div>

      {isLoading ? (
        <div
          role="status"
          aria-label={`Loading ${label}`}
          className="mt-3 h-6 w-24 animate-pulse rounded bg-panel-inset"
        />
      ) : (
        <div className="mt-3 flex items-baseline gap-2">
          {value === null || value === undefined ? (
            <span className="text-sm text-ink-faint">No data</span>
          ) : (
            <>
              <span className="tabular text-xl text-ink">
                {currencySymbol}
                {value}
              </span>
              {unit !== undefined && (
                <span className="tabular text-sm text-ink-muted">/ {unit}</span>
              )}
            </>
          )}
        </div>
      )}

      {(sourceName !== undefined || isStale) && (
        <div className="mt-3 flex items-center justify-between gap-2 text-xs">
          {sourceName !== undefined &&
            (sourceUrl === undefined ? (
              <span className="text-ink-faint">Source: {sourceName}</span>
            ) : (
              <a
                href={sourceUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="text-ink-faint underline decoration-hairline-strong hover:text-accent"
              >
                Source: {sourceName}
              </a>
            ))}
          {isStale && (
            <span className="rounded-pill border border-warn px-2 py-0.5 text-warn">Stale</span>
          )}
        </div>
      )}
    </Panel>
  );
}
