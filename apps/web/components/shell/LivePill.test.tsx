import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LivePill } from './LivePill';

describe('LivePill', () => {
  it('says when the data was last refreshed', () => {
    render(<LivePill updatedLabel="2m ago" />);

    expect(screen.getByText('2m ago')).toBeInTheDocument();
  });

  it('reads as live while collection is running', () => {
    render(<LivePill updatedLabel="2m ago" />);

    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Data collection: healthy' })).toBeInTheDocument();
  });

  it('says plainly when collection has stopped', () => {
    render(<LivePill updatedLabel="41m ago" isLive={false} />);

    expect(screen.getByText('Stopped')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Data collection: failed' })).toBeInTheDocument();
  });

  it('renders the refresh label monospaced so it does not jitter as it updates', () => {
    render(<LivePill updatedLabel="2m ago" />);

    expect(screen.getByText('2m ago')).toHaveClass('tabular');
  });
});
