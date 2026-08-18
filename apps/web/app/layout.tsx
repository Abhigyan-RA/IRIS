import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: 'Shadow CPI',
  description:
    'Alternative data intelligence: daily freight, energy, metals, agriculture, and institutional signals',
};

/**
 * Props for the root layout.
 */
interface RootLayoutProps {
  /** Page content rendered inside the document body. */
  children: ReactNode;
}

/**
 * Root layout wrapping every dashboard route.
 *
 * @param props - Layout props containing the routed page content.
 * @returns The HTML document shell.
 */
export default function RootLayout({ children }: RootLayoutProps): ReactNode {
  return (
    // suppressHydrationWarning applies to this element only. Browser extensions
    // commonly add attributes to the root element before React loads, which React then
    // reports as a mismatch it cannot patch. Suppressing it here keeps a real mismatch
    // inside the application visible, because the suppression does not extend to
    // children.
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
