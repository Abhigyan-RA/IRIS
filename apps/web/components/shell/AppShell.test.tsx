import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppShell, TopBar } from './AppShell';

vi.mock('next/navigation', () => ({
  usePathname: () => '/risk-map',
}));

const FIXED_MOMENT = new Date('2026-08-15T14:32:05Z');

describe('TopBar', () => {
  it('is a banner landmark carrying the product name', () => {
    render(<TopBar updatedLabel="2m ago" now={FIXED_MOMENT} />);

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByText('Shadow CPI')).toBeInTheDocument();
  });

  it('says whether collection is running and when it last did', () => {
    render(<TopBar updatedLabel="2m ago" now={FIXED_MOMENT} />);

    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.getByText('2m ago')).toBeInTheDocument();
  });

  it('offers a labelled search field', () => {
    render(<TopBar updatedLabel="2m ago" now={FIXED_MOMENT} />);

    expect(screen.getByRole('searchbox', { name: 'Search' })).toBeInTheDocument();
  });

  it('takes its search placeholder from the screen using it', () => {
    render(
      <TopBar
        updatedLabel="2m ago"
        searchPlaceholder="Search indicators, logs, nodes"
        now={FIXED_MOMENT}
      />,
    );

    expect(screen.getByPlaceholderText('Search indicators, logs, nodes')).toBeInTheDocument();
  });

  it('shows the shared UTC reference every figure is timestamped against', () => {
    render(<TopBar updatedLabel="2m ago" now={FIXED_MOMENT} />);

    expect(screen.getByText('14:32:05 UTC')).toBeInTheDocument();
  });
});

describe('AppShell', () => {
  it('renders the screen inside a main landmark', () => {
    render(
      <AppShell now={FIXED_MOMENT} currentPath="/risk-map">
        <p>Risk map</p>
      </AppShell>,
    );

    expect(screen.getByRole('main')).toContainElement(screen.getByText('Risk map'));
  });

  it('keeps navigation, banner, and screen all present', () => {
    render(
      <AppShell now={FIXED_MOMENT} currentPath="/risk-map">
        <p>Risk map</p>
      </AppShell>,
    );

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('marks the rail item for the screen being shown', () => {
    render(
      <AppShell now={FIXED_MOMENT} currentPath="/pipeline-health">
        <p>Health</p>
      </AppShell>,
    );

    expect(screen.getByRole('link', { name: 'Pipeline health' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('has exactly one main landmark, so screen readers do not have to choose', () => {
    render(
      <AppShell now={FIXED_MOMENT} currentPath="/risk-map">
        <p>Risk map</p>
      </AppShell>,
    );

    expect(screen.getAllByRole('main')).toHaveLength(1);
  });
});
