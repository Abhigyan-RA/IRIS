import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Sparkline } from './Sparkline';

describe('Sparkline', () => {
  it('describes the trend it draws, since a line alone tells a screen reader nothing', () => {
    render(<Sparkline values={[1, 2, 3]} label="Copper, 30 day trend, rising" />);

    expect(screen.getByRole('img', { name: 'Copper, 30 day trend, rising' })).toBeInTheDocument();
  });

  it('draws one point per value', () => {
    render(<Sparkline values={[1, 2, 3, 4]} label="Copper trend" />);

    const points = screen.getByRole('img').querySelector('polyline')?.getAttribute('points');
    expect(points?.split(' ')).toHaveLength(4);
  });

  it('spans the full width from first value to last', () => {
    render(<Sparkline values={[1, 2, 3]} label="Copper trend" width={100} />);

    const points = screen.getByRole('img').querySelector('polyline')?.getAttribute('points');
    expect(points?.startsWith('0.00,')).toBe(true);
    expect(points?.endsWith('100.00,0.00')).toBe(true);
  });

  it('draws a flat series along the middle rather than dividing by zero', () => {
    render(<Sparkline values={[5, 5, 5]} label="Flat trend" height={20} />);

    const points = screen.getByRole('img').querySelector('polyline')?.getAttribute('points');
    expect(points).toBe('0.00,20.00 36.00,20.00 72.00,20.00');
  });

  it('says so when there is not enough history to draw anything', () => {
    render(<Sparkline values={[4.52]} label="Copper trend" />);

    expect(
      screen.getByRole('img', { name: 'Copper trend: not enough history to draw a trend' }),
    ).toBeInTheDocument();
  });

  it('handles an empty series without failing', () => {
    render(<Sparkline values={[]} label="Copper trend" />);

    expect(screen.getByText('--')).toBeInTheDocument();
  });

  it('takes its colour from the caller, so a falling series can be drawn green', () => {
    render(<Sparkline values={[3, 2, 1]} label="Falling" strokeClassName="stroke-fall" />);

    expect(screen.getByRole('img').querySelector('polyline')).toHaveClass('stroke-fall');
  });
});
