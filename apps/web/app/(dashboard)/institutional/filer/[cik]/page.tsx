import type { ReactNode } from 'react';
import Link from 'next/link';
import { FailureNotice } from '../../../../../components/feedback/FailureNotice';
import { FilerHoldingsPanel } from '../../../../../components/institutional/FilerHoldingsPanel';
import { getFilerHoldings, type FilerHoldings } from '../../../../../lib/api';

interface FilerPageProps {
  params: Promise<{ cik: string }>;
}

/**
 * Full holdings breakdown for one institutional fund.
 * Data comes from the SEC EDGAR ledger stored in the database,
 * enriched with sector labels from the WhaleWisdom scraper.
 */
export default async function FilerPage({ params }: FilerPageProps): Promise<ReactNode> {
  const { cik } = await params;

  let data: FilerHoldings;
  try {
    data = await getFilerHoldings(cik);
  } catch (error) {
    return (
      <div className="space-y-4">
        <Link href="/institutional" className="text-sm text-accent hover:underline">
          &larr; Back to institutional overview
        </Link>
        <FailureNotice heading="Fund holdings" error={error} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/institutional" className="text-sm text-accent hover:underline">
          &larr; Institutional overview
        </Link>
      </div>
      <FilerHoldingsPanel holdings={data} />
    </div>
  );
}
