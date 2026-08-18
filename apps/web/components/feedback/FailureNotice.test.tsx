import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ApiError } from '../../lib/failures';
import { FailureNotice } from './FailureNotice';

describe('FailureNotice', () => {
  it('keeps the screen heading so the reader knows where they are', () => {
    render(<FailureNotice heading="Global risk map" error={new ApiError(0, 'x')} isOnline />);

    expect(screen.getByRole('heading', { name: 'Global risk map' })).toBeInTheDocument();
  });

  it('explains the failure instead of printing the raw error', () => {
    render(
      <FailureNotice
        heading="Global risk map"
        error={new ApiError(0, 'fetch failed: ECONNREFUSED 127.0.0.1:8000')}
        isOnline
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('The service cannot be reached');
    expect(screen.getByText(/ECONNREFUSED/)).not.toBeVisible();
  });

  it('reveals the technical detail on request', async () => {
    render(
      <FailureNotice heading="Ripple" error={new ApiError(500, 'psycopg failure')} isOnline />,
    );

    await userEvent.click(screen.getByText('Technical detail'));

    expect(screen.getByText('psycopg failure')).toBeVisible();
  });

  it('announces the failure to assistive technology', () => {
    render(<FailureNotice heading="Ripple" error={new ApiError(503, 'x')} isOnline />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('describes being offline as a connection problem, not a server fault', () => {
    render(<FailureNotice heading="Ripple" error={new ApiError(500, 'x')} isOnline={false} />);

    expect(screen.getByRole('alert')).toHaveTextContent('You appear to be offline');
  });
});
