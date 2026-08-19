import type { ReactNode } from 'react';
import { FailureNotice } from '../../../components/feedback/FailureNotice';
import { InstitutionalOverviewPanel } from '../../../components/institutional/InstitutionalOverviewPanel';
import {
  getHolders,
  getInstitutionalOverview,
  type Holders,
  type InstitutionalOverview,
} from '../../../lib/api';

/** Shown when there is no stock in the URL and the ledger is still empty. */
const DEFAULT_TICKER = 'NVDA';

interface InstitutionalPageProps {
  /** Query parameters carrying the selected stock ticker. */
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * Institutional intelligence built from the official SEC ledger with optional,
 * separately attributed WhaleWisdom watchlist enrichment.
 */
export default async function InstitutionalPage({
  searchParams,
}: InstitutionalPageProps): Promise<ReactNode> {
  let overview: InstitutionalOverview;
  try {
    overview = await getInstitutionalOverview();
  } catch (error) {
    return <FailureNotice heading="Institutional sentiment" error={error} />;
  }

  const params = await searchParams;
  const requested = params.ticker;
  const selected = Array.isArray(requested) ? requested[0] : requested;
  const ticker = (selected ?? overview.stocks[0]?.stock_ticker ?? DEFAULT_TICKER).toUpperCase();
  let holders: Holders | null = null;
  let holderFailure: unknown = null;
  try {
    holders = await getHolders(ticker);
  } catch (error) {
    holderFailure = error;
  }

  return (
    <>
      <InstitutionalOverviewPanel overview={overview} holders={holders} ticker={ticker} />
      {holders === null && (
        <div className="mt-6">
          <FailureNotice heading={`Holders in ${ticker}`} error={holderFailure} />
        </div>
      )}
    </>
  );
}
