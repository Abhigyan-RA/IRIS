'use client';

import { AlertTriangle, RefreshCw, WifiOff, X } from 'lucide-react';
import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { describeFailure } from '../../lib/failures';
import type { FriendlyFailure } from '../../lib/failures';

/**
 * Transient notices, for failures that do not stop a screen working.
 *
 * A toast is the right shape for a failure the reader can ignore: a refresh that did not
 * land, a repair that was refused. A failure that empties the screen is not a toast, because
 * a notice that disappears would leave a blank page with no explanation; those are rendered
 * in place instead.
 *
 * Notices are announced politely to assistive technology and never auto-dismiss, since a
 * message that vanishes on a timer is unreadable for anyone who reads slowly.
 */

/** One notice on screen. */
export interface Toast extends FriendlyFailure {
  /** Identity, so a repeat of the same failure replaces rather than stacks. */
  id: string;
  /** Optional action, offered when trying again could work. */
  onRetry?: () => void;
}

interface ToastContextValue {
  toasts: readonly Toast[];
  /** Show a failure, described in plain language. */
  notifyFailure: (error: unknown, options?: { id?: string; onRetry?: () => void }) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/**
 * Make the notice area available to a tree.
 *
 * @param props - The subtree that may raise notices.
 * @returns The provider, with the notice area rendered above the page.
 */
export function ToastProvider({ children }: { children: ReactNode }): ReactNode {
  const [toasts, setToasts] = useState<readonly Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notifyFailure = useCallback(
    (error: unknown, options?: { id?: string; onRetry?: () => void }) => {
      const described = describeFailure(error);
      const id = options?.id ?? described.title;
      // Log the technical detail where a developer will look for it, and keep it off the
      // screen. This is the one place the raw message is emitted, which is why the rule
      // against console output is lifted here rather than anywhere else.
      // eslint-disable-next-line no-console
      console.error(`[shadow-cpi] ${described.title}: ${described.technical}`);
      const retry = options?.onRetry;
      const toast: Toast = retry ? { ...described, id, onRetry: retry } : { ...described, id };
      setToasts((current) => [...current.filter((existing) => existing.id !== id), toast]);
    },
    [],
  );

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, notifyFailure, dismiss }),
    [toasts, notifyFailure, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

/**
 * Read the notice area from a component.
 *
 * @returns The notice controls.
 * @throws If used outside {@link ToastProvider}, which is a wiring mistake worth failing on.
 */
export function useToasts(): ToastContextValue {
  const context = useContext(ToastContext);
  if (context === null) {
    throw new Error('useToasts must be used inside a ToastProvider');
  }
  return context;
}

/**
 * The stack of notices.
 *
 * @param props - Notices and how to dismiss them.
 * @returns The notice area, or nothing when there is nothing to say.
 */
function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: readonly Toast[];
  onDismiss: (id: string) => void;
}): ReactNode {
  if (toasts.length === 0) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((toast) => {
        const Icon = toast.severity === 'degraded' ? WifiOff : AlertTriangle;
        return (
          <div
            key={toast.id}
            data-testid="toast"
            className={`pointer-events-auto rounded-card border bg-panel-raised p-3 shadow-marker ${
              toast.severity === 'blocking' ? 'border-rise' : 'border-hairline-strong'
            }`}
          >
            <div className="flex items-start gap-2.5">
              <Icon
                aria-hidden="true"
                className={`mt-0.5 h-4 w-4 shrink-0 ${
                  toast.severity === 'blocking' ? 'text-rise' : 'text-ink-muted'
                }`}
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{toast.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">{toast.detail}</p>
                {toast.onRetry ? (
                  <button
                    type="button"
                    onClick={toast.onRetry}
                    className="mt-2 inline-flex items-center gap-1.5 rounded-pill border border-hairline-strong px-2 py-1 text-label text-ink-muted uppercase hover:text-ink"
                  >
                    <RefreshCw aria-hidden="true" className="h-3 w-3" />
                    Try again
                  </button>
                ) : null}
                <details className="mt-2">
                  <summary className="cursor-pointer text-label text-ink-faint uppercase">
                    Technical detail
                  </summary>
                  <p className="mt-1 font-mono text-xs break-words text-ink-faint">
                    {toast.technical}
                  </p>
                </details>
              </div>
              <button
                type="button"
                onClick={() => {
                  onDismiss(toast.id);
                }}
                aria-label={`Dismiss: ${toast.title}`}
                className="shrink-0 text-ink-faint hover:text-ink"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
