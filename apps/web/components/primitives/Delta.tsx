import { ArrowDown, ArrowUp } from 'lucide-react';
import type { ReactNode } from 'react';

/**
 * Props for {@link Delta}.
 */
export interface DeltaProps {
  /**
   * The change in percent. The API sends decimals as strings to avoid rounding,
   * so both are accepted. `null` means no change was reported, which is different
   * from a change of zero.
   */
  value: number | string | null;
  /** Optional window label, such as `7d`, shown beside the figure. */
  period?: string;
}

/**
 * A percentage change, coloured by what it means for cost.
 *
 * Rising costs are shown in red and falling costs in green. That is the opposite of
 * a stock chart, and it is deliberate: a reader of this dashboard is buying these
 * things, so a price going up is bad news.
 *
 * The direction is also written out in the accessible name, because an arrow glyph
 * and a colour are both invisible to a screen reader.
 *
 * @param props - The change and an optional period label.
 * @returns The figure with its arrow.
 */
export function Delta({ value, period }: DeltaProps): ReactNode {
  if (value === null) {
    return (
      <span data-testid="delta" aria-label="no change reported" className="tabular text-ink-faint">
        --
      </span>
    );
  }

  const numeric = typeof value === 'string' ? Number.parseFloat(value) : value;
  if (Number.isNaN(numeric)) {
    return (
      <span data-testid="delta" aria-label="no change reported" className="tabular text-ink-faint">
        --
      </span>
    );
  }

  const magnitude = Math.abs(numeric).toFixed(1);
  const isFlat = numeric === 0;
  const isRise = numeric > 0;

  const tone = isFlat ? 'text-neutral' : isRise ? 'text-rise' : 'text-fall';
  const spokenDirection = isFlat ? 'unchanged at' : isRise ? 'up' : 'down';
  const sign = isFlat ? '' : isRise ? '+' : '-';

  return (
    <span
      data-testid="delta"
      aria-label={`${spokenDirection} ${magnitude} percent`}
      className={`tabular inline-flex items-center gap-1 text-sm ${tone}`}
    >
      <span>{`${sign}${magnitude}%`}</span>
      {!isFlat &&
        (isRise ? (
          <ArrowUp aria-hidden="true" className="h-3 w-3" />
        ) : (
          <ArrowDown aria-hidden="true" className="h-3 w-3" />
        ))}
      {period !== undefined && <span className="text-ink-faint">{period}</span>}
    </span>
  );
}
