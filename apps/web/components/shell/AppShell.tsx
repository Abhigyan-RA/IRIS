import { Search } from 'lucide-react';
import type { ReactNode } from 'react';
import { LivePill } from './LivePill';
import { NavRail } from './NavRail';
import { ThemeToggle } from './ThemeToggle';
import { UtcClock } from './UtcClock';

/**
 * Props for {@link TopBar}.
 */
export interface TopBarProps {
  /** How long ago data was last refreshed, phrased for reading. */
  updatedLabel: string;
  /** Placeholder for the search field, which differs per screen in the design. */
  searchPlaceholder?: string | undefined;
  /** Fixed moment for the clock, used by tests and Storybook. */
  now?: Date | undefined;
}

/**
 * The bar across the top of every screen.
 *
 * It carries the product name, whether collection is running, a search field, and
 * the UTC clock. The clock is not decoration: every figure on these screens is
 * timestamped in UTC, so the reader needs the same reference visible.
 *
 * @param props - Refresh label, search placeholder, and optional fixed moment.
 * @returns The bar.
 */
export function TopBar({
  updatedLabel,
  searchPlaceholder = 'Search asset class, ticker, region',
  now,
}: TopBarProps): ReactNode {
  return (
    <header className="sticky top-0 z-20 flex h-topbar items-center gap-4 border-b border-hairline bg-canvas/95 px-6 backdrop-blur">
      <p className="shrink-0 text-sm font-semibold tracking-wide text-ink uppercase">Shadow CPI</p>
      <div className="hidden min-w-0 lg:block">
        <LivePill updatedLabel={updatedLabel} />
      </div>

      <div className="ml-auto flex min-w-0 shrink items-center gap-3 sm:gap-4">
        <div className="relative hidden md:block">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-ink-faint"
          />
          <input
            type="search"
            aria-label="Search"
            placeholder={searchPlaceholder}
            className="w-44 rounded-card border border-hairline bg-panel py-2 pr-3 pl-9 text-sm text-ink placeholder:text-ink-faint lg:w-64"
          />
        </div>
        {/* The clock is dropped before the theme control on a narrow screen: it is
            context, while the control is something the reader acts on. */}
        <div className="hidden shrink-0 md:block">
          <UtcClock now={now} />
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}

/**
 * Props for {@link AppShell}.
 */
export interface AppShellProps {
  /** The screen being shown. */
  children: ReactNode;
  /** How long ago data was last refreshed. */
  updatedLabel?: string;
  /** Placeholder for the search field. */
  searchPlaceholder?: string | undefined;
  /** Fixed moment for the clock, used by tests and Storybook. */
  now?: Date | undefined;
  /** Current path, used by tests and Storybook to mark the active rail item. */
  currentPath?: string | undefined;
}

/**
 * The frame every screen sits in: icon rail, top bar, and the screen itself.
 *
 * The rail and bar are fixed and the screen scrolls, so the reader never loses the
 * navigation or the clock while reading a long feed.
 *
 * @param props - The screen and the frame's context.
 * @returns The application frame.
 */
export function AppShell({
  children,
  updatedLabel = 'just now',
  searchPlaceholder,
  now,
  currentPath,
}: AppShellProps): ReactNode {
  return (
    <div className="flex min-h-screen bg-canvas">
      <NavRail currentPath={currentPath} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar updatedLabel={updatedLabel} searchPlaceholder={searchPlaceholder} now={now} />
        <main className="min-w-0 flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
