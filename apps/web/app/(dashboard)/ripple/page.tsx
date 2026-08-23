import type { ReactNode } from 'react';
import Link from 'next/link';
import { Panel, SectionLabel } from '../../../components/primitives/Panel';
import { Delta } from '../../../components/primitives/Delta';
import { ApiError, getRiskMap } from '../../../lib/api';

const SECTOR_LABELS: Record<string, string> = {
  energy: 'Energy',
  freight: 'Freight & Shipping',
  metals: 'Metals',
  agriculture: 'Agriculture',
};

const SECTOR_ORDER = ['energy', 'metals', 'freight', 'agriculture'];

/**
 * The ripple index: all tracked entities grouped by sector with live prices.
 *
 * Reached by clicking the rail rather than a marker. Shows every tracked entity
 * so an analyst can immediately see what's moving and pick something to trace.
 */
export default async function RippleIndexPage(): Promise<ReactNode> {
  let failure: string | null = null;
  const bySector: Record<
    string,
    {
      name: string;
      price: string;
      currency: string;
      unit: string;
      change: string | null;
      region: string;
    }[]
  > = {};

  try {
    const map = await getRiskMap();
    for (const group of map.sectors) {
      bySector[group.sector] = group.entries.map((e) => ({
        name: e.entity_name,
        price: e.price,
        currency: e.currency,
        unit: e.unit,
        change: e.pct_change_1d,
        region: e.region,
      }));
    }
  } catch (error) {
    failure =
      error instanceof ApiError ? error.message : 'The tracked entities could not be loaded.';
  }

  const totalEntities = Object.values(bySector).reduce((s, g) => s + g.length, 0);

  return (
    <div className="space-y-6">
      <header>
        <SectionLabel tone="primary">Ripple effect</SectionLabel>
        <h1 className="mt-2 text-title text-ink">Choose something to trace</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Pick a tracked entity to see what it feeds into downstream and which funds hold companies
          exposed to it.
          {totalEntities > 0 && (
            <span className="ml-1 text-ink-faint">({totalEntities} entities tracked)</span>
          )}
        </p>
      </header>

      {failure !== null && <p className="text-sm text-warn">{failure}</p>}

      {totalEntities === 0 && failure === null ? (
        <Panel className="p-6">
          <p className="text-sm text-ink-faint">
            Nothing is being tracked yet. Entities appear here once a collector has reported a
            price.
          </p>
        </Panel>
      ) : (
        <div className="space-y-8">
          {SECTOR_ORDER.filter((s) => bySector[s]?.length).map((sector) => (
            <section key={sector} aria-labelledby={`${sector}-heading`} className="space-y-3">
              <SectionLabel>
                <span id={`${sector}-heading`}>{SECTOR_LABELS[sector] ?? sector}</span>
              </SectionLabel>

              <Panel className="overflow-x-auto">
                <table className="w-full min-w-[500px] text-sm" aria-label={`${sector} entities`}>
                  <thead>
                    <tr className="border-b border-hairline text-label text-ink-muted uppercase">
                      <th scope="col" className="p-3 text-left font-medium">
                        Entity
                      </th>
                      <th scope="col" className="p-3 text-left font-medium">
                        Region
                      </th>
                      <th scope="col" className="p-3 text-right font-medium">
                        Price
                      </th>
                      <th scope="col" className="p-3 text-right font-medium">
                        24h change
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(bySector[sector] ?? []).map((entry) => (
                      <tr
                        key={entry.name}
                        className="border-b border-hairline last:border-0 hover:bg-panel-raised"
                      >
                        <td className="p-3">
                          <Link
                            href={`/ripple/${encodeURIComponent(entry.name)}`}
                            className="text-accent hover:underline"
                          >
                            {entry.name.replace(/_/g, ' ')}
                          </Link>
                        </td>
                        <td className="p-3 text-ink-muted">{entry.region}</td>
                        <td className="tabular p-3 text-right text-ink">
                          {entry.price} {entry.currency}
                          <span className="text-ink-faint">/{entry.unit}</span>
                        </td>
                        <td className="p-3 text-right">
                          <Delta value={entry.change} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
