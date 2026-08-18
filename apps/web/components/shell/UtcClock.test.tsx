import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UtcClock, formatUtcClock } from './UtcClock';

describe('formatUtcClock', () => {
  it('formats a moment as a zero-padded UTC wall clock', () => {
    expect(formatUtcClock(new Date('2026-08-15T14:32:05Z'))).toBe('14:32:05');
  });

  it('pads single digits so the width never changes', () => {
    expect(formatUtcClock(new Date('2026-08-15T04:03:02Z'))).toBe('04:03:02');
  });

  it('ignores the reader local timezone, since the data is global', () => {
    const sameInstant = new Date('2026-08-15T14:32:05+09:00');

    expect(formatUtcClock(sameInstant)).toBe('05:32:05');
  });
});

describe('UtcClock', () => {
  it('shows the given moment in UTC', () => {
    render(<UtcClock now={new Date('2026-08-15T14:32:05Z')} />);

    expect(screen.getByText('14:32:05 UTC')).toBeInTheDocument();
  });

  it('exposes the moment in a machine-readable form', () => {
    render(<UtcClock now={new Date('2026-08-15T14:32:05Z')} />);

    expect(screen.getByRole('time')).toHaveAttribute('datetime', '2026-08-15T14:32:05.000Z');
  });

  it('renders monospaced so the digits do not shift each second', () => {
    render(<UtcClock now={new Date('2026-08-15T14:32:05Z')} />);

    expect(screen.getByRole('time')).toHaveClass('tabular');
  });
});
