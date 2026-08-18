import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MetricCard } from './MetricCard';

describe('MetricCard', () => {
  it('shows the label, value, and unit', () => {
    render(<MetricCard label="Steel HRC US" value="840" unit="ton" currencySymbol="$" />);

    expect(screen.getByText('Steel HRC US')).toBeInTheDocument();
    expect(screen.getByText('$840')).toBeInTheDocument();
    expect(screen.getByText('/ ton')).toBeInTheDocument();
  });

  it('shows the change when there is one', () => {
    render(<MetricCard label="Steel HRC US" value="840" unit="ton" change={8.2} />);

    expect(screen.getByText('+8.2%')).toBeInTheDocument();
  });

  it('attributes the figure to its source', () => {
    render(
      <MetricCard label="Steel HRC US" value="840" unit="ton" sourceName="COMEX / Chicago Spot" />,
    );

    expect(screen.getByText('Source: COMEX / Chicago Spot')).toBeInTheDocument();
  });

  it('links to the source when a URL is given, so a figure can be checked', () => {
    render(
      <MetricCard
        label="Copper"
        value="4.52"
        unit="lb"
        sourceName="investing.com"
        sourceUrl="https://www.investing.com/commodities/copper"
      />,
    );

    const link = screen.getByRole('link', { name: /investing.com/ });
    expect(link).toHaveAttribute('href', 'https://www.investing.com/commodities/copper');
  });

  it('opens an external source safely in a new tab', () => {
    render(
      <MetricCard
        label="Copper"
        value="4.52"
        unit="lb"
        sourceName="investing.com"
        sourceUrl="https://www.investing.com/commodities/copper"
      />,
    );

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noreferrer noopener');
  });

  it('marks a figure that is behind its freshness target', () => {
    render(<MetricCard label="Copper" value="4.52" unit="lb" isStale />);

    expect(screen.getByText('Stale')).toBeInTheDocument();
  });

  it('does not mark a fresh figure', () => {
    render(<MetricCard label="Copper" value="4.52" unit="lb" />);

    expect(screen.queryByText('Stale')).not.toBeInTheDocument();
  });

  it('renders numbers in the monospaced style so columns line up', () => {
    render(<MetricCard label="Copper" value="4.52" unit="lb" />);

    expect(screen.getByText('4.52')).toHaveClass('tabular');
  });

  it('shows a loading placeholder instead of an empty card', () => {
    render(<MetricCard label="Copper" isLoading />);

    expect(screen.getByRole('status', { name: 'Loading Copper' })).toBeInTheDocument();
  });

  it('says plainly when there is no value rather than showing a blank', () => {
    render(<MetricCard label="Copper" value={null} />);

    expect(screen.getByText('No data')).toBeInTheDocument();
  });
});
