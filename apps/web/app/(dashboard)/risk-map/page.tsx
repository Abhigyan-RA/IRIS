import type { ReactNode } from 'react';
import { RiskMapPanel } from '../../../components/risk-map/RiskMapPanel';
import { ContributionBreakdown, IndexSummary } from '../../../components/risk-map/IndexSummary';
import { TopMovers } from '../../../components/risk-map/TopMovers';
import { LanePrices } from '../../../components/risk-map/LanePrices';
import { FailureNotice } from '../../../components/feedback/FailureNotice';
import { getRiskMap, type RiskMap } from '../../../lib/api';

/**
 * The Global Risk Map: the landing screen.
 *
 * It answers "where did something change" before the reader asks a question, which
 * is why it is the default view. The map pins the largest movers, the row beneath
 * ranks them, and the right-hand column says which categories the pressure is coming
 * from.
 *
 * Data is fetched on the server so the first paint already contains figures, and a
 * failure is reported on the page rather than left as an empty layout: an operator
 * needs to know the difference between "nothing moved" and "we cannot reach the API".
 *
 * @returns The risk map screen.
 */
export default async function RiskMapPage(): Promise<ReactNode> {
  let map: RiskMap | null = null;
  let failure: unknown = null;

  try {
    map = await getRiskMap();
  } catch (error) {
    failure = error;
  }

  if (map === null) {
    return <FailureNotice heading="Global risk map" error={failure} />;
  }

  const entries = map.sectors.flatMap((group) => group.entries);

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_21rem]">
      <div className="min-w-0 space-y-6">
        <RiskMapPanel entries={entries} />
        <TopMovers entries={entries} />
        <LanePrices entries={entries} />
      </div>

      <aside className="space-y-8">
        <IndexSummary map={map} />
        <ContributionBreakdown map={map} />
      </aside>
    </div>
  );
}
