import type { ReactNode } from 'react';
import { Panel, SectionLabel } from '../../../components/primitives/Panel';
import { AuditLog } from '../../../components/pipeline/AuditLog';
import { CollectorHealth } from '../../../components/pipeline/CollectorHealth';
import { ApiError, getHealthFeed, type HealthFeed } from '../../../lib/api';

/**
 * The Pipeline Health screen.
 *
 * Every other screen asks you to trust the numbers. This one shows how they were
 * obtained: which collectors ran, which broke, which repaired themselves, and how
 * long each step took. A dashboard that cannot show its own failures is asking for
 * trust it has not earned.
 *
 * @returns The pipeline health screen.
 */
export default async function PipelineHealthPage(): Promise<ReactNode> {
  let feed: HealthFeed | null = null;
  let failure: string | null = null;

  try {
    feed = await getHealthFeed(100);
  } catch (error) {
    failure =
      error instanceof ApiError
        ? error.message
        : 'The health feed could not be loaded for an unexpected reason.';
  }

  if (feed === null) {
    return (
      <Panel className="p-6">
        <SectionLabel tone="primary">Pipeline health</SectionLabel>
        <p className="mt-2 text-sm text-warn">{failure}</p>
        <p className="mt-1 text-sm text-ink-faint">
          Check that the API is running and that the database schema has been applied.
        </p>
      </Panel>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_21rem]">
      <div className="min-w-0">
        <AuditLog events={feed.events} />
      </div>

      <aside className="space-y-6">
        <CollectorHealth events={feed.events} />
        <p className="text-xs text-ink-faint">
          A repair works by describing what to look for on a page rather than where it sits, which
          is why a redesign can be recovered from without anyone editing code. Failed repairs are
          left visible rather than retried indefinitely.
        </p>
      </aside>
    </div>
  );
}
