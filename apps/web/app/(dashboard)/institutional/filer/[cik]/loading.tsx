import type { ReactNode } from 'react';
import { Panel } from '../../../../../components/primitives/Panel';

/** Skeleton shown while the fund's holdings are fetched. */
export default function FilerLoading(): ReactNode {
  return (
    <div role="status" aria-label="Loading fund holdings" className="space-y-6">
      <div className="h-20 animate-pulse rounded-card bg-panel" />
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((key) => (
          <Panel key={key} className="h-20 animate-pulse">
            <span className="sr-only">Loading metric</span>
          </Panel>
        ))}
      </div>
      <Panel className="h-96 animate-pulse">
        <span className="sr-only">Loading holdings table</span>
      </Panel>
    </div>
  );
}
