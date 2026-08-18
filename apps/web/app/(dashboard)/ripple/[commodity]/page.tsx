import type { ReactNode } from 'react';
import { RippleChain, RippleLinks } from '../../../../components/ripple/RippleChain';
import { PropagationReport, SelectedNode } from '../../../../components/ripple/SelectedNode';
import { FailureNotice } from '../../../../components/feedback/FailureNotice';
import { getRipple, getTrend, type Ripple, type Trend } from '../../../../lib/api';

/**
 * Props for the ripple screen.
 */
interface RipplePageProps {
  /** Route parameters, carrying the commodity to examine. */
  params: Promise<{ commodity: string }>;
}

/**
 * The Ripple Effect screen: what a price move touches downstream.
 *
 * This is the answer to "why should I care". A price on its own is a number; the
 * chain from copper to stator coils to electric-vehicle manufacturing is what makes
 * it a consequence.
 *
 * Price history and the graph traversal are fetched together. History is optional:
 * an entity can be in the graph before any source reports a price for it, and the
 * screen is still useful in that state, so a missing price is not treated as a
 * failure.
 *
 * @param props - Route parameters.
 * @returns The ripple screen.
 */
export default async function RipplePage({ params }: RipplePageProps): Promise<ReactNode> {
  const { commodity: raw } = await params;
  const commodity = decodeURIComponent(raw);

  let ripple: Ripple | null = null;
  let trend: Trend | null;
  let failure: unknown = null;

  try {
    ripple = await getRipple(commodity);
  } catch (error) {
    failure = error;
  }

  try {
    // A commodity can exist in the graph before any price is recorded for it, so a
    // missing price is an expected state rather than a failure worth reporting.
    trend = await getTrend(commodity);
  } catch {
    trend = null;
  }

  if (ripple === null) {
    return <FailureNotice heading={commodity} error={failure} />;
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[20rem_1fr]">
      <aside className="min-w-0">
        <SelectedNode trend={trend} commodity={commodity} />
      </aside>

      <div className="min-w-0 space-y-6">
        <PropagationReport ripple={ripple} />
        <RippleChain ripple={ripple} />
        <RippleLinks ripple={ripple} />
      </div>
    </div>
  );
}
