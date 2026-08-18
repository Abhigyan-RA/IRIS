import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { ApiError } from '../../lib/failures';
import { ToastProvider, useToasts } from './Toast';

function Raiser({ error, onRetry }: { error: unknown; onRetry?: () => void }): ReactNode {
  const { notifyFailure } = useToasts();
  return (
    <button
      type="button"
      onClick={() => {
        notifyFailure(error, onRetry ? { onRetry } : undefined);
      }}
    >
      break it
    </button>
  );
}

describe('ToastProvider', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('shows nothing until something fails', () => {
    render(
      <ToastProvider>
        <p>content</p>
      </ToastProvider>,
    );

    expect(screen.queryByTestId('toast')).not.toBeInTheDocument();
  });

  it('explains a failure in plain language, not with the raw error', async () => {
    render(
      <ToastProvider>
        <Raiser error={new ApiError(503, 'psycopg pool timeout')} />
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'break it' }));

    expect(screen.getByText('The service is not ready yet')).toBeInTheDocument();
    // The raw message is present but folded away, so a reader sees the explanation first.
    expect(screen.getByText('psycopg pool timeout')).not.toBeVisible();
  });

  it('keeps the technical detail available behind a disclosure', async () => {
    render(
      <ToastProvider>
        <Raiser error={new ApiError(500, 'psycopg pool timeout')} />
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'break it' }));
    await userEvent.click(screen.getByText('Technical detail'));

    expect(screen.getByText('psycopg pool timeout')).toBeInTheDocument();
  });

  it('announces notices politely rather than interrupting', async () => {
    render(
      <ToastProvider>
        <Raiser error={new ApiError(500, 'boom')} />
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'break it' }));

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
  });

  it('offers a retry when one is given', async () => {
    const onRetry = vi.fn();
    render(
      <ToastProvider>
        <Raiser error={new ApiError(500, 'boom')} onRetry={onRetry} />
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'break it' }));
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('can be dismissed', async () => {
    render(
      <ToastProvider>
        <Raiser error={new ApiError(500, 'boom')} />
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'break it' }));
    await userEvent.click(screen.getByRole('button', { name: /dismiss/i }));

    expect(screen.queryByTestId('toast')).not.toBeInTheDocument();
  });

  it('does not stack the same failure repeated', async () => {
    render(
      <ToastProvider>
        <Raiser error={new ApiError(500, 'boom')} />
      </ToastProvider>,
    );

    const trigger = screen.getByRole('button', { name: 'break it' });
    await userEvent.click(trigger);
    await userEvent.click(trigger);
    await userEvent.click(trigger);

    expect(screen.getAllByTestId('toast')).toHaveLength(1);
  });

  it('logs the technical detail for whoever is debugging', async () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(
      <ToastProvider>
        <Raiser error={new ApiError(500, 'psycopg pool timeout')} />
      </ToastProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'break it' }));

    expect(logged).toHaveBeenCalledWith(expect.stringContaining('psycopg pool timeout'));
  });

  it('refuses to be used without a provider, since that is a wiring mistake', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(() => render(<Raiser error={new Error('x')} />)).toThrow(/ToastProvider/);
  });
});
