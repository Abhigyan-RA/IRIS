import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { THEME_STORAGE_KEY, ThemeToggle, preferredTheme } from './ThemeToggle';

function appliedTheme(): string | undefined {
  return document.documentElement.dataset.theme;
}

/**
 * jsdom does not implement media queries, so the system preference is stubbed. The
 * default answer is "not light", which matches a machine set to a dark appearance.
 */
function stubSystemPrefersLight(prefersLight: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: prefersLight,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  stubSystemPrefersLight(false);
});

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

describe('ThemeToggle', () => {
  it('offers a dark and a light choice, each with a readable name', () => {
    render(<ThemeToggle />);

    expect(screen.getByRole('button', { name: 'Dark theme' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Light theme' })).toBeInTheDocument();
  });

  it('is grouped and labelled, so its two buttons read as one control', () => {
    render(<ThemeToggle />);

    expect(screen.getByRole('group', { name: 'Colour theme' })).toBeInTheDocument();
  });

  it('shows dark as active when nothing else has been applied', () => {
    render(<ThemeToggle />);

    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('reflects the theme already applied to the document rather than assuming one', () => {
    // A script applies the stored theme before React loads, so the control reads the
    // document instead of deciding for itself. Otherwise the two could disagree.
    document.documentElement.dataset.theme = 'light';

    render(<ThemeToggle />);

    expect(screen.getByRole('button', { name: 'Light theme' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('applies the light theme to the document when chosen', async () => {
    render(<ThemeToggle />);

    await userEvent.click(screen.getByRole('button', { name: 'Light theme' }));

    expect(appliedTheme()).toBe('light');
    expect(screen.getByRole('button', { name: 'Light theme' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('returns to dark when chosen again', async () => {
    render(<ThemeToggle />);

    await userEvent.click(screen.getByRole('button', { name: 'Light theme' }));
    await userEvent.click(screen.getByRole('button', { name: 'Dark theme' }));

    expect(appliedTheme()).toBe('dark');
  });

  it('remembers the choice, so a reload does not undo it', async () => {
    render(<ThemeToggle />);

    await userEvent.click(screen.getByRole('button', { name: 'Light theme' }));

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('can be operated from the keyboard alone', async () => {
    render(<ThemeToggle />);

    screen.getByRole('button', { name: 'Light theme' }).focus();
    await userEvent.keyboard('{Enter}');

    expect(appliedTheme()).toBe('light');
  });
});

describe('preferredTheme', () => {
  it('prefers a stored choice over the system setting', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');

    expect(preferredTheme()).toBe('light');
  });

  it('falls back to dark, which is the default this interface is designed for', () => {
    expect(preferredTheme()).toBe('dark');
  });

  it('ignores a stored value that is not a theme', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia');

    expect(preferredTheme()).toBe('dark');
  });

  it('does not follow the system setting, because the design is dark by intent', () => {
    stubSystemPrefersLight(true);

    expect(preferredTheme()).toBe('dark');
  });
});
