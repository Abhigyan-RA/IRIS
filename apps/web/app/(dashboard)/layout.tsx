import type { ReactNode } from 'react';
import { AppShell } from '../../components/shell/AppShell';

/**
 * Props for the dashboard layout.
 */
interface DashboardLayoutProps {
  /** The screen being shown. */
  children: ReactNode;
}

/**
 * Wraps every dashboard screen in the shared frame.
 *
 * Grouping the screens under one layout means the rail and top bar are mounted once
 * and stay put while the reader moves between screens, rather than being torn down
 * and rebuilt on each navigation.
 *
 * @param props - The screen to frame.
 * @returns The framed screen.
 */
export default function DashboardLayout({ children }: DashboardLayoutProps): ReactNode {
  return <AppShell>{children}</AppShell>;
}
