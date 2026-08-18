import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Delta } from './Delta';

describe('Delta', () => {
  it('shows a rise with a plus sign and one decimal place', () => {
    render(<Delta value={8.2} />);

    expect(screen.getByText('+8.2%')).toBeInTheDocument();
  });

  it('shows a fall with a minus sign', () => {
    render(<Delta value={-2.1} />);

    expect(screen.getByText('-2.1%')).toBeInTheDocument();
  });

  it('colours a rising cost as bad news rather than as growth', () => {
    render(<Delta value={8.2} />);

    expect(screen.getByTestId('delta')).toHaveClass('text-rise');
  });

  it('colours a falling cost as good news', () => {
    render(<Delta value={-2.1} />);

    expect(screen.getByTestId('delta')).toHaveClass('text-fall');
  });

  it('states the direction in words for assistive technology', () => {
    render(<Delta value={8.2} />);

    expect(screen.getByTestId('delta')).toHaveAccessibleName('up 8.2 percent');
  });

  it('states a fall in words too', () => {
    render(<Delta value={-2.1} />);

    expect(screen.getByTestId('delta')).toHaveAccessibleName('down 2.1 percent');
  });

  it('renders an unreported change as a dash rather than as zero', () => {
    render(<Delta value={null} />);

    expect(screen.getByText('--')).toBeInTheDocument();
    expect(screen.getByTestId('delta')).toHaveAccessibleName('no change reported');
  });

  it('treats an exactly flat move as neutral', () => {
    render(<Delta value={0} />);

    expect(screen.getByTestId('delta')).toHaveClass('text-neutral');
    expect(screen.getByText('0.0%')).toBeInTheDocument();
  });

  it('can carry a period label such as the seven-day window', () => {
    render(<Delta value={8.4} period="7d" />);

    expect(screen.getByText('7d')).toBeInTheDocument();
  });

  it('accepts a decimal string, which is how the API sends it', () => {
    render(<Delta value="12.4" />);

    expect(screen.getByText('+12.4%')).toBeInTheDocument();
  });
});
