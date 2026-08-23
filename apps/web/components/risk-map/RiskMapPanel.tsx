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

/**
 * Override coordinates for specific entities that have a more precise home than their
 * region's centroid. Metals trade globally but the benchmarks originate in specific
 * financial centres; freight indices are averages of global lanes.
 */
export const ENTITY_COORDINATES: Record<string, { longitude: number; latitude: number }> = {
  // LME metals — London
  Copper: { longitude: -0.1, latitude: 51.5 },
  Gold: { longitude: -0.1, latitude: 51.5 },
  Aluminum: { longitude: -0.1, latitude: 51.5 },
  // Global freight indices — mid-Atlantic
  FBX_Global: { longitude: -35, latitude: 25 },
  Baltic_Dry_Index: { longitude: -35, latitude: 38 },
  // Henry Hub natural gas — Louisiana
  Natural_Gas: { longitude: -91, latitude: 30 },
};

const SEVERITY_STYLE: Record<ReturnType<typeof moveSeverity>, { dot: string; ring: string }> = {
  spike: { dot: 'fill-rise', ring: 'stroke-rise' },
  easing: { dot: 'fill-fall', ring: 'stroke-fall' },
  steady: { dot: 'fill-accent', ring: 'stroke-accent' },
};

/**
 * Shorten a tracked entity's name to something that fits on a marker.
 *
 * Stored names are identifiers, not labels: a freight lane is filed as
 * `FBX01_China_to_North_America_West_Coast`. Printed in full it is wider than the
 * ocean it crosses, and several of them overlap into an unreadable pile. A lane is
 * therefore shown by its code, which is how the route is referred to in practice, and
 * every other name simply reads as words. The full name stays on the link's title and
 * in the movers list below the map.
 *
 * @param entityName - The stored entity name.
 * @returns The label to draw on the marker.
 */
export function markerLabel(entityName: string): string {
  const code = /^(FBX\d+)_/i.exec(entityName)?.[1];
  if (code !== undefined) {
    return code.toUpperCase();
  }
  return entityName.replace(/_/g, ' ');
}

/**
 * Choose which entries to pin — at most one per region+sector combination.
 *
 * A region can legitimately have both an energy move and a freight move at the same
 * time. Showing one per region+sector keeps the map informative without overplotting:
 * North America can show WTI (energy) and an FBX lane (freight) as separate pins.
 * Within each region+sector pair, the largest mover is chosen.
 *
 * @param entries - Every entry available.
 * @param limit - Maximum total markers (prevents a fully-loaded map becoming unreadable).
 * @returns The entries to pin, largest move first.
 */
export function oneMarkerPerRegion(
  entries: readonly RiskMapEntry[],
  limit: number,
): RiskMapEntry[] {
  const byMove = [...entries].sort(
    (left, right) => Math.abs(changeOf(right)) - Math.abs(changeOf(left)),
  );
  const pinned: RiskMapEntry[] = [];
  const slotsTaken = new Set<string>();
  for (const entry of byMove) {
    if (pinned.length >= limit) {
      break;
    }
    // Key on region+sector so each region can show one pin per asset class.
    const slot = `${entry.region}::${entry.sector}`;
    if (slotsTaken.has(slot)) {
      continue;
    }
    slotsTaken.add(slot);
    pinned.push(entry);
  }
  return pinned;
}

/**
 * Read an entry's daily change as a number.
 *
 * @param entry - The entry.
 * @returns The change, or zero when none was reported. A missing change is not a
 * move, so it sorts last rather than breaking the comparison.
 */
function changeOf(entry: RiskMapEntry): number {
  const parsed = Number.parseFloat(entry.pct_change_1d ?? '0');
  return Number.isNaN(parsed) ? 0 : parsed;
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
export function RiskMapPanel({ entries, limit = 12 }: RiskMapPanelProps): ReactNode {
  const pinned = oneMarkerPerRegion(entries, limit);

  // When two pins land at the same projected point (e.g. two Global entries),
  // stagger them vertically so they don't stack invisibly.
  const seen = new Map<string, number>();
  const withOffset = pinned.map((entry) => {
    const coordinates =
      ENTITY_COORDINATES[entry.entity_name] ??
      REGION_COORDINATES[entry.region] ??
      GLOBAL_COORDINATES;
    const point = projectToMap(coordinates.longitude, coordinates.latitude);
    const key = `${String(point?.x ?? 0)},${String(point?.y ?? 0)}`;
    const count = seen.get(key) ?? 0;
    seen.set(key, count + 1);
    return { entry, point, stackIndex: count };
  });

  return (
    <section aria-labelledby="risk-map-heading" className="space-y-3">
      <SectionLabel tone="primary">
        <span id="risk-map-heading">Global risk map</span>
      </SectionLabel>

      <Panel className="relative overflow-hidden bg-panel-raised p-2">
        <div className="relative aspect-[960/500] w-full">
          <WorldMap />

          {withOffset.length === 0 ? (
            <p className="absolute inset-0 flex items-center justify-center text-sm text-ink-faint">
              No prices have been collected yet. Markers appear as sources report.
            </p>
          ) : (
            <ul className="absolute inset-0">
              {withOffset.map(({ entry, point, stackIndex }) => {
                const severity = moveSeverity(entry);
                const left = ((point?.x ?? 0) / MAP_WIDTH) * 100;
                // Stagger pins sharing the same coordinate (e.g. two Global entries)
                const top = ((point?.y ?? 0) / MAP_HEIGHT) * 100 + stackIndex * 6;

                return (
                  <li
                    key={`${entry.sector}-${entry.entity_name}`}
                    className="absolute -translate-x-1/2 -translate-y-1/2"
                    style={{ left: `${String(left)}%`, top: `${String(top)}%` }}
                  >
                    <Link
                      href={`/ripple/${encodeURIComponent(entry.entity_name)}`}
                      title={entry.entity_name}
                      className={`block rounded-card border bg-panel/95 px-2.5 py-1.5 shadow-marker ${
                        severity === 'spike'
                          ? 'border-rise'
                          : severity === 'easing'
                            ? 'border-fall'
                            : 'border-hairline-strong'
                      }`}
                    >
                      <span className="flex items-center gap-2 whitespace-nowrap">
                        <svg aria-hidden="true" className="h-2 w-2 shrink-0" viewBox="0 0 8 8">
                          <circle cx="4" cy="4" r="3" className={SEVERITY_STYLE[severity].dot} />
                        </svg>
                        <span className="text-label text-ink-muted uppercase">
                          {entry.region}: {markerLabel(entry.entity_name)}
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
