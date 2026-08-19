import type { ReactNode } from 'react';
import { Panel } from '../../../components/primitives/Panel';

/** Stable in-place loading state while the latest institutional quarter is read. */
export default function InstitutionalLoading(): ReactNode {
  return (
    <div role="status" aria-label="Loading institutional intelligence" className="space-y-6">
      <div className="h-16 animate-pulse rounded-card bg-panel" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((key) => (
          <Panel key={key} className="h-24 animate-pulse">
            <span className="sr-only">Loading metric</span>
          </Panel>
        ))}
      </div>
      <Panel className="h-72 animate-pulse">
        <span className="sr-only">Loading holdings</span>
      </Panel>
      <span className="sr-only">Loading institutional intelligence</span>
    </div>
  );
}
