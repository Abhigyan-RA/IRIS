import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NAV_ITEMS, NavRail } from './NavRail';

vi.mock('next/navigation', () => ({
  usePathname: () => '/risk-map',
}));

describe('NavRail', () => {
  it('is a labelled navigation landmark', () => {
    render(<NavRail currentPath="/risk-map" />);

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
  });

  it('offers every screen', () => {
    render(<NavRail currentPath="/risk-map" />);

    for (const item of NAV_ITEMS) {
      expect(screen.getByRole('link', { name: item.label })).toBeInTheDocument();
    }
  });

  it('names every icon-only link, since an unlabelled icon is a guess', () => {
    render(<NavRail currentPath="/risk-map" />);

    for (const link of screen.getAllByRole('link')) {
      expect(link).toHaveAccessibleName();
    }
  });

  it('marks the current screen for assistive technology, not only by colour', () => {
    render(<NavRail currentPath="/institutional" />);

    expect(screen.getByRole('link', { name: 'Institutional sentiment' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('marks only one screen as current', () => {
    render(<NavRail currentPath="/institutional" />);

    const current = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'page');
    expect(current).toHaveLength(1);
  });

  it('treats a nested route as being on its section', () => {
    render(<NavRail currentPath="/ripple/Copper" />);

    expect(screen.getByRole('link', { name: 'Ripple effect' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('orders the screens the way a reader moves through them', () => {
    expect(NAV_ITEMS.map((item) => item.href)).toEqual([
      '/risk-map',
      '/ripple',
      '/institutional',
      '/pipeline-health',
      '/copilot',
    ]);
  });
});
