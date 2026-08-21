'use client';

import { Activity, Building2, Globe, MessageCircle, Network } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ComponentType, ReactNode } from 'react';

/**
 * One destination in the rail.
 */
export interface NavItem {
  /** Route the item leads to. */
  href: string;
  /** What the item is called, used as its accessible name. */
  label: string;
  /** Icon component from the icon library. */
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>;
}

/**
 * The five screens, in the order a reader uses them: see what changed, find out
 * what it affects, check how the professionals are positioned, confirm the pipeline
 * is honest, then ask a question in words.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: '/risk-map', label: 'Global risk map', icon: Globe },
  { href: '/ripple', label: 'Ripple effect', icon: Network },
  { href: '/institutional', label: 'Institutional sentiment', icon: Building2 },
  { href: '/pipeline-health', label: 'Pipeline health', icon: Activity },
  { href: '/copilot', label: 'Ask the data', icon: MessageCircle },
];

/**
 * Props for {@link NavRail}.
 */
export interface NavRailProps {
  /**
   * Current path. Passed in by tests and Storybook; the running app reads it from
   * the router.
   */
  currentPath?: string | undefined;
}

/**
 * The fixed icon rail down the left edge.
 *
 * Icon-only navigation saves horizontal space for data, but an unlabelled icon is
 * a guessing game, so every item carries an accessible name and a tooltip, and the
 * current item is marked for assistive technology rather than by colour alone.
 *
 * @param props - Optionally the current path.
 * @returns The rail.
 */
export function NavRail({ currentPath }: NavRailProps): ReactNode {
  const pathname = usePathname();
  const active = currentPath ?? pathname;

  return (
    <nav
      aria-label="Main navigation"
      className="sticky top-0 flex h-screen w-rail flex-col items-center gap-2 border-r border-hairline bg-rail py-4"
    >
      <Link
        href="/risk-map"
        aria-label="Shadow CPI home"
        className="mb-8 flex h-10 w-10 items-center justify-center rounded-card border border-accent text-accent"
      >
        <span aria-hidden="true" className="text-lg font-semibold">
          S
        </span>
      </Link>

      {NAV_ITEMS.map((item) => {
        const isActive = active.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.label}
            aria-label={item.label}
            aria-current={isActive ? 'page' : undefined}
            className={`flex h-11 w-11 items-center justify-center rounded-card border transition-colors ${
              isActive
                ? 'border-accent bg-accent-wash text-accent'
                : 'border-transparent text-ink-faint hover:border-hairline hover:text-ink'
            }`}
          >
            <Icon aria-hidden="true" className="h-5 w-5" />
          </Link>
        );
      })}
    </nav>
  );
}
