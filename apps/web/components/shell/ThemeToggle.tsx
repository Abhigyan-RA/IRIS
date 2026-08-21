'use client';

import { Moon, Sun } from 'lucide-react';
import { useSyncExternalStore, type ReactNode } from 'react';

/**
 * Where the reader's theme choice is kept.
 *
 * Exported so the script that applies the theme before the first paint, and the
 * tests, refer to one name rather than repeating a string that could drift.
 */
export const THEME_STORAGE_KEY = 'shadow-cpi-theme';

/** The two themes the interface ships. */
export type Theme = 'dark' | 'light';

/**
 * Listeners notified when the theme changes.
 *
 * The theme lives on the document element and in storage rather than in React
 * state, because a script applies it before React loads to avoid a flash of the
 * wrong colours. React therefore subscribes to it as an external value instead of
 * owning it, which is also what keeps server and browser markup in agreement.
 */
const listeners = new Set<() => void>();

/**
 * Subscribe to theme changes.
 *
 * @param onChange - Called whenever the theme changes, including in another tab.
 * @returns A function that removes the subscription.
 */
function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener('storage', onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener('storage', onChange);
  };
}

/**
 * Read the theme currently applied to the document.
 *
 * @returns The active theme.
 */
function readTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

/**
 * The theme assumed while rendering on the server.
 *
 * @returns Dark, which is the default this interface is designed for.
 */
function readServerTheme(): Theme {
  return 'dark';
}

/**
 * Read the theme to start from when nothing has been applied yet.
 *
 * Only an explicit choice changes the answer. The interface is dark by design, not
 * by preference: these screens are built to be read for long stretches, where a
 * bright page is tiring and washes out the coloured signals. So the operating system
 * setting is deliberately not consulted, and a reader who wants light picks it once
 * and it is remembered.
 *
 * @returns The theme to apply.
 */
export function preferredTheme(): Theme {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === 'light' ? 'light' : 'dark';
}

/**
 * Apply a theme to the document and remember it.
 *
 * @param theme - The theme to apply.
 */
function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  for (const listener of listeners) {
    listener();
  }
}

/**
 * The dark and light control shown in the top bar.
 *
 * Two buttons rather than one switch, because the design shows both states and a
 * reader should be able to see which one is active without interpreting an icon.
 * Choosing one restyles every screen at once, since all colours resolve through the
 * theme tokens.
 *
 * @returns The control.
 */
export function ThemeToggle(): ReactNode {
  const theme = useSyncExternalStore(subscribe, readTheme, readServerTheme);

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className="flex items-center gap-1 rounded-pill border border-hairline bg-panel p-1"
    >
      <ThemeButton
        label="Dark theme"
        active={theme === 'dark'}
        onSelect={() => {
          applyTheme('dark');
        }}
      >
        <Moon aria-hidden="true" className="h-4 w-4" />
      </ThemeButton>
      <ThemeButton
        label="Light theme"
        active={theme === 'light'}
        onSelect={() => {
          applyTheme('light');
        }}
      >
        <Sun aria-hidden="true" className="h-4 w-4" />
      </ThemeButton>
    </div>
  );
}

/**
 * Props for one theme choice.
 */
interface ThemeButtonProps {
  /** Name announced to assistive technology. */
  label: string;
  /** Whether this choice is the active one. */
  active: boolean;
  /** Chooses this theme. */
  onSelect: () => void;
  /** The icon. */
  children: ReactNode;
}

/**
 * One theme choice.
 *
 * @param props - The label, active state, handler, and icon.
 * @returns The button.
 */
function ThemeButton({ label, active, onSelect, children }: ThemeButtonProps): ReactNode {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      onClick={onSelect}
      className={`rounded-pill p-1.5 transition-colors ${
        active ? 'bg-accent-wash text-accent' : 'text-ink-faint hover:text-ink-muted'
      }`}
    >
      {children}
    </button>
  );
}
