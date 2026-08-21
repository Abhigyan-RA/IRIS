import type { ReactNode } from 'react';
import Link from 'next/link';
import { Panel, SectionLabel } from '../../../components/primitives/Panel';
import { ApiError, getRiskMap } from '../../../lib/api';

/**
 * The ripple screen with nothing selected yet.
 *
 * Reached by clicking the rail rather than a marker, so it offers the tracked
 * entities to choose from instead of showing an empty graph.
 *
 * @returns The chooser.
 */
export default async function RippleIndexPage(): Promise<ReactNode> {
  let names: string[] = [];
  let failure: string | null = null;

  try {
    const map = await getRiskMap();
    names = map.sectors.flatMap((group) => group.entries.map((entry) => entry.entity_name)).sort();
  } catch (error) {
    failure =
      error instanceof ApiError ? error.message : 'The tracked entities could not be loaded.';
  }

  return (
    <div className="max-w-3xl space-y-4">
      <SectionLabel tone="primary">Ripple effect</SectionLabel>
      <h1 className="text-title text-ink">Choose something to trace</h1>
      <p className="text-sm text-ink-muted">
        Pick a tracked entity to see what it feeds into and which funds hold companies exposed to
        it.
      </p>

      {failure !== null && <p className="text-sm text-warn">{failure}</p>}

      {names.length === 0 && failure === null ? (
        <Panel className="p-6">
          <p className="text-sm text-ink-faint">
            Nothing is being tracked yet. Entities appear here once a collector has reported a
            price.
          </p>
        </Panel>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {names.map((name) => (
            <li key={name}>
              <Link
                href={`/ripple/${encodeURIComponent(name)}`}
                className="inline-block max-w-full rounded-card border border-hairline bg-panel px-3 py-2 text-sm break-words text-ink hover:border-accent hover:text-accent"
              >
                {name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
