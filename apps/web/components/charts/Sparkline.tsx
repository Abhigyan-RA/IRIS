import type { ReactNode } from 'react';

/**
 * Props for {@link Sparkline}.
 */
export interface SparklineProps {
  /** Values, oldest first. Two or more are needed to draw a line. */
  values: readonly number[];
  /** Line colour, given as a Tailwind stroke class. */
  strokeClassName?: string;
  /** Accessible description, such as "Copper, 30 day trend, rising". */
  label: string;
  /** Width in pixels. */
  width?: number;
  /** Height in pixels. */
  height?: number;
}

/**
 * A tiny trend line, drawn inline.
 *
 * Hand-drawn as an SVG path rather than pulled from a charting library: these appear
 * dozens of times per screen, with no axes, labels, tooltips, or interaction, and a
 * chart component per sparkline would cost far more than the shape is worth.
 *
 * @param props - The values and how to draw them.
 * @returns The sparkline, or an empty placeholder when there is not enough data.
 */
export function Sparkline({
  values,
  strokeClassName = 'stroke-accent',
  label,
  width = 72,
  height = 24,
}: SparklineProps): ReactNode {
  if (values.length < 2) {
    return (
      <span
        role="img"
        aria-label={`${label}: not enough history to draw a trend`}
        className="inline-block text-xs text-ink-faint"
      >
        --
      </span>
    );
  }

  const lowest = Math.min(...values);
  const highest = Math.max(...values);
  // A flat series would divide by zero, so it is drawn along the middle instead.
  const span = highest - lowest || 1;

  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - ((value - lowest) / span) * height;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return (
    <svg
      role="img"
      aria-label={label}
      width={width}
      height={height}
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      className="overflow-visible"
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={strokeClassName}
      />
    </svg>
  );
}
