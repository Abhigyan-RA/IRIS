/* eslint-disable react/forbid-dom-props --
   A marker's position on the map is data, not styling: the coordinates come from the
   region table and vary per entry, which no utility class can express. This is the
   exception the project's styling rule allows for. */
import Link from 'next/link';
import type { ReactNode } from 'react';
import type { RiskMapEntry } from '../../lib/api';
import { Delta } from '../primitives/Delta';
import { Panel, SectionLabel } from '../primitives/Panel';
import { moveSeverity } from './TopMovers';

/**
 * Where each region sits on the map, as a percentage of the panel's width and
 * height.
 *
 * The design shows markers pinned over continents. Rather than ship a projection
 * library and coordinate data for a picture with five pins on it, each region is
 * given a position once, here. Adding a region means adding a line.
 */
export const REGION_POSITIONS: Record<string, { left: string; top: string }> = {
  'North America': { left: '18%', top: '30%' },
  Europe: { left: '48%', top: '24%' },
  'Asia Pacific': { left: '76%', top: '38%' },
  'South America': { left: '30%', top: '68%' },
  Africa: { left: '52%', top: '58%' },
  Global: { left: '50%', top: '46%' },
};

const SEVERITY_STYLE: Record<ReturnType<typeof moveSeverity>, string> = {
  spike: 'border-rise text-rise',
  easing: 'border-fall text-fall',
  steady: 'border-hairline-strong text-ink-muted',
};

/**
 * Props for {@link RiskMapPanel}.
 */
export interface RiskMapPanelProps {
  /** Entries to pin, usually the largest movers across all categories. */
  entries: readonly RiskMapEntry[];
  /** How many to pin. More than a handful makes the map unreadable. */
  limit?: number;
}

/**
 * The world map with a marker over each region that has moved.
 *
 * The map is the landing view because it answers "where did something change"
 * before the reader asks anything. Markers are ordinary links, so the whole screen
 * is reachable by keyboard, and each one states its region, price, and change in
 * text rather than relying on position and colour.
 *
 * @param props - The entries to pin and how many.
 * @returns The map panel.
 */
export function RiskMapPanel({ entries, limit = 5 }: RiskMapPanelProps): ReactNode {
  const pinned = [...entries]
    .sort(
      (left, right) =>
        Math.abs(Number.parseFloat(right.pct_change_1d ?? '0')) -
        Math.abs(Number.parseFloat(left.pct_change_1d ?? '0')),
    )
    .slice(0, limit);

  return (
    <section aria-labelledby="risk-map-heading" className="space-y-3">
      <SectionLabel tone="primary">
        <span id="risk-map-heading">Global risk map</span>
      </SectionLabel>

      <Panel className="relative h-[26rem] overflow-hidden bg-panel-raised">
        {/* The land mass behind the markers is decorative: the information is in the
            markers, so it is hidden from assistive technology rather than described. */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-[radial-gradient(circle_at_30%_35%,rgba(148,163,184,0.10),transparent_45%),radial-gradient(circle_at_70%_45%,rgba(148,163,184,0.08),transparent_40%)]"
        />

        {pinned.length === 0 ? (
          <p className="absolute inset-0 flex items-center justify-center text-sm text-ink-faint">
            No prices have been collected yet. Markers appear as sources report.
          </p>
        ) : (
          <ul className="absolute inset-0">
            {pinned.map((entry) => {
              const position = REGION_POSITIONS[entry.region] ?? REGION_POSITIONS.Global;
              const severity = moveSeverity(entry);
              return (
                <li
                  key={`${entry.sector}-${entry.entity_name}`}
                  className="absolute -translate-x-1/2 -translate-y-1/2"
                  style={{ left: position?.left, top: position?.top }}
                >
                  <Link
                    href={`/ripple/${encodeURIComponent(entry.entity_name)}`}
                    className={`block rounded-card border bg-panel/90 px-3 py-2 shadow-marker ${SEVERITY_STYLE[severity]}`}
                  >
                    <span className="flex items-center gap-2">
                      <span className="text-label text-ink-muted uppercase">
                        {entry.region}: {entry.entity_name}
                      </span>
                      <Delta value={entry.pct_change_1d} />
                    </span>
                    <span className="tabular mt-1 block text-base text-ink">
                      {entry.price} {entry.currency}/{entry.unit}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </section>
  );
}
