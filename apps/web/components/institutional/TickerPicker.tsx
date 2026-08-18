'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState, type ReactNode, type SyntheticEvent } from 'react';

/**
 * Props for {@link TickerPicker}.
 */
export interface TickerPickerProps {
  /** Ticker currently being shown. */
  ticker: string;
}

/**
 * Lets the reader choose which stock's holders to look at.
 *
 * The chosen ticker lives in the URL rather than in component state, so a view can be
 * shared or reloaded and still show the same thing. That is worth more here than
 * anywhere else in the product: these screens get pasted into messages.
 *
 * @param props - The ticker currently shown.
 * @returns The picker.
 */
export function TickerPicker({ ticker }: TickerPickerProps): ReactNode {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [draft, setDraft] = useState(searchParams.get('ticker') ?? ticker);

  function submit(event: SyntheticEvent<HTMLFormElement>): void {
    event.preventDefault();
    const cleaned = draft.trim().toUpperCase();
    if (cleaned === '') {
      return;
    }
    router.push(`/institutional?ticker=${encodeURIComponent(cleaned)}`);
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
      <label htmlFor="ticker" className="text-label text-ink-muted uppercase">
        Stock ticker
      </label>
      <input
        id="ticker"
        name="ticker"
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
        }}
        maxLength={10}
        className="tabular w-32 rounded-card border border-hairline bg-panel px-3 py-2 text-sm text-ink uppercase"
      />
      <button
        type="submit"
        className="rounded-card border border-accent px-3 py-2 text-sm text-accent hover:bg-accent-wash"
      >
        Show holders
      </button>
    </form>
  );
}
