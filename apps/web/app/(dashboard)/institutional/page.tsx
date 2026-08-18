import type { ReactNode } from 'react';
import { HoldersTable } from '../../../components/institutional/HoldersTable';
import { TickerPicker } from '../../../components/institutional/TickerPicker';
import { SectionLabel } from '../../../components/primitives/Panel';
import { FailureNotice } from '../../../components/feedback/FailureNotice';
import { getHolders, type Holders } from '../../../lib/api';

/** Shown when the reader arrives without choosing a stock. */
const DEFAULT_TICKER = 'NVDA';

/**
 * Props for the institutional screen.
 */
interface InstitutionalPageProps {
  /** Query parameters, carrying the chosen ticker. */
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * The Institutional Sentiment screen: what professional money did last quarter.
 *
 * Managers overseeing more than 100 million dollars must disclose their US equity
 * positions every quarter. That makes this a slow signal compared with the price
 * screens, and a useful cross-check: it says whether anyone with money at stake is
 * acting on the same pressure the prices show.
 *
 * @param props - Query parameters.
 * @returns The institutional screen.
 */
export default async function InstitutionalPage({
  searchParams,
}: InstitutionalPageProps): Promise<ReactNode> {
  const params = await searchParams;
  const requested = params.ticker;
  const ticker = (Array.isArray(requested) ? requested[0] : requested) ?? DEFAULT_TICKER;

  let holders: Holders | null = null;
  let failure: unknown = null;

  try {
    holders = await getHolders(ticker);
  } catch (error) {
    failure = error;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <SectionLabel tone="primary">Institutional sentiment</SectionLabel>
        <TickerPicker ticker={ticker.toUpperCase()} />
      </div>

      {holders === null ? (
        <FailureNotice heading={`Holdings in ${ticker.toUpperCase()}`} error={failure} />
      ) : (
        <HoldersTable holders={holders} />
      )}

      <p className="max-w-3xl text-xs text-ink-faint">
        Quarterly disclosures describe positions as at the quarter end, not today. A fund may have
        changed its position since filing, and only long US equity positions are reported on this
        form.
      </p>
    </div>
  );
}
