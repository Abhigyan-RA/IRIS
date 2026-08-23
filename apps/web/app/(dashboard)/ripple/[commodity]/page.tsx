import type { ReactNode } from 'react';
import { RippleChain, RippleLinks } from '../../../../components/ripple/RippleChain';
import { PropagationReport, SelectedNode } from '../../../../components/ripple/SelectedNode';
import { ExposedFunds } from '../../../../components/ripple/ExposedFunds';
import { FailureNotice } from '../../../../components/feedback/FailureNotice';
import { getRipple, getTrend, type Ripple, type Trend } from '../../../../lib/api';

/**
 * Props for the ripple screen.
 */
interface RipplePageProps {
  /** Route parameters, carrying the commodity to examine. */
  params: Promise<{ commodity: string }>;
  /** Search parameters, carrying optional depth override. */
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * The Ripple Effect screen: what a price move touches downstream.
 */
export default async function RipplePage({
  params,
  searchParams,
}: RipplePageProps): Promise<ReactNode> {
  const { commodity: raw } = await params;
  const commodity = decodeURIComponent(raw);

  // Allow depth override via ?depth=3 for deeper traversal
  const sp = await searchParams;
  const depthParam = Array.isArray(sp.depth) ? sp.depth[0] : sp.depth;
  const depth = depthParam ? Math.min(5, Math.max(1, parseInt(depthParam, 10))) : 3;

  let ripple: Ripple | null = null;
  let trend: Trend | null;
  let failure: unknown = null;

  try {
    ripple = await getRipple(commodity, depth);
  } catch (error) {
    failure = error;
  }

  try {
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
        <ExposedFunds ripple={ripple} />
      </div>
    </div>
  );
}
