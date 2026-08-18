import type { ReactNode } from 'react';
import { AuditLog } from '../../../components/pipeline/AuditLog';
import { CollectorHealth } from '../../../components/pipeline/CollectorHealth';
import { FailureNotice } from '../../../components/feedback/FailureNotice';
import { getHealthFeed, type HealthFeed } from '../../../lib/api';

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
  let failure: unknown = null;

  try {
    feed = await getHealthFeed(100);
  } catch (error) {
    failure = error;
  }

  if (feed === null) {
    return <FailureNotice heading="Pipeline health" error={failure} />;
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
