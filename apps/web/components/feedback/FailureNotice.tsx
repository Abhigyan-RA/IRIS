import { AlertTriangle, WifiOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { describeFailure } from '../../lib/failures';
import { Panel } from '../primitives/Panel';

/**
 * The explanation shown when a failure leaves a screen with nothing to display.
 *
 * A notice that disappears on a timer is no use here, because the reader would be left
 * looking at an empty page with no idea why. So this is rendered in place, stays put, and
 * says the same thing every other screen would say about the same failure: the wording comes
 * from one shared mapping rather than from each page.
 */
export interface FailureNoticeProps {
  /** What the screen is called, so the heading still makes sense. */
  heading: string;
  /** Whatever was thrown. */
  error: unknown;
  /** Whether a connection exists. Passed in for server rendering, where there is no navigator. */
  isOnline?: boolean;
}

/**
 * Explain a failure where the content would have been.
 *
 * @param props - The screen name and the failure.
 * @returns The notice.
 */
export function FailureNotice({ heading, error, isOnline }: FailureNoticeProps): ReactNode {
  const failure = describeFailure(error, isOnline);
  const Icon = failure.severity === 'degraded' ? WifiOff : AlertTriangle;

  return (
    <Panel className="p-6" data-testid="failure-notice">
      <h1 className="text-title text-ink">{heading}</h1>
      <div className="mt-4 flex items-start gap-3">
        <Icon
          aria-hidden="true"
          className={`mt-0.5 h-5 w-5 shrink-0 ${
            failure.severity === 'blocking' ? 'text-rise' : 'text-ink-muted'
          }`}
        />
        <div>
          <p role="alert" className="text-sm font-medium text-ink">
            {failure.title}
          </p>
          <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-ink-muted">
            {failure.detail}
          </p>
          <details className="mt-3">
            <summary className="cursor-pointer text-label text-ink-faint uppercase">
              Technical detail
            </summary>
            <p className="mt-1.5 font-mono text-xs break-words text-ink-faint">
              {failure.technical}
            </p>
          </details>
        </div>
      </div>
    </Panel>
  );
}
