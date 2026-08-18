/* eslint-disable react/forbid-dom-props --
   A marker's position is data, not styling: it is the projected coordinate of the region the
   price belongs to, and varies per entry, which no utility class can express. */
import Link from 'next/link';
import type { ReactNode } from 'react';
import type { RiskMapEntry } from '../../lib/api';
import { Delta } from '../primitives/Delta';
import { Panel, SectionLabel } from '../primitives/Panel';
import { MAP_HEIGHT, MAP_WIDTH, WorldMap, projectToMap } from './WorldMap';
import { moveSeverity } from './TopMovers';

/**
 * Where a global benchmark is drawn: the mid-Atlantic, away from the regional markers.
 *
 * A container index covering every trade lane has no single home, and putting it over one
 * continent would imply a precision the figure does not have.
 */
export const GLOBAL_COORDINATES = { longitude: -35, latitude: 25 };

/**
 * Where each region sits, in longitude and latitude.
 *
 * Real coordinates rather than percentages of a panel, so a marker lands over the place it
 * describes and stays there when the panel is resized.
 */
export const REGION_COORDINATES: Record<string, { longitude: number; latitude: number }> = {
  'North America': { longitude: -98, latitude: 39 },
  Europe: { longitude: 10, latitude: 50 },
  'Asia Pacific': { longitude: 114, latitude: 30 },
  'South America': { longitude: -58, latitude: -15 },
  Africa: { longitude: 20, latitude: 2 },
  'Middle East': { longitude: 45, latitude: 25 },
  Global: GLOBAL_COORDINATES,
};

const SEVERITY_STYLE: Record<ReturnType<typeof moveSeverity>, { dot: string; ring: string }> = {
  spike: { dot: 'fill-rise', ring: 'stroke-rise' },
  easing: { dot: 'fill-fall', ring: 'stroke-fall' },
  steady: { dot: 'fill-accent', ring: 'stroke-accent' },
};

/**
 * Spread markers that share a region so they do not sit on top of each other.
 *
 * Several tracked entities are global, and drawing them at one point would hide all but the
 * last. They are fanned out around the region's coordinate instead.
 *
 * @param index - Position of this marker among those sharing the region.
 * @returns Offset in map units.
 */
function fanOut(index: number): { dx: number; dy: number } {
  const step = 46;
  const row = Math.floor(index / 2);
  const column = index % 2;
  return { dx: column === 0 ? -step : step, dy: row * 40 - 20 };
}

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
 * The world map, with a marker over each region that has moved.
 *
 * The map is the landing view because it answers "where did something change" before the
 * reader asks anything. Markers are ordinary links, so the whole screen works by keyboard,
 * and each one states its region, price, and change in text rather than relying on position
 * and colour.
 *
 * @param props - The entries to pin and how many.
 * @returns The map panel.
 */
export function RiskMapPanel({ entries, limit = 6 }: RiskMapPanelProps): ReactNode {
  const pinned = [...entries]
    .sort(
      (left, right) =>
        Math.abs(Number.parseFloat(right.pct_change_1d ?? '0')) -
        Math.abs(Number.parseFloat(left.pct_change_1d ?? '0')),
    )
    .slice(0, limit);

  const usedPerRegion = new Map<string, number>();

  return (
    <section aria-labelledby="risk-map-heading" className="space-y-3">
      <SectionLabel tone="primary">
        <span id="risk-map-heading">Global risk map</span>
      </SectionLabel>

      <Panel className="relative overflow-hidden bg-panel-raised p-2">
        <div className="relative aspect-[960/500] w-full">
          <WorldMap />

          {pinned.length === 0 ? (
            <p className="absolute inset-0 flex items-center justify-center text-sm text-ink-faint">
              No prices have been collected yet. Markers appear as sources report.
            </p>
          ) : (
            <ul className="absolute inset-0">
              {pinned.map((entry) => {
                const coordinates = REGION_COORDINATES[entry.region] ?? GLOBAL_COORDINATES;
                const point = projectToMap(coordinates.longitude, coordinates.latitude);
                const taken = usedPerRegion.get(entry.region) ?? 0;
                usedPerRegion.set(entry.region, taken + 1);
                const offset = fanOut(taken);
                const severity = moveSeverity(entry);

                // Positions are percentages of the map's own coordinate space, so a marker
                // stays over its region at any panel size.
                const left = (((point?.x ?? 0) + offset.dx) / MAP_WIDTH) * 100;
                const top = (((point?.y ?? 0) + offset.dy) / MAP_HEIGHT) * 100;

                return (
                  <li
                    key={`${entry.sector}-${entry.entity_name}`}
                    className="absolute -translate-x-1/2 -translate-y-1/2"
                    style={{ left: `${String(left)}%`, top: `${String(top)}%` }}
                  >
                    <Link
                      href={`/ripple/${encodeURIComponent(entry.entity_name)}`}
                      className={`block rounded-card border bg-panel/95 px-2.5 py-1.5 shadow-marker ${
                        severity === 'spike'
                          ? 'border-rise'
                          : severity === 'easing'
                            ? 'border-fall'
                            : 'border-hairline-strong'
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <svg aria-hidden="true" className="h-2 w-2 shrink-0" viewBox="0 0 8 8">
                          <circle cx="4" cy="4" r="3" className={SEVERITY_STYLE[severity].dot} />
                        </svg>
                        <span className="text-label text-ink-muted uppercase">
                          {entry.region}: {entry.entity_name}
                        </span>
                        <Delta value={entry.pct_change_1d} />
                      </span>
                      <span className="tabular mt-0.5 block text-sm text-ink">
                        {entry.price} {entry.currency}/{entry.unit}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Panel>
    </section>
  );
}
