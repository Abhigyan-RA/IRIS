import Link from 'next/link';
import type { ReactNode } from 'react';
import type { RiskMapEntry } from '../../lib/api';
import { Delta } from '../primitives/Delta';
import { Panel, SectionLabel } from '../primitives/Panel';

/**
 * The individual trade lanes behind a container freight index.
 *
 * The headline index is an average across routes, and an average is the least useful number
 * on the page for anyone who ships on one route. The lanes are collected separately and shown
 * ranked by cost, because that is the question an importer actually has: what does my route
 * cost, and is it one of the expensive ones.
 */

/** Lane names arrive as a code and a route, for example ``FBX03_China_to_North_America``. */
const LANE_NAME = /^([A-Z]+\d{2})_(.+)$/;

/**
 * Split a stored lane name into its code and a readable route.
 *
 * @param entityName - The stored name.
 * @returns The code and route, or null when the name is not a lane.
 */
export function readLaneName(entityName: string): { code: string; route: string } | null {
  const matched = LANE_NAME.exec(entityName);
  if (matched === null) {
    return null;
  }
  const [, code, route] = matched;
  if (code === undefined || route === undefined) {
    return null;
  }
  return { code, route: route.replaceAll('_', ' ') };
}

/**
 * Props for {@link LanePrices}.
 */
export interface LanePricesProps {
  /** Every tracked entry. Lanes are picked out of it by name. */
  entries: readonly RiskMapEntry[];
}

/**
 * A ranked table of lane prices.
 *
 * @param props - The entries to look through.
 * @returns The panel, or nothing when no lanes have been collected.
 */
export function LanePrices({ entries }: LanePricesProps): ReactNode {
  const lanes = entries
    .map((entry) => ({ entry, name: readLaneName(entry.entity_name) }))
    .filter(
      (candidate): candidate is { entry: RiskMapEntry; name: { code: string; route: string } } =>
        Boolean(candidate.name),
    )
    .sort(
      (left, right) => Number.parseFloat(right.entry.price) - Number.parseFloat(left.entry.price),
    );

  if (lanes.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="lanes-heading" className="space-y-3">
      <SectionLabel tone="primary">
        <span id="lanes-heading">Container lanes, most expensive first</span>
      </SectionLabel>

      <Panel className="overflow-hidden">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            Container freight prices per lane, ranked from most to least expensive
          </caption>
          <thead>
            <tr className="border-b border-hairline text-label text-ink-faint uppercase">
              <th scope="col" className="px-4 py-2.5 text-left font-normal">
                Lane
              </th>
              <th scope="col" className="px-4 py-2.5 text-left font-normal">
                Route
              </th>
              <th scope="col" className="px-4 py-2.5 text-right font-normal">
                Price
              </th>
              <th scope="col" className="px-4 py-2.5 text-right font-normal">
                Change
              </th>
            </tr>
          </thead>
          <tbody>
            {lanes.map(({ entry, name }) => (
              <tr key={entry.entity_name} className="border-b border-hairline last:border-0">
                <th scope="row" className="px-4 py-2.5 text-left font-normal text-ink-muted">
                  {name.code}
                </th>
                <td className="px-4 py-2.5 text-ink">
                  <Link
                    href={`/ripple/${encodeURIComponent(entry.entity_name)}`}
                    className="hover:text-accent"
                  >
                    {name.route}
                  </Link>
                </td>
                <td className="tabular px-4 py-2.5 text-right text-ink">
                  {entry.price} {entry.currency}/{entry.unit}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <Delta value={entry.pct_change_1d} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <p className="text-xs text-ink-faint">
        Lane prices are read from the same page as the headline index, which publishes one
        percentage change for the index as a whole rather than per lane. A lane shows a change only
        once enough readings exist to work one out.
      </p>
    </section>
  );
}
